#pragma once
#include "pcb_placement_fixture.hpp"
#include "occupancy_precision_fixture.hpp"
#include "schgen/floorplan_ledger_policy.hpp"
#include <array>
#include <iomanip>
#include <sstream>

namespace floorplan_precision_fixture {
using namespace schgen;
inline const std::array<std::string,6> names{{"floorplan_candidate_area_precision1dp",
    "floorplan_seed_aspect_precision4dp","floorplan_ledger_value_precision1dp",
    "floorplan_ledger_margin_precision3dp","floorplan_ledger_dimension_precision4dp",
    "floorplan_ledger_display_precision4dp"}};
inline bool added(const std::string& name) {
    return std::find(names.begin(),names.end(),name)!=names.end();
}
inline QuantizationCounts select(const QuantizationCounts& values,bool new_only=true) {
    QuantizationCounts out;for(const auto& [name,count]:values)
        if(added(name)==new_only&&!occupancy_precision_fixture::added(name))out[name]=count;
    return out;
}
// Lossless typed snapshot: exact binary-double round trip, insertion order,
// strings and all decision fields. Only the independently proved additive
// counts are removed; every prior counter remains in the byte comparison.
inline void node(std::ostream& out,const JsonNode& value) {
    out<<static_cast<int>(value.kind)<<' ';
    switch(value.kind) {
    case JsonKind::Null: break;
    case JsonKind::Bool: out<<value.bool_value;break;
    case JsonKind::Number: out<<std::setprecision(17)<<value.number_value;break;
    case JsonKind::String: out<<std::quoted(value.string_value);break;
    case JsonKind::Array: out<<value.array_value.size()<<' ';for(const auto& v:value.array_value)node(out,v);break;
    case JsonKind::Object: out<<value.object_value.size()<<' ';for(const auto& [k,v]:value.object_value){out<<std::quoted(k)<<' ';node(out,v);}break;
    }
    out<<'\n';
}
inline void policy(std::ostream& out) {
    const auto rows=floorplan_ledger_policy();out<<"POLICY "<<rows.size()<<'\n';
    for(const auto& row:rows) {
        for(const auto* text:{&row.name,&row.kind,&row.step,&row.unit,&row.basis,&row.source,&row.legacy_cover,&row.expression})out<<std::quoted(*text)<<' ';
        out<<row.repeated<<' '<<row.inputs.size();for(const auto& key:row.inputs)out<<' '<<std::quoted(key);out<<'\n';
    }
}
inline void plan(std::ostream& out,const std::string& name,FloorplanPlan value) {
    value.accounting.quantization_engagements=select(value.accounting.quantization_engagements,false);
    out<<"PLAN "<<name<<'\n';node(out,floorplan_plan_json(value));
    out<<"LEDGER\n"<<render_floorplan_ledger(value)<<"END LEDGER\n";
    out<<"SPEC\n";node(out,export_floorplan_spec(value));
}
inline void counts(std::ostream& out,const char* owner,const QuantizationCounts& values) {
    out<<owner<<'\n';for(const auto& [name,count]:select(values,false))out<<std::quoted(name)<<' '<<count<<'\n';
}
}
