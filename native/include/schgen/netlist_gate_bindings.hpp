#pragma once

// Transitional object transport. Do not validate or reload the circuit here:
// the gate must diagnose malformed/intermediate connectivity supplied by callers.
#include "schgen/netlist_gate.hpp"
#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/string_view.h>
#include <nanobind/stl/vector.h>

namespace schgen {
namespace netlist_gate_binding_detail {
inline CircuitSheetIr circuit_from_python(const nanobind::object& source) {
    namespace nb = nanobind;
    CircuitSheetIr circuit;
    circuit.name = nb::cast<std::string>(source.attr("name"));
    for (const auto [key, value] : nb::cast<nb::dict>(source.attr("parts"))) {
        CircuitPartIr part;
        part.ref = nb::cast<std::string>(key);
        part.lib_id = nb::cast<std::string>(value.attr("lib_id"));
        circuit.parts.push_back(std::move(part));
    }
    for (const auto [key, value] : nb::cast<nb::dict>(source.attr("nets"))) {
        (void)key;
        CircuitNetIr net;
        net.name = nb::cast<std::string>(value.attr("name"));
        net.net_class = nb::cast<std::string>(value.attr("net_class").attr("value"));
        for (const auto pin : nb::cast<nb::iterable>(value.attr("pins")))
            net.pins.push_back({nb::cast<std::string>(pin.attr("ref")),
                               nb::cast<std::string>(pin.attr("pin"))});
        circuit.nets.push_back(std::move(net));
    }
    for (const auto pin : nb::cast<nb::iterable>(source.attr("nc_pins")))
        circuit.nc.push_back({nb::cast<std::string>(pin.attr("ref")),
                             nb::cast<std::string>(pin.attr("pin"))});
    return circuit;
}
}

inline void bind_netlist_gate(nanobind::module_& m) {
    namespace nb = nanobind;
    m.def("netlist_normalize_name", &normalize_netlist_name);
    m.def("netlist_extract", [](const std::string& path) {
        ExtractedNetlist nets;
        {
            nb::gil_scoped_release release;
            nets = extract_netlist(std::filesystem::path(path));
        }
        nb::dict result;
        for (const auto& [name, pins] : nets) {
            nb::list rows;
            for (const auto& pin : pins) rows.append(nb::make_tuple(pin.ref, pin.pin));
            result[nb::cast(name)] = rows;
        }
        return result;
    });
    m.def("netlist_dead_two_terminal", [](const nb::object& source) {
        const auto circuit = netlist_gate_binding_detail::circuit_from_python(source);
        nb::gil_scoped_release release;
        return dead_two_terminal(circuit);
    });
    m.def("netlist_emitted_nc_cheats", [](const nb::object& source, const std::string& text) {
        const auto circuit = netlist_gate_binding_detail::circuit_from_python(source);
        nb::gil_scoped_release release;
        return emitted_nc_cheats(circuit, text);
    });
    m.def("netlist_check", [](const nb::object& source, const nb::dict& raw,
                              const std::string& text) {
        const auto circuit = netlist_gate_binding_detail::circuit_from_python(source);
        ExtractedNetlist nets;
        for (const auto [key, value] : raw) {
            std::vector<KicadNetlistPin> pins;
            for (const auto pin : nb::cast<nb::iterable>(value))
                pins.push_back({nb::cast<std::string>(pin.attr("ref")),
                                nb::cast<std::string>(pin.attr("pin"))});
            nets.emplace_back(nb::cast<std::string>(key), std::move(pins));
        }
        NetlistGateResult result;
        {
            nb::gil_scoped_release release;
            result = check_netlist(circuit, nets, text);
        }
        return nb::make_tuple(result.ok, result.shorts, result.opens, result.nc_cheats,
                             result.part_mismatches, result.name_mismatches);
    });
}
}  // namespace schgen
