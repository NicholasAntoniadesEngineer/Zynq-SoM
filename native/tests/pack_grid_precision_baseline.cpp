// Preserve the original transport; candidate removes only the three reviewed
// precision families and the independently proven initial-ledger +2 correction.
// Compare stdout byte-for-byte. Never regenerate existing frozen fixtures.
#include "pcb_placement_fixture.hpp"
#include "floorplan_precision_fixture.hpp"
#include "schgen/pcb_emit.hpp"
#ifdef PACK_GRID_CANDIDATE
#include "pack_grid_precision_fixture.hpp"
#include "pack_search_precision_fixture.hpp"
#include "pack_plain_precision_fixture.hpp"
#include "ledger_accounting_fixture.hpp"
#endif
#include <iostream>
#include <iomanip>
using namespace schgen;
int main(int argc,char** argv){try {
    if(argc!=2)throw std::runtime_error("repository root required");
    for(const auto* name:{"carrier","devkit_mini"}) {
        const auto f=placement_fixture::load(argv[1],name);
        auto result=build_pcb_model(f.input);
        const auto emitted=render_pcb(result.model,pcb_emit_policy(f.input.floorplan.project));
        auto q=pcb_placement_accounting(result).quantization_engagements;
        checked_quantization_merge(q,emitted.quantization_engagements);
#ifdef PACK_GRID_CANDIDATE
        q=pack_plain_precision_fixture::select(pack_search_precision_fixture::select(pack_grid_precision_fixture::select(q,false),false),false);
        q=ledger_accounting_fixture::before_initial_receipt_fix(q);
#endif
        std::cout<<name<<'\n'<<std::hexfloat;
        floorplan_precision_fixture::node(std::cout,pcb_model_json(result.model));
        std::cout<<emitted.pcb.size()<<'\n'<<emitted.pcb;
        for(const auto& diagnostic:emitted.diagnostics)std::cout<<std::quoted(diagnostic)<<'\n';
        std::cout<<result.floorplan.documents.svg.size()<<'\n'<<result.floorplan.documents.svg;
        std::cout<<result.floorplan.documents.markdown.size()<<'\n'<<result.floorplan.documents.markdown;
        for(const auto& [key,n]:q)std::cout<<std::quoted(key)<<' '<<n<<'\n';
    }
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
