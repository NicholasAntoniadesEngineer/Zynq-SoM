// Include the owned implementation to verify its private accounted evaluator.
// Link schgen_core; do not additionally compile floorplan_compose.cpp here.
#include "../src/floorplan_compose.cpp"
#include <iostream>

namespace {
using namespace schgen;
int checks=0;
void require(bool b,const char* msg) {++checks;if(!b)throw std::runtime_error(msg);}
FloorplanLegalizeInput input(bool subject_guard=false) {
    FloorplanLegalizeInput in;in.board_w=in.board_h=120;
    in.som_core_page={70,70,80,80};
    const std::string subject=subject_guard?"ethernet":"power";
    const std::string target=subject_guard?"other":"power_som";
    in.metrics[subject].offsets={{"U",2,2},{"C",1,2}};
    in.metrics[subject].zone_wh={4,4};
    in.metrics[target].offsets={{"T",1,2}};
    in.metrics[target].zone_wh={4,4};
    in.fixed_poses[target]={70,20};
    in.fixed_rects={{target,{70,20,74,24}}};
    FloorplanTerm facing;
    facing.kind="facing";facing.sheet=subject;facing.subject=subject;facing.target_raw=target;
    facing.enforced=true;facing.out_refs={"C"};
    in.index.hard={facing};return in;
}
FloorplanOffsets positions(const FloorplanLegalizeInput& in) {
    auto p=in.fixed_poses;
    if(!in.index.hard.empty())p[in.index.hard.front().subject]={20,20};
    return p;
}
void oracle(const FloorplanLegalizeInput& in) {
    const auto poses=positions(in);
    QuantizationCounts actual_counts{{"unrelated",7}},expected_counts=actual_counts;
    const auto actual=schgen::evaluate(in,poses,&actual_counts);
    std::vector<EvalMetric> metrics;
    for(const auto& [name,m]:in.metrics)metrics.push_back({name,m.offsets,m.pad_union});
    std::vector<FloorplanTerm> terms=in.index.hard;
    terms.insert(terms.end(),in.index.soft.begin(),in.index.soft.end());
    require(actual.size()==terms.size(),"row population");
    for(std::size_t k=0;k<terms.size();++k) {
        const auto& t=terms[k];
        const bool strict=t.enforced && t.kind=="facing" && t.require_positive_facing;
        const std::vector<std::pair<std::string,double>> guards=strict?
            std::vector<std::pair<std::string,double>>{}:
            std::vector<std::pair<std::string,double>>{{"ethernet",14},{"power_som",25}};
        const auto expected=evaluate_terms(in.board_w,in.board_h,in.som_core_page,
            {poses.begin(),poses.end()},metrics,{{t.kind,t.subject,t.target(),t.bound.value_or(0),t.bound.has_value(),t.out_refs}},
            guards,{},in.origin.first,in.origin.second,&expected_counts).at(0);
        const auto& a=actual[k];
        require(a.measured==expected.measured && a.bound==expected.bound && a.margin==expected.margin &&
                a.ok==expected.ok && a.note==expected.note,"per-row oracle/order/non-facing guard mismatch");
        require(a.term.kind==t.kind && a.term.subject==t.subject &&
                a.term.require_positive_facing==t.require_positive_facing,"metadata/order lost");
    }
    require(actual_counts==expected_counts,"actual accounted work differs from once-per-row scalar oracle");
}
void tests() {
    for(bool subject_guard:{false,true}) {
        auto legacy=input(subject_guard);
        const auto old=floorplan_evaluate_terms(legacy,positions(legacy)).at(0);
        require(old.ok && old.margin<0 && old.note.find("gate-arbitrated")!=std::string::npos,
                "legacy false-green witness disappeared");
        oracle(legacy);
        auto strict=legacy;strict.index.hard.front().require_positive_facing=true;
        const auto now=floorplan_evaluate_terms(strict,positions(strict)).at(0);
        require(!now.ok && now.measured==old.measured && now.margin==old.margin &&
                now.note.find("gate-arbitrated")==std::string::npos,"strict guard endpoint not enforced");
        oracle(strict);
        for(bool compact:{false,true}) {
            strict.compact=compact;
            const auto& t=strict.index.hard.front();
            std::vector<FloorplanLegalizeVar> vars{{t.subject,4,4,{20,20},20,20}};
            QuantizationCounts counts;std::vector<std::string> log;
            require(!floorplan_legalize_compact_accounted(strict,vars,log,counts),
                    "strict facing bypassed by compaction mode/fallback");
            require(vars.front().x==20 && vars.front().y==20,"rejected legalization mutated incumbent");
            require(!counts.empty(),"rejected work receipts dropped");
            require(!log.empty() && log.back().find("hard red")!=std::string::npos,"wrong rejection reason");
        }
        auto positive=strict;
        std::get<1>(positive.metrics.at(positive.index.hard.front().subject).offsets[1])=3;
        require(floorplan_evaluate_terms(positive,positions(positive)).at(0).ok,"positive facing rejected");
        oracle(positive);
        auto perpendicular=strict;
        auto& offsets=perpendicular.metrics.at(perpendicular.index.hard.front().subject).offsets;
        offsets={{"U",2,1},{"C",2,3}};
        require(!floorplan_evaluate_terms(perpendicular,positions(perpendicular)).at(0).ok,"zero-dot accepted");
        auto unknown=strict;unknown.metrics.erase(unknown.index.hard.front().target());
        require(!floorplan_evaluate_terms(unknown,positions(unknown)).at(0).ok,"unresolved strict target accepted");
        // Interleave legacy/non-facing rows with strict facing. A stray flag
        // on a different term must not erase its far/flow guard.
        auto mixed=strict;
        auto far=mixed.index.hard.front();far.kind="far_min";far.bound=10;
        auto flow=far;flow.kind="flow_hop";flow.bound.reset();
        mixed.index.hard={far,mixed.index.hard.front(),flow};
        auto soft=legacy.index.hard.front();soft.enforced=false;soft.require_positive_facing=true;
        mixed.index.soft={soft};
        oracle(mixed);
        const auto values=floorplan_evaluate_terms(mixed,positions(mixed));
        const auto guard=subject_guard?14:25;
        require(values[0].bound==10+guard,"far clearance guard removed");
        require(values[2].note.find("L4")!=std::string::npos,"flow guard removed");
        require(values[3].ok && values[3].note.find("gate-arbitrated")!=std::string::npos,
                "non-enforced legacy term semantics changed");
    }
    auto empty=input();empty.index={};oracle(empty);
}
}
int main() {
    try {tests();std::cout<<"PASS "<<checks<<" strict-facing, fallback, legacy and accounted mixed-row checks\n";}
    catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
