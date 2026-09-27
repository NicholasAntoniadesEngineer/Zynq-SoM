#include "schgen/pack.hpp"
#include "schgen/execution_accounting.hpp"
#include "pack_geometry_observer.hpp"
#ifdef PACK_GEOMETRY_CANDIDATE
#include "schgen/pack_geometry_precision.hpp"
#endif
#include <cstring>
#include <iostream>
#include <fstream>
#include <sstream>
std::ostringstream legacy;
#include <limits>
#include <stdexcept>
using namespace schgen;
QuantizationCounts counts;
#ifdef PACK_GEOMETRY_CANDIDATE
#define RECEIPT , &counts
#else
#define RECEIPT
#endif
void require(bool b) { if (!b) throw std::runtime_error("pack geometry contract"); }
void emit(double v) { std::uint64_t b; std::memcpy(&b,&v,sizeof b); legacy<<std::hex<<b<<' '; }
void emit(int v) { legacy<<std::dec<<v<<' '; }
void emit(const std::string& v) { legacy<<v.size()<<':'<<v<<' '; }
void emit(const Box4& b) { emit(b.x0);emit(b.y0);emit(b.x1);emit(b.y1); }
void emit(const Comp& c) {emit(c.dx);emit(c.dy);emit(c.w);emit(c.h);emit(c.mask);}
template<class A,class B> void emit(const std::pair<A,B>& p){emit(p.first);emit(p.second);}
template<class... T> void emit(const std::tuple<T...>& t){std::apply([](const auto&... x){(emit(x),...);},t);}
template<class T> void emit(const std::vector<T>& v){emit(static_cast<int>(v.size()));for(const auto& x:v)emit(x);}
void begin(const char* label) { legacy<<'\n'<<label<<' ';counts={{"preexisting_operation",7}}; geometry_fixture::begin(); }
void check(QuantizationCounts expected) {
    geometry_fixture::receipt(counts, geometry_fixture::end());
#ifdef PACK_GEOMETRY_CANDIDATE
    for(auto it=expected.begin();it!=expected.end();) if(!it->second)it=expected.erase(it);else ++it;
    expected["preexisting_operation"]=7;
    require(counts==expected);
#else
    (void)expected;require(counts==QuantizationCounts{{"preexisting_operation",7}});
#endif
}
int main(int argc,char** argv){
try{
    require(argc==2);
    for(char axis:{'E','S','N','W'}){
        begin("pair"); emit(pair_gap({1.23455,2.1,3.5,4.2},{.1,.2,.3,.4},
                              {2.5,3.2,1.1,2.2},{.3,.1,.4,.2},axis,.25 RECEIPT));
        check({{"pack_pair_gap_precision4dp",1}});
    }
    for(char edge:{'N','S','W','E','?'}) for(int n:{0,1,2}){
        std::vector<Comp> c{{-.00005,1.23455,2.55555,3.44445,4},{2.1,-.00005,4.5,6.5,1}};
        c.resize(n);begin("edge");emit(edge_components(edge,7.12345,9.45675,50,60,4,c RECEIPT));
        check({{"pack_edge_component_precision4dp",static_cast<std::size_t>(4*n)}});
    }
    for(int n:{-2,0,1,5,17}) for(double w:{.5,20.12345}){
        begin("grid");emit(som_decoupling_grid(w,13.12345,n,6 RECEIPT));
        check({{"pack_som_grid_precision0dp",n!=0},{"pack_som_grid_trunc",n!=0}});
        begin("cells");emit(som_decoupling_cells(-1.23455,2.55555,w,13.12345,n,6 RECEIPT));
        check({{"pack_som_grid_precision0dp",n>0},{"pack_som_grid_trunc",n>0},
               {"pack_som_cell_precision4dp",static_cast<std::size_t>(n>0?2*n:0)}});
    }
    for(int n:{0,1,2})for(int b:{0,1,2}){
        std::vector<std::pair<double,double>> cells{{1.23455,2.55555},{-3.33335,4.00005}};
        std::vector<Box4> bands{{-.00005,1.23455,2.00005,4.55555},{3.2,4.3,5.4,6.5}};
        cells.resize(n);bands.resize(b);begin("som");
        emit(som_components(.12345,-.12345,.55555,cells,bands,1,4 RECEIPT));
        check({{"pack_som_diameter_precision4dp",1},
               {"pack_som_component_pose_precision4dp",static_cast<std::size_t>(2*n)},
               {"pack_som_band_component_precision4dp",static_cast<std::size_t>(4*b)}});
        begin("zone");emit(zone_components_assemble(bands,bands,1,4 RECEIPT));
        check({{"pack_zone_component_precision4dp",static_cast<std::size_t>((b?4:0)+4*b)}});
    }
    for(int n:{0,1,3}){
        std::vector<std::pair<double,double>> halves{{.55555,.88885},{1.23455,.33335},{.4,.5}};
        halves.resize(n);begin("cout");
        emit(cout_column_centers({1.1,2.2,3.33335,4.44445},.25,1,.3,halves RECEIPT));
        check({{"pack_cout_pose_precision4dp",static_cast<std::size_t>(n?1+n:0)}});
    }
    for(const std::string direction:{"U","D","other"}){
        begin("bulk");emit(bulk_cap_pose(10,{1.2,2.33335,3.4,4.55555},direction,.3,1.2,.9,5.5,.3 RECEIPT));
        check({{"pack_bulk_pose_precision4dp",2}});
    }
    for(int n:{0,1,2}){
        std::vector<std::tuple<std::string,double,double>> offs{{"a",1.23455,-.00005},{"b",-2.5,3.55555}};
        offs.resize(n);begin("rotate");emit(rotate_offsets_90(offs,9.12345 RECEIPT));
        check({{"pack_rotated_offset_precision4dp",static_cast<std::size_t>(2*n)}});
    }
    for(double rot:{0.,90.,180.,270.,31.25}){
        begin("corridor");emit(corridor_board_rect({-1.12345,-2.33335,3.55555,4.66665},7.55555,8.99995,rot RECEIPT));
        check({{"pack_corridor_bound_precision4dp",4}});
    }
    begin("mirror");emit(mirror_offset_x(1.23455,-0.,{-.5,-1,2.33335,3},7.12345 RECEIPT));
    check({{"pack_mirror_offset_precision4dp",1}});
#ifdef PACK_GEOMETRY_CANDIDATE
    // Pure API calls never write to an unrelated receipt; copied receipts are independent.
    counts={{"sentinel",9}};auto copy=counts;
    auto pure=mirror_offset_x(1.23455,-0.,{-.5,-1,2.33335,3},7.12345);
    auto accounted=mirror_offset_x(1.23455,-0.,{-.5,-1,2.33335,3},7.12345,&copy);
    require(pure==accounted&&counts==QuantizationCounts{{"sentinel",9}});
    require(copy==QuantizationCounts({{"sentinel",9},{"pack_mirror_offset_precision4dp",1}}));
    for(double v:{std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN(),2147483648.,-2147483649.}){
        counts.clear();bool rejected=false;try{(void)pack_som_grid_trunc(v,&counts);}catch(const std::out_of_range&){rejected=true;}
        require(rejected&&counts==QuantizationCounts{{"pack_som_grid_trunc",1}});
    }
    require(pack_som_grid_trunc(2147483647.75)==2147483647);
    require(pack_som_grid_trunc(-2147483648.75)==std::numeric_limits<int>::min());
    counts={{"pack_pair_gap_precision4dp",std::numeric_limits<std::size_t>::max()}};
    bool overflow=false;try{(void)pack_pair_gap_precision4dp(1.,&counts);}catch(const std::overflow_error&){overflow=true;}
    require(overflow&&counts.at("pack_pair_gap_precision4dp")==std::numeric_limits<std::size_t>::max());
#endif
    legacy<<'\n';
    std::ifstream input(argv[1],std::ios::binary);
    if(!input)throw std::runtime_error("missing frozen helper fixture");
    const std::string expected{std::istreambuf_iterator<char>(input),std::istreambuf_iterator<char>()};
    require(legacy.str()==expected);
    std::cerr<<"pack geometry scalar/helper contracts PASS\n";
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
