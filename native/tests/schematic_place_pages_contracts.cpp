// Native page orchestration contracts against independent frozen Python data.
// Synthetic operations test policy only; public entry points use real kernels.
#include "../src/schematic_place_internal.hpp"
#include "schgen/json.hpp"

#include <filesystem>
#include <iomanip>
#include <iostream>
#include <sstream>

namespace {
using namespace schgen;
using namespace schgen::schematic_place;
namespace fs = std::filesystem;
std::size_t checks = 0;
void require(bool condition, const std::string& message) {
    ++checks;
    if (!condition) throw std::runtime_error(message);
}
const JsonNode& field(const JsonNode& n, const std::string& key) {
    const auto* f = object_field(n, key);
    require(f != nullptr, "missing fixture field: " + key);
    return *f;
}
std::string str(const JsonNode& n) {
    require(n.kind == JsonKind::String, "expected fixture string");
    return n.string_value;
}
double num(const JsonNode& n) {
    require(n.kind == JsonKind::Number, "expected fixture number");
    return n.number_value;
}
int integer(const JsonNode& n) { return static_cast<int>(num(n)); }
bool boolean(const JsonNode& n) {
    require(n.kind == JsonKind::Bool, "expected fixture bool");
    return n.bool_value;
}
JsonNode j(const std::string& s) { JsonNode n; n.kind = JsonKind::String; n.string_value = s; return n; }
JsonNode j(double v) { JsonNode n; n.kind = JsonKind::Number; n.number_value = v; return n; }
JsonNode j(int v) { return j(static_cast<double>(v)); }
JsonNode j(bool v) { JsonNode n; n.kind = JsonKind::Bool; n.bool_value = v; return n; }
JsonNode array(std::initializer_list<JsonNode> values = {}) {
    JsonNode n; n.kind = JsonKind::Array; n.array_value = values; return n;
}
JsonNode object(std::initializer_list<std::pair<std::string, JsonNode>> values) {
    JsonNode n; n.kind = JsonKind::Object; n.object_value = values; return n;
}
template <typename Container, typename F> JsonNode each(const Container& values, F convert) {
    auto out = array();
    for (const auto& v : values) out.array_value.push_back(convert(v));
    return out;
}
JsonNode strings(const Refs& values) { return each(values, [](const auto& v) { return j(v); }); }
JsonNode point(Point p) { return array({j(p.first), j(p.second)}); }
JsonNode box(const Box4& b) { return array({j(b.x0), j(b.y0), j(b.x1), j(b.y1)}); }
JsonNode visual(const VisualBox& b) {
    return object({{"x0", j(b.x0)}, {"y0", j(b.y0)}, {"x1", j(b.x1)}, {"y1", j(b.y1)},
                   {"kind", j(b.kind)}, {"owner", j(b.owner)}});
}
JsonNode textpos(const std::optional<SchematicTextPosition>& p) {
    return p ? array({j(p->x), j(p->y), j(p->rotation)}) : JsonNode{};
}
JsonNode placement(const SchematicPlacement& p) {
    return object({{"parts", each(p.parts, [](const auto& v) {
            return object({{"ref", j(v.ref)}, {"lib_id", j(v.lib_id)}, {"value", j(v.value)},
                {"x", j(v.x)}, {"y", j(v.y)}, {"rotation", j(v.rotation)},
                {"footprint", j(v.footprint)}, {"ref_pos", textpos(v.ref_pos)}, {"val_pos", textpos(v.val_pos)}});
        })}, {"powers", each(p.powers, [](const auto& v) {
            return object({{"lib_id", j(v.lib_id)}, {"value", j(v.value)}, {"ref", j(v.ref)},
                {"x", j(v.x)}, {"y", j(v.y)}, {"rotation", j(v.rotation)}, {"net", j(v.net)},
                {"val_pos", textpos(v.val_pos)}, {"show_value", j(v.show_value)}});
        })}, {"hlabels", each(p.hlabels, [](const auto& v) {
            return object({{"name", j(v.name)}, {"x", j(v.x)}, {"y", j(v.y)},
                {"rotation", j(v.rotation)}, {"shape", j(v.shape)}});
        })}, {"llabels", each(p.llabels, [](const auto& v) {
            return object({{"name", j(v.name)}, {"x", j(v.x)}, {"y", j(v.y)}, {"rotation", j(v.rotation)}});
        })}, {"no_connects", each(p.no_connects, [](const auto& v) {
            return object({{"x", j(v.x)}, {"y", j(v.y)}});
        })}, {"plans", each(p.plans, [](const auto& entry) {
            return array({j(entry.first), each(entry.second, [](const auto& path) {
                return each(path, [](Point v) { return point(v); });
            })});
        })}, {"boxes", each(p.boxes, [](const auto& b) { return visual(b); })},
        {"label_bridged", each(p.label_bridged, [](const auto& v) { return j(v); })}, {"paper", j(p.paper)}});
}
JsonNode spacing(const SchematicSpacing& s) {
    return object({{"port_run", j(s.port_run)}, {"label_tap_gap", j(s.label_tap_gap)},
        {"hang_stub", j(s.hang_stub)}, {"stagger_extra", j(s.stagger_extra)}, {"cap_pitch", j(s.cap_pitch)},
        {"cluster_dx", j(s.cluster_dx)}, {"cluster_dy", j(s.cluster_dy)},
        {"flags_dy", j(s.flags_dy)}, {"flag_pitch", j(s.flag_pitch)}});
}

// Intentionally exact IEEE double comparison, not tolerance: rounding and
// arithmetic grouping are part of the schematic placement contract.
void equal(const JsonNode& got, const JsonNode& expected, const std::string& where) {
    require(got.kind == expected.kind, where + ": JSON type differs");
    switch (expected.kind) {
        case JsonKind::Null: break;
        case JsonKind::Bool: require(got.bool_value == expected.bool_value, where + ": bool differs"); break;
        case JsonKind::Number: {
            std::ostringstream detail;
            detail << std::setprecision(17) << where << ": " << got.number_value << " != " << expected.number_value;
            require(got.number_value == expected.number_value, detail.str()); break;
        }
        case JsonKind::String: require(got.string_value == expected.string_value,
            where + ": '" + got.string_value + "' != '" + expected.string_value + "'"); break;
        case JsonKind::Array:
            require(got.array_value.size() == expected.array_value.size(), where + ": array size differs");
            for (std::size_t i = 0; i < expected.array_value.size(); ++i)
                equal(got.array_value[i], expected.array_value[i], where + "[" + std::to_string(i) + "]");
            break;
        case JsonKind::Object:
            require(got.object_value.size() == expected.object_value.size(), where + ": object size differs");
            for (const auto& [key, value] : expected.object_value) equal(field(got, key), value, where + "." + key);
            break;
    }
}

template <typename Error = SchematicPlaceError, typename F>
void rejects(F action, const std::string& expected) {
    try { action(); }
    catch (const Error& e) { require(e.what() == expected, "wrong error: " + std::string(e.what())); return; }
    throw std::runtime_error("expected error: " + expected);
}
Refs refs_from(const JsonNode& n) {
    Refs out;
    for (const auto& v : n.array_value) out.push_back(str(v));
    return out;
}
Point point_from(const JsonNode& n) { return {num(n.array_value.at(0)), num(n.array_value.at(1))}; }
SchematicPlacement placement_from(const JsonNode& n) {
    const auto d = schematic_design_from_json(n, {});
    SchematicPlacement p;
    p.parts = d.parts; p.powers = d.powers; p.hlabels = d.hlabels;
    p.llabels = d.llabels; p.no_connects = d.no_connects; p.paper = d.paper;
    for (const auto& entry : field(n, "plans").array_value) {
        std::vector<std::vector<Point>> paths;
        for (const auto& raw : entry.array_value.at(1).array_value) {
            std::vector<Point> path;
            for (const auto& pt : raw.array_value) path.push_back(point_from(pt));
            paths.push_back(std::move(path));
        }
        p.plans.emplace_back(str(entry.array_value.at(0)), std::move(paths));
    }
    for (const auto& b : field(n, "boxes").array_value)
        p.boxes.push_back({num(field(b,"x0")),num(field(b,"y0")),num(field(b,"x1")),num(field(b,"y1")),
                          str(field(b,"kind")),str(field(b,"owner"))});
    for (const auto& name : refs_from(field(n, "label_bridged"))) p.label_bridged.insert(name);
    return p;
}
JsonNode pins_json(const std::vector<CircuitPinRefIr>& pins) {
    return each(pins, [](const auto& p) { return j(p.ref + "." + p.pin); });
}
JsonNode circuit_view(const CircuitSheetIr& c) {
    auto nc = c.nc;
    std::sort(nc.begin(), nc.end(), [](const auto& a, const auto& b) {
        return std::make_pair(a.ref,a.pin) < std::make_pair(b.ref,b.pin);
    });
    return object({{"parts", each(c.parts, [](const auto& p) { return j(p.ref); })},
        {"nets", each(c.nets, [](const auto& n) { return array({j(n.name),j(n.net_class),pins_json(n.pins)}); })},
        {"nc", pins_json(nc)}});
}
JsonNode metadata(const CircuitSheetIr& c) {
    return object({{"schema",j(c.schema)},{"name",j(c.name)},{"title",j(c.title)},
        {"ports",each(c.port_types, [](const auto& p) {
            return array({j(p.net),j(p.kind),j(p.has_pair_with),j(p.pair_with),j(p.has_impedance),j(p.impedance),
                j(p.has_role),j(p.role),j(p.has_bus),j(p.bus),j(p.has_speed_hz),j(p.speed_hz),
                j(p.has_level_v),j(p.level_v),j(p.has_expect),j(p.expect)});
        })}, {"hints",each(c.hints, [](const auto& h) { return array({j(h.net),j(h.style)}); })},
        {"loads",each(c.loads, [](const auto& l) { return array({j(l.rail),j(l.amps),j(l.note)}); })},
        {"waivers",each(c.waivers, [](const auto& w) { return array({j(w.kind),j(w.key),j(w.reason)}); })}});
}
JsonNode complete_circuit(const CircuitSheetIr& c) {
    return object({{"view",circuit_view(c)}, {"metadata",metadata(c)},
        {"parts",each(c.parts, [](const auto& p) {
            return array({j(p.ref),j(p.lib_id),j(p.value),j(p.footprint),strings(p.pin_numbers),
                each(p.fields, [](const auto& f) { return array({j(f.key),j(f.value)}); }),
                each(p.pin_names, [](const auto& n) { return array({j(n.name),strings(n.numbers)}); })});
        })}});
}
JsonNode blobs_json(const std::vector<std::set<std::string>>& blobs) {
    return each(blobs, [](const auto& b) { return each(b, [](const auto& r) { return j(r); }); });
}
void split_and_blobs(const fs::path& repo, const JsonNode& baseline, SymbolLibrary& lib) {
    const auto frozen = parse_json_file((repo / "native/tests/data/schematic_place/classifications.json").string());
    std::size_t cases = 0;
    for (const auto& record : field(baseline,"real").array_value) {
        const auto source = str(field(record,"source"));
        const auto& originals = field(frozen,"cases").array_value;
        const auto found = std::find_if(originals.begin(), originals.end(), [&](const auto& r) {
            return str(field(r,"source")) == source;
        });
        require(found != originals.end(), "missing frozen circuit " + source);
        const auto c = parse_circuit_ir(field(*found,"circuit"));
        auto split = split_auxiliary(c);
        equal(strings(split.second),field(record,"refs"),source+" auxiliary order");
        equal(circuit_view(split.first),field(record,"core"),source+" core snapshot");
        equal(metadata(split.first),metadata(c),source+" split metadata");
        equal(blobs_json(signal_blobs(c,lib)),field(record,"blobs"),source+" signal blobs");
        ++cases;
    }
    require(cases > 0,"empty page circuit fixtures");
    std::cout << cases << " frozen auxiliary splits / signal-blob classifications\n";
}
void probe_contracts(const JsonNode& baseline, SymbolLibrary& lib) {
    for (const auto& record : field(baseline,"probes").array_value) {
        const auto name = str(field(record,"name"));
        const auto c = parse_circuit_ir(field(record,"circuit"));
        auto split = split_auxiliary(c);
        Engine engine(split.first,lib);
        engine.pl = placement_from(field(record,"initial"));
        add_probe_row(engine,c,split.second);
        equal(placement(engine.pl),field(record,"expected"),name+" probes");
        require(engine._done == std::set<std::string>(split.second.begin(),split.second.end()),name+" done references");
        require(std::count_if(engine.pl.hlabels.begin(),engine.pl.hlabels.end(),[](const auto& h) {
            return h.name == "ONLY_PORT";
        }) == 1,"probe-only PORT must have exactly one hierarchical label");
        if (name == "empty-core") {
            const auto routed = route_schematic(c,engine.pl,lib);
            require(!routed.segs.empty(),"real native router failed to join probe-only sheet");
        }
        center_on_sheet(engine.pl);
        equal(placement(engine.pl),field(record,"centered"),name+" centered probes");
    }
    const auto& first = field(baseline,"probes").array_value.front();
    auto c = parse_circuit_ir(field(first,"circuit"));
    auto split = split_auxiliary(c);
    Engine engine(split.first,lib);
    for (auto& n : c.nets) n.pins.erase(std::remove_if(n.pins.begin(),n.pins.end(),
        [](const auto& p) { return p.ref == "TP1"; }),n.pins.end());
    rejects<std::invalid_argument>([&] { add_probe_row(engine,c,{"TP1"}); },"TP1: test point carries no net");
    add_probe_row(engine,c,{});
    require(engine.pl.parts.empty(),"empty probe list must be a no-op");
}
void translation_contracts(const JsonNode& baseline) {
    for (const auto& record : field(baseline,"translations").array_value) {
        auto p = placement_from(field(baseline,"translation_initial"));
        translate(p,num(field(record,"dx")),num(field(record,"dy")));
        equal(placement(p),field(record,"expected"),"translation");
    }
    auto p = placement_from(field(baseline,"translation_initial"));
    center_on_sheet(p);
    equal(placement(p),field(baseline,"centered_primitives"),"primitive centering");
    SchematicPlacement empty;
    rejects([&] { center_on_sheet(empty); },"cannot center placement without boxes or planned points");
    empty.plan("N",{{-1.27,-2.54},{1.27,2.54}});
    center_on_sheet(empty);
    require(empty.plans.front().second.front().front() == Point{147.32,97.79},"plans-only centering");
}
void partition_contracts(const JsonNode& baseline, SymbolLibrary& lib) {
    const auto& fixture = field(baseline,"partition");
    const auto c = parse_circuit_ir(field(fixture,"circuit"));
    equal(blobs_json(signal_blobs(c,lib)),field(fixture,"blobs"),"synthetic signal blobs");
    for (const auto& record : field(fixture,"subsets").array_value) {
        const auto refs = refs_from(field(record,"refs"));
        const auto p = subset_page(c,{refs.begin(),refs.end()},integer(field(record,"page")));
        equal(complete_circuit(p),complete_circuit(parse_circuit_ir(field(record,"expected"))),"subset metadata and ordering");
    }
    for (const auto& record : field(fixture,"bins").array_value) {
        std::vector<Refs> calls;
        const auto pages = partition_pages_with_fit(c,lib,[&](const auto& candidate) {
            Refs names; for (const auto& p : candidate.parts) names.push_back(p.ref);
            calls.push_back(names); return names.size() <= static_cast<std::size_t>(integer(field(record,"limit")));
        });
        equal(each(calls,[](const auto& names) { return strings(names); }),field(record,"fit_calls"),"greedy fit call order");
        const auto& expected = field(record,"pages").array_value;
        require(pages.size() == expected.size(),"greedy page count");
        for (std::size_t i=0;i<pages.size();++i)
            equal(complete_circuit(pages[i]),complete_circuit(parse_circuit_ir(expected[i])),"greedy page contents");
    }
    rejects<std::invalid_argument>([&] { subset_page(c,{"U1"},1); },str(field(fixture,"cut_error")));
    rejects<std::invalid_argument>([&] { subset_page(c,{"UNKNOWN"},1); },"unknown page part 'UNKNOWN'");
    for (const auto& entry : field(baseline,"congestion").array_value)
        require(is_congestion(str(entry.array_value.at(0))) == boolean(entry.array_value.at(1)),"structural/congestion classification");
}
SchematicPlacement sized(double width,double height) {
    SchematicPlacement p; p.boxes.push_back({0,0,width,height,"body","test-size"}); return p;
}
void retry_contracts(const JsonNode& baseline, SymbolLibrary& lib) {
    CircuitSheetIr c; c.name="retry";
    int build_calls=0,route_calls=0,visual_calls=0;
    std::vector<SchematicSpacing> spaces;
    PageOperations ops{
        [&](const auto&,auto&,const auto& sp) {
            spaces.push_back(sp);
            if (++build_calls == 1) throw SchematicPlaceError("first build");
            return sized(272,180);
        },
        [&](const auto&,const auto&,auto&) {
            if (++route_calls == 1) throw SchematicRouteError("second route");
            return SchematicRoutedSheet{};
        },
        [&](const auto&) { ++visual_calls; return VisualResult{visual_calls>1,{"third visual"}}; }};
    const auto page = place_and_route_with(c,lib,{},4,ops);
    require(page.placement.paper == "A4" && page.circuit.name == "retry","A4 boundary / caller circuit snapshot");
    require(build_calls==4 && route_calls==3 && visual_calls==2,"retry operation sequencing");
    SchematicSpacing expected;
    for (const auto& s : spaces) { equal(spacing(s),spacing(expected),"fresh expanded spacing"); expected=expected.expanded(); }
    equal(box(page.geometry.boxes.front().bounds()),array({j(0),j(0),j(272),j(180)}),"A4 geometry");

    auto original = placement_from(field(baseline,"translation_initial"));
    original.boxes.push_back({0,0,300,200,"body","promotion"});
    SchematicRoutedSheet before;
    before.segs.push_back({12.3455,-8.9163,123.4555,-8.9163,"N"});
    before.junctions.push_back({12.3455,-8.9163});
    ops.build=[&](const auto&,auto&,const auto&) { return original; };
    ops.route=[&](const auto&,const auto&,auto&) { return before; };
    ops.check_visual=[](const auto&) { return VisualResult{}; };
    const auto promoted = place_and_route_with(c,lib,{},1,ops);
    require(promoted.placement.paper=="A3","A3 promotion");
    auto shifted=original;
    translate(shifted,62.23,48.26); shifted.paper="A3";
    equal(placement(promoted.placement),placement(shifted),"A3 translated primitives");
    require(promoted.routed.segs[0].x0==74.575 && promoted.routed.segs[0].y0==39.344
        && promoted.routed.segs[0].x1==185.685 && promoted.routed.junctions[0].x==74.575,
        "A3 routed/junction rounding");
    require(promoted.geometry.wires[0].x0==promoted.routed.segs[0].x0
        && promoted.geometry.junctions[0].y==promoted.routed.junctions[0].y,"A3 geometry refreshed");
    ops.route=[](const auto&,const auto&,auto&) { return SchematicRoutedSheet{}; };
    for (auto dims : {Point{390,265},Point{272.001,180},Point{272,180.001}}) {
        ops.build=[&](const auto&,auto&,const auto&) { return sized(dims.first,dims.second); };
        require(place_and_route_with(c,lib,{},1,ops).placement.paper=="A3","inclusive A3 boundaries");
    }
    ops.build=[](const auto&,auto&,const auto&) { return sized(390.501,265.501); };
    rejects([&] { place_and_route_with(c,lib,{},2,ops); },
        "placement infeasible after 2 expansions; last failure:\nsheet 391x266 mm exceeds even A3 (390x265)");
    ops.check_visual=[](const auto&) { return VisualResult{false,{"overlap A","cross B"}}; };
    rejects([&] { place_and_route_with(c,lib,{},1,ops); },
        "placement infeasible after 1 expansions; last failure:\nVISUAL GATE: FAIL\n  overlap A\n  cross B");
    rejects([&] { place_and_route_with(c,lib,{},0,ops); },"placement infeasible after 0 expansions; last failure:\n?");
    rejects([&] { place_and_route_with(c,lib,{},-1,ops); },"placement infeasible after -1 expansions; last failure:\n?");
    ops.build=[](const auto&,auto&,const auto&) -> SchematicPlacement { throw SymbolError("symbol failure"); };
    rejects<SymbolError>([&] { place_and_route_with(c,lib,{},8,ops); },"symbol failure");
}
void pagination_contracts(const JsonNode& baseline,SymbolLibrary& lib) {
    const auto c = parse_circuit_ir(field(field(baseline,"partition"),"circuit"));
    std::vector<std::string> calls;
    PageOperations ops{
        [&](const auto& sheet,auto&,const auto&) {
            calls.push_back(sheet.name);
            if (sheet.parts.size()>4) throw SchematicPlaceError("congested");
            return sized(100,100);
        }, [](const auto&,const auto&,auto&) { return SchematicRoutedSheet{}; },
        [](const auto&) { return VisualResult{}; }};
    const auto pages=paginate_and_route_with(c,lib,{},3,ops);
    require(pages.size()==2 && pages[0].circuit.name==c.name+".1" && pages[1].circuit.name==c.name+".2",
        "congestion must paginate and route child circuits");
    require(std::count(calls.begin(),calls.end(),c.name)==3,"full circuit attempt budget");
    require(std::count(calls.begin(),calls.end(),c.name+".0")==5,"fit uses two retries per failing bin, one on pass");
    const auto seen=calls.size();
    ops.build=[&](const auto& sheet,auto&,const auto&) -> SchematicPlacement {
        calls.push_back(sheet.name); throw SchematicPlaceError("no power symbol mapped for rail 'BAD'");
    };
    rejects([&] { paginate_and_route_with(c,lib,{},2,ops); },
        "placement infeasible after 2 expansions; last failure:\nroute: no power symbol mapped for rail 'BAD'");
    require(calls.size()==seen+2,"structural errors must not trigger pagination");
    CircuitSheetIr one; one.parts.push_back(c.parts.front());
    ops.build=[](const auto&,auto&,const auto&) -> SchematicPlacement { throw SchematicPlaceError("blocked"); };
    rejects([&] { paginate_and_route_with(one,lib,{},1,ops); },
        "placement infeasible after 1 expansions; last failure:\nroute: blocked");
}
JsonNode segments_json(const std::vector<VisualSegment>& segs) {
    return each(segs,[](const auto& s) {
        return object({{"x0",j(s.x0)},{"y0",j(s.y0)},{"x1",j(s.x1)},{"y1",j(s.y1)},{"net",j(s.net)}});
    });
}
void full_entry_contracts(const fs::path& repo,SymbolLibrary& lib) {
    const auto baseline=parse_json_file((repo/"native/tests/data/schematic_place_pages/full_pages.json").string());
    require(str(field(baseline,"schema"))=="schgen.schematic_place.full_pages_baseline/1","full pages schema");
    std::size_t count=0;
    for (const auto& record : field(baseline,"cases").array_value) {
        const auto name=str(field(record,"name"));
        const auto c=parse_circuit_ir(field(record,"circuit"));
        const auto before=complete_circuit(c);
        equal(placement(build_schematic_placement(c,lib)),field(record,"build"),name+" full build");
        const auto page=place_and_route_schematic(c,lib);
        equal(placement(page.placement),field(record,"placement"),name+" public placement");
        equal(object({{"segs",segments_json(page.routed.segs)},
            {"junctions",each(page.routed.junctions,[](const auto& p) { return point({p.x,p.y}); })}}),
            field(record,"routed"),name+" public route");
        equal(object({{"boxes",each(page.geometry.boxes,[](const auto& b) { return visual(b); })},
            {"wires",segments_json(page.geometry.wires)},
            {"junctions",each(page.geometry.junctions,[](const auto& p) { return object({{"x",j(p.x)},{"y",j(p.y)}}); })}}),
            field(record,"geometry"),name+" public geometry");
        require(check_visual_geometry(page.geometry).ok,name+" real visual gate");
        equal(complete_circuit(c),before,name+" input unchanged");
        if (name=="single_port_probe") {
            const auto pages=paginate_and_route_schematic(c,lib);
            require(pages.size()==1 && pages.front().placement.hlabels.size()==1,"public probe-only pagination/hierarchy");
            equal(placement(pages.front().placement),field(record,"placement"),"public single-page pagination");
        }
        ++count;
    }
    std::cout << count << " full native build/route/visual baselines passed\n";
}
} // namespace

int main(int argc,char** argv) {
    try {
        if (argc!=2) throw std::runtime_error("usage: schematic_place_pages_contracts <repository>");
        const auto repo=fs::canonical(argv[1]);
        const auto baseline=parse_json_file((repo/"native/tests/data/schematic_place_pages/pages.json").string());
        require(str(field(baseline,"schema"))=="schgen.schematic_place.pages_baseline/1","pages fixture schema");
        SymbolLibrary lib(std::vector<fs::path>{repo/"native/tests/data/symbols/kicad",repo/"schgen/lib",repo/"parts"});
        split_and_blobs(repo,baseline,lib);
        probe_contracts(baseline,lib);
        translation_contracts(baseline);
        partition_contracts(baseline,lib);
        retry_contracts(baseline,lib);
        pagination_contracts(baseline,lib);
        full_entry_contracts(repo,lib);
        std::cout << checks << " native schematic page checks passed\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "schematic page contract failure: " << e.what() << '\n'; return 1;
    }
}
