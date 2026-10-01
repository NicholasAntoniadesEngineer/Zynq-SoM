#include "schgen/spice.hpp"
#include "schgen/process.hpp"
#include "verification_internal.hpp"
#include "verification_unicode.hpp"
#include <cerrno>
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
    errno=0;char* end=nullptr;const double number=std::strtod(value.c_str(),&end);
    if(end==value.c_str()||end!=value.c_str()+value.size()||errno==ERANGE||!std::isfinite(number))
        throw ModelCheckError("could not convert finite, representable float: "+repr(value));
    return number;
}
}
std::optional<std::filesystem::path> ngspice_available(){return find_executable("ngspice");}
void run_ngspice_crosschecks(SpiceResult& result,const SpiceRunOptions& opts) {
    if(!opts.allow_ngspice)return;
    const auto exe=opts.executable?opts.executable:ngspice_available();if(!exe)return;
    static const std::regex resistors(R"(-\[\w+=([\d.eE+-]+)R\]-.*-\[\w+=([\d.eE+-]+)R\]-)");
    static const std::regex voltage(R"(@ ([\d.]+) V)");
    // Exactly one complete node-voltage row, not a substring of another node
    // or arbitrary text. ngspice .op emits "mid <value>"; test/probe engines
    // may emit "mid = <value>". Full-token numeric parsing follows below.
    static const std::regex output(R"(^\s*mid(?:\s*=\s*|\s+)(\S+)\s*$)");
    static const std::regex target_row(R"(^\s*mid(?:\s|=|$))");
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
        if(process.exit_code!=0)
            throw ProcessError("ngspice cross-check failed with exit "+std::to_string(process.exit_code)+
                (process.stderr_text.empty()?"":": "+process.stderr_text.substr(0,1024)));
        // Normalize Unicode digits/spacing per line: whole-output normalization
        // would turn newlines into spaces and destroy the row boundary.
        std::istringstream rows(process.stdout_text);std::string row;std::optional<double> measured;
        while(std::getline(rows,row)) {
            row=regex_numbers(row);
            std::smatch match;
            if(!std::regex_match(row,match,output)) {
                if(std::regex_search(row,target_row))
                    throw ModelCheckError("ngspice cross-check returned a malformed mid row");
                continue;
            }
            if(measured)throw ModelCheckError("ngspice cross-check returned ambiguous mid measurements");
            measured=parse_float(match[1]);
        }
        if(!measured)throw ModelCheckError("ngspice cross-check did not return a mid voltage");
        // Keep the measured precision. Rounding before the agreement gate can
        // hide a nonzero result when the analytic prediction is zero.
        check.spice_value=*measured;check.engine="analytic+ngspice";++ran;
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
