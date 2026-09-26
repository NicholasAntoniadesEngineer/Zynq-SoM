#include "schgen/procurement.hpp"
#include <cmath>
#include <iostream>
#include <limits>
#include <map>

namespace {
std::size_t checks=0;
void require(bool value,const std::string& why){++checks;if(!value)throw std::runtime_error(why);}
template<class F> void rejects(F fn){bool failed=false;try{fn();}catch(const std::exception&){failed=true;}require(failed,"expected rejection");}
}
int main(){using namespace schgen;try{
    for(long long need:{1,5,50,100})for(long long floor:{0,50,150})for(long long stock:{-1,0,1,3,49,50,99,100,1000}){
        const auto expected=stock<=0?"out":stock<need?"insufficient":stock<std::max(need,floor)?"low":"ok";
        require(assess_procurement_stock(stock,need,floor).first==expected,"stock boundary");
    }
    require(procurement_unit_price({},1)==0,"empty prices");
    require(procurement_unit_price({{10,2},{1,3}},0)==2,"first price below all tiers");
    require(procurement_unit_price({{10,2},{1,3}},5)==3,"sorted tiers");
    require(procurement_unit_price({{10,2},{1,3}},10)==2,"inclusive tier");
    rejects([]{procurement_unit_price({{1,-1}},1);});
    rejects([]{procurement_unit_price({{1,std::numeric_limits<double>::infinity()}},1);});
    const auto response=parse_json_text(R"({"data":{"componentPageInfo":{"list":[{"componentCode":"C1","componentModelEn":"R","componentBrandEn":"vendor","componentSpecificationEn":"0603","stockCount":"2","minPurchaseNum":10,"componentLibraryType":"base","componentPrices":[{"startNumber":1,"productPrice":"0.2"},{"startNumber":10,"productPrice":0.1}]}]}}})");
    const auto parsed=procurement_jlc_response(response,"C1");
    require(parsed&&parsed->stock==2&&parsed->min_qty==10&&parsed->library=="Basic"&&parsed->prices.size()==2,"JLC response");
    require(!procurement_jlc_response(response,"C2"),"absent component");
    require(procurement_lcsc_response(parse_json_text(R"({"code":200,"result":{"id":"C1"}})")),"catalog present");
    for(const auto* raw:{R"({"code":200,"result":{}})",R"({"code":200,"result":null})",R"({"code":500,"result":{"id":1}})"})require(!procurement_lcsc_response(parse_json_text(raw)),"catalog absent");
    rejects([]{procurement_jlc_response(parse_json_text(R"({"data":{"componentPageInfo":{"list":42}}})"),"C1");});
    rejects([]{procurement_jlc_response(parse_json_text(R"({"error":"service unavailable"})"),"C1");});
    rejects([]{procurement_lcsc_response(parse_json_text("{}"));});
    ProcurementInventory inventory{{{"C1","R",{"test:R1","test:R2"},{"C9"}},
        {"C2","X",{"test:R3"},{}},{"C3","Y",{"test:R4"},{}},{"C4","Z",{"test:R5"},{}}},{"test:R6 (missing)"}};
    ProjectCircuit source;source.name="test";source.circuit.name="test";
    const auto add=[&](const std::string& ref,const std::string& value,std::vector<CircuitFieldIr> fields){CircuitPartIr part;part.ref=ref;part.value=value;part.fields=std::move(fields);source.circuit.parts.push_back(std::move(part));};
    add("R7","excluded",{{"BOM","exclude"}});add("R6","missing",{});
    add("R5","Z",{{"LCSC","C4"}});add("R4","Y",{{"LCSC","C3"}});add("R3","X",{{"LCSC","C2"}});
    add("R2","R",{{"LCSC","C1"}});add("R1","R",{{"LCSC"," C1 "},{"ALT_LCSC"," C9,C9, "}});
    const auto collected=procurement_inventory({source});
    require(collected.missing==inventory.missing&&collected.items.size()==inventory.items.size(),"live inventory grouping");
    for(std::size_t i=0;i<inventory.items.size();++i){const auto& a=collected.items[i];const auto& b=inventory.items[i];require(a.lcsc==b.lcsc&&a.value==b.value&&a.refs==b.refs&&a.alternatives==b.alternatives,"ordered refs and unique alternatives");}
    std::map<std::string,ProcurementInfo> infos{
        {"C1",{"R","","","Extended",2,10,{{1,.2},{10,.1}}}},
        {"C9",{"alternate","","","Basic",100,1,{}}},
        {"C3",{"Y","","","Basic",20,1,{{1,1.25}}}},
        {"C4",{"Z","","","Extended",0,1,{{1,.5}}}}};
    ProcurementProvider provider{[&](const std::string& id)->std::optional<ProcurementInfo>{const auto it=infos.find(id);return it==infos.end()?std::nullopt:std::optional<ProcurementInfo>(it->second);},[](const std::string&){return true;}};
    const auto result=assess_procurement(inventory,provider,3);
    // Captured independently from the original Python command with the same
    // supplied inventory/provider responses. No network or native oracle used.
    const std::string expected=R"REPORT(preflight: 4 LCSC line item(s), 1 part(s) without an LCSC id, 3 board(s)
LCSC         MPN                      lib           stock  need   unit $    ext $  refs
---------------------------------------------------------------------------------------
C1           R                        Extended          2     6   0.1000   0.6000  test:R1,test:R2  ** INSUFFICIENT (stock 2 < need 6) **  -> 2nd source C9 OK (stock 100)
C2           X                        ?                 -     3        -        -  LCSC catalog only (not JLC assembly)
C3           Y                        Basic            20     3   1.2500   3.7500  test:R4  ** LOW STOCK (20 < floor 50) **
C4           Z                        Extended          0     3   0.5000   1.5000  test:R5  ** OUT OF STOCK **

TOTAL parts cost: $5.8500 for 3 board(s); Extended reels: 2 (+ JLC feeder fee each)
MISSING LCSC id (1):
  test:R6 (missing)
PROCUREMENT WARNINGS (2 — not fatal, review before a build):
  C1 (R): insufficient but covered by alternate C9 (stock 100)
  C3 (Y): LOW STOCK 20 < floor 50; no ALT_LCSC second source committed
PREFLIGHT: FAIL (2 availability problem(s))
  C2 (X): LCSC catalog only (not JLC assembly)
  C4 (Z): OUT
)REPORT";
    require(result.report==expected,"independent report bytes");
    require(!result.ok&&result.failures.size()==2&&result.warnings.size()==2&&result.extended_reels==2&&std::abs(result.cost-5.85)<1e-12,"result accounting");
    rejects([&]{assess_procurement(inventory,provider,0);});
    rejects([&]{assess_procurement(inventory,provider,std::numeric_limits<long long>::max());});
    auto unavailable=provider;unavailable.assembly=[](const std::string&)->std::optional<ProcurementInfo>{throw ProjectError("service unavailable");};
    rejects([&]{assess_procurement(inventory,unavailable);});
    require(assess_procurement({},provider).ok,"empty selected inventory");
    ProcurementInventory missing{{},{"test:R1"}};
    require(!assess_procurement(missing,provider).ok&&assess_procurement(missing,provider,1,50,true).ok,"explicit missing policy");
    auto healthy=inventory;healthy.items.resize(1);healthy.missing.clear();
    require(assess_procurement(healthy,provider,3).ok,"alternate covers shortage");
    healthy.items[0].alternatives.clear();require(!assess_procurement(healthy,provider,3).ok,"uncovered shortage fails");
    auto repeated=inventory;repeated.items[3].alternatives={"C9"};
    auto counted=provider;std::map<std::string,int> calls;
    counted.assembly=[&](const std::string& id){++calls[id];return provider.assembly(id);};
    assess_procurement(repeated,counted,3);
    require(calls["C9"]==1,"one consistent provider snapshot per identifier per assessment");
    rejects([]{live_procurement_provider(0);});
    // Invalid identifiers fail before any subprocess/network access.
    rejects([]{live_procurement_provider(20,"must-not-execute").assembly("C1&secret");});
    std::cout<<"Procurement: "<<checks<<" contracts passed\n";return 0;
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}}
