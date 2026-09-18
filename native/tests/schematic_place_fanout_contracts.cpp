// Frozen Python geometry/error snapshots, executed entirely in native C++.
// Run: schematic_place_fanout_contracts DATA_DIR. No installed KiCad libraries.
#include "../src/schematic_place_internal.hpp"

#include <cmath>
#include <filesystem>
#include <iostream>
#include <stdexcept>

namespace {
using namespace schgen;
using namespace schgen::schematic_place;
using J = JsonNode;
J arr() { J j; j.kind = JsonKind::Array; return j; }
J obj() { J j; j.kind = JsonKind::Object; return j; }
J s(const std::string& value) { J j; j.kind = JsonKind::String; j.string_value = value; return j; }
J n(double value) { J j; j.kind = JsonKind::Number; j.number_value = value; return j; }
J b(bool value) { J j; j.kind = JsonKind::Bool; j.bool_value = value; return j; }
J a(std::initializer_list<J> values) { J j = arr(); j.array_value = values; return j; }
const J& f(const J& j, const std::string& key) {
    const auto* value = object_field(j, key);
    if (!value) throw std::runtime_error("missing fixture field " + key);
    return *value;
}
const std::vector<J>& array(const J& j) { return j.array_value; }
std::string text(const J& j) { return j.string_value; }
double num(const J& j) { return j.number_value; }
int integer(const J& j) { return static_cast<int>(num(j)); }
Point point(const J& j) { return {num(array(j).at(0)), num(array(j).at(1))}; }
J jp(Point p) { return a({n(p.first), n(p.second)}); }
Box4 box(const J& j) { const auto& v = array(j); return {num(v.at(0)),num(v.at(1)),num(v.at(2)),num(v.at(3))}; }
VisualBox visual(const J& j) { const auto& v = array(j); return {num(v.at(0)),num(v.at(1)),num(v.at(2)),num(v.at(3)),text(v.at(4)),text(v.at(5))}; }
J jb(const VisualBox& v) { return a({n(v.x0),n(v.y0),n(v.x1),n(v.y1),s(v.kind),s(v.owner)}); }
J jb(const Box4& v) { return a({n(v.x0),n(v.y0),n(v.x1),n(v.y1)}); }
std::vector<Point> points(const J& j) { std::vector<Point> out; for (const auto& p : array(j)) out.push_back(point(p)); return out; }
Refs refs(const J& j) { Refs out; for (const auto& x : array(j)) out.push_back(text(x)); return out; }
template <typename Range> J texts(const Range& xs) { auto out = arr(); for (const auto& x : xs) out.array_value.push_back(s(x)); return out; }
J jp(const std::vector<Point>& xs) { auto out = arr(); for (const auto& x : xs) out.array_value.push_back(jp(x)); return out; }
J numbers(const std::vector<double>& xs) { auto out = arr(); for (const auto x : xs) out.array_value.push_back(n(x)); return out; }
J position(const std::optional<SchematicTextPosition>& v) { return v ? a({n(v->x),n(v->y),n(v->rotation)}) : J{}; }
J legs(const std::vector<Leg>& xs) { auto out = arr(); for (const auto& x : xs) out.array_value.push_back(a({s(x.ref),s(x.a),s(x.b)})); return out; }
FloatChain chain(const J& j) {
    FloatChain out; out.kind=text(f(j,"kind")); out.root=text(f(j,"root"));
    for (const auto& x : array(f(j,"legs"))) out.legs.push_back({text(array(x).at(0)),text(array(x).at(1)),text(array(x).at(2))});
    if (const auto* hangs=object_field(j,"hangs")) for (const auto& [name,rs] : hangs->object_value) out.hangs[name]=refs(rs);
    return out;
}
J jc(const FloatChain& c) {
    auto hangs=obj(); for (const auto& [name,rs] : c.hangs) hangs.object_value.push_back({name,texts(rs)});
    auto out=obj(); out.object_value={{"kind",s(c.kind)},{"root",s(c.root)},{"legs",legs(c.legs)},{"hangs",hangs}}; return out;
}
std::shared_ptr<Trunk> trunk(const J& j) {
    auto out=std::make_shared<Trunk>(); out->net=text(f(j,"net"));
    if (const auto* xs=object_field(j,"direct")) for (const auto& x : array(*xs)) out->direct.push_back({point(array(x).at(0)),text(array(x).at(1))});
    if (const auto* xs=object_field(j,"rungs")) for (const auto& x : array(*xs)) {
        const auto& v=array(x); out->rungs.push_back({text(v.at(0)),point(v.at(1)),text(v.at(2)),refs(v.at(3)),num(v.at(4))});
    }
    if (const auto* xs=object_field(j,"chains")) for (const auto& x : array(*xs)) out->chains.push_back(std::make_shared<FloatChain>(chain(x)));
    if (const auto* y=object_field(j,"y")) out->y=num(*y);
    return out;
}
J jt(const Trunk& t) {
    auto direct=arr(),rungs=arr(),chains=arr();
    for (const auto& x:t.direct) direct.array_value.push_back(a({jp(x.pin_pt),s(x.side)}));
    for (const auto& x:t.rungs) rungs.array_value.push_back(a({s(x.net),jp(x.pin_pt),s(x.kind),texts(x.legs),n(x.row)}));
    for (const auto& x:t.chains) chains.array_value.push_back(jc(*x));
    auto out=obj();out.object_value={{"net",s(t.net)},{"zone",s(t.zone)},{"direct",direct},{"rungs",rungs},{"terms",texts(t.terms)},
                                  {"chains",chains},{"nodes",numbers(t.nodes)},{"y",n(t.y)}};return out;
}
J snapshot(const Engine& e) {
    auto out=obj();
    for (const std::string key:{"parts","powers","hlabels","llabels","nc","boxes","plans","bridged","done","pin_islets",
            "rung_islets","series","pull","hang","sig_rows","rail_rows","deferred","trunks"}) out.object_value.push_back({key,arr()});
    const auto push=[&](const std::string& key,J item) { for (auto& [k,v]:out.object_value) if(k==key){v.array_value.push_back(std::move(item));return;} };
    for (const auto& p:e.pl.parts) push("parts",a({s(p.ref),s(p.lib_id),s(p.value),n(p.x),n(p.y),n(p.rotation),s(p.footprint),position(p.ref_pos),position(p.val_pos)}));
    for (const auto& p:e.pl.powers) push("powers",a({s(p.lib_id),s(p.value),s(p.ref),n(p.x),n(p.y),n(p.rotation),s(p.net),position(p.val_pos),b(p.show_value)}));
    for (const auto& x:e.pl.hlabels) push("hlabels",a({s(x.name),n(x.x),n(x.y),n(x.rotation),s(x.shape)}));
    for (const auto& x:e.pl.llabels) push("llabels",a({s(x.name),n(x.x),n(x.y),n(x.rotation)}));
    for (const auto& x:e.pl.no_connects) push("nc",a({n(x.x),n(x.y)}));
    for (const auto& x:e.pl.boxes) push("boxes",jb(x));
    for (const auto& [name,paths]:e.pl.plans) { auto ps=arr();for(const auto& path:paths)ps.array_value.push_back(jp(path));push("plans",a({s(name),ps})); }
    for (const auto& x:e.pl.label_bridged) push("bridged",s(x));
    for (const auto& x:e._done) push("done",s(x));
    for (const auto& x:e._pin_islets) push("pin_islets",s(x));
    for (const auto& x:e._rung_islets) push("rung_islets",a({s(x.trunk_net),s(x.far_net),s(x.ref)}));
    for (const auto& x:e.series) push("series",a({s(x.ref),s(x.a),s(x.b)}));
    for (const auto& [name,rs]:e.pull) {auto ps=arr();for(const auto& [ref,rail]:rs)ps.array_value.push_back(a({s(ref),s(rail)}));push("pull",a({s(name),ps}));}
    for (const auto& [name,rs]:e.hang) push("hang",a({s(name),texts(rs)}));
    for (double x:e._sig_rows) push("sig_rows",n(x));
    for (const auto& [row,name]:e._rail_row_net) push("rail_rows",a({n(row),s(name)}));
    for (const auto& [index,body]:e._deferred_texts) push("deferred",a({n(index),jb(body)}));
    for (const auto& [name,t]:e.trunks) push("trunks",a({s(name),jt(*t)}));
    return out;
}
void compare(const J& actual,const J& expected,const std::string& path) {
    if(actual.kind!=expected.kind)throw std::runtime_error(path+": kind differs");
    bool equal=true;
    switch(expected.kind){
        case JsonKind::Null:break;
        case JsonKind::Bool:equal=actual.bool_value==expected.bool_value;break;
        case JsonKind::String:equal=actual.string_value==expected.string_value;break;
        case JsonKind::Number:equal=std::isfinite(actual.number_value)&&std::fabs(actual.number_value-expected.number_value)<=1e-9;break;
        case JsonKind::Array:
            if(array(actual).size()!=array(expected).size())throw std::runtime_error(path+": size differs ("+std::to_string(array(actual).size())+" != "+std::to_string(array(expected).size())+")");
            for(std::size_t i=0;i<array(expected).size();++i)compare(array(actual)[i],array(expected)[i],path+"["+std::to_string(i)+"]");break;
        case JsonKind::Object:
            if(actual.object_value.size()!=expected.object_value.size())throw std::runtime_error(path+": object size differs");
            for(const auto& [key,value]:expected.object_value)compare(f(actual,key),value,path+"."+key);break;
    }
    if(!equal)throw std::runtime_error(path+": value differs ("+(actual.kind==JsonKind::String?actual.string_value:std::to_string(actual.number_value))+" != "+(expected.kind==JsonKind::String?expected.string_value:std::to_string(expected.number_value))+")");
}
void run_case(const J& spec,SymbolLibrary& library) {
    Engine e(parse_circuit_ir(f(spec,"circuit")),library);
    const auto& initial=f(spec,"initial");Handled handled;
    if(const auto* xs=object_field(initial,"handled"))for(const auto& x:array(*xs))handled.emplace(text(array(x).at(0)),text(array(x).at(1)),text(array(x).at(2)));
    if(const auto* xs=object_field(initial,"orient"))for(const auto& [ref,x]:xs->object_value)e.orient[ref]=integer(x);
    if(const auto* xs=object_field(initial,"boxes"))for(const auto& x:array(*xs))e.pl.boxes.push_back(visual(x));
    if(const auto* xs=object_field(initial,"plans"))for(const auto& x:array(*xs)){std::vector<std::vector<Point>> ps;for(const auto& path:array(array(x).at(1)))ps.push_back(points(path));e.pl.plans.push_back({text(array(x).at(0)),ps});}
    if(const auto* xs=object_field(initial,"sig_rows"))for(const auto& x:array(*xs))e._sig_rows.push_back(num(x));
    if(const auto* xs=object_field(initial,"rail_rows"))for(const auto& x:array(*xs))e._rail_row_net[num(array(x).at(0))]=text(array(x).at(1));
    if(const auto* xs=object_field(initial,"trunks"))for(const auto& x:array(*xs)){auto t=trunk(x);e.trunks[t->net]=t;}
    std::optional<PlacedBody> last;J returns=arr(),error;
    try {
        for(const auto& operation:array(f(spec,"ops"))){
            const auto& op=array(operation);const auto kind=text(op.at(0));J result;
            const auto arg=[&](std::size_t i)->const J&{return op.at(i+1);};
            if(kind=="body"){
                last=e._place_body(text(arg(0)),num(arg(1)),num(arg(2)));result=arr();
                for(const auto& [side,pins]:last->sides){auto ps=arr();for(const auto& x:pins)ps.array_value.push_back(a({s(x.pin->number),jp(x.point)}));result.array_value.push_back(a({s(side),ps}));}
            }else if(kind=="texts")e._part_texts(last->part_index,last->body);
            else if(kind=="fan")e._fan_side(e.pl.parts.at(last->part_index).ref,text(arg(0)),last->sides.at(text(arg(0))),handled);
            else if(kind=="cell")e._cell(text(arg(0)),num(arg(1)),num(arg(2)),handled,e.trunks,arg(3).bool_value,integer(arg(4)));
            else if(kind=="vertical_2pin"){auto [pt,name]=e._vertical_2pin(text(arg(0)),num(arg(1)),num(arg(2)),text(arg(3)),arg(4).bool_value,text(arg(5)));result=a({jp(pt),s(name)});}
            else if(kind=="horizontal_2pin")e._horizontal_2pin(text(arg(0)),num(arg(1)),num(arg(2)),text(arg(3)),text(arg(4)));
            else if(kind=="rail_run"){
                const auto ref=text(arg(0));const auto& symbol=library.get(e.part(ref).lib_id);std::vector<RailPin> pins;
                for(const auto& x:array(arg(1))){const auto no=text(array(x).at(0));pins.push_back({&pin(symbol,no),point(array(x).at(1)),e.net_of(ref,no)});}
                e._fan_rail_run(pins,integer(arg(2)),points(arg(3)));
            }else if(kind=="rail_stub")e._rail_stub(text(arg(0)),point(arg(1)),text(arg(2)));
            else if(kind=="rail_bus")e._rail_bus(text(arg(0)),points(arg(1)),text(arg(2)));
            else if(kind=="series"){
                auto it=std::find_if(e.series.begin(),e.series.end(),[&](const auto& leg){return leg.ref==text(arg(0));});
                if(it==e.series.end())throw std::runtime_error("missing series fixture leg");
                auto [edge,bounds]=e._series_inline(*it,text(arg(1)),point(arg(2)),integer(arg(3)),arg(4).kind==JsonKind::Null?std::nullopt:std::optional<Box4>(box(arg(4))));
                result=a({n(edge),jb(bounds)});
            }else if(kind=="trunk"||kind=="ladder"||kind=="side_ladder"){
                auto t=trunk(arg(0));e.trunks[t->net]=t;
                if(kind=="trunk")e._build_trunk(*t);
                else if(kind=="ladder")result=numbers(e._ladder_rung(*t,text(arg(1)),point(arg(2)),refs(arg(3)),num(arg(4))));
                else result=numbers(e._side_ladder_rung(*t,text(arg(1)),point(arg(2)),integer(arg(3)),refs(arg(4)),num(arg(5))));
            }else if(kind=="stack")e._stack_from_pin(chain(arg(0)),point(arg(1)),text(arg(2)),text(arg(3)));
            else if(kind=="mid"){
                if(arg(3).bool_value)e._chain_mid_features_left(chain(arg(0)),text(arg(1)),point(arg(2)));
                else e._chain_mid_features(chain(arg(0)),text(arg(1)),point(arg(2)));
            }else if(kind=="collect")e._collect_trunk_pins(text(arg(0)),num(arg(1)),num(arg(2)),e.trunks,handled);
            else if(kind=="lane_x")result=n(e._lane_x(integer(arg(0)),num(arg(1)),num(arg(2)),num(arg(3))));
            else if(kind=="foreign_rows_clear"){std::set<double> own;for(const auto& x:array(arg(2)))own.insert(num(x));result=b(e._foreign_rows_clear(box(arg(0)),text(arg(1)),own));}
            else if(kind=="cell_floor")result=n(e._cell_floor(num(arg(0)),num(arg(1))));
            else if(kind=="escape_run_legs"){result=arr();for(const auto& [p0,p1]:e._escape_run_legs(text(arg(0)),num(arg(1)),num(arg(2)),num(arg(3))))result.array_value.push_back(a({jp(p0),jp(p1)}));}
            else if(kind=="escape_path")result=jp(e._escape_path(integer(arg(0)),point(arg(1)),num(arg(2)),text(arg(3))));
            else if(kind=="escape_lane")result=n(e._escape_lane(integer(arg(0)),point(arg(1)),num(arg(2)),text(arg(3))));
            else throw std::runtime_error("unimplemented fixture operation "+kind);
            returns.array_value.push_back(result);
        }
    }catch(const SchematicPlaceError& err){error=s(err.what());}
    compare(error,f(spec,"error"),"error");compare(returns,f(spec,"returns"),"returns");compare(snapshot(e),f(spec,"expected"),"state");
}
}  // namespace

int main(int argc,char** argv){
    try{
        if(argc!=2)throw std::runtime_error("usage: schematic_place_fanout_contracts DATA_DIR");
        const std::filesystem::path fixtures=argv[1];SymbolLibrary library(std::vector<std::filesystem::path>{fixtures});
        const auto corpus=parse_json_file((fixtures/"cases.json").string());std::size_t passed=0,failed=0;
        for(const auto& spec:array(f(corpus,"cases")))try{run_case(spec,library);++passed;}catch(const std::exception& err){++failed;std::cerr<<text(f(spec,"name"))<<": "<<err.what()<<'\n';}
        std::cout<<"fanout contracts: "<<passed<<" passed, "<<failed<<" failed\n";return failed?1:0;
    }catch(const std::exception& err){std::cerr<<err.what()<<'\n';return 1;}
}
