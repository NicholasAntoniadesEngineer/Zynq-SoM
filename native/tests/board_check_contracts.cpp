#include "schgen/board_check.hpp"
#include "schgen/catalog.hpp"
#include "schgen/json.hpp"

#include <unistd.h>

#include <algorithm>
#include <cmath>
#include <set>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>

namespace {
namespace fs = std::filesystem;
using namespace schgen;

std::size_t checks = 0;
void require(bool value, const std::string& why) { ++checks; if (!value) throw std::runtime_error(why); }

constexpr int json_digits = 17;
const char* const board_name = "devkit_mini";
const char* const run_config_name = "schgen.json";
const char* const absent_folder = "parts";

std::string read(const fs::path& path) {
    std::ifstream in(path, std::ios::binary);
    require(bool(in), "read " + path.string());
    return {std::istreambuf_iterator<char>(in), {}};
}
void write(const fs::path& path, const std::string& text) {
    fs::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary);
    out << text;
    require(bool(out), "write " + path.string());
}
std::string quote(const std::string& text) {
    std::string out = "\"";
    for (char c : text) {
        if (c == '"' || c == '\\') { out += '\\'; out += c; }
        else if (c == '\n') out += "\\n";
        else out += c;
    }
    return out + "\"";
}
std::string dump(const JsonNode& node) {
    switch (node.kind) {
    case JsonKind::Null: return "null";
    case JsonKind::Bool: return node.bool_value ? "true" : "false";
    case JsonKind::String: return quote(node.string_value);
    case JsonKind::Number: { std::ostringstream out; out << std::setprecision(json_digits) << node.number_value; return out.str(); }
    case JsonKind::Array: { std::string out = "["; for (const auto& item : node.array_value) { if (out.size() > 1) out += ","; out += dump(item); } return out + "]"; }
    case JsonKind::Object: { std::string out = "{"; for (const auto& [key, value] : node.object_value) { if (out.size() > 1) out += ","; out += quote(key) + ":" + dump(value); } return out + "}"; }
    }
    throw std::logic_error("json kind");
}
JsonNode* member(JsonNode& document, const std::string& path) {
    JsonNode* node = &document;
    std::size_t start = 0;
    for (;;) {
        const auto dot = path.find('.', start);
        const std::string key = path.substr(start, dot == std::string::npos ? std::string::npos : dot - start);
        auto found = std::find_if(node->object_value.begin(), node->object_value.end(), [&](const auto& entry) { return entry.first == key; });
        if (found == node->object_value.end()) return nullptr;
        node = &found->second;
        if (dot == std::string::npos) return node;
        start = dot + 1;
    }
}
void erase_member(JsonNode& document, const std::string& path) {
    const auto dot = path.rfind('.');
    JsonNode* parent = dot == std::string::npos ? &document : member(document, path.substr(0, dot));
    require(parent != nullptr, "parent of " + path);
    const std::string key = dot == std::string::npos ? path : path.substr(dot + 1);
    auto& entries = parent->object_value;
    const auto before = entries.size();
    entries.erase(std::remove_if(entries.begin(), entries.end(), [&](const auto& entry) { return entry.first == key; }), entries.end());
    require(entries.size() + 1 == before, "removed " + path);
}
JsonNode text_node(const std::string& value) { JsonNode node; node.kind = JsonKind::String; node.string_value = value; return node; }
JsonNode number_node(double value) { JsonNode node; node.kind = JsonKind::Number; node.number_value = value; return node; }
JsonNode object_node() { JsonNode node; node.kind = JsonKind::Object; return node; }

struct Scratch {
    fs::path root;
    Scratch() { auto p = (fs::temp_directory_path() / "board-check-XXXXXX").string(); require(::mkdtemp(p.data()) != nullptr, "scratch"); root = p; }
    ~Scratch() { std::error_code e; fs::remove_all(root, e); }
};

struct Bench {
    fs::path repository, board, config;
    std::map<fs::path, std::string> saved;
    BoardDefinitionCheck check() const { return check_board_definition(repository, board, config); }
    void keep(const fs::path& path) { if (!saved.count(path)) saved[path] = fs::exists(path) ? read(path) : std::string(); }
    void edit(const fs::path& path, const std::function<void(JsonNode&)>& change) {
        keep(path);
        JsonNode document = parse_json_file(path.string());
        change(document);
        write(path, dump(document));
    }
    void put(const fs::path& path, const std::string& text) { keep(path); write(path, text); }
    void remove(const fs::path& path) { keep(path); fs::remove(path); }
    void restore() {
        for (const auto& [path, text] : saved) write(path, text);
        saved.clear();
    }
};

const BoardRequirement& row_of(const BoardDefinitionCheck& check, const BoardRequirement& wanted) {
    const auto found = std::find_if(check.rows.begin(), check.rows.end(), [&](const BoardRequirement& row) { return row.file == wanted.file && row.item == wanted.item; });
    require(found != check.rows.end(), "row disappeared: " + wanted.file + " " + wanted.item);
    return *found;
}

std::vector<std::string> missing_rows(const BoardDefinitionCheck& check) {
    std::vector<std::string> out;
    for (const auto& row : check.rows) if (row.status == RequirementStatus::missing) out.push_back(row.file + " " + row.item);
    return out;
}

BoardRequirement requirement(const std::string& file, const std::string& item) {
    BoardRequirement row;
    row.file = file;
    row.item = item;
    return row;
}
bool removal(Bench& bench, const BoardRequirement& row) {
    const auto board_file = [&](const std::string& name) { return bench.board / name; };
    if (row.file == "run config") {
        if (row.item == "file") { bench.config = bench.config.parent_path() / "absent.json"; return true; }
        bench.edit(bench.config, [&](JsonNode& document) { erase_member(document, row.item); });
        return true;
    }
    if (row.item == "file" && row.file == "module folder/module.json") {
        bench.edit(board_file("board.json"), [&](JsonNode& document) { *member(document, "module.folder") = text_node(absent_folder); });
        return true;
    }
    if (row.item == "file") { bench.remove(board_file(row.file)); return true; }
    for (const char* document : {"board.json", "project.json", "som_mapping.json"})
        if (row.file == document && row.item.find(' ') == std::string::npos && row.item != "loads" && row.item.rfind("sheets.", 0) != 0) {
            bench.edit(board_file(row.file), [&](JsonNode& json) { erase_member(json, row.item); });
            return true;
        }
    return false;
}

bool corruption(Bench& bench, const BoardRequirement& row) {
    const auto board_file = [&](const std::string& name) { return bench.board / name; };
    const auto add_key = [&](const std::string& name) {
        bench.edit(board_file(name), [](JsonNode& document) { document.object_value.emplace_back("unread_key", number_node(1)); });
    };
    if (row.item == "loads" && (row.file == "board.json" || row.file == "som_mapping.json")) { add_key(row.file); return true; }
    if (row.file == "project.json" && row.item == "loads") {
        bench.edit(board_file(row.file), [](JsonNode& document) { *member(document, "escape.genuine_pairs") = text_node("four"); });
        return true;
    }
    if (row.item == "loads" && row.file == "module folder/module.json") return removal(bench, requirement(row.file, "file"));
    if (row.item == "loads" && row.file == "module folder/som_interface.json") return removal(bench, requirement("module folder/module.json", "file"));
    if (row.file == "escape_triage.json" || row.file == "research/si_spec.json" || row.file == "floorplan.json") { bench.put(board_file(row.file), "[]"); return true; }
    if (row.file == "sheet_index.json") { bench.put(board_file(row.file), "{\"power\": -1}"); return true; }
    if (row.file == "component_basis.json") { bench.put(board_file(row.file), "{\"schema\": \"schgen.component_basis/1\", \"uses\": [], \"sheets\": []}"); return true; }
    if (row.file == "board.json" && row.item == "power") {
        bench.edit(board_file(row.file), [](JsonNode& document) { member(document, "power.rails")->array_value.clear(); });
        return true;
    }
    if (row.file == "board.json" && row.item.rfind("sheets.", 0) == 0) {
        const std::string sheet = row.item.substr(std::string("sheets.").size());
        bench.edit(board_file(row.file), [&](JsonNode& document) {
            for (auto& entry : member(document, "sheets")->array_value) {
                if (member(entry, "name")->string_value != sheet) continue;
                if (JsonNode* connector = member(entry, "module_connector")) *connector = text_node("J0");
                else {
                    JsonNode* settings = member(entry, "settings");
                    if (!settings) { entry.object_value.emplace_back("settings", object_node()); settings = member(entry, "settings"); }
                    settings->object_value.emplace_back("unread_setting", number_node(1));
                }
            }
        });
        return true;
    }
    if (row.file == "board.json" && row.item == "sheet roles") return corruption(bench, requirement(row.file, "sheets.som_j1"));
    if (row.file == "parts/part_facts.json" && row.item != "loads") return corruption(bench, requirement("board.json", "sheets.som_j1"));
    return false;
}

void contracts(const fs::path& repository) {
    Scratch scratch;
    for (const char* name : {"carrier", "devkit_mini"}) {
        const auto check = check_board_definition(repository, repository / name, repository / run_config_name);
        require(check.ok(), std::string("a building board defines everything: ") + name + "\n" + check.text());
    }
    Bench bench{repository, scratch.root / board_name, scratch.root / run_config_name, {}};
    fs::copy(repository / board_name, bench.board, fs::copy_options::recursive);
    write(bench.config, read(repository / run_config_name));
    const auto baseline = bench.check();
    require(baseline.ok(), "a copy outside the repository checks the same:\n" + baseline.text());
    std::size_t removals = 0, corruptions = 0;
    const std::set<std::pair<std::string, std::string>> shared{{"parts/part_facts.json", "loads"}};
    for (const auto& row : baseline.rows) {
        if (row.status == RequirementStatus::absent) continue;
        if (removal(bench, row)) {
            const auto mutated = bench.check();
            const auto missing = missing_rows(mutated);
            if (row.required) {
                require(missing == std::vector<std::string>{row.file + " " + row.item},
                        "removing " + row.file + " " + row.item + " must report exactly that row missing:\n" + mutated.text());
                require(!mutated.ok(), "a removed requirement fails the check: " + row.file + " " + row.item);
            } else {
                require(missing.empty() && row_of(mutated, row).status == RequirementStatus::absent,
                        "removing optional " + row.file + " " + row.item + " reports it absent and nothing missing:\n" + mutated.text());
            }
            ++removals;
        } else if (corruption(bench, row)) {
            const auto mutated = bench.check();
            require(row_of(mutated, row).status != RequirementStatus::present && !mutated.ok(),
                    "corrupting " + row.file + " " + row.item + " must leave that row not present:\n" + mutated.text());
            ++corruptions;
        } else {
            require(shared.count({row.file, row.item}) == 1, "every row has a mutation; none for " + row.file + " " + row.item);
        }
        bench.config = scratch.root / run_config_name;
        bench.restore();
        require(bench.check().text() == baseline.text(), "mutation restored: " + row.file + " " + row.item);
    }
    require(removals > 0 && corruptions > 0, "both kinds of mutation exercised");
    std::cout << "board check: " << removals << " removals, " << corruptions << " corruptions, ";
}
}

int main(int argc, char** argv) {
    try {
        require(argc == 3, "usage: board_check_contracts REPOSITORY CATALOG");
        require(open_part_catalog(argv[2]), "open catalog");
        contracts(fs::weakly_canonical(argv[1]));
        close_part_catalog();
        std::cout << checks << " checks passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "board check contracts FAILED: " << error.what() << '\n';
        return 1;
    }
}
