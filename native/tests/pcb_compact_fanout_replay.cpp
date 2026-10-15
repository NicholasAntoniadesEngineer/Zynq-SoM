#include "pcb_placement_fixture.hpp"
#include "pcb_placement_internal.hpp"
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
 // Bounded replay of the archived candidate, not a new floorplan search or audit.
 // The archived Markdown rounds unrelated block origins; target poses are checked below.
 auto observer=std::make_shared<PcbPlacementExperiment>();
 std::map<std::string, double> gaps;
 std::map<std::string, std::map<std::string, std::tuple<double,double,double>>> power_poses;
 Context context(f.input);context.pool=zones.footprints;
 const auto power_input=context.stage_input("power",zones.geometry);const pcb_stage::Engine power_engine(power_input);const auto power_outputs=power_engine.output_refs();
 observer->checkpoint=[&](const PcbPlacementObservation&o){
  if(!o.has_positions)return;PcbCheckModel m;m.board_w=168;m.board_h=163;m.insts=o.instances;PcbCheckInput c(std::move(m));auto fanout=check_fanout(c,0);
  for(const auto&r:fanout.records)if(r.ref=="U28002")gaps[o.stage]=r.clearance;
  for(const auto&i:o.instances)if(i.sheet=="power")power_poses[o.stage][i.ref]={i.x,i.y,i.rotation};
  for(const auto&r:fanout.records)if(r.ref=="SW7002"||r.ref=="SW19001"||r.ref=="U28002")std::cout<<"STAGE "<<o.stage<<" "<<r.ref<<" gap="<<r.clearance<<" need="<<r.need<<" nearest="<<r.nearest_ref<<'\n';
  std::vector<Box4> power_boxes;for(std::size_t k=0;k<o.instances.size();++k)if(o.instances[k].sheet=="power")power_boxes.push_back(c.courtyard_at(k));
  if(!power_boxes.empty()){const auto b=*boxes_union(power_boxes);std::cout<<"POWER_SPAN "<<o.stage<<" "<<b.x0<<","<<b.y0<<","<<b.x1<<","<<b.y1<<'\n';}
  std::vector<FloorplanPoint> all,out,down;for(const auto&i:o.instances){if(i.sheet=="power")all.emplace_back(i.x,i.y);if(power_outputs.count(i.ref))out.emplace_back(i.x,i.y);if(i.sheet=="power_som")down.emplace_back(i.x,i.y);}if(!all.empty()&&!out.empty()&&!down.empty()){auto a=points_centroid(all),b=points_centroid(out),d=points_centroid(down);std::cout<<"POWER_FACING "<<o.stage<<" "<<facing_align_dot(a.first,a.second,b.first,b.second,d.first-a.first,d.second-a.second)<<'\n';}
  for(const auto&i:o.instances)if(i.ref=="U28002"||i.ref=="D20001")std::cout<<"POSE "<<o.stage<<" "<<i.ref<<" "<<i.x<<","<<i.y<<","<<i.rotation<<" "<<i.side<<'\n';
 };
 f.input.experiment=observer;
 auto result=place_pcb_model_accounted(f.input,zones,f.stage,PcbZoneAccountingOwnership::SeparateFromFloorplan);
 require(std::abs(gaps.at("step3_emission")-2.9263347399092878)<1e-10,"archived USB JTAG seed reproduced");
 for(const auto* stage:{"l4_pull","edge_seat","breathe","refit_facing","reorder","corridor_eviction","instantiate","emission_frame","escape_copper"})
  require(gaps.at(stage)==gaps.at("step3_emission"),"checkpoint introduced USB JTAG fanout regression");
 require(power_poses.at("breathe")==power_poses.at("refit_facing"),"rejected power refit must retain every pose atomically");
 const auto diode=power_poses.at("breathe").at("D20001");
 require(std::abs(std::get<0>(diode)-190.4764)<1e-10 && std::abs(std::get<1>(diode)-141.03)<1e-10 && std::get<2>(diode)==90,"archived pre-refit crowder reproduced");
 require(result.placement_accounting.quantization_engagements.at("refit_pose_precision")>0,"rejected refit retains measured work");
 for(const auto&i:result.model.insts)if(i.ref=="U28002"||i.ref=="D20001"){
  const auto&p=emitted.at(i.ref);std::cout<<"FINAL_DELTA "<<i.ref<<" "<<i.x-25-p.x<<","<<i.y-25-p.y<<","<<normalize(i.rotation)-normalize(p.r)<<'\n';}
 for(const auto&r:check_fanout(PcbCheckInput(result.model),0).records)
  if(r.ref=="U28002"&&r.starved())throw std::runtime_error("refit introduced U28002 starvation");
 std::cout<<"PASS no new U28002 starvation; full facing acceptance remains required\n";
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
