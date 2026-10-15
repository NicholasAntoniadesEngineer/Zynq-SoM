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
int main(){try{properties();fractional_hash_properties();std::cout<<"PASS child halo contracts checks="<<checks<<'\n';return 0;}
catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
