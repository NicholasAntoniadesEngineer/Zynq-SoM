#include "pack_combined_source_contracts.hpp"
int main(int argc,char** argv){try{if(argc!=3)throw std::runtime_error("repository root and fresh scratch required");pack_combined_source::run(argv[1],argv[2]);return 0;}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
