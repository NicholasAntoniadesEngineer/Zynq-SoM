#include "compose_repair_internal.hpp"

namespace schgen {
namespace compose_detail {
std::string quote(const std::string &s) {
    const char *hex="0123456789abcdef";
    std::string out="\"";
    auto u16=[&](unsigned cp){out+="\\u";for(int shift:{12,8,4,0})out+=hex[(cp>>shift)&15];};
    for(auto cp:document_detail::codepoints(s)) {
        if(cp=='"'||cp=='\\'){out+='\\';out+=static_cast<char>(cp);}
        else if(cp=='\n')out+="\\n";
        else if(cp=='\r')out+="\\r";
        else if(cp=='\t')out+="\\t";
        else if(cp=='\b')out+="\\b";
        else if(cp=='\f')out+="\\f";
        else if(cp<32||cp>=127){if(cp<=0xffff)u16(cp);else {cp-=0x10000;u16(0xd800+(cp>>10));u16(0xdc00+(cp&1023));}}
        else out+=static_cast<char>(cp);
    }
    return out+'"';
}
std::string repr(const std::string &s) {
    const char q=s.find('\'')!=s.npos&&s.find('"')==s.npos?'"':'\'';
    std::string out(1,q);
    const char *hex="0123456789abcdef";
    // Preserve printable UTF-8; Python repr escapes control/whitespace codepoints.
    std::size_t i=0;
    for(auto cp:document_detail::codepoints(s)) {
        const auto begin=i; ++i;while(i<s.size()&&(static_cast<unsigned char>(s[i])&0xc0)==0x80)++i;
        if(cp==static_cast<unsigned>(q)||cp=='\\'){out+='\\';out+=static_cast<char>(cp);}
        else if(cp=='\n')out+="\\n";
        else if(cp=='\r')out+="\\r";
        else if(cp=='\t')out+="\\t";
        else if(cp<32||(cp>=127&&cp<=159)||(cp!=32&&document_detail::space(cp))){
            out+=cp<=255?"\\x":cp<=65535?"\\u":"\\U";
            for(int shift=cp<=255?4:cp<=65535?12:28;shift>=0;shift-=4)out+=hex[(cp>>shift)&15];
        } else out+=s.substr(begin,i-begin);
    }
    return out+q;
}
std::string scalar(const ComposeDocument &d,const JsonNode &n,const std::string &p) {
    if(n.kind==JsonKind::Null)return "None";
    if(n.kind==JsonKind::Bool)return n.bool_value?"True":"False";
    if(n.kind==JsonKind::String)return n.string_value;
    const auto value=jnum(n);
    if(d.float_paths.count(p)||std::trunc(value)!=value)return pyfloat(value);
    auto it=d.integer_tokens.find(p);
    if(it!=d.integer_tokens.end()&&std::stod(it->second)==value)return value==0?"0":it->second;
    return value==0?"0":fmt(value,0,true);
}
namespace {
std::string dump(const ComposeDocument &d,const JsonNode &n,const std::string &p,int indent,bool sorted,int level) {
    if(n.kind==JsonKind::Null)return "null";
    if(n.kind==JsonKind::Bool)return n.bool_value?"true":"false";
    if(n.kind==JsonKind::String)return quote(n.string_value);
    if(n.kind==JsonKind::Number)return scalar(d,n,p);
    std::vector<std::pair<std::string,const JsonNode *>> rows;
    if(n.kind==JsonKind::Object)for(const auto &[k,v]:n.object_value)rows.emplace_back(k,&v);
    if(sorted)std::sort(rows.begin(),rows.end(),[](const auto &a,const auto &b){return a.first<b.first;});
    const bool object=n.kind==JsonKind::Object;
    const auto size=object?rows.size():kind(n,JsonKind::Array).array_value.size();
    if(!size)return object?"{}":"[]";
    std::string out=object?"{\n":"[\n";
    for(std::size_t k=0;k<size;++k) {
        if(k)out+=",\n";
        const auto path=p+"/"+(object?pointer(rows[k].first):std::to_string(k));
        out+=std::string((level+1)*indent,' ');
        if(object)out+=quote(rows[k].first)+": ";
        out+=dump(d,object?*rows[k].second:n.array_value[k],path,indent,sorted,level+1);
    }
    return out+"\n"+std::string(level*indent,' ')+(object?"}":"]");
}
}
} // namespace compose_detail
using namespace compose_detail;
ComposeDocument parse_compose_document(std::string_view bytes,const std::string &source) {
    ComposeDocument d;d.data=parse_json_text(bytes,source);
    // Shared parser validates the document; this lexical pass retains only
    // integer tokens and float type information lost by its double-only tree.
    std::vector<std::string> tokens;
    for(std::size_t i=0;i<bytes.size();) {
        char c=bytes[i++];
        if(c=='"'){while(i<bytes.size()){c=bytes[i++];if(c=='\\')++i;else if(c=='"')break;}}
        else if(c=='-'||(c>='0'&&c<='9')) {
            const auto start=i-1;
            while(i<bytes.size()&&std::string("0123456789.eE+-").find(bytes[i])!=std::string::npos)++i;
            tokens.emplace_back(bytes.substr(start,i-start));
        }
    }
    std::size_t pos=0;
    std::function<void(const JsonNode &,const std::string &)> walk=[&](const JsonNode &n,const std::string &p){
        if(n.kind==JsonKind::Number){
            const auto &t=tokens.at(pos++);
            if(t.find_first_of(".eE")!=t.npos)d.float_paths.insert(p);else d.integer_tokens[p]=t;
        } else if(n.kind==JsonKind::Array)for(std::size_t k=0;k<n.array_value.size();++k)walk(n.array_value[k],p+"/"+std::to_string(k));
        else if(n.kind==JsonKind::Object)for(const auto &[k,v]:n.object_value)walk(v,p+"/"+pointer(k));
    };
    walk(d.data,"");
    if(pos!=tokens.size())throw std::invalid_argument("compose: number token mismatch");
    return d;
}
std::string render_compose_json(const ComposeDocument &d,int indent,bool sorted) {
    if(indent<0||indent>16)throw std::invalid_argument("compose: invalid JSON indentation");
    return dump(d,d.data,"",indent,sorted,0)+"\n";
}
ComposeLedgerDocuments append_compose_ledger(const ComposeDocument &history,const ComposeDocument &ledger,const std::string &step) {
    auto d=history;kind(d.data,JsonKind::Array);
    auto prefix="/"+std::to_string(d.data.array_value.size())+"/ledger";
    d.data.array_value.push_back(jo({{"step",j(step)},{"ledger",ledger.data}}));
    for(const auto &p:ledger.float_paths)d.float_paths.insert(prefix+p);
    for(const auto &[p,v]:ledger.integer_tokens)d.integer_tokens[prefix+p]=v;
    std::string md="# compose ledger (T1) — driver-written measurement time-series\n\n";
    for(std::size_t k=0;k<d.data.array_value.size();++k) {
        const auto &h=d.data.array_value[k],&led=required(h,"ledger"),&b=required(led,"board"),&agg=required(led,"aggregate_hard_margin");
        auto base="/"+std::to_string(k)+"/ledger";
        const auto &triggers=required(led,"repair_triggers").array_value;
        md+="## "+str(h,"step")+"\n- board "+fmt(jnum(required(b,"w")))+" x "+fmt(jnum(required(b,"h")))+" = "+scalar(d,required(b,"area_mm2"),base+"/board/area_mm2")+" mm^2\n";
        md+="- hard margin sum "+scalar(d,required(agg,"sum"),base+"/aggregate_hard_margin/sum")+" / min "+scalar(d,required(agg,"min"),base+"/aggregate_hard_margin/min")+" mm\n";
        md+="- LAW-5 slack "+scalar(d,required(required(led,"law5"),"slack_pct"),base+"/law5/slack_pct")+"%\n- repair triggers: "+std::to_string(triggers.size())+"\n";
        for(const auto &t:triggers)md+="  - "+jstr(t)+"\n";
        if(k+1<d.data.array_value.size())md+='\n';
    }
    return {render_compose_json(d,1,true),md};
}
void write_compose_ledger(const ComposeDocument &ledger,const std::string &step,const std::filesystem::path &jp,const std::filesystem::path &mp) {
    auto h=std::filesystem::exists(jp)?parse_compose_document(read(jp),jp.string()):parse_compose_document("[]");
    const auto docs=append_compose_ledger(h,ledger,step);
    if(!jp.parent_path().empty())std::filesystem::create_directories(jp.parent_path());
    publish(jp,docs.json);publish(mp,docs.markdown);
}
} // namespace schgen
