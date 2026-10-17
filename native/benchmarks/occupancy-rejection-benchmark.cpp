#include "schgen/occupancy.hpp"
#include <chrono>
#include <iostream>
#include <stdexcept>

int main(){
    using namespace schgen;
    for(const int strips:{1,2,4,16}){
        Occupancy o(80,70,.1,4,2,.5,.05);
        for(int i=0;i<strips;++i)o.add(i*80./strips,0,80./strips,70,{},{},1,{});
        QuantizationCounts counts;
        const auto start=std::chrono::steady_clock::now();
        for(int i=0;i<320;++i)
            if(o.place_near(25+i%32,35,2,2,{},{},1,{},0,80,0,70,&counts))
                throw std::runtime_error("fully occupied board returned a pose");
        std::cout<<"strips="<<strips<<" seconds="
            <<std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count()
            <<" cell_indices="<<counts["occupancy_cell_index"]
            <<" frontier="<<counts["occupancy_frontier_key1dp"]<<'\n';
    }
}
