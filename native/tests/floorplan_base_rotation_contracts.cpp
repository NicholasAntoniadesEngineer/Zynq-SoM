// Synthetic geometry contracts only: no board search, emitted files, or live catalog.
#include "../src/floorplan_internal.hpp"
#include "schgen/sexpr.hpp"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <stdexcept>

using namespace schgen;
using namespace schgen::floorplan_detail;
namespace {
int checks=0;
void require(bool v,const char* why){++checks;if(!v)throw std::runtime_error(why);}
// Independent corner transform: no production turn/halo/placement helper.
Box4 actual(Box4 b,double degrees,double x,double y){
    const double a=-degrees*std::acos(-1.)/180.;
    Box4 out{1e9,1e9,-1e9,-1e9};
    for(double px:{b.x0,b.x1})for(double py:{b.y0,b.y1}){
        const double xx=x+px*std::cos(a)-py*std::sin(a);
        const double yy=y+px*std::sin(a)+py*std::cos(a);
        out.x0=std::min(out.x0,xx);out.y0=std::min(out.y0,yy);
        out.x1=std::max(out.x1,xx);out.y1=std::max(out.y1,yy);
    }
    return out;
}
FloorplanFootprint document(bool mirrored,bool thru){
    const std::string bounds=mirrored?"(start 0 -1) (end 4 0)":"(start -4 -1) (end 0 0)";
    std::string text="(footprint \"asymmetric\" (fp_rect "+bounds+" (layer \"F.CrtYd\") (width 0.05))";
    for(int i=1;i<=9;++i)text+=" (pad \""+std::to_string(i)+"\" "+(thru?"thru_hole":"smd")+" rect (at "+(mirrored?"2":"-2")+" -0.5) (size 0.4 0.6) (layers \"*.Cu\"))";
    return {mirrored?"mirror.kicad_mod":"base.kicad_mod",sexpr_loads(text+")")};
}
void expected(Halo reach,Halo inset,Box4 box,double w,double h){
    const double margins[]{box.x0,w-box.x1,box.y0,h-box.y1};
    const double rs[]{reach.w,reach.e,reach.n,reach.s};
    const double is[]{inset.w,inset.e,inset.n,inset.s};
    for(int k=0;k<4;++k){
        if(std::abs(is[k]-margins[k])>.000051)std::cerr<<"inset axis="<<k<<" got="<<is[k]<<" expected="<<margins[k]<<'\n';
        require(std::abs(is[k]-margins[k])<=.000051,"member inset differs from independent actual corners");
        require(std::abs(rs[k]-std::max(0.,quant_credit(2.)-margins[k]))<=.000051,"member reach differs from independent actual corners");
    }
}
void matrix(bool before,bool default_only){
    for(bool compact:{false,true})for(bool bottom:{false,true})for(bool mirror:{false,true})
    for(bool thru:{false,true})for(double conn:{90.,37.,-123.})for(double extra:{0.,17.}){
        if(default_only&&compact)continue;
        FloorplanInput in;in.som.w=10;in.som.h=10;in.compact_search=compact;
        in.footprints["base"]=document(false,thru);in.footprints["mirror"]=document(true,thru);
        in.geometry.resolvable["U1"]="base";in.geometry.conn_rot["U1"]=conn;
        in.geometry.bbox_of["U1"]={-4,-1,0,0};
        Engine engine(in);FloorplanZoneShape shape;shape.w=10;shape.h=10;
        shape.side=bottom?"bottom":"top";shape.bot_off["U1"]={5,5};shape.extra_rot["U1"]=extra;
        if(mirror)shape.mirror["U1"]="mirror";
        const Box4 local=mirror?Box4{0,-1,4,0}:Box4{-4,-1,0,0};
        const auto physical=actual(local,conn+extra,5,5);
        auto halos=engine.fanout(shape);
        expected(halos.first,halos.second,actual(local,before?extra:conn+extra,5,5),10,10);
        const auto variant=engine.fanout(shape);
        expected(variant.first,variant.second,physical,10,10);
        if(default_only){
            for(auto halo:{halos.first,halos.second,variant.first,variant.second})
                std::cout<<std::hexfloat<<halo.w<<' '<<halo.e<<' '<<halo.n<<' '<<halo.s<<'\n';
            for(const auto& [key,count]:engine.plan.accounting.quantization_engagements)
                std::cout<<key<<'='<<count<<'\n';
        }
        for(bool pads:{false,true}){
            const auto children=engine.zone_components(shape,pads,nullptr);
            require(children.size()==(thru?10u:1u)||(!pads&&thru&&children.size()==2),"unexpected punch count");
            const auto& child=children.front();
            require(child.mask==(bottom?1:2),"minority physical face changed");
            auto relative=physical;relative.x0-=child.dx;relative.x1-=child.dx;
            relative.y0-=child.dy;relative.y1-=child.dy;
            if(compact)expected(child.reach,child.inset,relative,child.w,child.h);
            else require(child.reach.w==0&&child.reach.e==0&&child.reach.n==0&&child.reach.s==0,"default child halo changed");
            for(std::size_t k=1;k<children.size();++k)
                require(children[k].mask==3&&children[k].reach.w==0&&children[k].reach.e==0&&children[k].reach.n==0&&children[k].reach.s==0,"punch semantics changed");
        }
    }
}
void admission(bool before){
    for(bool bottom:{false,true})for(bool pads:{false,true})for(bool thru:{false,true}){
        FloorplanInput in;in.som.w=10;in.som.h=10;in.compact_search=true;
        in.footprints["base"]=document(false,thru);in.geometry.resolvable["U1"]="base";
        in.geometry.bbox_of["U1"]={-4,-1,0,0};in.geometry.conn_rot["U1"]=90;
        Engine engine(in);FloorplanZoneShape a;a.w=10;a.h=10;a.side=bottom?"bottom":"top";
        a.bot_off["U1"]={5,5};a.extra_rot["U1"]=0;
        const auto h=engine.fanout(a);auto c=engine.zone_components(a,pads,nullptr);
        const int primary=bottom?2:1,minor=bottom?1:2;
        Occupancy grid(50,50,.3,4,10,1,.05);
        grid.add(10,10,10,10,h.first,h.second,primary,c);
        // Independent foreign minority member occupies its entire second body.
        std::vector<Comp> crowder{{0,0,1,1,minor}};
        const bool accepted=grid.fits_hashed(14,20.5,1,1,{},{},primary,crowder);
        require(accepted==grid.fits_exhaustive(14,20.5,1,1,{},{},primary,crowder),"hash disagreement");
        const auto body=actual({-4,-1,0,0},90,15,15);
        const double actual_gap=20.5-body.y1;
        require(actual_gap<2.-1e-4,"witness is not hardware-starved");
        require(accepted==before,"base rotation unsafe admission not corrected");
        require(grid.fits_hashed(14,21.5,1,1,{},{},primary,crowder),"legal actual-member exit was lost");
        require(!occ_pair_active(minor,primary,false,minor,primary,false),"same-primary exemption altered");
        std::cout<<"WITNESS side="<<a.side<<" pad_punch="<<pads<<" thru="<<thru<<" gap="<<actual_gap<<" need=2 accepted="<<accepted<<'\n';
    }
}
void implicit_base(bool before){
    FloorplanInput in;in.som.w=10;in.som.h=10;in.compact_search=true;
    in.footprints["base"]=document(false,false);in.geometry.resolvable["U1"]="base";
    in.geometry.bbox_of["U1"]={-4,-1,0,0};in.geometry.conn_rot["U1"]=90;
    in.geometry.zone_extra_rot["U1"]=0;in.geometry.zone_box["nonpilot"]={10,10};
    in.geometry.bot_off["nonpilot"]["U1"]={5,5};
    Engine engine(in);FloorplanBlock block;block.name="nonpilot";block.kind="interior";
    engine.plan.interior_blocks.push_back(block);engine.prepare_geometry();
    const auto& built=engine.plan.interior_blocks.front();
    expected(built.fanout_reach,built.fanout_inset,actual({-4,-1,0,0},before?0:90,5,5),10,10);
    for(int policy:{0,1}){
        const auto& children=engine.components[policy].at({"nonpilot",0});
        require(children.size()==1,"implicit nonpilot base lost minority child");
        Occupancy grid(50,50,.3,4,10,1,.05);
        grid.add(10,10,10,10,built.fanout_reach,built.fanout_inset,1,children);
        require(grid.fits_hashed(14,20.5,1,1,{},{},1,{{0,0,1,1,2}})==before,
            "prepare_geometry implicit shape-zero admission");
    }
}
void primary_admission(){
    for(bool compact:{false,true})for(bool bottom:{false,true}){
        FloorplanInput in;in.som.w=in.som.h=10;in.compact_search=compact;
        in.footprints["base"]=document(false,false);in.geometry.resolvable["U1"]="base";
        in.geometry.bbox_of["U1"]={-4,-1,0,0};in.geometry.conn_rot["U1"]=90;
        Engine engine(in);FloorplanZoneShape shape;shape.w=shape.h=10;
        shape.side=bottom?"bottom":"top";shape.top_off["U1"]={5,5};shape.extra_rot["U1"]=0;
        const auto halo=engine.fanout(shape);const int face=bottom?2:1;
        Occupancy grid(50,50,.3,4,10,1,.05);
        grid.add(10,10,10,10,halo.first,halo.second,face,{});
        const auto body=actual({-4,-1,0,0},90,15,15);
        require(20.5-body.y1<2.-1e-4,"primary witness must be physically starved");
        require(!grid.fits_hashed(14,20.5,1,1,{},{},face,{})&&
                !grid.fits_exhaustive(14,20.5,1,1,{},{},face,{}),
            "default and compact must reject the same physically starved primary-face placement");
        require(grid.fits_hashed(14,21.5,1,1,{},{},face,{}),"legal primary-face exit lost");
    }
}
}
int main(int argc,char** argv){try{
    const bool before=argc==2&&std::string(argv[1])=="--before";
    const bool default_only=argc==2&&std::string(argv[1])=="--default-only";
    matrix(before,default_only);if(!default_only){admission(before);implicit_base(before);if(!before)primary_admission();}std::cout<<"PASS checks="<<checks<<'\n';return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
