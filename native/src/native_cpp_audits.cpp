#include "schgen/native_audit_state.hpp"
#include "schgen/process.hpp"
#include "schgen/audit_ast_projection.hpp"
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
std::string type_name(const JsonNode& n){const auto& t=get(n,"type");auto name=text(t,"desugaredQualType");return name.empty()?text(t,"qualType"):name;}
bool numeric_type(const JsonNode& n){
    auto type=type_name(n);
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
bool zero_initialization(const JsonNode& n){
    const auto kind=text(n,"kind");
    if(kind=="ImplicitValueInitExpr")return true;
    if(kind=="IntegerLiteral"||kind=="FloatingLiteral"||kind=="CharacterLiteral"){
        // Clang emits character values as JSON numbers, whereas ordinary
        // integer/floating literals use strings. Both represent zero state.
        const auto& literal=get(n,"value");
        if(literal.kind==JsonKind::Number)return literal.number_value==0;
        const auto value=text(n,"value");char* end=nullptr;const auto number=std::strtod(value.c_str(),&end);
        return !value.empty()&&end==value.c_str()+value.size()&&number==0;
    }
    if(kind=="UnaryOperator"&&text(n,"opcode")!="+"&&text(n,"opcode")!="-")return false;
    static const std::set<std::string> wrappers={"UnaryOperator","ParenExpr","ImplicitCastExpr","ConstantExpr","InitListExpr"};
    if(!wrappers.count(kind))return false;
    return std::all_of(children(n).begin(),children(n).end(),zero_initialization);
}
bool function_kind(const std::string& kind){return kind=="FunctionDecl"||kind=="CXXMethodDecl"||kind=="CXXConstructorDecl"||kind=="CXXConversionDecl"||kind=="CXXDestructorDecl";}
bool record_kind(const std::string& kind){return kind=="CXXRecordDecl"||kind=="RecordDecl"||kind=="ClassTemplateSpecializationDecl"||kind=="ClassTemplatePartialSpecializationDecl";}
std::string identity(const JsonNode& n){auto key=text(n,"mangledName");return key.empty()?type_name(n):key;}
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
    // Provisional keys retain the compiler's entity identity. A second pass
    // preserves old short names only for genuinely unambiguous implementations.
    std::map<std::string,std::map<std::string,std::string>> definitions;
    std::map<std::string,std::string> contexts;
    std::set<std::string> constant_ids;
    std::map<std::string,std::map<std::string,std::pair<std::size_t,std::size_t>>> constant_entities;
    void index(const JsonNode& n,std::string scope={}){
        const auto kind=text(n,"kind"),name=text(n,"name");
        if(get(n,"isImplicit").bool_value)return;
        const auto parent=text(n,"parentDeclContextId");
        if(!parent.empty()&&contexts.count(parent))scope=contexts.at(parent);
        if(kind=="NamespaceDecl"&&!name.empty())scope+=name+"::";
        if(record_kind(kind))scope+=(name.empty()?"<anonymous@"+text(location(get(n,"loc")),"file")+":"+std::to_string(get(location(get(n,"loc")),"offset").number_value)+">":name)+"::";
        if(function_kind(kind))scope+=name+"{"+identity(n)+"}::";
        if(kind=="NamespaceDecl"||record_kind(kind)||function_kind(kind)||kind=="TranslationUnitDecl")contexts[text(n,"id")]=scope;
        for(const auto& c:children(n))index(c,scope);
    }
    void finish(){
        // Block-local declarations can have the same spelling and function.
        // Keep their exact covers distinct rather than letting one cover bless
        // an unrelated shadow. Compiler IDs are process-local, so use source
        // offsets in the public spelling, never the AST pointer-like IDs.
        for(const auto& [symbol,entities]:constant_entities)if(entities.size()>1)
            for(const auto& [id,entry]:entities){(void)id;out.constants.at(entry.first).symbol=symbol+" [at "+std::to_string(entry.second)+"]";}
        std::vector<std::pair<std::string,std::string>> names;
        for(const auto& [base,overloads]:definitions){
            std::map<std::string,std::size_t> types;for(const auto& [key,type]:overloads){(void)key;++types[type];}
            for(const auto& [key,type]:overloads){
                auto shown=base;
                if(overloads.size()>1){shown+=" ["+type+"]";if(types[type]>1)shown+=key.substr(base.size());}
                names.emplace_back(key,shown);
            }
        }
        std::sort(names.begin(),names.end(),[](const auto& a,const auto& b){return a.first.size()>b.first.size();});
        const auto normalize=[&](std::string value){for(const auto& [key,shown]:names)if(value==key||value.compare(0,key.size()+2,key+"::")==0)value.replace(0,key.size(),shown);return value;};
        std::set<std::string> functions;for(const auto& f:out.functions)functions.insert(normalize(f));out.functions=std::move(functions);
        for(auto& c:out.constants)c.symbol=normalize(c.symbol);
        for(auto& q:out.quantization)q.function=normalize(q.function);
    }
    std::size_t line(const JsonNode& n)const{
        const auto& loc=location(get(n,"loc"));const auto& begin=location(get(get(n,"range"),"begin"));
        const auto& chosen=get(loc,"offset").kind==JsonKind::Number?loc:begin;
        const auto& off=get(chosen,"offset");if(off.kind!=JsonKind::Number)throw AuditSyntaxError(path+": compiler omitted source location");
        const auto offset=std::size_t(off.number_value);if(offset>source.size())throw AuditSyntaxError(path+": invalid compiler source offset");
        return std::size_t(std::count(source.begin(),source.begin()+static_cast<std::ptrdiff_t>(offset),'\n'))+1;
    }
    void visit(const JsonNode& n,std::string scope={},std::string function={},bool in_main=false,bool in_class=false,bool ordinal_enum=false){
        const auto kind=text(n,"kind"),name=text(n,"name");
        if(get(n,"isImplicit").bool_value&&kind!="ImplicitCastExpr")return;
        const auto& loc=location(get(n,"loc"));
        if(get(loc,"offset").kind==JsonKind::Number){const auto file=text(loc,"file");in_main=get(loc,"includedFrom").kind==JsonKind::Null&&(file.empty()||std::filesystem::path(file).lexically_normal()==absolute);}
        const auto parent=text(n,"parentDeclContextId");
        if(!parent.empty()){
            const auto found=contexts.find(parent);
            if(found==contexts.end())throw AuditSyntaxError(path+": compiler omitted semantic declaration context");
            scope=found->second;
        }
        if(kind=="NamespaceDecl"&&!name.empty())scope+=name+"::";
        if(kind=="EnumDecl"){
            if(!text(n,"scopedEnumTag").empty())scope+=name+"::";
            // An entirely unseeded enum supplies language identity ordinals.
            // Any authored initializer makes the whole enum numeric policy,
            // including members whose values follow that initializer implicitly.
            ordinal_enum=std::none_of(children(n).begin(),children(n).end(),[](const auto& member){
                if(text(member,"kind")!="EnumConstantDecl")return false;
                return std::any_of(children(member).begin(),children(member).end(),[](const auto& value){
                    const auto k=text(value,"kind");return k.size()<4||k.compare(k.size()-4,4,"Attr")!=0;
                });
            });
        }
        if(record_kind(kind)){scope=contexts.at(text(n,"id"));in_class=true;}
        if(kind=="LambdaExpr"){
            // Captures execute in the enclosing body; the lambda's implementation
            // is a distinct operation and must not inherit a scalar registration.
            const auto offset=get(location(get(get(n,"range"),"begin")),"offset").number_value;
            const auto lambda=(function.empty()?path:function)+"::<lambda@"+std::to_string(std::size_t(offset))+">";
            if(in_main)out.functions.insert(lambda);
            for(const auto& c:children(n))if(text(c,"kind")!="CXXRecordDecl"){
                const bool body=text(c,"kind")=="CompoundStmt";
                visit(c,body?lambda.substr(path.size()+2)+"::":scope,body?lambda:function,in_main,in_class);
            }
            return;
        }
        const bool fn=function_kind(kind);
        if(fn){
            const auto base=path+"::"+scope+name;function=base+"{"+identity(n)+"}";
            bool body=false;for(const auto& c:children(n))body|=text(c,"kind")=="CompoundStmt"||text(c,"kind")=="CXXTryStmt";
            if(in_main)definitions[base][function]=type_name(n);
            if(in_main&&body){
                out.functions.insert(function);
            }
            scope=function.substr(path.size()+2)+"::";
        }
        if(in_main){
            const bool enumeration=kind=="EnumConstantDecl";
            const bool variable=kind=="VarDecl"||kind=="FieldDecl";
            const bool local=!function.empty()||in_class;
            const auto typ=type_name(n);const bool immutable=typ.find("const")!=typ.npos||get(n,"constexpr").bool_value;
            const bool initialized=get(n,"init").kind!=JsonKind::Null||get(n,"hasInClassInitializer").bool_value;
            const bool literal_init=std::any_of(children(n).begin(),children(n).end(),[&](const auto& c){return static_number(c,constant_ids);});
            const bool state_field=kind=="FieldDecl"&&!immutable&&!upper_policy_name(name)&&
                std::all_of(children(n).begin(),children(n).end(),zero_initialization);
            const bool policy_storage=immutable||upper_policy_name(name)||text(n,"storageClass")=="static"||(kind=="FieldDecl"&&!state_field);
            // Ordinals remain compile-time values for detecting independently
            // authored engineering arithmetic derived from a category label.
            if(enumeration)constant_ids.insert(text(n,"id"));
            if((enumeration&&!ordinal_enum)||(variable&&initialized&&numeric_type(n)&&(!local||(policy_storage&&literal_init)))){
                if(enumeration||immutable)constant_ids.insert(text(n,"id"));
                const auto site=path+":"+std::to_string(line(n));const auto symbol=path+"::"+scope+name;
                const auto id=text(n,"id");auto& entities=constant_entities[symbol];
                if(!entities.count(id)){
                    entities[id]={out.constants.size(),std::size_t(get(loc,"offset").number_value)};
                    out.constants.push_back({symbol,site,local});
                }
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
        for(const auto& c:children(n))visit(c,scope,function,in_main,in_class,ordinal_enum);
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
        const auto ast=parse_audit_ast_projection(compiled.stdout_text,path.string()+" compiler AST");
        if(text(ast,"kind")!="TranslationUnitDecl")throw AuditSyntaxError(path.string()+": compiler did not return a translation-unit AST");
        CppSourceCensus local;
        Visitor visitor{relative.generic_string(),path.string(),model_checks::read(path),local,{},{},{},{}};
        visitor.index(ast);visitor.visit(ast);visitor.finish();
        result.constants.insert(result.constants.end(),local.constants.begin(),local.constants.end());
        result.functions.insert(local.functions.begin(),local.functions.end());
        result.quantization.insert(result.quantization.end(),local.quantization.begin(),local.quantization.end());++result.n_files;
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
    std::set<std::string> covered,constants,transforms;std::map<std::string,std::size_t> constant_counts;
    for(const auto& d:state.declarations){covered.insert(d.covers.begin(),d.covers.end());if(!d.repeated&&!state.recorded.count(d.name))r.absent.push_back(d.name);}
    for(const auto& c:census.constants){constants.insert(c.symbol);++constant_counts[c.symbol];if(!covered.count(c.symbol)){if(c.buried)r.buried.push_back(c.site+" "+c.symbol);else r.undeclared.push_back(c.symbol);}}
    for(const auto& [symbol,count]:constant_counts)if(count>1&&covered.count(symbol))r.problems.push_back("ambiguous constant cover "+symbol);
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
