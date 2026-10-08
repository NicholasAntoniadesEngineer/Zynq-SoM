#include "schgen/process.hpp"
#include <iostream>
#include <stdexcept>
int main(int argc,char** argv){try{
    if(argc!=2)throw std::runtime_error("executable required");
    const std::string binary=argv[1];
    const auto run=[&](std::vector<std::string> args){
        args.insert(args.begin(),binary);
        args.insert(args.end(),{"--help","--repo","/nonexistent/seed-help-must-not-read"});
        return schgen::run_process(args);
    };
    for(const auto* value:{"168x163","98x98","1e2x9.8e1","168.25x163.5"}){
        const auto result=run({"board","--initial-outline-mm",value});
        if(result.exit_code || result.stdout_text.find("Not a fixed outline or cached acceptance")==std::string::npos)
            throw std::runtime_error("valid seed/help failed without reading repository");
    }
    for(const auto* value:{"","168","168x","x163","168x163x1","0x98","-1x98","nanx98","infx98","1e300x1e300","1e999x98","168mmx163","168x163junk"," 168x163"}){
        const auto result=run({"board","--initial-outline-mm",value});
        if(result.exit_code==0 || (result.stderr_text+result.stdout_text).find("outline")==std::string::npos)
            throw std::runtime_error(std::string("malformed seed not rejected: ")+value);
    }
    if(run({"board","--initial-outline-mm","168x163","--initial-outline-mm","98x98"}).exit_code==0)
        throw std::runtime_error("duplicate seed accepted");
    if(run({"pcb-stage","--initial-outline-mm","168x163"}).exit_code==0)
        throw std::runtime_error("unsupported command accepted seed");
    if(run({"board","--initial-outline-mm","168x163","--compact-placement"}).exit_code!=0)
        throw std::runtime_error("seed and compact placement must be independent options");
    std::cout<<"PASS initial-outline CLI validation, help isolation and option boundaries\n";
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}}
