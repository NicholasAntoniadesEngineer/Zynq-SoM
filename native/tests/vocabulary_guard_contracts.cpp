#include "schgen/json.hpp"
#include "schgen/project_authoring.hpp"

#include <algorithm>
#include <cctype>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

namespace fs = std::filesystem;
using schgen::JsonKind;
using schgen::JsonNode;

constexpr std::size_t name_prefix_floor = 4;
constexpr std::size_t part_prefix_floor = 5;
constexpr std::size_t shown_matches_limit = 6;
constexpr const char* allowlist_schema = "schgen.vocabulary_allowlist/1";
constexpr const char* allowlist_relative = "native/tests/data/vocabulary_allowlist.json";
constexpr const char* part_ratings_relative = "parts/part_ratings.json";

const std::vector<std::string> category_names{"board", "subsystem", "module", "part", "reference"};
const std::set<std::string> name_segments{"name", "sheet", "scope", "group", "project", "board"};
const std::set<std::string> call_names{"starts", "starts_with", "rfind", "find", "compare", "count", "at", "sheet"};
const std::set<std::string> boundary_punct{"&&", "||", ",", ";", "{", "}", "?", ":", "=", "==", "!="};
const std::set<std::string> boundary_words{"return", "case"};
const std::set<std::string> string_prefixes{"u8", "u", "U", "L", "R", "u8R", "uR", "UR", "LR"};
const std::set<std::string> char_prefixes{"u8", "u", "U", "L"};
const std::string piece_separators = ":/ ";
const std::string two_char_ops[] = {"==", "!=", "&&", "||", "->", "::"};

struct Vocabulary {
    std::set<std::string> board_strong, board_generic, subsystem_strong, subsystem_generic;
    std::set<std::string> module_strong, module_prefix, part, reference;
    std::vector<std::vector<std::string>> board_runs, subsystem_runs, module_runs, part_runs;
};

struct Match {
    std::string category;
    std::size_t line;
    std::string text;
};

using Counts = std::map<std::string, std::map<std::string, std::size_t>>;

struct Allowlist {
    std::set<std::string> fixtures;
    Counts offenders;
};

enum class Kind { identifier, text, character, number, punct };

struct Token {
    Kind kind;
    std::string text;
    std::size_t line;
};

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

bool identifier_char(char c) { return std::isalnum(static_cast<unsigned char>(c)) != 0 || c == '_'; }

JsonNode load_json(const fs::path& path) { return schgen::parse_json_file(path.string()); }

const JsonNode& require_field(const JsonNode& node, const std::string& key, JsonKind kind, const std::string& where) {
    require(node.kind == JsonKind::Object, where + ": not an object");
    const JsonNode* field = schgen::object_field(node, key);
    require(field != nullptr, where + ": missing key \"" + key + "\"");
    require(field->kind == kind, where + ": key \"" + key + "\" has the wrong type");
    return *field;
}

std::vector<std::string> segments_of(const std::string& word) {
    std::vector<std::string> out;
    std::string current;
    const auto flush = [&] {
        if (!current.empty()) out.push_back(current);
        current.clear();
    };
    for (std::size_t at = 0; at < word.size(); ++at) {
        const char c = word[at];
        if (c == '_') {
            flush();
            continue;
        }
        const bool upper = std::isupper(static_cast<unsigned char>(c)) != 0;
        if (upper && at > 0) {
            const bool after_lower = std::islower(static_cast<unsigned char>(word[at - 1])) != 0;
            const bool before_lower = at + 1 < word.size() && std::islower(static_cast<unsigned char>(word[at + 1])) != 0;
            const bool after_upper = std::isupper(static_cast<unsigned char>(word[at - 1])) != 0;
            if (after_lower || (after_upper && before_lower)) flush();
        }
        current.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    flush();
    return out;
}

bool pure_identifier(const std::string& word) {
    return !word.empty() && std::all_of(word.begin(), word.end(), identifier_char);
}

bool generic_word(const std::string& word) {
    return std::all_of(word.begin(), word.end(), [](char c) { return std::islower(static_cast<unsigned char>(c)) != 0; });
}

bool has_name_segment(const std::string& word) {
    const std::vector<std::string> parts = segments_of(word);
    return std::any_of(parts.begin(), parts.end(), [](const std::string& part) { return name_segments.count(part) != 0; });
}

bool contains_run(const std::vector<std::string>& hay, const std::vector<std::string>& needle) {
    return !needle.empty() && std::search(hay.begin(), hay.end(), needle.begin(), needle.end()) != hay.end();
}

bool contains_word(const std::string& hay, const std::string& token) {
    for (std::size_t at = hay.find(token); at != std::string::npos; at = hay.find(token, at + 1)) {
        const bool before = at == 0 || !identifier_char(hay[at - 1]);
        const bool after = at + token.size() >= hay.size() || !identifier_char(hay[at + token.size()]);
        if (before && after) return true;
    }
    return false;
}

bool strong_in(const std::set<std::string>& tokens, const std::string& literal) {
    return std::any_of(tokens.begin(), tokens.end(), [&](const std::string& token) { return contains_word(literal, token); });
}

bool prefix_of_any(const std::set<std::string>& names, const std::string& literal) {
    if (literal.size() < name_prefix_floor) return false;
    return std::any_of(names.begin(), names.end(), [&](const std::string& name) {
        return literal.size() < name.size() && name.compare(0, literal.size(), literal) == 0;
    });
}

bool part_piece(const Vocabulary& vocabulary, const std::string& piece) {
    if (piece.empty()) return false;
    if (vocabulary.part.count(piece) != 0) return true;
    if (piece.size() < part_prefix_floor) return false;
    const auto at = vocabulary.part.lower_bound(piece);
    return at != vocabulary.part.end() && at->compare(0, piece.size(), piece) == 0;
}

bool part_literal(const Vocabulary& vocabulary, const std::string& literal) {
    if (part_piece(vocabulary, literal)) return true;
    std::string piece;
    for (const char c : literal) {
        if (piece_separators.find(c) == std::string::npos) {
            piece.push_back(c);
            continue;
        }
        if (part_piece(vocabulary, piece)) return true;
        piece.clear();
    }
    return part_piece(vocabulary, piece);
}

std::size_t line_end(const std::string& text, std::size_t from) {
    std::size_t at = from;
    while (at < text.size() && text[at] != '\n') at += (text[at] == '\\' && at + 1 < text.size()) ? 2 : 1;
    return at;
}

std::vector<Token> lex(const std::string& text) {
    std::vector<Token> out;
    std::size_t at = 0, line = 1;
    bool line_start = true;
    const auto count_lines = [&](std::size_t from, std::size_t to) {
        for (std::size_t i = from; i < to && i < text.size(); ++i)
            if (text[i] == '\n') ++line;
    };
    const auto push_text = [&](const std::string& content, std::size_t where) {
        if (!out.empty() && out.back().kind == Kind::text) out.back().text += content;
        else out.push_back({Kind::text, content, where});
    };
    while (at < text.size()) {
        const char c = text[at];
        if (c == '\n') {
            ++line;
            ++at;
            line_start = true;
            continue;
        }
        if (std::isspace(static_cast<unsigned char>(c)) != 0) {
            ++at;
            continue;
        }
        if (c == '/' && at + 1 < text.size() && text[at + 1] == '/') {
            const std::size_t end = line_end(text, at);
            count_lines(at, end);
            at = end;
            continue;
        }
        if (c == '/' && at + 1 < text.size() && text[at + 1] == '*') {
            const std::size_t close = text.find("*/", at + 2);
            const std::size_t end = close == std::string::npos ? text.size() : close + 2;
            count_lines(at, end);
            at = end;
            continue;
        }
        if (c == '#' && line_start) {
            std::size_t word = at + 1;
            while (word < text.size() && (text[word] == ' ' || text[word] == '\t')) ++word;
            std::size_t word_end = word;
            while (word_end < text.size() && identifier_char(text[word_end])) ++word_end;
            if (text.compare(word, word_end - word, "include") == 0 && word_end > word) {
                at = line_end(text, word_end);
                continue;
            }
        }
        line_start = false;
        const bool word_start = std::isalpha(static_cast<unsigned char>(c)) != 0 || c == '_';
        if (word_start) {
            std::size_t end = at;
            while (end < text.size() && identifier_char(text[end])) ++end;
            const std::string word = text.substr(at, end - at);
            const bool quote_next = end < text.size() && text[end] == '"';
            const bool apostrophe_next = end < text.size() && text[end] == '\'';
            if (quote_next && string_prefixes.count(word) != 0 && word.back() == 'R') {
                const std::size_t open = text.find('(', end + 1);
                require(open != std::string::npos, "unterminated raw string at line " + std::to_string(line));
                const std::string closer = ")" + text.substr(end + 1, open - end - 1) + "\"";
                const std::size_t close = text.find(closer, open + 1);
                require(close != std::string::npos, "unterminated raw string at line " + std::to_string(line));
                push_text(text.substr(open + 1, close - open - 1), line);
                count_lines(at, close);
                at = close + closer.size();
                continue;
            }
            if ((quote_next && string_prefixes.count(word) != 0) || (apostrophe_next && char_prefixes.count(word) != 0)) {
                at = end;
                continue;
            }
            out.push_back({Kind::identifier, word, line});
            at = end;
            continue;
        }
        if (c == '"' || c == '\'') {
            std::size_t end = at + 1;
            while (end < text.size() && text[end] != c) end += text[end] == '\\' ? 2 : 1;
            require(end < text.size(), "unterminated literal at line " + std::to_string(line));
            const std::string content = text.substr(at + 1, end - at - 1);
            if (c == '"') push_text(content, line);
            else out.push_back({Kind::character, content, line});
            count_lines(at, end);
            at = end + 1;
            continue;
        }
        const bool digit_start = std::isdigit(static_cast<unsigned char>(c)) != 0 ||
            (c == '.' && at + 1 < text.size() && std::isdigit(static_cast<unsigned char>(text[at + 1])) != 0);
        if (digit_start) {
            std::size_t end = at;
            while (end < text.size()) {
                const char d = text[end];
                const bool exponent_sign = (d == '+' || d == '-') && end > at &&
                    std::string("eEpP").find(text[end - 1]) != std::string::npos;
                const bool separator = d == '\'' && end + 1 < text.size() && identifier_char(text[end + 1]);
                if (!identifier_char(d) && d != '.' && !exponent_sign && !separator) break;
                ++end;
            }
            out.push_back({Kind::number, text.substr(at, end - at), line});
            at = end;
            continue;
        }
        std::string punct(1, c);
        for (const std::string& op : two_char_ops)
            if (text.compare(at, op.size(), op) == 0) punct = op;
        out.push_back({Kind::punct, punct, line});
        at += punct.size();
    }
    return out;
}

bool is_punct(const std::vector<Token>& tokens, std::size_t at, const std::string& text) {
    return at < tokens.size() && tokens[at].kind == Kind::punct && tokens[at].text == text;
}

bool is_opener(const Token& token) {
    return token.kind == Kind::punct && (token.text == "(" || token.text == "[" || token.text == "{");
}

bool is_closer(const Token& token) {
    return token.kind == Kind::punct && (token.text == ")" || token.text == "]" || token.text == "}");
}

struct Brackets {
    std::vector<std::size_t> parent, close;
};

Brackets bracket_map(const std::vector<Token>& tokens) {
    Brackets brackets{std::vector<std::size_t>(tokens.size(), std::string::npos),
                      std::vector<std::size_t>(tokens.size(), std::string::npos)};
    std::vector<std::size_t> stack;
    for (std::size_t at = 0; at < tokens.size(); ++at) {
        if (is_closer(tokens[at]) && !stack.empty()) {
            brackets.close[stack.back()] = at;
            stack.pop_back();
        }
        brackets.parent[at] = stack.empty() ? std::string::npos : stack.back();
        if (is_opener(tokens[at])) stack.push_back(at);
    }
    return brackets;
}

bool operand_has_name(const std::vector<Token>& tokens, std::size_t from, bool forward) {
    std::size_t depth = 0;
    for (std::size_t at = from; at < tokens.size(); forward ? ++at : --at) {
        const Token& token = tokens[at];
        if (token.kind == Kind::identifier) {
            if (boundary_words.count(token.text) != 0) return false;
            if (has_name_segment(token.text)) return true;
        }
        if (token.kind == Kind::punct) {
            const bool deeper = forward ? is_opener(token) && token.text != "{" : is_closer(token) && token.text != "}";
            const bool shallower = forward ? is_closer(token) && token.text != "}" : is_opener(token) && token.text != "{";
            if (deeper) ++depth;
            else if (shallower) {
                if (depth == 0) return false;
                --depth;
            } else if (depth == 0 && boundary_punct.count(token.text) != 0) return false;
        }
        if (!forward && at == 0) break;
    }
    return false;
}

bool receiver_has_name(const std::vector<Token>& tokens, std::size_t function_at) {
    if (function_at < 2 || !(is_punct(tokens, function_at - 1, ".") || is_punct(tokens, function_at - 1, "->"))) return false;
    std::size_t depth = 0, at = function_at - 1;
    while (at > 0) {
        --at;
        const Token& token = tokens[at];
        if (token.kind == Kind::punct && (token.text == ")" || token.text == "]")) ++depth;
        else if (token.kind == Kind::punct && (token.text == "(" || token.text == "[")) {
            if (depth == 0) return false;
            --depth;
        } else if (depth == 0 && !(token.kind == Kind::identifier || is_punct(tokens, at, ".") ||
                                   is_punct(tokens, at, "->") || is_punct(tokens, at, "::"))) {
            return false;
        }
        if (token.kind == Kind::identifier && has_name_segment(token.text)) return true;
    }
    return false;
}

bool name_call_position(const std::vector<Token>& tokens, const Brackets& brackets, std::size_t at) {
    const std::size_t open = brackets.parent[at];
    if (open == std::string::npos || !is_punct(tokens, open, "(") || open == 0) return false;
    const Token& function = tokens[open - 1];
    if (function.kind != Kind::identifier || call_names.count(function.text) == 0) return false;
    if (has_name_segment(function.text) || receiver_has_name(tokens, open - 1)) return true;
    for (std::size_t other = open + 1; other < brackets.close[open] && other < tokens.size(); ++other)
        if (tokens[other].kind == Kind::identifier && has_name_segment(tokens[other].text)) return true;
    return false;
}

bool name_comparison_position(const std::vector<Token>& tokens, std::size_t at) {
    const auto comparison = [&](std::size_t index) { return is_punct(tokens, index, "==") || is_punct(tokens, index, "!="); };
    if (at >= 2 && comparison(at - 1) && operand_has_name(tokens, at - 2, false)) return true;
    return comparison(at + 1) && operand_has_name(tokens, at + 2, true);
}

bool name_list_position(const std::vector<Token>& tokens, const Brackets& brackets,
                        const std::vector<std::size_t>& strong_before, std::size_t at) {
    const auto element_edge = [&](std::size_t index) { return is_punct(tokens, index, ",") || is_punct(tokens, index, "}"); };
    const auto start_edge = [&](std::size_t index) { return is_punct(tokens, index, ",") || is_punct(tokens, index, "{"); };
    if (at == 0 || !start_edge(at - 1) || !element_edge(at + 1)) return false;
    std::size_t list = brackets.parent[at];
    while (list != std::string::npos && is_punct(tokens, list, "{")) {
        if (strong_before[brackets.close[list] == std::string::npos ? tokens.size() : brackets.close[list]] > strong_before[list]) return true;
        if (list == 0 || !start_edge(list - 1)) return false;
        list = brackets.parent[list];
    }
    return false;
}

std::vector<Match> scan(const Vocabulary& vocabulary, const std::string& text, bool fixture) {
    const std::vector<Token> tokens = lex(text);
    const Brackets brackets = bracket_map(tokens);
    const auto strong_name = [&](const std::string& literal, bool& board, bool& subsystem, bool& module) {
        board = strong_in(vocabulary.board_strong, literal);
        subsystem = strong_in(vocabulary.subsystem_strong, literal);
        module = strong_in(vocabulary.module_strong, literal) ||
            (prefix_of_any(vocabulary.module_prefix, literal) && vocabulary.subsystem_generic.count(literal) == 0 && vocabulary.board_generic.count(literal) == 0);
    };
    const auto subsystem_prefix = [&](const std::string& literal) {
        return prefix_of_any(vocabulary.subsystem_strong, literal) && vocabulary.subsystem_generic.count(literal) == 0 && vocabulary.board_generic.count(literal) == 0;
    };
    std::vector<std::size_t> strong_before(tokens.size() + 1, 0);
    for (std::size_t at = 0; at < tokens.size(); ++at) {
        bool board = false, subsystem = false, module = false;
        if (tokens[at].kind == Kind::text) strong_name(tokens[at].text, board, subsystem, module);
        strong_before[at + 1] = strong_before[at] + ((board || subsystem || module) ? 1 : 0);
    }
    std::vector<Match> matches;
    const auto add = [&](const std::string& category, const Token& token) { matches.push_back({category, token.line, token.text}); };
    for (std::size_t at = 0; at < tokens.size(); ++at) {
        const Token& token = tokens[at];
        if (token.kind == Kind::identifier) {
            const std::vector<std::string> parts = segments_of(token.text);
            const auto any_run = [&](const std::vector<std::vector<std::string>>& runs) {
                return std::any_of(runs.begin(), runs.end(), [&](const std::vector<std::string>& run) { return contains_run(parts, run); });
            };
            if (any_run(vocabulary.board_runs)) add("board", token);
            if (any_run(vocabulary.subsystem_runs)) add("subsystem", token);
            if (any_run(vocabulary.module_runs)) add("module", token);
            if (any_run(vocabulary.part_runs)) add("part", token);
            continue;
        }
        if (token.kind != Kind::text) continue;
        bool board = false, subsystem = false, module = false;
        strong_name(token.text, board, subsystem, module);
        const bool generic_board = vocabulary.board_generic.count(token.text) != 0;
        const bool generic_subsystem = vocabulary.subsystem_generic.count(token.text) != 0;
        bool named = false, named_known = false;
        const auto in_name_position = [&] {
            if (!named_known) {
                named = name_comparison_position(tokens, at) || name_call_position(tokens, brackets, at) ||
                    name_list_position(tokens, brackets, strong_before, at);
                named_known = true;
            }
            return named;
        };
        if (board || (generic_board && in_name_position())) add("board", token);
        if (subsystem || ((generic_subsystem || subsystem_prefix(token.text)) && in_name_position())) add("subsystem", token);
        if (module) add("module", token);
        if (part_literal(vocabulary, token.text)) add("part", token);
        if (!fixture && vocabulary.reference.count(token.text) != 0) add("reference", token);
    }
    return matches;
}

void add_runs(std::vector<std::vector<std::string>>& runs, const std::string& token) {
    if (pure_identifier(token)) runs.push_back(segments_of(token));
}

Vocabulary read_vocabulary(const fs::path& repository) {
    Vocabulary vocabulary;
    std::set<std::string> subsystem_names, module_sheets, board_names;
    for (const fs::path& folder : schgen::board_folders(repository)) {
        board_names.insert(folder.filename().string());
        const fs::path board_file = folder / "board.json";
        const JsonNode board = load_json(board_file);
        for (const JsonNode& sheet : require_field(board, "sheets", JsonKind::Array, board_file.string()).array_value) {
            const std::string name = schgen::require_string(sheet, "name", false, board_file.string());
            const JsonNode* connector = schgen::object_field(sheet, "module_connector");
            if (connector == nullptr) {
                subsystem_names.insert(name);
                continue;
            }
            require(connector->kind == JsonKind::String && !connector->string_value.empty(),
                    board_file.string() + ": key \"module_connector\" is not a non-empty string");
            module_sheets.insert(name);
            vocabulary.module_strong.insert(connector->string_value);
            vocabulary.reference.insert(connector->string_value);
        }
        const fs::path interface_file = folder / "som_interface.json";
        const JsonNode interface = load_json(interface_file);
        for (const auto& entry : require_field(interface, "connectors", JsonKind::Object, interface_file.string()).object_value) {
            vocabulary.module_strong.insert(entry.first);
            vocabulary.reference.insert(entry.first);
        }
    }
    for (const std::string& sheet : module_sheets) {
        std::string stem = sheet;
        while (!stem.empty() && std::isdigit(static_cast<unsigned char>(stem.back())) != 0) stem.pop_back();
        require(!stem.empty(), "module sheet name \"" + sheet + "\" is only digits");
        vocabulary.module_strong.insert(sheet);
        vocabulary.module_strong.insert(stem);
        vocabulary.module_prefix.insert(sheet);
        vocabulary.module_prefix.insert(stem);
    }
    for (const auto& entry : fs::directory_iterator(repository / "subsystems")) {
        if (!entry.is_directory()) continue;
        const fs::path file = entry.path() / "subsystem.json";
        const JsonNode node = load_json(file);
        subsystem_names.insert(schgen::require_string(node, "name", false, file.string()));
        for (const JsonNode& part : require_field(node, "parts", JsonKind::Array, file.string()).array_value)
            vocabulary.reference.insert(schgen::require_string(part, "ref", false, file.string()));
    }
    for (const auto& entry : fs::directory_iterator(repository / "parts")) {
        if (!entry.is_directory()) continue;
        const fs::path file = entry.path() / "part.json";
        const JsonNode node = load_json(file);
        vocabulary.part.insert(entry.path().filename().string());
        for (const char* key : {"mpn", "lcsc"}) {
            const std::string value = schgen::require_string(node, key, true, file.string());
            if (!value.empty()) vocabulary.part.insert(value);
        }
    }
    const fs::path ratings_file = repository / part_ratings_relative;
    const JsonNode ratings = load_json(ratings_file);
    for (const JsonNode& rating : require_field(ratings, "ratings", JsonKind::Array, ratings_file.string()).array_value)
        vocabulary.part.insert(schgen::require_string(rating, "lcsc", false, ratings_file.string()));
    for (const std::string& name : board_names) {
        (generic_word(name) ? vocabulary.board_generic : vocabulary.board_strong).insert(name);
        add_runs(vocabulary.board_runs, name);
    }
    for (const std::string& name : subsystem_names) {
        const bool generic = generic_word(name);
        (generic ? vocabulary.subsystem_generic : vocabulary.subsystem_strong).insert(name);
        if (!generic) add_runs(vocabulary.subsystem_runs, name);
    }
    for (const std::string& token : vocabulary.module_prefix) add_runs(vocabulary.module_runs, token);
    for (const std::string& token : vocabulary.part) add_runs(vocabulary.part_runs, token);
    return vocabulary;
}

Counts measure(const Vocabulary& vocabulary, const fs::path& repository, const std::set<std::string>& fixtures,
               std::set<std::string>& files, std::map<std::string, std::vector<Match>>& found) {
    Counts counts;
    for (const char* root : {"native/src", "native/include"})
        for (const auto& entry : fs::recursive_directory_iterator(repository / root)) {
            const std::string extension = entry.path().extension().string();
            if (entry.is_regular_file() && (extension == ".cpp" || extension == ".hpp"))
                files.insert(fs::relative(entry.path(), repository).generic_string());
        }
    for (const std::string& file : files) {
        std::ifstream stream(repository / file);
        require(static_cast<bool>(stream), file + ": cannot be read");
        const std::string text((std::istreambuf_iterator<char>(stream)), std::istreambuf_iterator<char>());
        std::vector<Match> matches = scan(vocabulary, text, fixtures.count(file) != 0);
        if (matches.empty()) continue;
        for (const Match& match : matches) ++counts[file][match.category];
        found[file] = std::move(matches);
    }
    return counts;
}

std::size_t reference_matches(const Vocabulary& vocabulary, const fs::path& repository, const std::string& file) {
    std::ifstream stream(repository / file);
    require(static_cast<bool>(stream), file + ": cannot be read");
    const std::string text((std::istreambuf_iterator<char>(stream)), std::istreambuf_iterator<char>());
    const std::vector<Match> matches = scan(vocabulary, text, false);
    return static_cast<std::size_t>(std::count_if(matches.begin(), matches.end(), [](const Match& m) { return m.category == "reference"; }));
}

Allowlist load_allowlist(const fs::path& file) {
    const JsonNode root = load_json(file);
    const std::string where = file.string();
    require(root.kind == JsonKind::Object, where + ": not an object");
    schgen::reject_unknown_keys(root, {"schema", "fixtures", "offenders"}, where);
    require(schgen::require_string(root, "schema", false, where) == allowlist_schema, where + ": key \"schema\" is not " + allowlist_schema);
    Allowlist list;
    for (const JsonNode& fixture : require_field(root, "fixtures", JsonKind::Array, where).array_value) {
        require(fixture.kind == JsonKind::String && !fixture.string_value.empty(), where + ": key \"fixtures\" holds a non-string entry");
        require(list.fixtures.insert(fixture.string_value).second, where + ": fixture " + fixture.string_value + " is listed twice");
    }
    const std::set<std::string> known(category_names.begin(), category_names.end());
    for (const auto& entry : require_field(root, "offenders", JsonKind::Object, where).object_value) {
        require(entry.second.kind == JsonKind::Object && !entry.second.object_value.empty(), where + ": offender " + entry.first + " is not a non-empty object");
        schgen::reject_unknown_keys(entry.second, known, where + " offender " + entry.first);
        for (const auto& count : entry.second.object_value) {
            const double value = count.second.number_value;
            require(count.second.kind == JsonKind::Number && value >= 1.0 && value == static_cast<double>(static_cast<std::size_t>(value)),
                    where + ": offender " + entry.first + " category " + count.first + " is not a positive integer");
            list.offenders[entry.first][count.first] = static_cast<std::size_t>(value);
        }
    }
    return list;
}

std::vector<std::string> compare_counts(const Counts& measured, const Allowlist& allowlist, const std::set<std::string>& scanned) {
    std::vector<std::string> failures;
    for (const auto& file : measured)
        for (const auto& category : file.second) {
            const auto listed_file = allowlist.offenders.find(file.first);
            const std::size_t listed = listed_file == allowlist.offenders.end() || listed_file->second.count(category.first) == 0
                ? 0 : listed_file->second.at(category.first);
            if (category.second == 0) continue;
            if (listed == 0)
                failures.push_back(file.first + " [" + category.first + "] has " + std::to_string(category.second) + " offences and is not in the allow-list");
            else if (category.second > listed)
                failures.push_back(file.first + " [" + category.first + "] rose from " + std::to_string(listed) + " to " + std::to_string(category.second));
            else if (category.second < listed)
                failures.push_back(file.first + " [" + category.first + "] fell from " + std::to_string(listed) + " to " + std::to_string(category.second) + "; lower the allow-list");
        }
    for (const auto& file : allowlist.offenders) {
        if (scanned.count(file.first) == 0) {
            failures.push_back(file.first + " is listed in the allow-list and does not exist");
            continue;
        }
        const auto measured_file = measured.find(file.first);
        for (const auto& category : file.second)
            if (measured_file == measured.end() || measured_file->second.count(category.first) == 0 || measured_file->second.at(category.first) == 0)
                failures.push_back(file.first + " [" + category.first + "] is listed with " + std::to_string(category.second) + " and has no offence; remove it from the allow-list");
    }
    return failures;
}

void expect_counts(const Vocabulary& vocabulary, const std::string& source, const std::map<std::string, std::size_t>& wanted, bool fixture = false) {
    std::map<std::string, std::size_t> actual;
    for (const Match& match : scan(vocabulary, source, fixture)) ++actual[match.category];
    require(actual == wanted, "self-test: `" + source + "` gave " + std::to_string(actual.size()) + " matching categories that differ from the wanted counts");
}

void expect_matches(const Vocabulary& vocabulary, const std::string& source, const std::string& category, std::size_t wanted) {
    expect_counts(vocabulary, source, wanted == 0 ? std::map<std::string, std::size_t>{} : std::map<std::string, std::size_t>{{category, wanted}});
}

void self_tests(const Vocabulary& vocabulary) {
    require(vocabulary.board_strong.count("devkit_mini") != 0 && vocabulary.board_generic.count("carrier") != 0,
            "self-test: the board vocabulary lacks devkit_mini or carrier");
    require(vocabulary.subsystem_generic.count("power") != 0 && vocabulary.subsystem_strong.count("power_som") != 0 &&
            vocabulary.subsystem_generic.count("ethernet") != 0 && vocabulary.module_strong.count("som_j") != 0,
            "self-test: the subsystem or module vocabulary lacks power, power_som, ethernet or som_j");
    require(part_literal(vocabulary, "LM61460") && vocabulary.reference.count("J1") != 0, "self-test: the part or reference vocabulary lacks LM61460 or J1");
    expect_matches(vocabulary, "const char* x = \"devkit_mini\";", "board", 1);
    expect_matches(vocabulary, "const char* x = \"LM61460\";", "part", 1);
    expect_matches(vocabulary, "const char* x = \"PCA9306DCUR:PCA9306DCUR\";", "part", 1);
    expect_matches(vocabulary, "bool b = starts(name, \"som_j\");", "module", 1);
    expect_matches(vocabulary, "bool b = (sheet == \"power\");", "subsystem", 1);
    expect_matches(vocabulary, "bool b = (\"power\" != sheet.name);", "subsystem", 1);
    expect_matches(vocabulary, "auto s = sheet(s, scope, \"power\");", "subsystem", 1);
    expect_matches(vocabulary, "const char* x = \"board\";", "subsystem", 0);
    expect_matches(vocabulary, "const char* x = \"user\";", "subsystem", 0);
    expect_matches(vocabulary, "bool b = starts(sheet, \"bringup\");", "subsystem", 1);
    expect_matches(vocabulary, "const char* x = \"board_aux\";", "subsystem", 1);
    expect_matches(vocabulary, "bool b = (n.net_class == \"power\");", "subsystem", 0);
    expect_matches(vocabulary, "std::string net_class = \"power\";", "subsystem", 0);
    expect_matches(vocabulary, "f(a, \"power\", b);", "subsystem", 0);
    expect_matches(vocabulary, "std::vector<std::string> classes{\"power\", \"signal\"};", "subsystem", 0);
    expect_matches(vocabulary, "std::map<std::string, int> m{{\"ethernet\", 14}, {\"power_som\", 25}};", "subsystem", 2);
    expect_matches(vocabulary, "int x = 0; // devkit_mini carrier power_som LM61460 J1", "board", 0);
    expect_matches(vocabulary, "/* devkit_mini\n carrier power_som LM61460 \"J1\" */ int x = 0;", "board", 0);
    expect_matches(vocabulary, "#include \"devkit_mini/LM61460.hpp\"\nint x = 0;", "board", 0);
    expect_matches(vocabulary, "// devkit_mini\nconst char* x = \"devkit_mini\";", "board", 1);
    expect_matches(vocabulary, "const char* x = R\"raw(devkit_mini)raw\";", "board", 1);
    expect_matches(vocabulary, "const char* x = \"devkit\" \"_mini\";", "board", 1);
    expect_matches(vocabulary, "auto r = som_j_rects;", "module", 1);
    expect_matches(vocabulary, "auto r = carrier_surface_requirement_declaration;", "board", 1);
    expect_matches(vocabulary, "auto r = power_checks;", "subsystem", 0);
    expect_counts(vocabulary, "const char* x = \"J1\";", {{"module", 1}, {"reference", 1}});
    expect_counts(vocabulary, "const char* x = \"J1\";", {{"module", 1}}, true);
    expect_counts(vocabulary, "const char* x = \"U1\";", {{"reference", 1}});
    expect_counts(vocabulary, "const char* x = \"U1\";", {}, true);
    const Counts measured{{"native/src/a.cpp", {{"board", 3}}}};
    const std::set<std::string> scanned{"native/src/a.cpp", "native/src/b.cpp"};
    require(compare_counts(measured, {{}, {{"native/src/a.cpp", {{"board", 3}}}}}, scanned).empty(), "self-test: an exact allow-list fails");
    require(compare_counts(measured, {{}, {{"native/src/a.cpp", {{"board", 2}}}}}, scanned).size() == 1, "self-test: a rise passes");
    require(compare_counts(measured, {{}, {{"native/src/a.cpp", {{"board", 4}}}}}, scanned).size() == 1, "self-test: a fall passes");
    require(compare_counts(measured, {{}, {}}, scanned).size() == 1, "self-test: an unlisted offender passes");
    require(compare_counts(measured, {{}, {{"native/src/a.cpp", {{"board", 3}, {"part", 1}}}}}, scanned).size() == 1, "self-test: an unlisted category count passes");
    require(compare_counts(measured, {{}, {{"native/src/a.cpp", {{"board", 3}}}, {"native/src/gone.cpp", {{"board", 1}}}}}, scanned).size() == 1,
            "self-test: a listed missing file passes");
}

void guard_holds(const fs::path& repository) {
    const Vocabulary vocabulary = read_vocabulary(repository);
    self_tests(vocabulary);
    const Allowlist allowlist = load_allowlist(repository / allowlist_relative);
    std::set<std::string> files;
    std::map<std::string, std::vector<Match>> found;
    const Counts measured = measure(vocabulary, repository, allowlist.fixtures, files, found);
    std::vector<std::string> failures = compare_counts(measured, allowlist, files);
    for (const std::string& file : allowlist.fixtures) {
        if (files.count(file) == 0) failures.push_back(file + " is listed as a fixture and does not exist");
        else if (reference_matches(vocabulary, repository, file) == 0) failures.push_back(file + " is listed as a fixture and has no reference offence; remove it from the fixtures");
    }
    if (failures.empty()) return;
    std::ostringstream message;
    message << "vocabulary guard: " << failures.size() << " difference(s) from " << allowlist_relative << "\n";
    for (const std::string& failure : failures) message << "  " << failure << "\n";
    for (const std::string& failure : failures) {
        const std::string file = failure.substr(0, failure.find(' '));
        const auto shown = found.find(file);
        if (shown == found.end()) continue;
        std::size_t listed = 0;
        for (const Match& match : shown->second) {
            if (listed++ == shown_matches_limit) break;
            message << "    " << file << ":" << match.line << " [" << match.category << "] " << match.text << "\n";
        }
    }
    throw std::runtime_error(message.str());
}

}

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: vocabulary_guard_contracts REPOSITORY");
        guard_holds(fs::absolute(argv[1]));
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 1;
    }
}
