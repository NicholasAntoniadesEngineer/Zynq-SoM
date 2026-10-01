#define main original_helper_probe_unused
#include "helper_contracts.cpp"
#undef main
int main(){try{
 for(double step:{-.25,-1.}){
  QuantizationCounts q;search_proof::begin();
  auto s=seat_band({{"a",-.4,1},{"b",.4,1}}, {},{},{},{},1,.1,{{.45,.3}}, {.1,.3,.2,.1},.15,1.8,step,"J",0 SINK);
  search_proof::receipt(q);seat(s);
 }
 {
  QuantizationCounts q;search_proof::begin();
  auto s=seat_band({{"a",0,0}}, {},{},{},{},std::numeric_limits<double>::quiet_NaN(),0,{}, {},0,1,0,"J",0 SINK);
  search_proof::receipt(q);seat(s);
 }
 {
  QuantizationCounts q;search_proof::begin();
  auto s=seat_band({{"a",1e308,0}}, {},{},{},{},0,0,{{0,0}}, {},0,0,1e308,"J",0 SINK);
  search_proof::receipt(q);seat(s);
 }
 std::cerr<<"PASS defined negative-lattice, unused-NaN/zero-lattice, finite-coordinate/infinite-center behavior\n";
 return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
