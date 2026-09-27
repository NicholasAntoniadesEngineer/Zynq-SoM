#include "pack_geometry_observer.hpp"
#include "schgen/pack.hpp"
#include "schgen/occupancy.hpp"
#include <iostream>
#include <limits>
#include <cmath>
using namespace schgen;
using namespace geometry_fixture;
void require(bool b){if(!b)throw std::runtime_error("geometry14 negative proof");}
int main(){try{
 using Op=double(*)(double,QuantizationCounts*);
 const std::array<Op,13> ops{{pack_pair_gap_precision4dp,pack_edge_component_precision4dp,pack_som_grid_precision0dp,pack_som_cell_precision4dp,pack_som_diameter_precision4dp,pack_som_component_pose_precision4dp,pack_som_band_component_precision4dp,pack_cout_pose_precision4dp,pack_bulk_pose_precision4dp,pack_zone_component_precision4dp,pack_rotated_offset_precision4dp,pack_corridor_bound_precision4dp,pack_mirror_offset_precision4dp}};
 for(std::size_t i=0;i<ops.size();++i){
  QuantizationCounts q{{names[i],SIZE_MAX}};begin();bool threw=false;
  try{ops[i](1,&q);}catch(const std::overflow_error&){threw=true;}
  auto actual=end();require(threw&&q.at(names[i])==SIZE_MAX&&actual==QuantizationCounts{{names[i],1}});
  if(i!=2){
   q.clear();begin();threw=false;
   try{ops[i](0x1.0000000000001p51,&q);}catch(const std::runtime_error&){threw=true;}
   actual=end();require(threw);receipt(q,actual);require(actual==QuantizationCounts{{names[i],1}});
  }
  q.clear();begin();(void)ops[i](1.23455,nullptr);actual=end();
  bool missing=false;try{receipt(q,actual);}catch(const std::runtime_error&){missing=true;}
  require(missing&&actual==QuantizationCounts{{names[i],1}});
 }
 QuantizationCounts q{{names[13],SIZE_MAX}};begin();bool threw=false;
 try{pack_som_grid_trunc(1,&q);}catch(const std::overflow_error&){threw=true;}
 auto actual=end();require(threw&&actual==QuantizationCounts{{names[13],1}}&&q.at(names[13])==SIZE_MAX);
 // Consumer fails on its first actual diameter boundary: retained receipt,
 // no hypothetical cell/band counts credited after the throw.
 q.clear();begin();threw=false;
 try{(void)som_components(0,0,0x1.0000000000001p50,{{1,2}},{{1,2,3,4}},1,4,&q);}
 catch(const std::runtime_error&){threw=true;}
 actual=end();require(threw&&actual==QuantizationCounts{{"pack_som_diameter_precision4dp",1}});receipt(q,actual);
 std::cout<<"PASS: 14 overflow attempts; 12 magnitude rejections; 13 missing-sink negatives; aborted consumer retains only actual entry\n";
 return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
