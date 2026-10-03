#include "bench.hpp"
#include "schgen/occupancy.hpp"
#include <chrono>
Result ENTRY(int iterations,bool counted) {
    using namespace schgen;
    Occupancy occ(168,163,.5,12,4,1,.05);
    const std::vector<Comp> children{{-.5,.25,.75,1.25,2},{2.25,1.5,1,1,3}};
    for(int y=0;y<8;++y) for(int x=0;x<9;++x)
        occ.add(8+x*17,8+y*18,4+x%4,5+y%3,{1,2,1,2},{.5,.25,.5,.25},1+(x+y)%3,children);
    Result out{};
    for(int i=0;i<300;++i)out.counts["existing_receipt_"+std::to_string(i)]=i;
    auto* counts=counted?&out.counts:nullptr;
    const auto start=std::chrono::steady_clock::now();
    for(int i=0;i<iterations;++i) {
        const double x=i%159+.125,y=(std::uint64_t(i)*37)%154+.25;
        const bool fit=occ.fits_hashed(x,y,1.5,1.75,{.2,.3,.4,.1},{},1,children,counts);
        out.digest=out.digest*1099511628211ULL+std::uint64_t(fit);
    }
    out.seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
    return out;
}
