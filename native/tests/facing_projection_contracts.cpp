// Independent geometry and failure-accounting requirements for facing recovery.
#include "../src/floorplan_internal.hpp"
#include <iostream>
#include <stdexcept>
using namespace schgen;
void demand(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
int main(){try {
    int tested=0,misses=0;
    for(bool swap:{false,true})for(bool fx:{false,true})for(bool fy:{false,true})
    for(bool compact:{false,true})for(bool contradictory:{false,true}) {
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
        FloorplanTerm term;term.kind="facing";term.subject="source";term.target_raw="target";
        term.enforced=true;term.require_positive_facing=true;term.out_refs={"out"};in.index.hard={term};
        if(contradictory){term.out_refs={"in"};in.index.hard.push_back(term);}
        const auto geometry_holds=[&](FloorplanPoint p) {
            const auto [x,y]=p;
            if(x<in.clear||y<in.clear||x+2>60-in.clear||y+2>60-in.clear)return false;
            for(const auto& [name,b]:in.fixed_rects) {
                (void)name;
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
    std::cout<<"cases="<<tested<<" known_feasible_misses="<<misses<<"\n";
    return misses?1:0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}}
