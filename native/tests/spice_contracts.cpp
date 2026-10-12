#include "schgen/spice.hpp"
#include "schgen/process.hpp"
#include "spice_historical_precision.hpp"
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iomanip>
#include <limits>
#include <sstream>
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
const std::string no_coverage="No supported analytic checks were extracted; electrical behavior is unverified.";
std::string coverage_report(std::string historical){
    for(const auto& replacement:std::vector<std::pair<std::string,std::string>>{
            {"errors: none","ERRORS (1):\n  ERROR: "+no_coverage},
            {"SPICE GATE: PASS (0 checks)","SPICE GATE: UNVERIFIED (0 checks)"}}){
        const auto at=historical.find(replacement.first);
        require(at!=std::string::npos&&historical.find(replacement.first,at+1)==std::string::npos,"unexpected historical empty-coverage report");
        historical.replace(at,replacement.first.size(),replacement.second);
    }
    return historical;
}
void empty_coverage(){
    auto empty=extract_spice_checks({});
    require(empty.checks.empty()&&!empty.ok()&&empty.errors()==std::vector<std::string>{no_coverage},"empty extraction was accepted");
    empty.notes.push_back("informational note is not a check");
    require(!empty.ok(),"notes supplied nonexistent check coverage");
    for(bool installed:{false,true}){
        const auto report=spice_report(empty,installed);
        require(report.find("SPICE GATE: UNVERIFIED (0 checks)")!=std::string::npos&&report.find("SPICE GATE: PASS")==std::string::npos,
                "empty report claimed PASS");
    }
    const auto encoded=spice_result_json(empty);
    require(!field(encoded,"ok").bool_value&&field(encoded,"n_checks").number_value==0&&field(encoded,"errors").array_value.size()==1,
            "JSON concealed missing coverage");
    require(runnable().ok(),"valid positive coverage was rejected");
}
std::vector<ProjectCircuit> fixture_sheets(const std::filesystem::path& path){
    const auto row=parse_json_file(path.string());std::vector<ProjectCircuit> sheets;
    for(const auto& sc:field(row,"sheets").array_value)
        sheets.push_back({field(sc,"name").string_value,{},decode_intermediate_circuit_ir(field(sc,"circuit"))});
    return sheets;
}
void rejects_divider(const std::vector<ProjectCircuit>& sheets,const std::string& expected){
    bool rejected=false;
    try{(void)extract_spice_checks(sheets);}catch(const ModelCheckError& error){
        require(error.what()==expected,"required-divider diagnostic mismatch: "+std::string(error.what()));rejected=true;
    }
    require(rejected,"required-divider extraction silently accepted unsupported topology/source");
}
void required_divider_coverage(const std::filesystem::path& dir){
    auto unrelated=fixture_sheets(dir/"015_INFORMATIONAL_10k_10k.json");
    require(extract_spice_checks(unrelated).ok(),"unrelated coverage fixture must pass alone");
    for(auto& net:unrelated[0].circuit.nets)if(net.name=="INFORMATIONAL")net.name="HDMI_RX_5V_DET_suffix";
    require(extract_spice_checks(unrelated).ok(),"prefix-lookalike generic divider must remain independently valid");
    auto broken=fixture_sheets(dir/"022_named_not_extracted.json");
    auto combined=broken;combined.insert(combined.end(),unrelated.begin(),unrelated.end());
    rejects_divider(combined,"required divider HDMI_RX_5V_DET: topology could not be extracted");
    std::reverse(combined.begin(),combined.end());
    rejects_divider(combined,"required divider HDMI_RX_5V_DET: topology could not be extracted");
    auto wrong=fixture_sheets(dir/"021_wrong_named_source.json");
    for(auto& net:wrong[0].circuit.nets)if(net.name=="+VIN")net.name="+3V3";
    // Half of 3.3 V lies below the old upper-only check, but the rail is wrong.
    rejects_divider(wrong,"required divider HDMI_RX_5V_DET: source +3V3, expected HDMI_RX_5V");
}
void divider_threshold_precision(const std::filesystem::path& dir){
    const auto decimal=[](double value){std::ostringstream out;out<<std::setprecision(17)<<value;return out.str();};
    for(bool upper:{false,true})for(double delta:{-4e-5,-1e-7,0.,1e-7,4e-5}){
        const double limit=upper?3.465:2.,source=upper?5.25:4.75,target=limit+delta;
        auto sheets=fixture_sheets(dir/"003_HDMI_RX_5V_DET_10k_10k.json");
        for(auto& part:sheets[0].circuit.parts)part.value=decimal((part.ref=="R1"?source-target:target)*10000);
        const auto result=extract_spice_checks(sheets);
        const auto check=std::find_if(result.checks.begin(),result.checks.end(),[&](const auto& c){
            return upper?(c.hi&&*c.hi==limit):(c.lo&&*c.lo==limit);
        });
        require(check!=result.checks.end(),"threshold fixture lost required check");
        require(check->ok()==(upper?delta<=0:delta>=0),"pre-acceptance voltage rounding concealed a threshold violation");
        require(std::abs(check->value-target)<=8*std::numeric_limits<double>::epsilon()*target,"analytic voltage lost calculation precision");
        const auto encoded=spice_result_json(result);
        const auto index=static_cast<std::size_t>(check-result.checks.begin());
        require(field(field(encoded,"checks").array_value[index],"value").number_value==check->value,"JSON dropped acceptance precision");
        if(!check->ok()&&std::abs(delta)<1e-6)
            require(spice_report(result,false).find("= "+decimal(check->value)+" V")!=std::string::npos,
                    "report rounded a failed voltage to the displayed limit");
    }
}
SpiceResult historical_analytic_view(const SpiceResult& raw,const JsonNode& expected){
    auto view=raw;const auto& old=field(expected,"checks").array_value;
    require(old.size()==raw.checks.size(),"historical analytic check census changed");
    for(std::size_t i=0;i<old.size();++i){
        const auto& check=raw.checks[i];
        const auto scale=historical_spice_scale(check);
        const double rounded=field(old[i],"value").number_value;
        require(std::abs(std::round(check.value*scale)/scale-rounded)<1e-12,
                "raw result differs from historical rounded calculation");
        require(check.ok()==field(old[i],"ok").bool_value,"raw calculation changed a frozen fixture verdict");
        // Only this legacy comparison view is rounded. Actual gate values,
        // JSON and simulator comparisons retain full calculation precision.
        view.checks[i].value=rounded;
    }
    return view;
}
void remaining_threshold_precision(const std::filesystem::path& dir){
    struct Case {const char* file;const char* ref;const char* prefix;int formula;double limit,step;bool upper;};
    const std::vector<Case> cases{
        {"027_rc_False_100n.json","R1","RC ",0,.2,.001,false},
        {"027_rc_False_100n.json","R1","RC ",0,20,.001,true},
        {"035_sy7201_1.5R.json","R1","SY7201 ISET",1,125,.1,false},
        {"035_sy7201_1.5R.json","R1","SY7201 ISET",1,150,.1,true},
        {"040_buck_45k3_10k.json","R1","TPS54302DDCR FB",2,3.201,.0001,false},
        {"040_buck_45k3_10k.json","R1","TPS54302DDCR FB",2,3.399,.0001,true},
        {"043_buck_en_unclamped.json","R3","EN clamp ceiling",3,5.5,.001,true},
        {"045_buck_en_zener.json","R3","EN clamp turn-on",4,1.5,.001,false},
        {"045_buck_en_zener.json","R3","EN clamp ceiling",5,5.5,.001,true},
        {"032_boot0_100.json","R1","BOOT0 strap VIH",6,2.31,.001,false}
    };
    std::size_t hidden=0;
    for(const auto& test:cases)for(double delta:{-.4*test.step,-1e-7,0.,1e-7,.4*test.step}){
        const double target=test.limit+delta;
        double resistance=0;
        switch(test.formula){
        case 0: resistance=target*10000;break; // tau/ms, C=100nF
        case 1: resistance=200/target;break; // 0.2V / R in mA
        case 2: resistance=(target/.596-1)*10000;break; // feedback bottom 10k
        case 3: resistance=(21-target)/1.55e-6;break;
        case 4: resistance=(4.75-target)/1.55e-6;break; // below zener knee
        case 5: resistance=(21-target)/((target-(5.355-.02*17))/17+1.55e-6);break;
        case 6: resistance=1500*(3.3/target-1);break;
        default: throw std::runtime_error("unknown threshold fixture");
        }
        auto sheets=fixture_sheets(dir/test.file);std::ostringstream value;value<<std::setprecision(17)<<resistance;
        bool changed=false;for(auto& part:sheets[0].circuit.parts)if(part.ref==test.ref){part.value=value.str();changed=true;}
        require(changed,"threshold fixture resistor missing");
        const auto result=extract_spice_checks(sheets);
        const auto found=std::find_if(result.checks.begin(),result.checks.end(),[&](const auto& c){return c.name.rfind(test.prefix,0)==0;});
        require(found!=result.checks.end(),"threshold extraction missing "+std::string(test.prefix));
        const bool inside=test.upper?delta<=0:delta>=0;
        require(found->ok()==inside,"rounded acceptance at "+std::string(test.prefix));
        require(std::abs(found->value-target)<=32*std::numeric_limits<double>::epsilon()*std::max(1.,target),
                "raw calculation precision lost at "+std::string(test.prefix));
        if(!inside){auto rounded=*found;rounded.value=std::round(rounded.value/test.step)*test.step;
            require(rounded.ok(),"negative control no longer demonstrates rounded false pass");++hidden;}
    }
    require(hidden==20,"all twenty near-boundary rounded false passes must be rejected");
}
void numeric_safety() {
    for (const auto bad : {std::numeric_limits<double>::quiet_NaN(),
                           std::numeric_limits<double>::infinity(),
                           -std::numeric_limits<double>::infinity()}) {
        for (int field = 0; field < 4; ++field) {
            auto check = runnable().checks.front();
            if (field == 0) check.value = bad;
            else if (field == 1) check.lo = bad;
            else if (field == 2) check.hi = bad;
            else check.spice_value = bad;
            require(!check.ok(), "non-finite calculation/limit/measurement accepted");
        }
    }
    SpiceCheck zero;
    zero.value = 0; zero.spice_value = 99;
    require(!zero.ok(), "zero analytic prediction accepted unrelated simulated voltage");
    zero.spice_value = std::numeric_limits<double>::denorm_min();
    require(!zero.ok(), "zero prediction silently acquired an absolute error tolerance");
    zero.spice_value = -0.; require(zero.ok(), "signed-zero agreement rejected");
    zero.spice_value.reset(); zero.value = 1; zero.lo = 1 + 1e-10; zero.hi = 1;
    require(!zero.ok(), "reversed limits hidden by comparison tolerance");
}
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
        if(test=="nan_measurement"){std::cout<<"mid = nan\n";return 0;}
        if(test=="overflow_measurement"){std::cout<<"mid = 1e999\n";return 0;}
        if(test=="duplicate_measurement"){std::cout<<"mid = 1.65\nmid = 1.65\n";return 0;}
        if(test=="substring_measurement"){std::cout<<"not_mid = 1.65\n";return 0;}
        if(test=="trailing_measurement"){std::cout<<"mid = 1.65\nmid = malformed value\n";return 0;}
        if(test=="missing_success"){std::cout<<"no measurement\n";return 0;}
        if(test=="precise_measurement"){std::cout<<"mid = 1.65004\n";return 0;}
        if(test=="small_measurement"){std::cout<<"mid = 0.00001\n";return 0;}
        if(test=="sleep"){std::this_thread::sleep_for(std::chrono::seconds(5));return 0;}
        if(test=="argv"){std::cout<<argv[2];return 0;}
        std::cout<<"no measurement\n";return 3;
    }
    try {
        require(argc==2,"usage: spice_contracts <fixture-directory>");const std::filesystem::path dir(argv[1]);
        numeric_safety();empty_coverage();required_divider_coverage(dir);divider_threshold_precision(dir);remaining_threshold_precision(dir);
        const auto manifest=parse_json_file((dir/"manifest.json").string());std::size_t passed=0,live=0;
        const auto ngspice=ngspice_available();std::size_t corrected_empty=0,corrected_required=0;
        for(const auto& file:field(manifest,"cases").array_value) {
            const auto row=parse_json_file((dir/file.string_value).string());std::vector<ProjectCircuit> sheets;
            for(const auto& sc:field(row,"sheets").array_value)sheets.push_back({field(sc,"name").string_value,{},decode_intermediate_circuit_ir(field(sc,"circuit"))});
            if(file.string_value=="021_wrong_named_source.json"||file.string_value=="022_named_not_extracted.json"){
                rejects_divider(sheets,file.string_value=="021_wrong_named_source.json"
                    ?"required divider HDMI_RX_5V_DET: source +VIN, expected HDMI_RX_5V"
                    :"required divider HDMI_RX_5V_DET: topology could not be extracted");
                ++corrected_required;++passed;continue;
            }
            const auto* error=object_field(row,"error");std::optional<SpiceResult> result;
            try{result=extract_spice_checks(sheets);}
            catch(const ModelCheckError& e){require(error!=nullptr,file.string_value+": unexpected error "+e.what());require(field(*error,"message").string_value==e.what(),file.string_value+": diagnostic differs "+e.what());}
            require(bool(result)==!bool(error),file.string_value+": expected error presence differs");
            if(result){
                auto expected=field(row,"expected");
                auto absent=field(row,"report_absent").string_value,present=field(row,"report_present").string_value;
                if(result->checks.empty()){
                    require(field(expected,"ok").bool_value&&field(expected,"n_checks").number_value==0&&field(expected,"errors").array_value.empty(),
                            "unexpected frozen empty-coverage correction");
                    for(auto& [key,value]:expected.object_value){
                        if(key=="ok")value.bool_value=false;
                        if(key=="errors"){JsonNode message;message.kind=JsonKind::String;message.string_value=no_coverage;value.array_value.push_back(message);}
                    }
                    absent=coverage_report(absent);present=coverage_report(present);++corrected_empty;
                }
                const auto analytic_view=historical_analytic_view(*result,expected);
                same(spice_result_json(analytic_view),expected,file.string_value);
                require(spice_report(analytic_view,false)==absent,file.string_value+": absent report differs");
                require(spice_report(analytic_view,true)==present,file.string_value+": present report differs");
                if(const auto* expected=object_field(row,"ngspice");expected&&ngspice){
                    SpiceRunOptions opts;opts.executable=ngspice;run_ngspice_crosschecks(*result,opts);
                    auto historical_view=historical_analytic_view(*result,*expected);
                    const auto& old_checks=field(*expected,"checks").array_value;
                    require(old_checks.size()==result->checks.size(),"historical simulation check count");
                    for(std::size_t i=0;i<old_checks.size();++i) {
                        require(result->checks[i].ok()==field(old_checks[i],"ok").bool_value,
                                "raw measurement changed historical check verdict");
                        const auto old=number(old_checks[i],"spice_value");
                        if(old) {
                            require(result->checks[i].spice_value &&
                                    std::abs(*result->checks[i].spice_value-*old)<=0.00005000001,
                                    "raw measurement differs beyond frozen four-decimal precision");
                            // Only the historical presentation lost this precision.
                            // Production values and verdicts remain unmodified.
                            historical_view.checks[i].spice_value=old;
                        }
                    }
                    same(spice_result_json(historical_view),*expected,file.string_value+".ngspice");
                    require(spice_report(historical_view,true)==field(row,"ngspice_report").string_value,file.string_value+": historical ngspice report differs");++live;
                }
            }
            ++passed;
        }
        require(corrected_empty==6&&corrected_required==2,"exact historical empty/required-divider corrections required");
        const auto boundaries=parse_json_file((dir/"boundaries.json").string());
        std::size_t corrected_zero_cases = 0;
        for(const auto& row:boundaries.array_value) {
            const auto& c=field(row,"check");SpiceCheck value;
            value.value=field(c,"value").number_value;value.lo=number(c,"lo");value.hi=number(c,"hi");value.spice_value=number(c,"spice_value");
            if(value.value==0 && value.spice_value && *value.spice_value!=0) {
                require(*value.spice_value==99 && !value.lo && !value.hi && field(row,"ok").bool_value,
                        "unexpected frozen zero-check correction");
                require(!value.ok(),"historical zero-vs-99V false pass retained");
                ++corrected_zero_cases;
            } else require(value.ok()==field(row,"ok").bool_value,"comparison tolerance boundary differs");
        }
        require(corrected_zero_cases==1,"exact historical zero-check correction required");
        const auto executable=std::filesystem::absolute(argv[0]);SpiceRunOptions opts;opts.executable=executable;
        for(const auto* mode:{"value","disagreement","unicode_measurement"}) {
            ::setenv("SCHGEN_SELFTEST_PROCESS_MODE",mode,1);auto result=runnable();run_ngspice_crosschecks(result,opts);
            require(result.checks[0].spice_value.has_value(),"executable output was ignored");require(result.ok()==(std::string(mode)!="disagreement"),"1% agreement gate altered");
        }
        for(const auto* mode:{"nonzero_value","no_measurement","missing_success","nan_measurement",
                              "overflow_measurement","duplicate_measurement","substring_measurement","trailing_measurement"}) {
            ::setenv("SCHGEN_SELFTEST_PROCESS_MODE",mode,1);
            bool rejected=false;
            try{auto result=runnable();run_ngspice_crosschecks(result,opts);}
            catch(const ModelCheckError&){rejected=true;}
            catch(const ProcessError&){rejected=true;}
            require(rejected,std::string("untrustworthy simulator result accepted: ")+mode);
        }
        ::setenv("SCHGEN_SELFTEST_PROCESS_MODE","precise_measurement",1);
        auto precise=runnable();run_ngspice_crosschecks(precise,opts);
        require(precise.checks.front().spice_value==1.65004,"measurement precision discarded before validation");
        ::setenv("SCHGEN_SELFTEST_PROCESS_MODE","small_measurement",1);
        auto small=runnable();small.checks.front().value=0;run_ngspice_crosschecks(small,opts);
        require(small.checks.front().spice_value==0.00001&&!small.ok(),"rounded simulation falsely agrees with zero");
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
