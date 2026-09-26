#pragma once
#include "schgen/copper_debt.hpp"
#include "schgen/pcb_emit_bindings.hpp"
#include <nanobind/stl/set.h>

namespace schgen {
namespace authoring_audit_binding {
inline std::vector<ComponentBasisInput> inputs(const nanobind::iterable& rows) {
    namespace nb=nanobind;
    std::vector<ComponentBasisInput> out;
    for(auto item:rows) {
        const auto row=nb::cast<nb::dict>(item);
        out.push_back({nb::cast<std::string>(row["scope"]),nb::cast<std::string>(row["sheet"]),
            parse_circuit_ir(json_from_python(row["circuit"]))});
    }
    return out;
}
}
// Temporary data-only boundary. Does not execute Python constructors or use
// source anchors. Native callers use component_basis.hpp / copper_debt.hpp.
inline void bind_authoring_audits(nanobind::module_& m) {
    namespace nb=nanobind;
    using namespace authoring_audit_binding;
    nb::exception<CopperProvenanceError>(m,"CopperProvenanceError",PyExc_RuntimeError);
    m.def("component_basis_policy",[] { return json_to_python(component_basis_policy_json(default_component_basis_policy())); });
    m.def("component_basis_inputs",[](const std::string& repository) {
        nb::list out;
        for(const auto& x:author_component_basis_inputs(repository)) {
            nb::dict row;row["scope"]=x.scope;row["sheet"]=x.sheet;
            row["circuit"]=json_to_python(authored_circuit_json(x.circuit));out.append(row);
        }
        return out;
    });
    m.def("component_basis_audit",[](const nb::iterable& rows,const std::set<std::string>& scopes,
        const nb::object& declarations,const nb::object& constants) {
        auto p=default_component_basis_policy();
        std::vector<std::string> extra;
        // When the compatibility registry is supplied, replace its namespace:
        // removals/new declarations and value/rationale/class edits are audited.
        if(!declarations.is_none()) {
            p.declarations.erase(std::remove_if(p.declarations.begin(),p.declarations.end(),
                [](const auto& d){return d.name.rfind("subsystems.",0)==0;}),p.declarations.end());
            for(auto [key,value]:nb::cast<nb::dict>(declarations)) {
                const auto name=nb::cast<std::string>(key);
                const auto d=nb::cast<nb::dict>(value);
                const auto val=nb::cast<std::string>(d["value"]);
                p.declarations.push_back({"subsystems."+name,val,nb::cast<std::string>(d["unit"]),
                    nb::cast<std::string>(d["basis"]),nb::cast<std::string>(d["klass"]),false,
                    "subsystems/basis.py"});
                if(!constants.is_none()) {
                    const auto c=nb::cast<nb::dict>(constants);
                    if(!c.contains(key) || c[key].is_none() || nb::cast<std::string>(c[key])!=val)
                        extra.push_back(name+": public constant differs from registered value");
                }
            }
        }
        auto result=audit_component_basis(inputs(rows),scopes,p);
        result.broken.insert(result.broken.end(),extra.begin(),extra.end());
        return json_to_python(component_basis_result_json(result));
    },nb::arg("circuits"),nb::arg("scopes")=std::set<std::string>{"library","carrier","devkit_mini"},
      nb::arg("declarations").none()=nb::none(),nb::arg("constants").none()=nb::none());
    m.def("copper_debt_scan",[](const std::string& path) {
        return json_to_python(thermal_copper_json(scan_thermal_copper(std::filesystem::path(path))));
    });
    m.def("copper_debt_analyze",[](const nb::object& raw_copper,const nb::iterable& rows,
        const nb::dict& thermal,const nb::dict& emission,const nb::iterable& geometries) {
        CopperDebtSources sources;sources.circuits=inputs(rows);
        sources.thermal=model_binding::thermal_policy(thermal);
        sources.emission=pcb_emission_policy(emission);
        for(auto item:geometries) {
            const auto g=nb::cast<nb::dict>(item);
            sources.geometry.push_back({nb::cast<int>(g["impedance"]),nb::cast<double>(g["width_mm"]),
                nb::cast<double>(g["gap_mm"]),nb::cast<std::string>(g["source"])});
        }
        std::optional<ThermalCopper> copper;
        if(!raw_copper.is_none())copper=thermal_copper_from_json(json_from_python(raw_copper));
        return json_to_python(copper_debt_result_json(analyze_copper_debt(copper?&*copper:nullptr,sources)));
    },nb::arg("copper").none(),nb::arg("circuits"),nb::arg("thermal"),nb::arg("emission"),nb::arg("geometry"));
    m.def("copper_debt_report",[](const nb::dict& raw) {
        return copper_debt_report(copper_debt_result_from_json(json_from_python(raw)));
    });
}
} // namespace schgen
