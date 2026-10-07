#include "edge_translation_internal.hpp"
#include <iostream>
#include <limits>
using namespace schgen;
using namespace schgen::floorplan_detail;
namespace {
std::size_t calls=0;bool watching=false;
void require(bool value,const char* why){if(!value)throw std::runtime_error(why);}
bool same(const std::vector<EdgeFanoutBlock>& a,const std::vector<EdgeFanoutBlock>& b) {
    if(a.size()!=b.size())return false;
    for(std::size_t i=0;i<a.size();++i)
        if(a[i].x!=b[i].x||a[i].y!=b[i].y||a[i].w!=b[i].w||a[i].h!=b[i].h||a[i].edge!=b[i].edge)return false;
    return true;
}
}
extern "C" void __cyg_profile_func_enter(void* fn,void*) {
    if(watching&&fn==reinterpret_cast<void*>(&pack_edge_pose_precision4dp))++calls;
}
extern "C" void __cyg_profile_func_exit(void*,void*){}
int main(){try{
    const std::vector<EdgeFanoutBlock> source{{10,1.5,10,9,{},{},'N'},{1.5,10.5,9,5,{},{},'W'}};
    QuantizationCounts counts;calls=0;watching=true;
    const auto result=translate_edge_runs(source,{},30,30,10,.5,&counts);watching=false;
    require(result.valid&&result.moved_edge=='W'&&result.shift==.5,"bounded cross-edge repair");
    require(result.candidates==12&&calls==12&&counts.at("pack_edge_pose_precision4dp")==calls,"rejected and accepted coordinates independently counted");
    require(result.blocks[0].x==10&&result.blocks[1].y==11,"only selected edge translated");
    require(source[1].y==10.5,"source immutable");
    require(cross_edge_fanout_hold(result.blocks,.5),"repaired cross-edge clearance");
    const auto repeated=translate_edge_runs(source,{},30,30,10,.5);
    require(same(result.blocks,repeated.blocks)&&result.candidates==repeated.candidates,"repeatable bounded search");
    QuantizationCounts idle;const auto unchanged=translate_edge_runs(result.blocks,{},30,30,10,.5,&idle);
    require(unchanged.valid&&unchanged.candidates==0&&unchanged.moved_edge=='\0'&&idle.empty()&&same(result.blocks,unchanged.blocks),"valid incumbent does no search or quantization");
    calls=0;counts.clear();watching=true;
    const auto failed=translate_edge_runs(source,{{0,0,30,30}},30,30,10,.5,&counts);watching=false;
    require(!failed.valid&&failed.candidates==16&&same(source,failed.blocks),"exhausted repair preserves source exactly");
    require(calls==16&&counts.at("pack_edge_pose_precision4dp")==calls,"failed search retains every call");
    auto bounded=source;bounded[1].reach.s=10;
    require(!translate_edge_runs(bounded,{},30,30,10,.5).valid,"fanout margin cannot be waived to fit");
    auto paired=source;paired.push_back({1.5,16,9,2,{},{},'W'});
    const auto group=translate_edge_runs(paired,{},30,30,10,.5);
    require(group.valid&&group.blocks[2].y-group.blocks[1].y==5.5,"whole edge retains internal spacing");
    auto overlapping=source;overlapping.push_back(source[1]);
    require(!translate_edge_runs(overlapping,{},30,30,10,.5).valid,"same-edge overlap cannot be accepted");
    // Captured carrier arithmetic: rounded poses leave a roundoff-sized deficit in
    // the forward clearance expression. Do not hide it with an epsilon.
    const std::vector<EdgeFanoutBlock> rounding_gap{
        {110.3302,1.5,10.988099999999999,17.9341,{0,1.4499,0,0},{},'N'},
        {122.76819999999999,1.5,10.988099999999999,12.6341,{},{},'N'}};
    const auto rounding=translate_edge_runs(rounding_gap,{},168,159,10,.3);
    require(!rounding.valid||rounding.moved_edge!='\0',"rounded unsafe source cannot pass unchanged");
    auto rotated=source;
    for(int turn=0;turn<4;++turn) {
        const auto r=translate_edge_runs(rotated,{},30,30,10,.5);
        require(r.valid&&r.candidates<=32&&cross_edge_fanout_hold(r.blocks,.5),"all four edge orientations repair safely within bound");
        for(auto& b:rotated) {
            const auto old=b;b.x=30-old.y-old.h;b.y=old.x;b.w=old.h;b.h=old.w;
            b.edge=old.edge=='N'?'E':old.edge=='E'?'S':old.edge=='S'?'W':'N';
        }
    }
    for(int mode=0;mode<3;++mode) {
        auto bad=source;
        if(mode==0)bad[0].x=std::numeric_limits<double>::quiet_NaN();
        if(mode==1)bad[0].edge='?';
        if(mode==2)bad[0].w=-1;
        bool threw=false;try{(void)translate_edge_runs(bad,{},30,30,10,.5);}catch(const std::invalid_argument&){threw=true;}
        require(threw,"invalid input fails closed");
    }
    std::cout<<"PASS bounded edge translation, incumbent/failed state, margins, groups and independent counts\n";
}catch(const std::exception& e){watching=false;std::cerr<<e.what()<<'\n';return 1;}}
