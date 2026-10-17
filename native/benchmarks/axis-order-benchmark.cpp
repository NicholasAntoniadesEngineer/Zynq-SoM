#include "occupancy_axis_order_internal.hpp"
#include <chrono>
#include <cmath>
#include <iostream>

int main(){
    using Axis=std::vector<std::pair<double,double>>;
    std::vector<Axis> inputs;
    for(int k=0;k<64;++k){
        Axis a;
        for(int i=0;i<320;++i){const double x=i*.5;a.emplace_back(std::abs(x+10-k*3.),x);}
        inputs.push_back(std::move(a));
    }
    volatile double checksum=0;
    for(int round=0;round<4;++round)for(int pass=0;pass<2;++pass){
        const bool linear=(round+pass)%2;
        const auto start=std::chrono::steady_clock::now();
        for(int repeat=0;repeat<200;++repeat)for(const auto& input:inputs){
            auto a=input;
            if(linear)schgen::occupancy_detail::order_axis(a);
            else std::sort(a.begin(),a.end());
            checksum+=a[repeat%a.size()].second;
        }
        const double elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
        std::cout<<"round="<<round<<" method="<<(linear?"merge":"sort")<<" seconds="<<elapsed<<'\n';
    }
    std::cout<<"checksum="<<checksum<<'\n';
}
