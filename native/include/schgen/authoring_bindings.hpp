#pragma once
#include "schgen/project_authoring.hpp"
#include "schgen/json_bindings.hpp"
#include <nanobind/stl/optional.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>

namespace schgen {
// Parent integration: include this header in module.cpp and call
// schgen::bind_authoring(m) once after common JSON/catalog registration.
// Catalog must already be opened via the existing catalog-open boundary.
// This adapter exposes author inputs; it never substitutes stored circuit IR.
inline void bind_authoring(nanobind::module_& m) {
    namespace nb=nanobind;
    nb::exception<CircuitAuthoringError>(m,"CircuitAuthoringError",PyExc_ValueError);
    m.def("author_subsystem_interface",[](const std::string& name){return subsystem_definition(name).interface;});
    m.def("author_subsystem",[](const std::string& name,const nb::object& meta,const std::string& repository){
        return json_to_python(authored_circuit_json(author_subsystem(name,SubsystemMeta(json_from_python(meta)),make_authoring_context(repository))));
    },nb::arg("name"),nb::arg("meta").none(),nb::arg("repository"));
    m.def("author_project_subsystem",[](const std::string& project,const std::string& name,
            const std::string& repository,const std::string& project_root,const nb::object& meta){
        ProjectAuthoringInput input;input.project_root=project_root;input.context=make_authoring_context(repository);
        if(!meta.is_none())input.metadata.emplace(name,json_from_python(meta));
        return json_to_python(authored_circuit_json(author_project_subsystem(project,name,input)));
    },nb::arg("project"),nb::arg("name"),nb::arg("repository"),nb::arg("project_root"),nb::arg("meta").none()=nb::none());
    m.def("authoring_subsystem_structure",[](const std::string& library,const std::string& repository){
        return json_to_python(subsystem_structure_json(check_subsystem_structure(library,native_subsystem_factories(make_authoring_context(repository)))));
    });
    m.def("authoring_carrier_structure",[](const std::string& base,const std::string& library,
            const std::string& project,const std::string& repository,const std::string& project_root){
        ProjectAuthoringInput input;input.project_root=project_root;input.context=make_authoring_context(repository);
        return json_to_python(carrier_structure_json(check_carrier_structure(base,library,native_project_factories(project,input))));
    });
    m.def("authoring_bind",[](const nb::dict& raw,const nb::dict& mapping){
        CircuitAuthor c(decode_intermediate_circuit_ir(json_from_python(raw)));AuthoringStrings names;
        for(auto [key,value]:mapping)names.emplace_back(nb::cast<std::string>(key),nb::cast<std::string>(value));
        c.bind(names);return json_to_python(authored_circuit_json(c.view()));
    });
    m.def("authoring_mounting_hole",[](const nb::dict& raw,const std::string& net,const std::optional<std::string>& ref){
        CircuitAuthor c(decode_intermediate_circuit_ir(json_from_python(raw)));c.mounting_hole(net,ref);
        return json_to_python(authored_circuit_json(c.view()));
    },nb::arg("circuit"),nb::arg("net")="CHASSIS_GND",nb::arg("ref").none()=nb::none());
}
} // namespace schgen
