#include "pcb_placement_internal.hpp"
#include "schgen/legalize.hpp"
#include <iomanip>
#include <iostream>

namespace {
using namespace schgen;
using namespace schgen::pcb_placement;
void require(bool p,const std::string& message){if(!p)throw std::runtime_error(message);}
struct Fixture {
    PcbPlacementInput in;
    PcbZoneResult zones;
    FloorplanStage stage;
    std::unique_ptr<Placer> p;
    explicit Fixture(bool compact){
        in.floorplan.compact_search=compact;
        stage.plan.board_w=120;stage.plan.board_h=120;
        stage.plan.som_x=90;stage.plan.som_y=90;
        p=std::make_unique<Placer>(in,zones,stage);
    }
    void part(const std::string& ref,const std::string& sheet,const std::string& side,
              double x,double y,bool tht=false,bool fixed=false,int np=0){
        std::string bytes="(footprint \"probe\" (layer \"F.Cu\")";
        for(int k=1;k<=(np?np:fixed?2:3);++k)
            bytes+=" (pad \""+std::to_string(k)+"\" "+(tht?"thru_hole":"smd")+
                " circle (at "+std::to_string((k-2)*0.3)+" 0) (size 0.2 0.2) "+
                (tht?"(drill 0.1) (layers \"*.Cu\" \"*.Mask\")":"(layers \"F.Cu\" \"F.Mask\")")+")";
        bytes+=")";
        p->ctx.by_ref[ref]={ref,ref,sheet,"probe","probe","probe"};
        p->ctx.pool[ref]=pcb_check_footprint(ref,bytes);
        p->geometry.resolvable[ref]=ref;
        p->geometry.bbox_of[ref]={-.5,-.5,.5,.5};
        p->geometry.side_of[ref]=side;
        if(fixed)p->geometry.conn_edge[ref]="left";
        p->pos[ref]={x,y};
    }
};
void show(const std::string& title,Fixture& f){
    f.p->breathe("A");std::cout<<title;
    for(const auto& [r,p]:f.p->pos)std::cout<<" "<<r<<"="<<p.first<<","<<p.second;
    std::cout<<"\n";
    if(!f.in.floorplan.compact_search){
        for(const auto& [name,count]:f.p->ctx.quantization)std::cout<<name<<"="<<count<<" ";
        std::cout<<"\n";
    }
}
}
int main(int argc,char** argv){try{
    std::cout<<std::setprecision(17);
    const bool legacy_only=argc==2 && std::string(argv[1])=="--legacy-only";
    require(argc==1 || legacy_only,"usage: compact_breathe_tht_contracts [--legacy-only]");
    if(!legacy_only)
        for(bool compact:{false,true})for(bool reverse:{false,true})for(int kind:{0,1,2,3}) {
            const std::string own=reverse?"bottom":"top",opposite=reverse?"top":"bottom";
            Fixture rounding(compact);
            rounding.part("U1","rounding",own,60,60,kind==1);
            rounding.part("C1","rounding",kind==0?own:opposite,61.500041,60,kind==2,false,2);
            rounding.part("J1","fixed",own,58,60,false,true);
            rounding.p->geometry.bbox_of["C1"]={-.50004,-.5,.50004,.5};
            const auto entry=rounding.p->pos;
            const auto before=rect_gap(rounding.p->box("U1",entry.at("U1")),
                                       rounding.p->box("C1",entry.at("C1")));
            require(before>=rounding.in.floorplan.place_clear,"rounding fixture must start legal");
            show(std::string(compact?"compact":"default")+" rounded clearance "+own+" kind="+std::to_string(kind),rounding);
            if(kind!=3) {
                require(rect_gap(rounding.p->box("U1",rounding.p->pos.at("U1")),
                                 rounding.p->box("C1",rounding.p->pos.at("C1")))>=rounding.in.floorplan.place_clear,
                        "final per-member rounding must not violate internal group clearance");
                require(rounding.p->pos==entry,"rejected rounded commit must preserve every member");
            } else {
                require(rounding.p->pos.at("U1").first>60,
                        "opposite SMD faces must not acquire internal clearance coupling");
            }
            const auto receipt=rounding.p->ctx.quantization.find("breathe_commit_precision");
            const auto commits=receipt==rounding.p->ctx.quantization.end()?0:receipt->second;
            require(commits==(!compact && reverse && kind==2?0u:4u),
                    "actual rounded trial counts must survive rejection");
        }
    for(bool compact:{false,true}){
        if(compact && legacy_only)continue;
        for(bool reverse:{false,true})for(int kind:{0,1,2}){
            const std::string own=reverse?"bottom":"top",opposite=reverse?"top":"bottom";
            Fixture f(compact);
            f.part("U1","move",own,60,60,kind==1);
            f.part("J1","fixed",own,58,60,false,true);
            f.part("J2","back",opposite,62.5,60,kind==0,true);
            const auto source=f.p->ctx.pool.at("U1")->bytes;
            show(std::string(compact?"compact ":"default ")+own+" kind="+std::to_string(kind),f);
            if(compact && kind!=2)
                require(rect_gap(f.p->box("U1",f.p->pos.at("U1")),f.p->box("J2",f.p->pos.at("J2")))>=f.in.floorplan.place_clear,
                        "cross-face through-hole clearance violated");
            if(kind==2)require(f.p->pos.at("U1").first==61.36,"opposite-face SMD must not gain a through-hole shadow");
            require(f.p->pos.at("J1")==FloorplanPoint{58,60} && f.p->pos.at("J2")==FloorplanPoint{62.5,60},"fixed parts moved");
            require(f.p->side("U1")==own && f.p->rot("U1")==0 && f.p->ctx.pool.at("U1")->bytes==source,"breathe changed side/rotation/source geometry");
        }
        for(bool reverse:{false,true})for(bool chase:{false,true}){
            const std::string own=reverse?"bottom":"top",opposite=reverse?"top":"bottom";
            Fixture f(compact);
            f.part("U1","first",own,60,60,true);
            f.part("J1","fixed1",own,58,60,false,true);
            f.part("U2","second",opposite,chase?57:64.5,60);
            f.part("J2","fixed2",opposite,chase?55:66.5,60,false,true);
            show(std::string(compact?"compact ":"default ")+own+(chase?" vacated shadow":" new shadow"),f);
            if(compact){
                require(f.p->pos.at("U1").first==61.36,"first THT group must move before opposite group");
                if(chase)require(f.p->pos.at("U2").first>58,"vacated through-hole shadow still blocks later group");
                require(rect_gap(f.p->box("U1",f.p->pos.at("U1")),f.p->box("U2",f.p->pos.at("U2")))>=f.in.floorplan.place_clear,"restamped through-hole shadow missing at new pose");
            }
        }
        for(bool reverse:{false,true}){
            const std::string own=reverse?"bottom":"top",opposite=reverse?"top":"bottom";
            Fixture mixed(compact);
            mixed.part("U1","mixed",own,60,60,true);
            mixed.part("C1","mixed",opposite,60,64,false,false,2);
            mixed.part("J1","fixed",own,58,60,false,true);
            show(std::string(compact?"compact ":"default ")+own+" mixed-side rigid group",mixed);
            require(mixed.p->pos.at("U1").first==61.36,"mixed group did not move");
            require(mixed.p->pos.at("C1").first==mixed.p->pos.at("U1").first &&
                    std::abs(mixed.p->pos.at("C1").second-mixed.p->pos.at("U1").second-4)<1e-12,
                    "mixed group lost rigid offsets");
            if(compact)require(mixed.p->ctx.quantization.at("breathe_stamp_index")==88,
                               "mixed group must add/remove each own and cross-face reservation exactly once");
            Fixture blocked(compact);
            blocked.part("U1","move",own,60,60,true);
            blocked.part("J1","fixed",own,58,60,false,true);
            blocked.part("J2","back",opposite,61.75,60,false,true);
            show(std::string(compact?"compact ":"default ")+own+" rejected trial",blocked);
            if(compact){
                require(blocked.p->pos.at("U1")==FloorplanPoint{60,60},"rejected trial changed pose");
                require(blocked.p->ctx.quantization.at("breathe_stamp_index")==80,
                        "rejected trial must remove and restore both reservations exactly once");
                blocked.p->breathe("A");
                require(blocked.p->pos.at("U1")==FloorplanPoint{60,60} &&
                        blocked.p->ctx.quantization.at("breathe_stamp_index")==160,
                        "repeat rejected trial loses occupancy or actual receipts");
            }
        }
        // A later opposite-face group can legitimately enter the vacated halo.
        // A dispersion rollback must not then restore only the first sheet.
        for(bool reverse:{false,true}){
            const std::string own=reverse?"bottom":"top",opposite=reverse?"top":"bottom";
            Fixture rollback(compact);
            rollback.part("U1","first",own,60,60,true);
            rollback.part("U3","first",own,50,60);
            rollback.part("C1","first",own,50,61.5,false,false,2);
            rollback.part("C2","first",own,50,58.5,false,false,2);
            rollback.part("J1","fixed1",own,58,60,false,true);
            rollback.part("U2","second",opposite,57,60);
            rollback.part("J2","fixed2",opposite,55,60,false,true);
            const auto entry=rollback.p->pos;
            show(std::string(compact?"compact ":"default ")+own+" dispersion rollback",rollback);
            require(rect_gap(rollback.p->box("U1",rollback.p->pos.at("U1")),rollback.p->box("U2",rollback.p->pos.at("U2")))>=rollback.in.floorplan.place_clear,
                    "partial dispersion rollback invalidates cross-face shadow clearance");
            require(rollback.p->pos==entry,"dispersion rejection must restore the complete pass");
            require(rollback.p->ctx.quantization.at("breathe_commit_precision")>=4,"rollback erased actual trial receipts");
        }
    }
    std::cout<<"PASS real Placer::breathe two-face contracts\n";
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
