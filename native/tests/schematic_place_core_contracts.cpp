// Frozen Python-oracle contracts. No interpreter, installed KiCad, board or
// production placement entry point is used by this bounded-core executable.
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
JsonNode legs_json(const std::vector<Leg>& legs) {
    return each(legs, [](const auto& v) { return array({j(v.ref), j(v.a), j(v.b)}); });
}
JsonNode refs_json(const RefMap& refs) {
    return each(refs, [](const auto& v) { return array({j(v.first), strings(v.second)}); });
}
JsonNode chain_json(const FloatChain& c) {
    return object({{"kind", j(c.kind)}, {"root", j(c.root)},
                   {"legs", legs_json(c.legs)}, {"hangs", refs_json(c.hangs)}});
}
JsonNode chains_json(const std::vector<ChainPtr>& chains) {
    return each(chains, [](const auto& c) { return chain_json(*c); });
}
JsonNode classification(const Engine& e) {
    return object({{"multi", strings(e.multi)},
        {"multi_nets", each(e.multi_nets, [](const auto& s) { return j(s); })},
        {"cluster", refs_json(e.cluster)}, {"hang", refs_json(e.hang)},
        {"pull", each(e.pull, [](const auto& entry) {
            return array({j(entry.first), each(entry.second, [](const auto& v) {
                return array({j(v.first), j(v.second)});
            })});
        })}, {"series", legs_json(e.series)}, {"shunts", strings(e.shunts)},
        {"float_chains", chains_json(e.float_chains)},
        {"trunks", each(e.trunks, [](const auto& entry) {
            const auto& t = *entry.second;
            return array({j(entry.first), object({{"net", j(t.net)}, {"zone", j(t.zone)},
                {"direct", each(t.direct, [](const auto& d) {
                    return array({point(d.pin_pt), j(d.side)});
                })}, {"rungs", each(t.rungs, [](const auto& r) {
                    return object({{"net", j(r.net)}, {"pin_pt", point(r.pin_pt)},
                        {"kind", j(r.kind)}, {"legs", strings(r.legs)}, {"row", j(r.row)}});
                })}, {"terms", strings(t.terms)}, {"chains", chains_json(t.chains)},
                {"nodes", each(t.nodes, [](double n) { return j(n); })}, {"y", j(t.y)}})});
        })}});
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
template <typename F> void rejects(F f, const std::string& expected) {
    try { f(); }
    catch (const SchematicPlaceError& e) {
        require(e.what() == expected, "wrong placement error: " + std::string(e.what()) + " != " + expected);
        return;
    }
    throw std::runtime_error("expected placement error: " + expected);
}
Point point_from(const JsonNode& n) {
    require(n.kind == JsonKind::Array && n.array_value.size() == 2, "invalid fixture point");
    return {num(n.array_value[0]), num(n.array_value[1])};
}
Box4 box_from(const JsonNode& n) {
    require(n.kind == JsonKind::Array && n.array_value.size() == 4, "invalid fixture box");
    return {num(n.array_value[0]), num(n.array_value[1]), num(n.array_value[2]), num(n.array_value[3])};
}

void real_classifications(const fs::path& data, SymbolLibrary& lib) {
    const auto baseline = parse_json_file((data / "classifications.json").string());
    require(str(field(baseline, "schema")) == "schgen.schematic_place.core_baseline/1", "classification schema");
    const auto& cases = field(baseline, "cases").array_value;
    require(!cases.empty(), "empty classifications fixture");
    std::size_t aliases = 0;
    for (const auto& record : cases) {
        const auto name = str(field(record, "source"));
        auto circuit = parse_circuit_ir(field(record, "circuit"));
        std::set<std::string> excluded;
        for (const auto& ref : field(record, "excluded_aux_refs").array_value) excluded.insert(str(ref));
        // The fixture stores the explicit auxiliary split performed by Python;
        // this is not a second native implementation of the future page stage.
        circuit.parts.erase(std::remove_if(circuit.parts.begin(), circuit.parts.end(),
            [&](const auto& p) { return excluded.count(p.ref); }), circuit.parts.end());
        for (auto& n : circuit.nets) n.pins.erase(std::remove_if(n.pins.begin(), n.pins.end(),
            [&](const auto& p) { return excluded.count(p.ref); }), n.pins.end());
        circuit.nc.erase(std::remove_if(circuit.nc.begin(), circuit.nc.end(),
            [&](const auto& p) { return excluded.count(p.ref); }), circuit.nc.end());
        Engine e(circuit, lib);
        equal(classification(e), field(record, "expected"), name);
        for (const auto& ch : e.float_chains) if (ch->kind == "trunk") {
            const auto& links = e.trunks.at(ch->root)->chains;
            require(std::find(links.begin(), links.end(), ch) != links.end(), name + ": lost shared trunk chain");
            ++aliases;
        }
        e._classify();
        equal(classification(e), field(record, "expected"), name + " repeat classification");
        // Caller-owned IR mutation cannot invalidate the Engine's indices.
        circuit.parts.clear(); circuit.nets.clear();
        for (const auto& p : e.c.parts) require(&e.part(p.ref) == &p, name + ": part index snapshot");
        for (const auto& n : e.c.nets) require(&e.net(n.name) == &n, name + ": net index snapshot");
    }
    require(aliases != 0, "real fixtures do not exercise shared trunk/chain ownership");
    std::cout << cases.size() << " frozen circuit classifications; " << aliases << " shared trunk chains\n";
}

void primitives(const fs::path& data, SymbolLibrary& lib) {
    const auto baseline = parse_json_file((data / "primitives.json").string());
    require(str(field(baseline, "schema")) == "schgen.schematic_place.primitives_baseline/1", "primitive schema");
    Engine e(parse_circuit_ir(field(baseline, "circuit")), lib);
    for (const auto& op : field(baseline, "operations").array_value) {
        const auto& a = op.array_value;
        const auto name = str(a.at(0));
        if (name == "passive") e.passive(str(a.at(1)), num(a.at(2)), num(a.at(3)), integer(a.at(4)), str(a.at(5)));
        else if (name == "label") e.label(str(a.at(1)), num(a.at(2)), num(a.at(3)), integer(a.at(4)), str(a.at(5)));
        else if (name == "llabel") e.llabel(str(a.at(1)), num(a.at(2)), num(a.at(3)), integer(a.at(4)));
        else if (name == "power") e.power(str(a.at(1)), num(a.at(2)), num(a.at(3)), integer(a.at(4)), boolean(a.at(5)));
        else if (name == "flag") e.flag(str(a.at(1)), num(a.at(2)), num(a.at(3)), integer(a.at(4)));
        else if (name == "nc") e.pl.no_connects.push_back({num(a.at(1)), num(a.at(2))});
        else if (name == "plan") {
            std::vector<Point> path;
            for (const auto& p : a.at(2).array_value) path.push_back(point_from(p));
            e.pl.plan(str(a.at(1)), path);
        } else throw std::runtime_error("unknown primitive fixture operation: " + name);
    }
    equal(placement(e.pl), field(baseline, "placement"), "primitives.placement");
    require(e._done == std::set<std::string>{"C1", "L1", "R1"}, "passive completion state");
    const auto& helpers = field(baseline, "helpers");
    equal(box(e._extent()), field(helpers, "extent"), "extent");
    equal(each(e._plan_seg_boxes(), [](auto b) { return box(b); }), field(helpers, "segment_boxes"), "segment boxes");
    equal(each(e._nc_boxes(), [](auto b) { return box(b); }), field(helpers, "nc_boxes"), "NC boxes");
    for (const auto& q : field(helpers, "spot_queries").array_value) {
        const auto& a = q.array_value;
        require(e._spot_free(box_from(a.at(0)), num(a.at(1))) == boolean(a.at(2)), "spot-free baseline");
    }
    for (const auto& q : field(helpers, "band_queries").array_value) {
        const auto& a = q.array_value;
        equal(j(e._band_edge(num(a.at(0)), num(a.at(1)), integer(a.at(2)), num(a.at(3)))), a.at(4), "band edge");
    }
    for (const auto& record : field(helpers, "symbol_geometry").array_value) {
        const auto& symbol = lib.get(str(field(record, "lib_id")));
        const auto x = num(field(record, "x")), y = num(field(record, "y"));
        const auto rot = integer(field(record, "rotation"));
        const auto name = symbol.lib_id + "@" + std::to_string(rot);
        equal(visual(body_box_page(symbol, x, y, rot, "body", "X")), field(record, "body"), name + " body");
        equal(point(value_anchor(symbol, x, y, rot)), field(record, "value_anchor"), name + " value anchor");
        SchematicPlacedPart part;
        part.ref = "X"; part.x = x; part.y = y; part.rotation = rot;
        equal(each(pin_text_boxes(symbol, part), [](const auto& b) { return visual(b); }),
              field(record, "pin_text_boxes"), name + " pin text");
    }
    SchematicSpacing sp;
    for (const auto& expected : field(baseline, "spacings").array_value) {
        equal(spacing(sp), expected, "spacing expansion"); sp = sp.expanded();
    }
}

void chain_contracts(const fs::path& data, SymbolLibrary& lib) {
    const auto baseline = parse_json_file((data / "chains.json").string());
    require(str(field(baseline, "schema")) == "schgen.schematic_place.chains_baseline/1", "chain schema");
    const auto circuit = parse_circuit_ir(field(baseline, "circuit"));
    for (const auto& record : field(baseline, "cases").array_value) {
        Engine e(circuit, lib);
        std::set<std::string> component;
        for (const auto& n : field(record, "component").array_value) component.insert(str(n));
        FloatLegs legs;
        for (const auto& entry : field(record, "legs").array_value) {
            const auto name = str(entry.array_value.at(0));
            for (const auto& l : entry.array_value.at(1).array_value) {
                const auto& a = l.array_value;
                legs[name].push_back({str(a.at(0)), str(a.at(1)), str(a.at(2))});
            }
        }
        if (const auto* expected = object_field(record, "expected")) {
            const auto ch = e._linearise(component, legs);
            equal(chain_json(*ch), *expected, "chain " + str(field(record, "name")));
            if (ch->kind == "trunk") require(e.trunks.at(ch->root)->chains.back() == ch, "direct chain alias");
        } else {
            const auto* override_error = object_field(record, "native_error");
            const auto message = str(override_error ? *override_error : field(record, "error"));
            rejects([&] { e._linearise(component, legs); }, message);
        }
    }
}

void stable_handles(SymbolLibrary& lib) {
    OrderedMap<int> m;
    m["second"] = 2; m["first"] = 1; m["second"] = 22;
    require(m.size() == 2 && m.begin()->first == "second", "overwrite reordered OrderedMap");
    require(m.erase("second") && !m.erase("missing"), "OrderedMap erase result");
    m["second"] = 222;
    require(m.begin()->first == "first" && std::next(m.begin())->first == "second", "erase/reinsert must append");
    for (int i = 0; i < 1024; ++i) m["grow" + std::to_string(i)] = i;
    require(m.at("first") == 1 && m.at("second") == 222, "lookup after OrderedMap vector growth");
    // Never retain a reference to the vector pair/value across insertion. Copy
    // the shared_ptr by value; payload mutation then remains safe and aliases.
    TrunkMap trunks;
    trunks["root"] = std::make_shared<Trunk>();
    auto root = trunks.at("root");
    root->net = "root";
    auto chain = std::make_shared<FloatChain>();
    root->chains.push_back(chain);
    auto alias = trunks;
    for (int i = 0; i < 1024; ++i) trunks["grow" + std::to_string(i)] = std::make_shared<Trunk>();
    root->nodes.push_back(17.78); chain->root = "changed";
    require(trunks.at("root") == root && alias.at("root") == root, "shared trunk payload must survive map growth/copy");
    require(alias.at("root")->chains.front()->root == "changed", "shared chain payload must retain mutation");
    trunks.erase("root");
    require(root->nodes.front() == 17.78, "held shared payload must survive map erasure");
    rejects([&] { m.at("absent"); }, "missing placement key: absent");

    Engine e(CircuitSheetIr{}, lib);
    const auto first = e.power("+3V3", 0, 0);
    const auto second = e.flag("GND", 0, 0, 0);
    for (int i = 0; i < 1024; ++i) e.flag("GND", i * 1.27, 20.32, 0);
    require(first == 0 && second == 1 && e.pl.powers[first].ref == "#PWR01"
            && e.pl.powers[second].ref == "#FLG01", "power/flag indices survive vector growth");
    e.pl.powers[first].show_value = false;
    require(!e.pl.powers.at(first).show_value && e.pl.powers.back().ref == "#FLG1025", "index mutation/counter width");
}

CircuitSheetIr passive_circuit(const std::string& left_class = "power", const std::string& right_class = "ground") {
    CircuitSheetIr c;
    CircuitPartIr p; p.ref = "R1"; p.lib_id = "Device:R"; p.value = "10k";
    c.parts.push_back(p);
    c.nets.push_back({"A", left_class, {{"R1", "1"}}});
    c.nets.push_back({"B", right_class, {{"R1", "2"}}});
    return c;
}
void edge_contracts(SymbolLibrary& lib) {
    auto c = passive_circuit();
    Engine e(c, lib);
    require(e.other_pin("R1", "1") == "2" && e._pin_of_net("R1", "A") == "1", "pin index lookup");
    require(e.net_of("R1", "missing") == nullptr, "missing pin must return null");
    rejects([&] { e.other_pin("R1", "3"); }, "R1 is not a 2-pin part");
    rejects([&] { e._pin_of_net("R1", "missing"); }, "R1: no pin on net 'missing'");
    rejects([&] { e.part("missing"); }, "unknown part 'missing'");
    rejects([&] { e.net("missing"); }, "unknown net 'missing'");
    rejects([&] { e.power("UNMAPPED", 0, 0); }, "no power symbol mapped for rail 'UNMAPPED'");
    require(e._pwr == 1 && e.pl.powers.empty(), "failed power lookup counter/partial state");
    const auto index = e.power("+NATIVE_CORE_EDGE_RAIL", 0, 0);
    require(e.pl.powers[index].ref == "#PWR02", "failed lookup must still consume Python counter");
    rejects([&] { e._power_lib("can't"); }, "no power symbol mapped for rail \"can't\"");
    rejects([&] { e._power_lib("both'\"\\\n\r\t\x01"); },
        "no power symbol mapped for rail 'both\\'\"\\\\\\n\\r\\t\\x01'");
    require(side_of_rotation(-90) == "top" && side_of_rotation(450) == "bottom", "wrapped pin side rotation");
    rejects([&] { side_of_rotation(45); }, "unsupported pin side rotation 45");
    rejects([&] { pin(lib.get("Device:R"), "3"); }, "pin 3 not in Device:R");

    c.nets[1].pins.clear();
    rejects([&] { Engine bad(c, lib); }, "R1: unnetted passive");
    c = passive_circuit(); c.parts.push_back(c.parts.front());
    rejects([&] { Engine bad(c, lib); }, "duplicate part reference R1");
    c = passive_circuit(); c.nets.push_back(c.nets.front());
    rejects([&] { Engine bad(c, lib); }, "duplicate net name A");
    c = passive_circuit(); c.nets.push_back({"second_owner", "power", {{"R1", "1"}}});
    Engine first_owner(c, lib);
    require(first_owner.net_of("R1", "1")->name == "A", "pin2net first owner must win like setdefault");
    c = passive_circuit(); c.parts[0].lib_id = "Connector:TestPoint";
    rejects([&] { Engine bad(c, lib); }, "R1: 1-pin part is neither a multi-pin part nor a 2-pin passive");
    c = passive_circuit("signal", "power");
    rejects([&] { Engine bad(c, lib); }, "floating nets ['A']: single-ended chain tops out on non-PORT net 'A' — dangling internal net");
    c = passive_circuit("port", "power");
    Engine strap(c, lib);
    require(strap.float_chains.size() == 1 && strap.float_chains[0]->kind == "port"
        && strap.float_chains[0]->root == "A" && strap.float_chains[0]->legs[0].a == "A"
        && strap.float_chains[0]->legs[0].b == "B" && strap.pull.empty(), "one-leg port strap consumed/oriented");
    c = passive_circuit("signal", "signal");
    rejects([&] { Engine bad(c, lib); }, "floating nets ['A', 'B']: no rail/pin end");
    Engine empty(CircuitSheetIr{}, lib);
    equal(box(empty._extent()), array({j(0), j(0), j(0), j(0)}), "empty extent");
    require(empty._spot_free({0, 0, 1, 1}) && empty._band_edge(0, 1, 1, 42) == 42, "empty collision helpers");
}
}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: schematic_place_core_contracts <repository>");
        const fs::path repo = fs::canonical(argv[1]);
        const auto data = repo / "native/tests/data/schematic_place";
        SymbolLibrary lib(std::vector<fs::path>{repo / "native/tests/data/symbols/kicad", repo / "schgen/lib", repo / "parts"});
        real_classifications(data, lib);
        primitives(data, lib);
        chain_contracts(data, lib);
        stable_handles(lib);
        edge_contracts(lib);
        std::cout << checks << " schematic placement core checks passed\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "schematic placement core contract failure: " << e.what() << '\n';
        return 1;
    }
}
