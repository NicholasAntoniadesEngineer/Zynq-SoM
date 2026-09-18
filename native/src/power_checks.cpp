#include "schgen/power_checks.hpp"
#include "model_checks_internal.hpp"

namespace schgen {
using namespace model_checks;

const PowerPolicy& default_power_policy() {
    static const PowerPolicy policy{
        {{"^\\+VBUS_IN$", 20.0}, {"^\\+VIN_SYS$", 20.0}, {"^\\+VIN", 20.0}, {"^\\+5V_SOM$", 4.65}, {"^\\+5V_REG$", 5.0}, {"^\\+5V", 5.0}, {"^USB_VBUS$", 5.0}, {"^USB_UART_VBUS$", 5.0}, {"^HDMI_RX_5V$", 5.0}, {"^HDMI_TX_CON_5V0$", 5.0}, {"^LCD_VLED_P$", 30.0}, {"^\\+3V3_REG$", 3.3}, {"^\\+3V3", 3.3}, {"^\\+1V8_REG$", 1.8}, {"^\\+1V8", 1.8}, {"^\\+2V5", 2.5}, {"^\\+VCCO_35$", 2.5}, {"^\\+VCCO_", 3.3}, {"^VBUS$", 5.0}},
        {
        {"TPS54302", {"buck", 3.0, 0.9, "3", "2", "", 6800.0, "TI 3 A synchronous buck (SW->L->rail); thermal-gate test fixture"}},
        {"LM61460", {"buck", 6.0, 0.9, "8", "10", "", 6800.0, "TI 6 A 3-36V synchronous buck (VIN1=8 ->L<-SW=10 ->rail)"}},
        {"LMR33630", {"buck", 3.0, 0.9, "2", "8", "", 6800.0, "TI 3 A 36V synchronous buck (VIN=2, SW=8 ->L->rail)"}},
        {"AP2112K", {"ldo", 0.6, 1.0, "1", "5", "", 6800.0, "600 mA LDO"}},
        {"TLV75725", {"ldo", 0.4, 1.0, "1", "5", "", 6800.0, "1 A LDO held to 0.4 A continuous (PWR-3: DYD thermal-pad, RthJA ~92.5 C/W EP-to-GND, Tj ~80 C at 0.32 W/Ta=50 C — fmc.md section 3)"}},
        {"SY6280", {"load_switch", std::nullopt, 1.0, "IN", "OUT", "ISET", 6800.0, "ILIM = 6800/RSET from netlist"}},
        {"TPS26631", {"efuse", std::nullopt, 1.0, "IN", "OUT", "ILIM", 18000.0, "ILIM = 18/R_kohm from netlist (TPS2663 Eq 5)"}}
    },
        {
        {"+VBUS_IN", {20.0, 3.0, "USB-C PD sink contract 20 V / 3 A at the receptacle (pd_input J1; +VIN sits behind the TPS26631 eFuse, round 5)"}},
        {"+3V3_SC", {3.3, 0.3, "SoM TPS7A20 always-on SC LDO U13 (J1.37); 300 mA class — the SoM power_architecture sheet says '3V3 (300mA)'. Envelope shared with the SoM-side SC (STM32G431 ~50 mA); carrier tally only here"}},
        {"+5V_DBG", {5.0, 0.5, "debug USB-C VBUS (usb_jtag_connector J1) — host-supplied 5 V / 0.5 A USB2 default; feeds the usb_jtag AP2112K-3.3 debug-island LDO; isolated from carrier +5V"}}
    },
        {}
    };
    return policy;
}

std::optional<double> parse_si_value(const std::string& text) {
    auto t=numeric_text(trim(text));
    if(ends(t,"mR")) {
        auto h=trim(t.substr(0,t.size()-2));
        if(h.empty())return {};
        // These four control separators satisfy str.strip/re \s but not float.
        // At this point an internal separator before mR must not be trimmed.
        auto raw_head=t.substr(0,t.size()-2);
        if(raw_head.find_first_of("\x1c\x1d\x1e\x1f")!=std::string::npos)return {};
        // Python float permits signs, exponents and digit separators here only.
        static const std::regex number(R"(^[+-]?(?:(?:[0-9](?:_?[0-9])*)(?:\.(?:[0-9](?:_?[0-9])*)?)?|\.[0-9](?:_?[0-9])*)(?:[eE][+-]?[0-9](?:_?[0-9])*)?$)");
        const auto u=upper(h);
        if(!std::regex_match(h,number)&&u!="INF"&&u!="+INF"&&u!="-INF"&&u!="INFINITY"&&u!="+INFINITY"&&u!="-INFINITY"&&u!="NAN"&&u!="+NAN"&&u!="-NAN")return {};
        replace_all(h,"_",""); char* end=nullptr;auto v=std::strtod(h.c_str(),&end);
        return end==h.c_str()+h.size()?std::optional<double>(v*1e-3):std::nullopt;
    }
    t=numeric_text(t,true);replace_all(t,"µ","u");
    static const std::regex pattern(R"(^([0-9]+(?:\.[0-9]+)?)\s*([pnumkKMGR]?)([0-9]*)\s*(?:[RFH]|Ω|mR)?$)");
    std::smatch m;if(!std::regex_match(t,m,pattern))return {};
    auto digits=m[1].str();if(!m[3].str().empty())digits+="."+m[3].str();
    char* end=nullptr;double value=std::strtod(digits.c_str(),&end);
    if(end!=digits.c_str()+digits.size())throw ModelCheckError("could not convert string to float: "+repr(digits));
    const std::map<std::string,double> si{{"p",1e-12},{"n",1e-9},{"u",1e-6},{"m",1e-3},{"k",1e3},{"K",1e3},{"M",1e6},{"G",1e9},{"R",1},{"",1}};
    return value*si.at(m[2].str());
}

std::optional<double> rail_volts(const std::string& name,const PowerPolicy& policy) {
    // Match patterns, not policy object identity: binding callers pass copies,
    // and may override voltages while retaining the standard rail expressions.
    static const std::vector<std::pair<std::string,std::regex>> compiled=[] {
        std::vector<std::pair<std::string,std::regex>> out;
        for(const auto& [pattern,v]:default_power_policy().voltage_patterns) {
            (void)v;out.emplace_back(pattern,std::regex(pattern));
        }
        return out;
    }();
    const auto matches=[&](const std::regex& re) {
        if(std::regex_search(name,re,std::regex_constants::match_continuous))return true;
        // Python '$' also matches immediately before one terminal newline.
        return ends(name,"\n")&&std::regex_search(name.begin(),name.end()-1,re,std::regex_constants::match_continuous);
    };
    for(const auto& [pattern,v]:policy.voltage_patterns) {
        if(const auto* re=find(compiled,pattern)) {if(matches(*re))return v;}
        else if(matches(std::regex(pattern)))return v;
    }
    return {};
}

namespace {
void detect(const std::vector<ProjectCircuit>& sheets,const PowerPolicy& policy,PowerCheckResult& res) {
    for(const auto& s:sheets) {
        ModelSheetIndex idx(s.circuit);
        for(const auto& [ref,p]:idx.parts) {
            const PowerRegSpec* spec=nullptr;
            for(const auto& [prefix,v]:policy.regulators)if(starts(p->value,prefix)){spec=&v;break;}
            if(!spec)continue;
            auto vin=idx.alias_net(*p,spec->in_pin), out=idx.alias_net(*p,spec->out_pin);
            auto who=s.name+":"+ref+" ("+p->value+"): ";
            if(!vin||!out){res.errors.push_back(who+"cannot resolve IN/OUT pins for the power tree");continue;}
            std::string vout=out->name;
            if(spec->kind=="buck") {
                vout.clear();
                for(const auto& pin:out->pins) {
                    auto other=idx.part(pin.ref);if(!other||pin.ref==ref)continue;
                    if(ends(other->lib_id,":L")||ends(upper(other->value),"H"))
                        for(const auto* p2:{"1","2"})if(auto nn=idx.net(pin.ref,p2);nn&&nn->name!=out->name&&nn->net_class=="power")vout=nn->name;
                }
                if(vout.empty()){res.errors.push_back(who+"no SW->inductor->rail hop found");continue;}
            }
            auto limit=spec->limit_a;auto note=spec->note;
            if(spec->kind=="load_switch"||spec->kind=="efuse") {
                auto iset=idx.alias_net(*p,spec->iset_pin);std::optional<double> rset;
                if(iset)for(const auto& pin:iset->pins)if(auto rp=idx.part(pin.ref);rp&&ends(rp->lib_id,":R"))rset=parse_si_value(rp->value);
                if(rset&&*rset!=0) {
                    limit=py_round(spec->ilim_num / *rset,3);
                    note="ILIM = "+f(spec->ilim_num,0)+"/"+f(*rset,0)+"R = "+f(*limit*1000,0)+" mA";
                } else {res.errors.push_back(who+"ISET resistor not found — cannot prove ILIM");continue;}
            }
            if(!limit)throw ModelCheckError(who+"regulator policy has no current limit");
            res.regs.push_back({int(res.regs.size()+1),s.name,ref,p->value,spec->kind,vin->name,vout,*limit,spec->eff,note,0,0});
        }
        std::map<std::string,std::vector<const CircuitNetIr*>> nets;
        for(const auto& n:s.circuit.nets)for(const auto& p:n.pins)nets[p.ref].push_back(&n);
        for(const auto& [ref,ns]:nets)if(ns.size()==2&&ns[0]->net_class=="power"&&ns[1]->net_class=="power"&&ns[0]->name!=ns[1]->name)
            res.bridges.push_back({s.name,ref,ns[0]->name,ns[1]->name});
    }
}
struct Cap {std::string sheet,ref,value;double farads;};
std::vector<Cap> caps_on(const std::vector<ProjectCircuit>& sheets,const std::string& rail) {
    std::vector<Cap> out;
    for(const auto& s:sheets) {
        ModelSheetIndex idx(s.circuit);
        for(const auto& [ref,p]:idx.parts)if(ends(p->lib_id,":C")) {
            std::set<std::string> nets;for(const auto* pin:{"1","2"}){auto n=idx.net(ref,pin);nets.insert(n?n->name:"");}
            bool ground=std::any_of(nets.begin(),nets.end(),[](const auto& n){return starts(n,"GND");});
            if(nets.count(rail)&&ground)if(auto v=parse_si_value(p->value);v&&*v!=0)out.push_back({s.name,ref,p->value,*v});
        }
    }
    return out;
}
double cap_sum(const std::vector<Cap>& caps){FloatSum sum;for(const auto& c:caps)sum.add(c.farads);return sum.value()*1e6;}
std::string cap_detail(const std::vector<Cap>& caps){std::vector<std::string> rows;for(const auto& c:caps)rows.push_back(c.sheet+":"+c.ref+"="+c.value);return join(rows," + ");}
void precontract(const std::vector<ProjectCircuit>& sheets,PowerCheckResult& res) {
    const std::string inlet="+VBUS_IN";auto ci=caps_on(sheets,inlet),cb=caps_on(sheets,"+VIN");
    double iu=cap_sum(ci),bu=cap_sum(cb);std::vector<const PowerReg*> efuses;
    for(const auto& r:res.regs)if(r.kind=="efuse"&&r.vin==inlet)efuses.push_back(&r);
    if(efuses.empty()) {
        ci.insert(ci.end(),cb.begin(),cb.end());
        res.findings.push_back("VBUS PRE-CONTRACT CAPACITANCE (decision needed — the round-5 inlet eFuse is GONE from the netlist): the PD source sees "+f(iu+bu,1)+" uF un-switched ("+cap_detail(ci)+") vs the ~10 uF cSnkBulk guidance; restore an inrush-limited path (TPS2663-class eFuse with dVdT control) between the receptacle and the board bulk.");return;
    }
    if(iu>10) {
        res.findings.push_back("VBUS PRE-CONTRACT CAPACITANCE: "+inlet+" (ahead of the eFuse) carries "+f(iu,1)+" uF nominal ("+cap_detail(ci)+") — above the ~10 uF cSnkBulk guidance; keep the receptacle side lean and let the dVdT eFuse charge the bulk.");return;
    }
    std::string slew_note;
    for(const auto& s:sheets) {
        ModelSheetIndex idx(s.circuit);
        for(const auto* r:efuses)if(r->sheet==s.name) {
            auto p=idx.part(r->ref);if(!p)throw ModelCheckError("power checks: missing eFuse part "+s.name+":"+r->ref);
            auto n=idx.alias_net(*p,"dVdT");if(!n)continue;
            for(const auto& pin:n->pins)if(auto cp=idx.part(pin.ref);cp&&ends(cp->lib_id,":C"))
                if(auto cv=parse_si_value(cp->value);cv&&*cv!=0) {
                    double slew=1.0/(20.8e3 * *cv),inrush=bu*1e-6*slew*1e3;
                    slew_note="; dVdT "+cp->value+" -> slew "+f(slew/1e3,2)+" V/ms, inrush into the bulk ~"+f(inrush,0)+" mA";
                }
        }
    }
    std::vector<std::string> names;for(auto r:efuses)names.push_back(r->sheet+":"+r->ref+" "+r->value);
    res.notes.push_back("VBUS pre-contract audit (round-4 flag, RESOLVED round 5): source sees "+f(iu,2)+" uF at the receptacle ("+inlet+") — within the ~10 uF cSnkBulk guidance; "+f(bu,1)+" uF board bulk sits behind the "+join(names,", ")+" eFuse"+slew_note+".");
}
} // namespace

PowerCheckResult detect_power_regulators(const std::vector<ProjectCircuit>& sheets,const PowerPolicy& policy) {
    PowerCheckResult res;detect(sheets,policy,res);return res;
}

PowerCheckResult analyze_power(const std::vector<ProjectCircuit>& sheets,const PowerPolicy& policy) {
    auto res=detect_power_regulators(sheets,policy);std::set<std::string> all_rails;
    for(const auto& s:sheets) {
        for(const auto& n:s.circuit.nets)if(n.net_class=="power")all_rails.insert(n.name);
        for(const auto& l:s.circuit.loads) {
            auto v=find(res.draws,l.rail);if(!v){res.draws.emplace_back(l.rail,std::vector<PowerDraw>{});v=&res.draws.back().second;}
            v->push_back({s.name,l.amps,l.note});
        }
    }
    std::map<std::string,std::vector<std::size_t>> by_vin;std::set<std::string> has_load;
    for(const auto& d:res.draws)has_load.insert(d.first);
    for(std::size_t i=0;i<res.regs.size();++i){by_vin[res.regs[i].vin].push_back(i);has_load.insert(res.regs[i].vin);}
    std::map<std::string,std::vector<std::string>> bridge_down;
    for(const auto& b:res.bridges) {
        bool ad=has_load.count(b.from),bd=has_load.count(b.to);
        if(bd&&!ad)bridge_down[b.from].push_back(b.to);else if(ad&&!bd)bridge_down[b.to].push_back(b.from);
    }
    std::set<std::string> visiting;
    std::function<double(const std::string&)> total=[&](const std::string& rail)->double {
        if(auto p=find(res.rails,rail))return *p;
        if(visiting.count(rail)){res.errors.push_back("power-tree CYCLE through rail "+repr(rail));return 0;}
        visiting.insert(rail);FloatSum sum;
        if(auto ds=find(res.draws,rail))for(const auto& d:*ds)sum.add(d.amps);
        double load=sum.value();
        if(auto it=by_vin.find(rail);it!=by_vin.end())for(auto i:it->second) {
            auto& reg=res.regs[i];reg.i_out=total(reg.vout);
            if(reg.kind=="buck") {
                double vin=rail_volts(reg.vin,policy).value_or(0),vout=rail_volts(reg.vout,policy).value_or(0);
                if(vin&&reg.eff==0)throw ModelCheckError("power checks: zero buck efficiency");
                reg.i_in=vin?vout*reg.i_out/(vin*reg.eff):0;
            }else reg.i_in=reg.i_out;
            load+=reg.i_in;
        }
        if(auto it=bridge_down.find(rail);it!=bridge_down.end())for(const auto& down:it->second)load+=total(down);
        visiting.erase(rail);load=py_round(load,4);set(res.rails,rail,load);return load;
    };
    for(const auto& rail:all_rails)total(rail);
    for(const auto& r:res.regs)if(r.i_out>r.limit_a+1e-9)res.errors.push_back("OVERRUN: "+r.sheet+":"+r.ref+" ("+r.value+") "+r.vin+" -> "+r.vout+": load "+f(r.i_out,3)+" A > limit "+f(r.limit_a,3)+" A ("+r.note+")");
    std::set<std::string> sourced,children;
    for(const auto& [rail,src]:policy.sources) {
        sourced.insert(rail);auto p=find(res.rails,rail);double load=p?*p:0;res.source_load.emplace_back(rail,load);
        if(load>src.amps+1e-9)res.errors.push_back("OVERRUN: source "+rail+" ("+src.note+"): load "+f(load,3)+" A > "+f(src.amps,3)+" A");
    }
    for(const auto& r:res.regs)sourced.insert(r.vout);
    for(const auto& b:res.bridges){sourced.insert(b.from);sourced.insert(b.to);children.insert(b.to);}
    for(const auto& rail:all_rails)if(!sourced.count(rail)) {
        auto p=find(res.rails,rail);double load=p?*p:0;
        if(auto def=find(policy.known_deferred,rail))res.warnings.push_back("unsourced rail "+rail+" (load "+f(load,3)+" A) — KNOWN deferral: "+*def);
        else res.findings.push_back("UNSOURCED RAIL "+rail+" (declared load "+f(load,3)+" A): no regulator output, no source contract — needs a gate/tie decision before layout");
    }
    for(const auto& rail:children) {
        auto ds=find(res.draws,rail);auto def=find(policy.known_deferred,rail);
        if((!ds||ds->empty())&&!by_vin.count(rail)&&def)res.warnings.push_back("shunt-bridge rail "+rail+" feeds nothing — "+*def);
    }
    precontract(sheets,res);
    std::set<std::string> jrails,outs;
    for(const auto& s:sheets)if(starts(s.name,"som_j"))for(const auto& n:s.circuit.nets)if(n.net_class=="power"&&(n.name=="+3V3"||n.name=="+1V8"))jrails.insert(n.name);
    for(const auto& r:res.regs)outs.insert(r.vout);
    std::vector<std::string> clash;std::set_intersection(jrails.begin(),jrails.end(),outs.begin(),outs.end(),std::back_inserter(clash));
    if(!clash.empty())res.findings.push_back("PARALLEL-SOURCE QUESTION on "+join(clash,", ")+": these rails are OUTPUTS of carrier regulators (power.py LM61460/AP2112K) AND appear on SoM J1 contract pins (+3V3: J1.24-27, +1V8: J1.56/58/60) while the SoM's own Power sheet regulates same-named rails on-module (MPM3834 stages with 3V3_EN/PG + 1V8_EN/PG). If the SoM exports its rails on those pins, linking them to the carrier's bucks puts two regulators in parallel on one net — needs an explicit decision (rename one side, sense-only pins, or drop one source) before layout. Facts from som_interface.json + som/schematic/Power.kicad_sch; nothing changed here.");
    return res;
}

std::string power_report(const PowerCheckResult& res,const PowerPolicy& policy) {
    std::vector<std::string> ls{"schgen power-tree budget gate",std::string(64,'='),"","sources:"};
    for(const auto& [rail,s]:policy.sources) {
        auto p=find(res.source_load,rail);double load=p?*p:0,pct=s.amps?100*load/s.amps:0;
        ls.push_back("  "+pad(rail,10)+" "+pad(f(s.volts,1),5,true)+" V  limit "+f(s.amps,2)+" A  load "+f(load,3)+" A  ("+f(pct,0)+"%)  — "+s.note);
    }
    ls.insert(ls.end(),{"","regulators ("+std::to_string(res.regs.size())+") — numbered as in carrier/docs/power_tree.svg:"});
    for(const auto& r:res.regs)ls.push_back("  ("+pad(std::to_string(r.n),2,true)+") "+r.sheet+":"+pad(r.ref,4)+" "+pad(r.value,14)+" "+pad(r.vin,9,true)+" -> "+pad(r.vout,14)+" load "+f(r.i_out,3)+" A / limit "+f(r.limit_a,3)+" A ("+f(r.limit_a?100*r.i_out/r.limit_a:0,0)+"%)  in "+f(r.i_in,3)+" A ["+r.kind+"] "+r.note);
    ls.insert(ls.end(),{"","shunt bridges (series R rail->rail, power_mon):"});
    for(const auto& b:res.bridges)ls.push_back("  "+b.sheet+":"+b.ref+" "+b.from+" -> "+b.to);
    ls.insert(ls.end(),{"","declared draws (c.draws — every number cites its source):"});
    for(const auto& [rail,ds]:sorted(res.draws))for(const auto& d:ds)ls.push_back("  "+pad(rail,16)+" "+pad(f(d.amps*1000,1),8,true)+" mA  "+pad(d.sheet,18)+" "+d.note);
    ls.insert(ls.end(),{"","rail totals (declared + child regulator inputs):"});
    for(const auto& [rail,total]:sorted(res.rails)){auto v=rail_volts(rail,policy);ls.push_back("  "+pad(rail,16)+" "+pad(f(total,3),7,true)+" A"+(v&&*v!=0?"  @ "+f(*v,1)+" V":""));}
    if(!res.notes.empty()){ls.insert(ls.end(),{"","notes — resolved audits, recomputed every run ("+std::to_string(res.notes.size())+"):"});for(const auto& n:res.notes)ls.push_back("  + "+n);}
    if(!res.findings.empty()){ls.insert(ls.end(),{"","FINDINGS — decisions needed ("+std::to_string(res.findings.size())+"):"});for(const auto& n:res.findings)ls.push_back("  * "+n);}
    if(!res.warnings.empty()){ls.insert(ls.end(),{"","warnings ("+std::to_string(res.warnings.size())+"):"});for(const auto& n:res.warnings)ls.push_back("  WARNING: "+n);}
    ls.push_back("");
    if(!res.errors.empty()){ls.push_back("ERRORS ("+std::to_string(res.errors.size())+"):");for(const auto& n:res.errors)ls.push_back("  ERROR: "+n);}else ls.push_back("errors: none");
    ls.insert(ls.end(),{"",std::string("POWER TREE: ")+(res.ok()?"PASS":"FAIL")+" ("+std::to_string(res.errors.size())+" errors, "+std::to_string(res.findings.size())+" findings, "+std::to_string(res.warnings.size())+" warnings)"});return join(ls);
}

std::string power_svg(const PowerCheckResult& res,const PowerPolicy& policy) {
    std::map<std::string,int> depth;for(const auto& s:policy.sources)depth[s.first]=0;
    // The legacy relaxation never terminates for a source-reachable cycle.
    // Bound by graph vertices; do not publish a partial/misleading diagram.
    const auto bound=res.regs.size()+policy.sources.size()+1;
    bool changed=true;std::size_t pass=0;
    while(changed) {
        if(++pass>bound)throw ModelCheckError("power-tree SVG: source-reachable regulator cycle");
        changed=false;
        for(const auto& r:res.regs)if(auto it=depth.find(r.vin);it!=depth.end()) {
            int d=it->second+1;auto target=depth.find(r.vout);
            if(target==depth.end()||target->second<d){depth[r.vout]=d;changed=true;}
        }
    }
    for(const auto& b:res.bridges)if(depth.count(b.from)&&!depth.count(b.to))depth[b.to]=depth.at(b.from)+1;
    std::vector<std::string> orphans;for(const auto& [rail,v]:sorted(res.rails)){(void)v;if(!depth.count(rail))orphans.push_back(rail);}
    std::map<int,std::vector<std::string>> cols;for(const auto& [rail,d]:depth)cols[d].push_back(rail);
    std::vector<std::pair<std::string,std::pair<int,int>>> pos;
    int height=60,maxd=cols.empty()?0:cols.rbegin()->first;
    for(const auto& [d,rails]:cols){int y=50;for(const auto& rail:rails){pos.push_back({rail,{30+d*330,y}});y+=66;}height=std::max(height,y);}
    int oy=height+30,legend_h=22+16*(int(res.regs.size())+1),total_h=oy+90+18*(int(orphans.size())/4+1)+legend_h,width=30+maxd*330+190+60;
    auto i=[](auto v){return std::to_string(v);};
    auto esc=[](std::string s){replace_all(s,"&","&amp;");replace_all(s,"<","&lt;");replace_all(s,">","&gt;");return s;};
    std::vector<std::string> e{"<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 "+i(width)+" "+i(total_h)+"\" font-family=\"ui-monospace, SFMono-Regular, Menlo, monospace\" font-size=\"11\">",
        "<rect width=\""+i(width)+"\" height=\""+i(total_h)+"\" fill=\"white\"/>",
        "<text x=\"30\" y=\"28\" font-size=\"15\" font-weight=\"bold\">carrier power tree — budget gate ("+std::string(res.ok()?"PASS":"FAIL")+")</text>"};
    for(const auto& r:res.regs) {
        auto a=find(pos,r.vin),b=find(pos,r.vout);if(!a||!b)continue;
        int ax=a->first+190,ay=a->second+20,bx=b->first,by=b->second+20;
        std::string color=r.i_out>r.limit_a?"#dc2626":"#2563eb";
        e.push_back("<path d=\"M"+i(ax)+","+i(ay)+" C"+i(ax+60)+","+i(ay)+" "+i(bx-110)+","+i(by)+" "+i(bx)+","+i(by)+"\" fill=\"none\" stroke=\""+color+"\" stroke-width=\"2\"/>");
        std::string label="("+i(r.n)+") "+f(r.i_out,2)+"/"+f(r.limit_a,2)+"A";
        e.push_back("<rect x=\""+i(bx-106)+"\" y=\""+i(by-16)+"\" width=\""+i(chars(label)*7)+"\" height=\"14\" fill=\"white\" fill-opacity=\"0.85\"/>");
        e.push_back("<text x=\""+i(bx-104)+"\" y=\""+i(by-5)+"\" fill=\""+color+"\">"+esc(label)+"</text>");
    }
    for(const auto& r:res.bridges) {
        auto a=find(pos,r.from),b=find(pos,r.to);if(!a||!b)continue;
        e.push_back("<line x1=\""+i(a->first+190)+"\" y1=\""+i(a->second+20)+"\" x2=\""+i(b->first)+"\" y2=\""+i(b->second+20)+"\" stroke=\"#9ca3af\" stroke-width=\"1.5\" stroke-dasharray=\"5,4\"/>");
    }
    for(const auto& [rail,xy]:pos) {
        int x=xy.first,y=xy.second;auto src=find(policy.sources,rail);
        std::string fill=src?"#fef3c7":"#eff6ff",stroke=src?"#92400e":"#1e3a8a";
        e.push_back("<rect x=\""+i(x)+"\" y=\""+i(y)+"\" width=\"190\" height=\"40\" rx=\"8\" fill=\""+fill+"\" stroke=\""+stroke+"\" stroke-width=\"1.5\"/>");
        auto v=rail_volts(rail,policy);
        e.push_back("<text x=\""+i(x+10)+"\" y=\""+i(y+16)+"\" font-weight=\"bold\" font-size=\"12\">"+esc(rail)+(v&&*v!=0?" ("+g(*v)+" V)":"")+"</text>");
        auto load=find(res.rails,rail);
        e.push_back("<text x=\""+i(x+10)+"\" y=\""+i(y+32)+"\" fill=\"#374151\">load "+f(load?*load:0,3)+" A"+(src?" / "+g(src->amps)+" A":"")+"</text>");
    }
    e.push_back("<text x=\"30\" y=\""+i(oy)+"\" font-weight=\"bold\" fill=\"#6b7280\">unsourced rails (PLAN deferrals / findings):</text>");
    for(std::size_t n=0;n<orphans.size();++n)e.push_back("<text x=\""+i(30+(n%4)*200)+"\" y=\""+i(oy+18+18*(n/4))+"\" fill=\"#6b7280\">"+esc(orphans[n])+" ("+f(*find(res.rails,orphans[n]),3)+" A)</text>");
    int ly=oy+60+18*(int(orphans.size())/4+1);
    e.push_back("<text x=\"30\" y=\""+i(ly)+"\" font-weight=\"bold\">regulators:</text>");
    for(std::size_t n=0;n<res.regs.size();++n){const auto& r=res.regs[n];e.push_back("<text x=\"30\" y=\""+i(ly+18+16*n)+"\" fill=\"#374151\">("+i(r.n)+") "+esc(r.sheet)+":"+esc(r.ref)+" "+esc(r.value)+" "+esc(r.vin)+" -&gt; "+esc(r.vout)+" — load "+f(r.i_out,3)+" A / limit "+f(r.limit_a,3)+" A ["+r.kind+"]</text>");}
    e.push_back("</svg>");return join(e)+"\n";
}

PowerCheckResult run_power_checks(const std::vector<ProjectCircuit>& sheets,const std::filesystem::path& reports,const std::filesystem::path& docs,const PowerPolicy& policy) {
    auto res=analyze_power(sheets,policy);auto svg=power_svg(res,policy);
    publish(reports/"power_tree.txt",power_report(res,policy)+"\n");publish(docs/"power_tree.svg",svg);return res;
}

JsonNode power_result_json(const PowerCheckResult& res) {
    auto regs=arr(),bridges=arr(),draws=obj();
    for(const auto& r:res.regs)regs.array_value.push_back(obj({{"n",j(double(r.n))},{"sheet",j(r.sheet)},{"ref",j(r.ref)},{"value",j(r.value)},{"kind",j(r.kind)},{"vin",j(r.vin)},{"vout",j(r.vout)},{"limit_a",j(r.limit_a)},{"eff",j(r.eff)},{"note",j(r.note)},{"i_out",j(r.i_out)},{"i_in",j(r.i_in)}}));
    for(const auto& b:res.bridges)bridges.array_value.push_back(arr({j(b.sheet),j(b.ref),j(b.from),j(b.to)}));
    for(const auto& [rail,ds]:res.draws){auto es=arr();for(const auto& d:ds)es.array_value.push_back(arr({j(d.sheet),j(d.amps),j(d.note)}));draws.object_value.emplace_back(rail,std::move(es));}
    return obj({{"regs",regs},{"rails",number_map(res.rails)},{"draws",draws},{"bridges",bridges},{"errors",strings(res.errors)},{"warnings",strings(res.warnings)},{"findings",strings(res.findings)},{"notes",strings(res.notes)},{"source_load",number_map(res.source_load)}});
}

PowerCheckResult power_result_from_json(const JsonNode& n) {
    object_shape(n,{"regs","rails","draws","bridges","errors","warnings","findings","notes","source_load"},"power result");
    PowerCheckResult r;
    for(const auto& v:array_items(member(n,"regs"))) {
        object_shape(v,{"n","sheet","ref","value","kind","vin","vout","limit_a","eff","note","i_out","i_in"},"power regulator");
        r.regs.push_back({signed_int(member(v,"n")),string(member(v,"sheet")),string(member(v,"ref")),string(member(v,"value")),string(member(v,"kind")),string(member(v,"vin")),string(member(v,"vout")),number(member(v,"limit_a")),number(member(v,"eff")),string(member(v,"note")),number(member(v,"i_out")),number(member(v,"i_in"))});
    }
    r.rails=read_number_map(member(n,"rails"));r.source_load=read_number_map(member(n,"source_load"));
    const auto& draws=member(n,"draws");unique_map(draws);
    for(const auto& [rail,ds]:draws.object_value){std::vector<PowerDraw> entries;for(const auto& v:array_items(ds)){auto& a=tuple_items(v,3);entries.push_back({string(a[0]),number(a[1]),string(a[2])});}r.draws.emplace_back(rail,std::move(entries));}
    for(const auto& v:array_items(member(n,"bridges"))){auto& a=tuple_items(v,4);r.bridges.push_back({string(a[0]),string(a[1]),string(a[2]),string(a[3])});}
    r.errors=read_strings(member(n,"errors"));r.warnings=read_strings(member(n,"warnings"));r.findings=read_strings(member(n,"findings"));r.notes=read_strings(member(n,"notes"));return r;
}

} // namespace schgen
