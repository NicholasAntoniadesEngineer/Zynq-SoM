#include "schgen/thermal_checks.hpp"
#include "model_checks_internal.hpp"

namespace schgen {
using namespace model_checks;

const ThermalPolicy& default_thermal_policy() {
    static const ThermalPolicy policy{50.0,10.0,
        {
        {"TPS54302", {118.9, 125.0, 0.0, 0.85, "SOT-23-THIN-6 (DDC, no EP)", "TI SLVSDG6C 5.4 Thermal Information (RthJA 118.9 C/W JESD51-7; EVM 57.2 C/W) + 5.3 Rec-Op Tj-max 125 C (abs-max 150 C); no EP; eff floor 0.85 (DS plots 88-92%)", std::nullopt, "", ""}},
        {"LM61460", {58.7, 150.0, 0.0, 0.85, "VQFN-HR-14 (RJR, PGND pads->GND pour)", "TI SNVSBD5D LM61460 (VQFN-HR RthJA 58.7 C/W JESD51-7 bare; Tj op-max 150 C); eff floor 0.85 (DS plots ~88-91%)", 35.0, "DS 7.3: bare 58.7 C/W (JESD51-7) vs 25 C/W on a 4-layer PCB (DS note + LM61460-Q1 EVM). Credit gated on EMITTED copper, verified in the .kicad_pcb per build: In1.Cu GND plane + 8-via PGND field + local F.Cu/B.Cu pours (SNVSBD5D 11.1.1). Credited 35 C/W — 10 C/W above the DS 4-layer 25, ~30% of the bare->4L delta held back (0.5-oz inner plane, modest pours vs the EVM, 3-buck mutual heating)", "LM61460"}},
        {"AP2112K", {250.0, 125.0, 0.0, 0.85, "SOT-23-5", "Diodes AP2112 DS (SOT-23-5 RthJA ~250 C/W; Tj_max 125 C)", std::nullopt, "", ""}},
        {"TLV75725", {231.0, 125.0, 0.0, 0.85, "SOT-23-5 (DBV, no pad)", "TI TLV757P DS / fmc.md section 3 (DBV RthJA 231 C/W; Tj_max 125 C) — the HOT default; DYD pad variant below", std::nullopt, "", ""}},
        {"SY6280", {250.0, 150.0, 0.095, 0.85, "SOT-23-5", "Silergy SY6280 DS (SOT-23-5 RthJA ~250 C/W; Rds_on ~95 mohm; Tj_max 150 C)", std::nullopt, "", ""}},
        {"TPS26631", {33.6, 125.0, 0.031, 0.85, "HTSSOP-20 (PWP)", "TI SLVSE94 (HTSSOP-20 PowerPAD RthJA ~33.6 C/W 2s2p; FET Rds_on 31 mohm; Tj op-max 125 C)", std::nullopt, "", ""}}
    },
        {{"TLV75725","DYD",{231.0, 125.0, 0.0, 0.85, "SOT-23-5 (DYD, EP+vias->In1 plane)", "TI TLV757P DS / fmc.md section 3 + PWR-3 (DYD thermal-pad RthJA ~92.5 C/W JESD51-7 WITH JESD51-5 vias; Tj_max 125 C); no-copper fallback = DBV bare 231 C/W", 92.5, "DS DYD RthJA 92.5 C/W presumes the JESD51-5 stackup (thermal pad soldered + vias into a buried plane). Credit gated on EMITTED copper, verified per build: In1.Cu GND plane + >=2 GND vias beside the pad + local F.Cu pour. Fallback without it: DBV bare 231 C/W (no pad benefit claimable)", "TLV75725_DYD"}}},
        {
        {"LM61460", {"LM61460", 6, 5.2, {"F.Cu", "B.Cu"}}},
        {"TLV75725_DYD", {"TLV75725", 2, 3.0, {"F.Cu"}}}
    }
    };
    return policy;
}

const ThermalSpec* thermal_spec_for(const std::string& value,const std::string& footprint,const ThermalPolicy& policy) {
    for(const auto& fp:policy.footprint_specs)if(starts(value,fp.value_prefix)&&footprint.find(fp.footprint_contains)!=std::string::npos)return &fp.spec;
    for(const auto& [prefix,s]:policy.specs)if(starts(value,prefix))return &s;return nullptr;
}
double thermal_dissipation(const std::string& kind,double vin,double vout,double iout,const ThermalSpec& spec) {
    if(kind=="ldo")return std::max(0.0,vin-vout)*iout;
    if(kind=="buck"){if(spec.eff==0)throw ModelCheckError("thermal checks: zero buck efficiency");return std::max(0.0,1.0/spec.eff-1.0)*vout*iout;}
    if(kind=="load_switch"||kind=="efuse")return iout*iout*spec.rds_on;return 0;
}
std::vector<std::string> thermal_pour_layers(const ThermalPourNeed& need,const std::string& layer) {
    auto out=need.pour_layers;
    if(layer=="B.Cu") {for(auto& l:out) {if(l=="F.Cu")l="B.Cu";else if(l=="B.Cu")l="F.Cu";}}
    return out;
}
namespace {
bool zone_on(const CopperZoneEvidence& z,const std::string& net,const std::string& layer) {
    return !z.keepout&&z.filled&&z.net_name==net&&std::find(z.layers.begin(),z.layers.end(),layer)!=z.layers.end();
}
const SexprList* list(const Sexpr& n){return std::get_if<SexprList>(&n.v);}
bool atom_eq(const Sexpr& n,const std::string& s) {
    if(auto sym=std::get_if<Sexpr::Sym>(&n.v))return sym->name==s;
    if(auto str=std::get_if<std::string>(&n.v))return *str==s;
    return false;
}
bool tag(const SexprList& n,const std::string& s){return !n.empty()&&atom_eq(n[0],s);}
const SexprList* child(const SexprList& ns,const std::string& name){for(const auto& n:ns)if(auto l=list(n);l&&tag(*l,name))return l;return nullptr;}
std::string atom(const Sexpr& n) {
    if(auto s=std::get_if<std::string>(&n.v))return *s;
    if(auto s=std::get_if<Sexpr::Sym>(&n.v))return s->name;
    if(auto d=std::get_if<double>(&n.v)) {
        if(*d==0)return "0";
        if(*d==std::floor(*d))return f(*d,0);
        char text[64];auto r=std::to_chars(text,text+sizeof text,*d);
        if(r.ec!=std::errc{})throw ModelCheckError("thermal copper: numeric atom out of range");
        return {text,r.ptr};
    }
    if(auto b=std::get_if<bool>(&n.v))return *b?"True":"False";
    throw ModelCheckError("thermal copper: expected atom");
}
std::string attr(const SexprList& n,const std::string& name,std::size_t i=1){auto c=child(n,name);return c&&c->size()>i?atom((*c)[i]):"";}
double num(const Sexpr& n) {
    if(auto d=std::get_if<double>(&n.v))return *d;
    if(auto b=std::get_if<bool>(&n.v))return *b?1.0:0.0;
    auto s=trim(atom(n));char* end=nullptr;double d=std::strtod(s.c_str(),&end);
    if(s.empty()||end!=s.c_str()+s.size()||!std::isfinite(d))throw ModelCheckError("thermal copper: expected finite coordinate");return d;
}
double coord(const SexprList* n,std::size_t i){return n&&n->size()>i?num((*n)[i]):0.0;}
std::string netnum(const Sexpr& n) {
    double d=num(n);if(!std::isfinite(d)||d>=std::ldexp(1.0,63)||d<-std::ldexp(1.0,63))throw ModelCheckError("thermal copper: net number out of range");return std::to_string(static_cast<std::int64_t>(d));
}
}
bool ThermalCopper::gnd_plane(const std::string& layer)const {return std::any_of(zones.begin(),zones.end(),[&](const auto& z){return zone_on(z,"GND",layer);});}
std::vector<const CopperFootprintEvidence*> ThermalCopper::instances(const std::string& prefix)const {
    std::vector<const CopperFootprintEvidence*> out;for(const auto& f:footprints)if(starts(f.value,prefix))out.push_back(&f);
    std::stable_sort(out.begin(),out.end(),[](auto a,auto b){return a->ref<b->ref;});return out;
}
std::size_t ThermalCopper::gnd_vias_within(double x,double y,double radius)const {
    return std::count_if(vias.begin(),vias.end(),[&](const auto& v){return v.net_name=="GND"&&std::hypot(v.x-x,v.y-y)<=radius;});
}
bool ThermalCopper::pour_at(double x,double y,const std::string& layer,const std::string& net)const {
    return std::any_of(zones.begin(),zones.end(),[&](const auto& z){return zone_on(z,net,layer)&&z.bbox[0]<=x&&x<=z.bbox[2]&&z.bbox[1]<=y&&y<=z.bbox[3];});
}
ThermalCopper scan_thermal_copper(const Sexpr& board,const std::string& source) {
    auto doc=list(board);if(!doc)throw ModelCheckError("thermal copper: board must be an s-expression list");
    ThermalCopper bc;bc.path=source;std::map<std::string,std::string> nets;
    for(const auto& node:*doc) {
        auto ns=list(node);if(!ns||ns->empty())continue;
        if(tag(*ns,"zone")) {
            CopperZoneEvidence z;z.name=attr(*ns,"name");z.net_name=attr(*ns,"net_name");
            auto l1=child(*ns,"layer"),ln=child(*ns,"layers");
            if(l1&&l1->size()>1)z.layers.push_back(atom((*l1)[1]));else if(ln)for(std::size_t k=1;k<ln->size();++k)z.layers.push_back(atom((*ln)[k]));
            z.keepout=child(*ns,"keepout")!=nullptr;auto fill=child(*ns,"fill");
            if(fill&&fill->size()>1)z.filled=atom_eq((*fill)[1],"yes");
            bool first=true;
            if(auto poly=child(*ns,"polygon"))if(auto pts=child(*poly,"pts"))for(std::size_t k=1;k<pts->size();++k)if(auto xy=list((*pts)[k]);xy&&xy->size()>=3) {
                double x=num((*xy)[1]),y=num((*xy)[2]);
                if(first){z.bbox={x,y,x,y};first=false;}else {z.bbox[0]=std::min(z.bbox[0],x);z.bbox[1]=std::min(z.bbox[1],y);z.bbox[2]=std::max(z.bbox[2],x);z.bbox[3]=std::max(z.bbox[3],y);}
            }
            bc.zones.push_back(std::move(z));
        } else if(tag(*ns,"via")) {
            auto at=child(*ns,"at"),net=child(*ns,"net");
            if(!at||at->size()<3)throw ModelCheckError("thermal copper: via requires an at pair");
            bc.vias.push_back({num((*at)[1]),num((*at)[2]),net&&net->size()>1?netnum((*net)[1]):"0"});
        } else if(tag(*ns,"segment"))++bc.segments;
        else if(tag(*ns,"footprint")) {
            CopperFootprintEvidence fp;auto at=child(*ns,"at");fp.x=coord(at,1);fp.y=coord(at,2);fp.layer=attr(*ns,"layer");
            for(const auto& n:*ns)if(auto p=list(n);p&&tag(*p,"property")&&p->size()>2) {
                if(atom_eq((*p)[1],"Reference"))fp.ref=atom((*p)[2]);else if(atom_eq((*p)[1],"Value"))fp.value=atom((*p)[2]);
            }
            if(starts(fp.value,"LM61460")||starts(fp.value,"TLV75725")||starts(fp.value,"TPS26631"))
                for(const auto& n:*ns)if(auto p=list(n);p&&tag(*p,"pad")) {
                    auto pat=child(*p,"at"),dr=child(*p,"drill");double drill=0;
                    if(dr&&dr->size()>1&&(std::holds_alternative<double>((*dr)[1].v)||std::holds_alternative<bool>((*dr)[1].v)))drill=num((*dr)[1]);
                    fp.pads.push_back({p->size()>1?atom((*p)[1]):"",coord(pat,1),coord(pat,2),drill,attr(*p,"net",2)});
                }
            bc.footprints.push_back(std::move(fp));
        } else if(tag(*ns,"net")&&ns->size()>2){auto name=atom((*ns)[2]);bc.net_names.insert(name);nets[netnum((*ns)[1])]=name;}
    }
    for(auto& via:bc.vias)if(auto it=nets.find(via.net_name);it!=nets.end())via.net_name=it->second;
    return bc;
}
ThermalCopper scan_thermal_copper(const std::filesystem::path& path){return scan_thermal_copper(sexpr_loads(read(path)),path.string());}
std::pair<bool,std::string> thermal_pour_evidence(const ThermalCopper* copper,const ThermalPourNeed& need) {
    if(!copper)return {false,"no emitted-board scan (fail-closed: credit withheld)"};
    if(!copper->gnd_plane())return {false,"In1.Cu GND plane NOT emitted"};
    auto insts=copper->instances(need.value_prefix);
    if(insts.empty())return {false,"no "+need.value_prefix+"* footprint on the emitted board"};
    std::vector<std::string> rows;bool all=true;
    for(auto fp:insts) {
        auto nv=copper->gnd_vias_within(fp->x,fp->y,need.radius_mm);auto layers=thermal_pour_layers(need,fp->layer);
        bool pours=std::all_of(layers.begin(),layers.end(),[&](const auto& l){return copper->pour_at(fp->x,fp->y,l);});
        bool ok=double(nv)>=need.min_vias&&pours;all=all&&ok;
        for(auto& l:layers)l=l.substr(0,l.find('.'));
        rows.push_back(fp->ref+": "+std::to_string(nv)+"/"+std::to_string(need.min_vias)+" GND vias<="+g(need.radius_mm)+"mm, local "+join(layers,"+")+" pour "+(pours?"YES":"MISSING")+(ok?"":" [INSUFFICIENT]"));
    }
    return {all,"In1 GND plane + "+join(rows,"; ")};
}

ThermalCheckResult analyze_thermal(const std::vector<ProjectCircuit>& sheets,const PowerCheckResult& power,const ThermalCopper* copper,const std::string& source,const ThermalPolicy& policy,const PowerPolicy& pp) {
    ThermalCheckResult res;res.ta=policy.ambient_c;res.margin=policy.margin_c;res.waived=waivers(sheets,"thermal_waivers");res.copper_src=copper?source:"";
    std::vector<std::pair<std::string,std::pair<bool,std::string>>> ev;
    for(const auto& [key,need]:policy.pour_needs)ev.emplace_back(key,thermal_pour_evidence(copper,need));
    std::map<std::pair<std::string,std::string>,std::string> fps;
    for(const auto& s:sheets)for(const auto& p:s.circuit.parts)fps[{s.name,p.ref}]=p.footprint;
    for(auto r:sorted_regs(power)) {
        auto it=fps.find({r->sheet,r->ref});auto fp=it==fps.end()?std::string{}:it->second;
        auto spec=thermal_spec_for(r->value,fp,policy);auto key=r->sheet+":"+r->ref;
        if(!spec){res.findings.push_back("UNSPECED: "+key+" ("+r->value+", fp "+(fp.empty()?"<none>":fp)+") has no thermal spec — add a THERMAL_SPECS/FOOTPRINT_SPECS row with its datasheet RthJA + Tj_max before its Tj can be proven");continue;}
        double vin=rail_volts(r->vin,pp).value_or(0),vout=rail_volts(r->vout,pp).value_or(0),pd=thermal_dissipation(r->kind,vin,vout,r->i_out,*spec);
        auto evidence=spec->rth_ja_pour?find(ev,spec->pour_evidence):nullptr;
        bool granted=evidence&&evidence->first;std::string detail=evidence?evidence->second:"";
        double rth=granted?*spec->rth_ja_pour:spec->rth_ja,tj=res.ta+pd*rth,limit=spec->tj_max-res.margin,margin=limit-tj;
        res.devices.push_back({r->sheet,r->ref,r->value,spec->package,r->kind,r->vin,r->vout,vin,vout,r->i_out,pd,rth,tj,spec->tj_max,margin,spec->cite,spec->rth_ja,spec->pour_cite,granted,detail});
        if(spec->rth_ja_pour&&!granted)res.notes.push_back("POUR CREDIT WITHHELD: "+key+" ("+r->value+") judged at the bare "+g(spec->rth_ja)+" C/W, not the credited "+g(*spec->rth_ja_pour)+" — required copper not verified: "+detail);
        if(margin<0) {
            std::string withheld=spec->rth_ja_pour&&!granted?" — POUR CREDIT WITHHELD (required copper not emitted: "+detail+")":"";
            if(auto w=find(res.waived,key))res.notes.push_back("WAIVED over-limit: "+key+" ("+r->value+") Tj "+f(tj,1)+" C > limit "+f(limit,1)+" C (Tj_max "+f(spec->tj_max,0)+" - margin "+f(res.margin,0)+") — author waiver: "+w->second);
            else res.errors.push_back("OVER Tj: "+key+" ("+r->value+", "+spec->package+") "+r->vin+"->"+r->vout+": Iout "+f(r->i_out,3)+" A -> Pd "+f(pd*1000,0)+" mW, Tj = "+f(res.ta,0)+" + "+f(pd*1000,0)+"mW*"+g(rth)+" = "+f(tj,1)+" C > limit "+f(limit,1)+" C (Tj_max "+f(spec->tj_max,0)+" - margin "+f(res.margin,0)+") ["+spec->cite+"]"+withheld);
        }
    }
    return res;
}
ThermalCheckResult analyze_thermal(const std::vector<ProjectCircuit>& sheets,const ThermalCopper* copper,const std::string& source,const ThermalPolicy& policy,const PowerPolicy& pp) {
    return analyze_thermal(sheets,analyze_power(sheets,pp),copper,source,policy,pp);
}

std::string thermal_report(const ThermalCheckResult& res) {
    std::vector<std::string> ls{"schgen per-device thermal (Tj) gate",std::string(78,'='),"",
        "model: Tj = Ta + Pd*RthJA ; Ta = "+f(res.ta,0)+" C ; FAIL when Tj > Tj_max - "+f(res.margin,0)+" C margin",
        "  Pd(LDO) = (Vin-Vout)*Iout ; Pd(buck) = (1/eff-1)*Vout*Iout, eff="+g(thermal_buck_eff)+" ; Pd(switch/eFuse) = Iout^2*Rds_on",
        "  RthJA = bare JEDEC, unless '*' = pour-aware effective RthJA (EP/power pads -> GND copper + vias; basis cited below)",
        "  pour credits are granted ONLY against copper VERIFIED in the emitted board",
        "  emitted-copper evidence source: "+(res.copper_src.empty()?"NONE — all pour credits withheld (fail-closed)":res.copper_src),""};
    auto hdr="  "+pad("device",22)+" "+pad("package",24)+" "+pad("kind",11)+" "+pad("in->out",20)+" "+pad("Iout/A",7,true)+" "+pad("Pd/mW",7,true)+" "+pad("RthJA",7,true)+" "+pad("Tj/C",7,true)+" "+pad("limit",7,true)+" "+pad("mgn/C",7,true)+"  verdict";
    ls.push_back(hdr);ls.push_back("  "+std::string(chars(hdr)-2,'-'));
    std::vector<const ThermalDevice*> ds;for(const auto& d:res.devices)ds.push_back(&d);
    std::stable_sort(ds.begin(),ds.end(),[](auto a,auto b){return std::make_tuple(-a->tj,a->sheet,a->ref)<std::make_tuple(-b->tj,b->sheet,b->ref);});
    for(auto d:ds) {
        auto rth=f(d->rth_ja,1)+(d->poured()?"*":" ");
        ls.push_back("  "+pad(d->sheet+":"+d->ref,22)+" "+pad(d->package,24)+" "+pad(d->kind,11)+" "+pad(d->vin+"->"+d->vout,20)+" "+pad(f(d->i_out,3),7,true)+" "+pad(f(d->pd*1000,0),7,true)+" "+pad(rth,7,true)+" "+pad(f(d->tj,1),7,true)+" "+pad(f(d->tj_max-res.margin,1),7,true)+" "+pad(f(d->margin,1),7,true)+"  "+(d->over()?"OVER":"ok"));
    }
    ls.insert(ls.end(),{"","datasheet provenance (every RthJA / Tj_max / Rds_on cited):"});
    ds.clear();for(const auto& d:res.devices)ds.push_back(&d);
    std::stable_sort(ds.begin(),ds.end(),[](auto a,auto b){return a->value<b->value;});
    std::set<std::string> seen;
    for(auto d:ds)if(seen.insert(d->value+d->package).second)ls.push_back("  "+pad(d->value,16)+" "+pad(d->package,26)+" "+d->cite);
    bool heading=false;seen.clear();
    for(auto d:ds)if(d->poured()&&seen.insert(d->value).second) {
        if(!heading){ls.insert(ls.end(),{"","pour-aware effective RthJA (* rows) — basis, per part (bare->credited, cited; conservative, bench-verify at bring-up):"});heading=true;}
        ls.push_back("  "+pad(d->value,16)+" bare "+g(d->rth_bare)+" -> eff "+g(d->rth_ja)+" C/W ; "+d->pour_cite);
        ls.push_back("  "+pad("",16)+" emitted-copper evidence (verified in the board file): "+d->evidence);
    }
    if(!res.waived.empty()){ls.insert(ls.end(),{"","author thermal waivers, verbatim ("+std::to_string(res.waived.size())+"):"});for(const auto& [k,v]:sorted(res.waived))ls.push_back("  "+pad(k,22)+" "+v.second);}
    if(!res.notes.empty()){ls.insert(ls.end(),{"","notes ("+std::to_string(res.notes.size())+"):"});for(const auto& n:res.notes)ls.push_back("  + "+n);}
    if(!res.findings.empty()){ls.insert(ls.end(),{"","FINDINGS — unspeced devices ("+std::to_string(res.findings.size())+"):"});for(const auto& n:res.findings)ls.push_back("  * "+n);}
    ls.push_back("");if(res.errors.empty())ls.push_back("errors: none");else {ls.push_back("ERRORS ("+std::to_string(res.errors.size())+"):");for(const auto& n:res.errors)ls.push_back("  ERROR: "+n);}
    const ThermalDevice* hot=nullptr;for(const auto& d:res.devices)if(!hot||d.tj>hot->tj)hot=&d;
    auto hotstr=hot?"; hottest "+hot->sheet+":"+hot->ref+" ("+hot->value+") Tj "+f(hot->tj,1)+" C":"";
    ls.insert(ls.end(),{"",std::string("THERMAL: ")+(res.ok()?"PASS":"FAIL")+" ("+std::to_string(res.devices.size())+" devices speced, "+std::to_string(res.errors.size())+" over-limit, "+std::to_string(res.findings.size())+" unspeced, "+std::to_string(res.waived.size())+" waived)"+hotstr});return join(ls);
}
ThermalCheckResult run_thermal_checks(const std::vector<ProjectCircuit>& sheets,const std::filesystem::path& dir,const PowerCheckResult* power,const std::optional<std::filesystem::path>& pcb,const std::filesystem::path& repository_root,const ThermalPolicy& policy,const PowerPolicy& pp) {
    std::optional<ThermalCopper> copper;std::string source;
    if(pcb&&std::filesystem::exists(*pcb)) {
        copper=scan_thermal_copper(*pcb);source=pcb->string();
        if(!repository_root.empty()) {
            auto rel=std::filesystem::weakly_canonical(*pcb).lexically_relative(std::filesystem::weakly_canonical(repository_root));
            if(!rel.empty()&&*rel.begin()!="..")source=rel.string();
        }
    }
    auto res=power?analyze_thermal(sheets,*power,copper?&*copper:nullptr,source,policy,pp):analyze_thermal(sheets,copper?&*copper:nullptr,source,policy,pp);
    publish(dir/"thermal.txt",thermal_report(res)+"\n");return res;
}
JsonNode thermal_result_json(const ThermalCheckResult& res) {
    auto ds=arr();
    for(const auto& d:res.devices)ds.array_value.push_back(obj({{"sheet",j(d.sheet)},{"ref",j(d.ref)},{"value",j(d.value)},{"package",j(d.package)},{"kind",j(d.kind)},{"vin",j(d.vin)},{"vout",j(d.vout)},{"v_in",j(d.v_in)},{"v_out",j(d.v_out)},{"i_out",j(d.i_out)},{"pd",j(d.pd)},{"rth_ja",j(d.rth_ja)},{"tj",j(d.tj)},{"tj_max",j(d.tj_max)},{"margin",j(d.margin)},{"cite",j(d.cite)},{"rth_bare",j(d.rth_bare)},{"pour_cite",j(d.pour_cite)},{"pour_granted",j(d.pour_granted)},{"evidence",j(d.evidence)}}));
    return obj({{"devices",ds},{"errors",strings(res.errors)},{"findings",strings(res.findings)},{"waived",waiver_json(res.waived)},{"notes",strings(res.notes)},{"ta",j(res.ta)},{"margin",j(res.margin)},{"copper_src",j(res.copper_src)}});
}
JsonNode thermal_copper_json(const ThermalCopper& c) {
    auto zs=arr(),vs=arr(),fps=arr(),names=arr();
    for(const auto& z:c.zones)zs.array_value.push_back(obj({{"name",j(z.name)},{"net_name",j(z.net_name)},{"layers",strings(z.layers)},{"keepout",j(z.keepout)},{"filled",j(z.filled)},{"bbox",arr({j(z.bbox[0]),j(z.bbox[1]),j(z.bbox[2]),j(z.bbox[3])})}}));
    for(const auto& v:c.vias)vs.array_value.push_back(obj({{"x",j(v.x)},{"y",j(v.y)},{"net_name",j(v.net_name)}}));
    for(const auto& f:c.footprints){auto ps=arr();for(const auto& p:f.pads)ps.array_value.push_back(obj({{"name",j(p.name)},{"dx",j(p.dx)},{"dy",j(p.dy)},{"drill",j(p.drill)},{"net_name",j(p.net_name)}}));fps.array_value.push_back(obj({{"ref",j(f.ref)},{"value",j(f.value)},{"x",j(f.x)},{"y",j(f.y)},{"layer",j(f.layer)},{"pads",ps}}));}
    for(const auto& n:c.net_names)names.array_value.push_back(j(n));
    return obj({{"path",j(c.path)},{"zones",zs},{"vias",vs},{"segments",j(double(c.segments))},{"footprints",fps},{"net_names",names}});
}

ThermalCheckResult thermal_result_from_json(const JsonNode& n) {
    object_shape(n,{"devices","errors","findings","waived","notes","ta","margin","copper_src"},"thermal result");
    ThermalCheckResult r;
    for(const auto& v:array_items(member(n,"devices"))) {
        object_shape(v,{"sheet","ref","value","package","kind","vin","vout","v_in","v_out","i_out","pd","rth_ja","tj","tj_max","margin","cite","rth_bare","pour_cite","pour_granted","evidence"},"thermal device");
        r.devices.push_back({string(member(v,"sheet")),string(member(v,"ref")),string(member(v,"value")),string(member(v,"package")),string(member(v,"kind")),string(member(v,"vin")),string(member(v,"vout")),number(member(v,"v_in")),number(member(v,"v_out")),number(member(v,"i_out")),number(member(v,"pd")),number(member(v,"rth_ja")),number(member(v,"tj")),number(member(v,"tj_max")),number(member(v,"margin")),string(member(v,"cite")),number(member(v,"rth_bare")),string(member(v,"pour_cite")),boolean(member(v,"pour_granted")),string(member(v,"evidence"))});
    }
    r.errors=read_strings(member(n,"errors"));r.findings=read_strings(member(n,"findings"));r.waived=read_waivers(member(n,"waived"));r.notes=read_strings(member(n,"notes"));r.ta=number(member(n,"ta"));r.margin=number(member(n,"margin"));r.copper_src=string(member(n,"copper_src"));return r;
}
ThermalCopper thermal_copper_from_json(const JsonNode& n) {
    object_shape(n,{"path","zones","vias","segments","footprints","net_names"},"thermal copper");
    ThermalCopper c;c.path=string(member(n,"path"));c.segments=count(member(n,"segments"));
    for(const auto& s:read_strings(member(n,"net_names")))c.net_names.insert(s);
    for(const auto& z:array_items(member(n,"zones"))) {
        object_shape(z,{"name","net_name","layers","keepout","filled","bbox"},"copper zone");auto& box=tuple_items(member(z,"bbox"),4);
        c.zones.push_back({string(member(z,"name")),string(member(z,"net_name")),read_strings(member(z,"layers")),boolean(member(z,"keepout")),boolean(member(z,"filled")),{number(box[0]),number(box[1]),number(box[2]),number(box[3])}});
    }
    for(const auto& v:array_items(member(n,"vias"))){object_shape(v,{"x","y","net_name"},"copper via");c.vias.push_back({number(member(v,"x")),number(member(v,"y")),string(member(v,"net_name"))});}
    for(const auto& fp:array_items(member(n,"footprints"))) {
        object_shape(fp,{"ref","value","x","y","layer","pads"},"copper footprint");CopperFootprintEvidence f{string(member(fp,"ref")),string(member(fp,"value")),number(member(fp,"x")),number(member(fp,"y")),string(member(fp,"layer")),{}};
        for(const auto& p:array_items(member(fp,"pads"))) {object_shape(p,{"name","dx","dy","drill","net_name"},"copper pad");f.pads.push_back({string(member(p,"name")),number(member(p,"dx")),number(member(p,"dy")),number(member(p,"drill")),string(member(p,"net_name"))});}
        c.footprints.push_back(std::move(f));
    }
    return c;
}

} // namespace schgen
