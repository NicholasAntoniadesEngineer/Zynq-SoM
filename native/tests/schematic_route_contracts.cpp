// Native full-route differential contracts. Real fixtures capture all 37 carrier
// placements from schgen.layout.place.build + unchanged layout.route.route on
// 2026-09-18 (CPython 3.14, grid 1.27). Synthetic fixtures execute that same route.
// No Python/KiCad runtime is required. Run DATA_DIR [REPOSITORY_ROOT]; the optional
// repository argument also resolves every real fixture through SymbolLibrary.
#include "schgen/schematic_route.hpp"
#include "schgen/json.hpp"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
namespace fs = std::filesystem;
using namespace schgen;

void require(bool value, const std::string& message) {
    if (!value) throw std::runtime_error(message);
}
const JsonNode& field(const JsonNode& n, const std::string& key) {
    const auto* value = object_field(n, key);
    require(value != nullptr, "fixture missing " + key);
    return *value;
}
std::string str(const JsonNode& n, const std::string& key) {
    const auto* value = object_field(n, key);
    return value ? value->string_value : "";
}
double num(const JsonNode& n, const std::string& key) {
    const auto* value = object_field(n, key);
    return value ? value->number_value : 0;
}
bool boolean(const JsonNode& n, const std::string& key) {
    const auto* value = object_field(n, key);
    return value && value->bool_value;
}
RoutePoint point(const JsonNode& n) {
    require(n.kind == JsonKind::Array && n.array_value.size() == 2, "invalid fixture point");
    return {n.array_value[0].number_value, n.array_value[1].number_value};
}

struct Fixture {
    std::string name;
    CircuitSheetIr circuit;
    SchematicRoutePlacement placement;
    std::map<std::string, SymbolDef> symbols;
    std::optional<std::string> error;
    SchematicRoutedSheet expected;
    bool synthetic = false;
};

Fixture fixture(const JsonNode& root) {
    Fixture f;
    f.name = str(root, "name"); f.synthetic = boolean(root,"synthetic");
    const auto& c = field(root,"circuit");
    f.circuit.name = str(c,"name");
    for (const auto& n : field(c,"nets").array_value) {
        CircuitNetIr net;
        net.name = str(n,"name"); net.net_class = str(n,"net_class");
        for (const auto& p : field(n,"pins").array_value) net.pins.push_back({str(p,"ref"),str(p,"pin")});
        f.circuit.nets.push_back(std::move(net));
    }
    const auto& p = field(root,"placement");
    for (const auto& row : field(p,"parts").array_value) {
        SchematicPlacedPart part;
        part.ref=str(row,"ref");part.lib_id=str(row,"lib_id");part.value=str(row,"value");
        part.x=num(row,"x");part.y=num(row,"y");part.rotation=static_cast<int>(num(row,"rotation"));
        part.footprint=str(row,"footprint");f.placement.parts.push_back(std::move(part));
    }
    for (const auto& row : field(p,"powers").array_value) {
        SchematicPlacedPower power;
        power.ref=str(row,"ref");power.lib_id=str(row,"lib_id");power.value=str(row,"value");power.net=str(row,"net");
        power.x=num(row,"x");power.y=num(row,"y");power.rotation=static_cast<int>(num(row,"rotation"));
        f.placement.powers.push_back(std::move(power));
    }
    for (const auto& row : field(p,"hlabels").array_value)
        f.placement.hlabels.push_back({str(row,"name"),num(row,"x"),num(row,"y"),static_cast<int>(num(row,"rotation")),str(row,"shape")});
    for (const auto& row : field(p,"llabels").array_value)
        f.placement.llabels.push_back({str(row,"name"),num(row,"x"),num(row,"y"),static_cast<int>(num(row,"rotation"))});
    for (const auto& row : field(p,"no_connects").array_value)
        f.placement.no_connects.push_back({num(row,"x"),num(row,"y")});
    for (const auto& [net, paths] : field(p,"plans").object_value) {
        std::vector<std::vector<RoutePoint>> polylines;
        for (const auto& path : paths.array_value) {
            std::vector<RoutePoint> points;
            for (const auto& pt : path.array_value) points.push_back(point(pt));
            polylines.push_back(std::move(points));
        }
        f.placement.plans.emplace_back(net,std::move(polylines));
    }
    for (const auto& row : field(p,"boxes").array_value)
        f.placement.boxes.push_back({num(row,"x0"),num(row,"y0"),num(row,"x1"),num(row,"y1"),str(row,"kind"),str(row,"owner")});
    for (const auto& net : field(p,"label_bridged").array_value) f.placement.label_bridged.insert(net.string_value);
    for (const auto& row : field(root,"symbols").array_value) {
        SymbolDef symbol;
        symbol.lib_id=str(row,"lib_id");
        for (const auto& pin : field(row,"pins").array_value)
            symbol.pins.push_back({str(pin,"number"),str(pin,"name"),str(pin,"etype"),num(pin,"x"),num(pin,"y"),
                static_cast<int>(num(pin,"rotation")),num(pin,"length"),boolean(pin,"hidden")});
        f.symbols.emplace(symbol.lib_id,std::move(symbol));
    }
    if(const auto* error=object_field(root,"error")) f.error=error->string_value;
    else {
        const auto& expected=field(root,"expected");
        for(const auto& row:field(expected,"segs").array_value)
            f.expected.segs.push_back({num(row,"x0"),num(row,"y0"),num(row,"x1"),num(row,"y1"),str(row,"net")});
        for(const auto& row:field(expected,"junctions").array_value) {
            const auto pnt=point(row);f.expected.junctions.push_back({pnt.first,pnt.second});
        }
    }
    return f;
}

void same(const SchematicRoutedSheet& actual,const SchematicRoutedSheet& expected) {
    require(actual.segs.size()==expected.segs.size(),"wire count: "+std::to_string(actual.segs.size())+
        " vs "+std::to_string(expected.segs.size()));
    for(std::size_t i=0;i<actual.segs.size();++i) {
        const auto& a=actual.segs[i];const auto& e=expected.segs[i];
        require(a.net==e.net && a.x0==e.x0 && a.y0==e.y0 && a.x1==e.x1 && a.y1==e.y1,
            "wire "+std::to_string(i)+" differs: "+a.net+" ("+std::to_string(a.x0)+","+std::to_string(a.y0)+
            ")->("+std::to_string(a.x1)+","+std::to_string(a.y1)+") expected "+e.net+" ("+
            std::to_string(e.x0)+","+std::to_string(e.y0)+")->("+std::to_string(e.x1)+","+std::to_string(e.y1)+")");
    }
    require(actual.junctions.size()==expected.junctions.size(),"junction count differs");
    for(std::size_t i=0;i<actual.junctions.size();++i)
        require(actual.junctions[i].x==expected.junctions[i].x && actual.junctions[i].y==expected.junctions[i].y,
                "junction order/position differs at "+std::to_string(i));
}

struct Suite {
    int count=0;
    void run(const std::string& name,const std::function<void()>& fn) {
        try{fn();++count;}catch(const std::exception& e){throw std::runtime_error(name+": "+e.what());}
    }
};

void compare(const Fixture& f,const SchematicSymbolResolver& symbols) {
    try {
        const auto actual=route_schematic(f.circuit,f.placement,symbols);
        require(!f.error,"expected rejection was accepted: "+f.error.value_or(""));
        same(actual,f.expected);
        const auto geometry=schematic_route_geometry(f.placement,actual);
        same({geometry.wires,geometry.junctions},actual);
        require(geometry.boxes.size()==f.placement.boxes.size(),"geometry adapter lost boxes");
        for(std::size_t i=0;i<geometry.boxes.size();++i) {
            const auto& a=geometry.boxes[i];const auto& b=f.placement.boxes[i];
            require(a.x0==b.x0 && a.y0==b.y0 && a.x1==b.x1 && a.y1==b.y1 && a.kind==b.kind && a.owner==b.owner,
                    "geometry adapter changed boxes");
        }
        SchematicDesign design;
        design.circuit=f.circuit;design.parts=f.placement.parts;design.no_connects=f.placement.no_connects;
        design.paper="A3";design.wires.push_back({-1,-1,-1,-1});design.junctions.push_back({-1,-1});
        apply_schematic_route(design,actual);apply_schematic_route(design,actual);
        require(design.wires.size()==actual.segs.size() && design.junctions.size()==actual.junctions.size(),
                "emitter adapter appended stale geometry");
        require(design.paper=="A3" && design.parts.size()==f.placement.parts.size() &&
                design.circuit.name==f.circuit.name && design.no_connects.size()==f.placement.no_connects.size(),
                "emitter adapter changed placement/circuit");
    }catch(const SchematicRouteError& e){
        require(f.error && *f.error==e.what(),"wrong routing failure: "+std::string(e.what())+
            "; expected "+f.error.value_or("success"));
    }
}

void contracts(const fs::path& dir,const std::optional<fs::path>& repo) {
    Suite suite;
    std::vector<fs::path> files;
    for(const auto& file:fs::directory_iterator(dir))if(file.path().extension()==".json")files.push_back(file.path());
    std::sort(files.begin(),files.end());
    require(!files.empty(),"no routing fixtures");
    std::optional<SymbolLibrary> library;
    if(repo)library.emplace(*repo);
    std::size_t successes=0,failures=0,real=0,wires=0,junctions=0;
    const auto exercise=[&](const JsonNode& node) {
        const auto f=fixture(node);
        suite.run(f.name,[&]{compare(f,[&](const std::string& id)->const SymbolDef&{return f.symbols.at(id);});});
        if(f.error)++failures;else{++successes;wires+=f.expected.segs.size();junctions+=f.expected.junctions.size();}
        if(!f.synthetic) {
            ++real;
            if(library)suite.run(f.name+" live symbol library",[&] {
                compare(f,[&](const std::string& id)->const SymbolDef&{return library->get(id);});
            });
        }
    };
    for(const auto& file:files) {
        const auto root=parse_json_file(file.string());
        if(root.kind==JsonKind::Array)for(const auto& node:root.array_value)exercise(node);
        else exercise(root);
    }
    suite.run("nonfinite/overflow geometry fails before kernel integer casts",[&] {
        CircuitSheetIr c;c.nets.push_back({"N","signal",{}});
        for(const auto bad:{std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN(),1e100}) {
            SchematicRoutePlacement p;p.plans={{"N",{{{bad,0},{0,0}}}}};
            bool rejected=false;
            try{route_schematic(c,p,SchematicSymbolResolver{});}catch(const SchematicRouteError&){rejected=true;}
            require(rejected,"invalid coordinate accepted");
        }
    });
    suite.run("near-grid aliases fail instead of repeating an unproductive join",[&] {
        CircuitSheetIr c;c.nets.push_back({"N","signal",{}});
        SchematicRoutePlacement p;
        p.hlabels={{"N",0,0,0,"bidirectional"},{"N",0.001,0,0,"bidirectional"}};
        try{route_schematic(c,p,SchematicSymbolResolver{});}
        catch(const SchematicRouteError& e){
            require(std::string(e.what())=="net N: grid join made no connectivity progress","wrong alias diagnostic");
            return;
        }
        throw std::runtime_error("near-grid aliases caused a false successful join");
    });
    suite.run("opposite-sign endpoints cannot overflow a kernel span",[&] {
        CircuitSheetIr c;c.nets.push_back({"N","signal",{}});
        SchematicRoutePlacement p;p.plans={{"N",{{{-2540000000.0,0},{2540000000.0,0}}}}};
        try{route_schematic(c,p,SchematicSymbolResolver{});}
        catch(const SchematicRouteError& e){
            require(std::string(e.what())=="route: segment exceeds the native schematic cell span","wrong span diagnostic");
            return;
        }
        throw std::runtime_error("overflowing cell span accepted");
    });
    suite.run("diagnostic components retain bonds, anchors, and disconnected islets",[&] {
        const RoutePoint a{0,0}, b{1.27,0}, c{2.54,0}, d{5.08,0}, isolated{9.01,7.03};
        const auto comps=schematic_route_components({{a,b}}, {a,d}, {isolated}, {c}, {{b,c},{c,d}});
        require(comps.size()==2,"bonded component or isolated power anchor lost");
        std::set<std::set<RoutePoint>> sets;
        for(const auto& comp:comps)sets.emplace(comp.begin(),comp.end());
        require(sets==std::set<std::set<RoutePoint>>{{a,b,c,d},{isolated}},"wrong component membership");
        require(schematic_route_components({}, {}, {}, {}, {}).empty(),"empty graph has a component");
    });
    suite.run("diagnostic components do not invent interior taps or orthogonal restrictions",[&] {
        const RoutePoint a{0.1,0.2}, b{2.1,2.2}, mid{1.1,1.2};
        const auto comps=schematic_route_components({{a,b}}, {mid}, {}, {}, {});
        require(comps.size()==2,"unsplit interior pin was joined by diagnostic topology");
    });
    suite.run("diagnostic components reject nonfinite topology keys",[&] {
        try{schematic_route_components({}, {}, {{std::numeric_limits<double>::quiet_NaN(),0}}, {}, {});}
        catch(const SchematicRouteError& e){
            require(std::string(e.what())=="route components: points must be finite","wrong component diagnostic");
            return;
        }
        throw std::runtime_error("NaN component key accepted");
    });
    suite.run("compatibility join normalizes duplicate grid starts and compresses its path",[&] {
        RouteGrid grid;
        const auto path=schematic_route_join(grid,"N",{{0,0},{0.001,0},{0,0}},{{2.54,2.54}});
        require(path==std::vector<RoutePoint>{{0,0},{2.54,0},{2.54,2.54}},"join tie/compression changed");
        require(grid.owners().empty(),"path search changed ownership");
    });
    suite.run("compatibility join preserves blocked-corridor diagnostic",[&] {
        RouteGrid grid;
        grid.claim("OTHER",{{1,0},{-1,0},{0,1},{0,-1}},"cage");
        try{schematic_route_join(grid,"N",{{0,0}},{{2.54,0}});}
        catch(const SchematicRouteError& e){
            require(std::string(e.what())=="net N: no free corridor joins its parts — placement must expand", "wrong join error");
            return;
        }
        throw std::runtime_error("blocked join accepted");
    });
    std::cout<<suite.count<<" schematic routing contracts passed ("<<real<<" real carrier sheets, "
        <<successes<<" successful baselines, "<<failures<<" rejection baselines, "
        <<wires<<" ordered wires, "<<junctions<<" ordered junctions)\n";
}
}  // namespace

int main(int argc,char** argv) {
    try {
        require(argc==2 || argc==3,"usage: schematic_route_contracts FIXTURE_DIR [REPOSITORY_ROOT]");
        contracts(argv[1],argc==3 ? std::optional<fs::path>{argv[2]} : std::nullopt);
        return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
