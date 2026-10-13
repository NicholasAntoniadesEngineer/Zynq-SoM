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
  const auto& source=ctx.by_ref.at(ref);i.value=source.value;i.footprint=source.footprint;
  i.rotation=s.extra_rot.count(ref)?s.extra_rot.at(ref):0;
  i.side=offsets==&s.top_off?s.side:(s.side=="top"?"bottom":"top");
  i.mirror=s.mirror.count(ref);i.mod=ctx.pool.at(i.mirror?s.mirror.at(ref):g.resolvable.at(ref));
  i.pad_nets={{"1",{1,"signal_A"}},{"2",{2,"signal_B"}},{"3",{3,"return"}}};
  if(sheet!="unit") {
   i.pad_nets.clear();
   const auto stage=ctx.stage_input(sheet,g);
   for(const auto& pin:pad_names_from_text(i.mod->bytes)) {
    const auto net=stage.pad_nets.find({ref,pin});
    i.pad_nets.emplace(pin,std::make_pair(0,net==stage.pad_nets.end()?std::string{}:net->second));
   }
  }
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
 for(double value:{0.,1e-12,.000049,.000051,.1234,.12341,1.23456,999.999999}) {
  const auto positive=bottom_contact_shift(value),negative=bottom_contact_shift(-value);
  demand(positive>=value&&negative<=-value&&positive==-negative,
         "contact quantization moved toward the obstacle or broke reflection symmetry");
  demand(positive-value<=.000100001,"contact quantization added more than one output step");
  demand(bottom_contact_shift(positive)==positive,"contact quantization is not idempotent");
 }
 QuantizationCounts contact_counts;
 demand(bottom_contact_shift(.12341,&contact_counts)==.1235&&
        contact_counts.at("placement_bottom_pose_precision4dp")==2,
        "outward contact correction lost executed quantization work");
 for(double bad:{std::numeric_limits<double>::infinity(),-std::numeric_limits<double>::infinity(),
                 std::numeric_limits<double>::quiet_NaN()}) {
  bool rejected=false;
  try{(void)bottom_contact_shift(bad);}catch(const std::invalid_argument&){rejected=true;}
  demand(rejected,"nonfinite contact translation accepted");
 }
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
 g.side_of["R2"]="bottom";
 std::vector<std::string> bottom_events;
 const auto bottom_variants=bottom_shapes(ctx,g,"unit",{},std::nullopt,{},bottom_events);
 const auto bottom_repeat=bottom_shapes(ctx,g,"unit",{},std::nullopt,{},bottom_events);
 demand(!bottom_variants.empty()&&bottom_variants.size()==bottom_repeat.size(),"bottom alternatives repeat deterministically");
 for(std::size_t i=0;i<bottom_variants.size();++i) {
  const auto& candidate=bottom_variants[i];
  demand(equal(candidate,bottom_repeat[i]),"bottom variant changes across identical generation");
  for(const auto& ref:g.refs_by_sheet.at("unit"))
   demand(candidate.top_off.count(ref)+candidate.bot_off.count(ref)==1,"bottom alternative loses or duplicates member");
  for(std::size_t j=0;j<i;++j)
   demand(!same_zone_shape_geometry(candidate,bottom_variants[j]),"bottom alternative repeats physical geometry");
 }
 g.side_of["R2"]="top";
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
   dimensions=0;coordinates=0;bottom_coordinates=0;observing=true;auto result=build_pcb_zone_geometry(f.input);observing=false;
   const auto count=[&](const std::string& key){const auto p=result.quantization_engagements.find(key);
    return p==result.quantization_engagements.end()?0:p->second;};
   demand(count("placement_turn_dimension_precision4dp")==dimensions&&
          count("placement_turn_offset_precision4dp")==coordinates,"board trial entries missing from receipt");
   demand(count("placement_bottom_pose_precision4dp")==bottom_coordinates,"bottom enclosure work missing from receipt");
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
   demand((key=="placement_turn_dimension_precision4dp"||key=="placement_turn_offset_precision4dp"||key=="placement_bottom_pose_precision4dp")?
    actual>=n:actual==n,"unrelated counter changed");
  }
  for(const auto& [key,n]:after.quantization_engagements){(void)n;
   demand(before.quantization_engagements.count(key)||key=="placement_turn_dimension_precision4dp"||
    key=="placement_turn_offset_precision4dp"||key=="placement_bottom_pose_precision4dp","unexpected new engagement");
  }
  demand(before.fallback_events==after.fallback_events,"orientation manufactured fallback");
  std::cout<<project<<" appended="<<added<<" incumbent/prefix/old receipts unchanged\n";
  if(std::string(project)=="carrier") {
   auto power_input=f.input;
   for(const auto* sheet:{"power","power_som"})power_input.floorplan.spec->interior.at(sheet).layer="either";
   const auto power_zones=build_pcb_zone_geometry(power_input);
   Context power_context(power_input);power_context.pool=power_zones.footprints;
   for(const auto* sheet:{"power","power_som"}) {
    const auto& offers=power_zones.geometry.shapes.at(sheet);
    const auto base=std::find_if(offers.begin(),offers.end(),[](const auto& s){return s.tag=="bottom";});
    demand(base!=offers.end(),"eligible power template has no bottom incumbent");
    for(int turn=1;turn<=3;++turn) {
     const auto tag="bottom/r"+std::to_string(turn*90);
     const auto found=std::find_if(offers.begin(),offers.end(),[&](const auto& s){return s.tag==tag;});
     demand(found!=offers.end(),"eligible bottom power template missing quarter turn "+tag);
     const auto measured=model(*found,power_context,power_zones.geometry,sheet);
     demand(check_pcb_placement_contract(measured,sheet,&power_input.contracts.at(sheet),
             power_context.board_refs.at(sheet)).ok,"rotated bottom power template violated local contracts");
     auto expected=*base;for(int t=0;t<turn;++t)expected=turned(expected);
     const auto ref=expected.top_off.begin()->first;
     const FloorplanPoint shift{found->top_off.at(ref).first-expected.top_off.at(ref).first,
                               found->top_off.at(ref).second-expected.top_off.at(ref).second};
     for(bool primary:{false,true}) {
      const auto& old=primary?expected.top_off:expected.bot_off;
      const auto& actual=primary?found->top_off:found->bot_off;
      demand(old.size()==actual.size(),"power turn changed face assignment");
      for(const auto& [r,xy]:old)demand(std::abs(actual.at(r).first-xy.first-shift.first)<1e-4&&
          std::abs(actual.at(r).second-xy.second-shift.second)<1e-4,"power turn distorted rigid offsets");
     }
     demand(expected.extra_rot==found->extra_rot&&expected.mirror==found->mirror,"power turn changed mirror binding");
     for(std::size_t i=0;i<measured.model().insts.size();++i) {
      const auto b=measured.courtyard_at(i);
      demand(b.x0>=0&&b.y0>=0&&b.x1<=found->w&&b.y1<=found->h,"power turn clipped actual courtyard");
     }
    }
   }
   auto experiment=std::make_shared<FloorplanExperiment>();
   experiment->contract_group_face_sheets={"hdmi_rx_term"};f.input.floorplan.experiment=experiment;
   const auto near_shapes=build_pcb_zone_geometry(f.input);
   const auto& old_near=after.geometry.shapes.at("hdmi_rx_term");
   const auto& new_near=near_shapes.geometry.shapes.at("hdmi_rx_term");
   // The stage builder already supplies all four HDMI rigid turns, despite
   // the generic orientation helper excluding external contracts.
   demand(new_near.size()>=old_near.size()&&old_near.size()>=4,"HDMI existing rigid alternatives lost");
   for(std::size_t i=0;i<old_near.size();++i)
    demand(equal(old_near[i],new_near[i]),"HDMI incumbent offer changed");
   const auto prepared_near=prepare_pcb_floorplan(f.input,near_shapes);
   const auto hard_near=std::find_if(prepared_near.compose.index.hard.begin(),prepared_near.compose.index.hard.end(),
    [](const auto& t){return t.kind=="near_max"&&t.subject=="hdmi_rx_term"&&t.target_raw=="som_j2";});
   demand(hard_near!=prepared_near.compose.index.hard.end()&&hard_near->enforced&&hard_near->bound==10.,
          "HDMI alternatives lost or weakened hard proximity requirement");
   for(std::size_t i=1;i<new_near.size();++i){
    const auto& m=prepared_near.compose.shape_metrics.at({"hdmi_rx_term",static_cast<int>(i)});
    demand(m.zone_wh==FloorplanPoint{new_near[i].w,new_near[i].h}&&!m.pad_union.empty(),
           "HDMI alternative missing actual geometry for external evaluation");
   }
   experiment->contract_group_face_sheets={"uart_bridge"};
   const auto uart_shapes=build_pcb_zone_geometry(f.input);
   const auto prepared_uart=prepare_pcb_floorplan(f.input,uart_shapes);
   const auto hard_uart=std::find_if(prepared_uart.compose.index.hard.begin(),prepared_uart.compose.index.hard.end(),
    [](const auto& t){return t.kind=="near_max"&&t.subject=="uart_bridge"&&t.target_raw=="usb_uart_connector";});
   demand(hard_uart!=prepared_uart.compose.index.hard.end()&&hard_uart->enforced&&hard_uart->bound==40.,
          "UART alternatives lost or weakened hard proximity requirement");
   experiment->contract_group_face_sheets={"usb_jtag"};f.input.floorplan.experiment=experiment;
   bottom_coordinates=0;variant_dimensions=0;observing=true;
   auto split=build_pcb_zone_geometry(f.input);observing=false;
   demand(split.quantization_engagements.at("placement_bottom_pose_precision4dp")==bottom_coordinates&&
          split.quantization_engagements.at("placement_variant_dimension_precision4dp")==variant_dimensions,
          "actual mixed-face scalar operations differ from receipt");
   experiment->contract_group_face_sheets={"power_mon"};
   const auto monitor=build_pcb_zone_geometry(f.input);
   experiment->contract_group_face_sheets={"power"};
   const auto power_split=build_pcb_zone_geometry(f.input);
   const auto& power_originals=after.geometry.shapes.at("power");
   const auto& power_alternatives=power_split.geometry.shapes.at("power");
   demand(power_alternatives.size()>=power_originals.size(),"power expansion removed incumbent offers");
   for(std::size_t i=0;i<power_originals.size();++i)
    demand(equal(power_originals[i],power_alternatives[i]),"power expansion changed an existing shape index");
   Context split_power_context(f.input);split_power_context.pool=power_split.footprints;
   const auto original_power_model=model(power_originals.front(),split_power_context,power_split.geometry,"power");
   demand(check_pcb_placement_contract(original_power_model,"power",&f.input.contracts.at("power"),
          split_power_context.board_refs.at("power")).ok,"power seed no longer passes its local contract");
   bool seed_protrudes=false;
   for(std::size_t i=0;i<original_power_model.model().insts.size();++i) {
    const auto box=original_power_model.courtyard_at(i);
    if(box.x0<0||box.y0<0||box.x1>power_originals.front().w||box.y1>power_originals.front().h)
     seed_protrudes=true;
   }
   demand(seed_protrudes,"power enclosure witness no longer exercises an undersized stage envelope");
   std::size_t power_candidates=0,buck_candidates=0;
   for(const auto& candidate:power_split.geometry.shapes.at("power")) {
    if(candidate.tag.rfind("contract-bottom",0)!=0)continue;
    ++power_candidates;
    const auto checked=model(candidate,split_power_context,power_split.geometry,"power");
    demand(check_pcb_placement_contract(checked,"power",&f.input.contracts.at("power"),
             split_power_context.board_refs.at("power")).ok,"mixed power stage violates local hardware contract");
    demand(!candidate.top_off.empty()&&!candidate.bot_off.empty(),"power group offer is not actually mixed-face");
    for(const auto* local:{"U1","U2"})
     if(candidate.bot_off.count(split_power_context.board_refs.at("power").at(local)))++buck_candidates;
   }
   std::cout<<"power mixed candidates="<<power_candidates<<" moved buck stages="<<buck_candidates<<'\n';
   demand(power_candidates>0&&buck_candidates>0,"power stages still have no mixed-face alternatives");
   for(bool unknown_external:{false,true}) {
    auto blocked_input=f.input;
    if(unknown_external)for(auto& [key,value]:blocked_input.contracts.at("power").object_value)
     if(key=="external") {JsonNode unknown;unknown.kind=JsonKind::Bool;unknown.bool_value=true;
       value.object_value.emplace_back("unsupported_direction",unknown);}
    Context blocked(blocked_input);blocked.pool=after.footprints;
    demand(blocked.wired.count("power"),"power enforcement fixture is not wired");
    if(!unknown_external)blocked.wired.erase("power");
    auto geometry=after.geometry;
    append_contract_group_faces(blocked,geometry,"power",power_originals.front());
    demand(geometry.shapes.at("power").size()==power_originals.size(),
           "power expansion accepted unknown or unenforced external requirements");
   }
   const auto power_prepared=prepare_pcb_floorplan(f.input,power_split);
   for(const auto* kind:{"flow_hop","facing","far_min"})
    demand(std::any_of(power_prepared.compose.index.hard.begin(),power_prepared.compose.index.hard.end(),
        [&](const auto& term){return term.sheet=="power"&&term.kind==kind&&term.enforced;}),
        std::string("mixed-face power lost an enforced external requirement: ")+kind);
   experiment->contract_group_face_sheets={"usb_jtag","power_mon","power"};
   bottom_coordinates=0;variant_dimensions=0;observing=true;
   const auto combined=build_pcb_zone_geometry(f.input);observing=false;
   demand(combined.quantization_engagements.at("placement_bottom_pose_precision4dp")==bottom_coordinates&&
          combined.quantization_engagements.at("placement_variant_dimension_precision4dp")==variant_dimensions,
          "multi-sheet actual scalar operations differ from receipt");
   demand(monitor.geometry.shapes.at("power_mon").size()>after.geometry.shapes.at("power_mon").size(),
          "second selected sheet contributed no candidates");
   for(const auto& [name,actual]:combined.geometry.shapes){
    const auto& expected=(name=="usb_jtag"?split:name=="power_mon"?monitor:name=="power"?power_split:after).geometry.shapes.at(name);
    demand(actual.size()==expected.size(),"multi-sheet altered unrelated offer count: "+name);
    for(std::size_t i=0;i<actual.size();++i)demand(equal(actual[i],expected[i]),"multi-sheet offers differ from independent sheet: "+name);
   }
   experiment->contract_group_face_sheets={"power","power_mon","usb_jtag"};
   const auto combined_repeat=build_pcb_zone_geometry(f.input);
   demand(combined.quantization_engagements==combined_repeat.quantization_engagements,
          "multi-sheet declaration order changed operation receipt");
   for(const auto& [name,actual]:combined.geometry.shapes){
    const auto& repeated=combined_repeat.geometry.shapes.at(name);
    demand(actual.size()==repeated.size(),"multi-sheet replay offer count changed");
    for(std::size_t i=0;i<actual.size();++i)demand(equal(actual[i],repeated[i]),"multi-sheet replay geometry changed");
   }
   const auto count=[](const auto& result,const std::string& key){
    const auto p=result.quantization_engagements.find(key);return p==result.quantization_engagements.end()?std::size_t{}:p->second;
   };
   for(const auto& [key,n]:combined.quantization_engagements)
    demand(n+2*count(after,key)==count(split,key)+count(monitor,key)+count(power_split,key),"multi-sheet work differs from independent per-sheet deltas: "+key);
   experiment->contract_group_face_sheets.insert("missing-sheet");bool unknown=false;
   try{(void)build_pcb_zone_geometry(f.input);}catch(const PcbZoneInfeasible&){unknown=true;}
   demand(unknown,"unknown additional sheet must not be silently ignored");
   experiment->contract_group_face_sheets={"usb_jtag"};
   experiment->contract_group_rotations=true;
   bottom_coordinates=0;variant_dimensions=0;observing=true;
   const auto group_turns=build_pcb_zone_geometry(f.input);observing=false;
   demand(group_turns.quantization_engagements.at("placement_bottom_pose_precision4dp")==bottom_coordinates&&
          group_turns.quantization_engagements.at("placement_variant_dimension_precision4dp")==variant_dimensions,
          "group-only rotation operations differ from receipts");
   const auto group_repeat=build_pcb_zone_geometry(f.input);
   demand(group_turns.quantization_engagements==group_repeat.quantization_engagements,
          "group-only rotation receipts not reproducible");
   const auto& offers=group_turns.geometry.shapes.at("usb_jtag");
   const auto& originals=split.geometry.shapes.at("usb_jtag");
   demand(offers.size()>originals.size(),"group-only rotations added no candidates");
   demand(offers.size()==group_repeat.geometry.shapes.at("usb_jtag").size(),"group-only count not reproducible");
   Context gc(f.input);gc.pool=group_turns.footprints;
   const auto base=model(originals.front(),gc,group_turns.geometry,"usb_jtag");
   std::map<std::string,std::size_t> base_indices;
   for(std::size_t i=0;i<base.model().insts.size();++i)base_indices.emplace(base.model().insts[i].ref,i);
   std::set<int> seen_turns;
   std::size_t pair_candidates=0,contact_candidates=0;
   for(std::size_t n=0;n<offers.size();++n) {
    demand(equal(offers[n],group_repeat.geometry.shapes.at("usb_jtag")[n]),"group-only geometry not reproducible");
    if(offers[n].tag.rfind("contract-bottom-pair/",0)==0) {
     ++pair_candidates;
     if(const auto contact=offers[n].tag.find("/contact/");contact!=std::string::npos) {
      ++contact_candidates;
      const auto plus=offers[n].tag.find('+');
      const auto atag=offers[n].tag.substr(std::string("contract-bottom-pair/").size(),
          plus-std::string("contract-bottom-pair/").size());
      const auto btag=offers[n].tag.substr(plus+1,contact-plus-1);
      const auto a=std::find_if(offers.begin(),offers.end(),[&](const auto& s){return s.tag==atag;});
      const auto b=std::find_if(offers.begin(),offers.end(),[&](const auto& s){return s.tag==btag;});
      demand(a!=offers.end()&&b!=offers.end(),"contact repair lost its independently legal parent groups");
      demand(offers[n].top_off==a->top_off||offers[n].top_off.size()<a->top_off.size(),"contact repair added top parts");
      std::optional<FloorplanPoint> delta;
      for(const auto& [ref,xy]:offers[n].bot_off) {
       if(originals.front().top_off.count(ref)&&b->bot_off.count(ref)) {
        const auto old=b->bot_off.at(ref);const FloorplanPoint d{xy.first-old.first,xy.second-old.second};
        if(!delta)delta=d;
        demand(std::abs(d.first-delta->first)<1e-4&&std::abs(d.second-delta->second)<1e-4,
               "contact repair distorted a rigid group");
        demand(offers[n].extra_rot.at(ref)==b->extra_rot.at(ref)&&offers[n].mirror.at(ref)==b->mirror.at(ref),
               "contact repair changed rotation or chirality");
       }else demand(xy==a->bot_off.at(ref),"contact repair moved the other bottom group");
      }
      for(const auto& [ref,xy]:offers[n].top_off)demand(xy==a->top_off.at(ref),"contact repair moved a remaining top part");
      demand(delta&&(std::abs(delta->first)>0||std::abs(delta->second)>0),"contact repair did not translate any group");
     }
     const auto measured=model(offers[n],gc,group_turns.geometry,"usb_jtag");
     demand(check_pcb_placement_contract(measured,"usb_jtag",&f.input.contracts.at("usb_jtag"),gc.board_refs.at("usb_jtag")).ok,
            "combined bottom groups violated local contracts");
     demand(check_fanout(measured,0).ok,"combined bottom groups starved fanout");
     for(std::size_t i=0;i<measured.model().insts.size();++i) {
      const auto& part=measured.model().insts[i];
      demand(part.pad_nets==base.model().insts[base_indices.at(part.ref)].pad_nets,
             "combined bottom groups changed net identity");
      if(part.side!="bottom")continue;
      const auto a=measured.courtyard_at(i);
      for(std::size_t j=0;j<i;++j)if(measured.model().insts[j].side=="bottom") {
       const auto b=measured.courtyard_at(j);
       demand(a.x1+gc.clearance<=b.x0||b.x1+gc.clearance<=a.x0||
              a.y1+gc.clearance<=b.y0||b.y1+gc.clearance<=a.y0,
              "individually valid groups collide when combined on bottom");
      }
     }
     for(const auto* owner:{"U2","U4"})
      demand(offers[n].bot_off.count(gc.board_refs.at("usb_jtag").at(owner)),"combined candidate lacks both movable owners");
     if(n<originals.size())demand(equal(offers[n],originals[n]),"group rotations rewrote original pair");
     continue;
    }
    if(n<originals.size()){demand(equal(offers[n],originals[n]),"group rotations rewrote existing prefix");continue;}
    const auto& offer=offers[n];const auto pos=offer.tag.find("/group-r");
    demand(pos!=std::string::npos,"new group candidate missing orientation tag");
    const int turns=std::stoi(offer.tag.substr(pos+8))/90;seen_turns.insert(turns);
    const auto transform=[&](FloorplanPoint p){p.first=-p.first;for(int t=0;t<turns;++t)p={p.second,-p.first};return p;};
    const auto measured=model(offer,gc,group_turns.geometry,"usb_jtag");
    demand(check_pcb_placement_contract(measured,"usb_jtag",&f.input.contracts.at("usb_jtag"),gc.board_refs.at("usb_jtag")).ok,
           "group rotation violated local contract");
    const auto fanout=check_fanout(measured,0);
    demand(fanout.n_subjects>0&&fanout.ok,"group rotation fanout missing subjects or violated clearance");
    std::optional<FloorplanPoint> delta;
    for(std::size_t i=0;i<measured.model().insts.size();++i) {
     const auto& part=measured.model().insts[i];const auto oi=base_indices.at(part.ref);
     const auto& old=base.model().insts[oi];
     if(!offer.mirror.count(part.ref)) {
      demand(part.x==old.x&&part.y==old.y&&part.rotation==old.rotation&&part.side==old.side,
             "group rotation moved stationary part");continue;
     }
     const auto origin=transform({old.x,old.y});const FloorplanPoint shift{part.x-origin.first,part.y-origin.second};
     if(!delta)delta=shift;
     demand(std::abs(shift.first-delta->first)<1.1e-4&&std::abs(shift.second-delta->second)<1.1e-4,
            "group rotation lost rigid membership");
     for(const auto& [pin,box]:base.geometry_at(oi).pad_boxes) {
      const auto expected=transform(rect_center(box));const auto actual=rect_center(measured.geometry_at(i).pad_boxes.at(pin));
      demand(std::abs(actual.first-expected.first-shift.first)<1e-8&&
             std::abs(actual.second-expected.second-shift.second)<1e-8,"group-only pad transform wrong");
     }
    }
    const auto bound=bind_pcb_zone_shapes(group_turns,{{"usb_jtag",static_cast<int>(n)}});
    demand(gc.stage_input("usb_jtag",bound).pad_nets==gc.stage_input("usb_jtag",after.geometry).pad_nets,
           "group-only rotation changed net identity");
   }
   demand(seen_turns==std::set<int>{1,2,3},"missing legal group-only quarter turn");
   demand(pair_candidates>0,"no combined bottom-group assignments exercised");
   demand(contact_candidates>0,"colliding bottom groups yielded no geometry-directed contact repairs");
   std::cout<<"contact bottom candidates="<<contact_candidates<<'\n';
   std::cout<<"combined bottom candidates="<<pair_candidates<<'\n';
   std::cout<<"carrier independent group rotations="<<offers.size()-originals.size()<<'\n';
   // Synthetic packages: a third disconnected physical pad makes former
   // two-pin passives fanout subjects/crowders without changing their poses.
   // This catches both empty pin maps and connected-only pin counting.
   auto crowded=gc;auto crowded_geometry=after.geometry;std::set<std::string> replaced;
   for(const auto& ref:crowded_geometry.refs_by_sheet.at("usb_jtag")) {
    const auto key=crowded_geometry.resolvable.at(ref);
    if(!replaced.insert(key).second)continue;
    const auto fp=crowded.pool.at(key);
    if(pad_names_from_text(fp->bytes).size()!=2)continue;
    auto bytes=fp->bytes;
    bytes.insert(bytes.rfind(')')," (pad \"UNCONNECTED_TEST\" smd rect (at 0 0) (size 0.01 0.01) (layers \"F.Cu\"))");
    crowded.pool[key]=pcb_check_footprint(fp->source,bytes);crowded.pool.erase("@mirror/"+key);
   }
   demand(!check_fanout(model(originals.front(),crowded,crowded_geometry,"usb_jtag"),0).ok,
          "disconnected-pad crowding fixture did not exercise rejection");
   append_contract_group_faces(crowded,crowded_geometry,"usb_jtag",originals.front(),true);
   demand(crowded_geometry.shapes.at("usb_jtag").size()==after.geometry.shapes.at("usb_jtag").size(),
          "fanout-starved disconnected-pad candidates were offered");
   experiment->contract_group_rotations=false;
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
   std::size_t candidates=0,rotated_candidates=0,nonshrinking_candidates=0;
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
    if(candidate.w*candidate.h>=variants.front().w*variants.front().h) {
     ++nonshrinking_candidates;
     demand(candidate.top_off.size()<variants.front().top_off.size()&&
            candidate.bot_off.size()>variants.front().bot_off.size(),
            "nonshrinking face candidate did not free top-side occupancy");
    }
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
   demand(nonshrinking_candidates>0,"valid nonshrinking bottom assignments were pruned by local area");
   std::cout<<"nonshrinking face candidates="<<nonshrinking_candidates<<'\n';
   demand(rotated_candidates==3*(candidates-rotated_candidates),"new groups missing legal quarter turns");
   auto blocked_context=candidate_context;
   for(const auto* owner:{"U2","U4"})blocked_context.by_ref.at(blocked_context.board_refs.at("usb_jtag").at(owner)).lib_id="Switch:SW_SPST";
   auto blocked_geometry=after.geometry;
   append_contract_group_faces(blocked_context,blocked_geometry,"usb_jtag",variants.front());
   append_contract_group_faces(blocked_context,blocked_geometry,"usb_jtag",variants.front(),true);
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
   append_contract_group_faces(protruding_context,protruding_geometry,"usb_jtag",variants.front(),true);
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
