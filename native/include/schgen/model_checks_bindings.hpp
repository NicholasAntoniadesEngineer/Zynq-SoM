#pragma once
#include "schgen/part_checks.hpp"
#include "schgen/json_bindings.hpp"
#include <nanobind/stl/optional.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/vector.h>

namespace schgen {
namespace model_binding {
namespace nb = nanobind;
template<class T> T get(const nb::dict& d,const char* key) { return nb::cast<T>(d[key]); }
inline std::vector<ProjectCircuit> sheets(const nb::list& rows) {
    std::vector<ProjectCircuit> out;
    for (auto row : rows) {
        const auto d = nb::cast<nb::dict>(row);
        out.push_back({get<std::string>(d,"name"),{},decode_intermediate_circuit_ir(json_from_python(d["circuit"]))});
    }
    return out;
}
inline PowerPolicy power_policy(const nb::dict& d) {
    PowerPolicy p;
    p.voltage_patterns = get<std::vector<std::pair<std::string,double>>>(d,"voltage_patterns");
    for (auto [key,value] : get<nb::dict>(d,"regulators")) {
        const auto s = nb::cast<nb::dict>(value);
        p.regulators.emplace_back(nb::cast<std::string>(key),PowerRegSpec{
            get<std::string>(s,"kind"),get<std::optional<double>>(s,"limit_a"),get<double>(s,"eff"),
            get<std::string>(s,"in_pin"),get<std::string>(s,"out_pin"),get<std::string>(s,"iset_pin"),
            get<double>(s,"ilim_num"),get<std::string>(s,"note")});
    }
    for (auto [key,value] : get<nb::dict>(d,"sources")) {
        const auto s = nb::cast<nb::tuple>(value);
        p.sources.emplace_back(nb::cast<std::string>(key),PowerSource{
            nb::cast<double>(s[0]),nb::cast<double>(s[1]),nb::cast<std::string>(s[2])});
    }
    for (auto [key,value] : get<nb::dict>(d,"known_deferred"))
        p.known_deferred.emplace_back(nb::cast<std::string>(key),nb::cast<std::string>(value));
    return p;
}
inline ThermalSpec thermal_spec(const nb::dict& s) {
    ThermalSpec t;
    t.rth_ja=get<double>(s,"rth_ja");t.tj_max=get<double>(s,"tj_max");
    t.rds_on=get<double>(s,"rds_on");t.eff=get<double>(s,"eff");
    t.package=get<std::string>(s,"package");t.cite=get<std::string>(s,"cite");
    t.rth_ja_pour=get<std::optional<double>>(s,"rth_ja_pour");
    t.pour_cite=get<std::string>(s,"pour_cite");t.pour_evidence=get<std::string>(s,"pour_evidence");return t;
}
inline ThermalPolicy thermal_policy(const nb::dict& s) {
    ThermalPolicy p;p.ambient_c=get<double>(s,"ambient_c");p.margin_c=get<double>(s,"margin_c");
    for (auto [key,value] : get<nb::dict>(s,"specs")) p.specs.emplace_back(nb::cast<std::string>(key),thermal_spec(nb::cast<nb::dict>(value)));
    for (auto row : get<nb::list>(s,"footprint_specs")) {
        const auto v=nb::cast<nb::tuple>(row);
        p.footprint_specs.push_back({nb::cast<std::string>(v[0]),nb::cast<std::string>(v[1]),thermal_spec(nb::cast<nb::dict>(v[2]))});
    }
    for (auto [key,value] : get<nb::dict>(s,"pour_needs")) {
        const auto v=nb::cast<nb::dict>(value);
        p.pour_needs.emplace_back(nb::cast<std::string>(key),ThermalPourNeed{get<std::string>(v,"value_prefix"),
            get<int>(v,"min_vias"),get<double>(v,"radius_mm"),get<std::vector<std::string>>(v,"pour_layers")});
    }
    return p;
}
inline PartRatingsTable ratings(const nb::dict& raw) {
    PartRatingsTable result;
    for (auto [key,value] : raw) {
        const auto rating=part_ratings_from_json(json_from_python(value));
        if (!rating) throw nb::value_error("part rating must have a nonempty kind");
        result.emplace_back(nb::cast<std::string>(key),*rating);
    }
    return result;
}
}
inline void bind_model_checks(nanobind::module_& m) {
    namespace nb = nanobind;
    using namespace model_binding;
    nb::exception<ModelCheckError>(m,"ModelCheckError",PyExc_ValueError);
    m.def("parse_si_value",&parse_si_value,nb::call_guard<nb::gil_scoped_release>());
    m.def("parse_resistor_ohms",&parse_resistor_ohms,nb::call_guard<nb::gil_scoped_release>());
    m.def("power_rail_volts",[](const std::string& name,const std::vector<std::pair<std::string,double>>& patterns) {
        PowerPolicy policy;policy.voltage_patterns=patterns;
        nb::gil_scoped_release release;return rail_volts(name,policy);
    });
    m.def("power_detect",[](const nb::list& raw,const nb::dict& pol) {
        const auto input=sheets(raw);const auto policy=power_policy(pol);PowerCheckResult r;
        {nb::gil_scoped_release release;r=detect_power_regulators(input,policy);}
        return json_to_python(power_result_json(r));
    });
    m.def("power_analyze",[](const nb::list& raw,const nb::dict& pol) {
        const auto input=sheets(raw);const auto policy=power_policy(pol);PowerCheckResult r;
        {nb::gil_scoped_release release;r=analyze_power(input,policy);}
        return json_to_python(power_result_json(r));
    });
    m.def("power_render",[](const nb::dict& raw,const nb::dict& pol,bool svg) {
        const auto r=power_result_from_json(json_from_python(raw));const auto policy=power_policy(pol);
        nb::gil_scoped_release release;return svg?power_svg(r,policy):power_report(r,policy);
    });
    m.def("power_run",[](const nb::list& raw,const nb::dict& pol,
            const std::string& reports,const std::string& docs) {
        const auto input=sheets(raw);const auto policy=power_policy(pol);PowerCheckResult r;
        {nb::gil_scoped_release release;r=run_power_checks(input,reports,docs,policy);}
        return json_to_python(power_result_json(r));
    });
    m.def("thermal_analyze",[](const nb::list& raw,const nb::dict& pt,const nb::object& copper,
            const std::string& source,const nb::dict& thermal,const nb::dict& power) {
        const auto input=sheets(raw);const auto pr=power_result_from_json(json_from_python(pt));
        const auto policy=thermal_policy(thermal);const auto pp=power_policy(power);
        std::optional<ThermalCopper> scan;
        if (!copper.is_none()) scan=thermal_copper_from_json(json_from_python(copper));
        ThermalCheckResult result;
        {nb::gil_scoped_release release;result=analyze_thermal(input,pr,scan?&*scan:nullptr,source,policy,pp);}
        return json_to_python(thermal_result_json(result));
    },nb::arg("sheets"),nb::arg("power_result"),nb::arg("copper").none(),
       nb::arg("source"),nb::arg("thermal_policy"),nb::arg("power_policy"));
    m.def("thermal_report",[](const nb::dict& raw) {
        const auto r=thermal_result_from_json(json_from_python(raw));
        nb::gil_scoped_release release;return thermal_report(r);
    });
    m.def("thermal_run",[](const nb::list& raw,const nb::dict& pt,
            const std::string& pcb,const std::string& reports,const std::string& repository,
            const nb::dict& thermal,const nb::dict& power) {
        const auto input=sheets(raw);const auto pr=power_result_from_json(json_from_python(pt));
        const auto policy=thermal_policy(thermal);const auto pp=power_policy(power);
        ThermalCheckResult result;
        {
            nb::gil_scoped_release release;
            const auto path=pcb.empty()?std::nullopt:std::optional<std::filesystem::path>(pcb);
            result=run_thermal_checks(input,reports,&pr,path,repository,policy,pp);
        }
        return json_to_python(thermal_result_json(result));
    });
    m.def("thermal_dissipation",[](const std::string& kind,double vin,double vout,double current,const nb::dict& raw) {
        const auto spec=thermal_spec(raw);nb::gil_scoped_release release;
        return thermal_dissipation(kind,vin,vout,current,spec);
    });
    m.def("part_rules_analyze",[](const nb::list& raw,const nb::dict& pt,const nb::dict& table,
            const std::vector<double>& limits,const nb::dict& pol) {
        if(limits.size()!=4)throw nb::value_error("part policy needs four derating factors");
        const auto input=sheets(raw);const auto power=power_result_from_json(json_from_python(pt));
        const auto rs=ratings(table);const PartRulePolicy policy{limits[0],limits[1],limits[2],limits[3]};
        const auto pp=power_policy(pol);PartCheckResult result;
        {nb::gil_scoped_release release;result=analyze_part_rules(input,power,rs,policy,pp);}
        return json_to_python(part_result_json(result));
    });
    m.def("part_rules_report",[](const nb::dict& raw,const std::vector<double>& limits) {
        if(limits.size()!=4)throw nb::value_error("part policy needs four derating factors");
        const auto r=part_result_from_json(json_from_python(raw));
        const PartRulePolicy policy{limits[0],limits[1],limits[2],limits[3]};
        nb::gil_scoped_release release;return part_rules_report(r,policy);
    });
}
}
