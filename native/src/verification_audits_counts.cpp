#include "verification_audits_internal.hpp"
#include <iomanip>

namespace schgen {
namespace {
std::string decimal_ascii(const std::string& value){
    // Unicode 16.0 Nd zero points, captured independently from the original
    // interpreter. Every block has ten digits; no locale-dependent coercion.
    static constexpr std::uint32_t zeros[]={0x30,0x660,0x6f0,0x7c0,0x966,0x9e6,0xa66,0xae6,0xb66,0xbe6,0xc66,0xce6,0xd66,0xde6,0xe50,0xed0,0xf20,0x1040,0x1090,0x17e0,0x1810,0x1946,0x19d0,0x1a80,0x1a90,0x1b50,0x1bb0,0x1c40,0x1c50,0xa620,0xa8d0,0xa900,0xa9d0,0xa9f0,0xaa50,0xabf0,0xff10,0x104a0,0x10d30,0x10d40,0x11066,0x110f0,0x11136,0x111d0,0x112f0,0x11450,0x114d0,0x11650,0x116c0,0x116d0,0x116da,0x11730,0x118e0,0x11950,0x11bf0,0x11c50,0x11d50,0x11da0,0x11f50,0x16130,0x16a60,0x16ac0,0x16b50,0x16d70,0x1ccf0,0x1d7ce,0x1d7d8,0x1d7e2,0x1d7ec,0x1d7f6,0x1e140,0x1e2f0,0x1e4f0,0x1e5f1,0x1e950,0x1fbf0};
    std::string out;
    for(const auto& [cp,bytes]:verification::utf8(value)){
        if(cp>=128&&verification::space(cp)){out+=' ';continue;}
        bool digit=false;for(auto zero:zeros)if(cp>=zero&&cp<zero+10){out+=char('0'+cp-zero);digit=true;break;}
        if(!digit)out+=bytes;
    }
    // int() rejects ASCII file/group/record/unit separators even though Python
    // str.strip() regards them as whitespace; do not broaden that boundary.
    const auto whitespace=[](char c){return c==' '||(c>='\t'&&c<='\r');};
    std::size_t first=0,last=out.size();while(first<last&&whitespace(out[first]))++first;while(last>first&&whitespace(out[last-1]))--last;
    return out.substr(first,last-first);
}
}
AuditInteger::AuditInteger(std::int64_t value):digits_(std::to_string(value)){}
AuditInteger AuditInteger::decimal(std::string value){
    value=decimal_ascii(value);
    std::size_t i=0;bool negative=false;
    if(!value.empty()&&(value[0]=='+'||value[0]=='-')){negative=value[0]=='-';++i;}
    std::string digits;bool last_digit=false;
    for(;i<value.size();++i){const auto c=value[i];
        if(c=='_'&&last_digit&&i+1<value.size()&&value[i+1]>='0'&&value[i+1]<='9'){last_digit=false;continue;}
        if(c<'0'||c>'9')throw std::invalid_argument("audit integer requires decimal digits");
        digits+=c;last_digit=true;
    }
    if(digits.empty())throw std::invalid_argument("audit integer is empty");
    const auto begin=digits.find_first_not_of('0');
    AuditInteger out;out.digits_=begin==digits.npos?"0":(negative?"-":"")+digits.substr(begin);return out;
}
bool operator<(const AuditInteger& a,const AuditInteger& b){
    const bool an=a.digits_[0]=='-',bn=b.digits_[0]=='-';if(an!=bn)return an;
    if(a.digits_.size()!=b.digits_.size())return an?a.digits_.size()>b.digits_.size():a.digits_.size()<b.digits_.size();
    return an?a.digits_>b.digits_:a.digits_<b.digits_;
}
} // namespace schgen

namespace schgen::audit_detail {
namespace {
// Baseline-only lossless JSON reader. Number token spelling is retained until
// Python int() coercion, so a valid huge integer never becomes a corrupt file.
struct Value {
    char kind='n';std::string text;
    std::vector<std::pair<std::string,Value>> object;
};
void utf8(std::string& s,std::uint32_t cp){
    if(cp<0x80)s+=char(cp);
    else if(cp<0x800){s+=char(0xc0|(cp>>6));s+=char(0x80|(cp&63));}
    else if(cp<0x10000){s+=char(0xe0|(cp>>12));s+=char(0x80|((cp>>6)&63));s+=char(0x80|(cp&63));}
    else{s+=char(0xf0|(cp>>18));s+=char(0x80|((cp>>12)&63));s+=char(0x80|((cp>>6)&63));s+=char(0x80|(cp&63));}
}
struct Reader {
    const std::string& s;std::size_t i=0;
    [[noreturn]] void fail(){throw std::invalid_argument("invalid audit baseline JSON");}
    void ws(){while(i<s.size()&&(s[i]==' '||s[i]=='\t'||s[i]=='\r'||s[i]=='\n'))++i;}
    bool take(char c){ws();if(i<s.size()&&s[i]==c){++i;return true;}return false;}
    void need(char c){if(!take(c))fail();}
    unsigned hex4(){unsigned v=0;for(int k=0;k<4;++k){if(i==s.size())fail();const char c=s[i++];v<<=4;
        if(c>='0'&&c<='9')v|=c-'0';else if(c>='a'&&c<='f')v|=c-'a'+10;else if(c>='A'&&c<='F')v|=c-'A'+10;else fail();}return v;}
    std::string string(){
        need('"');std::string out;
        while(i<s.size()){
            const auto c=static_cast<unsigned char>(s[i++]);if(c=='"')return out;if(c<32)fail();
            if(c!='\\'){out+=char(c);continue;}if(i==s.size())fail();const auto escape=s[i++];
            if(escape=='"'||escape=='\\'||escape=='/')out+=escape;
            else if(escape=='b')out+='\b';else if(escape=='f')out+='\f';else if(escape=='n')out+='\n';else if(escape=='r')out+='\r';else if(escape=='t')out+='\t';
            else if(escape=='u'){
                auto cp=hex4();if(cp>=0xd800&&cp<=0xdbff&&s.compare(i,2,"\\u")==0){const auto pos=i;i+=2;const auto tail=hex4();
                    if(tail>=0xdc00&&tail<=0xdfff)cp=0x10000+((cp-0xd800)<<10)+(tail-0xdc00);else i=pos;}
                utf8(out,cp);
            }else fail();
        }fail();
    }
    Value value(unsigned depth=0){
        if(depth>512)fail();ws();if(i==s.size())fail();Value out;
        if(s[i]=='"'){out.kind='s';out.text=string();return out;}
        if(take('{')){out.kind='o';if(take('}'))return out;do{auto key=string();need(':');auto v=value(depth+1);
            auto p=std::find_if(out.object.begin(),out.object.end(),[&](const auto& entry){return entry.first==key;});
            if(p==out.object.end())out.object.emplace_back(std::move(key),std::move(v));else p->second=std::move(v);
            if(take('}'))return out;
        }while(take(','));fail();}
        if(take('[')){out.kind='a';if(take(']'))return out;do{value(depth+1);if(take(']'))return out;}while(take(','));fail();}
        for(const auto* word:{"true","false","null","NaN","Infinity","-Infinity"}){
            const std::string token=word;if(s.compare(i,token.size(),token)==0){i+=token.size();out.kind=token=="null"?'n':token=="true"||token=="false"?'b':'d';out.text=token;return out;}}
        const auto begin=i;if(s[i]=='-')++i;if(i==s.size())fail();
        if(s[i]=='0')++i;else{if(s[i]<'1'||s[i]>'9')fail();while(i<s.size()&&s[i]>='0'&&s[i]<='9')++i;}
        if(i<s.size()&&s[i]=='.'){++i;const auto start=i;while(i<s.size()&&s[i]>='0'&&s[i]<='9')++i;if(i==start)fail();}
        if(i<s.size()&&(s[i]=='e'||s[i]=='E')){++i;if(i<s.size()&&(s[i]=='+'||s[i]=='-'))++i;const auto start=i;while(i<s.size()&&s[i]>='0'&&s[i]<='9')++i;if(i==start)fail();}
        out.kind='d';out.text=s.substr(begin,i-begin);return out;
    }
};
AuditInteger integer(const Value& v){
    if(v.kind=='b')return AuditInteger(v.text=="true"?1:0);
    if(v.kind=='s')return AuditInteger::decimal(v.text);
    if(v.kind!='d')throw std::invalid_argument("baseline value is not coercible to int");
    if(v.text.find_first_of(".eE")==v.text.npos)return AuditInteger::decimal(v.text);
    char* end=nullptr;const auto x=std::strtod(v.text.c_str(),&end);
    if(end!=v.text.c_str()+v.text.size()||!std::isfinite(x))throw std::invalid_argument("nonfinite baseline count");
    std::ostringstream out;out.imbue(std::locale::classic());out<<std::fixed<<std::setprecision(0)<<std::trunc(x);
    return AuditInteger::decimal(out.str());
}
} // namespace

std::optional<AuditCounts> load_counts(const std::filesystem::path& path,const std::string& key,bool missing_key_empty){
    try{
        auto text=model_checks::read(path);
        if(verification::replace_invalid_utf8(text)!=text)throw std::invalid_argument("invalid baseline UTF-8");
        Reader reader{text};auto root=reader.value();reader.ws();if(reader.i!=text.size()||root.kind!='o')throw std::invalid_argument("invalid baseline root");
        const auto p=std::find_if(root.object.begin(),root.object.end(),[&](const auto& item){return item.first==key;});
        if(p==root.object.end()){if(missing_key_empty)return AuditCounts{};return std::nullopt;}
        if(p->second.kind!='o')return std::nullopt;
        AuditCounts out;for(const auto& [name,v]:p->second.object)out[name]=integer(v);return out;
    }catch(const std::exception&){return std::nullopt;}
}
std::string json_quote(const std::string& text){
    static constexpr char hex[]="0123456789abcdef";
    std::string out="\"";
    auto escape=[&](std::uint32_t cp){out+="\\u";for(int shift:{12,8,4,0})out+=hex[(cp>>shift)&15];};
    for(const auto& [cp,bytes]:verification::utf8(text)){
        if(cp=='"'||cp=='\\'){out+='\\';out+=char(cp);}
        else if(cp=='\b')out+="\\b";else if(cp=='\f')out+="\\f";else if(cp=='\n')out+="\\n";else if(cp=='\r')out+="\\r";else if(cp=='\t')out+="\\t";
        else if(cp<32||cp>=127){if(cp<=0xffff)escape(cp);else{const auto x=cp-0x10000;escape(0xd800+(x>>10));escape(0xdc00+(x&1023));}}
        else out+=bytes;
    }return out+'"';
}
} // namespace schgen::audit_detail

namespace schgen {
std::optional<AuditCounts> load_fallback_baseline(const std::filesystem::path& p){return audit_detail::load_counts(p,"counts",false);}
AuditCounts load_quantize_baseline(const std::filesystem::path& p){return audit_detail::load_counts(p,"allowed",true).value_or(AuditCounts{});}
std::string fallback_baseline_text(const AuditCounts& counts){
    using audit_detail::json_quote;
    std::string out="{\n \"counts\": {";bool first=true;
    for(const auto& [name,value]:counts){out+=first?"\n":",\n";first=false;out+="  "+json_quote(name)+": "+value.str();}
    if(!counts.empty())out+="\n ";
    out+="},\n \"note\": "+json_quote("fallback ratchet ceilings — a build whose count EXCEEDS its ceiling FAILS; ceilings only ever DECREASE (pinned from a measured build, reviewed in git). A name absent here is allowed zero firings.")+"\n}\n";return out;
}
FallbackAuditResult check_fallback_ratchet(const AuditCounts& census,const std::filesystem::path& path){
    return check_fallback_ratchet(census,path,path);
}
FallbackAuditResult check_fallback_ratchet(const AuditCounts& census,const std::filesystem::path& path,
                                         const std::filesystem::path& output){
    const auto baseline=load_fallback_baseline(path);FallbackAuditResult r;r.n_names=census.size();
    for(const auto& [name,v]:census){(void)name;if(v.nonzero())++r.n_fired;}
    if(!baseline){model_checks::publish(output,fallback_baseline_text(census));r.pinned=true;return r;}
    for(const auto& [name,count]:census){const auto found=baseline->find(name);const AuditInteger ceiling=found==baseline->end()?AuditInteger{}:found->second;
        if(ceiling<count)r.regressions.push_back(name+": fired "+count.str()+" > baseline "+ceiling.str()+" — a degraded path bound more often than the committed ceiling");}
    r.ok=r.regressions.empty();if(r.ok){auto lowered=*baseline;
        for(auto& [name,count]:lowered){const auto p=census.find(name);count=std::min(count,p==census.end()?AuditInteger{}:p->second);}
        if(lowered!=*baseline||output.lexically_normal()!=path.lexically_normal())
            model_checks::publish(output,fallback_baseline_text(lowered));
    }return r;
}
std::string FallbackAuditResult::summary()const{
    std::vector<std::string> lines={"FALLBACK RATCHET: "+std::string(ok?"PASS":"FAIL")+" — "+std::to_string(n_names)+" registered paths, "+std::to_string(n_fired)+" firing"+(pinned?" (baseline PINNED this build)":"")};
    for(const auto& r:regressions)lines.push_back("  REGRESSION: "+r);return model_checks::join(lines);
}
} // namespace schgen
