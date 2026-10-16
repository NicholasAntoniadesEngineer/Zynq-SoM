// Independent geometry and failure-accounting requirements for facing recovery.
#include "../src/floorplan_internal.hpp"
#include <iostream>
#include <stdexcept>
using namespace schgen;
void demand(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
int main(){try {
    int tested=0,misses=0;
    for(bool swap:{false,true})for(bool fx:{false,true})for(bool fy:{false,true})
    for(bool compact:{false,true})for(bool contradictory:{false,true})for(bool inset_pocket:{false,true})
    for(bool face_aware:{false,true}) {
        FloorplanLegalizeInput in;in.board_w=in.board_h=60;in.clear=.3;
        in.compact=compact;in.joint_separation_states=64;
        const auto box=[&](Box4 b) {
            if(swap){std::swap(b.x0,b.y0);std::swap(b.x1,b.y1);}
            if(fx){const double lo=60-b.x1;b.x1=60-b.x0;b.x0=lo;}
            if(fy){const double lo=60-b.y1;b.y1=60-b.y0;b.y0=lo;}
            return b;
        };
        const auto pose=[&](double x,double y){const auto b=box({x,y,x+2,y+2});return FloorplanPoint{b.x0,b.y0};};
        const auto target=pose(30,30),seed=pose(40,40),witness=pose(34,10);
        in.metrics["source"].offsets={{"out",fx?0.:2.,fy?0.:2.},{"in",fx?2.:0.,fy?2.:0.}};
        in.metrics["target"].offsets={{"p",1,1}};
        in.fixed_poses["target"]=target;
        in.fixed_rects={{"target",box({30,30,32,32})},
                        {"strip",box({0,0,33,28})},{"column",box({0,28,28,60})}};
        if(inset_pocket)in.fixed_rects.emplace_back("inset_strip",box({0,0,60,8}));
        if(face_aware) {
            for(const auto& [name,b]:in.fixed_rects){(void)b;in.primary_fanout[name]={{},{},1,1,std::vector<Comp>{}};}
            in.primary_fanout["source"]={{},{},1,1,std::vector<Comp>{}};
            in.fixed_rects.emplace_back("opposite_strip",box({0,0,60,55}));
            in.primary_fanout["opposite_strip"]={{},{},2,2,std::vector<Comp>{}};
        }
        FloorplanTerm term;term.kind="facing";term.subject="source";term.target_raw="target";
        term.enforced=true;term.require_positive_facing=true;term.out_refs={"out"};in.index.hard={term};
        if(contradictory){term.out_refs={"in"};in.index.hard.push_back(term);}
        const auto geometry_holds=[&](FloorplanPoint p) {
            const auto [x,y]=p;
            if(x<in.clear||y<in.clear||x+2>60-in.clear||y+2>60-in.clear)return false;
            for(const auto& [name,b]:in.fixed_rects) {
                if(face_aware&&!(in.primary_fanout.at(name).mask&1))continue;
                if(!(x>=b.x1+in.clear||x+2+in.clear<=b.x0||y>=b.y1+in.clear||y+2+in.clear<=b.y0))return false;
            }
            return true;
        };
        const auto facing_holds=[&](FloorplanPoint p) {
            const double dot=(fx?-1:1)*(target.first-p.first)+(fy?-1:1)*(target.second-p.second);
            if(dot<=0)return false;
            auto poses=in.fixed_poses;poses["source"]=p;
            for(const auto& row:floorplan_evaluate_terms(in,poses))if(!row.ok)return false;
            return true;
        };
        if(!contradictory)demand(geometry_holds(witness)&&facing_holds(witness),"invalid transformed witness");
        const auto initial=std::vector<FloorplanLegalizeVar>{{"source",2,2,seed,seed.first,seed.second}};
        int starts=0,ends=0;
        in.joint_retry_started=[&]{++starts;};
        in.joint_retry_completed=[&](const JointSeparationWork& work,bool) {
            ++ends;demand(work.visited<=work.generated&&work.generated<=64,"joint strategy exceeded declared work budget");
        };
        auto vars=initial;std::vector<std::string> log;QuantizationCounts counts;
        const bool accepted=floorplan_legalize_compact_accounted(in,vars,log,counts);
        demand(starts==ends,"lost joint completion callback");
        if(accepted) {
            demand(!contradictory,"opposing strict directions accepted");
            demand(geometry_holds({vars[0].x,vars[0].y})&&facing_holds({vars[0].x,vars[0].y}),"returned pose fails independent qualification");
        } else {
            demand(vars[0].x==seed.first&&vars[0].y==seed.second,"failure changed incumbent");
            if(!contradictory)++misses;
        }
        auto repeated=initial;std::vector<std::string> repeat_log;QuantizationCounts repeat_counts;
        const auto first_starts=starts;starts=ends=0;
        demand(floorplan_legalize_compact_accounted(in,repeated,repeat_log,repeat_counts)==accepted,"acceptance nondeterministic");
        demand(repeated[0].x==vars[0].x&&repeated[0].y==vars[0].y&&repeat_log==log&&repeat_counts==counts&&
               starts==ends&&starts==first_starts,"geometry, receipts or callbacks nondeterministic");
        if(accepted) {
            in.compact=false;
            auto settled=vars;settled[0].seed={settled[0].x,settled[0].y};
            std::vector<std::string> settled_log;starts=ends=0;
            demand(floorplan_legalize_compact(in,settled,settled_log),"valid incumbent rejected");
            demand(settled[0].x==vars[0].x&&settled[0].y==vars[0].y&&starts==0&&ends==0,
                   "valid incumbent moved or unnecessarily entered joint retry");
            for(const auto& line:settled_log)
                demand(line.find("capacity allocation")==std::string::npos,"valid incumbent entered projection fallback");
        }
        ++tested;
    }
    for(bool vertical:{false,true}) {
        FloorplanLegalizeInput in;in.board_w=in.board_h=60;in.joint_separation_states=64;
        in.metrics["source"].offsets={{"out",vertical?1.:2.,vertical?2.:1.},
                                    {"in",vertical?1.:0.,vertical?0.:1.}};
        in.metrics["target"].offsets={{"p",1,1}};
        in.fixed_poses["target"]={30,30};in.fixed_rects={{"target",{30,30,32,32}}};
        FloorplanTerm term;term.kind="facing";term.subject="source";term.target_raw="target";
        term.enforced=true;term.require_positive_facing=true;term.out_refs={"out"};in.index.hard={term};
        term.out_refs={"in"};in.index.hard.push_back(term);
        int starts=0,ends=0;
        in.joint_retry_started=[&]{++starts;};
        in.joint_retry_completed=[&](const JointSeparationWork&,bool){++ends;};
        std::vector<FloorplanLegalizeVar> vars{{"source",2,2,{20,20},20,20}};
        std::vector<std::string> log;
        demand(!floorplan_legalize_compact(in,vars,log),"axial contradiction accepted");
        int allocations=0;for(const auto& line:log)if(line.find("capacity allocation")!=std::string::npos)++allocations;
        demand(allocations==1&&starts==3&&ends==starts,"identical allocation constraints repeated a solver trial or lost work boundaries");
        demand(vars[0].x==20&&vars[0].y==20,"deduplicated failure changed seed");
        // A guarded proximity term between fixed endpoints changes no moving
        // constraint. It must not cause both joint solves to run a second time.
        FloorplanTerm fixed_near;fixed_near.kind="near_max";fixed_near.subject="target";
        fixed_near.target_raw="target";fixed_near.bound=5;fixed_near.enforced=true;
        in.index.hard.push_back(fixed_near);
        in.metrics["target"].pad_union={{"p",0,0,2,2}};
        starts=ends=0;log.clear();
        demand(!floorplan_legalize_compact(in,vars,log)&&starts==3&&ends==starts,
               "fixed-only proximity repeated equivalent full-envelope solves");
        in.index.hard.back().subject="source";
        in.metrics["source"].pad_union={{"out",0,0,2,2}};
        starts=ends=0;log.clear();
        demand(!floorplan_legalize_compact(in,vars,log)&&starts==5&&ends==starts,
               "distinct moving proximity bounds were incorrectly deduplicated");
    }
    {
        FloorplanLegalizeInput in;in.board_w=in.board_h=60;in.clear=.3;in.compact=true;in.joint_separation_states=64;
        in.fixed_poses["target"]={30,30};in.metrics["target"].offsets={{"p",1,1}};
        in.fixed_rects={{"target",{30,30,32,32}},{"a_strip",{0,0,33,28}},
            {"a_column",{0,28,28,60}},{"b_strip",{0,0,28,33}},{"b_row",{28,0,60,28}}};
        for(const auto& name:{"a","b"}) {
            in.metrics[name].offsets={{"out",2,2},{"in",0,0}};
            FloorplanTerm term;term.kind="facing";term.subject=name;term.target_raw="target";
            term.enforced=true;term.require_positive_facing=true;term.out_refs={"out"};in.index.hard.push_back(term);
        }
        for(const auto& [name,mask]:std::vector<std::pair<std::string,int>>{
            {"a",1},{"b",2},{"target",3},{"a_strip",1},{"a_column",1},{"b_strip",2},{"b_row",2}})
            in.primary_fanout[name]={{},{},mask,mask,std::vector<Comp>{}};
        const auto valid=[&](const std::vector<FloorplanLegalizeVar>& vars) {
            Occupancy occ(60,60,.3,2,0,1,.05);
            for(const auto& [name,b]:in.fixed_rects)
                occ.add(b.x0,b.y0,b.x1-b.x0,b.y1-b.y0,{},{},in.primary_fanout.at(name).mask,{});
            auto poses=in.fixed_poses;
            for(const auto& v:vars) {
                const int face=in.primary_fanout.at(v.name).mask;
                if(!occ.fits_exhaustive(v.x,v.y,2,2,{},{},face,{}))return false;
                occ.add(v.x,v.y,2,2,{},{},face,{});poses[v.name]={v.x,v.y};
                if((30-v.x)+(30-v.y)<=0)return false;
            }
            for(const auto& row:floorplan_evaluate_terms(in,poses))if(!row.ok)return false;
            return true;
        };
        demand(valid({{"a",2,2,{40,.3},40,.3},{"b",2,2,{.3,40},.3,40}}),"mixed allocation witness invalid");
        const std::vector<FloorplanLegalizeVar> seed{{"a",2,2,{40,40},40,40},{"b",2,2,{40,40},40,40}};
        int starts=0,ends=0;
        in.joint_retry_started=[&]{++starts;};
        in.joint_retry_completed=[&](const JointSeparationWork& w,bool){++ends;demand(w.generated<=64&&w.visited<=w.generated,"mixed allocation exceeded work budget");};
        auto vars=seed;std::vector<std::string> log;QuantizationCounts counts;
        demand(floorplan_legalize_compact_accounted(in,vars,log,counts)&&valid(vars),"mixed per-term facing allocations missed a known feasible layout");
        demand(starts==ends,"mixed allocation lost a completion callback");
        const auto original_starts=starts;starts=ends=0;
        auto repeated=seed;std::vector<std::string> repeated_log;QuantizationCounts repeated_counts;
        demand(floorplan_legalize_compact_accounted(in,repeated,repeated_log,repeated_counts)&&valid(repeated)&&
               log==repeated_log&&counts==repeated_counts&&starts==ends&&starts==original_starts,
               "mixed allocation receipts or callbacks not reproducible");
        for(std::size_t i=0;i<vars.size();++i)demand(vars[i].x==repeated[i].x&&vars[i].y==repeated[i].y,"mixed poses not reproducible");
        std::reverse(in.index.hard.begin(),in.index.hard.end());vars=seed;log.clear();
        demand(floorplan_legalize_compact(in,vars,log)&&valid(vars),"mixed allocation depends on facing term order");
        auto contradiction=in.index.hard.front();contradiction.out_refs={"in"};in.index.hard.push_back(contradiction);
        vars=seed;log.clear();demand(!floorplan_legalize_compact(in,vars,log),"mixed allocation accepted a strict contradiction");
        demand(starts==ends,"mixed contradiction lost a completion callback");
        for(std::size_t i=0;i<vars.size();++i)demand(vars[i].x==seed[i].x&&vars[i].y==seed[i].y,"mixed failure mutated seed");
    }
    std::cout<<"cases="<<tested<<" known_feasible_misses="<<misses<<" mixed_per_term_case=PASS\n";
    return misses?1:0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}}
