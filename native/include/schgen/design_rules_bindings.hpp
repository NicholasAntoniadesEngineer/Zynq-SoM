#pragma once

#include "schgen/design_rules.hpp"
#include "schgen/json_bindings.hpp"
#include "schgen/netlist_gate_bindings.hpp"
#include <set>

namespace schgen {
namespace design_rule_binding_detail {
inline std::vector<CircuitSheetIr> sheets_from_python(const nanobind::iterable& input) {
    namespace nb = nanobind;
    std::vector<CircuitSheetIr> sheets;
    for (const auto source : input) {
        const auto c = nb::borrow<nb::object>(source.attr("circuit"));
        auto sheet = netlist_gate_binding_detail::circuit_from_python(c);
        sheet.name = nb::cast<std::string>(source.attr("name"));
        const auto parts = nb::cast<nb::dict>(c.attr("parts"));
        for (auto& part : sheet.parts)
            part.value = nb::cast<std::string>(parts[nb::cast(part.ref)].attr("value"));
        for (const auto [key, value] : nb::cast<nb::dict>(c.attr("port_types"))) {
            CircuitPortIr port;
            port.net = nb::cast<std::string>(key);
            port.kind = nb::cast<std::string>(value.attr("kind"));
            sheet.port_types.push_back(std::move(port));
        }
        for (const auto* kind : {"tp_waivers", "decap_waivers", "pull_waivers",
                                "reset_waivers", "strap_waivers", "ep_waivers"}) {
            if (!nb::hasattr(c, kind)) continue;
            const auto raw = c.attr(kind);
            if (!nb::isinstance<nb::dict>(raw)) continue;
            for (const auto [key, value] : nb::cast<nb::dict>(raw))
                sheet.waivers.push_back({kind, nb::cast<std::string>(key), nb::cast<std::string>(value)});
        }
        sheets.push_back(std::move(sheet));
    }
    return sheets;
}
}

inline void bind_design_rules(nanobind::module_& m) {
    namespace nb = nanobind;
    nb::exception<UnnettedTestpoint>(m, "UnnettedTestpoint", PyExc_StopIteration);
    m.def("design_rule_power_pin", &is_power_pin_name);
    m.def("design_rule_format", [](const nb::object& source) {
        DesignRuleResult r;
        r.decap = nb::cast<std::vector<std::string>>(source.attr("decap"));
        r.i2c = nb::cast<std::vector<std::string>>(source.attr("i2c"));
        r.reset = nb::cast<std::vector<std::string>>(source.attr("reset"));
        r.strap = nb::cast<std::vector<std::string>>(source.attr("strap"));
        r.ep = nb::cast<std::vector<std::string>>(source.attr("ep"));
        r.waived = nb::cast<std::vector<std::string>>(source.attr("waived"));
        for (const auto [key, value] : nb::cast<nb::dict>(source.attr("checked")))
            r.checked.emplace_back(nb::cast<std::string>(key), nb::cast<std::size_t>(value));
        return nb::make_tuple(r.summary(), r.report());
    });
    m.def("testpoint_coverage_report", [](const nb::object& source) {
        TestpointCoverage r;
        for (const auto [key, value] : nb::cast<nb::dict>(source.attr("required")))
            r.required.emplace_back(nb::cast<std::string>(key), nb::cast<std::string>(value));
        for (const auto [key, value] : nb::cast<nb::dict>(source.attr("have")))
            r.have.emplace_back(nb::cast<std::string>(key), nb::cast<std::vector<std::string>>(value));
        for (const auto [key, value] : nb::cast<nb::dict>(source.attr("waived")))
            r.waived.emplace_back(nb::cast<std::string>(key), nb::cast<std::pair<std::string, std::string>>(value));
        r.errors = nb::cast<std::vector<std::string>>(source.attr("errors"));
        return r.report();
    });
    m.def("design_rule_check", [](const nb::iterable& input, const nb::object& get_symbol) {
        const auto sheets = design_rule_binding_detail::sheets_from_python(input);
        std::vector<SymbolDef> symbols;
        std::set<std::string> seen;
        // Resolve under the GIL before entering the native failure-tolerant
        // resolver. Python cancellation/resource failures must never become
        // empty symbols (and Python exception destruction needs the GIL).
        for (const auto& sheet : sheets) for (const auto& part : sheet.parts) {
            const auto& id = part.lib_id;
            if (!seen.insert(id).second) continue;
            nb::object raw;
            try { raw = get_symbol(nb::cast(id)); }
            catch (nb::python_error& error) {
                if (!error.matches(PyExc_Exception) || error.matches(PyExc_MemoryError)
                    || error.matches(PyExc_OSError)) throw;
                continue;
            }
            SymbolDef symbol;
            symbol.lib_id = id;
            for (const auto p : nb::cast<nb::iterable>(raw.attr("pins"))) {
                SymbolPin pin;
                pin.number = nb::cast<std::string>(p.attr("number"));
                pin.name = nb::cast<std::string>(p.attr("name"));
                pin.etype = nb::cast<std::string>(p.attr("etype"));
                symbol.pins.push_back(std::move(pin));
            }
            symbols.push_back(std::move(symbol));
        }
        DesignRuleResult result;
        {
            nb::gil_scoped_release release;
            result = check_design_rules(sheets, symbols);
        }
        return json_to_python(design_rule_result_json(result));
    });
    m.def("testpoint_coverage", [](const nb::iterable& input) {
        const auto sheets = design_rule_binding_detail::sheets_from_python(input);
        TestpointCoverage result;
        {
            nb::gil_scoped_release release;
            result = check_testpoint_coverage(sheets);
        }
        return json_to_python(testpoint_coverage_json(result));
    });
}
}
