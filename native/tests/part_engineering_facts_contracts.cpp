#include "schgen/part_facts.hpp"

#include <array>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using namespace schgen;

namespace fixture {
const std::array<std::string, 10> sections{"thermal", "thermal_copper", "ep_vias", "isolation", "regulators",
                                           "zeners", "reference_pins", "control_grid", "model_overrides", "footprint_aliases"};
const std::string part = "P1";
const std::string thermal_row =
    "{\"rth_ja\": 118.9, \"tj_max\": 125.0, \"rds_on\": 0.0, \"eff\": 0.85, \"package\": \"SOT-23-THIN-6\", \"cite\": \"fixture\", "
    "\"pour\": {\"rth_ja\": 35.0, \"cite\": \"fixture pour\", \"evidence\": \"P1\"}}";
const std::string plain_thermal_row =
    "{\"rth_ja\": 250.0, \"tj_max\": 150.0, \"rds_on\": 0.095, \"eff\": 0.85, \"package\": \"SOT-23-5\", \"cite\": \"fixture\"}";
const std::string copper_row =
    "{\"need\": {\"min_vias\": 2, \"radius_mm\": 3.0, \"pour_layers\": [\"F.Cu\"]}, "
    "\"field\": {\"via_offsets_mm\": [[-1.15, 0.0], [1.15, 0.0]], \"max_vias\": 3, \"pour_box_mm\": [-2.9, -1.6, 2.9, 1.6], "
    "\"pour_layers\": [\"F.Cu\"], \"cite\": \"fixture\"}}";
const std::string ep_row = "{\"min_pads\": 4, \"radius_mm\": 1.5}";
const std::string isolation_row = "{\"margin_mm\": 0.6}";
const std::string regulator_row =
    "{\"kind\": \"buck\", \"limit_a\": 6.0, \"eff\": 0.9, \"in_pin\": \"8\", \"out_pin\": \"10\", \"ilim_num\": 6800.0, "
    "\"note\": \"fixture\", \"fb_vref\": 1.0, \"enable\": {\"en_pin\": \"7\", \"vin_pins\": [\"8\", \"12\"]}}";
const std::string switch_row =
    "{\"kind\": \"load_switch\", \"eff\": 1.0, \"in_pin\": \"IN\", \"out_pin\": \"OUT\", \"iset_pin\": \"ISET\", "
    "\"ilim_num\": 6800.0, \"note\": \"fixture\", \"iset_v\": 0.2, \"enable\": {\"ihys_a\": 1.55e-6, \"recommended_max_v\": 5.5, "
    "\"threshold_v\": 1.21}}";
const std::string zener_row = "{\"vz_min_v\": 4.845, \"vz_max_v\": 5.355, \"izt_a\": 0.02, \"zzt_ohm\": 17.0}";
const std::string reference_row = "{\"vref1_pin\": \"2\", \"vref2_pin\": \"7\"}";
const std::string grid_row = "{\"button_gap_mm\": 2.0}";
const std::string override_row =
    "{\"footprint\": \"Package_DFN_QFN:fixture\", \"path\": \"${KIPRJMOD}/../parts/P1/P1.wrl\", \"rotation_z_deg\": 90}";
const std::string alias_row = "{\"footprint\": \"Capacitor_SMD:C_1206_3216Metric\"}";
}

void require(bool condition, const std::string& what) {
    if (!condition) throw std::runtime_error("part engineering facts contract failed: " + what);
}

template <typename Action>
void refuses(Action action, const std::string& names, const std::string& what) {
    try {
        action();
    } catch (const std::runtime_error& error) {
        require(std::string(error.what()).find(names) != std::string::npos, what + " names " + names);
        return;
    }
    throw std::runtime_error("part engineering facts contract failed: " + what);
}

std::filesystem::path write_facts(const std::filesystem::path& scratch, const std::string& section, const std::string& body,
                                  bool leave_out = false) {
    std::filesystem::create_directories(scratch / fixture::part);
    const auto file = scratch / "facts.json";
    std::ofstream out(file, std::ios::binary);
    out << "{\"schema\": \"schgen.part_facts/3\", \"classes\": {\"Device:R\": \"resistor\"}, \"connectors\": {}, \"stated_heights\": {}";
    for (const std::string& name : fixture::sections) {
        if (name == section && leave_out) continue;
        out << ", \"" << name << "\": " << (name == section ? body : std::string("{}"));
    }
    out << "}";
    return file;
}

PartFacts facts_from(const std::filesystem::path& scratch, const std::string& section, const std::string& body) {
    return load_part_facts(write_facts(scratch, section, body));
}

std::string rows(const std::string& row) { return "{\"" + fixture::part + "\": " + row + "}"; }

std::string with(std::string row, const std::string& from, const std::string& to) {
    require(row.find(from) != std::string::npos, "the fixture holds " + from);
    row.replace(row.find(from), from.size(), to);
    return row;
}

void refused_everywhere(const std::filesystem::path& scratch, const std::string& section, const std::string& row) {
    refuses([&] { facts_from(scratch, section, rows(with(row, "{\"", "{\"unknown_key\": 1, \""))); }, "unknown_key",
            section + ": an unknown key is refused");
    refuses([&] { facts_from(scratch, section, "{\"P2\": " + row + "}"); }, section + " P2",
            section + ": a part with no folder is refused naming the section and the key");
    refuses([&] { facts_from(scratch, section, "{\"..\": " + row + "}"); }, section + " ..",
            section + ": a key that is not a folder name is refused");
    refuses([&] { facts_from(scratch, section, "{\"P1\": " + row + ", \"P1\": " + row + "}"); }, "duplicate key 'P1'",
            section + ": a duplicate key is refused by the JSON reader naming the key");
    refuses([&] { facts_from(scratch, section, "{\"P1\": 3}"); }, section + " P1", section + ": a row that is not an object is refused");
    refuses([&] { facts_from(scratch, section, "[]"); }, section, section + ": a section that is not an object is refused");
    refuses([&] { load_part_facts(write_facts(scratch, section, "{}", true)); }, section, section + ": an absent section is refused");
    const auto file = write_facts(scratch, section, rows(row));
    require(load_part_facts(file).file == file, section + ": the good row loads");
}

void thermal_facts(const std::filesystem::path& scratch) {
    const PartFacts good = facts_from(scratch, "thermal", rows(fixture::thermal_row));
    const ThermalFact& fact = part_fact_of(good.thermal, "P1", "thermal");
    require(fact.rth_ja == 118.9 && fact.tj_max == 125.0 && fact.rds_on == 0.0 && fact.eff == 0.85, "a thermal row carries its numbers");
    require(fact.package == "SOT-23-THIN-6" && fact.cite == "fixture", "a thermal row carries its text");
    require(fact.pour && fact.pour->rth_ja == 35.0 && fact.pour->cite == "fixture pour" && fact.pour->evidence == "P1",
            "a thermal row carries its pour");
    const PartFacts plain = facts_from(scratch, "thermal", rows(fixture::plain_thermal_row));
    require(!part_fact_of(plain.thermal, "P1", "thermal").pour, "an absent pour stays absent");
    require(part_fact(plain.thermal, "P2") == nullptr, "a name without a row has no fact");
    refuses([&] { part_fact_of(plain.thermal, "P2", "thermal"); }, "P2", "a required fact for an unknown name is refused");
    refused_everywhere(scratch, "thermal", fixture::thermal_row);
    refuses([&] { facts_from(scratch, "thermal", rows(with(fixture::thermal_row, "118.9", "\"hot\""))); }, "rth_ja",
            "thermal: a text rth_ja is refused");
    refuses([&] { facts_from(scratch, "thermal", rows(with(fixture::thermal_row, "\"eff\": 0.85", "\"eff\": 1.5"))); }, "eff",
            "thermal: an efficiency above 1 is refused");
    refuses([&] { facts_from(scratch, "thermal", rows(with(fixture::thermal_row, "\"package\": \"SOT-23-THIN-6\", ", ""))); },
            "package", "thermal: a row without a package is refused");
    refuses([&] { facts_from(scratch, "thermal", rows(with(fixture::thermal_row, "\"evidence\": \"P1\"", "\"evidence\": 4"))); },
            "evidence", "thermal: a pour evidence that is not text is refused");
    refuses([&] { facts_from(scratch, "thermal", rows(with(fixture::thermal_row, "\"cite\": \"fixture pour\", ", ""))); },
            "cite", "thermal: a pour without a citation is refused");
    refuses([&] { facts_from(scratch, "thermal", rows(with(fixture::thermal_row, "\"rds_on\": 0.0", "\"rds_on\": -1"))); },
            "rds_on", "thermal: a negative on-resistance is refused");
}

void copper_facts(const std::filesystem::path& scratch) {
    const PartFacts good = facts_from(scratch, "thermal_copper", rows(fixture::copper_row));
    const ThermalCopperFact& fact = part_fact_of(good.thermal_copper, "P1", "thermal_copper");
    require(fact.need.min_vias == 2 && fact.need.radius_mm == 3.0 && fact.need.pour_layers == std::vector<std::string>{"F.Cu"},
            "a copper row carries its need");
    require(fact.field.via_offsets_mm.size() == 2 && fact.field.via_offsets_mm.front() == std::make_pair(-1.15, 0.0) &&
                fact.field.max_vias == 3 && fact.field.pour_box_mm == std::array<double, 4>{-2.9, -1.6, 2.9, 1.6} &&
                fact.field.pour_layers == std::vector<std::string>{"F.Cu"} && fact.field.cite == "fixture",
            "a copper row carries its field");
    refused_everywhere(scratch, "thermal_copper", fixture::copper_row);
    refuses([&] { facts_from(scratch, "thermal_copper", rows(with(fixture::copper_row, "\"min_vias\": 2", "\"min_vias\": 2.5"))); },
            "min_vias", "thermal_copper: a fractional via count is refused");
    refuses([&] { facts_from(scratch, "thermal_copper", rows(with(fixture::copper_row, "\"need\": {", "\"need\": {\"extra\": 1, "))); },
            "extra", "thermal_copper: an unknown key inside need is refused");
    refuses([&] { facts_from(scratch, "thermal_copper", rows(with(fixture::copper_row, "\"cite\": \"fixture\"", "\"citation\": \"fixture\""))); },
            "citation", "thermal_copper: an unknown key inside field is refused");
    refuses([&] { facts_from(scratch, "thermal_copper", rows(with(fixture::copper_row, "[-2.9, -1.6, 2.9, 1.6]", "[-2.9, -1.6, 2.9]"))); },
            "pour_box_mm", "thermal_copper: a box of three numbers is refused");
    refuses([&] { facts_from(scratch, "thermal_copper", rows(with(fixture::copper_row, "[-2.9, -1.6, 2.9, 1.6]", "[2.9, -1.6, -2.9, 1.6]"))); },
            "pour_box_mm", "thermal_copper: an inverted box is refused");
    refuses([&] { facts_from(scratch, "thermal_copper", rows(with(fixture::copper_row, "[[-1.15, 0.0], [1.15, 0.0]]", "[[-1.15], [1.15, 0.0]]"))); },
            "via_offsets_mm", "thermal_copper: an offset that is not a pair is refused");
    refuses([&] { facts_from(scratch, "thermal_copper", rows(with(fixture::copper_row, "\"pour_layers\": [\"F.Cu\"], \"cite\"", "\"pour_layers\": [4], \"cite\""))); },
            "pour_layers", "thermal_copper: a layer that is not text is refused");
    refuses([&] { facts_from(scratch, "thermal_copper", rows(with(fixture::copper_row, "\"need\": {\"min_vias\": 2, \"radius_mm\": 3.0, \"pour_layers\": [\"F.Cu\"]}, ", ""))); },
            "need", "thermal_copper: a row without a need is refused");
}

void small_facts(const std::filesystem::path& scratch) {
    const PartFacts ep = facts_from(scratch, "ep_vias", rows(fixture::ep_row));
    require(part_fact_of(ep.ep_vias, "P1", "ep_vias").min_pads == 4 && part_fact_of(ep.ep_vias, "P1", "ep_vias").radius_mm == 1.5,
            "an ep_vias row carries its numbers");
    refused_everywhere(scratch, "ep_vias", fixture::ep_row);
    refuses([&] { facts_from(scratch, "ep_vias", rows(with(fixture::ep_row, "\"min_pads\": 4", "\"min_pads\": \"4\""))); }, "min_pads",
            "ep_vias: a text count is refused");
    const PartFacts isolation = facts_from(scratch, "isolation", rows(fixture::isolation_row));
    require(part_fact_of(isolation.isolation, "P1", "isolation").margin_mm == 0.6, "an isolation row carries its margin");
    refused_everywhere(scratch, "isolation", fixture::isolation_row);
    refuses([&] { facts_from(scratch, "isolation", rows(with(fixture::isolation_row, "0.6", "true"))); }, "margin_mm",
            "isolation: a margin that is not a number is refused");
    const PartFacts zener = facts_from(scratch, "zeners", rows(fixture::zener_row));
    const ZenerFact& z = part_fact_of(zener.zeners, "P1", "zeners");
    require(z.vz_min_v == 4.845 && z.vz_max_v == 5.355 && z.izt_a == 0.02 && z.zzt_ohm == 17.0, "a zener row carries its numbers");
    refused_everywhere(scratch, "zeners", fixture::zener_row);
    refuses([&] { facts_from(scratch, "zeners", rows(with(fixture::zener_row, "\"zzt_ohm\": 17.0", "\"zzt_ohm\": null"))); }, "zzt_ohm",
            "zeners: a null impedance is refused");
    refuses([&] { facts_from(scratch, "zeners", rows(with(fixture::zener_row, "\"vz_min_v\": 4.845", "\"vz_min_v\": 6"))); }, "vz_min_v",
            "zeners: a minimum above the maximum is refused");
    const PartFacts reference = facts_from(scratch, "reference_pins", rows(fixture::reference_row));
    require(part_fact_of(reference.reference_pins, "P1", "reference_pins").vref1_pin == "2" &&
                part_fact_of(reference.reference_pins, "P1", "reference_pins").vref2_pin == "7",
            "a reference_pins row carries its pins");
    refused_everywhere(scratch, "reference_pins", fixture::reference_row);
    refuses([&] { facts_from(scratch, "reference_pins", rows(with(fixture::reference_row, "\"7\"", "7"))); }, "vref2_pin",
            "reference_pins: a pin that is not text is refused");
    refuses([&] { facts_from(scratch, "reference_pins", rows(with(fixture::reference_row, "\"7\"", "\"2\""))); }, "vref2_pin",
            "reference_pins: the same pin twice is refused");
    const PartFacts grid = facts_from(scratch, "control_grid", rows(fixture::grid_row));
    require(part_fact_of(grid.control_grid, "P1", "control_grid").button_gap_mm == 2.0, "a control_grid row carries its gap");
    refused_everywhere(scratch, "control_grid", fixture::grid_row);
    refuses([&] { facts_from(scratch, "control_grid", rows(with(fixture::grid_row, "2.0", "\"2\""))); }, "button_gap_mm",
            "control_grid: a text gap is refused");
    const PartFacts model = facts_from(scratch, "model_overrides", rows(fixture::override_row));
    const ModelOverrideFact& m = part_fact_of(model.model_overrides, "P1", "model_overrides");
    require(m.footprint == "Package_DFN_QFN:fixture" && m.path == "${KIPRJMOD}/../parts/P1/P1.wrl" && m.rotation_z_deg == 90,
            "a model_overrides row carries its model");
    refused_everywhere(scratch, "model_overrides", fixture::override_row);
    refuses([&] { facts_from(scratch, "model_overrides", rows(with(fixture::override_row, "\"rotation_z_deg\": 90", "\"rotation_z_deg\": \"90\""))); },
            "rotation_z_deg", "model_overrides: a text rotation is refused");
    refuses([&] { facts_from(scratch, "model_overrides", rows(with(fixture::override_row, "\"path\": \"${KIPRJMOD}/../parts/P1/P1.wrl\", ", ""))); },
            "path", "model_overrides: a row without a path is refused");
}

void regulator_facts(const std::filesystem::path& scratch) {
    const PartFacts buck = facts_from(scratch, "regulators", rows(fixture::regulator_row));
    const RegulatorFact& fact = part_fact_of(buck.regulators, "P1", "regulators");
    require(fact.kind == "buck" && fact.limit_a == 6.0 && fact.eff == 0.9 && fact.in_pin == "8" && fact.out_pin == "10" &&
                fact.ilim_num == 6800.0 && fact.note == "fixture" && fact.fb_vref == 1.0,
            "a regulator row carries its fields");
    require(!fact.iset_pin && !fact.iset_v, "absent optional fields stay absent");
    require(fact.enable && fact.enable->direct && fact.enable->direct->en_pin == "7" &&
                fact.enable->direct->vin_pins == std::vector<std::string>{"8", "12"} && !fact.enable->network,
            "a regulator row carries its direct enable");
    const PartFacts load = facts_from(scratch, "regulators", rows(fixture::switch_row));
    const RegulatorFact& other = part_fact_of(load.regulators, "P1", "regulators");
    require(other.iset_pin == "ISET" && other.iset_v == 0.2 && !other.limit_a && !other.fb_vref, "a switch row carries its ISET fields");
    require(other.enable && !other.enable->direct && other.enable->network && other.enable->network->ihys_a == 1.55e-6 &&
                other.enable->network->recommended_max_v == 5.5 && other.enable->network->threshold_v == 1.21,
            "a switch row carries its enable network");
    refused_everywhere(scratch, "regulators", fixture::regulator_row);
    refuses([&] { facts_from(scratch, "regulators", rows(with(fixture::regulator_row, "\"limit_a\": 6.0", "\"limit_a\": null"))); }, "limit_a",
            "regulators: a null limit is refused, absence is how a missing limit is stated");
    refuses([&] { facts_from(scratch, "regulators", rows(with(fixture::regulator_row, "\"in_pin\": \"8\"", "\"in_pin\": 8"))); }, "in_pin",
            "regulators: a numeric pin is refused");
    refuses([&] { facts_from(scratch, "regulators", rows(with(fixture::regulator_row, "\"eff\": 0.9", "\"eff\": 0"))); }, "eff",
            "regulators: a zero efficiency is refused");
    refuses([&] { facts_from(scratch, "regulators", rows(with(fixture::regulator_row, "\"kind\": \"buck\", ", ""))); }, "kind",
            "regulators: a row without a kind is refused");
    refuses([&] { facts_from(scratch, "regulators", rows(with(fixture::regulator_row, "\"en_pin\": \"7\", ", ""))); }, "en_pin",
            "regulators: vin_pins without en_pin is refused");
    refuses([&] { facts_from(scratch, "regulators", rows(with(fixture::regulator_row, "\"vin_pins\": [\"8\", \"12\"]", "\"vin_pins\": \"8\""))); },
            "vin_pins", "regulators: vin_pins that is not a list is refused");
    refuses([&] { facts_from(scratch, "regulators", rows(with(fixture::regulator_row, "\"en_pin\": \"7\"", "\"extra\": 1"))); }, "extra",
            "regulators: an unknown key inside enable is refused");
    refuses([&] { facts_from(scratch, "regulators", rows(with(fixture::switch_row, "\"threshold_v\": 1.21", "\"threshold_v\": \"low\""))); },
            "threshold_v", "regulators: a text threshold is refused");
    refuses([&] { facts_from(scratch, "regulators", rows(with(fixture::switch_row, "\"recommended_max_v\": 5.5, ", ""))); }, "recommended_max_v",
            "regulators: an incomplete enable network is refused");
    refuses([&] { facts_from(scratch, "regulators", rows(with(fixture::regulator_row, "\"enable\": {\"en_pin\": \"7\", \"vin_pins\": [\"8\", \"12\"]}", "\"enable\": {}"))); },
            "enable", "regulators: an empty enable is refused");
}

void alias_facts(const std::filesystem::path& scratch) {
    const std::string key = "Capacitor_SMD:C_1206_3225Metric";
    const PartFacts good = facts_from(scratch, "footprint_aliases", "{\"" + key + "\": " + fixture::alias_row + "}");
    require(part_fact_of(good.footprint_aliases, key, "footprint_aliases").footprint == "Capacitor_SMD:C_1206_3216Metric",
            "an alias row names its replacement footprint");
    refuses([&] { facts_from(scratch, "footprint_aliases", "{\"" + key + "\": " + with(fixture::alias_row, "{\"", "{\"unknown_key\": 1, \"") + "}"); },
            "unknown_key", "footprint_aliases: an unknown key is refused");
    refuses([&] { facts_from(scratch, "footprint_aliases", "{\"" + key + "\": {\"footprint\": 3}}"); }, "footprint_aliases " + key,
            "footprint_aliases: a replacement that is not text is refused naming the section and the key");
    refuses([&] { facts_from(scratch, "footprint_aliases", "{\"" + key + "\": " + fixture::alias_row + ", \"" + key + "\": " + fixture::alias_row + "}"); },
            "duplicate key '" + key + "'", "footprint_aliases: a duplicate key is refused");
    refuses([&] { facts_from(scratch, "footprint_aliases", "{\"" + key + "\": 3}"); }, "footprint_aliases " + key,
            "footprint_aliases: a row that is not an object is refused");
    refuses([&] { facts_from(scratch, "footprint_aliases", "[]"); }, "footprint_aliases", "footprint_aliases: a section that is not an object is refused");
    refuses([&] { load_part_facts(write_facts(scratch, "footprint_aliases", "{}", true)); }, "footprint_aliases",
            "footprint_aliases: an absent section is refused");
}

void repository_sections_are_empty(const std::filesystem::path& repository) {
    const PartFacts facts = load_part_facts(repository / "parts" / "part_facts.json");
    require(facts.thermal.empty() && facts.thermal_copper.empty() && facts.ep_vias.empty() && facts.isolation.empty() &&
                facts.regulators.empty() && facts.zeners.empty() && facts.reference_pins.empty() && facts.control_grid.empty() &&
                facts.model_overrides.empty() && facts.footprint_aliases.empty(),
            "the repository file carries every engineering section, empty");
}

}

int main(int argc, char** argv) {
    try {
        if (argc != 3) throw std::runtime_error("usage: part_engineering_facts_contracts REPOSITORY SCRATCH");
        const std::filesystem::path scratch = argv[2];
        std::filesystem::remove_all(scratch);
        std::filesystem::create_directories(scratch);
        thermal_facts(scratch);
        copper_facts(scratch);
        small_facts(scratch);
        regulator_facts(scratch);
        alias_facts(scratch);
        repository_sections_are_empty(std::filesystem::absolute(argv[1]));
        std::cout << "part engineering facts contracts ok\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 1;
    }
}
