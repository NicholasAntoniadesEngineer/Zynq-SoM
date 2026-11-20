#include "schgen/pcb_escape.hpp"

#include <set>
#include <stdexcept>

namespace schgen {
namespace {
namespace fs = std::filesystem;
const char *const triage_file = "escape_triage.json";
const char *const triage_schema = "schgen.escape_triage/1";

[[noreturn]] void fail(const fs::path &file, const std::string &what) {
    throw std::runtime_error("escape triage " + file.string() + ": " + what);
}

std::string text(const JsonNode &node, const std::string &key, const fs::path &file,
                 const std::string &where) {
    return require_string(node, key, false, "escape triage " + file.string() + " " + where);
}

bool known_class(const std::string &klass) {
    try {
        PcbEscapeSignalClass{{}, {}, klass, {}}.rank();
    } catch (const PcbEscapeError &) {
        return false;
    }
    return true;
}
}

PcbEscapeTriage load_escape_triage(const fs::path &board_root) {
    const auto file = board_root / triage_file;
    if (!fs::is_regular_file(file))
        fail(file, "file is missing");
    const auto doc = parse_json_file(file.string());
    reject_unknown_keys(doc, {"schema", "rules"}, "escape triage " + file.string());
    if (text(doc, "schema", file, "document") != triage_schema)
        fail(file, std::string("schema is not ") + triage_schema);
    const JsonNode *rules = object_field(doc, "rules");
    if (!rules || rules->kind != JsonKind::Array)
        fail(file, "field 'rules' is missing or is not an array");
    PcbEscapeTriage out;
    for (std::size_t i = 0; i < rules->array_value.size(); ++i) {
        const auto &row = rules->array_value[i];
        const auto where = "rule " + std::to_string(i);
        reject_unknown_keys(row, {"pattern", "class", "note"},
                            "escape triage " + file.string() + " " + where);
        PcbEscapeTriageRule rule;
        rule.source = text(row, "pattern", file, where);
        rule.klass = text(row, "class", file, where);
        rule.note = text(row, "note", file, where);
        if (!known_class(rule.klass))
            fail(file, where + " pattern " + rule.source + " has unknown class " + rule.klass);
        try {
            rule.pattern = std::regex(rule.source);
        } catch (const std::regex_error &error) {
            fail(file, where + " pattern " + rule.source +
                           " is not a valid regular expression: " + error.what());
        }
        out.rules.push_back(std::move(rule));
    }
    if (out.rules.empty())
        fail(file, "field 'rules' is empty");
    return out;
}
}
