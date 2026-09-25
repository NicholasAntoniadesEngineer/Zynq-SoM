#include "manufacturing_assembly_internal.hpp"

namespace schgen {
using namespace assembly_detail;
namespace {
std::string side_count(const PcbModel& m,const Indices& ids) {
    std::size_t top=0;for(auto i:ids)top+=m.insts.at(i).side=="top";
    return std::to_string(ids.size())+" parts ("+std::to_string(top)+" top / "+std::to_string(ids.size()-top)+" bottom)";
}
void table(std::ostringstream& o,const PcbModel& m,const Indices& ids,bool joint=false) {
    o<<(joint?"| ref | value | package | sheet | joint |\n|---|---|---|---|---|\n":"| ref | value | package | sheet |\n|---|---|---|---|\n");
    for(auto n:ids){const auto& i=m.insts.at(n);auto colon=i.footprint.find(':');auto pkg=colon==i.footprint.npos?i.footprint:i.footprint.substr(colon+1);if(pkg.empty())pkg=i.footprint;
        o<<"| "<<i.ref<<" | "<<i.value<<" | "<<pkg<<" | "<<i.sheet<<" |";
        if(joint)o<<' '<<(assembly_joint(footprint(i))=="tht"?"THT":"SMD")<<" |";o<<'\n';
    }
}
bool truth(const JsonNode& n) {
    switch(n.kind){case JsonKind::Null:return false;case JsonKind::Bool:return n.bool_value;case JsonKind::Number:return n.number_value!=0;case JsonKind::String:return !n.string_value.empty();case JsonKind::Array:return !n.array_value.empty();case JsonKind::Object:return !n.object_value.empty();}return false;
}
std::string transport_text(const JsonNode& n) {
    if(n.kind==JsonKind::String)return n.string_value;
    if(n.kind==JsonKind::Bool)return n.bool_value?"True":"False";
    if(n.kind==JsonKind::Null)return "None";
    if(n.kind==JsonKind::Number)return fixed(n.number_value,0);
    return dump(n);
}
std::string relative(const std::string& path,const std::filesystem::path& root) {
    // Path.relative_to is lexical, so do not resolve symlinks here.
    const auto p=std::filesystem::path(path).lexically_normal();const auto r=root.lexically_normal();
    auto pi=p.begin(),ri=r.begin();for(;ri!=r.end();++pi,++ri)if(pi==p.end()||*pi!=*ri)throw ProjectError(path+" is not in the subpath of "+root.string());
    std::filesystem::path out;for(;pi!=p.end();++pi)out/=*pi;return out.empty()?".":out.generic_string();
}
}
std::string render_assembly_markdown(const PcbModel& m,const AssemblyPlan& plan,const std::string& name) {
    partition(m,plan.steps,"step");partition(m,plan.phases,"phase");auto ids=parts(m);std::size_t top=0;for(auto i:ids)top+=m.insts[i].side=="top";
    std::ostringstream o;o.imbue(std::locale::classic());
    o<<"# Assembly order — "<<name<<"\n\nBoard "<<general(m.board_w)<<" x "<<general(m.board_h)<<" mm. "<<ids.size()<<" placed parts ("<<top<<" top / "<<ids.size()-top<<" bottom); "<<m.insts.size()-ids.size()<<" fiducials are bare-copper marks, excluded from every phase and step.\nSection A is the staged hand-assembly + bring-up order; section B is the PCBA process order. Every part appears in exactly one phase and exactly one step.\n\n## A. Incremental bring-up order\n\n| phase | section | parts | checkpoint |\n|---|---|---|---|\n";
    for(const auto& p:plan.phases)o<<"| "<<p.n<<" | "<<p.title<<" | "<<p.insts.size()<<" | "<<(p.checkpoints.empty()?"—":join(p.checkpoints,"; "))<<" |\n";o<<'\n';
    for(const auto& p:plan.phases){
        o<<"### Phase "<<p.n<<" — "<<p.title<<"\n\n![phase "<<p.n<<"](../renders/assembly/"<<phase_filename(p)<<")\n\n";
        if(!p.lead.empty())o<<p.lead<<"\n\n";
        if(!p.insts.empty()){o<<side_count(m,p.insts)<<"\n\n";table(o,m,p.insts);o<<'\n';}
        for(const auto& c:p.checkpoints)o<<"CHECKPOINT: "<<c<<'\n';if(!p.checkpoints.empty())o<<'\n';
    }
    o<<"## B. Production process order\n\n";
    for(const auto& s:plan.steps){
        o<<"### Step "<<s.n<<" — "<<s.title<<"\n\n![step "<<s.n<<"](../renders/assembly/"<<step_filename(s)<<")\n\n";
        if(s.insts.empty()){o<<"No parts in this step on this board.\n\n";continue;}
        if(s.n==3)o<<"Sorted short-to-tall by courtyard area (height proxy — no measured part heights in-tree).\n\n";
        o<<side_count(m,s.insts)<<"\n\n";table(o,m,s.insts,s.n==4);o<<'\n';
        for(const auto& n:s.notes)o<<"NOTES: "<<n<<'\n';if(!s.notes.empty())o<<'\n';
    }return o.str();
}
std::pair<bool,std::string> assembly_verdict(const JsonNode& result,const std::filesystem::path& repository_root) {
    if(!truth(result))return {false,"ASSEMBLY: FAIL — generation step did not run (emit.generate must call assembly.generate)"};
    if(result.kind!=JsonKind::Object)throw ProjectError("assembly result must be an object");
    if(const auto e=object_field(result,"error");e&&truth(*e))return {false,"ASSEMBLY: FAIL — "+transport_text(*e)};
    bool incomplete=false;for(const auto& k:{"md","png_dir","n_steps","n_phases","n_parts","n_pngs"}){auto p=object_field(result,k);incomplete|=!p||p->kind==JsonKind::Null;}
    auto ok=object_field(result,"ok");if(incomplete||!ok||!truth(*ok)){std::vector<std::string> keys;for(const auto& p:result.object_value)keys.push_back(p.first);std::sort(keys.begin(),keys.end());return {false,"ASSEMBLY: FAIL — incomplete result "+repr(keys)};}
    const auto get=[&](const std::string& k){return transport_text(*object_field(result,k));};
    return {true,"ASSEMBLY: "+get("n_steps")+" steps + "+get("n_phases")+" phases, "+get("n_parts")+" parts -> "+relative(get("md"),repository_root)+" + "+relative(get("png_dir"),repository_root)+" ("+get("n_pngs")+" PNGs)"};
}
} // namespace schgen
