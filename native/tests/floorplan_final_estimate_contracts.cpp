#include "pcb_placement_fixture.hpp"
#include "experiment_metric_contracts.hpp"
#include "floorplan_internal.hpp"
#include <array>
#include <iostream>

namespace {
using namespace schgen;
void require(bool ok,const std::string& why) { if(!ok) throw std::runtime_error(why); }
double value(const FloorplanDecision& d,const std::string& key) {
    for(const auto& [name,v]:d.inputs) if(name==key) return v.number_value;
    throw std::runtime_error("missing decision input "+key);
}
void verify(const FloorplanInput& input,const FloorplanPlan& result,
            const std::array<FloorplanPlan,2>& passes) {
    std::array<double,2> estimates{};
    for(std::size_t pass=0;pass<2;++pass)
        estimates[pass]=experiment_metric_contracts::estimate(input,passes[pass]);
    const double final=experiment_metric_contracts::estimate(input,result);
    int pass_count=0,choice_count=0,winner_count=0;
    for(const auto& decision:result.accounting.decisions) {
        if(decision.name=="pass_winner") {
            require(pass_count<2,"too many pass winners");
            require(value(decision,"est_cross")==estimates[pass_count],"pass winner uses stale screening estimate");
            ++pass_count;
        }
        if(decision.name=="plan_choice") {
            ++choice_count;
            require(value(decision,"conservative_est")==estimates[0] &&
                    value(decision,"free_est")==estimates[1],"pass comparison uses stale estimates");
        }
        if(decision.name=="sizing_winner") {
            ++winner_count;
            require(value(decision,"est_cross")==final,"final winner uses stale screening estimate");
            require(std::abs(value(decision,"headroom")-(value(decision,"budget")-final))<1e-9,
                    "winner headroom disagrees with final estimate");
            require(std::isfinite(final)&&final>=0,"invalid final airwire metric");
        }
    }
    require(pass_count==2&&choice_count==1&&winner_count==1,"complete automatic sizing decisions");
}
} // namespace
int main(int argc,char** argv) {
    try {
        require(argc==2,"usage: final-estimate REPOSITORY");
        using floorplan_detail::OutlineCandidate;
        using floorplan_detail::prefer_outline;
        const OutlineCandidate smaller{90,10,9,1000000,1},larger{100,10,10,0,1000000};
        require(prefer_outline(smaller,larger)&&!prefer_outline(larger,smaller),
                "wire quality must never outrank smaller area");
        const OutlineCandidate narrow{100,10,10,200,1000},shorter_wire{100,20,5,100,1};
        require(prefer_outline(shorter_wire,narrow)&&!prefer_outline(narrow,shorter_wire),
                "equal-area candidates must prefer lower wire estimate before dimensions");
        auto changed_reference=shorter_wire;std::get<4>(changed_reference)=999999;
        require(!prefer_outline(shorter_wire,changed_reference)&&!prefer_outline(changed_reference,shorter_wire),
                "advisory reference must not affect ranking");
        auto tied=narrow;std::get<3>(tied)=100;
        require(prefer_outline(tied,shorter_wire)&&!prefer_outline(tied,tied),
                "dimensions must deterministically break equal quality ties");
        auto fixture=placement_fixture::load(argv[1],"devkit_mini");
        for(bool multiscale:{false,true})for(bool compact:{false,true})for(bool seeded:{false,true}) {
            fixture.input.floorplan.compact_search=compact;
            const auto zones=build_pcb_zone_geometry(fixture.input);
            auto input=prepare_pcb_floorplan(fixture.input,zones);
            // A deliberately tiny advisory reference must not exclude valid geometry.
            input.cross_budget_k=0.000001;
            require(!input.spec || !input.spec->outline,"automatic outline witness");
            std::array<FloorplanPlan,2> passes;
            std::array<int,2> observed{};
            auto observer=std::make_shared<FloorplanExperiment>();
            observer->multiscale_outline=multiscale;
            if(seeded)observer->initial_outline={{98,98}};
            input.experiment=observer;
            floorplan_detail::Engine engine(input);
            observer->unscoped_estimate=[&](double) {
                const std::size_t pass=engine.plan.punch_free?1:0;
                passes[pass]=engine.plan;
                ++observed[pass];
            };
            const auto result=engine.run();
            require(observed[0]>0&&observed[1]>0,"both real passes observed");
            verify(input,result,passes);
            require(experiment_metric_contracts::estimate(input,result)>1,
                    "witness must exceed the deliberately tiny advisory reference");
            for(const auto* name:{"pass_winner","plan_choice","sizing_winner"}) {
                auto changed=result;
                bool altered=false;
                for(auto& d:changed.accounting.decisions) if(d.name==name&&!altered) {
                    for(auto& [key,v]:d.inputs) if(key=="est_cross"||key=="conservative_est") {
                        v.number_value+=1;altered=true;break;
                    }
                }
                require(altered,"negative control finds ledger input");
                bool rejected=false;
                try{verify(input,changed,passes);}catch(const std::runtime_error&){rejected=true;}
                require(rejected,"stale/mutated ledger value escaped");
            }
            std::cout<<"final estimate multiscale="<<multiscale<<" compact="<<compact<<" seeded="<<seeded<<" actual="
                <<experiment_metric_contracts::estimate(input,result)<<" PASS\n";
        }
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
