#include "pack_combined_source_contracts.hpp"
int main(int argc,char** argv){try{if(argc!=2&&argc!=3)throw std::runtime_error("[before-root] after-root required");pack_combined_source::run(argv[argc-1],pack_combined_source::scratch_path(),argc==3?std::filesystem::path(argv[1]):std::filesystem::path{});return 0;}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
