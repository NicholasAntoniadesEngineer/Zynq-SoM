#include "pcb_placement_fixture.hpp"
#include "floorplan_internal.hpp"
#include "schgen/pcb_escape.hpp"
#include "schgen/precision_ops.hpp"
#include <cmath>
#include <iostream>

namespace {
using namespace schgen;
void require(bool ok,const std::string& why){if(!ok)throw std::runtime_error(why);}
void same(Box4 a,Box4 b){
    require(std::abs(a.x0-b.x0)<1e-9&&std::abs(a.y0-b.y0)<1e-9&&
            std::abs(a.x1-b.x1)<1e-9&&std::abs(a.y1-b.y1)<1e-9,"corridor geometry differs");
}
void rotated_corridor_bounds(){
    const ContactGeom contacts{1.5,.15,.25,10,.5};
    std::size_t rejected_shortcuts=0;
    // Independently transform every local corner; compare extremal coordinates
    // within the established 4dp emission precision, not a two-corner shortcut.
    for(const int row:{-1,1})for(int degrees=-180;degrees<=360;degrees+=15){
        QuantizationCounts counts;
        const auto box=pcb_escape_row_corridor(contacts,-4,6,row,12,-8,degrees,&counts);
        double xmin=INFINITY,ymin=INFINITY,xmax=-INFINITY,ymax=-INFINITY;
        const double angle=degrees*std::acos(-1.0)/180.;
        for(const double u:{-4.5,6.5})for(const double v:{row*1.75,row*3.05}){
            const double x=12+u*std::cos(angle)+v*std::sin(angle);
            const double y=-8-u*std::sin(angle)+v*std::cos(angle);
            xmin=std::min(xmin,x);xmax=std::max(xmax,x);
            ymin=std::min(ymin,y);ymax=std::max(ymax,y);
        }
        require(std::abs(box.x0-xmin)<=.000050001&&std::abs(box.y0-ymin)<=.000050001&&
                std::abs(box.x1-xmax)<=.000050001&&std::abs(box.y1-ymax)<=.000050001,
                "rotated corridor does not bound all four corners at output precision");
        require(counts.at("escape_corridor_precision4dp")==4,"rotated bounds accounting changed");
        const auto a=uv_to_board(12,-8,-4.5,row*1.75,degrees);
        const auto b=uv_to_board(12,-8,6.5,row*3.05,degrees);
        if(std::abs(std::min(a.first,b.first)-xmin)>.000050001||
           std::abs(std::min(a.second,b.second)-ymin)>.000050001||
           std::abs(std::max(a.first,b.first)-xmax)>.000050001||
           std::abs(std::max(a.second,b.second)-ymax)>.000050001)++rejected_shortcuts;
    }
    require(rejected_shortcuts==60,"rotation corpus did not expose the old two-corner defect");
}
void check(const std::filesystem::path& root,const std::string& project){
    auto fixture=placement_fixture::load(root,project);
    // Historical generated rectangles are evidence to compare, not input.
    fixture.input.floorplan.compose.corridors.clear();
    floorplan_detail::Engine engine(fixture.input.floorplan);
    engine.plan=fixture.stage.plan;
    engine.prepare_escape_rows();
    const auto before=engine.plan.accounting.quantization_engagements;
    const auto base=engine.current_escape_corridors();
    require(base.size()==6,"all three connector rows must be reserved");
    const auto source=parse_json_file((root/"native/tests/data/pcb_escape"/(project+"_escape_block.json")).string());
    const auto& expected=*object_field(*object_field(source,"t1_constraints"),"corridors");
    for(const auto& [name,b]:base){
        const auto* row=object_field(expected,name.substr(7));require(row,"missing independent frozen corridor");
        const auto& a=object_field(*row,"rect")->array_value;
        same(b,{a[0].number_value-25,a[1].number_value-25,a[2].number_value-25,a[3].number_value-25});
    }
    const auto count=[](const auto& m,const char* k){const auto it=m.find(k);return it==m.end()?std::size_t{0}:it->second;};
    const auto& after=engine.plan.accounting.quantization_engagements;
    require(count(after,"escape_corridor_precision4dp")-count(before,"escape_corridor_precision4dp")==24,
            "current corridor precision work was not accounted");
    require(count(after,"fixed_part_grid")-count(before,"fixed_part_grid")==12,
            "current connector snapping work was not accounted");
    // Same prepared rows, different current outlines/SoM positions: no stale
    // absolute rectangle or last-run translation may survive.
    const auto old_x=engine.plan.som_x,old_y=engine.plan.som_y;
    for(const auto delta:std::vector<FloorplanPoint>{{1.27,2.54},{-.635,.3175},{8,-7}}){
        engine.plan.som_x=old_x+delta.first;engine.plan.som_y=old_y+delta.second;
        const auto moved=engine.current_escape_corridors();
        require(moved.size()==base.size(),"changing pose lost corridor rows");
        for(std::size_t i=0;i<moved.size();++i){
            const auto& row=engine.escape_rows[i];
            const double dx=fixed_part_grid(25+old_x+delta.first+row.offset.first)-fixed_part_grid(25+old_x+row.offset.first);
            const double dy=fixed_part_grid(25+old_y+delta.second+row.offset.second)-fixed_part_grid(25+old_y+row.offset.second);
            const auto& b=base[i].second;
            same(moved[i].second,{b.x0+dx,b.y0+dy,b.x1+dx,b.y1+dy});
        }
    }
    engine.plan.som_x=old_x;engine.plan.som_y=old_y;
    const auto repeated=engine.current_escape_corridors();
    for(std::size_t i=0;i<base.size();++i)same(repeated[i].second,base[i].second);
    // Authored caller constraints remain authoritative, unlike output sidecars.
    auto explicit_input=fixture.input.floorplan;
    explicit_input.compose.corridors.push_back({"authored:reserved",{1,2,3,4}});
    floorplan_detail::Engine explicit_engine(explicit_input);
    explicit_engine.plan=fixture.stage.plan;
    explicit_engine.prepare_escape_rows();
    const auto combined=explicit_engine.current_escape_corridors();
    require(combined.size()==7&&combined.front().first=="authored:reserved",
            "current rows displaced an explicit caller constraint");
    same(combined.front().second,{1,2,3,4});
    for(std::size_t i=0;i<base.size();++i)same(combined[i+1].second,base[i].second);
    auto missing=fixture.input.floorplan;
    missing.footprint_of.clear();
    floorplan_detail::Engine missing_engine(missing);
    missing_engine.plan=fixture.stage.plan;
    bool rejected=false;
    try{missing_engine.prepare_escape_rows();}catch(const FloorplanError&){rejected=true;}
    require(rejected,"missing current connector geometry silently dropped reservations");
    std::cout<<project<<" current corridor parity, translation, rebuild and accounting PASS\n";
}
}
int main(int argc,char** argv){try{
    require(argc==2,"usage: floorplan_escape_corridors REPOSITORY");
    rotated_corridor_bounds();
    check(argv[1],"carrier");check(argv[1],"devkit_mini");
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
