#include "schgen/run_config.hpp"
#include "schgen/board_definition.hpp"
#include "schgen/stackup.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
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

double number(const JsonNode& node, const std::string& key, const std::string& where) {
    const JsonNode* found = object_field(node, key);
    if (!found || found->kind != JsonKind::Number || !std::isfinite(found->number_value))
        fail("'" + where + key + "' is missing or not a number");
    return found->number_value;
}

std::size_t count(const JsonNode& node, const std::string& key, const std::string& where) {
    const double value = number(node, key, where);
    if (value < 1 || std::floor(value) != value) fail("'" + where + key + "' must be a whole number of at least one");
    return static_cast<std::size_t>(value);
}

SearchConfig parse_search(const JsonNode& node) {
    const std::string where = "search.";
    reject_unknown_keys(node, {"mode", "seeds", "promote", "threads", "objective", "max_minutes", "max_outline_mm", "reliability"},
                        std::string(run_config_file) + " 'search'");
    SearchConfig out;
    out.mode = member(node, "mode", JsonKind::String).string_value;
    if (out.mode != "quick" && out.mode != "release") fail("'search.mode' must be quick or release");
    std::set<std::uint64_t> seen;
    for (const JsonNode& item : member(node, "seeds", JsonKind::Array).array_value) {
        if (item.kind != JsonKind::Number || item.number_value < 0 || std::floor(item.number_value) != item.number_value ||
            item.number_value > static_cast<double>(std::numeric_limits<std::uint32_t>::max()))
            fail("'search.seeds' holds a value that is not a whole number");
        const auto seed = static_cast<std::uint64_t>(item.number_value);
        if (!seen.insert(seed).second) fail("'search.seeds' repeats seed " + std::to_string(seed));
        out.seeds.push_back(seed);
    }
    if (out.seeds.empty() || out.seeds.front() != 0) fail("'search.seeds' must start with the reference seed 0");
    out.promote = count(node, "promote", where);
    if (out.promote > out.seeds.size()) fail("'search.promote' exceeds the number of seeds");
    out.threads = count(node, "threads", where);
    const std::set<std::string> keys{"area", "long_side", "airwire", "rear_parts"};
    std::set<std::string> used;
    for (const std::string& key : names(member(node, "objective", JsonKind::Array), "search.objective")) {
        if (!keys.count(key)) fail("'search.objective' names " + key + "; known: area, long_side, airwire, rear_parts");
        if (!used.insert(key).second) fail("'search.objective' names " + key + " twice");
        out.objective.push_back(key);
    }
    if (out.objective.empty()) fail("'search.objective' names nothing");
    const JsonNode* minutes = object_field(node, "max_minutes");
    if (!minutes) fail("'search.max_minutes' is missing (a number, or null for no ceiling)");
    if (minutes->kind != JsonKind::Null) {
        out.max_minutes = number(node, "max_minutes", where);
        if (!(*out.max_minutes > 0)) fail("'search.max_minutes' must be above zero");
    }
    const JsonNode* outline = object_field(node, "max_outline_mm");
    if (!outline) fail("'search.max_outline_mm' is missing (an object with w and h, or null for no bound)");
    if (outline->kind != JsonKind::Null) {
        if (outline->kind != JsonKind::Object) fail("'search.max_outline_mm' must be an object or null");
        reject_unknown_keys(*outline, {"w", "h"}, std::string(run_config_file) + " 'search.max_outline_mm'");
        const double w = number(*outline, "w", "search.max_outline_mm."), h = number(*outline, "h", "search.max_outline_mm.");
        if (!(w > 0) || !(h > 0)) fail("'search.max_outline_mm' sides must be above zero");
        out.max_outline_mm = std::make_pair(w, h);
    }
    const JsonNode& reliability = member(node, "reliability", JsonKind::Object);
    reject_unknown_keys(reliability, {"pass_rate", "area_spread", "basis"}, std::string(run_config_file) + " 'search.reliability'");
    out.reliability.pass_rate = number(reliability, "pass_rate", "search.reliability.");
    out.reliability.area_spread = number(reliability, "area_spread", "search.reliability.");
    if (out.reliability.pass_rate <= 0 || out.reliability.pass_rate > 1) fail("'search.reliability.pass_rate' must be in (0, 1]");
    if (out.reliability.area_spread < 0) fail("'search.reliability.area_spread' must not be negative");
    out.reliability.basis = member(reliability, "basis", JsonKind::String).string_value;
    if (out.reliability.basis.empty()) fail("'search.reliability.basis' is empty");
    return out;
}

}

const std::string& RunConfig::stackup_of(const std::string& board) const {
    const auto found = stackup.find(board);
    if (found == stackup.end()) fail("'stackup' names no stack-up for board '" + board + "'");
    return found->second;
}

int RunConfig::density_of(const std::string& board) const {
    const auto found = density.find(board);
    if (found == density.end()) fail("'density' names no level for board '" + board + "'");
    return found->second;
}

const std::vector<std::string>& RunConfig::overmold_parts_of(const std::string& board) const {
    const auto found = overmold_parts.find(board);
    if (found == overmold_parts.end()) fail("'overmold_parts' names no entry for board '" + board + "'");
    return found->second;
}

const FabricationConfig& RunConfig::fabrication_of(const std::string& board) const {
    const auto found = fabrication.find(board);
    if (found == fabrication.end()) fail("'fabrication' names no entry for board '" + board + "'");
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
    reject_unknown_keys(document, {"schema", "boards", "output", "squeeze", "arrange", "construct", "plan", "renders", "labels", "timing", "plane_net",
                                   "audit_projections", "stackup", "density", "overmold_parts", "fabrication", "study", "search"}, run_config_file);
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
    config.construct = member(document, "construct", JsonKind::Bool).bool_value;
    if (config.construct && !config.squeeze) fail("'construct' needs 'squeeze'");
    config.plan = member(document, "plan", JsonKind::Bool).bool_value;
    if (config.plan && !config.squeeze) fail("'plan' needs 'squeeze'");
    config.labels = member(document, "labels", JsonKind::Bool).bool_value;
    config.timing = member(document, "timing", JsonKind::Bool).bool_value;
    config.plane_net = member(document, "plane_net", JsonKind::String).string_value;
    config.audit_projections = static_cast<int>(member(document, "audit_projections", JsonKind::Number).number_value);
    for (const auto& [board, name] : member(document, "stackup", JsonKind::Object).object_value) {
        if (name.kind != JsonKind::String || name.string_value.empty()) fail("stack-up of '" + board + "' is not a name");
        config.stackup[board] = name.string_value;
    }
    for (const auto& [board, level] : member(document, "density", JsonKind::Object).object_value) {
        const std::optional<int> value = density_level(level);
        if (!value) fail("'density' of '" + board + "' must be " + density_range());
        config.density[board] = *value;
    }
    for (const auto& [board, parts] : member(document, "overmold_parts", JsonKind::Object).object_value) {
        if (parts.kind != JsonKind::Array) fail("overmold parts of '" + board + "' must be a list");
        config.overmold_parts[board] = names(parts, "overmold_parts");
    }
    for (const auto& [board, entry] : member(document, "fabrication", JsonKind::Object).object_value) {
        const std::string where = "'fabrication' of '" + board + "'";
        if (entry.kind != JsonKind::Object) fail(where + " must be an object");
        reject_unknown_keys(entry, {"fabricator", "copper", "finish", "assembly_service", "build_count"}, std::string(run_config_file) + " " + where);
        FabricationConfig row;
        row.fabricator = member(entry, "fabricator", JsonKind::String).string_value;
        row.finish = member(entry, "finish", JsonKind::String).string_value;
        row.assembly_service = member(entry, "assembly_service", JsonKind::String).string_value;
        if (row.fabricator.empty() || row.finish.empty() || row.assembly_service.empty()) fail(where + " holds an empty name");
        const JsonNode& copper = member(entry, "copper", JsonKind::Object);
        reject_unknown_keys(copper, {"outer_oz", "inner_oz"}, std::string(run_config_file) + " " + where + " 'copper'");
        row.outer_oz = member(copper, "outer_oz", JsonKind::Number).number_value;
        row.inner_oz = member(copper, "inner_oz", JsonKind::Number).number_value;
        const double count = member(entry, "build_count", JsonKind::Number).number_value;
        if (!(count >= 1) || count != std::floor(count)) fail(where + " needs 'build_count' as a whole number of at least 1");
        row.build_count = static_cast<int>(count);
        config.fabrication[board] = row;
    }
    if (const JsonNode* study = object_field(document, "study")) {
        if (study->kind != JsonKind::Object) fail("'study' must be an object");
        reject_unknown_keys(*study, {"stackups"}, std::string(run_config_file) + " 'study'");
        config.study_stackups = names(member(*study, "stackups", JsonKind::Array), "study.stackups");
        if (config.study_stackups.empty()) fail("'study.stackups' names no stack-up");
    }
    config.search = parse_search(member(document, "search", JsonKind::Object));
    for (const std::string& board : config.boards) {
        config.stackup_of(board);
        config.fabrication_of(board);
        if (config.density_of(board) < densest_density && !config.squeeze)
            fail("'density' of '" + board + "' is below " + std::to_string(densest_density) + ", which needs 'squeeze'");
    }
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
    const FabricationConfig& chosen = config.fabrication_of(board);
    FabricatorProfile profile = load_fabricator(fabricator_file(chosen.fabricator));
    validate_fabrication(chosen, profile, listed->copper.size(), listed->outer_oz, listed->inner_oz, board);
    select_fabrication({chosen, std::move(profile)});
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
