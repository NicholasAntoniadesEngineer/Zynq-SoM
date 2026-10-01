#include "schgen/pack.hpp"
#include <cmath>
#include <climits>
#include <iostream>
using namespace schgen;
int main(int argc,char** argv){if(argc!=2)return 2;try{
 const std::string mode=argv[1];
 if(mode=="nan")(void)fallback_via_sites(0,0,NAN,1,0,1);
 else if(mode=="product")(void)fallback_via_sites(0,0,46340,46340,0,1);
 else if(mode=="vertical")(void)seat_band({{"a",-.4,0},{"b",.4,0}},{},{},{},{},double(INT_MIN),0,{{0,0}},{},0,0,1,"J",0);
 else if(mode=="depth")(void)seat_band({{"a",-2,0},{"b",2,0}},{},{},{},{},1,0,{},{},0,1,1,"J",INT_MAX);
 else return 2;
 std::cerr<<"unexpected accepted\n";return 1;
}catch(const std::exception& e){std::cout<<"checked rejection: "<<e.what()<<'\n';return 0;}}
