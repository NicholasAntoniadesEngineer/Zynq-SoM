#include "pcb_placement_orientations.hpp"
#include "pcb_placement_fixture.hpp"
#include "contract_rigid_groups_internal.hpp"
#include "floorplan_internal.hpp"
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
 // Pair-search inputs arrive one corner alignment at a time. Coincident
 // alignments must not multiply pair work, while a different rotation stays.
 std::vector<Shape> pair_inputs;
 for(const auto& candidate:{side_changed,side_changed,rotated_changed,side_changed})
  append_distinct_zone_shapes(sparse,pair_inputs,{candidate});
 demand(pair_inputs.size()==2&&equal(pair_inputs[0],side_changed)&&equal(pair_inputs[1],rotated_changed),
        "pair input dedup must retain first representatives and distinct rotations");
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
 // One independently movable component is not less eligible than a larger
 // connected group. Keep the service-access component fixed on top.
 input.contracts["unit"]=parse_json_text(R"({"contract":"placement/v2","structures":[{"type":"same_side","ics":["A"]}]})");
 auto single=seed;single.extra_rot.clear();single.bot_off.clear();
 single.top_off={{"R1",{5,4}},{"R2",{15,11}}};
 ctx.by_ref["R2"].lib_id="Switch:SW_SPST";
 g.shapes.clear();append_contract_group_faces(ctx,g,"unit",single);
 demand(g.shapes.count("unit")&&g.shapes.at("unit").size()>1,
        "independent singleton was excluded by group cardinality");
 demand(equal(g.shapes.at("unit").front(),single),"singleton exploration replaced incumbent");
 for(const auto& candidate:g.shapes.at("unit")) {
  if(candidate.tag.rfind("contract-bottom",0)!=0)continue;
  demand(candidate.bot_off.count("R1")&&candidate.top_off.count("R2")&&
         !candidate.bot_off.count("R2"),"singleton exploration moved top-access part");
  const auto checked=model(candidate,ctx,g);
  demand(check_pcb_placement_contract(checked,"unit",&input.contracts.at("unit"),ctx.board_refs.at("unit")).ok&&
         check_fanout(checked,0).ok,"singleton failed independent geometry/contract/fanout check");
  for(std::size_t i=0;i<checked.model().insts.size();++i) {
   const auto bounds=checked.courtyard_at(i);
   demand(bounds.x0>=0&&bounds.y0>=0&&bounds.x1<=candidate.w&&bounds.y1<=candidate.h,
          "singleton courtyard escaped candidate envelope");
  }
  const auto moved=std::find_if(checked.model().insts.begin(),checked.model().insts.end(),
      [](const auto& inst){return inst.ref=="R1";});
  demand(moved!=checked.model().insts.end()&&handed(model(single,ctx,g),0)*
         handed(checked,static_cast<std::size_t>(moved-checked.model().insts.begin()))<0,
         "singleton bottom move lost chirality");
 }
 const auto singleton_once=g.shapes.at("unit");
 append_contract_group_faces(ctx,g,"unit",single);
 demand(g.shapes.at("unit").size()==singleton_once.size(),"singleton replay accumulated duplicate offers");
 for(std::size_t i=0;i<singleton_once.size();++i)
  demand(equal(g.shapes.at("unit")[i],singleton_once[i]),"singleton replay changed deterministic order");
 input.contracts["unit"]=parse_json_text(R"({"contract":"placement/v2","structures":[{"type":"proximity","anchor":"A","members":["B"],"max_mm":30,"same_side":true}]})");
 // A connector pins its own group, not an unrelated group on the same sheet.
 const auto connector_contract=input.contracts.at("unit");
 input.contracts["unit"]=parse_json_text(R"({"contract":"placement/v2","structures":[{"type":"same_side","ics":["A"]}]})");
 ctx.by_ref["R2"].lib_id="Connector_Generic:Conn_01x03";
 g.shapes.clear();append_rigid_zone_orientations(ctx,g,"unit",single);
 demand(g.shapes.empty(),"connector sheet gained whole-sheet rotations");
 append_contract_group_faces(ctx,g,"unit",single,true,true);
 demand(g.shapes.count("unit")&&g.shapes.at("unit").size()>1,
        "connector blocked an independent bottom group");
 for(const auto& candidate:g.shapes.at("unit")) {
  demand(candidate.top_off.at("R2")==single.top_off.at("R2")&&
         !candidate.bot_off.count("R2")&&!candidate.mirror.count("R2")&&
         (!candidate.extra_rot.count("R2")||candidate.extra_rot.at("R2")==0),
         "connector pose changed during face exploration or leftover compaction");
 }
 auto protruding_connector=single;protruding_connector.top_off["R2"]={0,0};
 g.shapes.clear();append_contract_group_faces(ctx,g,"unit",protruding_connector,true,true);
 demand(g.shapes.empty(),"connector was implicitly translated to enclose a protruding seed");
 input.contracts["unit"]=connector_contract;
 g.shapes.clear();append_contract_group_faces(ctx,g,"unit",single,true,true);
 demand(g.shapes.empty(),"connector-connected group moved to bottom");
 ctx.by_ref["R2"].lib_id="Switch:SW_SPST";
 g.shapes.clear();append_contract_group_faces(ctx,g,"unit",single);
 demand(g.shapes.empty(),"singleton face exploration split a group pinned by service access");
 // The same connected group becomes eligible when no member needs top access.
 // There is no stationary remainder: that is not a reason to reject the move.
 ctx.by_ref["R2"].lib_id="Device:R";
 g.shapes.clear();append_contract_group_faces(ctx,g,"unit",single,true);
 demand(g.shapes.count("unit")&&g.shapes.at("unit").size()==5,
        "whole-sheet group must offer all four bottom orientations plus incumbent");
 PcbZoneResult whole_zones;whole_zones.geometry=g;whole_zones.footprints=ctx.pool;
 std::size_t whole_index=0;
 for(const auto& candidate:g.shapes.at("unit")) {
  const auto index=whole_index++;
  if(candidate.tag.rfind("contract-bottom",0)!=0)continue;
  demand(candidate.side=="bottom"&&candidate.top_off.size()==2&&candidate.bot_off.empty()&&candidate.mirror.size()==2,
         "whole-sheet face move lost members or mirror binding");
  const auto checked=model(candidate,ctx,g);
  const auto bound=bind_pcb_zone_shapes(whole_zones,{{"unit",static_cast<int>(index)}});
  for(const auto& [ref,key]:candidate.mirror)
   demand(bound.side_of.at(ref)=="bottom"&&bound.resolvable.at(ref)==key&&bound.mirror_refs.count(ref),
          "whole-sheet binding lost physical bottom face or mirrored footprint");
  demand(check_pcb_placement_contract(checked,"unit",&input.contracts.at("unit"),ctx.board_refs.at("unit")).ok&&
         check_fanout(checked,0).ok,"whole-sheet group failed contract/fanout checks");
  for(std::size_t i=0;i<checked.model().insts.size();++i) {
   const auto bounds=checked.courtyard_at(i);
   demand(bounds.x0>=0&&bounds.y0>=0&&bounds.x1<=candidate.w&&bounds.y1<=candidate.h,
          "whole-sheet bottom rotation clipped a courtyard");
   demand(handed(model(single,ctx,g),i)*handed(checked,i)<0,
          "whole-sheet bottom rotation lost chirality");
  }
 }
 const auto whole_once=g.shapes.at("unit");
 append_contract_group_faces(ctx,g,"unit",single,true);
 demand(g.shapes.at("unit").size()==whole_once.size(),"whole-sheet replay accumulated duplicates");
 for(std::size_t i=0;i<whole_once.size();++i)
  demand(equal(g.shapes.at("unit")[i],whole_once[i]),"whole-sheet replay changed deterministic order");
 // Exercise the real selector with these generated offers, not a separately
 // manufactured bottom flag. Physical geometry and binding are checked above.
 FloorplanInput selection;selection.som.w=selection.som.h=8;
 selection.module_offset=FloorplanPoint{0,0};selection.compact_search=true;
 selection.geometry.shapes["unit"]=whole_once;
 for(const auto& [key,footprint]:ctx.pool)
  selection.footprints[key]={footprint->source,footprint->document};
 auto required=std::make_shared<FloorplanExperiment>();required->require_bottom_sheets={"unit"};
 selection.experiment=required;
 floorplan_detail::Engine selector(selection);selector.board_size(80,70);selector.plan.punch_free=true;
 FloorplanBlock block;block.name="unit";block.kind="interior";block.zone="E";
 block.w=single.w;block.h=single.h;
 selector.plan.interior_blocks.push_back(block);selector.zbox["unit"]={single.w,single.h};
 for(const auto& candidate:whole_once)
  selector.shape_sets[1]["unit"].push_back({candidate.w,candidate.h,{},{},candidate.side,{}});
 demand(selector.attempt_pack_impl(false),"generated whole-bottom offers cannot satisfy required-bottom selection");
 const auto& placed=selector.plan.interior_blocks.at(0);
 demand(placed.shape_idx>0&&placed.side=="bottom"&&whole_once.at(placed.shape_idx).side=="bottom",
        "required-bottom selector did not choose a generated bottom-primary offer");
 // Opposite-face empty space is not physical occupancy. Reserve separate
 // courtyards while retaining each component's fanout and THT punches.
 FloorplanInput granular;granular.som.w=granular.som.h=8;granular.compact_search=true;
 std::string device="(footprint test (layer F.Cu) (fp_rect (start -1 -1) (end 1 1) (stroke (width .05) (type default)) (layer F.CrtYd))";
 for(int pin=1;pin<=8;++pin)device+=" (pad \""+std::to_string(pin)+"\" smd rect (at 0 0) (size .2 .2) (layers F.Cu))";
 device+=" (pad \"9\" thru_hole circle (at 0 0) (size .8 .8) (drill .4) (layers *.Cu *.Mask)))";
 const auto device_fp=pcb_check_footprint("test.kicad_mod",device);
 granular.footprints["test"]={device_fp->source,device_fp->document};
 for(const auto* ref:{"U1","U2"}) {
  granular.geometry.resolvable[ref]="test";granular.geometry.bbox_of[ref]=*device_fp->bbox;
 }
 for(const auto* primary:{"top","bottom"}) {
  Shape islands;islands.w=24;islands.h=5;islands.side=primary;
  islands.bot_off={{"U1",{2,2}},{"U2",{20,2}}};
  granular.experiment.reset();floorplan_detail::Engine union_engine(granular);
  QuantizationCounts united_counts,split_counts;
  const auto united=union_engine.zone_components(islands,true,&united_counts);
  auto policy=std::make_shared<FloorplanExperiment>();policy->granular_minor_occupancy=true;
  granular.experiment=policy;floorplan_detail::Engine split_engine(granular);
  const auto split=split_engine.zone_components(islands,true,&split_counts);
  demand(united.size()==3&&split.size()==4,"granular minority occupancy lost court or THT punch");
  const int face=std::string(primary)=="top"?2:1;
  demand(split[0].mask==face&&split[1].mask==face&&split[2].mask==3&&split[3].mask==3,
         "granular occupancy has incorrect physical face masks");
  demand(split[0].w*split[0].h+split[1].w*split[1].h<united[0].w*united[0].h,
         "granular minority occupancy did not release empty space");
  for(std::size_t i=0;i<2;++i) {
   demand(split[i].reach.w>0&&split[i].reach.e>0&&split[i].reach.n>0&&split[i].reach.s>0,
          "granular occupancy discarded individual fanout halo");
   demand(split[i+2].dx==united[i+1].dx&&split[i+2].dy==united[i+1].dy&&
          split[i+2].w==united[i+1].w&&split[i+2].h==united[i+1].h,
          "granular occupancy changed through-hole punches");
  }
  demand(split_counts.at("pack_zone_component_precision4dp")==16&&
         united_counts.at("pack_zone_component_precision4dp")==12,
         "granular occupancy dropped executed component quantization work");
  Occupancy coarse_grid(30,12,.2,2,3,1,.05),fine_grid(30,12,.2,2,3,1,.05);
  const int primary_mask=face==1?2:1;
  coarse_grid.add(0,0,24,5,{},{},primary_mask,united);
  fine_grid.add(0,0,24,5,{},{},primary_mask,split);
  demand(!coarse_grid.fits_exhaustive(10,2,1,1,{},{},face,{})&&
          fine_grid.fits_exhaustive(10,2,1,1,{},{},face,{}),
         "granular occupancy did not permit the physically empty opposite-face gap");
  demand(!fine_grid.fits_exhaustive(2,2,.2,.2,{},{},face,{})&&
         !fine_grid.fits_exhaustive(3.25,2,.2,.2,{},{},face,{}),
         "granular occupancy lost body or fanout collision rejection");
  auto primary_islands=islands;primary_islands.top_off=primary_islands.bot_off;primary_islands.bot_off.clear();
  const auto primary_children=split_engine.zone_components(primary_islands,true,&split_counts,true);
  demand(primary_children.size()==4&&primary_children[0].mask==primary_mask&&
         primary_children[1].mask==primary_mask&&primary_children[2].mask==3&&primary_children[3].mask==3,
         "component-primary producer lost physical faces or THT punches");
  Occupancy primary_grid(30,12,.2,2,3,1,.05);
  primary_grid.add(0,0,24,5,{},{},0,primary_children);
  demand(primary_grid.fits_exhaustive(10,2,1,1,{},{},primary_mask,{})&&
         !primary_grid.fits_exhaustive(2,2,.2,.2,{},{},primary_mask,{})&&
         !primary_grid.fits_exhaustive(3.25,2,.2,.2,{},{},primary_mask,{}),
         "component-primary producer lost gap reuse, body or fanout protection");
 }
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
   experiment->contract_group_face_sheets={"fmc"};f.input.floorplan.experiment=experiment;
   const auto fmc_shapes=build_pcb_zone_geometry(f.input);
   const auto& old_fmc=after.geometry.shapes.at("fmc");
   const auto& new_fmc=fmc_shapes.geometry.shapes.at("fmc");
   std::cout<<"FMC connector-pinned offers="<<new_fmc.size()<<" before="<<old_fmc.size()<<'\n';
   demand(new_fmc.size()>old_fmc.size(),"FMC independent regulator group has no bottom alternatives");
   Context fmc_context(f.input);fmc_context.pool=fmc_shapes.footprints;
   const auto connector=fmc_context.board_refs.at("fmc").at("J1");
   const auto regulator=fmc_context.board_refs.at("fmc").at("U1");
   for(std::size_t i=0;i<old_fmc.size();++i)
    demand(equal(old_fmc[i],new_fmc[i]),"FMC incumbent prefix changed");
   for(std::size_t i=old_fmc.size();i<new_fmc.size();++i) {
    const auto& candidate=new_fmc[i];
    demand(candidate.top_off.at(connector)==old_fmc.front().top_off.at(connector)&&
           !candidate.bot_off.count(connector)&&!candidate.mirror.count(connector),
           "FMC header pose changed while regulator moved");
    demand(candidate.bot_off.count(regulator),"FMC new offer did not move independent regulator");
    const auto checked=model(candidate,fmc_context,fmc_shapes.geometry,"fmc");
    demand(check_pcb_placement_contract(checked,"fmc",&f.input.contracts.at("fmc"),
              fmc_context.board_refs.at("fmc")).ok&&check_fanout(checked,0).ok,
           "FMC alternative violates local contract or fanout");
   }
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
   experiment->contract_group_face_sheets={"power_som"};
   const auto som_split=build_pcb_zone_geometry(f.input);
   Context som_context(f.input);som_context.pool=som_split.footprints;
   const auto& som_originals=after.geometry.shapes.at("power_som");
   const auto& som_offers=som_split.geometry.shapes.at("power_som");
   experiment->component_reservation_sheets={"power_som"};
   const auto prepared_components=prepare_pcb_floorplan(f.input,som_split);
   floorplan_detail::Engine component_engine(prepared_components);component_engine.initialize();component_engine.prepare_geometry();
   demand(!component_engine.component_shapes.empty(),"real power_som offers have no eligible component reservations");
   std::size_t preparation_ops=0;
   for(const auto& [name,n]:component_engine.plan.accounting.quantization_engagements){(void)name;preparation_ops+=n;}
   std::cout<<"component_preparation_operations="<<preparation_ops<<'\n';
   for(const auto& key:component_engine.component_shapes) {
    demand(key.first=="power_som"&&component_engine.reservation_mask(key.first,key.second,"top")==0,
           "component reservation selection escaped requested sheet");
    for(const int policy:{0,1}) {
     const auto& physical=component_engine.components[policy].at(key);
     demand(!physical.empty(),"eligible component candidate lost its children");
     auto shape=prepared_components.geometry.shapes.at(key.first).at(key.second);
     if(key.second==0) {
      shape={};const auto wh=prepared_components.geometry.zone_box.at(key.first);
      shape.w=wh.first;shape.h=wh.second;
      shape.top_off=prepared_components.geometry.top_off.at(key.first);
      shape.bot_off=prepared_components.geometry.bot_off.at(key.first);
      shape.extra_rot=prepared_components.geometry.zone_extra_rot;
     }
     const auto reference=component_engine.zone_components(shape,policy!=0,nullptr,true);
     demand(physical.size()==reference.size(),"prepared component count differs from direct kernel");
     const auto signature=[](const Comp& c){return std::make_tuple(c.dx,c.dy,c.w,c.h,c.mask,
         c.reach.w,c.reach.e,c.reach.n,c.reach.s,c.inset.w,c.inset.e,c.inset.n,c.inset.s);};
     for(std::size_t j=0;j<physical.size();++j)
      demand(signature(physical[j])==signature(reference[j]),"prepared courtyard, punch or fanout differs from direct kernel");
    }
   }
   auto incomplete_components=prepared_components;
   incomplete_components.geometry.refs_by_sheet.at("power_som").pop_back();
   floorplan_detail::Engine incomplete_engine(incomplete_components);
   incomplete_engine.initialize();incomplete_engine.prepare_geometry();
   demand(incomplete_engine.component_shapes.empty(),"incomplete member census reused eligible component state");
   for(const auto& key:component_engine.component_shapes)
    demand(incomplete_engine.reservation_mask(key.first,key.second,"top")==floorplan_detail::occ_top,
           "ineligible candidate lost its solid reservation");
   experiment->component_reservation_sheets.clear();
   std::size_t rebased=0;
   for(const auto& candidate:som_offers)if(auto other=opposite_primary_reservation(candidate)) {
    ++rebased;
    const auto roundtrip=opposite_primary_reservation(*other);
    demand(roundtrip&&same_zone_shape_geometry(candidate,*roundtrip),"primary rebase is not an involution");
    const auto original_model=model(candidate,som_context,som_split.geometry,"power_som");
    const auto alternate_model=model(*other,som_context,som_split.geometry,"power_som");
    for(const auto& a:original_model.model().insts) {
     const auto b=std::find_if(alternate_model.model().insts.begin(),alternate_model.model().insts.end(),
                             [&](const auto& part){return part.ref==a.ref;});
     demand(b!=alternate_model.model().insts.end()&&a.x==b->x&&a.y==b->y&&a.rotation==b->rotation&&
            a.mod==b->mod&&a.side==b->side&&a.mirror==b->mirror&&a.pad_nets==b->pad_nets,
            "reservation rebase changed physical geometry, face or connectivity");
    }
    auto invalid=candidate;invalid.mirror["not-a-member"]="unknown";
    demand(!opposite_primary_reservation(invalid),"foreign mirrored member accepted");
    auto one_face=candidate;one_face.bot_off.clear();
    demand(!opposite_primary_reservation(one_face),"single-face pack rebased");
   }
   demand(rebased>0,"no real mixed-face reservation rebase tested");
   experiment->dual_primary_reservations=true;
   bool invalid_primary=false;
   try{(void)build_pcb_zone_geometry(f.input);}catch(const std::invalid_argument&){invalid_primary=true;}
   demand(invalid_primary,"dual primary mode accepted without granular occupancy");
   experiment->granular_minor_occupancy=true;
   const auto dual=build_pcb_zone_geometry(f.input);
   const auto& dual_offers=dual.geometry.shapes.at("power_som");
   demand(dual_offers.size()>som_offers.size(),"dual primary offers not propagated through zone build");
   for(std::size_t i=0;i<som_offers.size();++i)
    demand(equal(som_offers[i],dual_offers[i]),"dual primary changed existing candidate/index");
   for(std::size_t i=som_offers.size();i<dual_offers.size();++i) {
    const auto bound=bind_pcb_zone_shapes(dual,{{"power_som",static_cast<int>(i)}});
    const auto physical=model(dual_offers[i],som_context,dual.geometry,"power_som");
    for(const auto& part:physical.model().insts)
     demand(bound.side_of.at(part.ref)==part.side,"bound reservation changed a physical face");
    auto corrupt=dual;
    corrupt.geometry.shapes.at("power_som")[i].top_off.begin()->second.first+=1;
    bool rejected=false;
    try{(void)bind_pcb_zone_shapes(corrupt,{{"power_som",static_cast<int>(i)}});}
    catch(const PcbZoneInfeasible&){rejected=true;}
    demand(rejected,"modified physical pose accepted as a reservation-only rebase");
   }
   experiment->dual_primary_reservations=false;experiment->granular_minor_occupancy=false;
   demand(som_offers.size()>som_originals.size(),"SoM power has no additional face offers");
   for(std::size_t i=0;i<som_originals.size();++i)
    demand(equal(som_originals[i],som_offers[i]),"SoM power expansion changed an incumbent");
   bool som_buck_bottom=false;
   std::size_t som_contact_offers=0;
   for(const auto& candidate:som_offers) {
    if(candidate.tag.rfind("contract-bottom",0)!=0)continue;
    const auto checked=model(candidate,som_context,som_split.geometry,"power_som");
    demand(check_pcb_placement_contract(checked,"power_som",&f.input.contracts.at("power_som"),
           som_context.board_refs.at("power_som")).ok,"SoM power face offer violates its local contract");
    demand(check_fanout(checked,0).ok,"SoM power face offer starves physical-pad fanout");
    som_buck_bottom|=candidate.bot_off.count(som_context.board_refs.at("power_som").at("U4"))!=0;
    for(const auto& inst:checked.model().insts)
     if(face_top(som_context.by_ref.at(inst.ref)))demand(inst.side=="top","SoM service access moved underneath");
    if(candidate.tag.find("/contact/")!=std::string::npos) {
     ++som_contact_offers;
     demand(candidate.w*candidate.h<24.4399*40.4904,
            "SoM contact repair did not improve the original corner-only bottom envelope");
     std::optional<FloorplanPoint> translation;
     for(const auto& [ref,xy]:candidate.bot_off) {
      const auto old=som_originals.front().top_off.find(ref);
      if(old==som_originals.front().top_off.end())continue;
      const FloorplanPoint delta{xy.first+old->second.first,xy.second-old->second.second};
      if(!translation)translation=delta;
      demand(std::abs(delta.first-translation->first)<1.1e-4&&
             std::abs(delta.second-translation->second)<1.1e-4,
             "single-group contact repair distorted mirrored rigid membership");
     }
     demand(translation.has_value(),"single-group contact repair moved no original top components");
     for(std::size_t i=0;i<checked.model().insts.size();++i) {
      const auto a=checked.courtyard_at(i);
      demand(a.x0>=0&&a.y0>=0&&a.x1<=candidate.w&&a.y1<=candidate.h,
             "single-group contact repair escaped its envelope");
      for(std::size_t j=0;j<i;++j) {
       const auto& pi=checked.model().insts[i];const auto& pj=checked.model().insts[j];
       if(pi.side!=pj.side&&!has_thru_pads_from_text(pi.mod->bytes)&&!has_thru_pads_from_text(pj.mod->bytes))continue;
       const auto b=checked.courtyard_at(j);
       demand(a.x0>=b.x1+som_context.clearance||a.x1+som_context.clearance<=b.x0||
              a.y0>=b.y1+som_context.clearance||a.y1+som_context.clearance<=b.y0,
              "single-group contact repair violates physical courtyard clearance");
      }
     }
    }
   }
   demand(som_buck_bottom,"SoM power candidates never move the buck stage");
   demand(som_contact_offers>0,"colliding SoM single group has no checked contact repairs");
   // Independently combine a repaired single with a disjoint single. This
   // probes catalogue coverage, not board acceptance or routing feasibility.
   // The optional pair-plus-single diagnostic reports missing triple offers;
   // it is deliberately not an assertion that triple coverage is complete.
   // See 2026-10-18-three-group-screen.json for the rejected eager expansion.
   const auto probe_repaired_pairs=[&](const auto& offers,const auto& originals,
       const auto& context,const auto& zones,const std::string& probe_sheet,bool triples=false) {
   std::size_t repaired_pair_witnesses=0,repaired_pair_disjoint=0,missing=0;
   for(const auto& a:offers) {
    if(a.tag.find("/leftover")!=std::string::npos)continue;
    if(triples) {
     if(a.tag.rfind("contract-bottom-pair/",0)!=0&&a.tag.rfind("contract-bottom-repaired-pair/",0)!=0)continue;
    } else if(a.tag.rfind("contract-bottom/",0)!=0||a.tag.find("/contact/")==std::string::npos)continue;
    for(const auto& b:offers) {
     if(b.tag.rfind("contract-bottom/",0)!=0||b.tag.find("/leftover")!=std::string::npos)continue;
     auto combined=a;bool disjoint=true,moved=false;
     for(const auto& [ref,xy]:b.bot_off)if(originals.front().top_off.count(ref)) {
      if(!a.top_off.count(ref)){disjoint=false;break;}
      combined.top_off.erase(ref);combined.bot_off[ref]=xy;
      combined.extra_rot[ref]=b.extra_rot.at(ref);combined.mirror[ref]=b.mirror.at(ref);moved=true;
     }
     if(!disjoint||!moved)continue;
     ++repaired_pair_disjoint;
     combined.w=std::max(a.w,b.w);combined.h=std::max(a.h,b.h);
     const auto checked=model(combined,context,zones.geometry,probe_sheet);
     bool physical=true;
     for(std::size_t i=0;i<checked.model().insts.size();++i) {
      const auto x=checked.courtyard_at(i);
      physical&=x.x0>=0&&x.y0>=0&&x.x1<=combined.w&&x.y1<=combined.h;
      for(std::size_t j=0;j<i;++j) {
       const auto& pi=checked.model().insts[i];const auto& pj=checked.model().insts[j];
       if(pi.side!=pj.side&&!has_thru_pads_from_text(pi.mod->bytes)&&!has_thru_pads_from_text(pj.mod->bytes))continue;
       const auto y=checked.courtyard_at(j);
       physical&=x.x0>=y.x1+context.clearance||x.x1+context.clearance<=y.x0||
                 x.y0>=y.y1+context.clearance||x.y1+context.clearance<=y.y0;
      }
     }
     if(physical&&check_fanout(checked,0).ok&&check_pcb_placement_contract(checked,probe_sheet,
         &f.input.contracts.at(probe_sheet),context.board_refs.at(probe_sheet)).ok) {
      ++repaired_pair_witnesses;
      if(std::none_of(offers.begin(),offers.end(),[&](const auto& offered){
       return offered.side==combined.side&&offered.top_off==combined.top_off&&
           offered.bot_off==combined.bot_off&&offered.extra_rot==combined.extra_rot&&offered.mirror==combined.mirror;
      }))++missing;
     }
    }
   }
   std::cout<<(triples?"three-group probe sheet=":"repaired single pair sheet=")<<probe_sheet<<" witnesses="<<repaired_pair_witnesses
            <<" disjoint="<<repaired_pair_disjoint<<" missing="<<missing<<'\n';
   if(!triples) {
    if(probe_sheet=="power")demand(repaired_pair_witnesses>0,"power fixture lost repaired pair coverage");
    demand(missing==0,"legal repaired-single combinations missing from catalogue");
   }
   };
   probe_repaired_pairs(som_offers,som_originals,som_context,som_split,"power_som");
   const auto som_vertical=build_zones_for_search(f.input,true,nullptr);
   const auto& vertical_offers=som_vertical.geometry.shapes.at("power_som");
   auto direct_input=f.input;
   auto direct_policy=std::make_shared<FloorplanExperiment>(*experiment);
   direct_policy->vertical_compaction=true;direct_input.floorplan.experiment=direct_policy;
   const auto direct_vertical=build_pcb_zone_geometry(direct_input);
   const auto& direct_offers=direct_vertical.geometry.shapes.at("power_som");
   demand(direct_offers.size()==vertical_offers.size()&&
          direct_vertical.quantization_engagements==som_vertical.quantization_engagements,
          "full-build vertical policy differs from search strategy geometry or work");
   for(std::size_t i=0;i<vertical_offers.size();++i)
    demand(equal(direct_offers[i],vertical_offers[i]),"full-build vertical policy changes search candidate geometry");
   demand(vertical_offers.size()>som_offers.size(),"vertical compaction yielded no SoM power alternative");
   for(std::size_t i=0;i<som_offers.size();++i)
    demand(equal(som_offers[i],vertical_offers[i]),"vertical compaction rewrote an incumbent offer");
   Context vertical_context(f.input);vertical_context.pool=som_vertical.footprints;
   std::size_t vertical_count=0;
   for(const auto& candidate:vertical_offers) {
    const auto suffix=candidate.tag.find("/leftover-y-contact");
    if(suffix==std::string::npos)continue;
    ++vertical_count;
    const auto parent=std::find_if(vertical_offers.begin(),vertical_offers.end(),[&](const auto& s){
     return s.tag==candidate.tag.substr(0,suffix);
    });
    demand(parent!=vertical_offers.end()&&candidate.w*candidate.h<parent->w*parent->h,
           "vertical compaction did not improve its parent's area");
    demand(candidate.mirror==parent->mirror&&candidate.extra_rot==parent->extra_rot,
           "vertical compaction changed rotation or chirality");
    for(bool top:{false,true}) {
     const auto& before=top?parent->top_off:parent->bot_off;
     const auto& after=top?candidate.top_off:candidate.bot_off;
     demand(before.size()==after.size(),"vertical compaction changed face membership");
     for(const auto& [ref,xy]:before)demand(after.count(ref)&&after.at(ref).first==xy.first&&after.at(ref).second<=xy.second,
            "vertical compaction moved left/right or changed face");
    }
    const auto checked=model(candidate,vertical_context,som_vertical.geometry,"power_som");
    demand(check_pcb_placement_contract(checked,"power_som",&f.input.contracts.at("power_som"),
           vertical_context.board_refs.at("power_som")).ok&&check_fanout(checked,0).ok,
           "vertical candidate failed independent contract/fanout checks");
   }
   demand(vertical_count>0,"vertical compaction regression witness disappeared");
   const auto som_prepared=prepare_pcb_floorplan(f.input,som_split);
   for(const auto* kind:{"flow_hop","facing","far_min"})
    demand(std::any_of(som_prepared.compose.index.hard.begin(),som_prepared.compose.index.hard.end(),
        [&](const auto& term){return term.sheet=="power_som"&&term.kind==kind&&term.enforced;}),
        std::string("SoM power expansion lost an enforced board constraint: ")+kind);
   experiment->contract_group_face_sheets={"power"};
   const auto power_split=build_pcb_zone_geometry(f.input);
   std::cout<<"power_variant_dimensions="<<power_split.quantization_engagements.at("placement_variant_dimension_precision4dp")<<'\n';
   const auto& power_originals=after.geometry.shapes.at("power");
   const auto& power_alternatives=power_split.geometry.shapes.at("power");
   demand(power_alternatives.size()>=power_originals.size(),"power expansion removed incumbent offers");
   for(std::size_t i=0;i<power_originals.size();++i)
    demand(equal(power_originals[i],power_alternatives[i]),"power expansion changed an existing shape index");
   Context split_power_context(f.input);split_power_context.pool=power_split.footprints;
   probe_repaired_pairs(power_alternatives,power_originals,split_power_context,power_split,"power");
   probe_repaired_pairs(power_alternatives,power_originals,split_power_context,power_split,"power",true);
   auto replay_geometry=power_split.geometry;
   append_contract_group_faces(split_power_context,replay_geometry,"power",power_originals.front());
   demand(replay_geometry.shapes.at("power").size()==power_alternatives.size(),
          "repaired-pair replay recursively expanded existing offers");
   for(std::size_t i=0;i<power_alternatives.size();++i)
    demand(equal(replay_geometry.shapes.at("power")[i],power_alternatives[i]),
           "repaired-pair replay changed offer order or physical geometry");
   const auto ownership_input=split_power_context.stage_input("power",power_split.geometry);
   const auto& ownership_refs=split_power_context.board_refs.at("power");
   const auto ownership_groups=contract_rigid_groups(f.input.contracts.at("power"),ownership_refs,{},true,&ownership_input.pad_nets);
   demand(ownership_groups.has_value(),"electrical power closure missing");
   for(const auto& [ic,resistor]:std::vector<std::pair<std::string,std::string>>{{"U1","R11"},{"U2","R13"}}) {
    const auto owner_ref=ownership_refs.at(ic);
    const auto group=std::find_if(ownership_groups->begin(),ownership_groups->end(),[&](const auto& item){
     return std::find(item.refs.begin(),item.refs.end(),owner_ref)!=item.refs.end();
    });
    demand(group!=ownership_groups->end()&&std::find(group->refs.begin(),group->refs.end(),ownership_refs.at(resistor))!=group->refs.end(),
           "bias resistor not joined to its electrical owner");
   }
   for(bool ambiguous:{false,true}) {
    auto nets=ownership_input.pad_nets;
    const auto owner=std::make_pair(ownership_refs.at("U1"),std::string("1"));
    if(ambiguous)nets[{ownership_refs.at("R13"),"2"}]=nets.at(owner);
    else nets.erase(owner);
    demand(!contract_rigid_groups(f.input.contracts.at("power"),ownership_refs,{},true,&nets),
           "mixed-face ownership guessed through missing or ambiguous electrical evidence");
   }
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
   std::size_t power_candidates=0,buck_candidates=0,compacted_candidates=0;
   for(const auto& candidate:power_split.geometry.shapes.at("power")) {
    if(candidate.tag.rfind("contract-bottom",0)!=0)continue;
    ++power_candidates;
    const auto suffix=candidate.tag.find("/leftover-contact");
    if(suffix!=std::string::npos) {
     ++compacted_candidates;
     const auto source=std::find_if(power_alternatives.begin(),power_alternatives.end(),[&](const auto& s){
      return s.tag==candidate.tag.substr(0,suffix);
     });
     demand(source!=power_alternatives.end()&&candidate.w*candidate.h<source->w*source->h,
            "leftover compaction must measurably reduce envelope area");
     demand(candidate.extra_rot==source->extra_rot&&candidate.mirror==source->mirror,
            "leftover compaction changed orientation or mirrored identity");
     for(bool top:{false,true}) {
      const auto& old=top?source->top_off:source->bot_off;
      const auto& moved=top?candidate.top_off:candidate.bot_off;
      demand(old.size()==moved.size(),"leftover compaction changed face membership");
      for(const auto& [ref,xy]:old)demand(moved.count(ref)&&moved.at(ref).second==xy.second&&moved.at(ref).first<=xy.first,
             "leftover compaction changed face or made a non-leftward move");
     }
    }
    const auto checked=model(candidate,split_power_context,power_split.geometry,"power");
    if(candidate.tag.rfind("contract-bottom-pair",0)==0) {
     for(const auto* side:{"top","bottom"}) {
      double right=-1,bottom=-1;std::string right_ref,bottom_ref;
      for(std::size_t i=0;i<checked.model().insts.size();++i) {
       const auto& part=checked.model().insts[i];if(part.side!=side)continue;
       const auto bounds=checked.courtyard_at(i);
       if(bounds.x1>right){right=bounds.x1;right_ref=part.ref;}
       if(bounds.y1>bottom){bottom=bounds.y1;bottom_ref=part.ref;}
      }
      std::cout<<"power paired extent side="<<side<<" right="<<right_ref<<":"<<right
               <<" bottom="<<bottom_ref<<":"<<bottom<<'\n';
     }
    }
    demand(check_pcb_placement_contract(checked,"power",&f.input.contracts.at("power"),
             split_power_context.board_refs.at("power")).ok,"mixed power stage violates local hardware contract");
    demand(!candidate.top_off.empty()&&!candidate.bot_off.empty(),"power group offer is not actually mixed-face");
    for(const auto* local:{"U1","U2"})
     if(candidate.bot_off.count(split_power_context.board_refs.at("power").at(local)))++buck_candidates;
    for(const auto& [ic,resistor]:std::vector<std::pair<std::string,std::string>>{{"U1","R11"},{"U2","R13"}}) {
     const auto& refs=split_power_context.board_refs.at("power");
     demand(candidate.bot_off.count(refs.at(ic))==candidate.bot_off.count(refs.at(resistor)),
            "mixed-face buck left its electrically owned bias resistor on another face");
    }
   }
   std::cout<<"power mixed candidates="<<power_candidates<<" moved buck stages="<<buck_candidates<<'\n';
   demand(power_candidates>0&&buck_candidates>0,"power stages still have no mixed-face alternatives");
   demand(compacted_candidates>0,"power leftovers did not yield a smaller checked candidate");
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
   probe_repaired_pairs(offers,originals,gc,group_turns,"usb_jtag");
   probe_repaired_pairs(offers,originals,gc,group_turns,"usb_jtag",true);
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
   // Reuse the context and filenames across invocations, but replace the
   // physical documents: through-hole classification must not outlive a call.
   auto hole_context=candidate_context;auto hole_geometry=after.geometry;
   append_contract_group_faces(hole_context,hole_geometry,"usb_jtag",variants.front());
   demand(hole_geometry.shapes.at("usb_jtag").size()>prefix.size(),"through-hole cache test did not warm eligible candidates");
   for(const auto* owner:{"U2","U4"}) {
    const auto ref=hole_context.board_refs.at("usb_jtag").at(owner);
    const auto key=hole_geometry.resolvable.at(ref);
    const auto fp=hole_context.pool.at(key);auto text=fp->bytes;
    text.insert(text.rfind(')')," (pad \"CACHE_PROBE\" np_thru_hole circle (at 0 0) (size 0.1 0.1) (drill 0.1) (layers \"*.Cu\" \"*.Mask\"))");
    hole_context.pool[key]=pcb_check_footprint(fp->source,text);
   }
   hole_geometry=after.geometry;
   append_contract_group_faces(hole_context,hole_geometry,"usb_jtag",variants.front());
   demand(hole_geometry.shapes.at("usb_jtag").size()==prefix.size(),"changed through-hole documents reused stale face eligibility");
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
