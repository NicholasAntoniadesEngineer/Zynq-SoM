#pragma once

#include "schgen/named_constant.hpp"
#include "schgen/sexpr.hpp"

#include <array>
#include <cstdint>
#include <filesystem>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace schgen {

namespace part_fact_constants {
inline constexpr NamedConstant vrml_unit{"vrml_unit", 2.54, "mm", "physical",
    "KiCad reads one VRML model unit as a tenth of an inch, and the part importer writes its models in that unit"};
inline constexpr std::array part_fact_registry{vrml_unit};
}

enum class PartClass : std::uint8_t {
    resistor,
    capacitor,
    inductor,
    ferrite,
    transformer,
    diode,
    led,
    transistor,
    integrated_circuit,
    connector,
    header,
    module_connector,
    control_switch,
    test_point,
    crystal,
    battery_holder,
    mounting_hole,
    fiducial
};

struct PartHeight {
    double mm = 0;
    std::string source;
};

struct PartFact {
    PartClass part_class;
    PartHeight height;
};

struct ConnectorFact {
    std::string mating_face;
    bool edge_pinned = false, overmold = false, pad_row_face_check = false;
    std::optional<std::string> description, numbered_label, pair_label;
};

using ConnectorFacts = std::map<std::string, ConnectorFact>;

struct ThermalPourFact {
    double rth_ja = 0;
    std::string cite, evidence;
};

struct ThermalFact {
    double rth_ja = 0, tj_max = 0, rds_on = 0, eff = 0;
    std::string package, cite;
    std::optional<ThermalPourFact> pour;
};

struct ThermalNeedFact {
    int min_vias = 0;
    double radius_mm = 0;
    std::vector<std::string> pour_layers;
};

struct ThermalFieldFact {
    std::vector<std::pair<double, double>> via_offsets_mm;
    int max_vias = 0;
    std::array<double, 4> pour_box_mm{};
    std::vector<std::string> pour_layers;
    std::string cite;
};

struct ThermalCopperFact {
    ThermalNeedFact need;
    ThermalFieldFact field;
};

struct EpViaFact {
    int min_pads = 0;
    double radius_mm = 0;
};

struct IsolationFact {
    double margin_mm = 0;
};

struct RegulatorDirectEnable {
    std::string en_pin;
    std::vector<std::string> vin_pins;
    std::string cite;
};

struct RegulatorEnableNetwork {
    double ihys_a = 0, recommended_max_v = 0, threshold_v = 0;
    std::string cite;
};

struct RegulatorEnableFact {
    std::optional<RegulatorDirectEnable> direct;
    std::optional<RegulatorEnableNetwork> network;
};

struct RegulatorFact {
    std::string kind, label;
    std::optional<double> limit_a;
    double eff = 0;
    std::string in_pin, out_pin;
    std::optional<std::string> iset_pin;
    double ilim_num = 0;
    std::string note;
    std::optional<double> fb_vref, iset_v;
    std::optional<RegulatorEnableFact> enable;
};

struct ZenerFact {
    double vz_min_v = 0, vz_max_v = 0, izt_a = 0, zzt_ohm = 0;
};

struct ReferencePinFact {
    std::string label, vref1_pin, vref2_pin;
};

struct ControlGridFact {
    double button_gap_mm = 0;
};

struct ModelOverrideFact {
    std::string footprint, path;
    double rotation_z_deg = 0;
};

struct FootprintAliasFact {
    std::string footprint;
};

using ThermalFacts = std::map<std::string, ThermalFact>;
using ThermalCopperFacts = std::map<std::string, ThermalCopperFact>;
using EpViaFacts = std::map<std::string, EpViaFact>;
using IsolationFacts = std::map<std::string, IsolationFact>;
using RegulatorFacts = std::map<std::string, RegulatorFact>;
using ZenerFacts = std::map<std::string, ZenerFact>;
using ReferencePinFacts = std::map<std::string, ReferencePinFact>;
using ControlGridFacts = std::map<std::string, ControlGridFact>;
using ModelOverrideFacts = std::map<std::string, ModelOverrideFact>;
using FootprintAliasFacts = std::map<std::string, FootprintAliasFact>;

template <typename Fact>
const Fact* part_fact(const std::map<std::string, Fact>& section, const std::string& name) {
    const auto found = section.find(name);
    return found == section.end() ? nullptr : &found->second;
}

template <typename Fact>
const Fact* part_fact_for(const std::map<std::string, Fact>& section, const std::string& value, const std::string& footprint) {
    if (const Fact* fact = part_fact(section, value)) return fact;
    return part_fact(section, footprint.substr(footprint.find_last_of(':') + 1));
}

template <typename Fact>
const Fact& part_fact_of(const std::map<std::string, Fact>& section, const std::string& name, const std::string& section_name) {
    const Fact* fact = part_fact(section, name);
    if (!fact) throw std::runtime_error("part facts: " + name + " has no " + section_name + " entry in the part facts");
    return *fact;
}

struct PartFacts {
    std::filesystem::path file;
    std::map<std::string, PartClass> classes;
    std::map<std::string, PartHeight> stated_heights;
    ConnectorFacts connectors;
    ThermalFacts thermal;
    ThermalCopperFacts thermal_copper;
    EpViaFacts ep_vias;
    IsolationFacts isolation;
    RegulatorFacts regulators;
    ZenerFacts zeners;
    ReferencePinFacts reference_pins;
    ControlGridFacts control_grid;
    ModelOverrideFacts model_overrides;
    FootprintAliasFacts footprint_aliases;
};

struct ModelRoots {
    std::filesystem::path model_directory, project_root, parts_directory;
};

std::string_view part_class_name(PartClass part_class);
PartClass part_class_named(std::string_view name);
bool presents_on_top(PartClass part_class);

const ConnectorFact* connector_fact(const ConnectorFacts& facts, const std::string& name);
const ConnectorFact& connector_fact_of(const ConnectorFacts& facts, const std::string& name);
std::pair<int, int> mating_face_vector(const ConnectorFact& fact);
ConnectorFacts load_connector_facts(const std::filesystem::path& parts_directory);

PartFacts load_part_facts(const std::filesystem::path& file);
PartFacts load_part_facts_in(const std::filesystem::path& parts_directory);
const ThermalFieldFact* thermal_field_for(const ThermalCopperFacts& rows, const RegulatorFacts& regulators, const std::string& value);
const EpViaFact* ep_via_for(const EpViaFacts& rows, const RegulatorFacts& regulators, const std::string& value);
const PartFacts& default_part_facts();
PartClass symbol_class(const PartFacts& facts, const std::string& symbol, const std::string& part);
double model_top(const std::string& text, const std::string& extension, const std::string& model);
PartHeight footprint_height(const PartFacts& facts, const std::string& footprint, const Sexpr& document,
                            const ModelRoots& roots, const std::string& part);
PartHeight model_height(const std::string& raw_path, const ModelRoots& roots, const std::string& part);

}
