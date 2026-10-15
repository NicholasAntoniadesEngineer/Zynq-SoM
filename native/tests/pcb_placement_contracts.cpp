#include "pcb_placement_fixture.hpp"
#include "schgen/pcb_emit.hpp"
#include "schgen/pcb_placement_gates.hpp"
#include "pcb_placement_requirements.hpp"
#include "../src/contract_rigid_groups_internal.hpp"
#include <iostream>
#include <limits>

namespace {
using namespace placement_fixture;
int checks = 0;
void require(bool p, const std::string &message) {
    ++checks;
    if (!p)
        throw std::runtime_error(message);
}
void exact(double a, double b, const std::string &context) {
    require(a == b, context + " actual " + std::to_string(a) + " expected " + std::to_string(b));
}
void constraint_merge_contracts() {
    for (bool hard : {false, true}) for (bool reverse : {false, true})
        for (bool minimum : {false, true}) {
            PcbPlacementInput in;
            CircuitSheetIr a, b; a.name="a"; b.name="b";
            in.floorplan.sheets={a,b};
            if(hard) in.floorplan.project.wired_sheets={"a"};
            const std::string key=minimum?"far":"near_max";
            const std::string target=minimum?"what":"other", bound=minimum?"min_mm":"max_mm";
            std::string rows;
            // Reordered and repeated declarations must describe the same
            // conjunction, independently of hard/advisory classification.
            for(int n : reverse?std::vector<int>{8,2,8}:std::vector<int>{2,8,2}) {
                if(!rows.empty())rows+=",";
                rows+="{\""+target+"\":\"b\",\""+bound+"\":"+std::to_string(n)+
                    ",\"basis\":\"requirement "+std::to_string(n)+"\"}";
            }
            in.contracts["a"]=parse_json_text("{\"external\":{\""+key+"\":["+rows+"]}}");
            const auto prepared=prepare_pcb_floorplan(in,{});
            PcbCheckModel model;model.insts.resize(2);
            model.insts[0].sheet="a";model.insts[1].sheet="b";
            const auto final_index=pcb_final_compose_index(in,model);
            for(const auto* index : {&prepared.compose.index,&final_index}) {
                const auto& terms=hard?index->hard:index->soft;
                require(terms.size()==1&&index->na.empty()&&
                        (hard?index->soft:index->hard).empty(),"merged requirement classification");
                const auto& term=terms.front();
                require(term.bound&&*term.bound==(minimum?8:2),"merged constraint weakened a bound");
                require(term.basis==std::string("requirement ")+(minimum?"8":"2"),
                        "retained bound lost its authored justification");
            }
        }
}
void rigid_group_contracts(const std::filesystem::path& root) {
    using pcb_placement::contract_rigid_groups;
    auto contract=parse_json_file((root/"subsystems/usb_jtag/placement_contract.json").string());
    const auto circuit=parse_json_file((root/"carrier/subsystems/usb_jtag/circuit.json").string());
    std::map<std::string,std::string> refs;
    for(const auto& part:field(circuit,"parts").array_value)refs.emplace(string(part,"ref"),"pcb/"+string(part,"ref"));
    const std::set<std::string> pinned{"pcb/U1","pcb/SW1","pcb/TP1","pcb/TP2","pcb/TP3"};
    const auto groups=contract_rigid_groups(contract,refs,pinned);
    require(groups&&groups->size()==7,"real USB-JTAG must have three rigid groups plus four controls");
    const auto group_of=[&](const std::string& ref)->const pcb_placement::ContractRigidGroup& {
        for(const auto& group:*groups)if(std::find(group.refs.begin(),group.refs.end(),"pcb/"+ref)!=group.refs.end())return group;
        throw std::runtime_error("missing rigid-group witness "+ref);
    };
    require(group_of("U4").refs==std::vector<std::string>{"pcb/C1","pcb/C2","pcb/C3","pcb/U4"},"LDO group closure");
    require(group_of("U2").refs==std::vector<std::string>{"pcb/C7","pcb/R4","pcb/U2"},"buffer group closure");
    require(group_of("U1").refs==std::vector<std::string>{"pcb/C4","pcb/C5","pcb/C6","pcb/R1","pcb/R2","pcb/R3","pcb/U1","pcb/Y1"},
        "bridge must retain transitive crystal/load-cap closure");
    require(group_of("C5").required_top_refs==std::vector<std::string>{"pcb/U1"},"controlled owner pins the entire connected group");
    require(group_of("U2").required_top_refs.empty()&&group_of("U4").required_top_refs.empty(),"same_side owners are not globally joined");
    require(group_of("SW1").required_top_refs==std::vector<std::string>{"pcb/SW1"},"top-access control remains pinned");
    const auto edit=[](JsonNode& node,const std::string& key)->JsonNode& {
        for(auto& item:node.object_value)if(item.first==key)return item.second;
        throw std::runtime_error("missing mutation key "+key);
    };
    auto reordered=contract;
    std::reverse(edit(reordered,"structures").array_value.begin(),edit(reordered,"structures").array_value.end());
    require(contract_rigid_groups(reordered,refs,pinned)==groups,"group partition must be independent of structure order");
    auto cyclic=contract;
    edit(cyclic,"structures").array_value.push_back(parse_json_text(
        R"({"type":"proximity","anchor":"R1","members":["U1"],"max_mm":6})"));
    require(contract_rigid_groups(cyclic,refs,pinned)==groups,"cyclic constraints must terminate without splitting or duplicating members");
    std::set<std::string> covered;
    for(const auto& group:*groups)for(const auto& ref:group.refs)require(covered.insert(ref).second,"part assigned to multiple rigid groups");
    require(covered.size()==refs.size(),"partition must cover every mapped part");
    auto linked=contract;
    edit(linked,"structures").array_value.front().object_value.emplace_back("min_from",parse_json_text(R"([{"part":"U2","min_mm":1}])"));
    const auto connected=contract_rigid_groups(linked,refs,pinned);
    require(connected&&connected->size()==6,"minimum-distance cross-link must prevent independently moving groups");
    for(const auto& mutation:{std::string("unknown-type"),std::string("missing-member"),std::string("bad-distance"),std::string("external"),std::string("schema"),
                             std::string("unknown-field"),std::string("bad-away-distance"),std::string("bad-pin"),std::string("empty-members"),std::string("nonfinite-bound")}) {
        auto changed=contract;auto& first=edit(changed,"structures").array_value.front();
        if(mutation=="unknown-type")edit(first,"type").string_value="future_constraint";
        if(mutation=="missing-member")edit(first,"members").array_value.front().string_value="MISSING";
        if(mutation=="bad-distance")edit(first,"max_mm").number_value=-1;
        if(mutation=="external")changed.object_value.emplace_back("external",parse_json_text(R"({"near":"unknown"})"));
        if(mutation=="schema")edit(changed,"contract").string_value="future-schema";
        if(mutation=="unknown-field")first.object_value.emplace_back("future_limit",parse_json_text("1"));
        if(mutation=="bad-away-distance")first.object_value.emplace_back("min_from",parse_json_text(R"([{"part":"U2","min_mm":-1}])"));
        if(mutation=="bad-pin")edit(first,"anchor_pins").array_value.front()=parse_json_text("14");
        if(mutation=="empty-members")edit(first,"members").array_value.clear();
        if(mutation=="nonfinite-bound")edit(first,"max_mm").number_value=std::numeric_limits<double>::quiet_NaN();
        require(!contract_rigid_groups(changed,refs,pinned),"unsupported grouping must fail closed: "+mutation);
    }
    auto aliases=refs;aliases["alias"]="pcb/U1";
    require(!contract_rigid_groups(contract,aliases,pinned),"ambiguous board identity must reject");
    auto unknown=pinned;unknown.insert("pcb/MISSING");
    require(!contract_rigid_groups(contract,refs,unknown),"unknown mandatory-top owner must reject");
}
void power_rigid_group_contracts(const std::filesystem::path& root) {
    using pcb_placement::contract_rigid_groups;
    const auto edit=[](JsonNode& node,const std::string& key)->JsonNode& {
        for(auto& [name,value]:node.object_value)if(name==key)return value;
        throw std::runtime_error("missing power mutation key "+key);
    };
    const auto erase=[](JsonNode& node,const std::string& key) {
        auto& values=node.object_value;
        values.erase(std::remove_if(values.begin(),values.end(),[&](const auto& kv){return kv.first==key;}),values.end());
    };
    const auto group_of=[](const auto& groups,const std::string& ref)->const pcb_placement::ContractRigidGroup& {
        for(const auto& group:groups)if(std::find(group.refs.begin(),group.refs.end(),"pcb/"+ref)!=group.refs.end())return group;
        throw std::runtime_error("missing power rigid-group witness "+ref);
    };
    const auto qualified=[](std::vector<std::string> refs) {
        for(auto& ref:refs)ref="pcb/"+ref;
        std::sort(refs.begin(),refs.end());return refs;
    };
    for(const std::string sheet:{"power","power_som"}) {
        const auto path=sheet=="power"?"subsystems/power/placement_contract.json":
            "carrier/subsystems/power_som/placement_contract.json";
        const auto contract=parse_json_file((root/path).string());
        const auto circuit=parse_json_file((root/"carrier/subsystems"/sheet/"circuit.json").string());
        std::map<std::string,std::string> refs;
        for(const auto& part:field(circuit,"parts").array_value)
            refs.emplace(string(part,"ref"),"pcb/"+string(part,"ref"));
        const std::string owner=sheet=="power"?"U1":"U4";
        const std::set<std::string> pinned{"pcb/"+owner};
        const auto groups=contract_rigid_groups(contract,refs,pinned,true);
        require(bool(groups),sheet+" real v2 contract must partition when opted in");
        require(!contract_rigid_groups(contract,refs,pinned)&&!contract_rigid_groups(contract,refs,pinned,false),
                sheet+" v2 must remain unsupported for default/explicit-false thermal callers");
        const std::vector<std::string> first=sheet=="power"?
            std::vector<std::string>{"U1","C1","C25","C2","C3","C5","C6","C26","L1","R1","R2","C27","R12","C4","C24","C28","R10"}:
            std::vector<std::string>{"U4","C14","C25","C15","C16","C18","C19","L3","R14","R15","C21","R19","C17","C22","C23","R18"};
        require(group_of(*groups,owner).refs==qualified(first),sheet+" exact buck closure");
        require(group_of(*groups,owner).required_top_refs==std::vector<std::string>{"pcb/"+owner},"top owner propagates within its stage");
        std::set<std::string> staged(first.begin(),first.end());
        if(sheet=="power") {
            const std::vector<std::string> second{"U2","C7","C29","C8","C30","C10","C11","L2","R4","R5","C23","R15","C9","C31","C32","R14"};
            require(group_of(*groups,"U2").refs==qualified(second),"foreign FB minima must not fuse buck stages");
            require(group_of(*groups,"U3").refs==qualified({"U3","C12","C13"}),"LDO stage closure");
            require(group_of(*groups,"U2").required_top_refs.empty()&&group_of(*groups,"U3").required_top_refs.empty(),
                    "same_side must not propagate a top pin across independent owners");
            staged.insert(second.begin(),second.end());staged.insert({"U3","C12","C13"});
        }
        std::set<std::string> covered;
        for(const auto& group:*groups)for(const auto& ref:group.refs)
            require(covered.insert(ref).second,"power partition overlaps");
        require(covered.size()==refs.size(),"power partition must include every mapped part");
        for(const auto& [local,board]:refs)if(!staged.count(local))
            require(group_of(*groups,local).refs==std::vector<std::string>{board},"unconstrained parts remain singleton: "+local);
        auto reversed=contract;
        std::reverse(edit(reversed,"structures").array_value.begin(),edit(reversed,"structures").array_value.end());
        require(contract_rigid_groups(reversed,refs,pinned,true)==groups,"power structure order must not change partition");
        auto duplicate=contract;
        edit(duplicate,"structures").array_value.push_back(field(contract,"structures").array_value.front());
        require(contract_rigid_groups(duplicate,refs,pinned,true)==groups,"repeated power structures are idempotent");

        // Check each branch alone so another structure cannot hide a missing edge.
        const std::map<std::string,std::vector<std::string>> own_fields{
            {"hot_loop",{"caps"}},{"bulk_in",{"caps"}},{"bulk_out",{"caps","inductor"}},
            {"sw_node",{"inductor"}},{"fb_cluster",{"members","own_inductor"}},
            {"boot",{"cap"}},{"vcc_cap",{"cap"}},{"bias_cap",{"cap"}},
            {"rt_r",{"resistor"}},{"ldo_stage",{"cin","cout"}}
        };
        for(const auto& structure:field(contract,"structures").array_value) {
            const auto type=string(structure,"type");
            auto only=contract;edit(only,"structures").array_value={structure};
            const auto isolated=contract_rigid_groups(only,refs,{},true);
            require(bool(isolated),"isolated valid power structure: "+type);
            if(type!="same_side") {
                auto lightweight=only;edit(lightweight,"contract").string_value="placement/lightweight-v0";
                edit(lightweight,"external")=parse_json_text("{}");
                require(!contract_rigid_groups(lightweight,refs,{})&&!contract_rigid_groups(lightweight,refs,{},true),
                        "power structures require the v2 schema: "+type);
            }
            if(type=="same_side")require(isolated->size()==refs.size(),"same_side alone must not join owners");
            else {
                std::vector<std::string> expected{string(structure,"ic")};
                for(const auto& key:own_fields.at(type)) {
                    const auto& value=field(structure,key);
                    if(value.kind==JsonKind::Array)for(const auto& ref:value.array_value)expected.push_back(ref.string_value);
                    else expected.push_back(value.string_value);
                }
                require(group_of(*isolated,string(structure,"ic")).refs==qualified(expected),"isolated own-member closure: "+type);
                require(isolated->size()==refs.size()-expected.size()+1,"only own members joined: "+type);
            }
            const auto reject=[&](const JsonNode& changed,const std::string& why) {
                auto bad=only;edit(bad,"structures").array_value={changed};
                require(!contract_rigid_groups(bad,refs,{},true),type+" must reject "+why);
            };
            auto extra=structure;extra.object_value.emplace_back("future_limit",parse_json_text("1"));
            reject(extra,"unknown field");
            extra=structure;extra.object_value.push_back(structure.object_value.front());
            reject(extra,"duplicate field");
            extra=structure;edit(extra,"type").string_value="future_stage";reject(extra,"unknown type");
            for(const auto& [key,value]:structure.object_value) {
                auto bad=structure;edit(bad,key)=parse_json_text("null");reject(bad,"null "+key);
                bad=structure;edit(bad,key)=parse_json_text("{}");reject(bad,"object "+key);
                if(key!="same_side"&&key!="basis") {
                    bad=structure;erase(bad,key);reject(bad,"missing "+key);
                }
                if(value.kind==JsonKind::Number) {
                    for(double n:{-1.0,std::numeric_limits<double>::infinity(),-std::numeric_limits<double>::infinity(),
                                  std::numeric_limits<double>::quiet_NaN()}) {
                        bad=structure;edit(bad,key).number_value=n;reject(bad,"invalid numeric "+key);
                    }
                    bad=structure;edit(bad,key)=parse_json_text("\"1\"");reject(bad,"string bound "+key);
                    bad=structure;edit(bad,key).number_value=0;
                    if(key.rfind("max",0)==0)reject(bad,"zero maximum "+key);
                    else {
                        auto zero=only;edit(zero,"structures").array_value={bad};
                        require(bool(contract_rigid_groups(zero,refs,{},true)),"zero minimum must be valid: "+key);
                    }
                } else if(value.kind==JsonKind::String&&key!="basis") {
                    bad=structure;edit(bad,key).string_value="";reject(bad,"empty "+key);
                    if(refs.count(value.string_value)) {
                        bad=structure;edit(bad,key).string_value="MISSING";reject(bad,"unknown ref "+key);
                    }
                } else if(value.kind==JsonKind::Array) {
                    bad=structure;edit(bad,key).array_value.clear();reject(bad,"empty "+key);
                    bad=structure;edit(bad,key).array_value.front()=parse_json_text("42");reject(bad,"bad array element "+key);
                    if(key=="caps"||key=="members"||key=="ics") {
                        bad=structure;edit(bad,key).array_value.front().string_value="MISSING";reject(bad,"unknown member "+key);
                    }
                }
            }
            if(type=="hot_loop") {
                auto bad=structure;erase(bad,"basis");reject(bad,"missing required basis");
                for(const auto* pair:{R"([])",R"(["8"])",R"(["8","9","10"])",R"(["8",9])",R"(["8",""])"}) {
                    bad=structure;edit(bad,"pin_pairs").array_value.front()=parse_json_text(pair);reject(bad,"malformed pin pair");
                }
            }
            if(type=="fb_cluster") {
                auto no_foreign=only;
                for(const auto* key:{"foreign_ic","foreign_inductor","foreign_sw_pin","min_to_foreign_sw_mm"})
                    erase(edit(no_foreign,"structures").array_value.front(),key);
                require(contract_rigid_groups(no_foreign,refs,{},true)==isolated,"foreign tuple is optional and adds no edges");
                if(object_field(structure,"foreign_ic")) {
                    auto distant=only;
                    edit(edit(distant,"structures").array_value.front(),"min_to_foreign_sw_mm").number_value=1e9;
                    require(contract_rigid_groups(distant,refs,{},true)==isolated,
                            "even an unqualified foreign bound must neither merge nor qualify stages");
                }
                // A lone foreign field cannot silently become an unchecked bound.
                for(const auto* tuple:{R"({"foreign_ic":"U4"})",R"({"foreign_inductor":"L3"})",
                                      R"({"foreign_sw_pin":"10"})",R"({"min_to_foreign_sw_mm":5})"}) {
                    auto partial=no_foreign;
                    edit(partial,"structures").array_value.front().object_value.push_back(parse_json_text(tuple).object_value.front());
                    require(!contract_rigid_groups(partial,refs,{},true),"partial foreign tuple must reject");
                }
            }
        }
        // External data grants no edges or qualification. Only its known syntax
        // is checked here; project targets cannot resolve against local part refs.
        for(const auto* ext:{R"({})",R"({"flow":["elsewhere","@som"],"downstream":"@som","output_roles":["cout_bulk"],"far":[{"what":"ethernet.line_side","min_mm":0}],"near_max":[{"other":"@som","max_mm":4}],"media_faces_near_max":true})"}) {
            auto changed=contract;edit(changed,"external")=parse_json_text(ext);
            require(contract_rigid_groups(changed,refs,pinned,true)==groups,"known external syntax must not change grouping");
        }
        auto no_external=contract;erase(no_external,"external");
        require(contract_rigid_groups(no_external,refs,pinned,true)==groups,"external object is optional");
        for(const auto* ext:{R"(null)",R"([])",R"({"future":true})",R"({"flow":"power"})",R"({"flow":[""]})",
                            R"({"downstream":[]})",R"({"downstream":""})",R"({"output_roles":[1]})",
                            R"({"media_faces_near_max":1})",R"({"far":{}})",R"({"far":[1]})",
                            R"({"far":[{"min_mm":2}]})",R"({"far":[{"what":"x","min_mm":-1}]})",
                            R"({"far":[{"what":"x","min_mm":2,"basis":false}]})",
                            R"({"near_max":[{"other":"x","max_mm":0}]})",R"({"near_max":[{"other":"x","max_mm":"2"}]})",
                            R"({"near_max":[{"other":"x","max_mm":2,"unknown":1}]})"}) {
            auto bad=contract;edit(bad,"external")=parse_json_text(ext);
            require(!contract_rigid_groups(bad,refs,pinned,true),"malformed external must reject: "+std::string(ext));
        }
        for(const auto* key:{"far","near_max"}) {
            auto bad=contract;
            edit(bad,"external")=parse_json_text(key==std::string("far")?R"({"far":[{"what":"x","min_mm":1}]})":
                R"({"near_max":[{"other":"x","max_mm":1}]})");
            auto& row=edit(edit(bad,"external"),key).array_value.front();
            edit(row,key==std::string("far")?"min_mm":"max_mm").number_value=std::numeric_limits<double>::infinity();
            require(!contract_rigid_groups(bad,refs,pinned,true),"nonfinite external bound must reject");
        }
        auto bad=contract;edit(bad,"stage_order").array_value.front().string_value="MISSING";
        require(!contract_rigid_groups(bad,refs,pinned,true),"unknown stage_order ref must reject");
        bad=contract;edit(bad,"roles").object_value.emplace_back("MISSING",parse_json_text("\"buck_ic\""));
        require(!contract_rigid_groups(bad,refs,pinned,true),"unknown role ref must reject");
        bad=contract;edit(bad,"structures").array_value.clear();
        require(!contract_rigid_groups(bad,refs,pinned,true),"empty v2 structures must reject");
        bad=contract;edit(bad,"contract").string_value="placement/v3";
        require(!contract_rigid_groups(bad,refs,pinned,true),"opt-in must not accept unknown schemas");
        bad=contract;bad.object_value.emplace_back("external",parse_json_text("{}"));
        require(!contract_rigid_groups(bad,refs,pinned,true),"duplicate v2 root fields must reject");
        bad=contract;bad.object_value.emplace_back("unhandled_hardware_rule",parse_json_text("{}"));
        require(!contract_rigid_groups(bad,refs,pinned,true),"unknown v2 root constraints must reject");
        auto aliases=refs;aliases["alias"]="pcb/"+owner;
        require(!contract_rigid_groups(contract,aliases,pinned,true),"v2 aliased board identity must reject");
        require(!contract_rigid_groups(contract,refs,{"pcb/MISSING"},true),"v2 unknown top owner must reject");
    }
    // Lightweight callers retain all prior closure, including min_from. The v2
    // caller instead rechecks between-stage minima after each candidate move.
    auto proximity=parse_json_text(R"({"contract":"placement/lightweight-v0","structures":[
        {"type":"proximity","anchor":"U1","members":["C1"],"max_mm":2,"min_from":[{"part":"U2","pin":"10","min_mm":1}]},
        {"type":"proximity","anchor":"U2","members":["C2"],"max_mm":2},
        {"type":"same_side","ics":["U1","U2"]}]})");
    const std::map<std::string,std::string> refs{{"U1","pcb/U1"},{"U2","pcb/U2"},{"C1","pcb/C1"},{"C2","pcb/C2"}};
    const auto original=contract_rigid_groups(proximity,refs,{});
    require(original&&original->size()==1&&contract_rigid_groups(proximity,refs,{},true)==original,
            "opting in must not alter lightweight semantics");
    auto external=proximity;external.object_value.emplace_back("external",parse_json_text(R"({"flow":["a","b"]})"));
    require(!contract_rigid_groups(external,refs,{})&&!contract_rigid_groups(external,refs,{},true),
            "lightweight external remains rejected even with opt-in");
    edit(proximity,"contract").string_value="placement/v2";
    const auto separate=contract_rigid_groups(proximity,refs,{},true);
    require(separate&&separate->size()==2,"v2 proximity minimum alone must not join stages");
    require(group_of(*separate,"U1").refs==qualified({"U1","C1"})&&
            group_of(*separate,"U2").refs==qualified({"U2","C2"}),"v2 proximity/same_side own closure");
    auto bad=proximity;
    edit(edit(bad,"structures").array_value.front(),"min_from").array_value.front().object_value.emplace_back("future",parse_json_text("1"));
    require(!contract_rigid_groups(bad,refs,{},true),"unknown v2 minimum field must reject");
    for(const auto* away:{R"([{"part":"MISSING","min_mm":1}])",R"([{"part":"U2","min_mm":-1}])",
                          R"([{"part":"U2","min_mm":1,"pin":2}])"}) {
        bad=proximity;edit(edit(bad,"structures").array_value.front(),"min_from")=parse_json_text(away);
        require(!contract_rigid_groups(bad,refs,{},true),"malformed v2 proximity minimum must reject");
    }
    auto transitive=proximity;
    edit(transitive,"structures").array_value.push_back(parse_json_text(R"({"type":"proximity","anchor":"C1","members":["U2"],"max_mm":3})"));
    const auto joined=contract_rigid_groups(transitive,refs,{},true);
    require(joined&&joined->size()==1,"explicit own-member overlap must still join transitively in v2");
}
void same(const J &a, const J &b, const std::string &path) {
    require(a.kind == b.kind, path + " type");
    if (a.kind == JsonKind::Object) {
        require(a.object_value.size() == b.object_value.size(), path + " key count");
        for (const auto &[k, v] : b.object_value)
            same(field(a, k), v, path + "/" + k);
    } else if (a.kind == JsonKind::Array) {
        require(a.array_value.size() == b.array_value.size(), path + " array size");
        for (std::size_t k = 0; k < b.array_value.size(); ++k)
            same(a.array_value[k], b.array_value[k], path + "/" + std::to_string(k));
    } else if (a.kind == JsonKind::Number)
        exact(a.number_value, b.number_value, path);
    else if (a.kind == JsonKind::String)
        require(a.string_value == b.string_value,
                path + " string: " + a.string_value + " != " + b.string_value);
    else if (a.kind == JsonKind::Bool)
        require(a.bool_value == b.bool_value, path + " bool");
}
void offsets(const FloorplanOffsets &actual, const J &expected, const std::string &context) {
    require(actual.size() == expected.object_value.size(), context + " member count");
    for (const auto &[r, p] : expected.object_value) {
        require(actual.count(r), context + " missing " + r);
        auto a = actual.at(r), b = point(p);
        exact(a.first, b.first, context + "/" + r + " x");
        exact(a.second, b.second, context + "/" + r + " y");
    }
}
void rotations(const FloorplanRotations &actual, const J &expected, const std::string &context) {
    require(actual.size() == expected.object_value.size(), context + " member count");
    for (const auto &[r, p] : expected.object_value)
        exact(actual.at(r), p.number_value, context + "/" + r);
}
void geometry(const PcbZoneResult &zones, const J &expected, const std::string &context) {
    const auto &g = zones.geometry;
    offsets(g.zone_box, field(expected, "zone_box"), context + "/size");
    for (const auto &[sheet, e] : field(expected, "top_off").object_value) {
        offsets(g.top_off.at(sheet), e, context + "/" + sheet + "/top");
        offsets(g.bot_off.at(sheet), field(field(expected, "bot_off"), sheet),
                context + "/" + sheet + "/bottom");
    }
    rotations(g.conn_rot, field(expected, "conn_rot"), context + "/connector rotations");
    rotations(g.zone_extra_rot, field(expected, "zone_extra_rot"), context + "/extra rotations");
    require(g.side_of.size() == field(expected, "side_of").object_value.size(),
            context + " sides count");
    for (const auto &[r, s] : field(expected, "side_of").object_value)
        require(g.side_of.at(r) == s.string_value, context + " side " + r);
    require(g.shapes.size() == field(expected, "shapes").object_value.size(),
            context + " shape sheets count");
    for (const auto &[sheet, ss] : field(expected, "shapes").object_value) {
        const auto &shapes = g.shapes.at(sheet);
        require(shapes.size() == ss.array_value.size(), context + " " + sheet + " shape count");
        for (std::size_t k = 0; k < shapes.size(); ++k) {
            const auto &s = shapes[k];
            const auto &e = ss.array_value[k];
            auto where = context + "/" + sheet + "/shape " + std::to_string(k);
            exact(s.w, number(e, "w"), where + " w");
            exact(s.h, number(e, "h"), where + " h");
            offsets(s.top_off, field(e, "top_off"), where + " top");
            offsets(s.bot_off, field(e, "bot_off"), where + " bottom");
            rotations(s.extra_rot, field(e, "extra_rot"), where + " rot");
            require(s.side == string(e, "side") && s.tag == string(e, "tag"), where + " tag/side");
            require(s.mirror.size() == field(e, "mirror").object_value.size(),
                    where + " mirror count");
        }
    }
}
void run(const std::filesystem::path &root, const std::string &name, const std::string &mode) {
    auto f = load(root, name);
    const bool single = mode == "--single";
    if(name=="carrier"&&!single) {
        // A two-sided search must not move the whole USB bridge zone onto an
        // unreferenced signal layer. Exercise both authored eligibility forms
        // against the real carrier net classes, not a mocked gate result.
        require(bool(f.input.floorplan.spec),"carrier side-policy witness needs a spec");
        for(const auto* layer:{"either","bottom"}) {
            auto changed=f.input;
            changed.floorplan.spec->interior.at("usb_jtag").layer=layer;
            bool rejected=false;
            try{(void)build_pcb_zone_geometry(changed);}
            catch(const std::exception& e){
                rejected=std::string(e.what()).find(
                    "usb_jtag carries impedance-controlled net class DP90_USB; B.Cu has no emitted reference plane")!=std::string::npos;
            }
            require(rejected,std::string("unreferenced USB face eligibility escaped: ")+layer);
        }
    }
    if (single) {
        const auto variant = parse_json_file(
            (root / "native/tests/data/pcb_placement" / (name + "_single.json")).string());
        f.input.two_side = false;
        // The old devkit result remains an immutable NEGATIVE physical witness.
        // Do not require current production to reproduce that failure, nor the
        // carrier's former wrong-shape rejection from mismatched planning zones.
        if (const auto *model = object_field(variant, "model")) {
            auto pool=f.expected_pool;
            for(const auto& [path,bytes]:field(variant,"footprints").object_value)
                pool[path]=pcb_check_footprint(path,bytes.string_value);
            const auto original=pcb_model_from_json(*model,pool);
            require(!check_fanout(PcbCheckInput(original),0).ok,
                    "immutable top-preferred overlap witness must still fail the physical gate");
        }
    }
    auto zones = build_pcb_zone_geometry(f.input);
    if (!single && mode == "--zones-only") {
        geometry(zones, f.geometry, name + " zones");
        std::cout << name << ": complete independently frozen zone/shape geometry passed\n";
        require(zones.fallback_events == strings(field(f.source, "zone_events")),
                name + " ordered zone fallback events");
        for (const auto &[key, value] : field(f.source, "zone_quant").object_value)
            exact(static_cast<double>(zones.quantization_engagements[key]), value.number_value,
                  name + " zone quantization " + key);
    }
    if (mode == "--zones-only")
        return;
    // A spill must not move a connector independently of the group for which
    // its offsets and orientation were prepared. Exercise every wrong edge,
    // using the live geometry rather than a hard-coded board/reference name.
    if(!single) {
        std::size_t mismatches=0;
        for(const auto& entry:zones.geometry.conn_edge) {
            const auto& ref=entry.first;
            const auto& edge=entry.second;
            const auto sheet=std::find_if(zones.geometry.refs_by_sheet.begin(),
                zones.geometry.refs_by_sheet.end(),[&](const auto& row){
                    return std::find(row.second.begin(),row.second.end(),ref)!=row.second.end();
                });
            require(sheet!=zones.geometry.refs_by_sheet.end(),"edge connector belongs to a sheet");
            for(const auto* wrong:{"N","E","S","W"}) {
                if(edge==wrong)continue;
                auto bad=f.stage;
                const auto block=std::find_if(bad.plan.edge_blocks.begin(),bad.plan.edge_blocks.end(),
                    [&](const auto& b){return b.name==sheet->first;});
                require(block!=bad.plan.edge_blocks.end(),"edge connector has a planned block");
                block->edge=wrong;
                ExecutionFailureReceipt failure;
                bool rejected=false;
                try {place_pcb_model_accounted(f.input,zones,bad,
                    PcbZoneAccountingOwnership::IncludedInFloorplan,&failure);}
                catch(const PcbZoneInfeasible& e) {
                    rejected=std::string(e.what()).find("edge geometry mismatch:")!=std::string::npos;
                }
                require(rejected,"mismatched edge geometry must reject before connector seating");
                require(failure.captured&&!failure.unavailable,"edge rejection retains failure receipt");
                ++mismatches;
            }
        }
        require(mismatches>0,"edge mismatch negative cases exercised");
    }
    auto result = (mode == "--production" || single) ? build_pcb_model(f.input)
                                                     : place_pcb_model(f.input, zones, f.stage);
    // Historical coordinates are valid renderer operands, not an optimisation
    // target. Preserve the immutable emitter oracle separately below.
    placement_requirements_test::structure(f.input,zones,result,require);
    const auto expected=pcb_model_from_json(f.model,f.expected_pool);
    placement_requirements_test::physical(f.input,result.model,require);
    require(result.model.netclass_of==expected.netclass_of,name+" source net-class assignment");
    same(field(pcb_model_json(result.model),"classes"),field(f.model,"classes"),name+" source impedance classes");
    const auto check_structure=[&](auto mutate,const std::string& why) {
        auto changed=result;mutate(changed);
        bool rejected=false;
        try {placement_requirements_test::structure(f.input,zones,changed,require);}
        catch(const std::exception&) {rejected=true;}
        require(rejected,"mutation escaped: "+why);
    };
    check_structure([](auto& r){r.model.insts.pop_back();},"missing instance");
    check_structure([](auto& r){r.model.insts.push_back(r.model.insts.front());},"duplicate instance");
    check_structure([](auto& r){r.model.insts.front().x=-100.;},"off-board pose");
    check_structure([](auto& r){++r.model.n_top;},"incorrect side population");
    require(!result.floorplan.plan.interior_blocks.empty(),"registered-shape mutation witness");
    check_structure([](auto& r){r.floorplan.plan.interior_blocks.front().shape_idx=1000000;},
                    "unregistered shape index");
    check_structure([](auto& r){r.model.insts.front().value="WRONG";},"part value");
    check_structure([](auto& r){r.model.insts.front().mirror=!r.model.insts.front().mirror;},"mirror identity");
    check_structure([](auto& r){r.stages.at("breathe").erase(r.stages.at("breathe").begin());},"missing stage reference");
    check_structure([](auto& r){++r.model.stage_moves.at("breathe");},"incorrect movement ledger");
    check_structure([](auto& r){std::get<0>(r.stages.at("instantiate").begin()->second)+=1;},"movement in frozen stage");
    if(!single) {
        auto wrong=result.model;
        const auto connector=std::find_if(wrong.insts.begin(),wrong.insts.end(),[](const auto& p) {
            return p.value=="TYPE-C-31-M-12";
        });
        require(connector!=wrong.insts.end(),"mechanical orientation negative witness");
        connector->rotation+=180;
        require(!check_placement_mech(PcbCheckInput(wrong)).ok,"reversed connector must fail physical acceptance");
        wrong=result.model;wrong.copper.clear();
        bool rejected=false;
        try {placement_requirements_test::physical(f.input,wrong,require);}
        catch(const std::runtime_error&) {rejected=true;}
        require(rejected,"missing return copper must fail physical acceptance");
    }
    if(!single) {
        auto fixture_policy=pcb_emit_policy(f.input.floorplan.project);
        fixture_policy.model_overrides.clear();
        // This immutable renderer operand predates interface-only silkscreen.
        // Current generated boards below still use the current project policy.
        fixture_policy.interface_reference_labels_only=false;
        require(render_pcb(expected,fixture_policy).pcb==
                    read(root/"native/tests/data/pcb_emit"/(name+".kicad_pcb")),
                name+" immutable model still renders exact historical PCB bytes");
        require(render_pcb_design_rules(expected)==
                    read(root/"native/tests/data/pcb_emit"/(name+".kicad_dru")),
                name+" immutable design-rule formatter bytes");
    }
    // Repetition tests same-input reproducibility, not equality to a different
    // algorithm/version/seed. Emitted current PCB and full model must agree.
    const auto repeated=(mode=="--production"||single)?build_pcb_model(f.input):
        place_pcb_model(f.input,zones,f.stage);
    same(pcb_model_json(result.model),pcb_model_json(repeated.model),name+" same-input full model");
    require(result.stages==repeated.stages,name+" same-input stage sequence");
    same(floorplan_plan_json(result.floorplan.plan),floorplan_plan_json(repeated.floorplan.plan),
         name+" same-input floorplan and complete execution ledger");
    require(result.placement_accounting.quantization_engagements==repeated.placement_accounting.quantization_engagements&&
            result.placement_accounting.fallback_events==repeated.placement_accounting.fallback_events&&
            result.zone_accounting.quantization_engagements==repeated.zone_accounting.quantization_engagements&&
            result.zone_accounting.fallback_events==repeated.zone_accounting.fallback_events,
            name+" same-input actual placement/zone work");
    require(result.floorplan.documents.svg==repeated.floorplan.documents.svg&&
            result.floorplan.documents.markdown==repeated.floorplan.documents.markdown,
            name+" same-input generated floorplan documents");
    const auto policy=pcb_emit_policy(f.input.floorplan.project);
    require(render_pcb(result.model,policy).pcb==render_pcb(repeated.model,policy).pcb,
            name+" same-input emitted PCB");
    std::cout<<name<<(single?" top-preferred":" two-sided")
        <<": source identity, stage transport, repeatability and scoped physical acceptance PASS\n";
}
} // namespace
int main(int argc, char **argv) {
    try {
        std::string mode = argc == 3 ? argv[2] : "--production";
        if (argc < 2 || argc > 3 ||
            (mode != "--zones-only" && mode != "--production" && mode != "--placed-only" &&
             mode != "--single" && mode != "--rigid-groups-only"))
            throw std::runtime_error(
                "repo root [--zones-only|--production|--placed-only|--single|--rigid-groups-only]");
        if(mode=="--rigid-groups-only") {
            rigid_group_contracts(argv[1]);
            power_rigid_group_contracts(argv[1]);
            std::cout << "PCB rigid groups: " << checks << " assertions passed\n";
            return 0;
        }
        constraint_merge_contracts();
        rigid_group_contracts(argv[1]);
        power_rigid_group_contracts(argv[1]);
        for (const auto &name : {"carrier", "devkit_mini"}) {
            run(argv[1], name, mode);
            if (mode == "--production")
                run(argv[1], name, "--single");
        }
        std::cout << "PCB placement: " << checks << " assertions passed\n";
    } catch (const std::exception &e) {
        std::cerr << e.what() << "\n";
        return 1;
    }
}
