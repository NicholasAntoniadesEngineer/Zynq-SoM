#include "schgen/board_files.hpp"
#include "schgen/json.hpp"
#include "schgen/link.hpp"
#include "schgen/module_pin_map.hpp"
#include "schgen/project.hpp"
#include "schgen/project_outputs.hpp"
#include "schgen/sheet_roles.hpp"

#include <algorithm>
#include <filesystem>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>

namespace {
using namespace schgen;
const int expected_arguments = 2;
const char* const empty_cell = module_pin_map_empty_cell;
std::size_t checks = 0;
void require(bool test, const std::string& why) {
    ++checks;
    if (!test) throw std::runtime_error(why);
}

const JsonNode& field(const JsonNode& node, const std::string& key, JsonKind kind, const std::string& where) {
    const JsonNode* found = object_field(node, key);
    require(found && found->kind == kind, where + " field " + key + " is missing or has the wrong type");
    return *found;
}

XdcStrings dictionary(const JsonNode& node, const std::string& where) {
    require(node.kind == JsonKind::Object, where + " is not a dictionary");
    XdcStrings out;
    for (const auto& [key, value] : node.object_value) {
        require(value.kind == JsonKind::String, where + " holds a value that is not a string");
        out.emplace_back(key, value.string_value);
    }
    return out;
}

SomZynq snapshot_live(const JsonNode& node, const std::string& where) {
    SomZynq live;
    live.zynq_ref = field(node, "zynq_ref", JsonKind::String, where).string_value;
    live.source = field(node, "source", JsonKind::String, where).string_value;
    live.value = field(node, "value", JsonKind::String, where).string_value;
    live.pin_names = dictionary(field(node, "pin_names", JsonKind::Object, where), where + " pin_names");
    live.ball_net = dictionary(field(node, "ball_net", JsonKind::Object, where), where + " ball_net");
    live.jpin_net = dictionary(field(node, "jpin_net", JsonKind::Object, where), where + " jpin_net");
    return live;
}

bool rejected(const ModulePinMap& map, const ModulePinInputs& inputs, const std::vector<XdcPin>& constraints) {
    return !verify_module_pin_map(map, inputs, constraints).empty();
}

const ModulePinRow& first_where(const ModulePinMap& map, bool (*wanted)(const ModulePinRow&)) {
    const auto found = std::find_if(map.rows.begin(), map.rows.end(), wanted);
    if (found == map.rows.end()) throw std::runtime_error("the pin map has no row of the wanted kind");
    return *found;
}

ModulePinRow& row_at(ModulePinMap& map, const ModulePinRow& original) {
    const auto found = std::find_if(map.rows.begin(), map.rows.end(), [&](const ModulePinRow& row) {
        return row.connector == original.connector && row.pin == original.pin;
    });
    return *found;
}

void board(const std::filesystem::path& root, const std::string& project) {
    const auto paths = resolve_project_paths(root, project);
    const auto circuits = load_project_circuits(paths);
    std::vector<CircuitSheetIr> sheets;
    for (const auto& item : circuits) sheets.push_back(item.circuit);
    const auto module_sheets = sheet_module_connectors(load_sheet_roles(paths, circuits));
    const SomInterface module = load_som_interface(paths.som_interface_file);
    const auto mapping_path = paths.project_root / "som_mapping.json";
    const LinkMapping mapping = link_mapping_from_json(parse_json_file(mapping_path.string()), paths.module.do_not_load_straps);
    const auto fpga = snapshot_live(field(parse_json_file((root / "native/tests/data/som_real_baseline.json").string()), "zynq", JsonKind::Object, "baseline"),
                                    "baseline zynq");
    const auto controller_live = snapshot_live(
        field(parse_json_file((root / "native/tests/data/firmware_docs" / project / "inputs.json").string()), "live", JsonKind::Object, "firmware inputs"),
        "firmware inputs live");
    require(fpga.zynq_ref == paths.module.fpga_ref, project + " module data names the FPGA reference of the snapshot");
    require(controller_live.zynq_ref == paths.module.controller_ref, project + " module data names the controller reference of the snapshot");
    const Stm32PinMap controller = stm32_pin_map(controller_live, module);
    XdcInput raw;
    for (const auto& [connector, data] : module.connectors) raw.refs.push_back(connector);
    raw.pins_file = board_file_name(paths.file_stem, BoardFileKind::PinConstraints);
    apply_som_to_xdc(raw, fpga);
    const XdcOutput constraints = generate_xdc(load_project_xdc_input(root, paths.project_root, sheets, raw, paths.som_schematic, paths.som_interface_file));
    const ModulePinInputs inputs{module, mapping, sheets, module_sheets, fpga, controller};

    const ModulePinMap map = build_module_pin_map(inputs);
    const auto errors = verify_module_pin_map(map, inputs, constraints.entries);
    require(errors.empty(), project + " pin map is complete: " + (errors.empty() ? std::string() : errors.front()));
    std::size_t pins = 0;
    for (const auto& [connector, data] : module.connectors) pins += data.pins.size();
    require(pins > 0 && map.rows.size() == pins, project + " one row per module connector pin");
    std::set<std::string> keys;
    for (const auto& row : map.rows) require(keys.insert(row.connector + "." + row.pin).second, project + " pin appears once: " + row.connector + "." + row.pin);
    for (const auto& entry : constraints.entries) {
        require(keys.count(entry.jpin) == 1, project + " constrained pin is in the map: " + entry.jpin);
    }
    require(!constraints.entries.empty(), project + " the constraints assign pins");
    require(std::any_of(map.rows.begin(), map.rows.end(), [](const ModulePinRow& r) { return r.board_net == empty_cell; }), project + " isolated or open pins are listed with no board net");
    require(std::any_of(map.rows.begin(), map.rows.end(), [](const ModulePinRow& r) { return r.sheets != empty_cell && r.port_kind != empty_cell; }),
            project + " pins reach consuming sheets and typed ports");
    require(std::any_of(map.rows.begin(), map.rows.end(), [](const ModulePinRow& r) { return r.ctrl_port != empty_cell; }), project + " pins reach the controller");
    for (const auto& row : map.rows)
        require(row.board_net != empty_cell || (row.sheets == empty_cell && row.port_kind == empty_cell),
                project + " a pin without a board net has no consumer: " + row.connector + "." + row.pin);
    require(map.text() == build_module_pin_map(inputs).text(), project + " report is reproducible");

    const ModulePinRow& with_ball = first_where(map, [](const ModulePinRow& r) { return r.ball != empty_cell; });

    auto dropped = map;
    dropped.rows.erase(dropped.rows.begin());
    require(rejected(dropped, inputs, constraints.entries), project + " mutation: dropped row");

    auto doubled = map;
    doubled.rows.push_back(doubled.rows.front());
    require(rejected(doubled, inputs, constraints.entries), project + " mutation: duplicated row");

    auto renamed = map;
    renamed.rows.front().board_net += "_X";
    require(rejected(renamed, inputs, constraints.entries), project + " mutation: changed board net");

    auto moved = map;
    row_at(moved, with_ball).ball += "_X";
    require(rejected(moved, inputs, constraints.entries), project + " mutation: changed ball");

    auto rebanked = map;
    row_at(rebanked, with_ball).bank += "_X";
    require(rejected(rebanked, inputs, constraints.entries), project + " mutation: changed bank");

    auto foreign = map;
    foreign.rows.front().pin += "_X";
    require(rejected(foreign, inputs, constraints.entries), project + " mutation: pin that is not on the module");
}
}

int main(int argc, char** argv) {
    try {
        if (argc != expected_arguments) throw std::runtime_error("usage: module_pin_map_contracts REPOSITORY");
        const std::filesystem::path root = std::filesystem::absolute(argv[1]);
        board(root, "carrier");
        board(root, "devkit_mini");
        std::cout << "module pin map: " << checks << " assertions passed\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
