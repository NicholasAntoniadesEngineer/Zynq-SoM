#include "schgen/pack.hpp"
#include "schgen/pack_search_precision.hpp"
#include "search_proof.hpp"
#include "schgen/native_audit_state.hpp"
#include <cmath>
#include <climits>
#include <limits>
#include <iostream>
using namespace schgen;
void require(bool b){if(!b)throw std::runtime_error("search9 independent oracle mismatch");}
template<class F> void rejects(F f){bool threw=false;try{f();}catch(const std::exception&){threw=true;}require(threw);}
int main(){try{
 for(int n=-10000;n<=10000;++n){
  const double q=n/16.;
  require(fallback_axis_count(q)==n/16+1);
  require(seat_vertical_extent(q)==n/16);
  require(seat_lower_index(q)==n/16+(n>0&&n%16!=0));
  require(seat_upper_index(q)==n/16-(n<0&&n%16!=0));
 }
 const auto max=std::numeric_limits<std::size_t>::max();
 for(auto a:{std::size_t(0),std::size_t(1),std::size_t(46341),max/2,max})
 for(auto b:{std::size_t(0),std::size_t(1),std::size_t(46341),max/2,max})
 for(auto limit:{std::size_t(0),std::size_t(100),max}){
  const unsigned __int128 exact=static_cast<unsigned __int128>(a)*b;
  if(exact>limit)rejects([&]{(void)pack_search_detail::checked_product(a,b,limit);});
  else require(pack_search_detail::checked_product(a,b,limit)==exact);
 }
 for(long lo:{LONG_MIN,-1L,0L,1L,LONG_MAX})
 for(long hi:{LONG_MIN,-1L,0L,1L,LONG_MAX})
 for(auto limit:{std::size_t(0),std::size_t(100),max}){
  const __int128 exact=lo>hi?0:static_cast<__int128>(hi)-lo+1;
  if(static_cast<unsigned __int128>(exact)>limit)rejects([&]{(void)pack_search_detail::inclusive_count(lo,hi,limit);});
  else require(pack_search_detail::inclusive_count(lo,hi,limit)==exact);
 }
 const double lbound=std::ldexp(1.,std::numeric_limits<long>::digits);
 for(long first:{LONG_MIN,LONG_MIN+1,-1L,0L,LONG_MAX-1,LONG_MAX}){
  const std::size_t count=first==LONG_MAX?1:2;
  std::vector<long> visited;
  pack_search_detail::for_each_index(first,count,[&](long v){visited.push_back(v);});
  require(visited.size()==count);
  for(std::size_t i=0;i<count;++i)require(static_cast<__int128>(visited[i])==static_cast<__int128>(first)+i);
 }
 std::size_t visited=0;
 pack_search_detail::for_each_index(LONG_MAX,0,[&](long){++visited;});
 require(visited==0);
 rejects([&]{pack_search_detail::for_each_index(LONG_MAX,2,[&](long){++visited;});});
 require(visited==1);
 require(seat_lower_index(-lbound)==LONG_MIN&&seat_upper_index(-lbound)==LONG_MIN);
 require(seat_lower_index(std::nextafter(lbound,0.))==static_cast<long>(std::nextafter(lbound,0.)));
 require(fallback_axis_count(double(INT_MIN)-.75)==INT_MIN+1);
 require(fallback_axis_count(double(INT_MAX)-.25)==INT_MAX);
 require(seat_vertical_extent(double(INT_MAX)+.75)==INT_MAX);
 require(seat_vertical_extent(double(INT_MIN)+.25)==INT_MIN+1);
 for(double v:{double(NAN),double(INFINITY),double(-INFINITY)}){
  QuantizationCounts q;search_proof::begin();rejects([&]{fallback_axis_count(v,&q);});search_proof::receipt(q);
  require(q==QuantizationCounts{{"fallback_axis_count",1}});
  q.clear();search_proof::begin();rejects([&]{seat_lower_index(v,&q);});search_proof::receipt(q);
  require(q==QuantizationCounts{{"seat_lower_index",1}});
  rejects([&]{fallback_via_sites(0,0,1,1,.2,v);});
  rejects([&]{fallback_via_sites(v,0,1,1,.2,.25);});
 }
 rejects([&]{fallback_axis_count(double(INT_MAX));});
 rejects([&]{fallback_axis_count(double(INT_MIN)-1.);});
 rejects([&]{seat_lower_index(lbound);});
 rejects([&]{seat_upper_index(lbound);});
 rejects([&]{seat_vertical_extent(double(INT_MIN));});
 rejects([&]{seat_vertical_extent(double(INT_MAX)+1.);});
 require(pack_search_detail::next_depth(INT_MIN)==INT_MIN+1);
 // An empty ladder never evaluates lattice/row arithmetic: retain that defined
 // behavior rather than validating unused parameters or manufacturing entries.
 QuantizationCounts unused;
 search_proof::begin();
 const auto empty=seat_band({{"a",0,0}}, {},{},{},{},NAN,0,{}, {},0,1,0,"J",0,&unused);
 search_proof::receipt(unused);
 require(empty.vias.empty()&&empty.ledger.empty()&&unused.empty());
 rejects([&]{pack_search_detail::next_depth(INT_MAX);});
 QuantizationCounts q;search_proof::begin();
 rejects([&]{seat_band({{"a",-.4,0},{"b",.4,0}}, {},{},{},{},double(INT_MIN),0,{{0,0}}, {},0,0,1,"J",0,&q);});
 search_proof::receipt(q);require(q==QuantizationCounts({{"seat_lower_index",1},{"seat_upper_index",1},{"seat_vertical_extent",1}}));
 q.clear();search_proof::begin();
 rejects([&]{seat_band({{"a",-2,0},{"b",2,0}}, {},{},{},{},1,0,{}, {},0,1,1,"J",INT_MAX,&q);});
 search_proof::receipt(q);require(q==QuantizationCounts{{"seat_split_precision4dp",1}});
 // Dropping the sink must be detectable independently.
 search_proof::begin();(void)fallback_axis_count(1,nullptr);
 rejects([&]{search_proof::receipt({});});
 NativeQuantizations all,r;register_native_quantizations(all);
 require(all.declarations().size()==131);
 for(const auto& d:all.declarations())if(search_proof::added(d.name))r.declare(d);
 require(r.declarations().size()==9);
 for(const auto& d:r.declarations()){
  require(d.arity==1&&d.symbol=="native/src/pack_search_precision.cpp::schgen::"+d.name);
  const std::array<double,9> expected{{2.,1.235,1.2346,2.,1.,1.,1.23455,1.2346,1.2346}};
  const auto index=static_cast<std::size_t>(std::find(search_proof::names.begin(),search_proof::names.end(),d.name)-search_proof::names.begin());
  search_proof::begin();require(r.invoke(d.name,{1.23455})==expected.at(index));
  require(search_proof::end()==QuantizationCounts{{d.name,1}});
  const auto prior=r.engagements();search_proof::begin();
  rejects([&]{r.invoke(d.name,{});});
  require(search_proof::end().empty()&&r.engagements()==prior);
 }
 std::cout<<"PASS: dyadic floor/ceil/trunc oracles; 128-bit product/interval oracles; range/NaN/INT_MIN/depth negatives; actual rejected receipts\n";
 return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
