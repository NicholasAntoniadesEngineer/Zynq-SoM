// Independent, frozen CPython place.py template/mutation baselines. No Python,
// KiCad CLI, board outputs, generated native oracle, or installed symbol library
// is needed: the fixture directory includes standalone source symbol snapshots.
#include "../src/schematic_place_internal.hpp"
#include "schgen/json.hpp"
#include "schgen/sexpr.hpp"

#include <cmath>
#include <filesystem>
#include <functional>
#include <iomanip>
#include <iostream>
#include <sstream>

namespace {
using namespace schgen;
using namespace schgen::schematic_place;
using J = JsonNode;
namespace fs = std::filesystem;

void require(bool ok, const std::string& why) { if (!ok) throw std::runtime_error(why); }
const J& field(const J& node, const std::string& key) {
    const auto* value = object_field(node, key);
    require(value != nullptr, "fixture missing " + key); return *value;
}
std::string str(const J& node, const std::string& key) {
    const auto* value = object_field(node, key); return value ? value->string_value : "";
}
double num(const J& node, const std::string& key) { return field(node, key).number_value; }
J text(const std::string& value) { J n; n.kind=JsonKind::String; n.string_value=value; return n; }
J number(double value) { J n; n.kind=JsonKind::Number; n.number_value=value; return n; }
J boolean(bool value) { J n; n.kind=JsonKind::Bool; n.bool_value=value; return n; }
J array(std::vector<J> values={}) { J n; n.kind=JsonKind::Array; n.array_value=std::move(values); return n; }
J object(std::vector<std::pair<std::string,J>> values={}) { J n; n.kind=JsonKind::Object; n.object_value=std::move(values); return n; }
J point(Point p) { return array({number(p.first),number(p.second)}); }
J strings(const Refs& values) { auto n=array(); for(const auto& s:values)n.array_value.push_back(text(s)); return n; }
J strings(const std::set<std::string>& values) { return strings(Refs(values.begin(),values.end())); }
J numbers(const std::vector<double>& values) { auto n=array(); for(auto v:values)n.array_value.push_back(number(v)); return n; }
J refmap(const RefMap& values) {
    auto n=object(); for(const auto& [name,refs]:values)n.object_value.emplace_back(name,strings(refs)); return n;
}
Refs refs(const J& n) { Refs out; for(const auto& v:n.array_value)out.push_back(v.string_value); return out; }
RefMap parse_refmap(const J& n) {
    RefMap out; for(const auto& [key,value]:n.object_value)out[key]=refs(value); return out;
}
Point parse_point(const J& n) {
    require(n.kind==JsonKind::Array && n.array_value.size()==2,"invalid fixture point");
    return {n.array_value[0].number_value,n.array_value[1].number_value};
}
VisualBox parse_box(const J& n) { return {num(n,"x0"),num(n,"y0"),num(n,"x1"),num(n,"y1"),str(n,"kind"),str(n,"owner")}; }
Stage stage(const J& n) { return {str(n,"kind"),str(n,"out"),str(n,"sw"),str(n,"l")}; }
J stages(const StageMap& values) {
    auto out=object();
    for(const auto& [ref,st]:values) {
        auto row=object({{"kind",text(st.kind)}});
        if(st.kind=="buck") { row.object_value.emplace_back("sw",text(st.sw));row.object_value.emplace_back("l",text(st.inductor)); }
        row.object_value.emplace_back("out",text(st.out));out.object_value.emplace_back(ref,std::move(row));
    }
    return out;
}
J text_position(const std::optional<SchematicTextPosition>& p) {
    return p ? array({number(p->x),number(p->y),number(p->rotation)}) : J{};
}
J placement(const SchematicPlacement& p) {
    auto parts=array(),powers=array(),hlabels=array(),llabels=array(),ncs=array(),plans=object(),boxes=array();
    for(const auto& v:p.parts)parts.array_value.push_back(object({
        {"ref",text(v.ref)},{"lib_id",text(v.lib_id)},{"value",text(v.value)},
        {"x",number(v.x)},{"y",number(v.y)},{"rotation",number(v.rotation)},
        {"footprint",text(v.footprint)},{"ref_pos",text_position(v.ref_pos)},{"val_pos",text_position(v.val_pos)}}));
    for(const auto& v:p.powers)powers.array_value.push_back(object({
        {"lib_id",text(v.lib_id)},{"value",text(v.value)},{"ref",text(v.ref)},
        {"x",number(v.x)},{"y",number(v.y)},{"rotation",number(v.rotation)},
        {"net",text(v.net)},{"val_pos",text_position(v.val_pos)},{"show_value",boolean(v.show_value)}}));
    for(const auto& v:p.hlabels)hlabels.array_value.push_back(object({
        {"name",text(v.name)},{"x",number(v.x)},{"y",number(v.y)},{"rotation",number(v.rotation)},{"shape",text(v.shape)}}));
    for(const auto& v:p.llabels)llabels.array_value.push_back(object({
        {"name",text(v.name)},{"x",number(v.x)},{"y",number(v.y)},{"rotation",number(v.rotation)}}));
    for(const auto& v:p.no_connects)ncs.array_value.push_back(object({{"x",number(v.x)},{"y",number(v.y)}}));
    for(const auto& [name,paths]:p.plans) {
        auto lines=array();
        for(const auto& path:paths) { auto points=array();for(auto v:path)points.array_value.push_back(point(v));lines.array_value.push_back(std::move(points)); }
        plans.object_value.emplace_back(name,std::move(lines));
    }
    for(const auto& v:p.boxes)boxes.array_value.push_back(object({
        {"x0",number(v.x0)},{"y0",number(v.y0)},{"x1",number(v.x1)},{"y1",number(v.y1)},
        {"kind",text(v.kind)},{"owner",text(v.owner)}}));
    return object({{"parts",parts},{"powers",powers},{"hlabels",hlabels},{"llabels",llabels},{"no_connects",ncs},
        {"plans",plans},{"boxes",boxes},{"label_bridged",strings(p.label_bridged)},{"paper",text(p.paper)}});
}
J legs(const std::vector<Leg>& values) {
    auto n=array();for(const auto& v:values)n.array_value.push_back(array({text(v.ref),text(v.a),text(v.b)}));return n;
}
J chain(const FloatChain& c) { return object({{"kind",text(c.kind)},{"root",text(c.root)},{"legs",legs(c.legs)},{"hangs",refmap(c.hangs)}}); }
J chains(const std::vector<ChainPtr>& values) {
    auto n=array();for(const auto& v:values)n.array_value.push_back(chain(*v));return n;
}
J state(const Engine& e) {
    auto rungs=array(),rail_rows=array(),orient=object(),pulls=object(),trunks=object();
    for(const auto& r:e._rung_islets)rungs.array_value.push_back(array({text(r.trunk_net),text(r.far_net),text(r.ref)}));
    for(const auto& [y,n]:e._rail_row_net)rail_rows.array_value.push_back(array({number(y),text(n)}));
    for(const auto& [r,n]:e.orient)orient.object_value.emplace_back(r,number(n));
    for(const auto& [name,items]:e.pull) {
        auto values=array();for(const auto& [r,n]:items)values.array_value.push_back(array({text(r),text(n)}));
        pulls.object_value.emplace_back(name,std::move(values));
    }
    for(const auto& [name,t]:e.trunks) {
        auto direct=array(),rung=array();
        for(const auto& d:t->direct)direct.array_value.push_back(array({point(d.pin_pt),text(d.side)}));
        for(const auto& r:t->rungs)rung.array_value.push_back(array({text(r.net),point(r.pin_pt),text(r.kind),strings(r.legs),number(r.row)}));
        trunks.object_value.emplace_back(name,object({{"net",text(t->net)},{"zone",text(t->zone)},
            {"direct",direct},{"rungs",rung},{"terms",strings(t->terms)},{"chains",chains(t->chains)},{"nodes",numbers(t->nodes)},{"y",number(t->y)}}));
    }
    return object({{"placement",placement(e.pl)},{"pwr",number(e._pwr)},{"flg",number(e._flg)},
        {"n_box_bucks",number(e._n_box_bucks)},{"done",strings(e._done)},{"pin_islets",strings(e._pin_islets)},
        {"rung_islets",rungs},{"comp_starts",strings(e._comp_starts)},{"sig_rows",numbers(e._sig_rows)},
        {"rail_row_net",rail_rows},{"orient",orient},{"multi",strings(e.multi)},{"shunts",strings(e.shunts)},
        {"multi_nets",strings(e.multi_nets)},{"cluster",refmap(e.cluster)},{"hang",refmap(e.hang)},
        {"pull",pulls},{"series",legs(e.series)},{"float_chains",chains(e.float_chains)},{"trunks",trunks}});
}

void same(const J& actual,const J& expected,const std::string& path) {
    require(actual.kind==expected.kind,path+": JSON type differs");
    switch(actual.kind) {
    case JsonKind::Null:break;
    case JsonKind::Bool:require(actual.bool_value==expected.bool_value,path+": bool differs");break;
    case JsonKind::String:require(actual.string_value==expected.string_value,path+": "+actual.string_value+" != "+expected.string_value);break;
    case JsonKind::Number:
        if(actual.number_value!=expected.number_value) {
            std::ostringstream msg;msg<<std::setprecision(17)<<path<<": "<<actual.number_value<<" != "<<expected.number_value;
            throw std::runtime_error(msg.str());
        }
        break;
    case JsonKind::Array:
        require(actual.array_value.size()==expected.array_value.size(),path+": array size "+std::to_string(actual.array_value.size())+
            " != "+std::to_string(expected.array_value.size()));
        for(std::size_t i=0;i<actual.array_value.size();++i)same(actual.array_value[i],expected.array_value[i],path+"["+std::to_string(i)+"]");
        break;
    case JsonKind::Object:
        require(actual.object_value.size()==expected.object_value.size(),path+": object size differs");
        for(std::size_t i=0;i<actual.object_value.size();++i) {
            const auto& [key,value]=actual.object_value[i];
            require(key==expected.object_value[i].first,path+": key order differs: "+key+" != "+expected.object_value[i].first);
            same(value,expected.object_value[i].second,path+"."+key);
        }
        break;
    }
}
SchematicSpacing spacing(const J& s) {
    return {num(s,"port_run"),num(s,"label_tap_gap"),num(s,"hang_stub"),num(s,"stagger_extra"),num(s,"cap_pitch"),
        num(s,"cluster_dx"),num(s,"cluster_dy"),num(s,"flags_dy"),num(s,"flag_pitch")};
}

void compare(const J& fixture,SymbolLibrary& lib) {
    const auto c=parse_circuit_ir(field(fixture,"circuit"));
    Engine e(c,lib,spacing(field(fixture,"spacing")));
    const auto& initial=field(fixture,"initial");
    e._n_box_bucks=static_cast<std::size_t>(num(initial,"n_box_bucks"));
    for(const auto& box:field(field(initial,"placement"),"boxes").array_value)e.pl.boxes.push_back(parse_box(box));
    same(state(e),initial,"initial");
    auto args=field(fixture,"args");
    const auto method=str(fixture,"method"),ref=str(args,"ref");
    std::optional<std::string> error;
    J result;
    try {
        if(method=="connector")e._connector_template(ref);
        else if(method=="regulator")e._regulator_template(e._detect_stages());
        else if(method=="stages")result=stages(e._detect_stages());
        else if(method=="cluster")e._decoupling_cluster(num(args,"ax"),num(args,"ay"),parse_box(field(args,"body")));
        else if(method=="flags")e._flags_row();
        else if(method=="needs_flags") {
            result=object();for(const auto& n:c.nets)result.object_value.emplace_back(n.name,boolean(e._needs_flag(n.name)));
        } else if(method=="helper_info") {
            result=object();const auto all=e._detect_stages();
            const auto nullable=[](const std::optional<std::string>& n){return n ? text(*n) : J{};};
            for(const auto& r:e.multi) {
                result.object_value.emplace_back(r,object({{"in",nullable(e._stage_in_rail(r))},
                    {"left",boolean(e._stage_has_left_input(r))},{"out",nullable(e._stages_out(r))},
                    {"fb",all.contains(r) ? nullable(e._stage_fb_net(r,all.at(r))) : J{}}}));
            }
        } else if(method=="box_left")e._box_left_pin_islet(str(args,"net"),parse_point(field(args,"point")),parse_box(field(args,"body")));
        else if(method=="box_right")e._box_right_pin_islet(str(args,"net"),parse_point(field(args,"point")));
        else if(method=="fb_left") {
            const auto st=stage(field(args,"stage"));
            e._fb_left_network(ref,st,parse_point(field(args,"point")),str(args,"net"),st.out);
        }
        else if(method=="power_at") {
            const auto& value=field(args,"value");
            e._power_at(str(args,"net"),num(args,"x"),num(args,"y"),static_cast<int>(num(args,"rotation")),
                value.kind==JsonKind::Null ? std::nullopt : std::optional<Point>{parse_point(value)});
        } else if(method=="stage_row" || method=="buck_right" || method=="ldo_right") {
            RefMap inputs,outputs=parse_refmap(field(args,"out_caps"));
            if(method=="stage_row")inputs=parse_refmap(field(args,"in_caps"));
            try {
                if(method=="stage_row")e._stage_row(ref,stage(field(args,"stage")),num(args,"ay"),inputs,outputs);
                else if(method=="buck_right")e._buck_right(ref,stage(field(args,"stage")),num(args,"ay"),{},lib.get(e.part(ref).lib_id),outputs);
                else e._ldo_right(ref,stage(field(args,"stage")),num(args,"ay"),{},lib.get(e.part(ref).lib_id),outputs);
            } catch(const SchematicPlaceError& ex) { error=ex.what(); }
            for(auto& [key,value]:args.object_value) {
                if(key=="in_caps")value=refmap(inputs);
                if(key=="out_caps")value=refmap(outputs);
            }
        } else throw std::runtime_error("unknown fixture method: "+method);
    } catch(const SchematicPlaceError& ex) { error=ex.what(); }
    const auto* expected_error=object_field(fixture,"error");
    require(error.has_value()==(expected_error!=nullptr),"error status differs: "+error.value_or("successful"));
    if(error)require(*error==expected_error->string_value,"error text: "+*error+" != "+expected_error->string_value);
    same(state(e),field(fixture,"expected"),"after");
    same(args,field(fixture,"after_args"),"mutated arguments");
    if(const auto* expected=object_field(fixture,"result"))same(result,*expected,"result");
}

void mutations(const std::vector<J>& fixtures,SymbolLibrary& lib,std::size_t& count) {
    const auto find=[&](const std::string& name)->const J& {
        const auto it=std::find_if(fixtures.begin(),fixtures.end(),[&](const auto& f){return str(f,"name")==name;});
        require(it!=fixtures.end(),"missing named fixture: "+name);return *it;
    };
    const auto& connector=find("carrier/som_j1");
    auto c=parse_circuit_ir(field(connector,"circuit"));
    Engine first(c,lib),second(c,lib);
    first._connector_template("J1");second._connector_template("J1");
    same(placement(first.pl),placement(second.pl),"repeat connector/shared symbol cache");++count;
    first.pl.parts.front().value="MUTATED";
    first.pl.plans.front().second.front().front().first+=19.05;
    first.pl.boxes.clear();
    same(placement(second.pl),field(field(connector,"expected"),"placement"),"placement copy isolation");++count;
    Engine edited(c,lib);
    edited.pl=second.pl;
    edited.pl.parts.front().ref_pos->x+=2.54;
    require(edited.pl.parts.front().ref_pos->x!=second.pl.parts.front().ref_pos->x,"optional text positions alias");++count;
    const auto& cluster_fixture=find("cluster_6");
    auto caps=parse_circuit_ir(field(cluster_fixture,"circuit"));
    Engine clustered(caps,lib);
    clustered._decoupling_cluster(0,0,{-10,-8,10,8,"body","U0"});
    require(clustered.cluster.empty(),"cluster is not consumed");
    const auto before=state(clustered);
    clustered._decoupling_cluster(1e6,1e6,{});
    same(state(clustered),before,"empty cluster must not mutate any state");++count;
    const auto& regulator=find("carrier/power");
    auto power=parse_circuit_ir(field(regulator,"circuit"));
    Engine detection(power,lib);
    const auto prior=state(detection);
    const auto detected=detection._detect_stages();
    same(state(detection),prior,"stage detection is read-only");
    require(detected.size()==3 && detected.at("U1").inductor=="L1" && detected.at("U3").kind=="ldo","topology classification");++count;
    const auto fb=SymbolPin{"1","FB/VSENSE","input",0,0,0,2.54,false};
    require(detection._is_fb_pin(fb,"unknown", "+3V3_REG"),"named feedback not recognized");
    for(const auto& name:{"BIAS","VCC","RT","PGOOD","SS","COMP","EN_SYNC","EN"}) {
        auto pin=fb;pin.name=name;
        require(!detection._is_fb_pin(pin,"FB_3V3", "+3V3_REG"),"named non-feedback pin classified as feedback");
    }
    ++count;
    Engine missing(caps,lib);
    bool rejected=false;
    try { missing._ldo_right("C1",{"ldo","+3V3","",""},0,{},lib.get("Device:C"),missing.cluster); }
    catch(const SchematicPlaceError& ex) { rejected=std::string(ex.what())=="C1: LDO stage without right-facing power output pin"; }
    require(rejected,"missing LDO pin did not produce deterministic native error");++count;
    SymbolDef broken=lib.get("Device:C");
    require(!broken.pins.empty(),"frozen capacitor has no pins");
    broken.pins.front().number="changed";
    require(lib.get("Device:C").pins.front().number!="changed","symbol value copy aliases library");++count;
}

}  // namespace

int main(int argc,char** argv) {
    try {
        require(argc==2,"usage: schematic_place_templates_contracts FIXTURE_DIR");
        const fs::path dir=argv[1];
        SymbolLibrary library(std::vector<fs::path>{dir/"symbols"});
        std::vector<fs::path> files;
        for(const auto& entry:fs::directory_iterator(dir))if(entry.path().extension()==".json")files.push_back(entry.path());
        std::sort(files.begin(),files.end());
        require(files.size()>=66,"incomplete independent template baselines");
        std::vector<J> fixtures;std::size_t count=0;
        for(const auto& file:files) {
            fixtures.push_back(parse_json_file(file.string()));
            try { compare(fixtures.back(),library);++count; }
            catch(const std::exception& ex){throw std::runtime_error(str(fixtures.back(),"name")+": "+ex.what());}
        }
        mutations(fixtures,library,count);
        std::cout<<count<<" schematic placement template contracts passed ("<<files.size()
                 <<" independent frozen outputs/state snapshots, mutation and invalid-input checks)\n";
        return 0;
    } catch(const std::exception& ex) { std::cerr<<ex.what()<<'\n';return 1; }
}
