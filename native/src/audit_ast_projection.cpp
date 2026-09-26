#include "schgen/audit_ast_projection.hpp"
#include <algorithm>
#include <array>
#include <charconv>
#include <cmath>
#include <cstdint>
#include <istream>
#include <stdexcept>
#include <vector>

namespace schgen {
bool audit_ast_projection_keeps_field(std::string_view key) {
    // Preserve every field read by the visitor, plus declaration-chain identity.
    static constexpr std::array<std::string_view,28> fields{{
        "begin", "castKind", "constexpr", "desugaredQualType", "expansionLoc",
        "file", "hasInClassInitializer", "id", "includedFrom", "init", "inner",
        "isImplicit", "kind", "loc", "mangledName", "name", "offset", "opcode",
        "parentDeclContextId", "previousDecl", "qualType", "range", "referencedDecl",
        "scopedEnumTag", "storageClass", "type", "value", "isInvalid"}};
    return std::find(fields.begin(),fields.end(),key)!=fields.end();
}
namespace {
struct StringInput {
    std::string_view remaining;
    std::size_t at=0;
    std::string_view chunk()const{return remaining;}
    void advance(std::size_t count){remaining.remove_prefix(count);at+=count;}
};
class StreamInput {
public:
    explicit StreamInput(std::istream& in):in_(in){}
    std::string_view chunk(){
        if(begin_==end_&&!done_){
            try{in_.read(bytes_.data(),static_cast<std::streamsize>(bytes_.size()));}
            catch(const std::ios_base::failure&){if(in_.bad()||!in_.eof())throw;}
            if(in_.bad()||(in_.fail()&&!in_.eof()))throw std::runtime_error("audit AST input read failed");
            begin_=0;end_=static_cast<std::size_t>(in_.gcount());done_=in_.eof();
            if(!end_&&!done_)throw std::runtime_error("audit AST input made no progress");
        }
        return {bytes_.data()+begin_,end_-begin_};
    }
    void advance(std::size_t count){begin_+=count;at+=count;}
    std::size_t at=0;
private:
    std::istream& in_;
    std::array<char,65536> bytes_{};
    std::size_t begin_=0,end_=0;
    bool done_=false;
};
// The same parser/validator handles memory and bounded-stream inputs. Nothing
// depends on object-key order, buffer boundaries, source names or namespaces.
template<class Input> class ProjectionParser {
public:
    ProjectionParser(Input& input,const std::string& source):input_(input),source_(source){}
    JsonNode parse(){
        auto result=value(true,0);space();
        if(!end())fail("trailing content after top-level value");
        stats.input_bytes=input_.at;return result;
    }
    AuditAstProjectionStats stats;
private:
    Input& input_;
    const std::string& source_;
    [[noreturn]] void fail(const std::string& detail)const{
        throw std::runtime_error("audit AST json "+source_+":"+std::to_string(input_.at)+": "+detail);
    }
    bool end(){return input_.chunk().empty();}
    char peek(){const auto c=input_.chunk();if(c.empty())fail("unexpected end of JSON");return c.front();}
    char take(){const auto c=peek();input_.advance(1);return c;}
    static bool white(char c){return c==' '||c=='\t'||c=='\r'||c=='\n';}
    void space(){for(;;){const auto v=input_.chunk();std::size_t i=0;while(i<v.size()&&white(v[i]))++i;input_.advance(i);if(i<v.size()||v.empty())return;}}
    bool consume(char c){if(!end()&&peek()==c){input_.advance(1);return true;}return false;}
    void expect(char c){space();if(!consume(c))fail(std::string("expected '")+c+"'");}
    static bool digit(char c){return c>='0'&&c<='9';}
    std::uint32_t unicode_unit(){
        std::uint32_t out=0;
        for(int i=0;i<4;++i){if(end())fail("truncated Unicode escape");const auto c=take();out<<=4;
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
    std::uint32_t raw_utf8(){
        const auto lead=static_cast<unsigned char>(take());
        const int remaining=lead>=0xc2&&lead<=0xdf?1:lead>=0xe0&&lead<=0xef?2:lead>=0xf0&&lead<=0xf4?3:0;
        if(!remaining)fail("invalid UTF-8 lead byte");
        std::uint32_t cp=lead&static_cast<unsigned>(remaining==1?0x1f:remaining==2?0x0f:0x07);
        for(int i=0;i<remaining;++i){if(end())fail("truncated UTF-8");const auto c=static_cast<unsigned char>(take());if((c&0xc0)!=0x80)fail("invalid UTF-8 continuation");cp=(cp<<6)|(c&0x3f);}
        if(cp<(remaining==1?0x80u:remaining==2?0x800u:0x10000u)||cp>0x10ffffu||(cp>=0xd800u&&cp<=0xdfffu))fail("invalid UTF-8 scalar");
        return cp;
    }
    std::string string(bool keep){
        if(!consume('"'))fail("expected string");std::string out;
        while(!end()){
            const auto v=input_.chunk();std::size_t count=0;
            while(count<v.size()){
                const auto c=static_cast<unsigned char>(v[count]);if(c=='"'||c=='\\'||c<0x20||c>=0x80)break;++count;
            }
            if(keep)out.append(v.data(),count);input_.advance(count);
            if(count==v.size())continue;
            if(static_cast<unsigned char>(peek())>=0x80){const auto cp=raw_utf8();if(keep)utf8(out,cp);continue;}
            const auto c=take();if(c=='"')return out;
            if(c!='\\')fail("unescaped control character");if(end())fail("truncated string escape");
            const auto escape=take();char decoded=0;
            switch(escape){
                case '"':case '\\':case '/':decoded=escape;break;
                case 'b':decoded='\b';break;case 'f':decoded='\f';break;
                case 'n':decoded='\n';break;case 'r':decoded='\r';break;case 't':decoded='\t';break;
                case 'u':{
                    auto cp=unicode_unit();
                    if(cp>=0xd800u&&cp<=0xdbffu){
                        if(!consume('\\')||!consume('u'))fail("missing low surrogate");
                        const auto low=unicode_unit();if(low<0xdc00u||low>0xdfffu)fail("invalid low surrogate");
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
        std::string token;if(consume('-'))token+='-';if(end()||!digit(peek()))fail("invalid number");
        if(consume('0'))token+='0';else while(!end()&&digit(peek()))token+=take();
        if(consume('.')){token+='.';if(end()||!digit(peek()))fail("invalid fraction");while(!end()&&digit(peek()))token+=take();}
        if(!end()&&(peek()=='e'||peek()=='E')){token+=take();if(!end()&&(peek()=='+'||peek()=='-'))token+=take();if(end()||!digit(peek()))fail("invalid exponent");while(!end()&&digit(peek()))token+=take();}
        double out=0;const auto parsed=std::from_chars(token.data(),token.data()+token.size(),out,std::chars_format::general);
        if(parsed.ec!=std::errc{}||parsed.ptr!=token.data()+token.size()||!std::isfinite(out))fail("unrepresentable number");return out;
    }
    JsonNode value(bool keep,std::size_t depth){
        if(depth>1024)fail("nesting exceeds 1024 levels");
        ++stats.json_values;if(keep)++stats.retained_values;space();if(end())fail("unexpected end of JSON");
        JsonNode out;const auto c=peek();
        if(c=='"'){out.kind=JsonKind::String;out.string_value=string(keep);return out;}
        if(c=='{'||c=='['){
            (void)take();const bool object=c=='{';out.kind=object?JsonKind::Object:JsonKind::Array;
            const char close=object?'}':']';space();if(consume(close))return out;std::vector<std::string> seen;
            while(true){
                if(object){
                    space();auto key=string(true);if(std::find(seen.begin(),seen.end(),key)!=seen.end())fail("duplicate key '"+key+"'");
                    seen.push_back(key);expect(':');const bool retain=keep&&audit_ast_projection_keeps_field(key);
                    if(retain)++stats.retained_fields;else ++stats.discarded_fields;
                    auto child=value(retain,depth+1);if(retain)out.object_value.emplace_back(std::move(key),std::move(child));
                }else{auto child=value(keep,depth+1);if(keep)out.array_value.push_back(std::move(child));}
                space();if(consume(close))return out;expect(',');
            }
        }
        if(c=='-'||digit(c)){out.kind=JsonKind::Number;out.number_value=number();return out;}
        const std::string_view word=c=='t'?"true":c=='f'?"false":c=='n'?"null":"";
        if(word.empty())fail("invalid value");for(const auto wanted:word)if(!consume(wanted))fail("invalid value");
        out.kind=word=="null"?JsonKind::Null:JsonKind::Bool;out.bool_value=word=="true";return out;
    }
};
template<class Input> JsonNode parse_input(Input& input,const std::string& source,AuditAstProjectionStats* stats){
    ProjectionParser<Input> parser(input,source);auto root=parser.parse();if(stats)*stats=parser.stats;return root;
}
}
JsonNode parse_audit_ast_projection(std::string_view json,const std::string& source,AuditAstProjectionStats* stats){
    StringInput input{json};return parse_input(input,source,stats);
}
JsonNode parse_audit_ast_projection(std::istream& json,const std::string& source,AuditAstProjectionStats* stats){
    StreamInput input(json);return parse_input(input,source,stats);
}
}
