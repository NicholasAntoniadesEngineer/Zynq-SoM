#include "schgen/json.hpp"

#include <cstdint>
#include <fstream>
#include <iterator>
#include <set>
#include <stdexcept>
#include <string>
#include <string_view>

namespace schgen {
namespace {

struct JsonParser {
    std::string_view text;
    std::size_t index = 0;
    std::string source_name;

    [[noreturn]] void fail(const std::string& detail) const {
        throw std::runtime_error("json " + source_name + ": " + detail);
    }

    bool at_end() const {
        return index >= text.size();
    }

    std::size_t skip_ws() {
        while (index < text.size()) {
            const char ch = text[index];
            if (ch != ' ' && ch != '\t' && ch != '\r' && ch != '\n') {
                break;
            }
            ++index;
        }
        return index;
    }

    void expect(char wanted) {
        skip_ws();
        if (at_end() || text[index] != wanted) {
            fail(std::string("expected '") + wanted + "'");
        }
        ++index;
    }

    JsonNode parse_value();

    JsonNode parse_string() {
        if (at_end() || text[index] != '"') {
            fail("expected string");
        }
        ++index;
        std::string out;
        while (!at_end()) {
            const unsigned char ch = static_cast<unsigned char>(text[index]);
            ++index;
            if (ch == '"') {
                JsonNode node;
                node.kind = JsonKind::String;
                node.string_value = std::move(out);
                return node;
            }
            if (ch == '\\') {
                if (at_end()) {
                    fail("unterminated string escape");
                }
                const char esc = text[index];
                ++index;
                if (esc == '"' || esc == '\\' || esc == '/') {
                    out.push_back(esc);
                } else if (esc == 'b') {
                    out.push_back('\b');
                } else if (esc == 'f') {
                    out.push_back('\f');
                } else if (esc == 'n') {
                    out.push_back('\n');
                } else if (esc == 'r') {
                    out.push_back('\r');
                } else if (esc == 't') {
                    out.push_back('\t');
                } else if (esc == 'u') {
                    if (index + 4 > text.size()) {
                        fail("truncated unicode escape");
                    }
                    uint32_t code = 0;
                    for (int digit_i = 0; digit_i < 4; ++digit_i) {
                        const char hex = text[index];
                        ++index;
                        code <<= 4;
                        if (hex >= '0' && hex <= '9') {
                            code |= static_cast<uint32_t>(hex - '0');
                        } else if (hex >= 'a' && hex <= 'f') {
                            code |= static_cast<uint32_t>(hex - 'a' + 10);
                        } else if (hex >= 'A' && hex <= 'F') {
                            code |= static_cast<uint32_t>(hex - 'A' + 10);
                        } else {
                            fail("invalid unicode escape");
                        }
                    }
                    if (code <= 0x7Fu) {
                        out.push_back(static_cast<char>(code));
                    } else if (code <= 0x7FFu) {
                        out.push_back(static_cast<char>(0xC0u | (code >> 6)));
                        out.push_back(static_cast<char>(0x80u | (code & 0x3Fu)));
                    } else {
                        out.push_back(static_cast<char>(0xE0u | (code >> 12)));
                        out.push_back(static_cast<char>(0x80u | ((code >> 6) & 0x3Fu)));
                        out.push_back(static_cast<char>(0x80u | (code & 0x3Fu)));
                    }
                } else {
                    fail("invalid string escape");
                }
                continue;
            }
            if (ch < 0x20) {
                fail("unescaped control character in string");
            }
            out.push_back(static_cast<char>(ch));
        }
        fail("unterminated string");
    }

    JsonNode parse_number() {
        const std::size_t start = index;
        if (!at_end() && text[index] == '-') {
            ++index;
        }
        if (at_end() || text[index] < '0' || text[index] > '9') {
            fail("invalid number");
        }
        if (text[index] == '0') {
            ++index;
        } else {
            while (!at_end() && text[index] >= '0' && text[index] <= '9') {
                ++index;
            }
        }
        if (!at_end() && text[index] == '.') {
            ++index;
            if (at_end() || text[index] < '0' || text[index] > '9') {
                fail("invalid number fraction");
            }
            while (!at_end() && text[index] >= '0' && text[index] <= '9') {
                ++index;
            }
        }
        if (!at_end() && (text[index] == 'e' || text[index] == 'E')) {
            ++index;
            if (!at_end() && (text[index] == '+' || text[index] == '-')) {
                ++index;
            }
            if (at_end() || text[index] < '0' || text[index] > '9') {
                fail("invalid number exponent");
            }
            while (!at_end() && text[index] >= '0' && text[index] <= '9') {
                ++index;
            }
        }
        JsonNode node;
        node.kind = JsonKind::Number;
        node.number_value = std::stod(std::string(text.substr(start, index - start)));
        return node;
    }

    JsonNode parse_array() {
        expect('[');
        JsonNode node;
        node.kind = JsonKind::Array;
        skip_ws();
        if (!at_end() && text[index] == ']') {
            ++index;
            return node;
        }
        while (true) {
            node.array_value.push_back(parse_value());
            skip_ws();
            if (at_end()) {
                fail("unterminated array");
            }
            if (text[index] == ']') {
                ++index;
                return node;
            }
            if (text[index] != ',') {
                fail("expected comma in array");
            }
            ++index;
        }
    }

    JsonNode parse_object() {
        expect('{');
        JsonNode node;
        node.kind = JsonKind::Object;
        skip_ws();
        if (!at_end() && text[index] == '}') {
            ++index;
            return node;
        }
        std::set<std::string> seen;
        while (true) {
            skip_ws();
            JsonNode key = parse_string();
            if (seen.count(key.string_value) != 0) {
                fail("duplicate key '" + key.string_value + "'");
            }
            seen.insert(key.string_value);
            expect(':');
            node.object_value.emplace_back(key.string_value, parse_value());
            skip_ws();
            if (at_end()) {
                fail("unterminated object");
            }
            if (text[index] == '}') {
                ++index;
                return node;
            }
            if (text[index] != ',') {
                fail("expected comma in object");
            }
            ++index;
        }
    }
};

JsonNode JsonParser::parse_value() {
    skip_ws();
    if (at_end()) {
        fail("unexpected end of file");
    }
    const char ch = text[index];
    if (ch == '"') {
        return parse_string();
    }
    if (ch == '{') {
        return parse_object();
    }
    if (ch == '[') {
        return parse_array();
    }
    if (ch == '-' || (ch >= '0' && ch <= '9')) {
        return parse_number();
    }
    if (text.substr(index, 4) == "true") {
        index += 4;
        JsonNode node;
        node.kind = JsonKind::Bool;
        node.bool_value = true;
        return node;
    }
    if (text.substr(index, 5) == "false") {
        index += 5;
        JsonNode node;
        node.kind = JsonKind::Bool;
        node.bool_value = false;
        return node;
    }
    if (text.substr(index, 4) == "null") {
        index += 4;
        JsonNode node;
        node.kind = JsonKind::Null;
        return node;
    }
    fail("invalid value");
}

}  // namespace

JsonNode parse_json_file(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        throw std::runtime_error("json: cannot read " + path);
    }
    std::string text((std::istreambuf_iterator<char>(in)),
                     std::istreambuf_iterator<char>());
    if (text.empty()) {
        throw std::runtime_error("json: empty file " + path);
    }
    JsonParser parser;
    parser.text = text;
    parser.source_name = path;
    JsonNode root = parser.parse_value();
    parser.skip_ws();
    if (!parser.at_end()) {
        parser.fail("trailing content after top-level value");
    }
    return root;
}

const JsonNode* object_field(const JsonNode& node, const std::string& key) {
    if (node.kind != JsonKind::Object) {
        throw std::runtime_error("json: expected object for field '" + key + "'");
    }
    for (const auto& field : node.object_value) {
        if (field.first == key) {
            return &field.second;
        }
    }
    return nullptr;
}

std::string require_string(const JsonNode& node, const std::string& key,
                           bool allow_empty, const std::string& prefix) {
    const JsonNode* field = object_field(node, key);
    if (field == nullptr) {
        throw std::runtime_error(prefix + ": missing required field '" + key + "'");
    }
    if (field->kind != JsonKind::String) {
        throw std::runtime_error(prefix + ": field '" + key + "' must be a string");
    }
    if (!allow_empty && field->string_value.empty()) {
        throw std::runtime_error(prefix + ": field '" + key + "' must not be empty");
    }
    return field->string_value;
}

void reject_unknown_keys(const JsonNode& node,
                         const std::set<std::string>& allowed,
                         const std::string& where) {
    if (node.kind != JsonKind::Object) {
        throw std::runtime_error(where + " must be an object");
    }
    for (const auto& field : node.object_value) {
        if (allowed.count(field.first) == 0) {
            throw std::runtime_error("unknown key '" + field.first + "' in " + where);
        }
    }
}

}  // namespace schgen
