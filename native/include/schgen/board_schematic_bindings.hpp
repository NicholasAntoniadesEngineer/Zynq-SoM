#pragma once

// Transitional transport; hierarchy, references, flags and all gates are native.
#include "schgen/board_schematic.hpp"
#include "schgen/schematic_route_bindings.hpp"

namespace schgen {
template<class FromPython>
void bind_board_schematic(nanobind::module_& m, FromPython from_python) {
    namespace nb = nanobind;
    nb::exception<BoardSchematicError>(m, "BoardSchematicError", PyExc_ValueError);
    m.def("board_renamed_ref", &board_renamed_ref);
    m.def("build_board_schematic", [from_python](const nb::list& rows,
            const symbol_binding_detail::Library& source_library,
            const std::string& output, const std::string& root_name,
            const std::string& sheet_subdir, const std::string& reports_dir) {
        std::vector<BoardSheetInput> inputs;
        for (const auto item : rows) {
            const auto row = nb::cast<nb::dict>(item);
            BoardSheetInput input;
            input.circuit = decode_intermediate_circuit_ir(json_from_python(row["circuit"]));
            input.reference_band = nb::cast<std::int64_t>(row["band"]);
            if (row.contains("placement")) {
                const auto raw = nb::cast<nb::dict>(row["placement"]);
                BoardPreparedSheet prepared;
                static_cast<SchematicRoutePlacement&>(prepared.placement) =
                    schematic_route_binding_detail::placement_from_python(raw);
                prepared.placement.paper = nb::cast<std::string>(raw["paper"]);
                for (const auto segment : nb::cast<nb::iterable>(row["segments"])) {
                    const auto s = nb::cast<nb::dict>(segment);
                    prepared.routed.segs.push_back({nb::cast<double>(s["x0"]), nb::cast<double>(s["y0"]),
                        nb::cast<double>(s["x1"]), nb::cast<double>(s["y1"]), nb::cast<std::string>(s["net"])});
                }
                for (const auto point : nb::cast<std::vector<RoutePoint>>(row["junctions"]))
                    prepared.routed.junctions.push_back({point.first, point.second});
                input.prepared = std::move(prepared);
            }
            inputs.push_back(std::move(input));
        }
        auto library = source_library.snapshot(from_python);
        BoardSchematicResult result;
        {
            nb::gil_scoped_release release;
            BoardSchematicOptions options;
            options.root_name = root_name; options.sheet_subdir = sheet_subdir;
            options.reports_dir = reports_dir;
            result = build_board_schematic(inputs, library, output, options);
        }
        return nb::make_tuple(result.ok(), result.report);
    });
    m.def("board_netlist_gate", [from_python](const nb::list& rows,
            const symbol_binding_detail::Library& source_library,
            const std::string& root, const std::string& reports) {
        std::vector<BoardPlacedSheet> sheets;
        for (const auto item : rows) {
            const auto row = nb::cast<nb::dict>(item);
            auto circuit = decode_intermediate_circuit_ir(json_from_python(row["circuit"]));
            auto design = schematic_design_from_json(json_from_python(row["design"]), std::move(circuit));
            sheets.push_back({nb::cast<std::string>(row["name"]), std::move(design),
                              nb::cast<std::string>(row["uuid"])});
        }
        auto library = source_library.snapshot(from_python);
        BoardNetlistResult result;
        {
            nb::gil_scoped_release release;
            result = check_board_netlist(sheets, root, reports, library);
        }
        return nb::make_tuple(result.ok(), result.summary());
    });
}
}  // namespace schgen
