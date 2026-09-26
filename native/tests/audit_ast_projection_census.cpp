// This is deliberately a separate executable/TU. It uses the REAL visitor,
// unchanged, for both full and projected trees; it is not a second scanner.
// Private proof builds can point at a frozen pre-optimization source snapshot.
#ifndef SCHGEN_AUDIT_VISITOR_SOURCE
#define SCHGEN_AUDIT_VISITOR_SOURCE "../src/native_cpp_audits.cpp"
#endif
#include SCHGEN_AUDIT_VISITOR_SOURCE
#include "schgen/audit_ast_projection.hpp"
#include "schgen/board_policy.hpp"
#include <chrono>
#include <fstream>
#include <iostream>
#include <sys/resource.h>

namespace schgen {
CppSourceCensus projection_test_visit(const JsonNode& ast,const std::string& absolute,
    const std::string& relative,const std::string& source){
    if(text(ast,"kind")!="TranslationUnitDecl")throw std::runtime_error("not a Clang translation unit");
    CppSourceCensus out;
    Visitor visitor{relative,absolute,source,out,{},{},{},{}};
    visitor.index(ast);visitor.visit(ast);visitor.finish();out.n_files=1;return out;
}
}
namespace {
using namespace schgen;
std::string read_bulk(const std::string& path){
    std::ifstream in(path,std::ios::binary|std::ios::ate);if(!in)throw std::runtime_error("open "+path);
    const auto length=in.tellg();if(length<0)throw std::runtime_error("size "+path);
    std::string out(static_cast<std::size_t>(length),'\0');in.seekg(0);
    if(!out.empty()&&!in.read(out.data(),static_cast<std::streamsize>(out.size())))throw std::runtime_error("read "+path);
    return out;
}
void write_census(const CppSourceCensus& c,const std::string& path){
    std::ofstream out(path,std::ios::binary);if(!out)throw std::runtime_error("open census "+path);
    // Complete tuples, preserving vector order and duplicate populations. No
    // hashes, deduplication, blanket exclusions or scanner-derived covers.
    out<<"files "<<c.n_files<<'\n';
    for(const auto& k:c.constants)out<<"constant "<<std::quoted(k.symbol)<<' '<<std::quoted(k.site)<<' '<<k.buried<<'\n';
    for(const auto& f:c.functions)out<<"function "<<std::quoted(f)<<'\n';
    for(const auto& q:c.quantization)out<<"quantization "<<std::quoted(q.site)<<' '<<std::quoted(q.function)<<' '<<std::quoted(q.detector)<<'\n';
    out.close();if(!out)throw std::runtime_error("write census "+path);
}
bool equal_census(const CppSourceCensus& a,const CppSourceCensus& b){
    if(a.n_files!=b.n_files||a.functions!=b.functions||a.constants.size()!=b.constants.size()||a.quantization.size()!=b.quantization.size())return false;
    for(std::size_t i=0;i<a.constants.size();++i){const auto& x=a.constants[i];const auto& y=b.constants[i];if(x.symbol!=y.symbol||x.site!=y.site||x.buried!=y.buried)return false;}
    for(std::size_t i=0;i<a.quantization.size();++i){const auto& x=a.quantization[i];const auto& y=b.quantization[i];if(x.site!=y.site||x.function!=y.function||x.detector!=y.detector)return false;}
    return true;
}
void reverse_keys(const JsonNode& n,std::ostream& out){
    switch(n.kind){
    case JsonKind::Null:out<<"null";break;
    case JsonKind::Bool:out<<(n.bool_value?"true":"false");break;
    case JsonKind::Number:out<<std::setprecision(17)<<n.number_value;break;
    case JsonKind::String:{out<<'"';for(const auto raw:n.string_value){const auto c=static_cast<unsigned char>(raw);
        if(c=='"'||c=='\\')out<<'\\'<<raw;else if(c<32)out<<"\\u00"<<"0123456789abcdef"[c>>4]<<"0123456789abcdef"[c&15];else out<<raw;}out<<'"';break;}
    case JsonKind::Array:{out<<'[';bool first=true;for(const auto& v:n.array_value){if(!first)out<<',';first=false;reverse_keys(v,out);}out<<']';break;}
    case JsonKind::Object:{out<<'{';bool first=true;for(auto it=n.object_value.rbegin();it!=n.object_value.rend();++it){if(!first)out<<',';first=false;out<<std::quoted(it->first)<<':';reverse_keys(it->second,out);}out<<'}';break;}
    }
}
std::size_t inner_nodes(const JsonNode& n){std::size_t out=1;for(const auto& c:children(n))out+=inner_nodes(c);return out;}
double seconds(std::chrono::steady_clock::time_point start){return std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();}
std::uint64_t peak_rss(){
    rusage usage{};if(getrusage(RUSAGE_SELF,&usage)!=0)throw std::runtime_error("getrusage failed");
    return static_cast<std::uint64_t>(usage.ru_maxrss)
#ifndef __APPLE__
        *1024
#endif
        ;
}
void compile_census(const std::string& mode,const std::filesystem::path& root,const std::string& relative,const std::string& output){
    const auto start=std::chrono::steady_clock::now();
    const auto absolute=std::filesystem::absolute(root/relative).lexically_normal().string();
    const std::vector<std::string> prefix={"clang++","-I"+(root/"native/include").string(),"-I"+(root/"native/src").string(),"-std=c++17","-ffp-contract=off","-x","c++"};
    auto command=prefix;command.insert(command.end(),{"-fsyntax-only","-Xclang","-ast-dump=json",absolute});
    JsonNode ast;AuditAstProjectionStats stats;
    if(mode=="stream"){
        const auto status=run_process_consume_stdout(command,[&](std::istream& in){ast=parse_audit_ast_projection(in,absolute,&stats);});
        if(status.exit_code)throw std::runtime_error("compiler failed: "+status.stderr_text);
    }else{
        const auto compiled=run_process(command);if(compiled.exit_code)throw std::runtime_error("compiler failed: "+compiled.stderr_text);
        ast=parse_audit_ast_projection(compiled.stdout_text,absolute,&stats);
    }
    const auto captured=seconds(start);const auto nodes=inner_nodes(ast);
    auto census=projection_test_visit(ast,absolute,relative,read_bulk(absolute));
    command=prefix;command.insert(command.end(),{"-E","-dD",absolute});
    const auto expanded=run_process(command);if(expanded.exit_code)throw std::runtime_error("preprocessor failed: "+expanded.stderr_text);
    schgen::macros(expanded.stdout_text,absolute,relative,census);write_census(census,output);
    std::cout<<mode<<" capture_bytes="<<stats.input_bytes<<" inner_nodes="<<nodes<<" compiler_capture_parse_seconds="<<captured
        <<" total_seconds="<<seconds(start)<<" constants="<<census.constants.size()<<" functions="<<census.functions.size()
        <<" sites="<<census.quantization.size()<<" peak_rss_bytes="<<peak_rss()<<'\n';
}
void selftest(const std::filesystem::path& root){
    std::size_t checks=0;const auto require=[&](bool ok,const std::string& why){++checks;if(!ok)throw std::runtime_error(why);};
    for(const auto* malformed:{
            R"({"kind":"TranslationUnitDecl","id":"root","inner":[{"kind":"VarDecl","parentDeclContextId":"missing"}]})",
            R"({"kind":"TranslationUnitDecl","id":"root","inner":[{"kind":"VarDecl","name":"gap","type":{"qualType":"double"},"init":"c","loc":{"offset":99999}}]})",
            R"({"kind":"TranslationUnitDecl","id":"root","inner":[{"kind":"NamespaceDecl","name":"n","id":"n","loc":{"offset":0},"inner":[{"kind":"VarDecl","name":"gap","type":{"qualType":"double"},"init":"c"}]}]})",
            R"({"kind":"NotATranslationUnit","inner":[]})"}){
        const auto failure=[&](bool projected){try{
            (void)projection_test_visit(projected?parse_audit_ast_projection(malformed):parse_json_text(malformed),"/fixture.cpp","fixture.cpp","double gap=1;\n");
            return std::string{};
        }catch(const std::exception& e){return std::string(e.what());}};
        const auto raw=failure(false);require(!raw.empty()&&raw==failure(true),"semantic malformed/context/location failures preserved exactly");
    }
    for(const std::string relative:{"native/tests/data/audit_ast_projection/policy.cpp","native/tests/data/audit_ast_projection/policy.hpp"}){
        const auto absolute=std::filesystem::absolute(root/relative).lexically_normal().string(),source=read_bulk(absolute);
        const auto compiled=run_process({"clang++","-std=c++17","-ffp-contract=off","-x","c++","-fsyntax-only","-Xclang","-ast-dump=json",absolute});
        require(compiled.exit_code==0,"compile adversarial fixture: "+compiled.stderr_text);
        const auto full=parse_json_text(compiled.stdout_text),projected=parse_audit_ast_projection(compiled.stdout_text);
        const auto baseline=projection_test_visit(full,absolute,relative,source);
        require(equal_census(baseline,projection_test_visit(projected,absolute,relative,source)),"exact adversarial census tuples");
        std::istringstream stream(compiled.stdout_text);const auto streamed=parse_audit_ast_projection(stream);
        require(equal_census(baseline,projection_test_visit(streamed,absolute,relative,source)),"bounded stream exact census tuples");
        require(inner_nodes(full)==inner_nodes(streamed),"bounded stream retains every node");
        JsonNode consumed;const auto status=run_process_consume_stdout({"clang++","-std=c++17","-ffp-contract=off","-x","c++","-fsyntax-only","-Xclang","-ast-dump=json",absolute},
            [&](std::istream& in){consumed=parse_audit_ast_projection(in);});
        require(status.exit_code==0&&equal_census(baseline,projection_test_visit(consumed,absolute,relative,source)),"real scoped capture consumer exact census");
        require(inner_nodes(full)==inner_nodes(projected),"every adversarial inner node retained");
        std::ostringstream reversed;reverse_keys(full,reversed);
        require(equal_census(baseline,projection_test_visit(parse_audit_ast_projection(reversed.str()),absolute,relative,source)),"arbitrary object key order retains context/source/macro semantics");
        require(equal_census(baseline,projection_test_visit(parse_json_text(reversed.str()),absolute,relative,source)),"key-order oracle is independently equivalent");
        if(relative.find(".cpp")!=relative.npos){
            for(const auto* suffix:{"global_clearance","anonymous_gap","other::State::hidden","other::State::frozen","other::Physical::Gap","other::Physical::Successor","other::Δ","other::macros::buried_macro","included_policy::Engine::snap [double (double) const]::eps","after_include"})
                require(std::any_of(baseline.constants.begin(),baseline.constants.end(),[&](const auto& c){return c.symbol==relative+"::"+suffix;}),std::string("independent expected finding: ")+suffix);
            require(std::none_of(baseline.constants.begin(),baseline.constants.end(),[](const auto& c){return c.symbol.find("header_gap")!=c.symbol.npos;}),"included header owned by its own manifest entry");
            require(std::any_of(baseline.functions.begin(),baseline.functions.end(),[](const auto& f){return f.find("::<lambda@")!=f.npos;}),"lambda owns a separate body");
            NativeLedger empty;NativeQuantizations none;const auto audit=check_native_audits(baseline,empty,none);
            require(!audit.ok&&!audit.buried.empty()&&!audit.undeclared.empty()&&!audit.unregistered_quantization.empty(),"unregistered policy still fails all coverage classes");
            for(const auto* detector:{"raw-round","float-to-integer","credit-0.05"})require(std::any_of(baseline.quantization.begin(),baseline.quantization.end(),[&](const auto& s){return s.detector==detector;}),std::string("independent detector: ")+detector);
        }else require(std::any_of(baseline.constants.begin(),baseline.constants.end(),[](const auto& c){return c.symbol.find("header_gap")!=c.symbol.npos;}),"standalone header policies remain visible");
    }
    std::cout<<checks<<" live Clang AST projection census contracts PASS\n";
}
void census_file(const std::string& mode,const std::string& ast_path,const std::string& absolute,const std::string& relative,const std::string& output,const std::string& preprocessed){
    const auto input=mode=="stream"?std::string{}:read_bulk(ast_path),source=read_bulk(absolute);
    const auto start=std::chrono::steady_clock::now();AuditAstProjectionStats stats;
    JsonNode ast;
    if(mode=="stream"){std::ifstream in(ast_path,std::ios::binary);if(!in)throw std::runtime_error("open "+ast_path);ast=parse_audit_ast_projection(in,ast_path,&stats);}
    else ast=mode=="raw"?parse_json_text(input,ast_path):parse_audit_ast_projection(input,ast_path,&stats);
    const auto parsed=seconds(start);const auto count=inner_nodes(ast);
    auto census=projection_test_visit(ast,absolute,relative,source);
    if(!preprocessed.empty())schgen::macros(read_bulk(preprocessed),absolute,relative,census);
    write_census(census,output);
    std::cout<<mode<<" bytes="<<(mode=="stream"?stats.input_bytes:input.size())<<" inner_nodes="<<count<<" retained_values="<<stats.retained_values
        <<" json_values="<<stats.json_values<<" parse_seconds="<<parsed<<" total_seconds="<<seconds(start)
        <<" constants="<<census.constants.size()<<" functions="<<census.functions.size()<<" sites="<<census.quantization.size()<<" peak_rss_bytes="<<peak_rss()<<'\n';
}
}
int main(int argc,char** argv){try{
    if(argc==2&&std::string(argv[1])=="--manifest"){
        for(const auto& s:schgen::native_board_policy_audit_sources())std::cout<<s.path<<'\n';return 0;}
    if(argc==3&&std::string(argv[1])=="--selftest"){selftest(argv[2]);return 0;}
    if(argc==6&&std::string(argv[1])=="--compile-census"&&(std::string(argv[2])=="projected"||std::string(argv[2])=="stream")){
        compile_census(argv[2],std::filesystem::absolute(argv[3]),argv[4],argv[5]);return 0;}
    if((argc!=7&&argc!=8)||std::string(argv[1])!="--census"||(std::string(argv[2])!="raw"&&std::string(argv[2])!="projected"&&std::string(argv[2])!="stream"))
        throw std::invalid_argument("usage: --manifest | --selftest ROOT | --census raw|projected|stream AST_JSON ABSOLUTE_SOURCE RELATIVE_SOURCE OUTPUT_CENSUS [PREPROCESSED]");
    census_file(argv[2],argv[3],argv[4],argv[5],argv[6],argc==8?argv[7]:"");return 0;
}catch(const std::exception& e){std::cerr<<"AST census proof FAILED: "<<e.what()<<'\n';return 1;}}
