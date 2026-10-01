#include "pcb_placement_orientations.hpp"
#include "pcb_placement_fixture.hpp"
#include "schgen/pcb_placement_gates.hpp"
#include <array>
#include <atomic>
#include <iostream>

using namespace schgen;
using namespace schgen::pcb_placement;
namespace {
std::atomic<bool> observing{false};
std::atomic<std::size_t> dimensions{0}, coordinates{0};
void demand(bool ok,const std::string& why){if(!ok)throw std::runtime_error(why);}
bool equal(const Shape& a,const Shape& b){return a.w==b.w&&a.h==b.h&&a.top_off==b.top_off&&
 a.bot_off==b.bot_off&&a.extra_rot==b.extra_rot&&a.mirror==b.mirror&&a.side==b.side&&a.tag==b.tag;}
PcbCheckInput model(const Shape& s,const Context& ctx,const Geometry& g) {
 PcbCheckModel m;m.board_w=s.w;m.board_h=s.h;m.origin_x=0;m.origin_y=0;
 for(const auto* offsets:{&s.top_off,&s.bot_off})for(const auto& [ref,p]:*offsets){
  PcbCheckInstance i;i.ref=ref;i.sheet="unit";i.x=p.first;i.y=p.second;
  i.rotation=s.extra_rot.count(ref)?s.extra_rot.at(ref):0;
  i.side=offsets==&s.top_off?s.side:(s.side=="top"?"bottom":"top");
  i.mirror=s.mirror.count(ref);i.mod=ctx.pool.at(i.mirror?s.mirror.at(ref):g.resolvable.at(ref));
  i.pad_nets={{"1",{1,"signal_A"}},{"2",{2,"signal_B"}},{"3",{3,"return"}}};
  m.insts.push_back(i);
 }
 return PcbCheckInput(std::move(m));
}
double handed(const PcbCheckInput& m,std::size_t i){
 const auto& p=m.geometry_at(i).pad_boxes;
 auto a=rect_center(p.at("1")),b=rect_center(p.at("2")),c=rect_center(p.at("3"));
 return (b.first-a.first)*(c.second-a.second)-(b.second-a.second)*(c.first-a.first);
}
void rigid(const Shape& seed,const Shape& result,int turns,const Context& ctx,const Geometry& g) {
 const auto a=model(seed,ctx,g),b=model(result,ctx,g);
 demand(a.model().insts.size()==b.model().insts.size(),"member lost");
 for(std::size_t i=0;i<a.model().insts.size();++i){
  const auto& x=a.model().insts[i];const auto& y=b.model().insts[i];
  demand(x.ref==y.ref&&x.mod==y.mod&&x.pad_nets==y.pad_nets&&x.side==y.side&&x.mirror==y.mirror,
         "identity, pad-net, face or mirrored-document mutation");
  demand(handed(a,i)*handed(b,i)>0,"rigid rotation changed chirality");
  for(const auto& [pin,box]:a.geometry_at(i).pad_boxes){
   auto p=rect_center(box);double w=seed.w,h=seed.h;
   for(int t=0;t<turns;++t){p={p.second,w-p.first};std::swap(w,h);}
   auto q=rect_center(b.geometry_at(i).pad_boxes.at(pin));
   demand(std::abs(p.first-q.first)<1e-9&&std::abs(p.second-q.second)<1e-9,
          "asymmetric pad did not follow independent rigid transform");
   const auto& next=b.geometry_at(i).pad_boxes.at(pin);
   const double width=box.x1-box.x0,height=box.y1-box.y0;
   demand(std::abs(next.x1-next.x0-(turns%2?height:width))<1e-9&&
          std::abs(next.y1-next.y0-(turns%2?width:height))<1e-9,"pad extents changed");
  }
 }
}
void unit(){
 PcbPlacementInput input;input.floorplan.compact_search=true;Context ctx(input);Geometry g;
 const std::string bytes="(footprint asymmetric (layer F.Cu) (fp_rect (start -2 -1) (end 3 2) (stroke (width 0.05) (type default)) (layer F.CrtYd)) (pad 1 smd rect (at -1 -.5) (size .4 .6) (layers F.Cu)) (pad 2 smd rect (at 2 .25) (size .8 .4) (layers F.Cu)) (pad 3 smd rect (at .25 1.5) (size .3 .5) (layers F.Cu)))";
 auto fp=pcb_check_footprint("asymmetric.kicad_mod",bytes);
 auto doc=mirrored_footprint(fp->document);
 auto mirrored=pcb_check_footprint("mirrored.kicad_mod",sexpr_dumps(doc),doc);
 ctx.pool={{"normal",fp},{"mirrored",mirrored}};
 g.refs_by_sheet["unit"]={"R1","R2"};ctx.board_refs["unit"]={{"A","R1"},{"B","R2"}};
 for(const auto& r:g.refs_by_sheet.at("unit")){
  ctx.by_ref[r]={r,r,"unit","normal","resistor","Device:R"};
  g.resolvable[r]="normal";g.bbox_of[r]=*fp->bbox;g.side_of[r]="top";
 }
 Shape seed;seed.w=24;seed.h=18;seed.tag="incumbent";seed.top_off={{"R1",{5,4}}};seed.bot_off={{"R2",{15,11}}};
 seed.extra_rot={{"R1",90},{"R2",270}};
 for(bool bottom:{false,true}){
  auto s=seed;if(bottom){s.side="bottom";s.mirror["R1"]="mirrored";}
  if(bottom)demand(handed(model(seed,ctx,g),0)*handed(model(s,ctx,g),0)<0,
                    "asymmetric mirrored footprint did not reverse handedness");
  g.shapes.clear();ctx.quantization.clear();dimensions=0;coordinates=0;observing=true;
  append_rigid_zone_orientations(ctx,g,"unit",s);observing=false;
  demand(g.shapes.at("unit").size()==4,"all four orientations required for asymmetric group");
  demand(equal(g.shapes.at("unit")[0],s),"incumbent replaced");
  demand(ctx.quantization==QuantizationCounts{{"placement_turn_dimension_precision4dp",6},
   {"placement_turn_offset_precision4dp",12}},"attempt receipt differs");
  demand(dimensions==6&&coordinates==12,"actual scalar entries differ from receipt");
  for(int t=0;t<4;++t)rigid(s,g.shapes.at("unit")[t],t,ctx,g);
  auto saved=g.shapes.at("unit");append_rigid_zone_orientations(ctx,g,"unit",s);
  demand(g.shapes.at("unit").size()==saved.size(),"duplicate variants accumulated");
  for(std::size_t i=0;i<saved.size();++i)demand(equal(saved[i],g.shapes.at("unit")[i]),"old order changed");
 }
 auto suppressed=[&](const std::string& why){
  g.shapes.clear();ctx.quantization.clear();append_rigid_zone_orientations(ctx,g,"unit",seed);
  demand(g.shapes.empty()&&ctx.quantization.empty(),why);
 };
 input.floorplan.compact_search=false;suppressed("default changed");input.floorplan.compact_search=true;
 g.conn_rot["R1"]=0;suppressed("fixed connector rotated");g.conn_rot.clear();
 ctx.by_ref["R1"].lib_id="Connector_Generic:Conn_01x03";suppressed("connector-class rotated");ctx.by_ref["R1"].lib_id="Device:R";
 // Only the exact known stock test-point pad is exempt from connector class.
 const auto saved_part=ctx.by_ref.at("R1");
 ctx.by_ref["R1"].lib_id="Connector:TestPoint";
 ctx.by_ref["R1"].footprint="TestPoint:TestPoint_Pad_D1.5mm";
 g.shapes.clear();append_rigid_zone_orientations(ctx,g,"unit",seed);
 demand(g.shapes.at("unit").size()==4,"known top-side probe pad wrongly treated as mating connector");
 g.conn_rot["R1"]=0;suppressed("probe exception bypassed fixed connector rotation");g.conn_rot.clear();
 auto bottom_probe=seed;bottom_probe.bot_off["R1"]=bottom_probe.top_off.at("R1");bottom_probe.top_off.erase("R1");
 g.shapes.clear();append_rigid_zone_orientations(ctx,g,"unit",bottom_probe);
 demand(g.shapes.empty(),"testpoint exemption bypassed top-side semantics");
 ctx.by_ref["R1"].footprint="TestPoint:UnknownProbe";suppressed("unknown testpoint footprint permitted");
 ctx.by_ref["R1"].footprint="TestPoint:TestPoint_Pad_D1.5mm";
 ctx.by_ref["R1"].lib_id="Connector_Generic:Conn_01x03";suppressed("mating connector with probe footprint permitted");
 ctx.by_ref["R1"].lib_id="Connector:Unknown";suppressed("unknown connector permitted");
 ctx.by_ref["R1"]=saved_part;
 input.contracts["unit"]=parse_json_text(R"({"external":{"downstream":"other","output_roles":["output"]}})");
 suppressed("contract direction rotated");input.contracts.clear();
 ctx.by_ref["R2"].lib_id="Switch:SW_SPST";g.shapes.clear();
 append_rigid_zone_orientations(ctx,g,"unit",seed);demand(g.shapes.empty(),"face-top part accepted on bottom");
 ctx.by_ref["R2"].lib_id="Device:R";
 input.contracts["unit"]=parse_json_text(R"({"contract":"placement/v2","structures":[{"type":"proximity","anchor":"A","members":["B"],"max_mm":0.1}]})");
 g.shapes.clear();append_rigid_zone_orientations(ctx,g,"unit",seed);demand(g.shapes.empty(),"failed authored proximity accepted");
 input.contracts.clear();
 auto invalid=seed;invalid.w=2;g.shapes.clear();append_rigid_zone_orientations(ctx,g,"unit",invalid);
 demand(g.shapes.empty(),"out-of-bounds candidate accepted");
 // A square outline does not make distinct pad arrangements duplicates.
 seed.w=24;seed.h=24;g.shapes.clear();append_rigid_zone_orientations(ctx,g,"unit",seed);
 demand(g.shapes.at("unit").size()==4,"dimension-only dedup discarded orientations");
 // Four successive turns must not add an identity variant merely because
 // turned() materializes missing zero rotations. Preserve the sparse original.
 auto sparse=seed;sparse.extra_rot.clear();sparse.tag="sparse-zero";
 g.shapes.clear();append_rigid_zone_orientations(ctx,g,"unit",sparse);
 const auto sparse_prefix=g.shapes.at("unit");
 append_rigid_zone_orientations(ctx,g,"unit",sparse);
 demand(g.shapes.at("unit").size()==4,"absent/zero rotation generated duplicate");
 for(std::size_t i=0;i<sparse_prefix.size();++i)
  demand(equal(sparse_prefix[i],g.shapes.at("unit")[i]),"dedup rewrote original sparse representation");
 demand(g.shapes.at("unit")[0].extra_rot.empty(),"dedup filled original rotation map");
 auto explicit_zero=sparse;explicit_zero.extra_rot={{"R1",0},{"R2",0}};explicit_zero.tag="explicit-zero";
 g.shapes["unit"]={sparse,explicit_zero};append_rigid_zone_orientations(ctx,g,"unit",sparse);
 demand(g.shapes.at("unit").size()==5,"equivalent old zeros generated duplicate new variants");
 demand(equal(g.shapes.at("unit")[0],sparse)&&equal(g.shapes.at("unit")[1],explicit_zero),
        "dedup changed existing zero/absent variants or indices");
 // Explicit nonzero rotations remain distinct from missing/zero rotations.
 auto nonzero=sparse;nonzero.extra_rot["R1"]=90;nonzero.tag="nonzero";
 g.shapes["unit"]={sparse,nonzero};append_rigid_zone_orientations(ctx,g,"unit",sparse);
 demand(g.shapes.at("unit").size()==8,"dedup erased genuinely different member rotation");
}
void live(const std::filesystem::path& root){
 for(const auto* project:{"carrier","devkit_mini"}){
  auto f=placement_fixture::load(root,project);
  auto observed_build=[&]{
   dimensions=0;coordinates=0;observing=true;auto result=build_pcb_zone_geometry(f.input);observing=false;
   const auto count=[&](const std::string& key){const auto p=result.quantization_engagements.find(key);
    return p==result.quantization_engagements.end()?0:p->second;};
   demand(count("placement_turn_dimension_precision4dp")==dimensions&&
          count("placement_turn_offset_precision4dp")==coordinates,"board trial entries missing from receipt");
   return result;
  };
  auto before=observed_build();
  f.input.floorplan.compact_search=true;auto after=observed_build();
  Context connectivity(f.input);
  for(const auto& [sheet,refs]:before.geometry.refs_by_sheet){(void)refs;
   demand(connectivity.stage_input(sheet,before.geometry).pad_nets==
          connectivity.stage_input(sheet,after.geometry).pad_nets,"authored pin-net identity changed");
  }
  demand(before.geometry.top_off==after.geometry.top_off&&before.geometry.bot_off==after.geometry.bot_off&&
   before.geometry.zone_box==after.geometry.zone_box&&before.geometry.zone_extra_rot==after.geometry.zone_extra_rot&&
   before.geometry.side_of==after.geometry.side_of&&before.geometry.resolvable==after.geometry.resolvable,
   "compact changed incumbent geometry");
  std::size_t added=0;
  for(const auto& [sheet,old]:before.geometry.shapes){
   const auto& next=after.geometry.shapes.at(sheet);demand(next.size()>=old.size(),"old variants removed");
   for(std::size_t i=0;i<old.size();++i)demand(equal(old[i],next[i]),"old variant index changed");
  }
  for(const auto& [sheet,next]:after.geometry.shapes){
   const auto prior=before.geometry.shapes.find(sheet);
   const auto count=next.size()-(prior==before.geometry.shapes.end()?1:prior->second.size());
   if(std::string(project)=="carrier"&&(sheet=="board_aux"||sheet=="bringup_rails"))
    demand(prior!=before.geometry.shapes.end()&&count==3*prior->second.size(),
           "known test-point group did not expose all validated quarter turns");
   if(std::string(project)=="carrier"&&sheet=="power_mon")
    demand(count==0,"power_mon gained redundant identity orientation");
   added+=count;
   if(count)std::cout<<project<<" "<<sheet<<" +"<<count<<" orientations\n";
  }
  if(std::string(project)=="carrier")demand(added>0,"compact mode added no real-board alternatives");
  for(const auto& [key,n]:before.quantization_engagements){
   const auto actual=after.quantization_engagements.at(key);
   demand((key=="placement_turn_dimension_precision4dp"||key=="placement_turn_offset_precision4dp")?
    actual>=n:actual==n,"unrelated counter changed");
  }
  for(const auto& [key,n]:after.quantization_engagements){(void)n;
   demand(before.quantization_engagements.count(key)||key=="placement_turn_dimension_precision4dp"||
    key=="placement_turn_offset_precision4dp","unexpected new engagement");
  }
  demand(before.fallback_events==after.fallback_events,"orientation manufactured fallback");
  std::cout<<project<<" appended="<<added<<" incumbent/prefix/old receipts unchanged\n";
 }
}
}
extern "C" void __cyg_profile_func_enter(void* fn,void*) {
 if(!observing)return;
 if(fn==reinterpret_cast<void*>(&placement_turn_dimension_precision4dp))++dimensions;
 if(fn==reinterpret_cast<void*>(&placement_turn_offset_precision4dp))++coordinates;
}
extern "C" void __cyg_profile_func_exit(void*,void*) {}
int main(int argc,char** argv){try{demand(argc==2,"fixture root required");unit();live(argv[1]);
 std::cout<<"PASS rigid orientation, chirality, identity, eligibility, negatives and incumbent contracts\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
