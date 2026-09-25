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
    // Transport live connector inputs, including caller-edited pin/mapping and
    // policy dictionaries. Never reduce the Python generator API to a frozen
    // project/default connector lookup.
    m.def("author_som_connector",[](const std::string& project,const std::string& ref,
            const std::string& name,const std::string& title,const nb::dict& pins,
            const nb::dict& mapping,const nb::dict& overrides,const std::string& repository){
        SomInterface som;SomConnector connector;
        for(auto [pin,net]:pins)connector.pins.emplace_back(nb::cast<std::string>(pin),nb::cast<std::string>(net));
        som.connectors.emplace_back(ref,std::move(connector));
        auto policy=project_connector_policy(project);
        for(auto [key,value]:overrides) {
            const auto field=nb::cast<std::string>(key);
            if(field=="part")policy.part=nb::cast<std::string>(value);
            else if(field=="module_draw_a")policy.module_draw_a=nb::cast<double>(value);
            else if(field=="sdio_level_v")policy.sdio_level_v=nb::cast<double>(value);
            else if(field=="sd_bus")policy.sd_bus=nb::cast<std::vector<std::string>>(value);
            else if(field=="pairs") {
                policy.pairs.clear();
                for(auto row:nb::borrow<nb::iterable>(value)) {
                    nb::tuple item(nb::borrow<nb::object>(row));
                    if(item.size()!=4)throw nb::value_error("connector pairs must have four fields");
                    policy.pairs.push_back({nb::cast<std::string>(item[0]),nb::cast<std::string>(item[1]),
                        nb::cast<std::string>(item[2]),nb::cast<std::optional<int32_t>>(item[3])});
                }
            } else throw nb::value_error(("unknown connector policy field "+field).c_str());
        }
        return json_to_python(authored_circuit_json(author_som_connector(ref,name,title,som,
            link_mapping_from_json(json_from_python(mapping)),policy,make_authoring_context(repository))));
    },nb::arg("project"),nb::arg("ref"),nb::arg("name"),nb::arg("title"),nb::arg("pins"),
      nb::arg("mapping"),nb::arg("policy"),nb::arg("repository"));
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
