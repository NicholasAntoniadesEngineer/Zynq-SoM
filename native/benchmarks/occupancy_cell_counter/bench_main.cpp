#include "bench.hpp"
#include <iomanip>
#include <iostream>
#include <stdexcept>
int main() {try {
    std::cout<<std::setprecision(9);
    for(bool counted:{true,false}) {
        (void)baseline_run(10000,counted);(void)candidate_run(10000,counted);
        for(int trial=0;trial<6;++trial) {
            Result before,after;
            if(trial%2) {after=candidate_run(1000000,counted);before=baseline_run(1000000,counted);}
            else {before=baseline_run(1000000,counted);after=candidate_run(1000000,counted);}
            if(before.digest!=after.digest || before.counts!=after.counts)throw std::runtime_error("query result/receipt mismatch");
            std::cout<<"counted="<<counted<<" trial="<<trial<<" order="<<(trial%2?"new-old":"old-new")
                <<" reference_seconds="<<before.seconds<<" candidate_seconds="<<after.seconds
                <<" ratio="<<after.seconds/before.seconds<<" digest="<<before.digest
                <<" cell_entries="<<before.counts["occupancy_cell_index"]<<'\n'<<std::flush;
        }
    }
    std::cout<<"REAL_HASH_QUERY_PAIR_PASS\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
