#pragma once
#include "schgen/selftest_full.hpp"
#include "verification_internal.hpp"
#include "pcb_checks_internal.hpp"

namespace schgen::selftesting {
using namespace model_checks;
namespace fs=std::filesystem;
inline std::string first(const std::vector<std::string>& x,const std::string& fallback){return x.empty()?fallback:x.front();}
inline std::string first_line(const std::string& x){return x.substr(0,x.find('\n'));}
inline std::string shorten(const std::string& s,std::size_t n){std::string out;for(const auto& [cp,bytes]:verification::utf8(s)){(void)cp;if(!n--)break;out+=bytes;}return out;}
inline std::vector<std::string> lines(const std::string& s){std::vector<std::string> out;std::istringstream in(s);std::string line;while(std::getline(in,line))out.push_back(line);return out;}
inline std::string pf(double x){return pcb_checks::pyfloat(x);}
inline std::string pin(const CircuitPinRefIr& p){return p.ref+"."+p.pin;}
inline void safe_name(const std::string& name){if(name.empty()||name=="."||name==".."||name.find('/')!=name.npos||name.find('\\')!=name.npos||name.find('\0')!=name.npos)throw std::invalid_argument("selftest: unsafe output name");}
inline SchematicDesign design(const SchematicPlacedPage& p){
    SchematicDesign d;d.circuit=p.circuit;d.parts=p.placement.parts;d.powers=p.placement.powers;
    d.hlabels=p.placement.hlabels;d.llabels=p.placement.llabels;d.no_connects=p.placement.no_connects;d.paper=p.placement.paper;
    for(const auto& s:p.routed.segs)d.wires.push_back({s.x0,s.y0,s.x1,s.y1});
    for(const auto& j:p.routed.junctions)d.junctions.push_back({j.x,j.y});return d;
}
inline bool tag(const Sexpr& s,const std::string& name){return pcb_checks::tag(s,name);}
inline Sexpr sym(const std::string& s){return {Sexpr::Sym{s}};}
inline Sexpr node(const std::string& tag,std::initializer_list<Sexpr> xs){SexprList a{sym(tag)};a.insert(a.end(),xs.begin(),xs.end());return {std::move(a)};}
inline SexprList& sl(Sexpr& s){return std::get<SexprList>(s.v);}
inline const SexprList& sl(const Sexpr& s){return std::get<SexprList>(s.v);}
inline const Sexpr* child(const Sexpr& s,const std::string& name){for(const auto& n:sl(s))if(tag(n,name))return &n;return nullptr;}
inline double number_at(const Sexpr& s,std::size_t i){return std::get<double>(sl(s).at(i).v);}
inline std::string atom(const Sexpr& s){return pcb_checks::atom(s);}
inline double length(const VisualSegment& s){return std::abs(s.x1-s.x0)+std::abs(s.y1-s.y0);}
inline SheetGeometry rebuild_geo(const SelftestBuilt& b){SheetGeometry g;g.boxes=b.page.geometry.boxes;for(const auto& s:b.page.routed.segs)g.wires.push_back({s.x0,s.y0,s.x1,s.y1,s.net});return g;}
JsonNode circuit_json(const CircuitSheetIr&);
std::string json_text(const JsonNode&);
std::string drift_diff(const std::string&,const std::string&,const std::string&,const std::string&);
} // namespace schgen::selftesting
