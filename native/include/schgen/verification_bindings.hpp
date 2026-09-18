#pragma once
#include "schgen/model_checks_bindings.hpp"
#include "schgen/bom_values.hpp"
#include "schgen/footprint_pads.hpp"
#include "schgen/pin_completeness.hpp"
#include "schgen/symbol_law.hpp"
#include "schgen/spice.hpp"
#include <nanobind/stl/set.h>

namespace schgen {
namespace verification_binding {
namespace nb = nanobind;
template<class T> T attr(const nb::object& s,const char* key) {return nb::cast<T>(s.attr(key));}
inline SpiceCheck spice_check(const nb::dict& d) {
    using model_binding::get;
    return {get<std::string>(d,"name"),get<std::string>(d,"sheet"),get<std::string>(d,"kind"),
        get<std::string>(d,"detail"),get<double>(d,"value"),get<std::string>(d,"unit"),
        get<std::optional<double>>(d,"lo"),get<std::optional<double>>(d,"hi"),
        get<std::string>(d,"engine"),get<std::optional<double>>(d,"spice_value")};
}
inline SpiceResult spice_result(const nb::dict& d) {
    SpiceResult r;r.notes=model_binding::get<std::vector<std::string>>(d,"notes");
    r.engine=model_binding::get<std::string>(d,"engine");
    for(auto row:model_binding::get<nb::list>(d,"checks")) r.checks.push_back(spice_check(nb::cast<nb::dict>(row)));
    return r;
}
inline FootprintResolutionOptions options(const nb::dict& d) {
    using model_binding::get;
    FootprintResolutionOptions r;r.parts_dir=get<std::string>(d,"parts_dir");
    r.kicad_footprint_root=get<std::string>(d,"root");
    for(const auto& path:get<std::vector<std::string>>(d,"tables"))r.library_tables.emplace_back(path);
    r.aliases=get<std::map<std::string,std::string>>(d,"aliases");return r;
}
}
template<class FromPython>
void bind_verification(nanobind::module_& m, FromPython from_python) {
    namespace nb=nanobind;using namespace verification_binding;
    m.def("bom_value_normalize",[](const std::string& value,const std::optional<std::string>& hint)->nb::object {
        auto r=normalize_bom_value(value,hint);if(!r)return nb::none();
        return nb::make_tuple(r->component_class,r->magnitude);
    },nb::arg("value"),nb::arg("hint").none());
    m.def("bom_value_equal",[](const std::pair<std::string,double>& a,const std::pair<std::string,double>& b){
        return equal_bom_values({a.first,a.second},{b.first,b.second});
    });
    m.def("bom_value_check",[](const nb::list& input,const nb::dict& cat){
        const auto s=model_binding::sheets(input);const auto c=bom_value_catalog_from_json(json_from_python(cat));
        BomValueResult r;{nb::gil_scoped_release release;r=check_bom_values(s,c);}return json_to_python(bom_value_result_json(r));
    });
    m.def("bom_value_report",[](const nb::object& s){
        BomValueResult r;r.ok=attr<bool>(s,"ok");r.checked=attr<std::size_t>(s,"checked");r.catalog_size=attr<std::size_t>(s,"catalog_size");
        r.mismatches=attr<std::vector<std::string>>(s,"mismatches");r.unverified=attr<std::vector<std::string>>(s,"unverified");return r.report();
    });
    m.def("footprint_pad_numbers",&footprint_pad_numbers);
    m.def("footprint_library_tables",[](const nb::dict& raw){
        const auto opt=options(raw);std::map<std::string,std::string> r;
        for(const auto& [key,path]:load_footprint_library_tables(opt))r.emplace(key,path.string());return r;
    });
    m.def("footprint_resolve",[](const std::string& fp,const std::map<std::string,std::string>& paths,const nb::dict& raw)->std::optional<std::string>{
        FootprintPaths libs;for(const auto& [key,path]:paths)libs.emplace(key,path);
        const auto found=resolve_footprint(fp,libs,options(raw));return found?std::optional<std::string>(found->string()):std::nullopt;
    });
    m.def("footprint_pad_check",[](const nb::list& input,const nb::object& pin_numbers,const nb::dict& raw){
        const auto s=model_binding::sheets(input);const auto opt=options(raw);const auto paths=load_footprint_library_tables(opt);
        const auto r=check_footprint_pads(s,[&](const auto& id){return nb::cast<std::set<std::string>>(pin_numbers(id));},
            [&](const auto& id)->std::optional<std::set<std::string>>{
                const auto path=resolve_footprint(id,paths,opt);return path?std::optional<std::set<std::string>>(read_footprint_pad_numbers(*path)):std::nullopt;
            });return json_to_python(footprint_pads_result_json(r));
    });
    m.def("footprint_pad_report",[](const nb::object& s){
        FootprintPadsResult r;r.ok=attr<bool>(s,"ok");r.checked=attr<std::size_t>(s,"checked");
        r.violations=attr<std::vector<std::string>>(s,"violations");r.unresolved=attr<std::vector<std::string>>(s,"unresolved");return r.report();
    });
    m.def("pin_completeness_check",[](const nb::list& input,const nb::object& get_symbol,const nb::dict& allow){
        const auto s=model_binding::sheets(input);const auto a=nc_allowlist_from_json(json_from_python(allow));
        std::map<std::string,SymbolDef> symbols;
        const auto r=check_pin_completeness(s,[&](const auto& id)->const SymbolDef&{
            auto found=symbols.find(id);if(found!=symbols.end())return found->second;
            const auto source=get_symbol(id);SymbolDef def;def.lib_id=id;
            for(auto raw:nb::cast<nb::iterable>(source.attr("pins"))){SymbolPin pin;
                pin.number=nb::cast<std::string>(raw.attr("number"));pin.name=nb::cast<std::string>(raw.attr("name"));def.pins.push_back(std::move(pin));}
            return symbols.emplace(id,std::move(def)).first->second;
        },a);return json_to_python(pin_completeness_result_json(r));
    });
    m.def("pin_completeness_report",[](const nb::object& s){
        PinCompletenessResult r;r.ok=attr<bool>(s,"ok");r.parts_checked=attr<std::size_t>(s,"parts_checked");r.nc_total=attr<std::size_t>(s,"nc_total");
        r.floats=attr<std::vector<std::string>>(s,"floats");r.nc_seeded=attr<std::vector<std::string>>(s,"nc_seeded");r.nc_new=attr<std::vector<std::string>>(s,"nc_new");return r.report();
    });
    m.def("symbol_power_flag",[from_python](const nb::object& raw){
        SymbolDef def;def.raw=from_python(raw);return symbol_is_power_flag([&](const auto&)->const SymbolDef&{return def;},"");
    });
    m.def("symbol_law_check",[from_python](const nb::list& input,const nb::object& get_raw,const std::map<std::string,std::string>& pending){
        std::vector<CircuitSheetIr> cs;for(const auto& s:model_binding::sheets(input))cs.push_back(s.circuit);
        std::map<std::string,SymbolDef> symbols;
        const auto r=check_symbol_law(cs,[&](const auto& id)->const SymbolDef&{
            auto found=symbols.find(id);if(found!=symbols.end())return found->second;
            const auto raw=get_raw(id);if(raw.is_none())throw SymbolError("unresolved symbol: "+id);
            SymbolDef def;def.lib_id=id;def.raw=from_python(raw);return symbols.emplace(id,std::move(def)).first->second;
        },pending);return json_to_python(symbol_law_result_json(r));
    });
    m.def("symbol_law_summary",[](const nb::object& s){
        return SymbolLawResult{attr<std::vector<std::string>>(s,"violations"),attr<std::vector<std::string>>(s,"pending")}.summary();
    });
    m.def("spice_check_ok",[](const nb::dict& d){return spice_check(d).ok();});
    m.def("spice_errors",[](const nb::dict& d){return spice_result(d).errors();});
    m.def("spice_extract",[](const nb::list& raw,const nb::dict& policy){
        const auto s=model_binding::sheets(raw);const auto p=model_binding::power_policy(policy);SpiceResult r;
        {nb::gil_scoped_release release;r=extract_spice_checks(s,p);}return json_to_python(spice_result_json(r));
    });
    m.def("ngspice_available",[]()->std::optional<std::string>{const auto p=ngspice_available();return p?std::optional<std::string>(p->string()):std::nullopt;});
    m.def("spice_crosscheck",[](const nb::dict& d,const std::string& executable){
        auto r=spice_result(d);SpiceRunOptions options;options.executable=executable;
        {nb::gil_scoped_release release;run_ngspice_crosschecks(r,options);}return json_to_python(spice_result_json(r));
    });
    m.def("spice_report",[](const nb::dict& d,bool available){return spice_report(spice_result(d),available);});
}
}
