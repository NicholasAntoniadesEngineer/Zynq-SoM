#include "compose_repair_internal.hpp"

namespace schgen {
using namespace compose_detail;
bool ComposeSpecEdit::intent() const {
    if(kind==ComposeEditKind::MoveEdgeBlock)return true;
    if(kind==ComposeEditKind::Composite)return std::any_of(edits.begin(),edits.end(),[](const auto &e){return e.intent();});
    return false;
}
std::string ComposeSpecEdit::describe() const {
    switch(kind) {
    case ComposeEditKind::AddPull:return "AddPull "+block+" -> "+to+" w="+fmt(weight)+" face="+face+" exclusive="+(exclusive?"True":"False");
    case ComposeEditKind::SetPullWeight:return "SetPullWeight "+block+" w="+fmt(weight);
    case ComposeEditKind::MoveEdgeBlock:return "MoveEdgeBlock "+name+": "+from_edge+"->"+to_edge;
    case ComposeEditKind::Composite:{std::vector<std::string> a;for(const auto &e:edits)a.push_back(e.describe());return document_detail::join(a," + ");}
    }throw std::invalid_argument("compose: unknown edit");
}
ComposeDocument ComposeSpecEdit::apply(const ComposeDocument &raw) const {
    auto out=raw;
    if(kind==ComposeEditKind::Composite){for(const auto &e:edits)out=e.apply(out);return out;}
    if(kind==ComposeEditKind::MoveEdgeBlock) {
        if(!object_field(out.data,"edges"))set(out.data,"edges",jo());
        auto &edges=field(out.data,"edges");
        if(!object_field(edges,from_edge))throw std::invalid_argument(name+" not on edge "+from_edge);
        auto &src=field(edges,from_edge);compose_detail::kind(src,JsonKind::Array);
        auto it=std::find_if(src.array_value.begin(),src.array_value.end(),[&](const auto &n){return n.kind==JsonKind::String&&n.string_value==name;});
        if(it==src.array_value.end())throw std::invalid_argument(name+" not on edge "+from_edge);
        src.array_value.erase(it);
        if(!object_field(edges,to_edge))set(edges,to_edge,ja());
        auto &dst=field(edges,to_edge);compose_detail::kind(dst,JsonKind::Array);dst.array_value.push_back(j(name));
        return out;
    }
    if(!std::isfinite(weight))throw std::invalid_argument("compose: nonfinite pull weight");
    if(kind==ComposeEditKind::AddPull) {
        if(!object_field(out.data,"interior"))set(out.data,"interior",jo());
        auto &interior=field(out.data,"interior");
        if(!object_field(interior,block))set(interior,block,jo());
        auto &entry=field(interior,block);
        if(object_field(entry,"pull"))throw std::invalid_argument(block+" already carries a pull (one pull per block — use SetPullWeight)");
        set(entry,"pull",jo({{"to",j(to)},{"weight",j(weight)},{"face",j(face)},{"exclusive",jb(exclusive)},{"basis",j(basis)}}));
    } else {
        const auto &entry=opt(opt(out.data,"interior"),block);
        if(!truth(entry)||!object_field(entry,"pull"))throw std::invalid_argument(block+" has no pull to re-weight");
        set(field(field(field(out.data,"interior"),block),"pull"),"weight",j(weight));
    }
    auto path="/interior/"+pointer(block)+"/pull/weight";
    erase_metadata(out,path);out.float_paths.insert(path);
    return out;
}
std::vector<ComposeSpecEdit> parse_compose_allow_intent(const std::vector<std::string> &items) {
    auto strip=[](const std::string &s){
        auto cps=document_detail::codepoints(s);std::size_t left=0,right=cps.size();
        while(left<right&&document_detail::space(cps[left]))++left;
        while(right>left&&document_detail::space(cps[right-1]))--right;
        std::vector<std::size_t> offsets;for(std::size_t i=0;i<s.size();++i)if((static_cast<unsigned char>(s[i])&0xc0)!=0x80)offsets.push_back(i);offsets.push_back(s.size());
        return s.substr(offsets[left],offsets[right]-offsets[left]);
    };
    std::vector<ComposeSpecEdit> out;
    for(const auto &item:items) {
        const auto colon=item.find(':'),arrow=colon==item.npos?item.npos:item.find("->",colon+1);
        if(colon==item.npos||arrow==item.npos)throw std::invalid_argument("--allow-intent "+repr(item)+" must be NAME:FROM->TO");
        ComposeSpecEdit e;e.kind=ComposeEditKind::MoveEdgeBlock;e.name=strip(item.substr(0,colon));e.from_edge=strip(item.substr(colon+1,arrow-colon-1));e.to_edge=strip(item.substr(arrow+2));out.push_back(e);
    }return out;
}
std::vector<ComposeSpecEdit> propose_compose_repairs(ComposeDocument &ledger,const ComposeDocument &raw,const std::vector<ComposeSpecEdit> &allowed) {
    const auto &interior=opt(raw.data,"interior");
    std::set<std::string> edges;
    for(const auto &[k,names]:opt(raw.data,"edges").object_value){(void)k;for(const auto &name:names.array_value)edges.insert(jstr(name));}
    std::map<std::string,ComposeSpecEdit> moves;for(const auto &m:allowed)moves[m.name]=m;
    std::set<std::pair<std::string,std::string>> seen;
    std::vector<std::string> gated;
    std::vector<ComposeSpecEdit> out;
    const std::map<std::string,double> floor{{"flow_hop",10.},{"near_max",2.},{"near_intent",0.}};
    const auto &terms=opt(ledger.data,"terms").array_value;
    for(std::size_t i=0;i<terms.size();++i) {
        const auto &t=terms[i],&margin=opt(t,"margin");const auto kindname=str(t,"kind");
        auto f=floor.find(kindname);if(f==floor.end())continue;
        if(truth(required(t,"ok"))&&!(truth(opt(t,"enforced"))&&margin.kind!=JsonKind::Null&&jnum(margin)<f->second))continue;
        const auto subj=str(t,"subject"),target=str(t,"target"),tgt=target.substr(0,target.find('.'));
        const auto tkey=key(t);
        if(!seen.emplace(subj,tgt).second)continue;
        if(edges.count(subj)) {
            auto m=moves.find(subj);
            if(m==moves.end()) {gated.push_back(kindname+" "+subj+"->"+tgt+": subject is an EDGE block — repair is an INTENT edge move (--allow-intent "+subj+":<FROM>-><TO>)");continue;}
            auto e=m->second;e.target_key=tkey;out.push_back(e);
            const auto *other=object_field(interior,tgt);
            if(other&&!object_field(*other,"pull")) {
                ComposeSpecEdit pull;pull.block=tgt;pull.to=subj;pull.basis="driver: "+kindname+" "+subj+"<->"+tgt+" composite with "+m->second.describe();
                ComposeSpecEdit composite;composite.kind=ComposeEditKind::Composite;composite.target_key=tkey;composite.edits={m->second,pull};out.push_back(composite);
            }
            continue;
        }
        auto *entry=object_field(interior,subj);
        if(!entry||entry->kind==JsonKind::Null){gated.push_back(kindname+" "+subj+"->"+tgt+": subject not spec-pinned — add it to floorplan.json first (reviewed edit)");continue;}
        if(auto p=object_field(*entry,"pull")) {
            const auto &weight=opt(*p,"weight");
            const auto cur=weight.kind==JsonKind::Null?0.:weight.kind==JsonKind::String?std::stod(weight.string_value):jnum(weight);
            for(double w:{2.,5.,10.,20.,40.,60.})if(w>cur){ComposeSpecEdit e;e.kind=ComposeEditKind::SetPullWeight;e.block=subj;e.weight=w;e.target_key=tkey;out.push_back(e);}
        } else {
            const auto &near=opt(*entry,"near");const bool seat=near.kind==JsonKind::String&&near.string_value==tgt&&edges.count(tgt);
            for(double w:{2.,5.,10.,20.,40.,60.}) {
                ComposeSpecEdit e;e.block=subj;e.to=tgt;e.weight=w;e.face=seat?"inboard":"center";e.exclusive=seat;e.target_key=tkey;
                e.basis="driver: "+kindname+" "+subj+"->"+tgt+" repair (margin "+scalar(ledger,margin,"/terms/"+std::to_string(i)+"/margin")+")";out.push_back(e);
            }
        }
    }
    set(ledger.data,"intent_gated",sorted_strings(gated));return out;
}
ComposeAcceptance accept_compose_repair(const ComposeDocument &before,const ComposeDocument &after,const std::set<ComposeTermKey> &targets,bool allow_area_growth) {
    ComposeAcceptance result;auto &reasons=result.reasons;
    if(!jbool(required(required(after.data,"flow_gate"),"ok")))reasons.push_back("flow gate FAIL on rebuilt model");
    if(!jbool(required(required(after.data,"law5"),"ok")))reasons.push_back("LAW-5 ratsnest gate FAIL on rebuilt model");
    const auto &a0=required(required(before.data,"board"),"area_mm2"),&a1=required(required(after.data,"board"),"area_mm2");
    if(jnum(a1)>jnum(a0)+1e-6&&!allow_area_growth)reasons.push_back("area grew "+scalar(before,a0,"/board/area_mm2")+" -> "+scalar(after,a1,"/board/area_mm2")+" mm^2 (A' <= A violated)");
    using Indexed=std::pair<const JsonNode *,std::size_t>;
    auto term_map=[](const ComposeDocument &d){std::map<ComposeTermKey,Indexed> out;const auto &a=opt(d.data,"terms").array_value;for(std::size_t i=0;i<a.size();++i)out[key(a[i])]={&a[i],i};return out;};
    const auto tb=term_map(before),ta=term_map(after);
    const auto floor=floors();
    for(const auto &[k,brow]:tb) {
        auto it=ta.find(k);if(it==ta.end())continue;
        const auto &b=*brow.first,&a=*it->second.first,&bm=required(b,"margin"),&am=required(a,"margin");
        if(bm.kind==JsonKind::Null||am.kind==JsonKind::Null)continue;
        const double bv=jnum(bm),av=jnum(am);
        const auto change=" ("+scalar(before,bm,"/terms/"+std::to_string(brow.second)+"/margin")+" -> "+scalar(after,am,"/terms/"+std::to_string(it->second.second)+"/margin")+")";
        const auto keytext=key_repr(k);
        if(targets.count(k)){if(!truth(required(a,"ok"))&&av<=bv)reasons.push_back("target "+keytext+" not improved"+change);continue;}
        if(truth(required(b,"ok"))&&!truth(required(a,"ok")))reasons.push_back(keytext+" left GREEN"+change);
        const auto f=floor.find(std::get<0>(k));
        if(truth(opt(b,"enforced"))&&f!=floor.end()&&bv<f->second&&av<bv-1e-9)reasons.push_back("FRAGILE "+keytext+" lost margin"+change);
        if(!truth(required(b,"ok"))&&std::get<0>(k)!="near_intent"&&av<bv-1e-9)reasons.push_back("non-target RED "+keytext+" lost margin"+change);
    }
    std::map<std::string,const JsonNode *> counts;for(const auto &[k,v]:opt(before.data,"contract_violations").object_value)counts[k]=&v;
    for(const auto &[k,b]:counts) {
        const auto &a=opt(opt(after.data,"contract_violations"),k);
        if(a.kind!=JsonKind::Null&&jnum(a)>jnum(*b))reasons.push_back("contract violations worsened on "+k+": "+scalar(before,*b,"/contract_violations/"+pointer(k))+" -> "+scalar(after,a,"/contract_violations/"+pointer(k)));
    }
    result.ok=reasons.empty();return result;
}
} // namespace schgen
