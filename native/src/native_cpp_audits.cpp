#include "schgen/native_audit_state.hpp"
#include "schgen/process.hpp"
#include "verification_internal.hpp"
#include "verification_audits_unicode.hpp"
#include <cctype>
#include <cstring>

namespace schgen {
namespace {
const JsonNode empty;
const JsonNode& get(const JsonNode& n,const std::string& key){if(n.kind!=JsonKind::Object)return empty;const auto* p=object_field(n,key);return p?*p:empty;}
std::string text(const JsonNode& n,const std::string& key){return get(n,key).string_value;}
const std::vector<JsonNode>& children(const JsonNode& n){return get(n,"inner").array_value;}
const JsonNode& location(const JsonNode& n){const auto& expansion=get(n,"expansionLoc");return expansion.kind==JsonKind::Object?expansion:n;}
bool numeric_type(const JsonNode& n){
    const auto& t=get(n,"type");auto type=text(t,"desugaredQualType");if(type.empty())type=text(t,"qualType");
    for(const auto* qualifier:{"const ","volatile "})for(auto i=type.find(qualifier);i!=type.npos;i=type.find(qualifier))type.erase(i,std::strlen(qualifier));
    static const std::set<std::string> types={"char","signed char","unsigned char","short","unsigned short","int","unsigned int","long","unsigned long","long long","unsigned long long","float","double","long double","__int128","unsigned __int128"};
    return types.count(type);
}
bool upper_policy_name(const std::string& name){
    bool upper=false;for(const auto& [cp,bytes]:verification::utf8(name)){(void)bytes;const auto f=audit_detail::unicode_flags(cp);if(f&2)return false;upper|=bool(f&1);}return upper;
}
bool geometry(const JsonNode& n){
    auto name=text(n,"name");if(name.empty())name=text(get(n,"referencedDecl"),"name");
    for(char& c:name)c=char(std::tolower(static_cast<unsigned char>(c)));
    for(const auto* token:{"need","reach","clr","clear","bound","lim","gap","margin"})if(name.find(token)!=name.npos)return true;
    for(const auto& c:children(n))if(geometry(c))return true;return false;
}
bool credit(const JsonNode& n){
    if(text(n,"kind")=="FloatingLiteral"){char* end=nullptr;const auto value=text(n,"value");const double d=std::strtod(value.c_str(),&end);return end==value.c_str()+value.size()&&d==0.05;}
    const auto kind=text(n,"kind");return (kind=="ParenExpr"||kind=="ImplicitCastExpr"||kind=="ConstantExpr")&&children(n).size()==1&&credit(children(n).front());
}
bool static_number(const JsonNode& n,const std::set<std::string>& known){
    const auto kind=text(n,"kind");
    if(kind=="IntegerLiteral"||kind=="FloatingLiteral"||kind=="CharacterLiteral")return true;
    if(kind=="DeclRefExpr")return known.count(text(get(n,"referencedDecl"),"id"));
    static const std::set<std::string> operators={"BinaryOperator","UnaryOperator","ParenExpr","ImplicitCastExpr","CXXStaticCastExpr","CStyleCastExpr","ConstantExpr","InitListExpr"};
    if(!operators.count(kind)||children(n).empty())return false;
    return std::all_of(children(n).begin(),children(n).end(),[&](const auto& c){return static_number(c,known);});
}
std::string callee(const JsonNode& n){
    const auto& ref=get(n,"referencedDecl");if(text(ref,"kind")=="FunctionDecl")return text(ref,"name");
    if(text(n,"kind")=="MemberExpr")return text(n,"name");
    for(const auto& c:children(n)){auto name=callee(c);if(!name.empty())return name;}return {};
}
bool raw_round(std::string target){
    if(target.compare(0,10,"__builtin_")==0)target.erase(0,10);
    static const std::set<std::string> raw={"round","roundf","roundl","lround","llround","floor","floorf","floorl","ceil","ceilf","ceill","trunc","nearbyint","rint","py_round"};
    return raw.count(target);
}
bool numeric_macro(const std::string& expression,const std::set<std::string>& known){
    bool value=false;
    for(std::size_t i=0;i<expression.size();){const auto c=static_cast<unsigned char>(expression[i]);
        if(std::isspace(c)||std::strchr("()+-*/%&|^~<>!?:",c)){++i;continue;}
        if(std::isdigit(c)||(c=='.'&&i+1<expression.size()&&std::isdigit(static_cast<unsigned char>(expression[i+1])))){
            value=true;++i;while(i<expression.size()&&(std::isalnum(static_cast<unsigned char>(expression[i]))||expression[i]=='.'||expression[i]=='\''))++i;continue;
        }
        if(std::isalpha(c)||c=='_'){const auto start=i++;while(i<expression.size()&&(std::isalnum(static_cast<unsigned char>(expression[i]))||expression[i]=='_'))++i;
            if(!known.count(expression.substr(start,i-start)))return false;value=true;continue;}
        return false;
    }
    return value;
}
void macros(const std::string& preprocessed,const std::filesystem::path& absolute,const std::string& path,CppSourceCensus& out){
    std::istringstream input(preprocessed);std::string row,current;std::size_t line=0;std::set<std::string> numbers;
    while(std::getline(input,row)){
        if(row.compare(0,2,"# ")==0){std::istringstream marker(row.substr(2));marker>>line>>std::quoted(current);continue;}
        if(row.compare(0,8,"#define ")==0){const auto start=std::size_t(8);auto end=start;
            while(end<row.size()&&(std::isalnum(static_cast<unsigned char>(row[end]))||row[end]=='_'))++end;
            const auto name=row.substr(start,end-start);
            if(end<row.size()&&row[end]!='('&&numeric_macro(row.substr(end),numbers)){
                numbers.insert(name);if(std::filesystem::path(current).lexically_normal()==absolute)
                    out.constants.push_back({path+"::macro::"+name,path+":"+std::to_string(line),false});
            }
        }else if(row.compare(0,7,"#undef ")==0)numbers.erase(verification::strip(row.substr(7)));
        ++line;
    }
}
struct Visitor {
    std::string path,absolute,source;
    CppSourceCensus& out;
    std::map<std::string,std::string> definitions;
    std::set<std::string> constant_ids;
    std::size_t line(const JsonNode& n)const{
        const auto& loc=location(get(n,"loc"));const auto& begin=location(get(get(n,"range"),"begin"));
        const auto& chosen=get(loc,"offset").kind==JsonKind::Number?loc:begin;
        const auto& off=get(chosen,"offset");if(off.kind!=JsonKind::Number)throw AuditSyntaxError(path+": compiler omitted source location");
        const auto offset=std::size_t(off.number_value);if(offset>source.size())throw AuditSyntaxError(path+": invalid compiler source offset");
        return std::size_t(std::count(source.begin(),source.begin()+static_cast<std::ptrdiff_t>(offset),'\n'))+1;
    }
    void visit(const JsonNode& n,std::string scope={},std::string function={},bool in_main=false,bool in_class=false){
        const auto kind=text(n,"kind"),name=text(n,"name");
        if(get(n,"isImplicit").bool_value&&kind!="ImplicitCastExpr")return;
        const auto& loc=location(get(n,"loc"));
        if(get(loc,"offset").kind==JsonKind::Number){const auto file=text(loc,"file");in_main=get(loc,"includedFrom").kind==JsonKind::Null&&(file.empty()||std::filesystem::path(file).lexically_normal()==absolute);}
        if(kind=="NamespaceDecl"&&!name.empty())scope+=name+"::";
        if(kind=="EnumDecl"&&!text(n,"scopedEnumTag").empty())scope+=name+"::";
        if(kind=="CXXRecordDecl"||kind=="RecordDecl"){scope+=name+"::";in_class=true;}
        const bool fn=kind=="FunctionDecl"||kind=="CXXMethodDecl"||kind=="CXXConstructorDecl"||kind=="CXXConversionDecl";
        if(fn){
            function=path+"::"+scope+name;
            bool body=false;for(const auto& c:children(n))body|=text(c,"kind")=="CompoundStmt"||text(c,"kind")=="CXXTryStmt";
            if(in_main&&body){
                const auto signature=text(n,"mangledName");const auto [p,inserted]=definitions.emplace(function,signature);
                if(!inserted&&p->second!=signature)throw AuditSyntaxError(path+": overloaded audit implementation needs distinct registered names: "+function);
                out.functions.insert(function);
            }
            scope+=name+"::";
        }
        if(in_main){
            const bool enumeration=kind=="EnumConstantDecl";
            const bool variable=kind=="VarDecl"||kind=="FieldDecl";
            const bool local=!function.empty()||in_class;
            const auto typ=text(get(n,"type"),"qualType");
            const bool initialized=get(n,"init").kind!=JsonKind::Null||get(n,"hasInClassInitializer").bool_value;
            const bool literal_init=std::any_of(children(n).begin(),children(n).end(),[&](const auto& c){return static_number(c,constant_ids);});
            if(enumeration||(variable&&initialized&&numeric_type(n)&&(!local||((kind=="FieldDecl"||typ.find("const")!=typ.npos||get(n,"constexpr").bool_value||upper_policy_name(name))&&literal_init)))){
                if(!local||enumeration||typ.find("const")!=typ.npos)constant_ids.insert(text(n,"id"));
                const auto site=path+":"+std::to_string(line(n));const auto symbol=path+"::"+scope+name;
                out.constants.push_back({symbol,site,local});
                static const std::set<std::string> banned={"_SNAP_EROSION","_SEAT_SLIDE","OUTLINE_SNAP","OUTLINE_SNAP_PCB","FINE_SNAP","REFINE_SPAN","GRID"};
                if(banned.count(name))out.quantization.push_back({site,function,"banned-constant"});
            }
            auto hit=[&](const std::string& detector){out.quantization.push_back({path+":"+std::to_string(line(n)),function,detector});};
            if(kind=="CallExpr"||kind=="CXXMemberCallExpr"){
                const auto& cs=children(n);auto target=cs.empty()?std::string{}:callee(cs.front());if(target.compare(0,10,"__builtin_")==0)target.erase(0,10);
                static const std::set<std::string> banned={"_gridify","_r5","_snap_up","_snap_up_fp"};
                if(raw_round(target))hit("raw-round");if(banned.count(target))hit("banned-call");
            }
            // Taking a raw-round function's address must not hide it behind an
            // innocently named function pointer at the eventual call site.
            if(kind=="DeclRefExpr"&&raw_round(callee(n)))hit("raw-round");
            if(text(n,"castKind")=="FloatingToIntegral")hit("float-to-integer");
            if(kind=="BinaryOperator"&&(text(n,"opcode")=="+"||text(n,"opcode")=="-")&&children(n).size()==2){const auto& cs=children(n);
                if((credit(cs[0])&&geometry(cs[1]))||(credit(cs[1])&&geometry(cs[0])))hit("credit-0.05");}
        }
        for(const auto& c:children(n))visit(c,scope,function,in_main,in_class);
    }
};
}
CppSourceCensus scan_cpp_audit_sources(const std::filesystem::path& root,const std::vector<CppAuditSource>& files,const CppAuditOptions& options){
    if(files.empty())throw std::invalid_argument("native source audit requires a nonempty decision-file manifest");
    if(options.compiler.empty())throw std::invalid_argument("native source audit requires a compiler");
    CppSourceCensus result;std::set<std::string> unique;
    for(const auto& file:files){
        const auto relative=std::filesystem::path(file.path).lexically_normal();
        if(relative.is_absolute()||relative.empty()||*relative.begin()=="..")throw std::invalid_argument("native audit manifest paths must be root-relative");
        if(!unique.insert(relative.generic_string()).second)throw std::invalid_argument("duplicate native audit manifest file: "+file.path);
        const auto path=std::filesystem::absolute(root/relative).lexically_normal();
        if(!std::filesystem::is_regular_file(path))throw std::runtime_error("native audit source is missing/not a file: "+path.string());
        std::vector<std::string> command{options.compiler};command.insert(command.end(),options.flags.begin(),options.flags.end());
        command.insert(command.end(),{"-std=c++17","-ffp-contract=off","-x","c++","-fsyntax-only","-Xclang","-ast-dump=json",path.string()});
        const auto compiled=run_process(command,options.timeout);
        if(compiled.exit_code!=0)throw AuditSyntaxError(path.string()+": C++ compiler failed ("+std::to_string(compiled.exit_code)+")\n"+compiled.stderr_text);
        const auto ast=parse_json_text(compiled.stdout_text,path.string()+" compiler AST");
        if(text(ast,"kind")!="TranslationUnitDecl")throw AuditSyntaxError(path.string()+": compiler did not return a translation-unit AST");
        Visitor{relative.generic_string(),path.string(),model_checks::read(path),result,{},{}}.visit(ast);++result.n_files;
        // Clang's JSON AST contains macro *expansions*, not definitions. Keep
        // object-like numeric policy macros visible using its preprocessor,
        // with the same target/defines/includes and compiler line markers.
        command={options.compiler};command.insert(command.end(),options.flags.begin(),options.flags.end());
        command.insert(command.end(),{"-std=c++17","-ffp-contract=off","-x","c++","-E","-dD",path.string()});
        const auto expanded=run_process(command,options.timeout);
        if(expanded.exit_code!=0)throw AuditSyntaxError(path.string()+": C++ preprocessing failed\n"+expanded.stderr_text);
        macros(expanded.stdout_text,path,relative.generic_string(),result);
    }
    return result;
}
NativeAuditResult check_native_audits(const CppSourceCensus& census,const NativeLedger& ledger,const NativeQuantizations& quantize){
    if(!census.n_files||(census.constants.empty()&&census.functions.empty()))throw std::invalid_argument("native audit cannot pass an empty source census");
    NativeAuditResult r;r.n_files=census.n_files;r.n_constants=census.constants.size();const auto state=ledger.audit_state();r.problems=state.problems;
    std::set<std::string> covered,constants,transforms;
    for(const auto& d:state.declarations){covered.insert(d.covers.begin(),d.covers.end());if(!d.repeated&&!state.recorded.count(d.name))r.absent.push_back(d.name);}
    for(const auto& c:census.constants){constants.insert(c.symbol);if(c.buried)r.buried.push_back(c.site+" "+c.symbol);else if(!covered.count(c.symbol))r.undeclared.push_back(c.symbol);}
    for(const auto& cover:covered)if(!constants.count(cover))r.stale.push_back("constant "+cover);
    for(const auto& d:quantize.declarations()){++r.n_transforms;transforms.insert(d.symbol);if(!census.functions.count(d.symbol))r.stale.push_back("transform "+d.symbol);}
    for(const auto& site:census.quantization)if(!transforms.count(site.function)||site.detector=="banned-constant"||site.detector=="banned-call")r.unregistered_quantization.push_back(site.site+" ["+site.detector+"] "+site.function);
    for(auto* rows:{&r.absent,&r.undeclared,&r.buried,&r.stale,&r.unregistered_quantization}){std::sort(rows->begin(),rows->end());rows->erase(std::unique(rows->begin(),rows->end()),rows->end());}
    r.ok=r.absent.empty()&&r.undeclared.empty()&&r.buried.empty()&&r.stale.empty()&&r.problems.empty()&&r.unregistered_quantization.empty();return r;
}
NativeAuditResult check_native_audits(const std::filesystem::path& root,const std::vector<CppAuditSource>& files,const NativeLedger& ledger,const NativeQuantizations& quantize,const CppAuditOptions& options){
    return check_native_audits(scan_cpp_audit_sources(root,files,options),ledger,quantize);
}
std::string NativeAuditResult::summary()const{
    std::vector<std::string> lines={"NATIVE POLICY AUDIT: "+std::string(ok?"PASS":"FAIL")+" — "+std::to_string(n_files)+" C++ files, "+std::to_string(n_constants)+" constants, "+std::to_string(n_transforms)+" registered transforms"};
    const auto rows=[&](const char* kind,const auto& values){for(const auto& value:values)lines.push_back(std::string("  ")+kind+": "+value);};
    rows("DECLARED BUT ABSENT",absent);rows("UNREGISTERED CONSTANT",undeclared);rows("BURIED CONSTANT",buried);rows("STALE COVER",stale);rows("LEDGER PROBLEM",problems);rows("UNREGISTERED QUANTIZATION",unregistered_quantization);return model_checks::join(lines);
}
} // namespace schgen
