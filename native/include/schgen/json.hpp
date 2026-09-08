#pragma once

#include <set>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace schgen {

enum class JsonKind {
    Null,
    Bool,
    Number,
    String,
    Array,
    Object
};

struct JsonNode {
    JsonKind kind = JsonKind::Null;
    bool bool_value = false;
    double number_value = 0.0;
    std::string string_value;
    std::vector<JsonNode> array_value;
    std::vector<std::pair<std::string, JsonNode>> object_value;
};

JsonNode parse_json_file(const std::string& path);
const JsonNode* object_field(const JsonNode& node, const std::string& key);
std::string require_string(const JsonNode& node, const std::string& key,
                           bool allow_empty, const std::string& prefix);
void reject_unknown_keys(const JsonNode& node,
                         const std::set<std::string>& allowed,
                         const std::string& where);

}  // namespace schgen
