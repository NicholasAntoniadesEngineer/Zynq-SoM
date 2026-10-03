#include "pcb_placement_fixture.hpp"
#include "pcb_placement_internal.hpp"
#include "schgen/pcb_placement_gates.hpp"
#include "pcb_placement_gates_internal.hpp"
#include "schgen/legalize.hpp"
#include <iostream>
#include <iomanip>
#include <regex>
#include <sstream>
using namespace schgen;
using namespace schgen::pcb_placement;
void require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
const SexprList* list(const Sexpr&s){return std::get_if<SexprList>(&s.v);}
std::string atom(const Sexpr&s){if(auto p=std::get_if<std::string>(&s.v))return *p;if(auto p=std::get_if<Sexpr::Sym>(&s.v))return p->name;return {};}
const SexprList* child(const SexprList&s,const std::string&key){for(const auto&v:s)if(auto l=list(v);l&&!l->empty()&&atom(l->front())==key)return l;return nullptr;}
std::string trim(std::string s){auto a=s.find_first_not_of(" \t"),b=s.find_last_not_of(" \t");return a==std::string::npos?"":s.substr(a,b-a+1);}
struct EmittedPose {double x,y,r;std::string side;};
int main(int argc,char**argv){try{
 if(argc!=3)return 2;std::cout<<std::setprecision(15);
 const std::filesystem::path root=argv[1],evidence=argv[2];
 auto f=placement_fixture::load(root,"carrier");f.input.floorplan.compact_search=true;
 const auto zones=build_pcb_zone_geometry(f.input);
 auto pcb=sexpr_loads(placement_fixture::read(evidence/"Zynq_Carrier.kicad_pcb"));std::map<std::string,EmittedPose> emitted;
 for(const auto&node:*list(pcb))if(auto l=list(node);l&&!l->empty()&&atom(l->front())=="footprint"){
  std::string ref;for(const auto&v:*l)if(auto prop=list(v);prop&&prop->size()>2&&atom(prop->at(0))=="property"&&atom(prop->at(1))=="Reference")ref=atom(prop->at(2));
  auto a=child(*l,"at");if(!a||a->size()<3)continue;
  emitted[ref]={std::get<double>(a->at(1).v)-25,std::get<double>(a->at(2).v)-25,a->size()>3?std::get<double>(a->at(3).v):0,atom(child(*l,"layer")->at(1))=="B.Cu"?"bottom":"top"};
 }
 std::map<std::string,std::array<double,4>> rows;std::istringstream doc(placement_fixture::read(evidence/"docs/FLOORPLAN.md"));std::string line;
 const std::regex box(R"(\((-?[0-9.]+), (-?[0-9.]+), ([0-9.]+) x ([0-9.]+)\))");
 while(std::getline(doc,line)){std::smatch m;if(!std::regex_search(line,m,box))continue;std::istringstream cells(line);std::vector<std::string> v;std::string cell;while(std::getline(cells,cell,'|'))v.push_back(trim(cell));if(v.size()<4)continue;std::string name=v[1];if(name=="N"||name=="E"||name=="S"||name=="W")name=v[2];rows[name]={std::stod(m[1]),std::stod(m[2]),std::stod(m[3]),std::stod(m[4])};}
 f.stage.plan.board_w=168;f.stage.plan.board_h=163;f.stage.plan.som_x=49;f.stage.plan.som_y=66.5;
 for(auto*blocks:{&f.stage.plan.edge_blocks,&f.stage.plan.interior_blocks})for(auto&b:*blocks){
  const auto d=rows.at(b.name);b.x=d[0];b.y=d[1];b.w=d[2];b.h=d[3];
  auto variants=zones.geometry.shapes.find(b.name);if(variants==zones.geometry.shapes.end())continue;
  double best=1e100;int chosen=-1;
  for(std::size_t k=0;k<variants->second.size();++k){const auto&s=variants->second[k];if(std::abs(s.w-b.w)>.001||std::abs(s.h-b.h)>.001)continue;double score=0;
   for(const auto*off:{&s.top_off,&s.bot_off})for(const auto&[r,xy]:*off){if(!emitted.count(r))continue;const auto&p=emitted.at(r);const auto side=off==&s.top_off?s.side:(s.side=="top"?"bottom":"top");score+=side==p.side?0:10000;double angle=s.extra_rot.count(r)?s.extra_rot.at(r):0;if(zones.geometry.conn_rot.count(r))angle+=zones.geometry.conn_rot.at(r);score+=std::abs(normalize(angle)-normalize(p.r));score+=std::abs(xy.first+b.x-p.x)+std::abs(xy.second+b.y-p.y);}
   if(score<best){best=score;chosen=static_cast<int>(k);}
  }
  if(chosen<0)throw std::runtime_error("no dimension-matched shape "+b.name);
  b.shape_idx=chosen;b.side=variants->second.at(chosen).side;
  std::cout<<"BIND "<<b.name<<" idx="<<chosen<<" tag="<<variants->second.at(chosen).tag<<" score="<<best<<'\n';
 }


 const auto compiled=prepare_pcb_floorplan(f.input,zones);
 const auto ti=std::find_if(compiled.compose.index.hard.begin(),compiled.compose.index.hard.end(),
     [](const auto& t){return t.kind=="facing" && t.subject=="power" && t.target()=="power_som";});
 require(ti!=compiled.compose.index.hard.end() && ti->enforced && ti->require_positive_facing,"compiled strict enforced facing missing");
 const auto term=*ti;
 FloorplanLegalizeInput li;
 li.board_w=f.stage.plan.board_w;li.board_h=f.stage.plan.board_h;li.index.hard={term};
 li.metrics=compiled.compose.metrics;
 li.som_core_page=som_core_rect(f.stage.plan.som_x,f.stage.plan.som_y,f.stage.plan.som.w,f.stage.plan.som.h,25,25,.03);
 FloorplanOffsets poses;
 FloorplanBlock power,down;
 for(const auto* blocks:{&f.stage.plan.edge_blocks,&f.stage.plan.interior_blocks})
  for(const auto& b:*blocks) {
   poses[b.name]={b.x,b.y};
   if(b.shape_idx)li.metrics[b.name]=compiled.compose.shape_metrics.at({b.name,b.shape_idx});
   if(b.name=="power")power=b;
   if(b.name=="power_som")down=b;
  }
 require(power.shape_idx==4,"archive power selected shape changed");
 std::cout<<"COMPILED enforced="<<term.enforced<<" power_shape="<<power.shape_idx
     <<" power_members="<<li.metrics.at("power").offsets.size()<<" target_members="<<li.metrics.at("power_som").offsets.size()<<" output_refs=";
 for(const auto& ref:term.out_refs)std::cout<<ref<<",";
 std::cout<<"\n";
 const auto& pm=li.metrics.at("power");
 const auto& dm=li.metrics.at("power_som");
 const auto pred_zone=*predicted_centroid(power.x,power.y,25,25,pm.offsets,nullptr);
 const auto pred_output=*predicted_centroid(power.x,power.y,25,25,pm.offsets,&term.out_refs);
 const auto pred_target=*predicted_centroid(down.x,down.y,25,25,dm.offsets,nullptr);
 const auto pred_face=facing_dot(pred_zone.first,pred_zone.second,pred_output.first,pred_output.second,pred_target.first,pred_target.second);
 const auto predicted=floorplan_evaluate_terms(li,poses).at(0);
 std::cout<<"PREDICT zone="<<pred_zone.first<<","<<pred_zone.second<<" output="<<pred_output.first<<","<<pred_output.second
     <<" target="<<pred_target.first<<","<<pred_target.second<<" dot="<<pred_face.first<<" angle="<<pred_face.second<<"\n";
 std::cout<<"COMPOSE ok="<<predicted.ok<<" margin="<<predicted.margin<<" note="<<predicted.note<<"\n";
 require(pred_face.first<0 && !predicted.ok,"compiled strict hard facing still false-green");
 std::vector<EvalMetric> metrics;
 for(const auto& [name,m]:li.metrics)metrics.push_back({name,m.offsets,m.pad_union});
 const auto strict=evaluate_terms(li.board_w,li.board_h,li.som_core_page,{poses.begin(),poses.end()},metrics,
     {{term.kind,term.subject,term.target(),0,false,term.out_refs}}, {},{},25,25).at(0);
 require(!strict.ok && strict.measured==predicted.measured,"guard alone changes verdict without changing prediction");
 std::cout<<"SAME_METRICS_NO_FACING_GUARD ok="<<strict.ok<<" measured="<<strict.measured<<" note="<<strict.note<<"\n";
 std::vector<PcbCheckInstance> observed;
 auto observer=std::make_shared<PcbPlacementExperiment>();
 observer->checkpoint=[&](const auto& frame){observed=frame.instances;};
 f.input.experiment=observer;
 Placer p(f.input,zones,f.stage);p.seed();
 auto check_stage=[&](const char* name) {
  p.observe_checkpoint(name);
  PcbCheckModel model;model.insts=observed;
  const PcbCheckInput input(std::move(model));
  const placement_gates::FinalGeometry actual(input);
  const auto z=*actual.centroid("power"),o=*actual.members("power",{term.out_refs.begin(),term.out_refs.end()}),d=*actual.centroid("power_som");
  const auto face=facing_dot(z.first,z.second,o.first,o.second,d.first,d.second);
  double delta=0;
  for(const auto& group:{"power","power_som"})for(const auto& [ref,x,y]:li.metrics.at(group).offsets) {
   const auto pose=poses.at(group);const auto xy=p.pos.at(ref);
   delta=std::max({delta,std::abs(pose.first+x-xy.first),std::abs(pose.second+y-xy.second)});
  }
  std::cout<<"ACTUAL "<<name<<" zone="<<z.first<<","<<z.second<<" output="<<o.first<<","<<o.second
      <<" target="<<d.first<<","<<d.second<<" dot="<<face.first<<" max_metric_pose_delta="<<delta<<"\n";
  require(z==pred_zone && o==pred_output && d==pred_target && delta<1e-10,"selected metrics differ from emitted group geometry");
 };
 check_stage("seed");
 p.l4_pull();p.edge_seat();p.breathe("probe");check_stage("breathe");
 p.refit();check_stage("guarded_refit");
 li.fixed_poses["power_som"]=poses.at("power_som");
 li.fixed_rects.push_back({"power_som",{down.x,down.y,down.x+down.w,down.y+down.h}});
 std::vector<FloorplanLegalizeVar> vars{{"power",power.w,power.h,{power.x,power.y},power.x,power.y}};
 std::vector<std::string> log;
 li.compact=false;
 const auto accepted=floorplan_legalize_compact(li,vars,log);
 std::cout<<"ISOLATED_COMPOSER accepted="<<accepted<<"\n";
 for(const auto& line:log)std::cout<<" "<<line<<"\n";
 require(!accepted && vars[0].x==power.x && vars[0].y==power.y,"compact=false fallback did not reject compiled strict facing atomically");
 li.compact=true;
 require(!floorplan_legalize_compact(li,vars,log),"compact legalization bypassed compiled strict facing");
 auto disabled=f.input;disabled.floorplan.compact_search=false;
 const auto original=prepare_pcb_floorplan(disabled,zones);
 for(const auto* terms:{&original.compose.index.hard,&original.compose.index.soft,&original.compose.index.na})
  for(const auto& t:*terms)require(!t.require_positive_facing,"default compiler tagged strict facing");
 auto advisory=f.input;advisory.floorplan.project.wired_sheets.clear();
 const auto soft=prepare_pcb_floorplan(advisory,zones);
 for(const auto& t:soft.compose.index.soft)require(!t.require_positive_facing,"non-enforced compiler tagged strict facing");
 std::cout<<"PASS compiled strict negative term rejects in both modes; metrics unchanged; default/advisory flags remain false.\n";
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
