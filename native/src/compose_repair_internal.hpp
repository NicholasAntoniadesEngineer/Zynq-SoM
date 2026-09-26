#pragma once
#include "schgen/compose_repair.hpp"
#include "pcb_emit_internal.hpp"
#include "gallery_diagram_internal.hpp"
#include <fstream>

namespace schgen::compose_detail {
using pcb_emission::j;
using pcb_emission::jb;
using pcb_emission::ja;
using pcb_emission::jo;
using pcb_emission::set;
using pcb_emission::required;
using pcb_emission::kind;
using pcb_emission::jnum;
using pcb_emission::jstr;
using pcb_emission::jbool;
using pcb_emission::pyfloat;
using pcb_emission::fmt;
using document_detail::read;
inline std::string pointer(const std::string &s) {
    std::string out;
    for (char c : s) out += c == '~' ? "~0" : c == '/' ? "~1" : std::string(1,c);
    return out;
}
inline JsonNode &field(JsonNode &n, const std::string &k) {
    kind(n,JsonKind::Object);
    for (auto &[key,v] : n.object_value) if(key==k) return v;
    throw std::invalid_argument("compose: missing " + k);
}
inline const JsonNode &opt(const JsonNode &n, const std::string &k) {
    static const JsonNode absent;
    auto p=object_field(n,k); return p?*p:absent;
}
inline std::string str(const JsonNode &n,const std::string &k) { return jstr(required(n,k)); }
inline bool truth(const JsonNode &v) {
    switch(v.kind) {
    case JsonKind::Null:return false;
    case JsonKind::Bool:return v.bool_value;
    case JsonKind::Number:return v.number_value!=0;
    case JsonKind::String:return !v.string_value.empty();
    case JsonKind::Array:return !v.array_value.empty();
    case JsonKind::Object:return !v.object_value.empty();
    } return false;
}
inline JsonNode strings(const std::vector<std::string> &v) {
    auto a=ja(); for(const auto &s:v)a.array_value.push_back(j(s));return a;
}
inline JsonNode sorted_strings(std::vector<std::string> v) {std::sort(v.begin(),v.end());return strings(v);}
inline void floats(ComposeDocument &d,const JsonNode &n,const std::string &p="") {
    if(n.kind==JsonKind::Number)d.float_paths.insert(p);
    else if(n.kind==JsonKind::Array)for(std::size_t i=0;i<n.array_value.size();++i)floats(d,n.array_value[i],p+"/"+std::to_string(i));
    else if(n.kind==JsonKind::Object)for(const auto &[k,v]:n.object_value)floats(d,v,p+"/"+pointer(k));
}
inline void erase_metadata(ComposeDocument &d,const std::string &p) {
    for(auto i=d.float_paths.begin();i!=d.float_paths.end();)if(*i==p||i->compare(0,p.size()+1,p+"/")==0)i=d.float_paths.erase(i);else ++i;
    for(auto i=d.integer_tokens.begin();i!=d.integer_tokens.end();)if(i->first==p||i->first.compare(0,p.size()+1,p+"/")==0)i=d.integer_tokens.erase(i);else ++i;
}
std::string quote(const std::string &);
std::string repr(const std::string &);
std::string scalar(const ComposeDocument &,const JsonNode &,const std::string &);
inline ComposeTermKey key(const JsonNode &t) {return {str(t,"kind"),str(t,"subject"),str(t,"target")};}
inline ComposeTermKey key(const FloorplanTerm &t) {return {t.kind,t.subject,t.target_raw};}
inline std::string key_repr(const ComposeTermKey &k) {return "("+repr(std::get<0>(k))+", "+repr(std::get<1>(k))+", "+repr(std::get<2>(k))+")";}
inline std::string list_repr(const std::vector<std::string> &v) {
    std::vector<std::string> a;for(const auto &s:v)a.push_back(repr(s));return "["+document_detail::join(a,", ")+"]";
}
inline std::map<std::string,double> floors() {return {{"flow_hop",10.},{"near_max",2.},{"far_min",5.},{"facing",15.}};}
inline void publish(const std::filesystem::path &p,const std::string &s) {
    write_atomic_file(p,{s.begin(),s.end()});
}
} // namespace schgen::compose_detail
