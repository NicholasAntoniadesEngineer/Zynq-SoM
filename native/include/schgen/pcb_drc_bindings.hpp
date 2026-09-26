#pragma once
#include "schgen/pcb_drc.hpp"
#include <nanobind/nanobind.h>
#include <nanobind/stl/map.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>

namespace schgen {
inline void bind_pcb_drc(nanobind::module_& m) {
    m.def("pcb_drc", [](const std::string& path, bool include_warnings) {
        PcbDrcResult result;
        { nanobind::gil_scoped_release release; result = run_pcb_drc(path, std::chrono::minutes{5}, include_warnings); }
        nanobind::dict out;
        out["returncode"] = result.returncode;
        out["n_violations"] = result.n_violations;
        out["n_errors"] = nanobind::cast(result.n_errors);
        out["n_unconnected"] = result.n_unconnected;
        out["by_type"] = nanobind::cast(result.by_type);
        out["other_sample"] = nanobind::cast(result.other_sample);
        out["stderr"] = nanobind::cast(result.stderr_tail);
        return out;
    }, nanobind::arg("path"), nanobind::arg("include_warnings") = true);
}
}
