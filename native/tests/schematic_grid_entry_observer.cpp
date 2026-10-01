// Test-only instrumented quantize.cpp calls these hooks. There is no global
// counter/sink: raw entry events go to the child's captured stderr pipe.
#include "schgen/schematic_place.hpp"
#include "schgen/board_schematic.hpp"
#include "schgen/quantize.hpp"
#include "schgen/process.hpp"
#include <cstdio>
#include <iostream>
#include <sstream>

extern "C" void __cyg_profile_func_enter(void* function, void*) {
    if (function == reinterpret_cast<void*>(&schgen::gsnap)) std::fputs("ENTRY gsnap\n",stderr);
    else if (function == reinterpret_cast<void*>(&schgen::gfloor)) std::fputs("ENTRY gfloor\n",stderr);
    else if (function == reinterpret_cast<void*>(&schgen::gceil)) std::fputs("ENTRY gceil\n",stderr);
}
extern "C" void __cyg_profile_func_exit(void*, void*) {}

int schematic_grid_observe(const std::filesystem::path& repo) {
    using namespace schgen;
    SymbolLibrary lib(std::vector<std::filesystem::path>{
        repo/"native/tests/data/symbols/kicad",repo/"schgen/lib",repo/"parts"});
    const auto fixtures=parse_json_file((repo/"native/tests/data/schematic_place_pages/full_pages.json").string());
    const auto* cases=object_field(fixtures,"cases");
    if(!cases || cases->array_value.empty())throw std::runtime_error("missing entry fixtures");
    for(const auto& record:cases->array_value) {
        const auto* ir=object_field(record,"circuit");
        if(!ir)throw std::runtime_error("missing circuit");
        const auto original=parse_circuit_ir(*ir);
        // Ordinary success, no attempts, and a structural failure after the
        // placement/probe prefix. No estimated/replayed production counts.
        for(int scenario=0;scenario<3;++scenario) {
            auto c=original;
            if(scenario==2) {
                CircuitPartIr p; p.ref="ZZ_RECEIPT_PROBE";p.lib_id="Connector:TestPoint";p.value="unnetted";
                c.parts.push_back(p);
            }
            std::cerr<<"BEGIN "<<c.name<<":"<<scenario<<"\n";
            QuantizationCounts counts;
            bool success=false;
            try {
                const auto page=place_and_route_schematic(c,lib,{},scenario==1?0:8,&counts);
                SchematicDesign d;d.circuit=c;d.parts=page.placement.parts;d.powers=page.placement.powers;
                d.hlabels=page.placement.hlabels;d.llabels=page.placement.llabels;
                d.no_connects=page.placement.no_connects;d.paper=page.placement.paper;
                apply_schematic_route(d,page.routed);
                make_board_hierarchy({{d,1}},lib,"entry_oracle",{},&counts);
                success=true;
            }
            catch(const std::exception&) {}
            for(const auto& [name,count]:counts)std::cerr<<"RECEIPT "<<name<<" "<<count<<"\n";
            std::cerr<<"END\n";
            if(success!=(scenario==0))throw std::runtime_error("unexpected scenario outcome");
        }
    }
    return 0;
}
void verify_schematic_grid_entries(const std::string& executable,const std::filesystem::path& repo) {
    using namespace schgen;
    const auto child=run_process({executable,repo.string(),"--observe"},std::chrono::seconds{60});
    if(child.exit_code)throw std::runtime_error("entry child failed: "+child.stderr_text);
    std::istringstream stream(child.stderr_text);
    QuantizationCounts observed,receipts;
    std::string line,case_name;
    bool inside=false;std::size_t cases=0,entries=0;
    while(std::getline(stream,line)) {
        std::istringstream row(line);std::string tag,name;row>>tag;
        if(tag=="BEGIN") {
            if(inside)throw std::runtime_error("nested entry case");
            row>>case_name;inside=true;observed.clear();receipts.clear();
        } else if(tag=="ENTRY") {
            if(!inside)throw std::runtime_error("unowned scalar entry");
            row>>name;++observed[name];++entries;
        } else if(tag=="RECEIPT") {
            std::size_t n;row>>name>>n;
            if(!inside||!receipts.emplace(name,n).second)throw std::runtime_error("duplicate receipt");
        } else if(tag=="END") {
            if(!inside||observed!=receipts)throw std::runtime_error("independent entry mismatch: "+case_name);
            inside=false;++cases;
        } else if(!line.empty())throw std::runtime_error("unexpected observer output: "+line);
    }
    if(inside||cases<3||entries==0)throw std::runtime_error("entry coverage incomplete");
    std::cout<<cases<<" independent real-entry scenarios; "<<entries<<" exact observed scalars\n";
}
