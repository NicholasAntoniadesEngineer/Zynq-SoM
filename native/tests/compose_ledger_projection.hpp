#pragma once
#include "schgen/compose_repair.hpp"
#include <sstream>
#include <algorithm>
#include <numeric>
#include <tuple>

namespace schgen::test {
// Translate only the reviewed historical policy. Do not modify current output:
// all numeric measurements, unresolved failures and unrelated decisions remain
// exact regression evidence. Reindex numeric spelling metadata with moved rows.
inline ComposeDocument flow_policy_oracle(ComposeDocument d) {
    const auto member=[](JsonNode& n,const std::string& key)->JsonNode* {
        for(auto& [k,v]:n.object_value)if(k==key)return &v;
        return nullptr;
    };
    const auto str=[&](JsonNode& n,const std::string& key){
        auto* v=member(n,key);return v?v->string_value:std::string{};
    };
    const auto translate=[&](JsonNode& led,const std::string& path){
        for(const auto* name:{"flow_gate","advisory_gate"})if(auto* gate=member(led,name))
            if(auto* rows=member(*gate,"terms"))for(auto& row:rows->array_value) {
                auto* measured=member(row,"measured");JsonNode flag;flag.kind=JsonKind::Bool;
                flag.bool_value=str(row,"kind")=="flow"&&measured&&measured->kind==JsonKind::Number;
                if(!member(row,"advisory"))row.object_value.emplace_back("advisory",flag);
            }
        auto* rows=member(led,"terms");if(!rows)return;
        std::vector<std::string> trigger_prefixes;
        for(auto& row:rows->array_value)if(str(row,"kind")=="flow_hop") {
            auto* basis=member(row,"basis");
            if(!basis||basis->string_value.rfind("flow chain [",0)!=0)continue;
            basis->string_value.replace(0,10,"ADVISORY board-size-derived flow preference");
            if(auto* enforced=member(row,"enforced"))enforced->bool_value=false;
            const auto pair=str(row,"subject")+"->"+str(row,"target")+":";
            trigger_prefixes.push_back("flow "+pair+" margin ");
            trigger_prefixes.push_back("ADVISORY-RED flow_hop "+pair+" ");
        }
        if(auto* triggers=member(led,"repair_triggers")) {
            auto& list=triggers->array_value;
            list.erase(std::remove_if(list.begin(),list.end(),[&](const auto& t){
                return std::any_of(trigger_prefixes.begin(),trigger_prefixes.end(),
                    [&](const auto& prefix){return t.string_value.rfind(prefix,0)==0;});
            }),list.end());
        }
        std::vector<std::size_t> order(rows->array_value.size());std::iota(order.begin(),order.end(),0);
        const auto key=[&](std::size_t i){auto& row=rows->array_value[i];auto* enforced=member(row,"enforced");
            return std::make_tuple(!(enforced&&enforced->bool_value),str(row,"kind"),str(row,"subject"),str(row,"target"));};
        std::stable_sort(order.begin(),order.end(),[&](auto a,auto b){return key(a)<key(b);});
        const auto old=rows->array_value;const auto floats=d.float_paths;const auto integers=d.integer_tokens;
        const auto prefix=path+"/terms/";
        for(auto it=d.float_paths.begin();it!=d.float_paths.end();)if(it->rfind(prefix,0)==0)it=d.float_paths.erase(it);else ++it;
        for(auto it=d.integer_tokens.begin();it!=d.integer_tokens.end();)if(it->first.rfind(prefix,0)==0)it=d.integer_tokens.erase(it);else ++it;
        for(std::size_t i=0;i<order.size();++i) {
            rows->array_value[i]=old[order[i]];
            const auto from=prefix+std::to_string(order[i])+"/",to=prefix+std::to_string(i)+"/";
            for(const auto& p:floats)if(p.rfind(from,0)==0)d.float_paths.insert(to+p.substr(from.size()));
            for(const auto& [p,v]:integers)if(p.rfind(from,0)==0)d.integer_tokens[to+p.substr(from.size())]=v;
        }
    };
    if(d.data.kind==JsonKind::Array) {
        for(std::size_t i=0;i<d.data.array_value.size();++i)
            if(auto* led=member(d.data.array_value[i],"ledger"))translate(*led,"/"+std::to_string(i)+"/ledger");
    }else translate(d.data,"");
    return d;
}
// Strip only the reviewed unit-summary schema change; flow-policy translation
// is applied separately to the historical oracle, never to current output.
inline std::pair<std::string,std::size_t> compose_ledger_without_margins(const std::string& text) {
    auto d=parse_compose_document(text);std::size_t removed=0;
    const auto strip=[&](JsonNode& n){
        if(n.kind!=JsonKind::Object)return;
        for(auto it=n.object_value.begin();it!=n.object_value.end();){
            if(it->first=="hard_margins"||it->first=="aggregate_hard_margin"){
                ++removed;it=n.object_value.erase(it);
            }else ++it;
        }
    };
    if(d.data.kind==JsonKind::Array){
        for(auto& entry:d.data.array_value)for(auto& [key,value]:entry.object_value)
            if(key=="ledger")strip(value);
    }else strip(d.data);
    return {render_compose_json(d,1,true),removed};
}
inline bool compose_ledger_projection(const std::string& actual,const std::string& historical) {
    const auto a=compose_ledger_without_margins(actual),b=compose_ledger_without_margins(
        render_compose_json(flow_policy_oracle(parse_compose_document(historical)),1,true));
    return a.second>0&&a==b;
}
inline bool compose_markdown_projection(const std::string& actual,const std::string& historical) {
    const auto strip=[](const std::string& text){
        std::istringstream lines(text);std::string line,out;std::size_t removed=0;
        while(std::getline(lines,line)){
            if(line.rfind("- hard margin sum ",0)==0||line.rfind("- legacy mixed-unit margin ",0)==0||
               line.rfind("- hard margins distance_mm:",0)==0)++removed;
            else out+=line+'\n';
        }return std::make_pair(out,removed);
    };
    const auto a=strip(actual),b=strip(historical);return a.second>0&&a==b;
}
}
