#include "schgen/pack.hpp"
#include "search_proof.hpp"
#include <cstring>
#include <iostream>
#include <iomanip>
using namespace schgen;
#ifdef SEARCH_CANDIDATE
#define SINK , &q
#else
#define SINK
#endif
void bits(double x){std::uint64_t n;std::memcpy(&n,&x,8);std::cout<<n<<' ';}
void strings(const std::vector<std::string>& v){std::cout<<v.size()<<' ';for(const auto& s:v)std::cout<<std::quoted(s)<<' ';}
void seat(const SeatBandResult& s){
 std::cout<<s.vias.size()<<' ';for(const auto& v:s.vias){bits(v.u);bits(v.v);bits(v.dia);bits(v.drill);bits(v.worst);strings(v.members);}
 std::cout<<s.ledger.size()<<' ';for(const auto& l:s.ledger){std::cout<<std::quoted(l.kind)<<' '<<std::quoted(l.conn)<<' '<<l.depth<<' ';bits(l.u);bits(l.v);bits(l.dia);bits(l.drill);bits(l.worst);bits(l.at);strings(l.members);}
 strings(s.audit);std::cout<<'\n';
}
int main(){try{
 for(double x:{-1.125,0.,.00005})for(double width:{-.75,0.,.4,1.,2.})for(double pitch:{.125,.3,1.}){
  QuantizationCounts q;search_proof::begin();auto out=fallback_via_sites(x,-.375,x+width,1.25,.25,pitch SINK);search_proof::receipt(q);
  std::cout<<out.size()<<' ';for(auto [a,b]:out){bits(a);bits(b);}std::cout<<'\n';
#ifdef SEARCH_CANDIDATE
  if(q.at("fallback_axis_count")!=2)throw std::runtime_error("axis multiplicity");
  if(!out.empty()&&(q.at("fallback_coordinate_precision3dp")!=out.size()*2||q.at("fallback_rank_precision4dp")!=out.size()))throw std::runtime_error("point multiplicity");
#endif
 }
 for(int mode=0;mode<6;++mode){
  std::vector<std::tuple<std::string,double,double>> members{{"1",-.4,1.},{"2",.4,1.}};
  if(mode==1)members={{"1",-2.,1.},{"2",2.,1.}};
  if(mode==2)members={{"1",0.,-1.},{"2",0.,1.}};
  if(mode==3)members={{"1",0.,1.}};
  std::vector<std::tuple<double,double,double,double,double,std::string>> obstacles;
  if(mode==4)obstacles.emplace_back(-5,-5,5,5,0,"blocked");
  std::vector<std::pair<double,double>> ladder{{.45,.3},{.35,.2}};
  if(mode==5)ladder.clear();
  QuantizationCounts q;search_proof::begin();
  auto result=seat_band(members,obstacles,{}, {},{},1.,.1,ladder,{.1,.3,.2,.1},.15,1.8,.25,"J1",0 SINK);
  search_proof::receipt(q);seat(result);
 }
 std::cerr<<"search9 helper bytes and entry receipts PASS\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
