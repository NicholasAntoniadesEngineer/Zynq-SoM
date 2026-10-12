#pragma once
#include "schgen/compose_repair.hpp"
#include <sstream>

namespace schgen::test {
// Permit only the explicitly reviewed margin-summary schema change. Preserve
// every original term, verdict, acceptance decision and integer/float spelling.
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
    const auto a=compose_ledger_without_margins(actual),b=compose_ledger_without_margins(historical);
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
