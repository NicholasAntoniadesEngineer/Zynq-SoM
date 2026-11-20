#pragma once
#include "schgen/board_pipeline.hpp"
#include "schgen/board_schematic.hpp"
#include "schgen/catalog.hpp"
#include "schgen/layout_adapter.hpp"
#include "schgen/part_facts.hpp"
#include "schgen/pcb_model.hpp"
#include "schgen/pcb_placement.hpp"
#include "schgen/project.hpp"

namespace placement_report_fixture {
using namespace schgen;

inline constexpr int grid_columns = 40;
inline constexpr double grid_pitch = 5;
inline constexpr double pad_size = 1;
inline constexpr double part_height = 1;

struct Scene {
    std::vector<CircuitSheetIr> sheets;
    SheetIndex index;
    PcbModel model;
    layout::AuthoredIntent intent;
};

inline std::string net_name(const std::string &sheet, const CircuitNetIr &net) {
    return net.net_class == "signal" ? "/" + sheet + "/" + net.name : net.name;
}

inline Scene scene(const std::filesystem::path &root, const std::string &project) {
    if (!open_part_catalog((root / "native/catalog.bin").string()))
        throw std::runtime_error("cannot open the part catalog");
    const auto paths = resolve_project_paths(root, std::filesystem::path(project));
    const auto authored = author_board_pipeline_inputs(paths);
    Scene out;
    out.index = load_sheet_index(paths);
    std::map<std::string, std::int64_t> bands(out.index.begin(), out.index.end());
    PcbPlacementInput inputs;
    int next_net = 1, count = 0;
    for (const auto &sheet : authored.circuits) {
        out.sheets.push_back(sheet.circuit);
        inputs.floorplan.sheets.push_back(sheet.circuit);
        std::map<std::string, std::vector<std::pair<std::string, std::string>>> pins;
        for (const auto &net : sheet.circuit.nets)
            for (const auto &pin : net.pins)
                pins[pin.ref].emplace_back(pin.pin, net_name(sheet.name, net));
        for (const auto &part : sheet.circuit.parts) {
            PcbCheckInstance inst;
            inst.ref = board_renamed_ref(part.ref, bands.at(sheet.name), sheet.name);
            inst.value = part.value;
            inst.footprint = part.footprint;
            inst.sheet = sheet.name;
            inst.side = count % 2 ? "bottom" : "top";
            inst.x = (count % grid_columns) * grid_pitch;
            inst.y = (count / grid_columns) * grid_pitch;
            ++count;
            inst.part_class = symbol_class(default_part_facts(), part.lib_id, part.ref + " (" + sheet.name + ")");
            inst.height = PartHeight{part_height, "synthetic"};
            std::string text = "(footprint \"synthetic\" (layer \"F.Cu\")";
            for (const auto &[pad, net] : pins[part.ref]) {
                const auto number = out.model.net_numbers.emplace(net, next_net);
                next_net += number.second;
                inst.pad_nets[pad] = {number.first->second, net};
                text += " (pad \"" + pad + "\" smd rect (at 0 0) (size " + std::to_string(pad_size) + " " + std::to_string(pad_size) +
                        ") (layers \"F.Cu\" \"F.Mask\"))";
            }
            inst.mod = pcb_check_footprint("synthetic", text + ")");
            out.model.insts.push_back(std::move(inst));
        }
    }
    inputs.floorplan.sheet_index = out.index;
    out.intent = layout::authored_intent(inputs);
    return out;
}

}
