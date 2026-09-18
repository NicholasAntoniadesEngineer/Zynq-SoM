#include "schgen/spice.hpp"
#include "schgen/process.hpp"
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <sys/stat.h>
#include <thread>
#include <unistd.h>

namespace {
using namespace schgen;
std::size_t checks=0;
void require(bool v,const std::string& message){++checks;if(!v)throw std::runtime_error(message);}
const JsonNode& field(const JsonNode& n,const std::string& key){auto p=object_field(n,key);if(!p)throw std::runtime_error("missing "+key);return *p;}
void same(const JsonNode& a,const JsonNode& b,const std::string& path) {
    require(a.kind==b.kind,path+": type differs");
    switch(a.kind){
    case JsonKind::Null:break;
    case JsonKind::Bool:require(a.bool_value==b.bool_value,path+": boolean differs");break;
    case JsonKind::Number:require(a.number_value==b.number_value,path+": numeric value differs");break;
    case JsonKind::String:require(a.string_value==b.string_value,path+": "+a.string_value+" != "+b.string_value);break;
    case JsonKind::Array:require(a.array_value.size()==b.array_value.size(),path+": count differs");for(std::size_t i=0;i<a.array_value.size();++i)same(a.array_value[i],b.array_value[i],path+"["+std::to_string(i)+"]");break;
    case JsonKind::Object:require(a.object_value.size()==b.object_value.size(),path+": field count differs");for(const auto& [k,v]:a.object_value)same(v,field(b,k),path+"."+k);break;
    }
}
std::optional<double> number(const JsonNode& n,const std::string& key){const auto& v=field(n,key);return v.kind==JsonKind::Null?std::nullopt:std::optional<double>(v.number_value);}
SpiceResult runnable(){SpiceResult out;out.checks.push_back({"divider TEST","sheet","divider","+3V3 -[R1=10000R]- TEST -[R2=10000R]- GND @ 3.3 V",1.65,"V",0.0,3.3,"analytic",{}});return out;}
}
int main(int argc,char** argv) {
    if(argc==3&&std::string(argv[1])=="-b") {
        const auto* mode=std::getenv("SCHGEN_SELFTEST_PROCESS_MODE");const std::string test=mode?mode:"";
        if(test=="value"){std::cout<<"mid = 1.65\r\n";return 0;}
        if(test=="nonzero_value"){std::cout<<"mid = 1.65\n";std::cerr<<"warn\n";return 7;}
        if(test=="disagreement"){std::cout<<"mid = 1.8\n";return 0;}
        if(test=="invalid_utf8"){std::cout<<char(0xff)<<"mid = 1.65\n";return 0;}
        if(test=="unicode_measurement"){std::cout<<"mid\u00a0=\u2003١.٦٥\n";return 0;}
        if(test=="malformed_measurement"){std::cout<<"mid = 1-2\n";return 0;}
        if(test=="sleep"){std::this_thread::sleep_for(std::chrono::seconds(5));return 0;}
        if(test=="argv"){std::cout<<argv[2];return 0;}
        std::cout<<"no measurement\n";return 3;
    }
    try {
        require(argc==2,"usage: spice_contracts <fixture-directory>");const std::filesystem::path dir(argv[1]);
        const auto manifest=parse_json_file((dir/"manifest.json").string());std::size_t passed=0,live=0;
        const auto ngspice=ngspice_available();
        for(const auto& file:field(manifest,"cases").array_value) {
            const auto row=parse_json_file((dir/file.string_value).string());std::vector<ProjectCircuit> sheets;
            for(const auto& sc:field(row,"sheets").array_value)sheets.push_back({field(sc,"name").string_value,{},decode_intermediate_circuit_ir(field(sc,"circuit"))});
            const auto* error=object_field(row,"error");std::optional<SpiceResult> result;
            try{result=extract_spice_checks(sheets);}
            catch(const ModelCheckError& e){require(error!=nullptr,file.string_value+": unexpected error "+e.what());require(field(*error,"message").string_value==e.what(),file.string_value+": diagnostic differs "+e.what());}
            require(bool(result)==!bool(error),file.string_value+": expected error presence differs");
            if(result){same(spice_result_json(*result),field(row,"expected"),file.string_value);require(spice_report(*result,false)==field(row,"report_absent").string_value,file.string_value+": absent report differs");require(spice_report(*result,true)==field(row,"report_present").string_value,file.string_value+": present report differs");
                if(const auto* expected=object_field(row,"ngspice");expected&&ngspice){SpiceRunOptions opts;opts.executable=ngspice;run_ngspice_crosschecks(*result,opts);same(spice_result_json(*result),*expected,file.string_value+".ngspice");require(spice_report(*result,true)==field(row,"ngspice_report").string_value,file.string_value+": live ngspice report differs");++live;}
            }
            ++passed;
        }
        const auto boundaries=parse_json_file((dir/"boundaries.json").string());
        for(const auto& row:boundaries.array_value) {
            const auto& c=field(row,"check");SpiceCheck value;
            value.value=field(c,"value").number_value;value.lo=number(c,"lo");value.hi=number(c,"hi");value.spice_value=number(c,"spice_value");
            require(value.ok()==field(row,"ok").bool_value,"comparison tolerance boundary differs");
        }
        const auto executable=std::filesystem::absolute(argv[0]);SpiceRunOptions opts;opts.executable=executable;
        for(const auto* mode:{"value","nonzero_value","disagreement","no_measurement","unicode_measurement"}) {
            ::setenv("SCHGEN_SELFTEST_PROCESS_MODE",mode,1);auto result=runnable();run_ngspice_crosschecks(result,opts);
            if(std::string(mode)=="no_measurement"){require(!result.checks[0].spice_value,"no-output run fabricated a value");require(result.notes.size()==1,"no-runnable note missing");}
            else {require(result.checks[0].spice_value.has_value(),"executable output was ignored");require(result.ok()==(std::string(mode)!="disagreement"),"1% agreement gate altered");}
        }
        ::setenv("SCHGEN_SELFTEST_PROCESS_MODE","argv",1);const auto command=run_process({executable.string(),"-b","literal ; $HOME $(false) `false`"});require(command.stdout_text=="literal ; $HOME $(false) `false`","process arguments passed through shell");
        ::setenv("SCHGEN_SELFTEST_PROCESS_MODE","sleep",1);opts.timeout=std::chrono::milliseconds(20);bool timed_out=false;
        try{auto result=runnable();run_ngspice_crosschecks(result,opts);}catch(const ProcessTimeout&){timed_out=true;}
        require(timed_out,"ngspice timeout was swallowed");::unsetenv("SCHGEN_SELFTEST_PROCESS_MODE");
        ::setenv("SCHGEN_SELFTEST_PROCESS_MODE","invalid_utf8",1);opts.timeout=std::chrono::milliseconds(30000);bool invalid_utf8=false;
        try{auto result=runnable();run_ngspice_crosschecks(result,opts);}catch(const ProcessError&){invalid_utf8=true;}
        require(invalid_utf8,"invalid process text was silently accepted");::unsetenv("SCHGEN_SELFTEST_PROCESS_MODE");
        ::setenv("SCHGEN_SELFTEST_PROCESS_MODE","malformed_measurement",1);bool malformed=false;
        try{auto result=runnable();run_ngspice_crosschecks(result,opts);}catch(const ModelCheckError&){malformed=true;}
        require(malformed,"malformed measurement was partially parsed as success");::unsetenv("SCHGEN_SELFTEST_PROCESS_MODE");
        opts.executable="/nonexistent/schgen-ngspice-test";opts.allow_ngspice=false;auto disabled=runnable();run_ngspice_crosschecks(disabled,opts);require(disabled.notes.empty()&&!disabled.checks[0].spice_value,"disabled ngspice still ran");
        opts.allow_ngspice=true;bool failed=false;try{run_ngspice_crosschecks(disabled,opts);}catch(const ProcessError&){failed=true;}require(failed,"spawn failure swallowed");
        failed=false;try{run_process({std::string("invalid\0command",15)});}catch(const ProcessError&){failed=true;}require(failed,"NUL argument accepted");
        std::cout<<passed<<" frozen spice cases + "<<boundaries.array_value.size()<<" tolerance vectors + "<<live<<" live ngspice cases; "<<checks<<" exact checks passed\n";
        if(!ngspice)std::cout<<"ngspice not installed: live cases skipped; process/failure contracts still executed\n";
    }catch(const std::exception& e){std::cerr<<"spice contracts failed: "<<e.what()<<'\n';return 1;}
}
