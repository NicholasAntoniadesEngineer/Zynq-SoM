#include "schgen/spice.hpp"
#include "schgen/process.hpp"
#include "verification_internal.hpp"
#include "verification_unicode.hpp"
#include <unistd.h>

namespace schgen {
using namespace verification;
namespace {
struct SpiceScratch {
    std::filesystem::path path;
    SpiceScratch(){auto pattern=(std::filesystem::temp_directory_path()/"schgen_spice_XXXXXX").string();if(!::mkdtemp(pattern.data()))throw ProcessError("cannot create ngspice scratch");path=pattern;}
    ~SpiceScratch(){std::error_code error;std::filesystem::remove_all(path,error);}
};
std::string float_text(double value) {
    char buffer[512];const auto end=std::to_chars(buffer,buffer+sizeof buffer,value);
    if(end.ec!=std::errc{})throw ModelCheckError("ngspice value out of range");
    std::string out(buffer,end.ptr);if(out.find_first_of(".e")==std::string::npos)out+=".0";return out;
}
double parse_float(const std::string& value) {
    char* end=nullptr;const double number=std::strtod(value.c_str(),&end);
    if(end==value.c_str()||end!=value.c_str()+value.size())throw ModelCheckError("could not convert string to float: "+repr(value));
    return number;
}
}
std::optional<std::filesystem::path> ngspice_available(){return find_executable("ngspice");}
void run_ngspice_crosschecks(SpiceResult& result,const SpiceRunOptions& opts) {
    if(!opts.allow_ngspice)return;
    const auto exe=opts.executable?opts.executable:ngspice_available();if(!exe)return;
    static const std::regex resistors(R"(-\[\w+=([\d.eE+-]+)R\]-.*-\[\w+=([\d.eE+-]+)R\]-)");
    static const std::regex voltage(R"(@ ([\d.]+) V)");
    static const std::regex output(R"(mid\s*=?\s*([\d.eE+-]+))");
    std::size_t ran=0;
    for(auto& check:result.checks) {
        if(check.kind!="divider")continue;std::smatch resist,volts;
        std::string detail;
        for(const auto& [cp,bytes]:utf8(check.detail))detail+=cp>=128&&unicode_word(cp)?"x":bytes;
        if(!std::regex_search(detail,resist,resistors)||!std::regex_search(check.detail,volts,voltage))continue;
        const auto rt=parse_float(resist[1]),rb=parse_float(resist[2]),vs=parse_float(volts[1]);
        auto name=check.name;std::replace(name.begin(),name.end(),'\n',' ');std::replace(name.begin(),name.end(),'\r',' ');
        // Name is a comment, never ngspice control input. Numeric deck fields
        // are parsed doubles. No arbitrary circuit/source file is executed.
        const auto deck="* schgen divider check: "+name+"\nV1 in 0 "+float_text(vs)+"\nR1 in mid "+float_text(rt)+"\nR2 mid 0 "+float_text(rb)+"\n.op\n.print op v(mid)\n.end\n";
        SpiceScratch scratch;const auto path=scratch.path/"divider.cir";write_atomic_file(path.string(),{deck.begin(),deck.end()});
        const auto process=run_process({exe->string(),"-b",path.string()},opts.timeout);
        // Python consumes matching stdout even on nonzero exit, and leaves the
        // analytic verdict unchanged if ngspice prints no matching value.
        const auto measurements=regex_numbers(process.stdout_text);
        std::smatch match;if(std::regex_search(measurements,match,output)) {
            check.spice_value=py_round(parse_float(match[1]),4);check.engine="analytic+ngspice";++ran;
        }
    }
    if(ran)result.engine="analytic (gate) + ngspice .op cross-check on "+std::to_string(ran)+" divider(s), 1% agreement enforced";
    else result.notes.push_back("NOTE: ngspice present but no check was cross-runnable");
}
SpiceResult run_spice_checks(const std::vector<ProjectCircuit>& sheets,const std::filesystem::path& reports,const SpiceRunOptions& options,const PowerPolicy& policy) {
    auto result=extract_spice_checks(sheets,policy);run_ngspice_crosschecks(result,options);
    std::filesystem::create_directories(reports);
    write_report(reports/"spice.txt",spice_report(result,bool(options.executable?options.executable:ngspice_available())));return result;
}
}  // namespace schgen
