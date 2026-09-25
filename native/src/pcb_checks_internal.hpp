#pragma once
#include "schgen/pcb_checks.hpp"
#include "schgen/occupancy.hpp"
#include "schgen/pack.hpp"
#include "schgen/turn.hpp"
#include <algorithm>
#include <charconv>
#include <cmath>
#include <filesystem>
#include <limits>
#include <regex>
#include <sstream>
#include <stdexcept>

namespace schgen::pcb_checks {
inline bool starts(const std::string& s,const std::string& p){return s.compare(0,p.size(),p)==0;}
inline bool ends(const std::string& s,const std::string& p){return s.size()>=p.size()&&s.compare(s.size()-p.size(),p.size(),p)==0;}
inline std::string fmt(double x,int precision=6,bool fixed=false){
    char b[768];auto r=std::to_chars(b,b+sizeof b,x,fixed?std::chars_format::fixed:std::chars_format::general,precision);
    if(r.ec!=std::errc{})throw std::runtime_error("PCB numeric formatting out of range");return {b,r.ptr};
}
inline std::string g(double x){return fmt(x);}
inline std::string f(double x,int digits){return fmt(x,digits,true);}
inline std::string sign(double x,int digits){return (std::signbit(x)?"":"+")+f(x,digits);}
inline std::string pyfloat(double x){
    if(!std::isfinite(x))return std::isnan(x)?"nan":std::signbit(x)?"-inf":"inf";
    char b[768];auto r=std::to_chars(b,b+sizeof b,std::abs(x),std::chars_format::scientific);
    if(r.ec!=std::errc{})throw std::runtime_error("PCB float out of range");
    std::string s(b,r.ptr),sign=std::signbit(x)?"-":"";auto e=s.find('e');int exponent=std::stoi(s.substr(e+1));
    if(exponent< -4||exponent>=16)return sign+s;
    std::string digits=s.substr(0,e);auto dot=digits.find('.');if(dot!=digits.npos)digits.erase(dot,1);int point=exponent+1;
    if(point<=0)return sign+"0."+std::string(-point,'0')+digits;
    if(point>=static_cast<int>(digits.size()))return sign+digits+std::string(point-digits.size(),'0')+".0";
    digits.insert(static_cast<std::size_t>(point),".");return sign+digits;
}
inline std::string pad(std::string s,std::size_t width,bool right=false){std::size_t n=0;for(unsigned char c:s)if((c&0xc0)!=0x80)++n;if(n>=width)return s;return right?std::string(width-n,' ')+s:s+std::string(width-n,' ');}
inline std::string join(const std::vector<std::string>& a,const std::string& sep="\n"){std::string s;for(const auto& x:a){if(&x!=&a.front())s+=sep;s+=x;}return s;}
inline std::string verdict(bool ok){return ok?"PASS":"FAIL";}
inline std::string repr(const std::string& s){char q=s.find('\'')!=s.npos&&s.find('"')==s.npos?'"':'\'';std::string r(1,q);for(char c:s){if(c==q||c=='\\')r+='\\';if(c=='\n')r+="\\n";else if(c=='\t')r+="\\t";else if(c=='\r')r+="\\r";else r+=c;}return r+q;}
inline std::string list_repr(const std::vector<std::string>& a){std::vector<std::string> q;for(const auto& x:a)q.push_back(repr(x));return "["+join(q,", ")+"]";}
inline const SexprList* list(const Sexpr& n){return std::get_if<SexprList>(&n.v);}
inline std::string atom(const Sexpr& n){if(auto s=std::get_if<std::string>(&n.v))return *s;if(auto s=std::get_if<Sexpr::Sym>(&n.v))return s->name;if(auto d=std::get_if<double>(&n.v))return g(*d);if(auto b=std::get_if<bool>(&n.v))return *b?"True":"False";throw std::runtime_error("PCB atom required");}
inline bool tag(const Sexpr& n,const std::string& s){auto l=list(n);return l&&!l->empty()&&atom((*l)[0])==s;}
inline const SexprList* child(const Sexpr& n,const std::string& s){if(auto l=list(n))for(const auto& v:*l)if(tag(v,s))return list(v);return nullptr;}
inline double number(const SexprList& n,std::size_t i){if(i>=n.size()||!std::holds_alternative<double>(n[i].v))throw std::runtime_error("PCB numeric coordinate required");return std::get<double>(n[i].v);}
inline std::pair<double,double> xy(const SexprList& n){return {number(n,1),number(n,2)};}
inline std::string pair_repr(std::pair<int,int> p){return "("+std::to_string(p.first)+", "+std::to_string(p.second)+")";}
inline std::string box_repr(Box4 b){return "("+pyfloat(b.x0)+", "+pyfloat(b.y0)+", "+pyfloat(b.x1)+", "+pyfloat(b.y1)+")";}
inline Box4 translated(Box4 b,double x,double y){return {b.x0+x,b.y0+y,b.x1+x,b.y1+y};}
inline Box4 united(Box4 a,Box4 b){return {std::min(a.x0,b.x0),std::min(a.y0,b.y0),std::max(a.x1,b.x1),std::max(a.y1,b.y1)};}
inline bool touches(Box4 a,Box4 b){return a.x0<=b.x1+1e-9&&b.x0<=a.x1+1e-9&&a.y0<=b.y1+1e-9&&b.y0<=a.y1+1e-9;}
inline bool contains(Box4 b,double x,double y){return b.x0<=x&&x<=b.x1&&b.y0<=y&&y<=b.y1;}
inline std::string conn_ref(const std::string& s){return s=="som_j1"?"J1":s=="som_j2"?"J2":s=="som_j3"?"J3":"";}
inline std::map<std::string,std::size_t> connectors(const PcbCheckModel& m){std::map<std::string,std::size_t> out;for(std::size_t i=0;i<m.insts.size();++i){auto r=conn_ref(m.insts[i].sheet);if(!r.empty())out[r]=i;}return out;}
inline const std::map<std::string,std::string>& mating_faces(){static const std::map<std::string,std::string> v={{"TYPE-C-31-M-12","+Y"},{"HDMI-019S","+Y"},{"AFC07-S40FCA-00","+Y"},{"KH-5224-8P8C-D","+Y"},{"TF-01A","+Y"},{"SFW15R-1STE1LF","+Y"},{"ZX-SH1.0-4PWT","+Y"},{"DS1024-2x6R2","+Y"},{"XT60PW-M","+X"}};return v;}
inline std::string mpn(const PcbCheckInstance& i){if(mating_faces().count(i.value))return i.value;auto s=i.footprint.substr(i.footprint.find_last_of(':')+1);return mating_faces().count(s)?s:"";}
inline std::string net_name(const PcbCheckInstance& i,const std::string& pad){auto p=i.pad_nets.find(pad);return p==i.pad_nets.end()?"":p->second.second;}
inline const JsonNode& required(const JsonNode& n,const std::string& key){auto p=object_field(n,key);if(!p)throw std::runtime_error("PCB input missing "+key);return *p;}
inline const JsonNode& kind(const JsonNode& n,JsonKind k){if(n.kind!=k)throw std::runtime_error("PCB input has wrong JSON type");return n;}
inline int integer(const JsonNode& n){double v=kind(n,JsonKind::Number).number_value;if(!std::isfinite(v)||std::trunc(v)!=v||v<std::numeric_limits<int>::min()||v>std::numeric_limits<int>::max())throw std::runtime_error("PCB integer out of range");return static_cast<int>(v);}
inline double jnum(const JsonNode& n){double v=kind(n,JsonKind::Number).number_value;if(!std::isfinite(v))throw std::runtime_error("PCB nonfinite number");return v;}
inline std::string jstr(const JsonNode& n){return kind(n,JsonKind::String).string_value;}
} // namespace schgen::pcb_checks
