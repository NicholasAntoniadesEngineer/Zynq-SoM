#pragma once
#include "schgen/json.hpp"
#include <algorithm>
#include <cmath>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace schgen::pcb_placement {
struct ContractRigidGroup {
    std::vector<std::string> refs;
    std::vector<std::string> required_top_refs;
    bool operator==(const ContractRigidGroup& other) const {
        return refs==other.refs&&required_top_refs==other.required_top_refs;
    }
};

// Partition supported lightweight contracts into rigid translation groups.
// This is constraint closure, NOT bottom-side permission: geometry, electrical,
// assembly and thermal qualification must still decide candidate eligibility.
// Unsupported or malformed constraints return no partition, never free parts.
inline std::optional<std::vector<ContractRigidGroup>> contract_rigid_groups(
        const JsonNode& contract,const std::map<std::string,std::string>& board_refs,
        const std::set<std::string>& required_top) {
    if(contract.kind!=JsonKind::Object||board_refs.empty())return std::nullopt;
    const auto* schema=object_field(contract,"contract");
    if(!schema||schema->kind!=JsonKind::String||schema->string_value!="placement/lightweight-v0")return std::nullopt;
    const auto* external=object_field(contract,"external");
    if(external&&!(external->kind==JsonKind::Object&&external->object_value.empty()))return std::nullopt;
    const auto* structures=object_field(contract,"structures");
    if(!structures||structures->kind!=JsonKind::Array||structures->array_value.empty())return std::nullopt;
    std::map<std::string,std::set<std::string>> graph;
    for(const auto& [local,qualified]:board_refs) {
        if(local.empty()||qualified.empty()||graph.count(qualified))return std::nullopt;
        graph.emplace(qualified,std::set<std::string>{});
    }
    for(const auto& ref:required_top)if(!graph.count(ref))return std::nullopt;
    const auto resolve=[&](const JsonNode* node)->std::optional<std::string> {
        if(!node||node->kind!=JsonKind::String)return std::nullopt;
        const auto found=board_refs.find(node->string_value);
        if(found==board_refs.end())return std::nullopt;
        return found->second;
    };
    const auto connect=[&](const std::string& a,const std::string& b) {
        graph.at(a).insert(b);graph.at(b).insert(a);
    };
    for(const auto& structure:structures->array_value) {
        if(structure.kind!=JsonKind::Object)return std::nullopt;
        const auto* type=object_field(structure,"type");
        if(!type||type->kind!=JsonKind::String)return std::nullopt;
        if(type->string_value=="same_side") {
            // This lists owners, not a single all-IC face group. Each owner's
            // proximity members are already joined by their own structures.
            for(const auto& [key,value]:structure.object_value) {
                (void)value;if(key!="type"&&key!="ics"&&key!="basis")return std::nullopt;
            }
            const auto* ics=object_field(structure,"ics");
            if(!ics||ics->kind!=JsonKind::Array||ics->array_value.empty())return std::nullopt;
            for(const auto& ic:ics->array_value)if(!resolve(&ic))return std::nullopt;
            continue;
        }
        if(type->string_value!="proximity")return std::nullopt;
        for(const auto& [key,value]:structure.object_value) {
            (void)value;
            if(key!="type"&&key!="anchor"&&key!="anchor_pins"&&key!="members"&&
               key!="max_mm"&&key!="same_side"&&key!="min_from"&&key!="basis")return std::nullopt;
        }
        const auto anchor=resolve(object_field(structure,"anchor"));
        const auto* members=object_field(structure,"members");
        const auto* bound=object_field(structure,"max_mm");
        if(!anchor||!members||members->kind!=JsonKind::Array||members->array_value.empty()||
           !bound||bound->kind!=JsonKind::Number||!std::isfinite(bound->number_value)||bound->number_value<=0)
            return std::nullopt;
        if(const auto* side=object_field(structure,"same_side");side&&side->kind!=JsonKind::Bool)return std::nullopt;
        if(const auto* pins=object_field(structure,"anchor_pins")) {
            if(pins->kind!=JsonKind::Array)return std::nullopt;
            for(const auto& pin:pins->array_value)if(pin.kind!=JsonKind::String||pin.string_value.empty())return std::nullopt;
        }
        for(const auto& member:members->array_value) {
            const auto ref=resolve(&member);if(!ref)return std::nullopt;connect(*anchor,*ref);
        }
        if(const auto* away=object_field(structure,"min_from")) {
            if(away->kind!=JsonKind::Array)return std::nullopt;
            for(const auto& item:away->array_value) {
                if(item.kind!=JsonKind::Object)return std::nullopt;
                for(const auto& [key,value]:item.object_value) {
                    (void)value;if(key!="part"&&key!="pin"&&key!="min_mm")return std::nullopt;
                }
                const auto* distance=object_field(item,"min_mm");
                if(!distance||distance->kind!=JsonKind::Number||!std::isfinite(distance->number_value)||distance->number_value<0)
                    return std::nullopt;
                if(const auto* pin=object_field(item,"pin");pin&&(pin->kind!=JsonKind::String||pin->string_value.empty()))return std::nullopt;
                const auto ref=resolve(object_field(item,"part"));
                if(!ref)return std::nullopt;connect(*anchor,*ref);
            }
        }
    }
    std::set<std::string> visited;
    std::vector<ContractRigidGroup> groups;
    for(const auto& [start,edges]:graph) {
        (void)edges;if(visited.count(start))continue;
        ContractRigidGroup group;std::vector<std::string> pending{start};visited.insert(start);
        while(!pending.empty()) {
            const auto ref=pending.back();pending.pop_back();group.refs.push_back(ref);
            if(required_top.count(ref))group.required_top_refs.push_back(ref);
            for(const auto& next:graph.at(ref))if(visited.insert(next).second)pending.push_back(next);
        }
        std::sort(group.refs.begin(),group.refs.end());
        std::sort(group.required_top_refs.begin(),group.required_top_refs.end());
        groups.push_back(std::move(group));
    }
    return groups;
}
} // namespace schgen::pcb_placement
