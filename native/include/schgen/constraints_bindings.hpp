#pragma once
#include "schgen/constraints.hpp"
#include "schgen/json_bindings.hpp"
#include <nanobind/stl/tuple.h>

namespace schgen {
inline void bind_layout_constraints(nanobind::module_& m) {
    namespace nb = nanobind;
    m.def("layout_constraints", [](const nb::list& rows, const nb::dict& raw_specs, const std::string& source) {
        std::vector<ProjectCircuit> sheets;
        for (auto item : rows) {
            const auto row = nb::cast<nb::dict>(item);
            sheets.push_back({nb::cast<std::string>(row["name"]),{},
                decode_intermediate_circuit_ir(json_from_python(row["circuit"]))});
        }
        const auto specs = parse_signal_specs(json_from_python(raw_specs));
        LayoutConstraints result;
        { nb::gil_scoped_release release; result = generate_layout_constraints(sheets,specs,source); }
        return nb::make_tuple(result.dru,result.csv);
    });
}
}
