#include "schgen/pack.hpp"
#include "schgen/occupancy.hpp"
#include "../src/pack_refine_internal.hpp"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {
using namespace schgen;
std::size_t checks=0;
void require(bool ok,const char* why){++checks;if(!ok)throw std::runtime_error(why);}
bool halo(Halo a,Halo b){return a.w==b.w&&a.e==b.e&&a.n==b.n&&a.s==b.s;}
void eviction_region_properties() {
    // A removal can only enable a previously blocked pose if it conflicted
    // with the removed entity. Check that every such pose is inside the
    // proposed region using independent pair decomposition/collision tests.
    // Include protruding children on both faces and asymmetric signed insets.
    std::size_t affected=0,unaffected=0;
    for(int stored_mask:{1,2,3})for(int query_mask:{1,2,3})
      for(double offset:{-3.,0.,3.})for(bool asymmetric:{false,true}) {
        const Halo stored_reach=asymmetric?Halo{.25,2.,.75,1.5}:Halo{};
        const Halo stored_inset=asymmetric?Halo{-.5,.25,1.,-.25}:Halo{};
        const Halo query_reach=asymmetric?Halo{1.5,.25,2.,.5}:Halo{};
        const Halo query_inset=asymmetric?Halo{.75,-.5,.25,-.75}:Halo{};
        const std::vector<Comp> stored{{offset,-1.5,2,1,stored_mask==1?2:1,
                                     {1.25,.5,2.,.25},{-.25,.75,-.5,.25}}};
        const std::vector<Comp> query{{-offset,2.,1,2,query_mask==1?2:1,
                                     {.5,1.75,.25,1.25},{.25,-.25,.5,-.5}}};
        const auto region=evict_window(12,11,3,4,stored_reach,stored_inset,stored,
                                       2,3,query_reach,query_inset,query,.3);
        const auto obstacle=pairs_entity(12,11,3,4,stored_reach,stored_inset,stored_mask,stored);
        Occupancy empty(32,32,.3,2,3,.5,.05),occupied=empty;
        occupied.add(12,11,3,4,stored_reach,stored_inset,stored_mask,stored);
        for(int ix=0;ix<64;++ix)for(int iy=0;iy<64;++iy) {
            const double x=ix*.5,y=iy*.5;
            if(!empty.fits_exhaustive(x,y,2,3,query_reach,query_inset,query_mask,query))continue;
            const auto candidate=pairs_entity(x,y,2,3,query_reach,query_inset,query_mask,query);
            const bool separated=pairs_hold({obstacle,candidate},2,.3);
            require(occupied.fits_exhaustive(x,y,2,3,query_reach,query_inset,query_mask,query)==separated,
                    "eviction oracle disagrees with actual occupied-board geometry");
            if(separated){++unaffected;continue;}
            ++affected;
            require(x>=std::get<0>(region)&&x<=std::get<1>(region)&&
                    y>=std::get<2>(region)&&y<=std::get<3>(region),
                    "eviction region excludes a pose enabled by removal");
        }
    }
    require(affected>0&&unaffected>0,"eviction property must exercise blocked and unblocked poses");
    std::cout<<"eviction_region affected="<<affected<<" unaffected="<<unaffected<<'\n';
}
void frontier_rejection_properties() {
    for(int stored_mask:{1,2,3})for(int mask:{1,2,3})for(double anchor:{2.,5.05,8.}) {
        Occupancy grid(12,12,.25,2,3,1,.05);
        grid.add(3,3,4,4,{.5,1,.25,.75},{},stored_mask,
                 {{-.5,1,2,1,stored_mask==1?2:1,{1,.25,.5,.75},{}}});
        const std::vector<Comp> children{{1,-.5,1,1,mask==1?2:1,{.25,.75,1,.5},{}}};
        std::vector<std::tuple<double,double,double>> expected;
        for(int x=0;x<12;++x)for(int y=0;y<12;++y)
            if(grid.fits_exhaustive(x,y,2,2,{},{},mask,children))
                expected.emplace_back(py_round(std::abs(x+1-anchor)+std::abs(y+1-anchor),1),x,y);
        std::sort(expected.begin(),expected.end());
        const auto all=grid.place_near_candidates(anchor,anchor,2,2,{},{},mask,children,
                                                 0,12,0,12,200,1000);
        require(all.search_complete&&!all.budget_exhausted,"exhaustive frontier did not finish");
        require(all.poses.size()==expected.size(),"early rejection lost or added a legal pose");
        for(std::size_t i=0;i<expected.size();++i)
            require(all.poses[i].x==std::get<1>(expected[i])&&all.poses[i].y==std::get<2>(expected[i]),
                    "early rejection changed independent distance/x/y ordering");
        const auto limited=grid.place_near_candidates(anchor,anchor,2,2,{},{},mask,children,
                                                     0,12,0,12,200,10);
        require(limited.budget_exhausted&&limited.frontier_nodes==10,"rejected nodes escaped frontier budget");
        for(std::size_t i=0;i<limited.poses.size();++i)
            require(limited.poses[i].x==all.poses[i].x&&limited.poses[i].y==all.poses[i].y,
                    "limited frontier changed accepted prefix");
    }
}
void frontier_shape_properties() {
    // Include singleton rows/columns, uneven row lengths and many equal keys.
    for(int width:{1,2,3,7})for(int height:{1,2,6,11})for(double anchor:{0.,2.5,9.05}) {
        Occupancy grid(width,height,0,2,3,1,.05);
        std::vector<std::tuple<double,double,double>> expected;
        for(int x=0;x<width;++x)for(int y=0;y<height;++y)
            expected.emplace_back(py_round(std::abs(x+.5-anchor)+std::abs(y+.5-anchor),1),x,y);
        std::sort(expected.begin(),expected.end());
        const auto all=grid.place_near_candidates(anchor,anchor,1,1,{},{},1,{},
                                                 0,width,0,height,1000,1000);
        require(all.search_complete&&all.frontier_nodes==expected.size(),"frontier lost a row successor");
        require(all.poses.size()==expected.size(),"frontier result count changed");
        for(std::size_t i=0;i<expected.size();++i)
            require(all.poses[i].x==std::get<1>(expected[i])&&all.poses[i].y==std::get<2>(expected[i]),
                    "frontier replacement changed independent exhaustive ordering");
    }
}
void fractional_hash_properties() {
    // Stored children round absolute coordinates; query children deliberately
    // do not. Compare the two actual predicates, not a rounded-query oracle.
    for(double bucket:{.4,2.,12.})for(int parent:{1,2,3})
        for(double offset:{-.000051,-.00005,-.000049,0.,.000049,.00005,.000051}) {
            Occupancy grid(26,26,.3,bucket,8,1,.05);
            const std::vector<Comp> stored{{offset,.99995,2.000049,1.000051,
                parent==1?2:1,{.7,1.3,.9,1.9},{-.3,.8,-.4,.1}}};
            grid.add(8.000049,9.000051,3,3,{.2,.7,.5,.8},{},parent,stored);
            for(int mask:{1,2,3})for(int n=4;n<=36;++n)
                for(double direction:{-1.,1.}) {
                    const double x=std::nextafter(n*.5+offset,
                        direction*std::numeric_limits<double>::infinity());
                    const std::vector<Comp> query{{offset,-.500051,1.000049,1,
                        mask==1?2:1,{1,.5,2,.25},{.2,-.3,.5,-.7}}};
                    for(double y:{8.99995,9.00005,12.30005})
                        require(grid.fits_hashed(x,y,1,1,{},{},mask,query)==
                            grid.fits_exhaustive(x,y,1,1,{},{},mask,query),
                            "fractional child halo hash/exhaustive mismatch");
                }
        }
}
void properties() {
    const Halo r{.5,1,1.5,2},i{.25,.5,.25,0};
    for(double bucket:{.5,2.,9.})for(int parent:{1,2})for(int other:{1,2,3}) {
        const int minor=parent==1?2:1;
        std::vector<Comp> children{{-.5,.25,2,2,minor,r,i}};
        Occupancy grid(24,24,.25,bucket,3,1,.05);
        QuantizationCounts counts;
        grid.add(8,8,3,3,{},{},parent,children,&counts);
        const auto saved=pairs_entity(8,8,3,3,{},{},parent,children);
        require(halo(saved[1].reach,r)&&halo(saved[1].inset,i),"decomposition lost child halo");
        for(int y=2;y<=18;++y)for(int x=2;x<=18;++x) {
            std::vector<Comp> query{{.25,-.5,1,1,minor,{1,.5,.25,.75},{0,.25,0,.25}}};
            const bool hashed=grid.fits_hashed(x,y,2,2,{},{},other,query,&counts);
            const bool exhaustive=grid.fits_exhaustive(x,y,2,2,{},{},other,query);
            require(hashed==exhaustive,"child halo hash/exhaustive mismatch");
            const auto wanted=pairs_entity(x,y,2,2,{},{},other,query);
            require(hashed==pairs_hold({saved,wanted},2,.25),"child halo pair decomposition mismatch");
        }
        auto copy=grid;
        auto different=children;different[0].reach.w+=.25;
        copy.remove(8,8,3,3,{},{},parent,different,&counts);
        require(copy.rect_count()==1,"remove equality ignored child halo");
        copy=grid;copy.remove(8,8,3,3,{},{},parent,children,&counts);
        require(copy.rect_count()==0&&grid.rect_count()==2,"copy/remove leaked or lost child halo");
        for(char edge:{'N','S','E','W'}) {
            const auto moved=edge_components(edge,4,5,24,24,3,children,&counts);
            require(halo(moved[0].reach,r)&&halo(moved[0].inset,i),"edge copy lost minority halo");
        }
    }
    // Separate mask domains: a bottom primary's top child now protects its
    // fanout without preventing a bottom body from using top-only free space.
    Occupancy grid(30,30,.3,4,3,1,.05);
    const std::vector<Comp> child{{0,0,2,2,1,{2,2,2,2},{}}};
    grid.add(5,5,2,2,{},{},2,child);
    require(!grid.fits_hashed(8,5,1,1,{},{},1,{}),"minority fanout not enforced");
    require(grid.fits_hashed(8,5,1,1,{},{},2,{}),"child halo crossed copper mask");
    const auto old=evict_window(10,10,1,1,{},{},{},1,1,{},{},{},.3);
    const auto with_child=evict_window(10,10,1,1,{},{},child,1,1,{},{},{},.3);
    const auto with_query=evict_window(10,10,1,1,{},{},{},1,1,{},{},child,.3);
    require(std::get<0>(with_child)<std::get<0>(old)&&std::get<1>(with_child)>std::get<1>(old),"evicted child halo absent from window");
    require(std::get<0>(with_query)<std::get<0>(old)&&std::get<1>(with_query)>std::get<1>(old),"query child halo absent from window");
    // A halo-only candidate difference cannot be served by the first result.
    Occupancy occ(20,20,.3,4,3,1,.05);occ.add(8,8,1,1,{},{},1,{});
    SeatShapeCand a{0,1,1,{},{},2,"bottom",{{0,0,1,1,1}},0,19,0,19};
    auto b=a;b.index=1;b.comps[0].reach={2,2,2,2};
    QuantizationCounts all,memo;
    const auto expected=seat_shape_candidates(occ,7,8,{a,b},20,20,.3,&all);
    const auto got=floorplan_detail::seat_shape_candidates_on_current_board(occ,7,8,{a,b},20,20,.3,&memo);
    require(got.size()==expected.size()&&all==memo,"halo-distinct queries memoized");
    for(std::size_t n=0;n<got.size();++n)
        require(got[n].x==expected[n].x&&got[n].y==expected[n].y&&
            halo(got[n].comps[0].reach,expected[n].comps[0].reach),"halo-distinct result changed");
}
}
int main(){try{eviction_region_properties();frontier_shape_properties();frontier_rejection_properties();properties();fractional_hash_properties();std::cout<<"PASS child halo contracts checks="<<checks<<'\n';return 0;}
catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
