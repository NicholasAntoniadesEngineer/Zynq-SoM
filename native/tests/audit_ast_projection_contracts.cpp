#include "schgen/audit_ast_projection.hpp"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <set>
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
    AuditAstProjectionStats stats;stats.input_bytes=918;stats.json_values=117;
    bool threw=false;try{(void)parse_audit_ast_projection(input,"negative",&stats);}catch(const std::runtime_error&){threw=true;}
    require(threw,"must reject malformed JSON: "+input.substr(0,100));
    require(stats.input_bytes==918&&stats.json_values==117,"failed parse must not publish partial stats");
}
void contracts(){
    for(const auto& field:schema)require(audit_ast_projection_keeps_field(field),"schema field missing: "+field);
    for(const auto* field:{"line","col","end","spellingLoc","tokLen","isUsed","valueCategory","definitionData","unknown"})require(!audit_ast_projection_keeps_field(field),"unused field retained");
    const std::string ast=R"JSON({"unused":{"deep":[1,true,null,{"inner":["ignored"]}]},"inner":[{"parentDeclContextId":"0xparent","kind":"CXXMethodDecl","id":"0xmethod","mangledName":"_Zmethod","loc":{"offset":12,"line":2,"col":1,"includedFrom":{"file":"header.hpp"}},"type":{"qualType":"double (double)","desugaredQualType":"double (double)","typeAliasDeclId":"unused"},"isImplicit":false,"inner":[{"range":{"end":{"offset":99},"begin":{"offset":14,"expansionLoc":{"offset":18,"file":"main.cpp"},"spellingLoc":{"offset":999}}},"kind":"DeclRefExpr","referencedDecl":{"kind":"VarDecl","id":"0xvar","name":"α😀","type":{"qualType":"const double"}}}]},{"name":"","kind":"NamespaceDecl","id":"0xanon"}],"kind":"TranslationUnitDecl","id":"0xroot"})JSON";
    AuditAstProjectionStats stats;
    same(strip(parse_json_text(ast)),parse_audit_ast_projection(ast,"fixture",&stats));
    require(stats.input_bytes==ast.size()&&stats.discarded_fields==10,"projection accounts discarded fields");
    require(stats.json_values>stats.retained_values,"skipped values were parsed without materializing");
    // Field order is not constrained to Clang's usual kind/id/inner order.
    for(const auto* input:{R"({"inner":[{"value":"2.5","kind":"FloatingLiteral"}],"id":"x","kind":"VarDecl"})",
            R"({"value":"\uD83D\uDE00\n\u0000","loc":{"offset":-0},"id":"é"})",
            R"({"value":-12345.6789e-3,"unknown":{"value":"\uD834\uDD1E"}})",
            R"([null,false,true,1,0,-0,1e25,1.25e-25,"",{},[]])"})
        same(strip(parse_json_text(input)),parse_audit_ast_projection(input));
    for(const auto* input:{R"({"name":"\u007f\u0080\u07ff\u0800\ud7ff\ue000\uffff\ud800\udc00\udbff\udfff"})",
            R"({"id":"\"\\\/\b\f\n\r\t","name":"","\u006bind":"TranslationUnitDecl"})",
            R"({"offset":9007199254740991,"inner":[0.1,1.2345678901234567,2.2250738585072014e-308,1.7976931348623157e308]})"})
        same(strip(parse_json_text(input)),parse_audit_ast_projection(input));
    // Independent generated trees put whitelisted names beneath discarded
    // objects and discarded names beside real nodes. No field may leak back
    // out of a skipped parent merely because its spelling is retained elsewhere.
    for(int i=0;i<256;++i){
        const auto n=std::to_string(i);
        const auto input=std::string("{\"unknown\":{\"inner\":[{\"kind\":\"VarDecl\",\"value\":")+n+
            "}]},\"inner\":[{\"value\":"+n+",\"kind\":\"IntegerLiteral\",\"ignored\":[{\"name\":\"hidden\"}]}],\"offset\":"+n+"}";
        same(strip(parse_json_text(input)),parse_audit_ast_projection(input));
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
        parse_audit_ast_projection(std::string(1024,'[')+"0"+std::string(1024,']')));
    const auto wide=std::string("{\"unused\":\"")+std::string(8*1024*1024,'a')+"\",\"kind\":\"TranslationUnitDecl\"}";
    const auto projected=parse_audit_ast_projection(wide,"large skipped string",&stats);
    require(projected.object_value.size()==1&&stats.retained_values==2&&stats.json_values==3,"large unknown string has no DOM payload");
}
}
int main(){try{contracts();std::cout<<checks<<" AST projection parser contracts PASS\n";return 0;}catch(const std::exception& e){std::cerr<<"AST projection FAILED after "<<checks<<": "<<e.what()<<'\n';return 1;}}
