#pragma once
#include "schgen/json.hpp"
#include <filesystem>
#include <map>
#include <set>
#include <stdexcept>

// TEST ONLY. An explicit, independently authored provenance delta over the
// immutable Python reference. Geometry, math results, events, and counters are
// never transformed. Production has no dependency on this file or the fixture.
namespace board_policy_reference {
inline const schgen::JsonNode& field(const schgen::JsonNode& n,const std::string& name){
    const auto* p=schgen::object_field(n,name);if(!p)throw std::runtime_error("policy reference missing "+name);return *p;
}
inline std::string name(const schgen::JsonNode& n){return field(n,"name").string_value;}
inline schgen::JsonNode migrate(schgen::JsonNode expected,const std::filesystem::path& data){
    using namespace schgen;
    const auto ref=parse_json_file((data/"board_policy/native_ledger_migration.json").string());
    const auto additions=parse_json_file((data/"precision_ops/policy_additions.json").string());
    const auto geometry_additions=parse_json_file((data/"board_policy/geometry_policy_additions.json").string());
    const auto remaining_additions=parse_json_file((data/"board_policy/composition_escape_policy_additions.json").string());
    const auto buried_additions=parse_json_file((data/"board_policy/buried_policy_additions.json").string());
    std::set<std::string> remove,removed;for(const auto* key:{"retired","replaced"})
        for(const auto& n:field(ref,key).array_value)remove.insert(n.string_value);
    std::map<std::string,JsonNode> texts,calculations;
    for(const auto& n:field(ref,"calculation_rows").array_value)texts.emplace(name(n),n);
    for(const auto& n:field(ref,"calculations").array_value)calculations.emplace(name(n),n);
    std::size_t inserted=0,changed=0,exposed=0;
    for(auto& [key,value]:expected.object_value){
        if(key=="ledger"){
            std::vector<JsonNode> rows;
            for(const auto& n:value.array_value){const auto id=name(n);
                if(field(n,"kind").string_value=="ASSUME"&&remove.count(id)){
                    if(!removed.insert(id).second)throw std::runtime_error("duplicate retired assumption");
                    if(id=="via_size")for(const auto& added:field(ref,"assumption_rows").array_value){rows.push_back(added);++inserted;}
                }else if(texts.count(id)){rows.push_back(texts.at(id));++changed;}
                else rows.push_back(n);
                if(id==field(additions,"after").string_value){
                    for(const auto& added:field(additions,"assumption_rows").array_value){rows.push_back(added);++exposed;}
                    for(const auto& added:field(geometry_additions,"assumption_rows").array_value){rows.push_back(added);++exposed;}
                    for(const auto& added:field(remaining_additions,"assumption_rows").array_value){rows.push_back(added);++exposed;}
                    for(const auto& added:field(buried_additions,"assumption_rows").array_value){rows.push_back(added);++exposed;}
                }
            }
            value.array_value=std::move(rows);
        }else if(key=="decisions"){
            for(auto& n:value.array_value)if(calculations.count(name(n)))n=calculations.at(name(n));
        }
    }
    if(removed!=remove||inserted!=2||changed!=2||exposed!=26)throw std::runtime_error("historical ledger provenance precondition changed");
    return expected;
}
}
