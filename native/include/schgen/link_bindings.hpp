#pragma once

#include "schgen/json_bindings.hpp"
#include "schgen/link.hpp"
#include <nanobind/stl/map.h>
#include <nanobind/stl/set.h>
#include <nanobind/stl/tuple.h>
#include <nanobind/stl/vector.h>

namespace schgen {
inline CircuitPortIr link_port_from_python(const nanobind::dict& value, const std::string& net) {
    namespace nb = nanobind;
    CircuitPortIr out;
    out.net = net;
    out.kind = nb::cast<std::string>(value["kind"]);
    auto string = [&](const char* key, std::string& target, bool& present) {
        const auto raw = value[key];
        present = !raw.is_none();
        if (present) target = nb::cast<std::string>(raw);
    };
    string("pair_with", out.pair_with, out.has_pair_with);
    string("role", out.role, out.has_role);
    string("bus", out.bus, out.has_bus);
    string("expect", out.expect, out.has_expect);
    out.has_impedance = !value["impedance"].is_none();
    if (out.has_impedance) out.impedance = nb::cast<int32_t>(value["impedance"]);
    out.has_speed_hz = !value["speed_hz"].is_none();
    if (out.has_speed_hz) out.speed_hz = nb::cast<int32_t>(value["speed_hz"]);
    out.has_level_v = !value["level_v"].is_none();
    if (out.has_level_v) out.level_v = nb::cast<double>(value["level_v"]);
    return out;
}
inline void bind_link(nanobind::module_& m) {
    namespace nb = nanobind;
    m.def("link_drift_candidates", &link_drift_candidates);
    m.def("link_sheets", [](const nb::list& raw_sheets, const LinkSomNets& som,
                            const nb::dict& raw_mapping,
                            const std::vector<std::tuple<std::size_t, std::string,
                                std::vector<std::string>>>& pairs,
                            const std::vector<std::string>& missing_roles) {
        std::vector<CircuitSheetIr> sheets;
        for (auto value : raw_sheets) {
            const auto item = nb::cast<nb::tuple>(value);
            auto sheet = parse_circuit_ir(json_from_python(item[1]));
            sheet.name = nb::cast<std::string>(item[0]);
            sheets.push_back(std::move(sheet));
        }
        const auto mapping = link_mapping_from_json(json_from_python(raw_mapping));
        LinkDiagnosticOrder order;
        order.missing_i2c_roles = missing_roles;
        for (const auto& [index, name, members] : pairs) order.pairs.push_back({index, name, members});
        LinkResult result;
        { nb::gil_scoped_release release; result = link_sheets(sheets, som, mapping, order); }
        return json_to_python(link_result_json(result));
    });
    m.def("link_report", [](const nb::dict& raw, const nb::dict& mapping) {
        LinkResult result;
        result.mapping = link_mapping_from_json(json_from_python(mapping));
        for (const auto& name : nb::cast<std::vector<std::string>>(raw["sheets"])) {
            CircuitSheetIr sheet; sheet.name = name; result.sheets.push_back(std::move(sheet));
        }
        for (auto value : nb::cast<nb::list>(raw["bindings"])) {
            const auto item = nb::cast<nb::dict>(value);
            LinkPortBinding binding;
            binding.sheet = nb::cast<std::string>(item["sheet"]);
            binding.net = nb::cast<std::string>(item["net"]);
            binding.ptype = link_port_from_python(nb::cast<nb::dict>(item["ptype"]), binding.net);
            binding.targets = nb::cast<std::vector<std::string>>(item["targets"]);
            binding.status = nb::cast<std::string>(item["status"]);
            result.bindings.push_back(std::move(binding));
        }
        result.rail_bindings = nb::cast<std::vector<std::string>>(raw["rail_bindings"]);
        result.errors = nb::cast<std::vector<std::string>>(raw["errors"]);
        result.warnings = nb::cast<std::vector<std::string>>(raw["warnings"]);
        result.unbound_som = nb::cast<std::vector<std::string>>(raw["unbound_som"]);
        result.deferred = nb::cast<std::vector<std::string>>(raw["deferred"]);
        nb::gil_scoped_release release;
        return result.report();
    });
}
}
