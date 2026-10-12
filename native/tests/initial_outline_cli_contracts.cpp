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
    const std::vector<std::string> reseat{"board","--compact-placement","--interior-order","3","--reseat-poses","8","--reseat-frontier","4096","--reseat-continuations","3"};
    const auto reseat_help=run(reseat);
    auto shape_args=reseat;shape_args.push_back("--reseat-victim-shapes");
    const auto shape_help=run(shape_args);
    if(shape_help.exit_code||shape_help.stdout_text.find("original strategies fail")==std::string::npos)
        throw std::runtime_error("shape strategy options/help failed");
    auto combined_args=shape_args;combined_args.push_back("--failed-first-retry");
    if(run(combined_args).exit_code)throw std::runtime_error("combined continuation/order/shape options rejected");
    shape_args.push_back("--reseat-victim-shapes");
    if(!run(shape_args).exit_code)throw std::runtime_error("duplicate shape strategy accepted");
    for(const auto& args:std::vector<std::vector<std::string>>{
        {"board","--reseat-victim-shapes"},
        {"board","--compact-placement","--reseat-poses","8","--reseat-frontier","4096","--reseat-victim-shapes"},
        {"pcb-stage","--reseat-victim-shapes"}})
        if(!run(args).exit_code)throw std::runtime_error("invalid shape strategy configuration accepted");
    if(reseat_help.exit_code||reseat_help.stdout_text.find("limits bound search effort, not feasibility")==std::string::npos)
        throw std::runtime_error("valid continuation options/help failed");
    for(const auto& args:std::vector<std::vector<std::string>>{
        {"board","--reseat-poses","8","--reseat-frontier","4096"},
        {"board","--compact-placement","--reseat-poses","8"},
        {"board","--compact-placement","--reseat-frontier","4096"},
        {"board","--compact-placement","--reseat-poses","1","--reseat-frontier","4096"},
        {"board","--compact-placement","--reseat-poses","8","--reseat-frontier","4096","--reseat-continuations","3"},
        {"pcb-stage","--reseat-poses","8","--reseat-frontier","4096"}})
        if(!run(args).exit_code)throw std::runtime_error("invalid continuation configuration accepted");
    for(const auto* flag:{"--reseat-poses","--reseat-frontier","--reseat-continuations"}){
        auto duplicate=reseat;duplicate.insert(duplicate.end(),{flag,"2"});
        if(!run(duplicate).exit_code)throw std::runtime_error("duplicate reseat limit accepted");
        for(const auto* value:{"0","-1","2.5","2x","","99999999999999999999999999"})
            if(!run({"board","--compact-placement",flag,value}).exit_code)
                throw std::runtime_error("invalid reseat integer accepted");
    }
    auto composed=reseat;composed.push_back("--failed-first-retry");
    if(run(composed).exit_code)throw std::runtime_error("continuation and failed-first composition rejected");
    for(const auto* slots:{"1","2"}){
        const auto result=run({"board","--audit-projections",slots});
        if(result.exit_code||result.stdout_text.find("audit coverage and source-change checks are unchanged")==std::string::npos)
            throw std::runtime_error("audit projection choice/help rejected");
    }
    for(const auto* slots:{"0","3","-1","2.0","2junk",""})
        if(!run({"board","--audit-projections",slots}).exit_code)throw std::runtime_error("invalid projection choice accepted");
    for(const auto& args:std::vector<std::vector<std::string>>{
        {"board","--audit-projections"},{"board","--audit-projections","1","--audit-projections","2"},
        {"pcb-stage","--audit-projections","2"}})
        if(!run(args).exit_code)throw std::runtime_error("invalid projection option scope accepted");
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
    const auto feasible=run({"board","--compact-placement","--edge-feasibility"});
    for(const auto* value:{"1","128"})
        if(run({"board","--compact-placement","--joint-separation-states",value}).exit_code)
            throw std::runtime_error("valid joint search option rejected");
    for(const auto* value:{"","0","-1","1.0","128junk"," 128","18446744073709551615","9999999999999999999999999"})
        if(run({"board","--compact-placement","--joint-separation-states",value}).exit_code==0)
            throw std::runtime_error("invalid joint search budget accepted");
    for(const auto& args:std::vector<std::vector<std::string>>{
        {"board","--joint-separation-states","128"},
        {"pcb-stage","--joint-separation-states","128"},
        {"board","--compact-placement","--joint-separation-states"},
        {"board","--compact-placement","--joint-separation-states","128","--joint-separation-states","128"}})
        if(run(args).exit_code==0)throw std::runtime_error("invalid joint search invocation accepted");
    if(feasible.exit_code||feasible.stdout_text.find("Not a complete joint solver")==std::string::npos)
        throw std::runtime_error("edge feasibility help must disclose solver limits");
    if(run({"board","--compact-placement","--interior-order","3","--failed-first-retry"}).exit_code)
        throw std::runtime_error("valid failed-first retry option rejected");
    for(const auto& args:std::vector<std::vector<std::string>>{
        {"board","--compact-placement","--failed-first-retry"},
        {"board","--interior-order","3","--failed-first-retry"},
        {"board","--compact-placement","--interior-order","3","--failed-first-retry","--failed-first-retry"},
        {"pcb-stage","--failed-first-retry"}})
        if(run(args).exit_code==0)throw std::runtime_error("invalid failed-first retry option accepted");
    const auto quality=run({"board","--compact-placement","--owned-quality-first"});
    if(quality.exit_code||quality.stdout_text.find("May increase inter-block estimate")==std::string::npos)
        throw std::runtime_error("quality-first help must disclose tradeoff");
    const auto extent=run({"board","--compact-placement","--owned-extent-alternatives"});
    if(extent.exit_code||extent.stdout_text.find("Original alternatives and all gates remain active")==std::string::npos)
        throw std::runtime_error("extent alternatives help must disclose retained safeguards");
    for(const auto& args:std::vector<std::vector<std::string>>{
        {"board","--owned-extent-alternatives"},
        {"board","--compact-placement","--owned-extent-alternatives","--owned-extent-alternatives"},
        {"pcb-stage","--owned-extent-alternatives"}})
        if(run(args).exit_code==0)throw std::runtime_error("invalid extent-alternative option accepted");
    if(run({"board","--compact-placement","--owned-face-cohesion","--owned-shape","board_aux=tag","--owned-shape","bringup_rails=tag2"}).exit_code)
        throw std::runtime_error("valid named candidate help failed");
    const auto groups=run({"board","--compact-placement","--contract-group-face-sheet","usb_jtag"});
    if(groups.exit_code||groups.stdout_text.find("No assembly or thermal approval is implied")==std::string::npos)
        throw std::runtime_error("contract-group help must disclose qualification limits");
    if(run({"board","--compact-placement","--contract-group-face-sheet","usb_jtag","--contract-group-face-sheet","power"}).exit_code)
        throw std::runtime_error("distinct contract-group sheets must be accepted together");
    for(const auto& args:std::vector<std::vector<std::string>>{
        {"board","--owned-face-cohesion"}, {"board","--owned-shape","board_aux=tag"},
        {"board","--contract-group-face-sheet","usb_jtag"},
        {"board","--compact-placement","--contract-group-face-sheet"},
        {"board","--compact-placement","--contract-group-face-sheet",""},
        {"board","--compact-placement","--contract-group-face-sheet","a","--contract-group-face-sheet","a"},
        {"pcb-stage","--contract-group-face-sheet","usb_jtag"},
        {"board","--compact-placement","--owned-face-cohesion","--owned-face-cohesion"},
        {"board","--compact-placement","--owned-shape","=tag"},
        {"board","--compact-placement","--owned-shape","a="},
        {"board","--compact-placement","--owned-shape","a=b=c"},
        {"board","--compact-placement","--owned-shape","a=b","--owned-shape","a=c"},
        {"pcb-stage","--owned-shape","a=b"}})
        if(run(args).exit_code==0)throw std::runtime_error("invalid named candidate option accepted");
    for(const auto& args:std::vector<std::vector<std::string>>{
        {"board","--owned-quality-first"},
        {"board","--compact-placement","--owned-quality-first","--owned-quality-first"},
        {"pcb-stage","--owned-quality-first"}})
        if(run(args).exit_code==0)throw std::runtime_error("invalid quality-first option accepted");
    for(const auto& args:std::vector<std::vector<std::string>>{
        {"board","--edge-feasibility"},
        {"board","--compact-placement","--edge-feasibility","--edge-feasibility"},
        {"pcb-stage","--edge-feasibility"}})
        if(run(args).exit_code==0)throw std::runtime_error("invalid edge feasibility option accepted");
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
