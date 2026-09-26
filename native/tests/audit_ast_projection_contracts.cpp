#include "schgen/audit_ast_projection.hpp"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <set>
#include <sstream>
#include <streambuf>
#include <stdexcept>

namespace {
using namespace schgen;
std::size_t checks=0;
void require(bool ok,const std::string& why){++checks;if(!ok)throw std::runtime_error(why);}
// Independent schema: intentional duplication makes accidental additions or
// omissions a contract change, not something the projector blesses itself.
const std::set<std::string> schema={
    "begin","castKind","constexpr","desugaredQualType","expansionLoc","file",
    "hasInClassInitializer","id","includedFrom","init","inner","isImplicit",
    "isInvalid","kind","loc","mangledName","name","offset","opcode",
    "parentDeclContextId","previousDecl","qualType","range","referencedDecl",
    "scopedEnumTag","storageClass","type","value"};
JsonNode strip(JsonNode n){
    if(n.kind==JsonKind::Object){
        auto& fields=n.object_value;
        fields.erase(std::remove_if(fields.begin(),fields.end(),[](const auto& p){return !schema.count(p.first);}),fields.end());
        for(auto& p:fields)p.second=strip(std::move(p.second));
    }else if(n.kind==JsonKind::Array)for(auto& c:n.array_value)c=strip(std::move(c));
    return n;
}
void same(const JsonNode& a,const JsonNode& b){
    require(a.kind==b.kind,"JSON kind preserved");
    require(a.string_value==b.string_value,"string bytes preserved");
    require(a.bool_value==b.bool_value,"boolean preserved");
    require(a.number_value==b.number_value&&std::signbit(a.number_value)==std::signbit(b.number_value),"number bits/sign preserved");
    require(a.array_value.size()==b.array_value.size(),"array population preserved");
    require(a.object_value.size()==b.object_value.size(),"exact field projection");
    for(std::size_t i=0;i<a.array_value.size();++i)same(a.array_value[i],b.array_value[i]);
    for(std::size_t i=0;i<a.object_value.size();++i){require(a.object_value[i].first==b.object_value[i].first,"object key/order preserved");same(a.object_value[i].second,b.object_value[i].second);}
}
void rejected(const std::string& input){
    for(bool streaming:{false,true}){
        AuditAstProjectionStats stats;stats.input_bytes=918;stats.json_values=117;
        bool threw=false;try{std::istringstream stream(input);
            (void)(streaming?parse_audit_ast_projection(stream,"negative",&stats):parse_audit_ast_projection(input,"negative",&stats));
        }catch(const std::runtime_error&){threw=true;}
        require(threw,"must reject malformed JSON: "+input.substr(0,100));
        require(stats.input_bytes==918&&stats.json_values==117,"failed parse must not publish partial stats");
    }
}
JsonNode projected(const std::string& input,const std::string& source="fixture",AuditAstProjectionStats* stats=nullptr){
    AuditAstProjectionStats memory_stats,stream_stats;std::istringstream stream(input);
    const auto memory=parse_audit_ast_projection(input,source,&memory_stats);
    const auto streamed=parse_audit_ast_projection(stream,source,&stream_stats);same(memory,streamed);
    require(memory_stats.input_bytes==stream_stats.input_bytes&&memory_stats.json_values==stream_stats.json_values&&
        memory_stats.retained_values==stream_stats.retained_values&&memory_stats.retained_fields==stream_stats.retained_fields&&
        memory_stats.discarded_fields==stream_stats.discarded_fields,"memory/stream complete accounting agrees");
    if(stats)*stats=memory_stats;return memory;
}
void contracts(){
    for(const auto& field:schema)require(audit_ast_projection_keeps_field(field),"schema field missing: "+field);
    for(const auto* field:{"line","col","end","spellingLoc","tokLen","isUsed","valueCategory","definitionData","unknown"})require(!audit_ast_projection_keeps_field(field),"unused field retained");
    const std::string ast=R"JSON({"unused":{"deep":[1,true,null,{"inner":["ignored"]}]},"inner":[{"parentDeclContextId":"0xparent","kind":"CXXMethodDecl","id":"0xmethod","mangledName":"_Zmethod","loc":{"offset":12,"line":2,"col":1,"includedFrom":{"file":"header.hpp"}},"type":{"qualType":"double (double)","desugaredQualType":"double (double)","typeAliasDeclId":"unused"},"isImplicit":false,"inner":[{"range":{"end":{"offset":99},"begin":{"offset":14,"expansionLoc":{"offset":18,"file":"main.cpp"},"spellingLoc":{"offset":999}}},"kind":"DeclRefExpr","referencedDecl":{"kind":"VarDecl","id":"0xvar","name":"α😀","type":{"qualType":"const double"}}}]},{"name":"","kind":"NamespaceDecl","id":"0xanon"}],"kind":"TranslationUnitDecl","id":"0xroot"})JSON";
    AuditAstProjectionStats stats;
    same(strip(parse_json_text(ast)),projected(ast,"fixture",&stats));
    require(stats.input_bytes==ast.size()&&stats.discarded_fields==10,"projection accounts discarded fields");
    require(stats.json_values>stats.retained_values,"skipped values were parsed without materializing");
    // Field order is not constrained to Clang's usual kind/id/inner order.
    for(const auto* input:{R"({"inner":[{"value":"2.5","kind":"FloatingLiteral"}],"id":"x","kind":"VarDecl"})",
            R"({"value":"\uD83D\uDE00\n\u0000","loc":{"offset":-0},"id":"é"})",
            R"({"value":-12345.6789e-3,"unknown":{"value":"\uD834\uDD1E"}})",
            R"([null,false,true,1,0,-0,1e25,1.25e-25,"",{},[]])"})
        same(strip(parse_json_text(input)),projected(input));
    for(const auto* input:{R"({"name":"\u007f\u0080\u07ff\u0800\ud7ff\ue000\uffff\ud800\udc00\udbff\udfff"})",
            R"({"id":"\"\\\/\b\f\n\r\t","name":"","\u006bind":"TranslationUnitDecl"})",
            R"({"offset":9007199254740991,"inner":[0.1,1.2345678901234567,2.2250738585072014e-308,1.7976931348623157e308]})"})
        same(strip(parse_json_text(input)),projected(input));
    // Independent generated trees put whitelisted names beneath discarded
    // objects and discarded names beside real nodes. No field may leak back
    // out of a skipped parent merely because its spelling is retained elsewhere.
    for(int i=0;i<256;++i){
        const auto n=std::to_string(i);
        const auto input=std::string("{\"unknown\":{\"inner\":[{\"kind\":\"VarDecl\",\"value\":")+n+
            "}]},\"inner\":[{\"value\":"+n+",\"kind\":\"IntegerLiteral\",\"ignored\":[{\"name\":\"hidden\"}]}],\"offset\":"+n+"}";
        same(strip(parse_json_text(input)),projected(input));
    }
    // Every incomplete non-whitespace prefix of a complete nested document.
    for(std::size_t i=0;i<ast.size();++i)rejected(ast.substr(0,i));
    for(const auto* bad:{"", " ","{", "[", "null null", "falsex", "[1,]", "{\"x\":1,}",
            "{\"x\" 1}","{\"x\":}","{\"x\":01}","{\"x\":+1}","{\"x\":1.}",
            "{\"x\":1e}","{\"x\":1e+}","{\"x\":1e9999}","{\"x\":NaN}","{\"x\":Infinity}",
            R"({"unknown":{"x":1,"x":2}})",R"({"name":"one","\u006eame":"two"})",
            R"({"unknown":"\x00"})",R"({"unknown":"\uD800"})",R"({"unknown":"\uDC00"})",
            R"({"unknown":"\uD800\uD800"})",R"({"unknown":"\uD800\u0041"})",R"({"unknown":"\uZZZZ"})"})rejected(bad);
    for(const auto& bytes:{std::string("\xc0\x80",2),std::string("\xed\xa0\x80",3),std::string("\xf4\x90\x80\x80",4),std::string("\xe2\x82",2),std::string("\x80",1),std::string("\xe2\x28\xa1",3),std::string("\0",1),std::string("\n",1)})
        for(const auto* key:{"unknown","name"})rejected(std::string("{\"")+key+"\":\""+bytes+"\"}");
    rejected(std::string(1026,'[')+"0"+std::string(1026,']'));
    same(strip(parse_json_text(std::string(1024,'[')+"0"+std::string(1024,']'))),
        projected(std::string(1024,'[')+"0"+std::string(1024,']')));
    const auto wide=std::string("{\"unused\":\"")+std::string(8*1024*1024,'a')+"\",\"kind\":\"TranslationUnitDecl\"}";
    const auto wide_node=projected(wide,"large skipped string",&stats);
    require(wide_node.object_value.size()==1&&stats.retained_values==2&&stats.json_values==3,"large unknown string has no DOM payload");
}
void streaming_boundaries(){
    const std::vector<std::string> valid={
        R"({"name":"\uD83D\uDE00α😀\\\"","unknown":"\uD834\uDD1E","loc":{"offset":-123.45678e+12}})",
        R"({"inner":[true,false,null,1.7976931348623157e308],"kind":"TranslationUnitDecl"})",
        R"({"unknown":{"inner":[0,{},[],{"deep":"escaped\ntext"}]},"referencedDecl":{"id":"0xabcdef","kind":"VarDecl"}})"};
    for(std::size_t pad=65400;pad<=65560;++pad)for(const auto& tail:valid){
        const auto input=std::string(pad,' ')+tail;same(strip(parse_json_text(input)),projected(input));
    }
    for(std::size_t pad=65500;pad<=65540;++pad)for(const auto* tail:{
            R"({"unknown":"\uD800\u0041"})",R"({"unknown":{"x":1,"\u0078":2}})",
            R"({"unknown":1e+})",R"({"kind":"TranslationUnitDecl"} trailing)",
            "{\"unknown\":\"\xf0\x9f\x98\"}","{\"name\":\"\xed\xa0\x80\"}"})
        rejected(std::string(pad,' ')+tail);
    // Long retained and discarded strings span several input buffers.
    const auto long_value=std::string("{\"name\":\"")+std::string(200000,'x')+"😀\",\"unknown\":\""+std::string(200000,'y')+"\"}";
    same(strip(parse_json_text(long_value)),projected(long_value));
    struct Broken final:std::streambuf {int_type underflow()override{throw std::runtime_error("injected read failure");}} broken;
    std::istream input(&broken);bool rejected_io=false;try{(void)parse_audit_ast_projection(input);}catch(const std::runtime_error&){rejected_io=true;}
    require(rejected_io,"I/O failure is not successful EOF");
    std::istringstream exception_eof("{\"kind\":\"TranslationUnitDecl\"}");exception_eof.exceptions(std::ios::badbit|std::ios::failbit);
    require(parse_audit_ast_projection(exception_eof).kind==JsonKind::Object,"ordinary EOF with caller exception mask works");
}
void wide_object_keys(){
    // Cross the inline/spill boundary in both retained and skipped objects.
    // The independent schema and generic JSON parser remain the oracle.
    for(const std::size_t width:{7u,8u,9u,16u,65u}){
        std::string fields="\"kind\":\"TranslationUnitDecl\"";
        for(std::size_t i=1;i<width;++i)fields+=",\"unknown_"+std::to_string(i)+"\":{}";
        for(const bool skipped:{false,true}){
            const auto prefix=skipped?"{\"unknown\":{" : "{";
            const auto suffix=skipped?"}}":"}";
            const auto valid=prefix+fields+suffix;
            same(strip(parse_json_text(valid)),projected(valid));
            // First, last inline, and spilled keys; escaped spellings must
            // compare by decoded bytes. Padding also exercises stream refill.
            for(const auto& duplicate:{std::string("kind"),"unknown_"+std::to_string(width-1)}){
                auto escaped=duplicate;escaped.replace(0,1,duplicate.front()=='k'?"\\u006b":"\\u0075");
                for(const auto& key:{duplicate,escaped}){
                    const auto bad=prefix+fields+",\""+key+"\":null"+suffix;
                    rejected(bad);rejected(std::string(65525,' ')+bad);
                }
            }
        }
    }
}
}
int main(){try{contracts();streaming_boundaries();wide_object_keys();std::cout<<checks<<" AST projection parser contracts PASS\n";return 0;}catch(const std::exception& e){std::cerr<<"AST projection FAILED after "<<checks<<": "<<e.what()<<'\n';return 1;}}
