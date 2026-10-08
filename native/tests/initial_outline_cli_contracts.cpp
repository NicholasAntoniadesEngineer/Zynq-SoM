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
    const auto multiscale=run({"board","--initial-outline-mm","168x160","--compact-placement","--multiscale-outline"});
    if(multiscale.exit_code||multiscale.stdout_text.find("larger local solution")==std::string::npos)
        throw std::runtime_error("multiscale help must disclose local-solution limits");
    if(run({"board","--multiscale-outline","--multiscale-outline"}).exit_code==0||
       run({"pcb-stage","--multiscale-outline"}).exit_code==0)
        throw std::runtime_error("duplicate or unsupported multiscale option accepted");
    for(const auto* value:{"0","1","2","3"})
        if(run({"board","--interior-order",value,"--floorplan-spec","/nonexistent/help-only.json","--compact-placement"}).exit_code)
            throw std::runtime_error("valid candidate options must parse without reading repository during help");
    for(const auto* value:{"","-1","4","nan","3.0","3junk","999999999999999999"," 3"})
        if(run({"board","--interior-order",value}).exit_code==0)
            throw std::runtime_error("invalid order accepted");
    for(const auto* option:{"--floorplan-spec","--interior-order"}) {
        const std::string value=std::string(option)=="--interior-order"?"3":"candidate.json";
        if(run({"board",option,value,option,value}).exit_code==0)
            throw std::runtime_error("duplicate candidate option accepted");
        if(run({"pcb-stage",option,value}).exit_code==0)
            throw std::runtime_error("candidate option accepted by unsupported command");
    }
    std::cout<<"PASS seed/candidate CLI validation, help isolation and option boundaries\n";
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}}
