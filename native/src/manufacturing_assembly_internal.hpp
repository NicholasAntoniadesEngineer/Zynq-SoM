#pragma once
#include "schgen/assembly_documents.hpp"
#include "manufacturing_exports_internal.hpp"

namespace schgen::assembly_detail {
using namespace manufacturing_detail;
inline constexpr const char* fiducial = "Fiducial:Fiducial_1mm_Mask2mm";
using Indices = std::vector<std::size_t>;
using Names = std::set<std::string>;
inline bool mechanical(const PcbCheckInstance& i) { return has(i.footprint,"MountingHole"); }
inline bool connector(const PcbCheckInstance& i) { return starts(i.ref,"J"); }
inline std::pair<std::string,std::string> natural(const std::string& ref) {
    static const std::regex re("([A-Za-z]+)([0-9]+)"); std::smatch m;
    if(!std::regex_match(ref,m,re))return {ref,"0"};
    auto n=m[2].str();auto first=n.find_first_not_of('0');n=first==n.npos?"0":n.substr(first);
    return {m[1].str(),n};
}
inline bool ref_less(const std::string& a,const std::string& b) {
    const auto x=natural(a),y=natural(b);
    if(x.first!=y.first)return x.first<y.first;
    return x.second.size()!=y.second.size()?x.second.size()<y.second.size():x.second<y.second;
}
inline void sort_refs(std::vector<std::string>& a) { std::stable_sort(a.begin(),a.end(),ref_less); }
inline void sort_indices(Indices& a,const PcbModel& m) {
    std::stable_sort(a.begin(),a.end(),[&](auto i,auto j){return ref_less(m.insts.at(i).ref,m.insts.at(j).ref);});
}
inline Indices parts(const PcbModel& m) {
    Indices a;for(std::size_t i=0;i<m.insts.size();++i)if(m.insts[i].footprint!=fiducial)a.push_back(i);return a;
}
inline const PcbCheckFootprint& footprint(const PcbCheckInstance& i) {
    if(!i.mod)throw ProjectError(i.ref+": footprint geometry unresolved");return *i.mod;
}
inline std::string stem(const PcbCheckInstance& i) { return std::filesystem::path(footprint(i).source).stem().string(); }
inline std::string step_filename(const AssemblyStep& s) { return "step_"+std::to_string(s.n)+"_"+s.slug+".png"; }
inline std::string phase_filename(const AssemblyPhase& p) {
    auto n=std::to_string(p.n);return std::string("phase_")+(n.size()<2?"0":"")+n+"_"+p.slug+".png";
}
template<class Group> void partition(const PcbModel& m,const std::vector<Group>& groups,const std::string& kind) {
    auto all=parts(m);std::map<std::string,std::size_t> seen;
    for(std::size_t g=0;g<groups.size();++g)for(auto i:groups[g].insts){
        if(i>=m.insts.size())throw ProjectError("assembly member index out of range");
        const auto& ref=m.insts.at(i).ref;auto old=seen.find(ref);
        if(old!=seen.end())throw ProjectError(kind+" partition: "+ref+" appears in "+kind+"s "+std::to_string(old->second+1)+" and "+std::to_string(g+1));
        seen[ref]=g;
    }
    std::vector<std::string> missing;for(auto i:all)if(!seen.count(m.insts[i].ref))missing.push_back(m.insts[i].ref);sort_refs(missing);
    if(!missing.empty()||seen.size()!=all.size()){
        if(missing.size()>8)missing.resize(8);
        throw ProjectError(kind+" partition: "+std::to_string(seen.size())+" assigned != "+std::to_string(all.size())+" parts; missing "+repr(missing));
    }
}
} // namespace schgen::assembly_detail
