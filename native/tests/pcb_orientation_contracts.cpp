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
std::atomic<std::size_t> bottom_coordinates{0}, variant_dimensions{0};
void demand(bool ok,const std::string& why){if(!ok)throw std::runtime_error(why);}
bool equal(const Shape& a,const Shape& b){return a.w==b.w&&a.h==b.h&&a.top_off==b.top_off&&
 a.bot_off==b.bot_off&&a.extra_rot==b.extra_rot&&a.mirror==b.mirror&&a.side==b.side&&a.tag==b.tag;}
PcbCheckInput model(const Shape& s,const Context& ctx,const Geometry& g,const std::string& sheet="unit") {
 PcbCheckModel m;m.board_w=s.w;m.board_h=s.h;m.origin_x=0;m.origin_y=0;
 for(const auto* offsets:{&s.top_off,&s.bot_off})for(const auto& [ref,p]:*offsets){
  PcbCheckInstance i;i.ref=ref;i.sheet=sheet;i.x=p.first;i.y=p.second;
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
  const auto& pins=a.geometry_at(i).pad_boxes;
  if(pins.count("1")&&pins.count("2")&&pins.count("3"))
   demand(std::abs(handed(a,i)-handed(b,i))<1e-8,"rigid rotation changed signed pad-triangle area");
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
 // Equal outlines are not equal layouts. Preserve every existing index and
 // compare the actual member geometry, including opposite-face placement.
 auto rearranged=sparse;rearranged.top_off.at("R1").first+=1;rearranged.tag="same-size-rearranged";
 auto back_changed=sparse;back_changed.bot_off.at("R2").second+=1;
 auto mirrored_changed=sparse;mirrored_changed.mirror["R1"]="mirrored";
 auto rotated_changed=sparse;rotated_changed.extra_rot["R1"]=90;
 auto side_changed=sparse;side_changed.side="bottom";
 std::vector<Shape> retained{sparse,explicit_zero};const auto original_prefix=retained;
 const std::vector<Shape> alternatives{explicit_zero,rearranged,rearranged,back_changed,mirrored_changed,rotated_changed,side_changed};
 append_distinct_zone_shapes(sparse,retained,alternatives);
 demand(retained.size()==7,"equal-box dedup discarded distinct geometry or retained duplicates");
 demand(equal(retained[0],original_prefix[0])&&equal(retained[1],original_prefix[1]),"equal-box dedup rewrote legacy prefix");
 const auto once=retained;append_distinct_zone_shapes(sparse,retained,alternatives);
 demand(retained.size()==once.size(),"repeated same-box expansion is not idempotent");
 for(std::size_t i=0;i<once.size();++i)demand(equal(retained[i],once[i]),"repeat expansion changed geometry/index");
 std::vector<Shape> alias{sparse};alias.shrink_to_fit();
 append_distinct_zone_shapes(alias.front(),alias,alternatives);
 demand(alias.size()==6&&equal(alias.front(),sparse),"append invalidated a borrowed incumbent");
 g.shapes["unit"]={sparse,explicit_zero};append_rigid_zone_orientations(ctx,g,"unit",sparse);
 demand(g.shapes.at("unit").size()==5,"equivalent old zeros generated duplicate new variants");
 demand(equal(g.shapes.at("unit")[0],sparse)&&equal(g.shapes.at("unit")[1],explicit_zero),
        "dedup changed existing zero/absent variants or indices");
 // Explicit nonzero rotations remain distinct from missing/zero rotations.
 auto nonzero=sparse;nonzero.extra_rot["R1"]=90;nonzero.tag="nonzero";
 g.shapes["unit"]={sparse,nonzero};append_rigid_zone_orientations(ctx,g,"unit",sparse);
 demand(g.shapes.at("unit").size()==8,"dedup erased genuinely different member rotation");
 // Incremental orientation expansion must not redo the old candidate prefix.
 g.shapes["unit"]={sparse,nonzero};ctx.quantization.clear();dimensions=0;coordinates=0;observing=true;
 append_rigid_zone_orientations(ctx,g,"unit",sparse,1);observing=false;
 demand(dimensions==6&&coordinates==12,"suffix expansion repeated old orientation work");
 demand(equal(g.shapes.at("unit")[0],sparse)&&equal(g.shapes.at("unit")[1],nonzero),"suffix changed prior indices");
 const auto suffix_count=g.shapes.at("unit").size();ctx.quantization.clear();
 append_rigid_zone_orientations(ctx,g,"unit",sparse,suffix_count);
 demand(ctx.quantization.empty()&&g.shapes.at("unit").size()==suffix_count,"empty suffix performed work");
 bool invalid_suffix=false;
 try {append_rigid_zone_orientations(ctx,g,"unit",sparse,suffix_count+1);}catch(const PcbZoneInfeasible&){invalid_suffix=true;}
 demand(invalid_suffix&&ctx.quantization.empty(),"invalid suffix did not fail before work");
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
  if(std::string(project)=="carrier") {
   auto experiment=std::make_shared<FloorplanExperiment>();
   experiment->contract_group_face_sheet="usb_jtag";f.input.floorplan.experiment=experiment;
   bottom_coordinates=0;variant_dimensions=0;observing=true;
   auto split=build_pcb_zone_geometry(f.input);observing=false;
   demand(split.quantization_engagements.at("placement_bottom_pose_precision4dp")==bottom_coordinates&&
          split.quantization_engagements.at("placement_variant_dimension_precision4dp")==variant_dimensions,
          "actual mixed-face scalar operations differ from receipt");
   // Test incremental alternatives independently. Automatically offering all
   // of them regresses the qualified global plan; production keeps its offers.
   const auto expand=[&](PcbZoneResult& zones) {
    Context ctx(f.input);ctx.pool=zones.footprints;
    const auto& originals=zones.geometry.shapes.at("usb_jtag");
    const auto start=std::find_if(originals.begin(),originals.end(),[](const auto& s){return s.tag.rfind("contract-bottom/",0)==0;});
    demand(start!=originals.end(),"missing new contract-group suffix");
    const auto first=static_cast<std::size_t>(start-originals.begin());
    const Shape seed=originals.front();
    append_rigid_zone_orientations(ctx,zones.geometry,"usb_jtag",seed,first);
   };
   expand(split);
   const auto& variants=split.geometry.shapes.at("usb_jtag");
   auto repeated=build_pcb_zone_geometry(f.input);
   expand(repeated);
   demand(split.quantization_engagements==repeated.quantization_engagements,"face candidate receipts not reproducible");
   const auto& repeated_variants=repeated.geometry.shapes.at("usb_jtag");
   demand(variants.size()==repeated_variants.size(),"face candidate count not reproducible");
   for(std::size_t i=0;i<variants.size();++i)demand(equal(variants[i],repeated_variants[i]),"face candidates not reproducible");
   const auto& prefix=after.geometry.shapes.at("usb_jtag");
   for(std::size_t i=0;i<prefix.size();++i)demand(equal(prefix[i],variants[i]),"face experiment rewrote original variants");
   Context candidate_context(f.input);candidate_context.pool=split.footprints;
   const auto original=model(variants.front(),candidate_context,split.geometry,"usb_jtag");
   std::map<std::string,std::size_t> original_indices;
   for(std::size_t i=0;i<original.model().insts.size();++i)original_indices.emplace(original.model().insts[i].ref,i);
   std::size_t candidates=0,rotated_candidates=0;
   for(std::size_t index=0;index<variants.size();++index) {
    const auto& candidate=variants[index];
    if(candidate.tag.rfind("contract-bottom/",0)!=0)continue;
    ++candidates;
    const auto measured=model(candidate,candidate_context,split.geometry,"usb_jtag");
    demand(check_pcb_placement_contract(measured,"usb_jtag",&f.input.contracts.at("usb_jtag"),
        candidate_context.board_refs.at("usb_jtag")).ok,"local mixed-face contract failed");
    const auto slash=candidate.tag.find_last_of('/');
    const auto suffix=candidate.tag.substr(slash);
    if(suffix=="/r90"||suffix=="/r180"||suffix=="/r270") {
     ++rotated_candidates;
     const auto parent_tag=candidate.tag.substr(0,slash);
     const auto parent=std::find_if(variants.begin(),variants.end(),[&](const auto& s){return s.tag==parent_tag;});
     demand(parent!=variants.end(),"rotated candidate lost its unrotated parent");
     rigid(*parent,candidate,suffix=="/r90"?1:suffix=="/r180"?2:3,candidate_context,split.geometry);
     const auto bound=bind_pcb_zone_shapes(split,{{"usb_jtag",static_cast<int>(index)}});
     for(const auto& [ref,key]:candidate.mirror)
      demand(bound.resolvable.at(ref)==key&&bound.mirror_refs.count(ref)&&bound.side_of.at(ref)=="bottom",
             "rotated mixed-face candidate lost mirrored binding");
     demand(candidate_context.stage_input("usb_jtag",bound).pad_nets==
            candidate_context.stage_input("usb_jtag",after.geometry).pad_nets,"rotated binding changed authored net identity");
     continue;
    }
    for(const auto* pinned:{"U1","SW1","TP1","TP2","TP3"}) {
     const auto ref=candidate_context.board_refs.at("usb_jtag").at(pinned);
     demand(candidate.top_off.at(ref)==variants.front().top_off.at(ref)&&!candidate.mirror.count(ref),
            "controlled owner or top-access part moved");
    }
    demand(candidate.w*candidate.h<variants.front().w*variants.front().h,"candidate did not reduce envelope");
    std::optional<FloorplanPoint> translation;
    for(std::size_t i=0;i<measured.model().insts.size();++i) {
     const auto& part=measured.model().insts[i];const auto oi=original_indices.at(part.ref);
     const auto& old=original.model().insts[oi];
     demand(part.pad_nets==old.pad_nets,"candidate changed pad-net identity");
     if(!candidate.mirror.count(part.ref))continue;
     const FloorplanPoint delta{part.x+old.x,part.y-old.y};
     if(!translation)translation=delta;
     demand(std::abs(delta.first-translation->first)<1e-4&&std::abs(delta.second-translation->second)<1e-4,
            "group was not moved rigidly");
     for(const auto& [pin,box]:original.geometry_at(oi).pad_boxes) {
      const auto a=rect_center(box),b=rect_center(measured.geometry_at(i).pad_boxes.at(pin));
      demand(std::abs(b.first-(delta.first-a.first))<1e-8&&std::abs(b.second-(delta.second+a.second))<1e-8,
             "named pad failed independent bottom reflection");
     }
    }
    const auto bound=bind_pcb_zone_shapes(split,{{"usb_jtag",static_cast<int>(index)}});
    for(const auto& [ref,key]:candidate.mirror) {
     demand(bound.resolvable.at(ref)==key&&bound.mirror_refs.count(ref),"mixed-face binder lost mirrored document");
     demand(bound.side_of.at(ref)=="bottom","mixed-face binder lost bottom face");
    }
    demand(candidate_context.stage_input("usb_jtag",bound).pad_nets==
           candidate_context.stage_input("usb_jtag",after.geometry).pad_nets,"binding changed authored net identity");
   }
   demand(candidates>0,"contract-group face experiment generated no candidates");
   demand(rotated_candidates==3*(candidates-rotated_candidates),"new groups missing legal quarter turns");
   auto blocked_context=candidate_context;
   for(const auto* owner:{"U2","U4"})blocked_context.by_ref.at(blocked_context.board_refs.at("usb_jtag").at(owner)).lib_id="Switch:SW_SPST";
   auto blocked_geometry=after.geometry;
   append_contract_group_faces(blocked_context,blocked_geometry,"usb_jtag",variants.front());
   demand(blocked_geometry.shapes.at("usb_jtag").size()==prefix.size(),"pinned owners still generated bottom candidates");
   // An unconnected copper pad is still physical occupancy. Keep the authored
   // courtyard unchanged, so a courtyard-only gate cannot detect this escape.
   auto protruding_context=candidate_context;auto protruding_geometry=after.geometry;
   const auto switch_ref=protruding_context.board_refs.at("usb_jtag").at("SW1");
   const auto switch_key=protruding_geometry.resolvable.at(switch_ref);
   const auto original_fp=protruding_context.pool.at(switch_key);auto bytes=original_fp->bytes;
   bytes.insert(bytes.rfind(')')," (pad \"PROBE\" smd rect (at 1000 0) (size 1 1) (layers \"F.Cu\" \"F.Paste\" \"F.Mask\"))");
   protruding_context.pool[switch_key]=pcb_check_footprint(original_fp->source,bytes);
   append_contract_group_faces(protruding_context,protruding_geometry,"usb_jtag",variants.front());
   demand(protruding_geometry.shapes.at("usb_jtag").size()==prefix.size(),"copper outside courtyard escaped contract-group bounds");
   protruding_geometry.shapes["usb_jtag"]={variants.front()};
   append_rigid_zone_orientations(protruding_context,protruding_geometry,"usb_jtag",variants.front());
   demand(protruding_geometry.shapes.at("usb_jtag").size()==1,"copper outside courtyard escaped orientation bounds");
   std::cout<<"carrier contract-group candidates="<<candidates<<'\n';
  }
 }
}
}
extern "C" void __cyg_profile_func_enter(void* fn,void*) {
 if(!observing)return;
 if(fn==reinterpret_cast<void*>(&placement_turn_dimension_precision4dp))++dimensions;
 if(fn==reinterpret_cast<void*>(&placement_turn_offset_precision4dp))++coordinates;
 if(fn==reinterpret_cast<void*>(&placement_bottom_pose_precision4dp))++bottom_coordinates;
 if(fn==reinterpret_cast<void*>(&placement_variant_dimension_precision4dp))++variant_dimensions;
}
extern "C" void __cyg_profile_func_exit(void*,void*) {}
int main(int argc,char** argv){try{demand(argc==2,"fixture root required");unit();live(argv[1]);
 std::cout<<"PASS rigid orientation, chirality, identity, eligibility, negatives and incumbent contracts\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
