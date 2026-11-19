#include "schgen/run_config.hpp"
#include "schgen/stackup.hpp"

#include <algorithm>
#include <set>
#include <stdexcept>

namespace schgen {
[[noreturn]] void run_config_failure(const std::string& what) {
    throw std::runtime_error(std::string(run_config_file) + ": " + what);
}

namespace {

[[noreturn]] void fail(const std::string& what) { run_config_failure(what); }

const JsonNode& member(const JsonNode& node, const std::string& key, JsonKind kind) {
    const JsonNode* found = object_field(node, key);
    if (!found || found->kind != kind) fail("field '" + key + "' is missing or has the wrong type");
    return *found;
}

std::vector<std::string> names(const JsonNode& node, const std::string& key) {
    std::vector<std::string> out;
    for (const JsonNode& item : node.array_value) {
        if (item.kind != JsonKind::String || item.string_value.empty()) fail("'" + key + "' holds a value that is not a name");
        out.push_back(item.string_value);
    }
    return out;
}

}

const std::string& RunConfig::stackup_of(const std::string& board) const {
    const auto found = stackup.find(board);
    if (found == stackup.end()) fail("'stackup' names no stack-up for board '" + board + "'");
    return found->second;
}

std::vector<std::string> RunConfig::board_arguments(const std::string& board) const {
    std::vector<std::string> arguments{"schgen", "board", "--project", board, "--output", (output / board).string(),
                                       "--audit-projections", std::to_string(audit_projections), "--plane-net",
                                       plane_net};
    if (squeeze) arguments.push_back("--layout-squeeze");
    if (!renders) arguments.push_back("--no-render");
    if (timing) arguments.push_back("--timing");
    const auto parts = overmold_parts.find(board);
    if (parts != overmold_parts.end())
        for (const std::string& part : parts->second) {
            arguments.push_back("--overmold-part");
            arguments.push_back(part);
        }
    return arguments;
}

RunConfig parse_run_config(const JsonNode& document) {
    if (document.kind != JsonKind::Object) fail("the file must hold one object");
    reject_unknown_keys(document, {"schema", "boards", "output", "squeeze", "renders", "labels", "timing", "plane_net",
                                   "audit_projections", "stackup", "overmold_parts"}, run_config_file);
    if (member(document, "schema", JsonKind::String).string_value != "schgen.run/1") fail("unknown schema");
    RunConfig config;
    config.boards = names(member(document, "boards", JsonKind::Array), "boards");
    if (config.boards.empty()) fail("'boards' names no board");
    config.output = member(document, "output", JsonKind::String).string_value;
    if (config.output.empty()) fail("'output' names no folder");
    config.squeeze = member(document, "squeeze", JsonKind::Bool).bool_value;
    config.renders = member(document, "renders", JsonKind::Bool).bool_value;
    config.labels = member(document, "labels", JsonKind::Bool).bool_value;
    config.timing = member(document, "timing", JsonKind::Bool).bool_value;
    config.plane_net = member(document, "plane_net", JsonKind::String).string_value;
    config.audit_projections = static_cast<int>(member(document, "audit_projections", JsonKind::Number).number_value);
    for (const auto& [board, name] : member(document, "stackup", JsonKind::Object).object_value) {
        if (name.kind != JsonKind::String || name.string_value.empty()) fail("stack-up of '" + board + "' is not a name");
        config.stackup[board] = name.string_value;
    }
    for (const auto& [board, parts] : member(document, "overmold_parts", JsonKind::Object).object_value) {
        if (parts.kind != JsonKind::Array) fail("overmold parts of '" + board + "' must be a list");
        config.overmold_parts[board] = names(parts, "overmold_parts");
    }
    for (const std::string& board : config.boards) config.stackup_of(board);
    return config;
}

RunConfig load_run_config(const std::filesystem::path& file) {
    if (!std::filesystem::exists(file)) fail("not found at " + file.string());
    return parse_run_config(parse_json_file(file.string()));
}

RunConfig apply_run_config(const std::filesystem::path& config_file, const std::string& board) {
    RunConfig config = load_run_config(config_file);
    const std::string& name = config.stackup_of(board);
    const StackupCatalogue catalogue = load_stackups(stackup_catalogue_file());
    const auto listed = std::find_if(catalogue.entries.begin(), catalogue.entries.end(),
                                     [&](const Stackup& row) { return row.fabricator_name == name; });
    if (listed == catalogue.entries.end())
        fail("'stackup' of board '" + board + "' names '" + name + "', which is not in " +
             stackup_catalogue_file().string());
    select_stackup(*listed);
    return config;
}

std::string run_usage() {
    return "usage: schgen [run] [BOARD ...] [--config FILE]\n"
           "  Builds every board named in schgen.json, or only the boards named here.\n"
           "  Every setting lives in schgen.json; see README.md for the table.\n"
           "  schgen tools    lists the individual commands used for diagnosis.\n";
}

}
