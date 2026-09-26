#include "schgen/audit_ast_projection.hpp"
#include <algorithm>
#include <array>
#include <charconv>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace schgen {
bool audit_ast_projection_keeps_field(std::string_view key) {
    // Include previousDecl even though today's visitor only needs id and
    // parentDeclContextId: do not discard declaration-chain identity.
    static constexpr std::array<std::string_view,28> fields{{
        "begin", "castKind", "constexpr", "desugaredQualType", "expansionLoc",
        "file", "hasInClassInitializer", "id", "includedFrom", "init", "inner",
        "isImplicit", "kind", "loc", "mangledName", "name", "offset", "opcode",
        "parentDeclContextId", "previousDecl", "qualType", "range", "referencedDecl",
        "scopedEnumTag", "storageClass", "type", "value", "isInvalid"}};
    return std::find(fields.begin(),fields.end(),key)!=fields.end();
}
namespace {
class ProjectionParser {
public:
    ProjectionParser(std::string_view input,const std::string& source):input_(input),source_(source) {
        stats.input_bytes=input.size();
    }
    JsonNode parse(){
        auto result=value(true,0);space();
        if(at_!=input_.size())fail("trailing content after top-level value");
        return result;
    }
    AuditAstProjectionStats stats;
private:
    std::string_view input_;
    const std::string& source_;
    std::size_t at_=0;
    [[noreturn]] void fail(const std::string& detail)const{
        throw std::runtime_error("audit AST json "+source_+":"+std::to_string(at_)+": "+detail);
    }
    bool end()const{return at_==input_.size();}
    void space(){while(!end()&&(input_[at_]==' '||input_[at_]=='\t'||input_[at_]=='\r'||input_[at_]=='\n'))++at_;}
    bool consume(char c){if(!end()&&input_[at_]==c){++at_;return true;}return false;}
    void expect(char c){space();if(!consume(c))fail(std::string("expected '")+c+"'");}
    static bool digit(char c){return c>='0'&&c<='9';}
    std::uint32_t unicode_unit(){
        if(input_.size()-at_<4)fail("truncated Unicode escape");
        std::uint32_t out=0;
        for(int i=0;i<4;++i){const auto c=input_[at_++];out<<=4;
            if(c>='0'&&c<='9')out|=static_cast<std::uint32_t>(c-'0');
            else if(c>='a'&&c<='f')out|=static_cast<std::uint32_t>(c-'a'+10);
            else if(c>='A'&&c<='F')out|=static_cast<std::uint32_t>(c-'A'+10);
            else fail("invalid Unicode escape");
        }
        return out;
    }
    static void utf8(std::string& out,std::uint32_t cp){
        if(cp<=0x7f)out.push_back(static_cast<char>(cp));
        else if(cp<=0x7ff){out.push_back(static_cast<char>(0xc0|(cp>>6)));out.push_back(static_cast<char>(0x80|(cp&0x3f)));}
        else if(cp<=0xffff){out.push_back(static_cast<char>(0xe0|(cp>>12)));out.push_back(static_cast<char>(0x80|((cp>>6)&0x3f)));out.push_back(static_cast<char>(0x80|(cp&0x3f)));}
        else{out.push_back(static_cast<char>(0xf0|(cp>>18)));out.push_back(static_cast<char>(0x80|((cp>>12)&0x3f)));out.push_back(static_cast<char>(0x80|((cp>>6)&0x3f)));out.push_back(static_cast<char>(0x80|(cp&0x3f)));}
    }
    void raw_utf8(){
        const auto lead=static_cast<unsigned char>(input_[at_++]);
        const int remaining=lead>=0xc2&&lead<=0xdf?1:lead>=0xe0&&lead<=0xef?2:lead>=0xf0&&lead<=0xf4?3:0;
        if(!remaining)fail("invalid UTF-8 lead byte");
        if(input_.size()-at_<static_cast<std::size_t>(remaining))fail("truncated UTF-8");
        std::uint32_t cp=lead&static_cast<unsigned>(remaining==1?0x1f:remaining==2?0x0f:0x07);
        for(int i=0;i<remaining;++i){const auto c=static_cast<unsigned char>(input_[at_++]);if((c&0xc0)!=0x80)fail("invalid UTF-8 continuation");cp=(cp<<6)|(c&0x3f);}
        if(cp<(remaining==1?0x80u:remaining==2?0x800u:0x10000u)||cp>0x10ffffu||(cp>=0xd800u&&cp<=0xdfffu))fail("invalid UTF-8 scalar");
    }
    std::string string(bool keep){
        if(!consume('"'))fail("expected string");
        std::string out;
        while(!end()){
            const auto start=at_;
            while(!end()){
                const auto c=static_cast<unsigned char>(input_[at_]);
                if(c=='"'||c=='\\'||c<0x20)break;
                if(c>=0x80)raw_utf8();else ++at_;
            }
            if(keep)out.append(input_.data()+start,at_-start);
            if(end())fail("unterminated string");
            const auto c=input_[at_++];if(c=='"')return out;
            if(c!='\\')fail("unescaped control character");
            if(end())fail("truncated string escape");
            const auto escape=input_[at_++];char decoded=0;
            switch(escape){
                case '"':case '\\':case '/':decoded=escape;break;
                case 'b':decoded='\b';break;case 'f':decoded='\f';break;
                case 'n':decoded='\n';break;case 'r':decoded='\r';break;case 't':decoded='\t';break;
                case 'u':{
                    auto cp=unicode_unit();
                    if(cp>=0xd800u&&cp<=0xdbffu){
                        if(input_.size()-at_<2||input_[at_]!='\\'||input_[at_+1]!='u')fail("missing low surrogate");
                        at_+=2;const auto low=unicode_unit();if(low<0xdc00u||low>0xdfffu)fail("invalid low surrogate");
                        cp=0x10000u+((cp-0xd800u)<<10)+low-0xdc00u;
                    }else if(cp>=0xdc00u&&cp<=0xdfffu)fail("unpaired low surrogate");
                    if(keep)utf8(out,cp);continue;
                }
                default:fail("invalid string escape");
            }
            if(keep)out.push_back(decoded);
        }
        fail("unterminated string");
    }
    double number(){
        const auto start=at_;consume('-');if(end()||!digit(input_[at_]))fail("invalid number");
        if(!consume('0'))while(!end()&&digit(input_[at_]))++at_;
        if(consume('.')){if(end()||!digit(input_[at_]))fail("invalid fraction");while(!end()&&digit(input_[at_]))++at_;}
        if(consume('e')||consume('E')){if(!consume('+'))consume('-');if(end()||!digit(input_[at_]))fail("invalid exponent");while(!end()&&digit(input_[at_]))++at_;}
        double out=0;
        const auto parsed=std::from_chars(input_.data()+start,input_.data()+at_,out,std::chars_format::general);
        if(parsed.ec!=std::errc{}||parsed.ptr!=input_.data()+at_||!std::isfinite(out))fail("unrepresentable number");
        return out;
    }
    JsonNode value(bool keep,std::size_t depth){
        if(depth>1024)fail("nesting exceeds 1024 levels");
        ++stats.json_values;if(keep)++stats.retained_values;space();
        if(end())fail("unexpected end of JSON");
        JsonNode out;const auto c=input_[at_];
        if(c=='"'){out.kind=JsonKind::String;out.string_value=string(keep);return out;}
        if(c=='{'||c=='['){
            ++at_;const bool object=c=='{';out.kind=object?JsonKind::Object:JsonKind::Array;
            const char close=object?'}':']';space();if(consume(close))return out;
            std::vector<std::string> seen;
            while(true){
                if(object){
                    space();auto key=string(true);
                    if(std::find(seen.begin(),seen.end(),key)!=seen.end())fail("duplicate key '"+key+"'");
                    seen.push_back(key);expect(':');
                    const bool retain=keep&&audit_ast_projection_keeps_field(key);
                    if(retain)++stats.retained_fields;else ++stats.discarded_fields;
                    auto child=value(retain,depth+1);
                    if(retain)out.object_value.emplace_back(std::move(key),std::move(child));
                }else{
                    auto child=value(keep,depth+1);if(keep)out.array_value.push_back(std::move(child));
                }
                space();if(consume(close))return out;expect(',');
            }
        }
        if(c=='-'||digit(c)){out.kind=JsonKind::Number;out.number_value=number();return out;}
        for(const auto word:{std::string_view{"true"},std::string_view{"false"},std::string_view{"null"}})
            if(input_.substr(at_,word.size())==word){at_+=word.size();out.kind=word=="null"?JsonKind::Null:JsonKind::Bool;out.bool_value=word=="true";return out;}
        fail("invalid value");
    }
};
}
JsonNode parse_audit_ast_projection(std::string_view json,const std::string& source,AuditAstProjectionStats* stats){
    ProjectionParser parser(json,source);auto root=parser.parse();if(stats)*stats=parser.stats;return root;
}
}
