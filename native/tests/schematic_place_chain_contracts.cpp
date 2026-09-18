// Frozen full Python Engine-state contracts for the chain seam.
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
        {"pull",pulls},{"series",legs(e.series)},{"float_chains",chains(e.float_chains)},{"trunks",trunks},
        {"deferred_texts", [&] { auto values=array(); for(const auto& item:e._deferred_texts) values.array_value.push_back(array({number(item.first),object({{"x0",number(item.second.x0)},{"y0",number(item.second.y0)},{"x1",number(item.second.x1)},{"y1",number(item.second.y1)},{"kind",text(item.second.kind)},{"owner",text(item.second.owner)}})})); return values; }()}});
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

J facing(const std::vector<FacingPair>& pairs) {
    auto result=array();
    for(const auto& p:pairs) {
        auto a=array(),b=array();
        for(auto tip:p.a_extra)a.array_value.push_back(point(tip));
        for(auto tip:p.b_extra)b.array_value.push_back(point(tip));
        result.array_value.push_back(array({text(p.net),point(p.a),point(p.b),a,b}));
    }
    return result;
}
J inspect(Engine& e) {
    const auto order=e._chain_order();
    auto tips=object(),pairs=array(),reaches=object();
    for(const auto& ref:e.multi) {
        auto list=array();
        for(const auto& tip:e._side_tips(ref))
            list.array_value.push_back(array({text(tip.ref),text(tip.number),text(tip.side),point(tip.point)}));
        tips.object_value.emplace_back(ref,std::move(list));
    }
    for(std::size_t i=1;i<order.size();++i)pairs.array_value.push_back(facing(e._facing_pairs(order[i-1],order[i])));
    for(const auto& ref:e.multi) {
        auto row=object();
        for(const auto* side:{"left","right","top","bottom"})row.object_value.emplace_back(side,number(e._side_reach(ref,side)));
        reaches.object_value.emplace_back(ref,std::move(row));
    }
    return object({{"order",strings(order)},{"tips",tips},{"pairs",pairs},{"reaches",reaches}});
}
void setup(Engine& e,const J& raw) {
    for(const auto& [name,value]:raw.object_value) {
        if(name=="cluster")e.cluster=parse_refmap(value);
        else if(name=="shunts")e.shunts=refs(value);
        else if(name=="hang")e.hang=parse_refmap(value);
        else if(name=="_pin_islets")for(const auto& ref:refs(value))e._pin_islets.insert(ref);
        else if(name=="_rung_islets")for(const auto& row:value.array_value)e._rung_islets.push_back({row.array_value[0].string_value,row.array_value[1].string_value,row.array_value[2].string_value});
        else if(name=="orient")for(const auto& [ref,rot]:value.object_value)e.orient[ref]=static_cast<int>(rot.number_value);
        else if(name=="boxes")for(const auto& box:value.array_value)e.pl.boxes.push_back(parse_box(box));
        else if(name=="sp")e.sp=spacing(value);
        else if(name=="float_chains") {
            e.float_chains.clear();
            for(const auto& row:value.array_value) {
                auto chain=std::make_shared<FloatChain>();chain->kind=str(row,"kind");chain->root=str(row,"root");
                for(const auto& leg:field(row,"legs").array_value)chain->legs.push_back({leg.array_value[0].string_value,leg.array_value[1].string_value,leg.array_value[2].string_value});
                chain->hangs=parse_refmap(field(row,"hangs"));e.float_chains.push_back(chain);
            }
        }
        else throw std::runtime_error("unknown fixture setup "+name);
    }
}
J invoke(Engine& e,const std::string& action,const J& args) {
    if(action=="inspect")return inspect(e);
    if(action=="run"){e.run();return {};}
    if(action=="_chain_template"){e._chain_template();return {};}
    if(action=="_stack_columns_template"){e._stack_columns_template();return {};}
    if(action=="_chain_order")return strings(e._chain_order());
    if(action=="_eval_chain") {
        const auto score=e._eval_chain(refs(args.array_value.at(0)));
        auto rotations=object();
        for(const auto& [ref,rot]:score.orient)rotations.object_value.emplace_back(ref,number(rot));
        return array({array({number(score.score[0]),number(score.score[1]),number(score.score[2])}),rotations});
    }
    if(action=="_tip_group") {
        std::vector<Point> points;for(const auto& p:args.array_value.at(0).array_value)points.push_back(parse_point(p));
        const auto group=Engine::_tip_group(points);if(!group)return {};
        auto rest=array();for(auto p:group->rest)rest.array_value.push_back(point(p));
        return array({point(group->first),rest});
    }
    if(action=="_rail_decoupling_columns")e._rail_decoupling_columns();
    else if(action=="_leftover_chains_columns")e._leftover_chains_columns();
    else if(action=="_port_strap_columns")e._port_strap_columns();
    else if(action=="_series_port_columns")e._series_port_columns();
    else if(action=="_pull_rank_columns")e._pull_rank_columns();
    else if(action=="_trunk_series_columns")e._trunk_series_columns();
    else if(action=="_rung_islet_columns")e._rung_islet_columns();
    else if(action=="_pin_divider_columns")e._pin_divider_columns();
    else if(action=="_rung_islet_drop")e._rung_islet_drop(args.array_value.at(0).string_value,parse_point(args.array_value.at(1)),static_cast<int>(args.array_value.at(2).number_value));
    else if(action=="_pin_num_at")return text(e._pin_num_at(args.array_value.at(0).string_value,parse_point(args.array_value.at(1)),args.array_value.at(2).string_value));
    else throw std::runtime_error("unknown fixture action "+action);
    return {};
}
void compare(const J& fixture,SymbolLibrary& lib) {
    Engine e(parse_circuit_ir(field(fixture,"circuit")),lib,spacing(field(fixture,"spacing")));
    setup(e,field(fixture,"setup"));
    same(state(e),field(fixture,"initial"),"initial");
    const auto& expected_error=field(fixture,"error");
    J result;
    bool failed=false;
    try { result=invoke(e,str(fixture,"action"),field(fixture,"args")); }
    catch(const SchematicPlaceError& error) {
        require(expected_error.kind!=JsonKind::Null,"unexpected native error: "+std::string(error.what()));
        require(str(expected_error,"message")==error.what(),"wrong error: "+std::string(error.what())
                +" != "+str(expected_error,"message"));failed=true;
    }
    require(failed==(expected_error.kind!=JsonKind::Null),"expected reference diagnostic was not raised");
    if(!failed)same(result,field(fixture,"result"),"result");
    same(state(e),field(fixture,"expected"),"final state");
}
}  // namespace

int main(int argc,char** argv) {
    try {
        require(argc==2||argc==3,"usage: schematic_place_chain_contracts <fixture-dir> [name-filter]");
        const fs::path dir(argv[1]);
        SymbolLibrary lib(std::vector<fs::path>{dir/"symbols"});
        const auto manifest=parse_json_file((dir/"manifest.json").string());
        const std::string filter=argc==3?argv[2]:"";
        std::size_t passed=0,failed=0;
        for(const auto& name:field(manifest,"cases").array_value) {
            if(name.string_value.find(filter)==std::string::npos)continue;
            try {
                compare(parse_json_file((dir/name.string_value).string()),lib);
                ++passed;
            } catch(const std::exception& error) {
                ++failed;std::cerr<<"FAIL "<<name.string_value<<": "<<error.what()<<'\n';
            }
        }
        require(passed+failed>0,"no matching contract cases");
        std::cout<<passed<<" full chain-state contracts passed; "<<failed<<" failed\n";
        return failed?1:0;
    } catch(const std::exception& error) {
        std::cerr<<"chain contract setup failure: "<<error.what()<<'\n';return 1;
    }
}
