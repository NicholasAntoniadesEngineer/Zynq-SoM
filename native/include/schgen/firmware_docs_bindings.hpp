#pragma once
#include "schgen/firmware_docs.hpp"
#include "schgen/verification_bindings.hpp"

namespace schgen {
namespace firmware_binding {
namespace nb=nanobind;
inline CircuitSheetIr circuit(const nb::dict& raw){return decode_intermediate_circuit_ir(json_from_python(raw));}
inline Stm32PinMap stm32(const nb::dict& d) {
    using model_binding::get;Stm32PinMap r;r.value=get<std::string>(d,"value");
    for(const auto* kind:{"nets","internal"}) { for(auto [key,value]:get<nb::dict>(d,kind)) {
        const auto n=nb::cast<nb::dict>(value);Stm32Net net{get<std::string>(n,"net"),get<std::string>(n,"port"),
            get<int>(n,"pin"),get<std::vector<std::string>>(n,"j_pins")};
        (std::string(kind)=="nets"?r.nets:r.internal).emplace(nb::cast<std::string>(key),std::move(net));
    }}
    return r;
}
inline FirmwareDocsInput input(const nb::list& sheets,const nb::dict& pins,const std::vector<std::string>& sources){
    return {model_binding::sheets(sheets),stm32(pins),sources};
}
inline nb::dict sequence(const PowerSequence& seq) {
    nb::dict out;out["stage0"]=nb::cast(seq.stage0);
    for(const auto* key:{"chain","modules"}) {nb::list rows;
        for(const auto& r:std::string(key)=="chain"?seq.chain:seq.modules){nb::dict d;
            d["vout"]=nb::cast(r.vout);d["vin"]=nb::cast(r.vin);d["v"]=nb::cast(r.volts);
            d["load"]=nb::cast(r.load);d["limit"]=nb::cast(r.limit);d["kind"]=nb::cast(r.kind);
            d["ref"]=nb::cast(r.ref);d["sheet"]=nb::cast(r.sheet);d["en"]=nb::cast(r.enable);rows.append(d);}
        out[key]=rows;
    }return out;
}
inline PowerSequence sequence(const nb::dict& d) {
    using model_binding::get;PowerSequence r;r.stage0=get<std::vector<std::string>>(d,"stage0");
    for(const auto* key:{"chain","modules"}) { for(auto row:get<nb::list>(d,key)) {
        const auto v=nb::cast<nb::dict>(row);
        (std::string(key)=="chain"?r.chain:r.modules).push_back({get<std::string>(v,"vout"),get<std::string>(v,"vin"),
            get<std::optional<double>>(v,"v"),get<double>(v,"load"),get<double>(v,"limit"),get<std::string>(v,"kind"),
            get<std::string>(v,"ref"),get<std::string>(v,"sheet"),get<std::optional<std::string>>(v,"en")});
    }}
    return r;
}
}
inline void bind_firmware_docs(nanobind::module_& m) {
    namespace nb=nanobind;using namespace firmware_binding;
    nb::exception<FirmwareDocsError>(m,"FirmwareDocsError",PyExc_ValueError);
    m.def("bringup_parse_value_ohms",&bringup_parse_value_ohms);
    m.def("bringup_c_ident",&bringup_c_ident);
    m.def("bringup_dip_refs",[](const nb::dict& c){return dip_switch_refs(circuit(c));});
    m.def("bringup_dip_positions",[](const nb::dict& c,const std::string& ref,const std::vector<std::string>& common){
        nb::list r;for(const auto& row:dip_positions(circuit(c),ref,common))r.append(nb::make_tuple(row.switch_ref,row.position,row.net));return r;
    });
    m.def("bringup_en_cells",[](const nb::dict& c){
        nb::list r;for(const auto& row:en_cells(circuit(c)))r.append(nb::make_tuple(row.sheet,row.gate,row.dip_net,row.override_net,row.enable));return r;
    });
    m.def("bringup_expander",[](const nb::dict& c){
        const auto r=bringup_expander(circuit(c));nb::dict ports;
        for(const auto& [key,value]:r.ports)ports[nb::cast(key)]=nb::cast(value);return nb::make_tuple(r.ref,r.addr,ports);
    });
    m.def("bringup_monitors",[](const nb::dict& c){
        nb::list r;for(const auto& row:ina3221_monitors(circuit(c)))r.append(nb::make_tuple(row.ref,row.addr,row.channels));return r;
    });
    m.def("bringup_regulator_chain",[](const nb::dict& c,const std::string& root,const nb::object& monitor){
        const auto power=circuit(c);std::optional<CircuitSheetIr> mon;
        if(!monitor.is_none())mon=circuit(nb::cast<nb::dict>(monitor));nb::list r;
        for(const auto& row:regulator_chain(power,root,mon?&*mon:nullptr))r.append(nb::make_tuple(row.ref,row.value,row.enable,row.rail_in,row.rail_out,row.vout,row.pg_led));return r;
    },nb::arg("power"),nb::arg("root"),nb::arg("monitor").none());
    m.def("bringup_module_gates",[](const nb::dict& c){
        nb::list r;for(const auto& row:module_gates(circuit(c)))r.append(nb::make_tuple(row.ref,row.module,row.rail_in,row.rail_out,row.enable,row.ilim_ma,row.status_led));return r;
    });
    m.def("bringup_shunt_mohm",[](const nb::dict& c,const std::string& a,const std::string& b){return bringup_shunt_mohm(circuit(c),a,b);});
    m.def("bringup_id_eeprom_addr",[](const nb::dict& c){return bringup_id_eeprom_addr(circuit(c));});
    m.def("bringup_stm32_map",[](const nb::dict& raw,const std::map<std::string,std::vector<std::string>>& nets){
        using model_binding::get;SomZynq live;live.value=get<std::string>(raw,"value");
        for(auto [key,value]:get<nb::dict>(raw,"ball_net"))live.ball_net.emplace_back(nb::cast<std::string>(key),nb::cast<std::string>(value));
        for(auto [key,value]:get<nb::dict>(raw,"pin_names"))live.pin_names.emplace_back(nb::cast<std::string>(key),nb::cast<std::string>(value));
        SomInterface contract;std::map<std::string,SomConnector> connectors;
        for(const auto& [net,pins]:nets)for(const auto& pin:pins){const auto pos=pin.find('.');
            if(pos==std::string::npos)throw nb::value_error("invalid connector.pin in STM32 contract");
            connectors[pin.substr(0,pos)].pins.emplace_back(pin.substr(pos+1),net);}
        for(auto& item:connectors)contract.connectors.push_back(std::move(item));
        const auto map=stm32_pin_map(live,contract);nb::dict out;out["value"]=nb::cast(map.value);
        for(const auto* key:{"nets","internal"}){nb::dict rows;
            for(const auto& [name,n]:std::string(key)=="nets"?map.nets:map.internal)rows[nb::cast(name)]=nb::make_tuple(n.net,n.port,n.pin,n.j_pins);
            out[key]=rows;}return out;
    });
    m.def("firmware_sources",[](const std::string& repo,const std::string& project){return firmware_sources(resolve_project_paths(repo,project));});
    m.def("testplan_i2c_devices",[](const nb::list& sheets){
        nb::list out;
        for(const auto& row:testplan_i2c_devices(model_binding::sheets(sheets)))
            out.append(nb::cast(row));
        return out;
    });
    m.def("firmware_docs_missing",[](const nb::list& sheets,const std::string& kind){
        FirmwareDocsInput in;in.sheets=model_binding::sheets(sheets);
        if(kind=="firmware")return firmware_absent_inputs(in);
        if(kind=="manual")return manual_missing_requirements(in);
        if(kind=="scfw")return scfw_missing_requirements(in);throw nb::value_error("unknown document kind");
    });
    m.def("firmware_docs_render",[](const nb::list& sheets,const nb::dict& pins,const std::vector<std::string>& sources,const std::string& kind){
        const auto in=input(sheets,pins,sources);nb::gil_scoped_release release;
        if(kind=="firmware")return render_firmware_contract(in);
        if(kind=="manual")return render_bringup_manual(in);throw std::invalid_argument("unknown document kind");
    });
    m.def("firmware_scfw_render",[](const nb::list& sheets,const nb::dict& pins,const std::vector<std::string>& sources){
        const auto in=input(sheets,pins,sources);std::vector<FirmwareDocArtifact> result;
        {nb::gil_scoped_release release;result=render_scfw(in);}nb::dict out;
        for(const auto& row:result)out[nb::cast(row.path)]=nb::cast(row.text);return out;
    });
    m.def("firmware_testplan_render",[](const nb::list& sheets,const nb::dict& pins,const std::vector<std::string>& sources,const nb::dict& checks,const std::map<std::string,std::string>& probes){
        const auto in=input(sheets,pins,sources);const auto sp=verification_binding::spice_result(checks);ProjectStrings ps;
        for(const auto& p:probes)ps.push_back(p);nb::gil_scoped_release release;return render_test_plan(in,sp,ps);
    });
    m.def("power_sequence_build",[](const nb::list& sheets,const nb::dict& power,const nb::dict& policy){
        const auto s=model_binding::sheets(sheets);const auto p=power_result_from_json(json_from_python(power));
        const auto pol=model_binding::power_policy(policy);PowerSequence r;
        {nb::gil_scoped_release release;r=build_power_sequence(s,p,pol);}return sequence(r);
    });
    m.def("power_sequence_svg",[](const nb::dict& raw,bool ok,const nb::dict& policy){
        const auto s=sequence(raw);const auto pol=model_binding::power_policy(policy);
        nb::gil_scoped_release release;return render_power_sequence_svg(s,ok,pol);
    });
}
}
