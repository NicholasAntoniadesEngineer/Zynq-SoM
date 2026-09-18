#pragma once

// Transitional transport only; the complete gate lives in validation.cpp.
#include "schgen/validation.hpp"
#include <nanobind/nanobind.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/tuple.h>
#include <nanobind/stl/vector.h>

namespace schgen {
inline void bind_validation(nanobind::module_& m) {
    namespace nb = nanobind;
    using BoxRow = std::tuple<double, double, double, double, std::string, std::string>;
    using WireRow = std::tuple<double, double, double, double, std::string>;
    m.def("check_visual_geometry", [](const std::vector<BoxRow>& boxes,
            const std::vector<WireRow>& wires,
            const std::vector<std::pair<double, double>>& junctions, double clearance) {
        SheetGeometry geometry;
        for (const auto& [x0, y0, x1, y1, kind, owner] : boxes)
            geometry.boxes.push_back({x0, y0, x1, y1, kind, owner});
        for (const auto& [x0, y0, x1, y1, net] : wires)
            geometry.wires.push_back({x0, y0, x1, y1, net});
        for (const auto& [x, y] : junctions) geometry.junctions.push_back({x, y});
        VisualResult result;
        {
            nb::gil_scoped_release release;
            result = check_visual_geometry(geometry, clearance);
        }
        return nb::make_tuple(result.ok, result.findings);
    });
}
}
