#include "schgen/stackup.hpp"
#include "schgen/run_config.hpp"

#include <algorithm>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>

namespace schgen {
namespace {

const int rear_ordinal = 31;

std::optional<Stackup>& selection() {
    static std::optional<Stackup> chosen;
    return chosen;
}

[[noreturn]] void fail(const std::string& where, const std::string& what) {
    throw std::runtime_error("stack-up " + where + ": " + what);
}

const JsonNode& member(const JsonNode& node, const std::string& key, JsonKind kind, const std::string& where) {
    const JsonNode* found = object_field(node, key);
    if (!found || found->kind != kind) fail(where, "field '" + key + "' is missing or has the wrong type");
    return *found;
}

double positive(const JsonNode& node, const std::string& key, const std::string& where) {
    const double value = member(node, key, JsonKind::Number, where).number_value;
    if (!(value > 0)) fail(where, "field '" + key + "' must be positive");
    return value;
}

CopperRole role_of(char letter, const std::string& where) {
    switch (letter) {
    case 'S': return CopperRole::signal;
    case 'G': return CopperRole::ground;
    case 'P': return CopperRole::power;
    }
    fail(where, std::string("role letter '") + letter + "' is not S, G or P");
}

const char* role_label(CopperRole role) {
    switch (role) {
    case CopperRole::signal: return "Sig";
    case CopperRole::ground: return "GND";
    case CopperRole::power: return "PWR";
    }
    throw std::logic_error("unknown copper role");
}

std::string trimmed(double value) {
    std::ostringstream text;
    text << value;
    return text.str();
}

Stackup parse_stackup(const JsonNode& node) {
    Stackup stackup;
    stackup.fabricator_name = require_string(node, "name", false, "stack-up");
    const std::string& where = stackup.fabricator_name;
    reject_unknown_keys(node, {"name", "fabricator", "thickness_mm", "outer_copper_mm", "inner_copper_mm", "roles",
                               "between", "pair_basis", "pairs"}, "stack-up " + where);
    stackup.fabricator = require_string(node, "fabricator", false, where);
    stackup.thickness_mm = positive(node, "thickness_mm", where);
    const double outer = positive(node, "outer_copper_mm", where), inner = positive(node, "inner_copper_mm", where);
    const std::string roles = require_string(node, "roles", false, where);
    if (roles.size() < 2) fail(where, "a board needs two copper layers");
    const auto& between = member(node, "between", JsonKind::Array, where).array_value;
    if (between.size() + 1 != roles.size()) fail(where, "every neighbouring copper pair needs its dielectric");
    std::string order;
    for (std::size_t index = 0; index < roles.size(); ++index) {
        const bool first = index == 0, last = index + 1 == roles.size();
        CopperLayer layer;
        layer.ordinal = last ? rear_ordinal : static_cast<int>(index);
        layer.name = first ? "F.Cu" : last ? "B.Cu" : "In" + std::to_string(index) + ".Cu";
        layer.role = role_of(roles[index], where);
        layer.thickness_mm = first || last ? outer : inner;
        layer.label = "L" + std::to_string(index + 1) + " (" + role_label(layer.role) + ")";
        order += std::string(index ? " / " : "") + role_label(layer.role);
        stackup.copper.push_back(std::move(layer));
    }
    if (stackup.copper.front().role != CopperRole::signal || stackup.copper.back().role != CopperRole::signal)
        fail(where, "both outer layers carry parts and must be signal layers");
    for (std::size_t gap = 0; gap < between.size(); ++gap) {
        if (between[gap].kind != JsonKind::Array || between[gap].array_value.empty())
            fail(where, "the dielectric under copper layer " + std::to_string(gap + 1) + " is empty");
        for (const JsonNode& sheet : between[gap].array_value) {
            DielectricLayer layer;
            layer.name = "dielectric " + std::to_string(stackup.dielectric.size() + 1);
            layer.kind = require_string(sheet, "kind", false, where);
            layer.material = require_string(sheet, "material", false, where);
            layer.thickness_mm = positive(sheet, "thickness_mm", where);
            layer.permittivity = positive(sheet, "permittivity", where);
            layer.above = gap;
            stackup.dielectric.push_back(std::move(layer));
        }
    }
    stackup.pair_basis = require_string(node, "pair_basis", true, where);
    for (const JsonNode& row : member(node, "pairs", JsonKind::Array, where).array_value) {
        DifferentialGeometry pair;
        pair.impedance = static_cast<int>(positive(row, "impedance", where));
        pair.width_mm = positive(row, "width_mm", where);
        pair.gap_mm = positive(row, "gap_mm", where);
        pair.source = require_string(row, "source", false, where);
        if (stackup.pair(pair.impedance)) fail(where, "impedance " + std::to_string(pair.impedance) + " is listed twice");
        stackup.pairs.push_back(std::move(pair));
    }
    if (!stackup.pairs.empty() && stackup.pair_basis.empty()) fail(where, "pair widths need a stated basis");
    const std::string count = std::to_string(roles.size());
    stackup.summary = count + "-layer " + trimmed(stackup.thickness_mm) + " mm (" + order + ")";
    stackup.brief = count + "L " + trimmed(stackup.thickness_mm) + "mm";
    const DielectricLayer& top = stackup.dielectric.front();
    stackup.prepreg = top.material + " prepreg " + trimmed(top.thickness_mm) + "mm";
    return stackup;
}

}

const CopperLayer& Stackup::reference_of(bool rear) const { return rear ? copper[copper.size() - 2] : copper[1]; }

std::vector<std::string> Stackup::ground_layers() const {
    std::vector<std::string> names;
    for (const CopperLayer& layer : copper)
        if (layer.role == CopperRole::ground) names.push_back(layer.name);
    return names;
}

std::size_t Stackup::signal_layers() const {
    return static_cast<std::size_t>(std::count_if(copper.begin(), copper.end(), [](const CopperLayer& layer) {
        return layer.role == CopperRole::signal;
    }));
}

bool Stackup::ground_referenced(bool rear) const { return reference_of(rear).role == CopperRole::ground; }

const DifferentialGeometry* Stackup::pair(int impedance) const {
    const auto found = std::find_if(pairs.begin(), pairs.end(),
                                    [&](const DifferentialGeometry& row) { return row.impedance == impedance; });
    return found == pairs.end() ? nullptr : &*found;
}

std::string Stackup::pair_list(const std::string& label, const std::string& unit, const std::string& joint) const {
    std::ostringstream text;
    for (std::size_t index = 0; index < pairs.size(); ++index)
        text << (index ? joint : "") << pairs[index].impedance << label << pairs[index].width_mm << "/"
             << pairs[index].gap_mm << unit;
    return text.str();
}

std::string Stackup::placement_family() const {
    return std::string("top over ") + copper_role_name(reference_of(false).role) + ", rear over " +
           copper_role_name(reference_of(true).role);
}

const char* copper_role_name(CopperRole role) {
    switch (role) {
    case CopperRole::signal: return "signal";
    case CopperRole::ground: return "ground";
    case CopperRole::power: return "power";
    }
    throw std::logic_error("unknown copper role");
}

StackupCatalogue parse_stackups(const JsonNode& document) {
    if (require_string(document, "schema", false, "stack-up catalogue") != "schgen.stackups/1")
        fail("catalogue", "unknown schema");
    reject_unknown_keys(document, {"schema", "source", "stackups"}, "stack-up catalogue");
    require_string(document, "source", false, "stack-up catalogue");
    StackupCatalogue catalogue;
    std::set<std::string> names;
    for (const JsonNode& node : member(document, "stackups", JsonKind::Array, "catalogue").array_value) {
        catalogue.entries.push_back(parse_stackup(node));
        if (!names.insert(catalogue.entries.back().fabricator_name).second)
            fail(catalogue.entries.back().fabricator_name, "listed twice");
    }
    return catalogue;
}

StackupCatalogue load_stackups(const std::filesystem::path& file) {
    return parse_stackups(parse_json_file(file.string()));
}

std::filesystem::path stackup_catalogue_file() { return SCHGEN_STACKUP_CATALOG; }

const Stackup& StackupCatalogue::named(const std::string& name) const {
    const auto found = std::find_if(entries.begin(), entries.end(),
                                    [&](const Stackup& row) { return row.fabricator_name == name; });
    if (found != entries.end()) return *found;
    std::string known;
    for (const Stackup& row : entries) known += (known.empty() ? "" : ", ") + row.fabricator_name;
    fail(name, "is not in the catalogue; known: " + known);
}

void select_stackup(Stackup stackup) { selection() = std::move(stackup); }

const Stackup& board_stackup() {
    if (!selection())
        throw std::runtime_error("no stack-up is selected; a board is built only from an explicit configuration (" +
                                 std::string(run_config_file) + ")");
    return *selection();
}

}
