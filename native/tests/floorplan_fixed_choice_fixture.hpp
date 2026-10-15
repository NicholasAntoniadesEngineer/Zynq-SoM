#pragma once
#include "floorplan_internal.hpp"
namespace fixed_choice_fixture {
// Two real one-pad net participants, opposite zone preferences, one bottom
// variant. The true-piercing pass naturally wins on estimated airwire at 50x50.
inline schgen::FloorplanInput input(){
    using namespace schgen;FloorplanInput in;in.som.w=in.som.h=20;in.spec=FloorplanSpec{};in.spec->outline={{50,50}};
    in.footprints["one"]={"synthetic-one-pad",sexpr_loads(R"((footprint "one" (fp_rect (start -1 -1) (end 1 1) (layer "F.CrtYd") (width 0.05)) (pad "1" smd rect (at 0 0) (size 1 1))))")};
    in.footprint_of["Test:One"]="one";
    for(int k=1;k<=2;++k){
        const std::string name=k==1?"source":"sink",ref="U"+std::to_string(k*1000+1);
        CircuitSheetIr sheet;sheet.name=name;sheet.parts.push_back({"U1","Test:One","one","Test:One",{},{},{}});
        sheet.nets.push_back({"signal","port",{{"U1","1"}}});in.sheets.push_back(sheet);in.sheet_index.emplace_back(name,k);
        in.geometry.zone_box[name]={12,8};in.geometry.top_off[name][ref]={0,0};in.geometry.side_of[ref]="top";
        in.geometry.resolvable[ref]="one";in.geometry.bbox_of[ref]={-1,-1,1,1};
        FloorplanZoneShape top;top.w=12;top.h=8;top.top_off[ref]={0,0};auto bottom=top;
        bottom.side="bottom";bottom.top_off.clear();bottom.bot_off[ref]={0,0};in.geometry.shapes[name]={top,bottom};
        in.spec->interior[name].layer=k==1?"top":"bottom";in.spec->interior[name].side=k==1?"W":"E";
    }
    return in;
}
}
