#include "pack_plain_observer.hpp"
#include "schgen/pack.hpp"
#include "schgen/occupancy.hpp"
#include "schgen/native_audit_state.hpp"
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>
#include <thread>
using namespace schgen;
void require(bool b){if(!b)throw std::runtime_error("plain precision contract");}
std::uint64_t bits(double x){std::uint64_t u;std::memcpy(&u,&x,sizeof u);return u;}
struct Op { double(*call)(double,int,QuantizationCounts*); int digits; };
const std::array<Op,18> ops{{
{+[](double x,int d,QuantizationCounts* q){(void)d;return pack_fanout_reach_precision4dp(x,q);},4},
{+[](double x,int d,QuantizationCounts* q){(void)d;return pack_band_sort_precision4dp(x,q);},4},
{+[](double x,int d,QuantizationCounts* q){(void)d;return pack_contact_column_precision4dp(x,q);},4},
{+[](double x,int d,QuantizationCounts* q){(void)d;return pack_plane_bound_precision3dp(x,q);},3},
{+[](double x,int d,QuantizationCounts* q){(void)d;return pack_isolation_bound_precision3dp(x,q);},3},
{+[](double x,int d,QuantizationCounts* q){(void)d;return pack_ladder_coordinate_precision4dp(x,q);},4},
{+[](double x,int d,QuantizationCounts* q){(void)d;return pack_redundancy_candidate_precision6dp(x,q);},6},
{+[](double x,int d,QuantizationCounts* q){return pack_aabb_coordinate_precision(x,d,q);},-1},
{+[](double x,int d,QuantizationCounts* q){(void)d;return pack_block_area_precision1dp(x,q);},1},
{+[](double x,int d,QuantizationCounts* q){return pack_xy_coordinate_precision(x,d,q);},-1},
{+[](double x,int d,QuantizationCounts* q){return pack_box_coordinate_precision(x,d,q);},-1},
{+[](double x,int d,QuantizationCounts* q){(void)d;return pack_svg_map_precision1dp(x,q);},1},
{+[](double x,int d,QuantizationCounts* q){return pack_unique_coordinate_precision(x,d,q);},-1},
{+[](double x,int d,QuantizationCounts* q){return pack_centroid_coordinate_precision(x,d,q);},-1},
{+[](double x,int d,QuantizationCounts* q){(void)d;return pack_row_extent_precision4dp(x,q);},4},
{+[](double x,int d,QuantizationCounts* q){return pack_halfturn_origin_precision(x,d,q);},-1},
{+[](double x,int d,QuantizationCounts* q){return pack_rotated_origin_precision(x,d,q);},-1},
{+[](double x,int d,QuantizationCounts* q){return pack_named_center_precision(x,d,q);},-1},
}};
int main(){try{
 NativeQuantizations registry;register_native_quantizations(registry);
 require(registry.declarations().size()==155);
 const auto declarations=registry.declarations();
 for(std::size_t i=0;i<ops.size();++i){
  const auto& name=plain_fixture::names[i];const auto& op=ops[i];
  for(int digits: {0,1,2,3,4,6,15}){
   if(op.digits>=0&&digits!=op.digits)continue;
   const double divisor=std::pow(10.,digits);
   for(int k=-16;k<=16;++k){
    const double midpoint=(k+.5)/divisor;
    for(double x:{std::nextafter(midpoint,-INFINITY),midpoint,std::nextafter(midpoint,INFINITY),-0.,0.}){
     QuantizationCounts counts;plain_fixture::begin();const double actual=op.call(x,digits,&counts);
     auto observed=plain_fixture::end();plain_fixture::receipt(counts,observed);
     require(observed==QuantizationCounts{{name,1}}&&bits(actual)==bits(py_round(x,digits)));
     plain_fixture::begin();const auto pure=op.call(x,digits,nullptr);
     require(plain_fixture::end()==observed&&bits(pure)==bits(actual)&&counts.at(name)==1);
    }
   }
  }
  const int digits=op.digits<0?4:op.digits;
  QuantizationCounts full{{name,std::numeric_limits<std::size_t>::max()}};
  plain_fixture::begin();bool threw=false;try{op.call(1,digits,&full);}catch(const std::overflow_error&){threw=true;}
  require(threw&&plain_fixture::end()==QuantizationCounts{{name,1}}&&full.at(name)==std::numeric_limits<std::size_t>::max());
  auto declaration=std::find_if(declarations.begin(),declarations.end(),[&](const auto& d){return d.name==name;});
  require(declaration!=declarations.end()&&declaration->arity==(op.digits<0?2u:1u)&&
    declaration->symbol=="native/src/pack_plain_precision.cpp::schgen::"+name);
  const std::vector<double> args=op.digits<0?std::vector<double>{1.23455,4}:std::vector<double>{1.23455};
  plain_fixture::begin();const auto v=registry.invoke(name,args);
  require(bits(v)==bits(py_round(1.23455,digits))&&plain_fixture::end()==QuantizationCounts{{name,1}});
  plain_fixture::begin();threw=false;try{registry.invoke(name,{});}catch(const std::invalid_argument&){threw=true;}
  require(threw&&plain_fixture::end().empty());
  if(op.digits<0){
   for(double bad:{.5,double(INFINITY),2147483648.}){
    plain_fixture::begin();threw=false;try{registry.invoke(name,{1,bad});}catch(const std::invalid_argument&){threw=true;}
    require(threw&&plain_fixture::end().empty());
   }
   for(int bad:{-1,16}){
    QuantizationCounts q;plain_fixture::begin();threw=false;try{op.call(1,bad,&q);}catch(const std::runtime_error&){threw=true;}
    const auto observed=plain_fixture::end();plain_fixture::receipt(q,observed);require(threw&&q==QuantizationCounts{{name,1}});
   }
  }
  // Receipt verifier must reject deleted and fabricated counts.
  for(const QuantizationCounts& mutation: {QuantizationCounts{},QuantizationCounts{{name,2}}}){
   threw=false;try{plain_fixture::receipt(mutation,{{name,1}});}catch(const std::runtime_error&){threw=true;}require(threw);
  }
 }
 QuantizationCounts unknown{{"unregistered_plain_probe",9},{"pack_xy_coordinate_precision_extra",3}};
 auto mixed=unknown;for(const auto& name:plain_fixture::names)mixed[name]=2;
 require(plain_fixture::select(mixed,false)==unknown);
 std::array<QuantizationCounts,2> owned;
 plain_fixture::begin();std::thread a([&]{for(int i=0;i<10;++i)round_xy(1,2,4,&owned[0]);});
 std::thread b([&]{for(int i=0;i<10;++i)round_xy(3,4,4,&owned[1]);});a.join();b.join();
 require(owned[0]==owned[1]&&owned[0]==QuantizationCounts{{"pack_xy_coordinate_precision",20}});
 require(plain_fixture::end()==QuantizationCounts{{"pack_xy_coordinate_precision",40}});
 // Rejected contact geometry retains the rounded-column prefix.
 QuantizationCounts q;plain_fixture::begin();bool threw=false;
 try{contact_geometry({{0.,0.,1.,1.}},&q);}catch(const std::runtime_error&){threw=true;}
 auto observed=plain_fixture::end();plain_fixture::receipt(q,observed);
 require(threw&&q==QuantizationCounts{{"pack_contact_column_precision4dp",1}});
 // Sorting executes actual comparisons rather than one fabricated count per point.
 q.clear();plain_fixture::begin();const auto bands=band_cover({{2.00005,"2"},{1.00005,"1"},{1.00004,"3"}},.2,&q);
 observed=plain_fixture::end();plain_fixture::receipt(q,observed);require(!bands.empty()&&!observed.empty());

 // Every rejected lattice candidate counts, including repeated step-zero positions.
 q.clear();plain_fixture::begin();
 const auto rejected=escape_redundancy_u(0,0,.6,.3,{},{},{},{{0,0,100,"blocker"}},{},1,.25,3,&q);
 observed=plain_fixture::end();plain_fixture::receipt(q,observed);
 require(!rejected&&q==QuantizationCounts{{"pack_redundancy_candidate_precision6dp",12}});
 q.clear();plain_fixture::begin();
 const auto accepted=escape_redundancy_u(0,0,.6,.3,{},{},{},{},{},1,.25,3,&q);
 observed=plain_fixture::end();plain_fixture::receipt(q,observed);
 require(accepted&&bits(*accepted)==bits(py_round(1.,6))&&q==QuantizationCounts{{"pack_redundancy_candidate_precision6dp",1}});
 // Independent original-expression oracles for generic APIs (including API-only boundaries).
 QuantizationCounts helpers;plain_fixture::begin();
 const Box4 box{-1.23455,-0.00005,3.45675,4.56785};
 auto same=[](double a,double b){require(bits(a)==bits(b));};
 const auto aabb=aabb_from_corners(box.x1,box.y1,box.x0,box.y0,4,&helpers);
 same(aabb.x0,py_round(box.x0,4));same(aabb.y0,py_round(box.y0,4));same(aabb.x1,py_round(box.x1,4));same(aabb.y1,py_round(box.y1,4));
 same(block_area(3.45675,4.56785,&helpers),py_round(3.45675*4.56785,1));
 const auto xy=round_xy(-0.,1.23455,3,&helpers);
 same(xy.first,py_round(-0.,3));same(xy.second,py_round(1.23455,3));
 const auto rounded=round_box(box,3,&helpers);
 same(rounded.x0,py_round(box.x0,3));same(rounded.y0,py_round(box.y0,3));same(rounded.x1,py_round(box.x1,3));same(rounded.y1,py_round(box.y1,3));
 same(svg_map(1.23455,46.,6.,&helpers),py_round(46.+1.23455*6.,1));
 const auto unique=rounded_unique_sorted({1.23455,1.23454,-0.,0.},4,&helpers);
 const std::set<double> expectedUnique{py_round(1.23455,4),py_round(1.23454,4),py_round(-0.,4),py_round(0.,4)};
 require(unique==std::vector<double>(expectedUnique.begin(),expectedUnique.end()));
 const auto center=rounded_centroid({{1.23455,2.34565},{3.45675,4.56785}},4,&helpers);
 same(center.first,py_round((1.23455+3.45675)/2.,4));same(center.second,py_round((2.34565+4.56785)/2.,4));
 const auto extent=row_extent({box},.3,&helpers);
 same(extent.first,py_round(box.x1+.3,4));same(extent.second,py_round(box.y1+.3,4));
 const auto half=turn_origin_180(1.23455,2.34565,3.45675,4.56785,.1,.2,4,&helpers);
 same(half.first,py_round(2.*1.23455-3.45675-.1,4));same(half.second,py_round(2.*2.34565-4.56785-.2,4));
 const auto turned=rotate_origin(1.23455,2.34565,3.45675,4.56785,.1,.2,31.25,4,&helpers);
 const double rad=31.25*(M_PI/180.0),cs=std::cos(rad),sn=std::sin(rad),rx=3.45675-1.23455,ry=4.56785-2.34565;
 same(turned.first,py_round((1.23455+(rx*cs+ry*sn))-.1,4));same(turned.second,py_round((2.34565+(-rx*sn+ry*cs))-.2,4));
 const auto sig=named_box_center_sigs({{"net",box.x0,box.y0,box.x1,box.y1}},2,&helpers);
 require(sig.size()==1&&std::get<2>(sig[0])=="net");
 same(std::get<0>(sig[0]),py_round((box.x0+box.x1)/2.,2));same(std::get<1>(sig[0]),py_round((box.y0+box.y1)/2.,2));
 const auto plane=canonical_plane_rect(25.,25.,20.12345,30.23455,.5,&helpers);
 same(plane.x0,py_round(25.+.5,3));same(plane.y0,py_round(25.+.5,3));
 same(plane.x1,py_round(25.+20.12345-.5,3));same(plane.y1,py_round(25.+30.23455-.5,3));
 const auto isolation=isolation_void_rect(box,.6,&helpers);
 same(isolation.x0,py_round(box.x0-.6,3));same(isolation.y0,py_round(box.y0-.6,3));
 same(isolation.x1,py_round(box.x1+.6,3));same(isolation.y1,py_round(box.y1+.6,3));
 (void)zone_fanout_reach(20,30,{},3,&helpers);
 plain_fixture::receipt(helpers,plain_fixture::end());
 require(helpers.at("pack_fanout_reach_precision4dp")==8);

 std::cout<<"plain18 scalar bits/registry/entries/ownership/negative contracts PASS\n";
 return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
