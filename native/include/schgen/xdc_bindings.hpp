#pragma once

// Integration: include this header in module.cpp and call
// schgen::bind_xdc(m) inside NB_MODULE. Add src/xdc.cpp to schgen_core.
#include "schgen/xdc.hpp"
#include <nanobind/nanobind.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/tuple.h>
#include <nanobind/stl/vector.h>
#include <tuple>

namespace schgen {
inline void bind_xdc(nanobind::module_& m) {
    namespace nb = nanobind;
    m.def("xdc_rail_volts", [](const std::string& rail) {
        try { return xdc_rail_volts(rail); }
        catch (const XdcError& e) { throw nb::value_error(e.what()); }
    });
    m.def("xdc_pin_traits", &xdc_pin_traits);
    m.def("generate_xdc", [](const nb::dict& raw) {
        XdcInput in;
        in.connectors = nb::cast<decltype(in.connectors)>(raw["connectors"]);
        in.ball_net = nb::cast<XdcStrings>(raw["ball_net"]);
        in.pin_names = nb::cast<XdcStrings>(raw["pin_names"]);
        in.jpin_net = nb::cast<XdcStrings>(raw["jpin_net"]);
        in.function_map = nb::cast<XdcStrings>(raw["function_map"]);
        in.bank_rails = nb::cast<XdcStrings>(raw["bank_rails"]);
        in.vcco_rails = nb::cast<XdcStrings>(raw["vcco_rails"]);
        in.refs = nb::cast<std::vector<std::string>>(raw["refs"]);
        if (raw.contains("drift_order"))
            in.drift_order = nb::cast<std::vector<std::string>>(raw["drift_order"]);
        in.device = nb::cast<std::string>(raw["device"]);
        in.zynq_ref = nb::cast<std::string>(raw["zynq_ref"]);
        in.contract_path = nb::cast<std::string>(raw["contract_path"]);
        in.contract_source = nb::cast<std::string>(raw["contract_source"]);
        in.som_source = nb::cast<std::string>(raw["som_source"]);
        using Port = std::tuple<std::string, std::string, std::string,
                               std::optional<std::string>, std::optional<int>, int>;
        for (const auto& p : nb::cast<std::vector<Port>>(raw["ports"]))
            in.ports.push_back({std::get<0>(p), std::get<1>(p), std::get<2>(p),
                               std::get<3>(p), std::get<4>(p), std::get<5>(p)});
        XdcOutput result;
        try {
            nb::gil_scoped_release release;
            result = generate_xdc(in);
        } catch (const XdcError& e) { throw nb::value_error(e.what()); }
        nb::list entries;
        for (const auto& e : result.entries)
            entries.append(nb::make_tuple(e.net, e.jpin, e.ball, e.pin_name,
                                         e.bank, e.iostd, e.consumers, e.type.type_index));
        return nb::make_tuple(result.text, entries, result.checks);
    });
}
}  // namespace schgen
