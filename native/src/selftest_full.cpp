#include "selftest_full_internal.hpp"
#include "schgen/process.hpp"
#include <cstdlib>
#include <cerrno>
#include <system_error>
#include <unistd.h>

namespace schgen {
using namespace selftesting;

std::string SelftestStackVerdict::killed_by() const {
    std::vector<std::string> head(failures.begin(),failures.begin()+std::min<std::size_t>(2,failures.size()));
    return join(head,"; ")+(failures.size()>2?" (+"+std::to_string(failures.size()-2)+" more)":"");
}
SelftestBuilt build_selftest_sheet(const CircuitSheetIr& c,SymbolLibrary& lib,const fs::path& outdir){
    safe_name(c.name);validate_circuit(c,lib);
    auto page=place_and_route_schematic(c,lib);
    auto emitted=emit_schematic(design(page),[&](const std::string& id)->const SymbolDef&{return lib.get(id);});
    const auto file=outdir/(c.name+".kicad_sch");publish(file,emitted.text);
    return {c,file,std::move(emitted.text),std::move(page)};
}
SelftestStackVerdict selftest_gate_stack(const CircuitSheetIr& c,const fs::path& sch,
        SymbolLibrary& lib,const SheetGeometry* geo,const NetlistExtractOptions& options){
    SelftestStackVerdict v;const auto net=check_netlist(c,sch,options);
    if(net.ok)v.passed.push_back("netlist");
    else {auto ls=lines(net.summary());v.failures.push_back("netlist gate: "+trim(ls.at(1)));}
    auto project=sch;project.replace_extension(".kicad_pro");
    publish(project,board_project_json(obj(),sch.stem().string()));
    const auto erc=run_kicad_erc(sch,options);auto report=sch;report.replace_extension(".erc.rpt");
    auto txt=strip_board_report_timestamp(erc.report.empty()?erc.stderr_text:erc.report);publish(report,txt);
    // KiCad uses 5 for rule violations. A crash, bad invocation or missing
    // report is an infrastructure error, never evidence of a killed mutant.
    if((erc.exit_code!=0&&erc.exit_code!=5)||erc.report.empty())
        throw SomInterfaceError("selftest ERC failed to run on "+sch.string()+": exit "+
            std::to_string(erc.exit_code)+": "+erc.stderr_text);
    if(!erc.exit_code)v.passed.push_back("erc");
    else {
        std::string line="errors > 0";
        for(auto s:lines(txt)){auto lower=s;for(auto& ch:lower)if(ch>='A'&&ch<='Z')ch=char(ch-'A'+'a');
            if(lower.find("; error")!=lower.npos||s.find('[')!=s.npos){line=trim(s);break;}}
        v.failures.push_back("ERC gate: "+shorten(line,120));
    }
    const auto driven=check_inputs_driven(c,lib);
    if(driven.empty())v.passed.push_back("inputs-driven");else v.failures.push_back("inputs-driven gate: "+driven.front());
    if(geo){const auto visual=check_visual_geometry(*geo);if(visual.ok)v.passed.push_back("visual");else v.failures.push_back("visual gate: "+visual.findings.front());}
    return v;
}
std::vector<SelftestMutation> selftest_sheet_mutations(const SelftestBuilt& b,SymbolLibrary& lib){
    std::vector<SelftestMutation> out;
    auto addtext=[&](std::string name,std::string desc,const Sexpr& doc){SelftestMutation m;m.name=std::move(name);m.description=std::move(desc);m.text=sexpr_dumps(doc)+"\n";out.push_back(std::move(m));};
    {auto c=b.circuit;std::vector<CircuitNetIr*> nets;for(auto& n:c.nets)if(!n.pins.empty())nets.push_back(&n);
        std::stable_sort(nets.begin(),nets.end(),[](auto a,auto b){return a->name<b->name;});
        if(nets.size()>=2){auto& a=*nets[0];auto& z=*nets[1];std::string desc="pin swap: "+pin(a.pins[0])+" ("+repr(a.name)+") <-> "+pin(z.pins[0])+" ("+repr(z.name)+")";
            std::swap(a.pins[0],z.pins[0]);SelftestMutation m;m.name="mutate_pin_swap";m.description=desc;m.circuit=std::move(c);out.push_back(std::move(m));}}
    {auto doc=sexpr_loads(b.text);Sexpr* label=nullptr;
        for(const auto& name:{"global_label","hierarchical_label","label"}){for(auto& n:sl(doc))if(tag(n,name)){label=&n;break;}if(label)break;}
        if(label){const auto old=atom(sl(*label).at(1));std::vector<const CircuitNetIr*> targets;
            for(const auto& n:b.circuit.nets)if(n.name!=old&&!n.pins.empty())targets.push_back(&n);
            std::stable_sort(targets.begin(),targets.end(),[](auto a,auto b){return std::make_pair(a->net_class!="ground",a->name)<std::make_pair(b->net_class!="ground",b->name);});
            if(!targets.empty()){sl(*label)[1]=Sexpr{targets[0]->name};addtext("mutate_label_alias","label alias: label "+repr(old)+" rewritten to "+repr(targets[0]->name),doc);}}}
    {auto parts=b.page.placement.parts;std::stable_sort(parts.begin(),parts.end(),[](auto& a,auto& b){return a.ref<b.ref;});bool done=false;
        ModelSheetIndex idx(b.circuit);
        for(const auto& p:parts){for(const auto& pin:lib.get(p.lib_id).pins){if(!idx.net(p.ref,pin.number))continue;
                auto [x,y]=pin_page_position(pin,p.x,p.y,p.rotation);auto doc=sexpr_loads(b.text);
                auto nc=node("no_connect",{node("at",{{x},{y}}),node("uuid",{{schematic_stable_uuid({b.circuit.name,"selftest-stray-nc"})}})});
                sl(doc).insert(sl(doc).end()-1,std::move(nc));addtext("mutate_stray_nc","stray NC on netted pin "+p.ref+"."+pin.number+" @("+pf(x)+","+pf(y)+")",doc);done=true;break;}
            if(done)break;}}
    {std::map<std::string,std::vector<VisualSegment>> by_net;
        for(const auto& s:b.page.routed.segs)by_net[s.net].push_back({s.x0,s.y0,s.x1,s.y1,s.net});
        if(by_net.size()>=2){auto ia=by_net.begin(),ib=std::next(ia);auto pick=[](const auto& xs){return *std::max_element(xs.begin(),xs.end(),[](const auto& a,const auto& b){return length(a)<length(b);});};
            auto midpoint=[](const VisualSegment& s){return std::make_pair(py_round(py_round(((s.x0+s.x1)/2)/symbol_grid,0)*symbol_grid,2),py_round(py_round(((s.y0+s.y1)/2)/symbol_grid,0)*symbol_grid,2));};
            auto [ax,ay]=midpoint(pick(ia->second));auto [bx,by]=midpoint(pick(ib->second));auto doc=sexpr_loads(b.text);std::size_t id=0;
            auto uuid=[&](){return node("uuid",{{schematic_stable_uuid({b.circuit.name,"selftest-bridge",std::to_string(id++)})}});};
            auto wire=[&](double x0,double y0,double x1,double y1){return node("wire",{node("pts",{node("xy",{{x0},{y0}}),node("xy",{{x1},{y1}})}),node("stroke",{node("width",{{0.0}}),node("type",{sym("default")})}),uuid()});};
            auto junction=[&](double x,double y){return node("junction",{node("at",{{x},{y}}),node("diameter",{{0.0}}),node("color",{{0.0},{0.0},{0.0},{0.0}}),uuid()});};
            auto append=[&](Sexpr n){sl(doc).insert(sl(doc).end()-1,std::move(n));};
            if(ax!=bx)append(wire(ax,ay,bx,ay));if(ay!=by)append(wire(bx,ay,bx,by));append(junction(ax,ay));append(junction(bx,by));
            addtext("mutate_foreign_junction","foreign junction: bridge "+repr(ia->first)+"@("+pf(ax)+","+pf(ay)+") -> "+repr(ib->first)+"@("+pf(bx)+","+pf(by)+") with junctioned contacts",doc);}}
    {const auto original=sexpr_loads(b.text);std::size_t count=0;
        for(std::size_t i=0;i<sl(original).size();++i)if(tag(sl(original)[i],"wire")){
            std::string coords="?";if(auto pts=child(sl(original)[i],"pts")){std::vector<std::string> nums;for(const auto& xy:sl(*pts))if(tag(xy,"xy"))for(std::size_t k=1;k<sl(xy).size();++k)nums.push_back(sexpr_fmt_num(number_at(xy,k)));coords=join(nums," ");}
            auto doc=original;sl(doc).erase(sl(doc).begin()+static_cast<std::ptrdiff_t>(i));const auto index=std::to_string(count++);
            addtext("mutate_wire_delete_"+index,"wire delete #"+index+" ["+coords+"]",doc);}}
    {auto geo=rebuild_geo(b);bool done=false;
        for(const auto& v:geo.wires){if(std::abs(v.x0-v.x1)>=1e-6)continue;
            const auto lo=std::min(v.y0,v.y1),hi=std::max(v.y0,v.y1);
            for(std::size_t i=0;i<geo.wires.size();++i){const auto h=geo.wires[i];if(std::abs(h.y0-h.y1)>=1e-6||h.net==v.net)continue;
                const auto mid=py_round((lo+hi)/2,3);if(!(lo<mid&&mid<hi))continue;
                const auto span=std::max(std::abs(h.x1-h.x0),2*symbol_grid);
                auto desc="geo: wire "+repr(h.net)+" shifted to cross foreign "+repr(v.net)+" @("+pf(v.x0)+","+pf(mid)+")";
                geo.wires[i]={py_round(v.x0-span/2,3),mid,py_round(v.x0+span/2,3),mid,h.net};
                SelftestMutation m;m.name="mutate_geo_wire_crosses_foreign";m.description=desc;m.geometry=std::move(geo);out.push_back(std::move(m));done=true;break;}
            if(done)break;}}
    {auto geo=rebuild_geo(b);auto box=std::find_if(geo.boxes.begin(),geo.boxes.end(),[](const auto& x){return x.kind=="value";});
        if(box!=geo.boxes.end()&&!geo.wires.empty()){
            const auto& w=*std::max_element(geo.wires.begin(),geo.wires.end(),[](const auto& a,const auto& b){return length(a)<length(b);});
            const auto x=py_round((w.x0+w.x1)/2,3),y=py_round((w.y0+w.y1)/2,3),dx=box->x1-box->x0,dy=box->y1-box->y0;
            auto desc="geo: value box "+repr(box->owner)+" dragged onto wire "+repr(w.net)+" @("+pf(x)+","+pf(y)+")";
            *box={py_round(x-dx/2,3),py_round(y-dy/2,3),py_round(x+dx/2,3),py_round(y+dy/2,3),box->kind,box->owner};
            SelftestMutation m;m.name="mutate_geo_text_over_wire";m.description=desc;m.geometry=std::move(geo);out.push_back(std::move(m));}}
    return out;
}

SelftestSheetResult selftest_sheet(const SelftestSheetInput& input,SymbolLibrary& lib,
        const fs::path& scratch,const NetlistExtractOptions& options){
    auto b=build_selftest_sheet(input.circuit,lib,scratch/"base");SelftestSheetResult out;out.name=b.circuit.name;
    std::vector<std::string> log={"--- "+out.name+" ("+input.display_path+") ---"};
    out.baseline=selftest_gate_stack(b.circuit,b.schematic,lib,&b.page.geometry,options);
    if(!out.baseline.green()){out.problems.push_back(out.name+": baseline NOT green: "+out.baseline.killed_by());
        log.push_back("  baseline: FAIL — "+out.baseline.killed_by());out.report=join(log);return out;}
    log.push_back("  baseline: green ("+join(out.baseline.passed,", ")+")");const auto mutations=selftest_sheet_mutations(b,lib);
    for(const auto& name:{"mutate_pin_swap","mutate_label_alias","mutate_stray_nc","mutate_foreign_junction","mutate_geo_wire_crosses_foreign","mutate_geo_text_over_wire"}){
        if(std::none_of(mutations.begin(),mutations.end(),[&](const auto& m){return m.name==name;})){
            const bool geo=starts(name,"mutate_geo");out.problems.push_back(out.name+": "+(geo?"geometry mutation ":"mutation ")+name+
                (geo?" NOT APPLICABLE — fixture lacks the geometry to exercise the visual gate":" NOT APPLICABLE — fixture too small to exercise the gate"));}}
    std::size_t k=0;
    for(const auto& m:mutations){++out.injected;auto file=b.schematic;
        if(m.text){file=scratch/"mut"/(out.name+".mut"+(k<10?"0":"")+std::to_string(k)+".kicad_sch");publish(file,*m.text);}if(!m.geometry)++k;
        auto verdict=selftest_gate_stack(m.circuit?*m.circuit:b.circuit,file,lib,m.geometry?&*m.geometry:nullptr,options);
        bool kill=!verdict.green();
        if(!kill){out.problems.push_back(out.name+(m.geometry?": GEOMETRY MUTANT SURVIVED every gate: ":": MUTANT SURVIVED every gate: ")+m.description);
            log.push_back("  SURVIVED  "+m.description+(m.geometry?"   <-- HOLE IN THE VISUAL GATE":"   <-- HOLE IN THE GATE STACK"));}
        else if(m.geometry&&std::none_of(verdict.failures.begin(),verdict.failures.end(),[](const auto& s){return starts(s,"visual gate");})){
            kill=false;out.problems.push_back(out.name+": geometry mutant killed by a NON-visual gate ("+verdict.killed_by()+"): "+m.description);
            log.push_back("  MISCREDIT "+m.description+"   <-- not the visual gate");}
        else {++out.killed;log.push_back("  killed    "+m.description+"\n            by "+verdict.killed_by());}
        out.mutations.push_back({m.name,m.description,std::move(verdict),kill});
    }
    out.report=join(log);return out;
}

SelftestDeterminism selftest_determinism(const CircuitSheetIr& c,SymbolLibrary& lib,const fs::path& scratch){
    const auto a=build_selftest_sheet(c,lib,scratch/"det1"),b=build_selftest_sheet(c,lib,scratch/"det2");
    if(a.text==b.text)return {true,"byte-identical (uuids included, zero tolerance)"};
    return {false,"DRIFT between two builds:\n    "+drift_diff(a.text,b.text,"build-1","build-2")};
}
SelftestFullResult run_full_selftest(const std::vector<SelftestSheetInput>& sheets,
        const SelftestModelFixtures& fixtures,SymbolLibrary& lib,const SelftestFullOptions& options){
    if(options.worker_command.empty())throw std::invalid_argument("selftest requires a native worker command for cross-process determinism");
    if(sheets.empty())throw std::invalid_argument("selftest requires at least one sheet");
    if(options.worker_timeout.count()<=0)throw std::invalid_argument("selftest worker timeout must be positive");
    std::set<std::string> names;
    for(const auto& input:sheets){
        const auto name=input.scratch_name.empty()?input.circuit.name:input.scratch_name;
        safe_name(name);safe_name(input.circuit.name);
        if(!names.insert(name).second)throw std::invalid_argument("selftest duplicate scratch name: "+name);
    }
    const auto parent=options.scratch_parent.empty()?fs::temp_directory_path():options.scratch_parent;
    auto pattern=(parent/"schgen_selftest_XXXXXX").string();std::vector<char> bytes(pattern.begin(),pattern.end());bytes.push_back('\0');
    if(!::mkdtemp(bytes.data()))throw std::system_error(errno,std::generic_category(),"selftest scratch");
    struct Cleanup {fs::path path;bool keep;~Cleanup(){if(!keep){std::error_code ec;fs::remove_all(path,ec);}}} cleanup{fs::path(bytes.data()),options.keep};
    SelftestFullResult out;out.scratch=cleanup.path;std::vector<std::string> log;
    auto say=[&](const std::string& s){log.push_back(s);if(options.progress)options.progress(s+"\n");};
    say("schgen selftest — gate mutation testing + determinism ("+std::to_string(sheets.size())+" sheets, scratch "+out.scratch.string()+")");
    for(const auto& input:sheets){const auto name=input.scratch_name.empty()?input.circuit.name:input.scratch_name;safe_name(name);const auto tmp=out.scratch/name;
        auto result=selftest_sheet(input,lib,tmp,options.extraction);say(result.report);
        result.determinism=selftest_determinism(input.circuit,lib,tmp);
        say("  determinism: "+std::string(result.determinism.ok?"PASS":"FAIL")+" — "+result.determinism.diagnostic);
        if(!result.determinism.ok)result.problems.push_back(name+": determinism FAIL");
        result.hashseed=selftest_hashseed_determinism(input.circuit,lib,tmp,options);
        say("  hash-seed:   "+std::string(result.hashseed.ok?"PASS":"FAIL")+" — "+result.hashseed.diagnostic);
        if(!result.hashseed.ok)result.problems.push_back(name+": hash-seed determinism FAIL");
        out.injected+=result.injected;out.killed+=result.killed;out.problems.insert(out.problems.end(),result.problems.begin(),result.problems.end());out.sheets.push_back(std::move(result));}
    out.models=selftest_model_gates(fixtures,lib,out.scratch/"model_gates",options.extraction);say(out.models.report);
    out.injected+=out.models.injected;out.killed+=out.models.killed;out.problems.insert(out.problems.end(),out.models.problems.begin(),out.models.problems.end());
    if(options.keep)say("scratch kept: "+out.scratch.string());say("");
    const auto counts=std::to_string(out.killed)+"/"+std::to_string(out.injected)+" mutants killed";
    if(out.ok())say("SELFTEST: PASS — "+counts+", determinism proven on "+std::to_string(sheets.size())+" sheet(s)");
    else {say("SELFTEST: FAIL — "+counts+"; "+std::to_string(out.problems.size())+" problem(s):");for(const auto& p:out.problems)say("  "+p);}
    out.report=join(log)+"\n";return out;
}
} // namespace schgen
