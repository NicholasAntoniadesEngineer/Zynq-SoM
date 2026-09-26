#include "schgen/authoring.hpp"
#include "authoring_values.hpp"
#include <tuple>

namespace schgen {
JsonNode authored_circuit_json(const CircuitSheetIr& c) {
    using namespace authoring_values;
    auto parts=arr(),nets=arr(),nc=arr(),types=obj(),hints=obj(),loads=obj();
    for(const auto& p:c.parts) {
        auto fields=obj(),names=obj();
        for(const auto& f:p.fields)fields.object_value.emplace_back(f.key,j(f.value));
        for(const auto& n:p.pin_names)names.object_value.emplace_back(n.name,strings(n.numbers));
        auto numbers=p.pin_numbers;std::sort(numbers.begin(),numbers.end());
        parts.array_value.push_back(obj({{"ref",j(p.ref)},{"lib_id",j(p.lib_id)},{"value",j(p.value)},
            {"footprint",j(p.footprint)},{"fields",fields},{"pin_names",names},{"pin_numbers",strings(numbers)}}));
    }
    for(const auto& n:c.nets) {
        auto pins=arr();for(const auto& p:n.pins)pins.array_value.push_back(j(p.ref+"."+p.pin));
        nets.array_value.push_back(obj({{"name",j(n.name)},{"net_class",j(n.net_class)},{"pins",pins}}));
    }
    auto nc_pins=c.nc;
    std::sort(nc_pins.begin(),nc_pins.end(),[](const CircuitPinRefIr& a,const CircuitPinRefIr& b){return std::tie(a.ref,a.pin)<std::tie(b.ref,b.pin);});
    for(const auto& p:nc_pins)nc.array_value.push_back(j(p.ref+"."+p.pin));
    for(const auto& p:c.port_types)types.object_value.emplace_back(p.net,obj({
        {"kind",j(p.kind)},{"pair_with",p.has_pair_with?j(p.pair_with):JsonNode{}},
        {"impedance",p.has_impedance?j(double(p.impedance)):JsonNode{}},
        {"role",p.has_role?j(p.role):JsonNode{}},{"bus",p.has_bus?j(p.bus):JsonNode{}},
        {"speed_hz",p.has_speed_hz?j(double(p.speed_hz)):JsonNode{}},
        {"level_v",p.has_level_v?j(p.level_v):JsonNode{}},{"expect",p.has_expect?j(p.expect):JsonNode{}}}));
    for(const auto& h:c.hints)hints.object_value.emplace_back(h.net,j(h.style));
    for(const auto& l:c.loads) {
        auto a=find(loads.object_value,l.rail);
        if(!a){loads.object_value.emplace_back(l.rail,arr());a=&loads.object_value.back().second;}
        a->array_value.push_back(arr({j(l.amps),j(l.note)}));
    }
    auto out=obj({{"schema",j(c.schema)},{"name",j(c.name)},{"title",j(c.title)},
        {"parts",parts},{"nets",nets},{"nc",nc},{"port_types",types},{"hints",hints},{"loads",loads}});
    for(const auto* kind:{"tp_waivers","decap_waivers","pull_waivers","reset_waivers","strap_waivers","ep_waivers","thermal_waivers","part_rule_waivers"}) {
        auto entries=obj();for(const auto& w:c.waivers)if(w.kind==kind)entries.object_value.emplace_back(w.key,j(w.reason));
        out.object_value.emplace_back(kind,entries);
    }
    return out;
}
bool authoring_json_equal(const JsonNode& a,const JsonNode& b) {
    if(a.kind!=b.kind)return false;
    switch(a.kind) {
    case JsonKind::Null:return true;
    case JsonKind::Bool:return a.bool_value==b.bool_value;
    case JsonKind::Number:return a.number_value==b.number_value;
    case JsonKind::String:return a.string_value==b.string_value;
    case JsonKind::Array:
        return a.array_value.size()==b.array_value.size()&&std::equal(a.array_value.begin(),a.array_value.end(),b.array_value.begin(),authoring_json_equal);
    case JsonKind::Object:
        if(a.object_value.size()!=b.object_value.size())return false;
        {
            std::set<std::string> left,right;
            for(const auto& entry:a.object_value)if(!left.insert(entry.first).second)return false;
            for(const auto& entry:b.object_value)if(!right.insert(entry.first).second)return false;
            if(left!=right)return false;
        }
        for(const auto& [key,value]:a.object_value){auto p=object_field(b,key);if(!p||!authoring_json_equal(value,*p))return false;}
        return true;
    }
    return false;
}
} // namespace schgen
