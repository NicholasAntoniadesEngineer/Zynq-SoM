#pragma once

#include "schgen/som_interface.hpp"
#include <nanobind/nanobind.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>

namespace schgen {
inline void bind_som_interface(nanobind::module_& m) {
    namespace nb = nanobind;
    auto dictionary = [](const XdcStrings& values) {
        nb::dict out;
        for (const auto& [key, value] : values) out[nb::str(key.c_str())] = nb::cast(value);
        return out;
    };
    m.def("som_extract", [dictionary](const std::string& path,
                                      const std::vector<std::string>& refs) {
        SomInterface data;
        { nb::gil_scoped_release release; data = extract_som_interface(path, refs); }
        nb::dict out, connectors;
        for (const auto& [ref, connector] : data.connectors) {
            nb::dict item;
            item["value"] = nb::cast(connector.value);
            item["footprint"] = nb::cast(connector.footprint);
            item["pins"] = dictionary(connector.pins);
            connectors[nb::str(ref.c_str())] = item;
        }
        out["source"] = nb::cast(data.source);
        out["connectors"] = connectors;
        return out;
    });
    m.def("som_extract_zynq", [dictionary](const std::string& path,
                    const std::string& ref, const std::vector<std::string>& jrefs) {
        SomZynq data;
        { nb::gil_scoped_release release; data = extract_som_zynq(path, ref, jrefs); }
        nb::dict out;
        out["zynq_ref"] = nb::cast(data.zynq_ref);
        out["source"] = nb::cast(data.source);
        out["value"] = nb::cast(data.value);
        out["pin_names"] = dictionary(data.pin_names);
        out["ball_net"] = dictionary(data.ball_net);
        out["jpin_net"] = dictionary(data.jpin_net);
        return out;
    });
    m.def("som_write_interface", [](const std::string& path, const std::string& refs,
                                     const std::string& output) {
        nb::gil_scoped_release release;
        return write_som_interface(path, refs, output);
    });
}
}
