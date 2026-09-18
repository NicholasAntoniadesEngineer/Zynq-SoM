#pragma once

// Transitional transport only; every routing decision lives in the native core.
// Integration in module.cpp:
//   #include "schgen/schematic_route_bindings.hpp"
//   schgen::bind_schematic_route(m);
// No S-expression converter is needed: routing consumes symbol pin metadata.
#include "schgen/json_bindings.hpp"
#include "schgen/schematic_route.hpp"
#include "schgen/symbol_bindings.hpp"

#include <nanobind/nanobind.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/tuple.h>
#include <nanobind/stl/vector.h>

#include <map>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace schgen {
namespace schematic_route_binding_detail {

// This is deliberately a transport conversion, not parse_circuit_ir: route()
// accepts empty/intermediate circuits, with electrical validation at its caller.
inline CircuitSheetIr circuit_from_python(const nanobind::dict& raw) {
    namespace nb = nanobind;
    CircuitSheetIr circuit;
    if (raw.contains("name")) circuit.name = nb::cast<std::string>(raw["name"]);
    for (const auto item : nb::cast<nb::iterable>(raw["nets"])) {
        const auto row = nb::cast<nb::dict>(item);
        CircuitNetIr net;
        net.name = nb::cast<std::string>(row["name"]);
        net.net_class = nb::cast<std::string>(row["net_class"]);
        for (const auto pin : nb::cast<nb::iterable>(row["pins"])) {
            // Accept Circuit.to_ir() pin strings as well as structured frozen
            // placement snapshots and the minimal route.py adapter transport.
            if (nb::isinstance<nb::str>(pin)) {
                const auto spec = nb::cast<std::string>(pin);
                const auto dot = spec.rfind('.');
                if (dot == std::string::npos)
                    throw nb::value_error("schematic_route: expected REF.PIN");
                net.pins.push_back({spec.substr(0, dot), spec.substr(dot + 1)});
            } else {
                const auto ref = nb::cast<nb::dict>(pin);
                net.pins.push_back({nb::cast<std::string>(ref["ref"]),
                                    nb::cast<std::string>(ref["pin"])});
            }
        }
        circuit.nets.push_back(std::move(net));
    }
    return circuit;
}

inline SchematicRoutePlacement placement_from_python(const nanobind::dict& raw) {
    namespace nb = nanobind;
    // Reuse the emitter's typed placement decoder for all common records.
    auto design = schematic_design_from_json(json_from_python(raw), {});
    SchematicRoutePlacement placement;
    placement.parts = std::move(design.parts);
    placement.powers = std::move(design.powers);
    placement.hlabels = std::move(design.hlabels);
    placement.llabels = std::move(design.llabels);
    placement.no_connects = std::move(design.no_connects);
    if (raw.contains("plans")) {
        for (const auto [key, paths] : nb::cast<nb::dict>(raw["plans"]))
            placement.plans.emplace_back(nb::cast<std::string>(key),
                nb::cast<std::vector<std::vector<RoutePoint>>>(paths));
    }
    if (raw.contains("boxes")) {
        for (const auto item : nb::cast<nb::iterable>(raw["boxes"])) {
            const auto row = nb::cast<nb::dict>(item);
            VisualBox box;
            box.x0 = nb::cast<double>(row["x0"]); box.y0 = nb::cast<double>(row["y0"]);
            box.x1 = nb::cast<double>(row["x1"]); box.y1 = nb::cast<double>(row["y1"]);
            if (row.contains("kind")) box.kind = nb::cast<std::string>(row["kind"]);
            if (row.contains("owner")) box.owner = nb::cast<std::string>(row["owner"]);
            placement.boxes.push_back(std::move(box));
        }
    }
    if (raw.contains("label_bridged"))
        for (const auto net : nb::cast<nb::iterable>(raw["label_bridged"]))
            placement.label_bridged.insert(nb::cast<std::string>(net));
    return placement;
}

}  // namespace schematic_route_binding_detail

inline void bind_schematic_route(nanobind::module_& m) {
    namespace nb = nanobind;
    nb::exception<SchematicRouteError>(m, "SchematicRouteError", PyExc_ValueError);
    m.def("schematic_route", [](const nb::dict& raw_circuit,
            const nb::dict& raw_placement, const nb::object& get_symbol) {
        if (!PyCallable_Check(get_symbol.ptr()))
            throw nb::type_error("schematic_route: get_symbol must be callable");
        const auto circuit = schematic_route_binding_detail::circuit_from_python(raw_circuit);
        const auto placement = schematic_route_binding_detail::placement_from_python(raw_placement);
        std::map<std::string, SymbolDef> definitions;
        const auto resolve = [&](const std::string& id) -> const SymbolDef& {
            const auto found = definitions.find(id);
            if (found != definitions.end()) return found->second;
            nb::gil_scoped_acquire acquire;
            const nb::object source = get_symbol(nb::cast(id));
            SymbolDef definition;
            definition.lib_id = id;
            for (const auto pin : nb::cast<nb::iterable>(source.attr("pins")))
                definition.pins.push_back(symbol_pin_from_python(pin));
            return definitions.emplace(id, std::move(definition)).first->second;
        };
        SchematicRoutedSheet routed;
        {
            nb::gil_scoped_release release;
            routed = route_schematic(circuit, placement, resolve);
        }
        // Plain immutable rows reconstruct the existing Python Seg/dataclass
        // boundary without registering duplicate native geometry Python types.
        std::vector<std::tuple<double, double, double, double, std::string>> segs;
        for (const auto& seg : routed.segs)
            segs.emplace_back(seg.x0, seg.y0, seg.x1, seg.y1, seg.net);
        std::vector<RoutePoint> junctions;
        for (const auto& point : routed.junctions) junctions.emplace_back(point.x, point.y);
        return nb::make_tuple(segs, junctions);
    }, nb::arg("circuit"), nb::arg("placement"), nb::arg("get_symbol"));
    m.def("schematic_route_components", &schematic_route_components,
        nb::arg("legs"), nb::arg("pin_points"), nb::arg("power_points"),
        nb::arg("label_points"), nb::arg("bonds"), nb::call_guard<nb::gil_scoped_release>());
    m.def("schematic_route_join", &schematic_route_join,
        nb::arg("grid"), nb::arg("net"), nb::arg("first"), nb::arg("second"),
        nb::call_guard<nb::gil_scoped_release>());
}

}  // namespace schgen
