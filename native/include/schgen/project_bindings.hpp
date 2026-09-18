#pragma once

#include "schgen/bom.hpp"
#include "schgen/devicetree.hpp"
#include "schgen/json_bindings.hpp"
#include <nanobind/stl/tuple.h>
#include <nanobind/stl/vector.h>

namespace schgen {
inline void bind_project_outputs(nanobind::module_& m) {
    namespace nb = nanobind;
    m.def("generate_bom", [](const nb::list& raw, bool qualified) {
        std::vector<CircuitSheetIr> sheets;
        for (auto item : raw) sheets.push_back(parse_circuit_ir(json_from_python(item)));
        BomOutput result;
        { nb::gil_scoped_release release; result = generate_bom(sheets, qualified); }
        nb::list rows;
        for (const auto& row : result.rows)
            rows.append(nb::make_tuple(row.value, row.footprint, row.lcsc, row.refs));
        return nb::make_tuple(result.csv, rows, result.missing_lcsc, result.missing_footprints);
    });
    m.def("generate_devicetree", [](const std::string& repository, const std::string& project,
            const std::string& som, const std::string& contract,
            const std::vector<std::string>& refs) {
        try {
            DeviceTreeOutput result;
            {
                nb::gil_scoped_release release;
                const auto live = extract_som_zynq(som, "U2", refs);
                result = generate_devicetree(load_devicetree_input(repository, project, live, contract, refs));
            }
            return nb::make_tuple(result.text, result.mio_rows.size());
        } catch (const DeviceTreeError& error) { throw nb::value_error(error.what()); }
    });
}
}
