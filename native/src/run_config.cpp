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

std::optional<std::string>& studied() {
    static std::optional<std::string> name;
    return name;
}

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

const std::vector<std::string>& RunConfig::overmold_parts_of(const std::string& board) const {
    const auto found = overmold_parts.find(board);
    if (found == overmold_parts.end()) fail("'overmold_parts' names no entry for board '" + board + "'");
    return found->second;
}

std::vector<std::string> RunConfig::board_arguments(const std::string& board, const std::filesystem::path& file) const {
    std::vector<std::string> arguments{"schgen", "board", "--project", board, "--output", (output / board).string(),
                                       "--run-config", std::filesystem::absolute(file).string(),
                                       "--audit-projections", std::to_string(audit_projections), "--plane-net",
                                       plane_net};
    if (squeeze) arguments.push_back("--layout-squeeze");
    if (!renders) arguments.push_back("--no-render");
    if (timing) arguments.push_back("--timing");
    for (const std::string& part : overmold_parts_of(board)) {
        arguments.push_back("--overmold-part");
        arguments.push_back(part);
    }
    return arguments;
}

RunConfig parse_run_config(const JsonNode& document) {
    if (document.kind != JsonKind::Object) fail("the file must hold one object");
    reject_unknown_keys(document, {"schema", "boards", "output", "squeeze", "arrange", "renders", "labels", "timing", "plane_net",
                                   "audit_projections", "stackup", "overmold_parts", "study"}, run_config_file);
    if (member(document, "schema", JsonKind::String).string_value != "schgen.run/1") fail("unknown schema");
    RunConfig config;
    config.boards = names(member(document, "boards", JsonKind::Array), "boards");
    if (config.boards.empty()) fail("'boards' names no board");
    config.output = member(document, "output", JsonKind::String).string_value;
    if (config.output.empty()) fail("'output' names no folder");
    config.squeeze = member(document, "squeeze", JsonKind::Bool).bool_value;
    config.renders = member(document, "renders", JsonKind::Bool).bool_value;
    config.arrange = member(document, "arrange", JsonKind::Bool).bool_value;
    if (config.arrange && !config.squeeze) fail("'arrange' needs 'squeeze'");
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
    if (const JsonNode* study = object_field(document, "study")) {
        if (study->kind != JsonKind::Object) fail("'study' must be an object");
        reject_unknown_keys(*study, {"stackups"}, std::string(run_config_file) + " 'study'");
        config.study_stackups = names(member(*study, "stackups", JsonKind::Array), "study.stackups");
        if (config.study_stackups.empty()) fail("'study.stackups' names no stack-up");
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
    config.stackup_of(board);
    if (studied()) config.stackup[board] = *studied();
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

void study_stackup(std::optional<std::string> name) { studied() = std::move(name); }

RunArguments parse_run_arguments(const std::vector<std::string>& arguments, const std::set<std::string>& valued) {
    RunArguments out;
    out.file = run_config_file;
    for (std::size_t index = 0; index < arguments.size(); ++index) {
        const std::string& argument = arguments[index];
        if (argument == "--config") {
            if (++index == arguments.size()) fail("--config needs a file");
            out.file = arguments[index];
        } else if (valued.count(argument)) {
            if (++index == arguments.size()) fail(argument + " needs a value");
            if (!out.options.emplace(argument, arguments[index]).second) fail(argument + " is given twice");
        } else if (argument.rfind("--", 0) == 0) {
            fail("unknown option " + argument + "; settings belong in the file");
        } else {
            out.boards.push_back(argument);
        }
    }
    return out;
}

std::vector<std::string> chosen_boards(const RunConfig& config, const std::vector<std::string>& chosen) {
    const std::set<std::string> known(config.boards.begin(), config.boards.end());
    for (const std::string& board : chosen)
        if (!known.count(board)) fail("board '" + board + "' is not listed under 'boards'");
    return chosen.empty() ? config.boards : chosen;
}

std::string run_usage() {
    return "usage: schgen [run] [BOARD ...] [--config FILE]\n"
           "  Builds every board named in schgen.json, or only the boards named here.\n"
           "  Every setting lives in schgen.json; see README.md for the table.\n"
           "usage: schgen study layers [BOARD ...] [--config FILE] [--stackups NAME,NAME,...]\n"
           "  Builds the same boards once per stack-up into <output>/study/ and writes one comparison per board.\n"
           "  The stack-ups come from --stackups, or from 'study.stackups' in schgen.json.\n"
           "  schgen tools    lists the individual commands used for diagnosis.\n";
}

}
