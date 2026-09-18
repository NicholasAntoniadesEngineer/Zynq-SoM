#include "schematic_place_internal.hpp"

#include "schgen/occupancy.hpp"
#include "schgen/pack.hpp"
#include "schgen/place_search.hpp"
#include "schgen/turn.hpp"

#include <cmath>
#include <iomanip>
#include <sstream>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace schgen {

SchematicSpacing SchematicSpacing::expanded() const {
    auto up = [](double v) { return gceil(v * 1.25, symbol_grid); };
    return {up(port_run), label_tap_gap, hang_stub, up(stagger_extra), up(cap_pitch),
            up(cluster_dx), up(cluster_dy), up(flags_dy), up(flag_pitch)};
}

void SchematicPlacement::plan(const std::string& net, const std::vector<RoutePoint>& points) {
    std::vector<RoutePoint> rounded;
    rounded.reserve(points.size());
    for (const auto& p : points) rounded.emplace_back(py_round(p.first, 3), py_round(p.second, 3));
    for (auto& [name, paths] : plans) {
        if (name == net) { paths.push_back(std::move(rounded)); return; }
    }
    plans.push_back({net, {std::move(rounded)}});
}

namespace schematic_place {
namespace {
bool signal(const CircuitNetIr& n) { return n.net_class == "signal" || n.net_class == "port"; }
std::string py_quote(const std::string& s) {
    const char quote = s.find('\'') != std::string::npos && s.find('"') == std::string::npos ? '"' : '\'';
    std::string out(1, quote);
    constexpr char hex[] = "0123456789abcdef";
    for (unsigned char ch : s) {
        if (ch == quote || ch == '\\') out += '\\';
        if (ch == '\n') out += "\\n";
        else if (ch == '\r') out += "\\r";
        else if (ch == '\t') out += "\\t";
        else if (ch < 32 || ch == 127) {
            out += "\\x"; out += hex[ch >> 4]; out += hex[ch & 15];
        } else out += static_cast<char>(ch);
    }
    return out + quote;
}
std::string component_name(const std::set<std::string>& component) {
    std::string out = "[";
    for (const auto& name : component) out += (out.size() == 1 ? "" : ", ") + py_quote(name);
    return out + "]";
}
std::string numbered(const std::string& prefix, std::size_t count) {
    std::ostringstream out;
    out << prefix << std::setfill('0') << std::setw(2) << count;
    return out.str();
}
VisualBox visual(const Box4& b, const std::string& kind, const std::string& owner) {
    return {b.x0, b.y0, b.x1, b.y1, kind, owner};
}
const Sexpr* child(const Sexpr& value, const std::string& tag) {
    const auto* list = std::get_if<SexprList>(&value.v);
    if (!list) return nullptr;
    for (const auto& entry : *list) {
        const auto* node = std::get_if<SexprList>(&entry.v);
        if (node && !node->empty()) {
            const auto* sym = std::get_if<Sexpr::Sym>(&node->front().v);
            if (sym && sym->name == tag) return &entry;
        }
    }
    return nullptr;
}
double coordinate(const Sexpr& value) {
    if (const auto* number = std::get_if<double>(&value.v)) return *number;
    const auto* str = std::get_if<std::string>(&value.v);
    const auto* sym = std::get_if<Sexpr::Sym>(&value.v);
    if (!str && !sym) throw SchematicPlaceError("symbol Value property: expected coordinate");
    const std::string& text = str ? *str : sym->name;
    try {
        std::size_t used;
        const double out = std::stod(text, &used);
        if (used == text.size() && std::isfinite(out)) return out;
    } catch (const std::exception&) {}
    throw SchematicPlaceError("symbol Value property: invalid coordinate " + py_quote(text));
}
int priority(const std::string& kind) {
    if (kind == "trunk") return 0;
    if (kind == "pin") return 1;
    if (kind == "rail") return 2;
    if (kind == "gnd") return 3;
    throw SchematicPlaceError("invalid floating-chain endpoint kind: " + kind);
}
template <typename T, typename Predicate> void remove_if(std::vector<T>& values, Predicate predicate) {
    values.erase(std::remove_if(values.begin(), values.end(), predicate), values.end());
}
}  // namespace

std::pair<double, double> text_wh(const std::string& text) {
    return schgen::text_wh(text, TEXT_SIZE, CHAR_W, LINE_H);
}
Box4 centered_box(const std::string& text, double x, double y, bool vertical) {
    return schgen::centered_box(text, x, y, TEXT_SIZE, CHAR_W, LINE_H, vertical);
}
Box4 glabel_box(const std::string& text, double x, double y, int rotation) {
    return schgen::glabel_box(text, x, y, rotation, TEXT_SIZE, CHAR_W, LINE_H,
                              GLABEL_PAD_LEN, GLABEL_H, GLABEL_INSET);
}
Box4 llabel_box(const std::string& text, double x, double y, int rotation) {
    return schgen::llabel_box(text, x, y, rotation, TEXT_SIZE, CHAR_W, LINE_H, 0.7, 0.127);
}
VisualBox body_box_page(const SymbolDef& symbol, double ax, double ay, int rotation,
                        const std::string& kind, const std::string& owner) {
    const auto b = symbol_body_box_page(symbol, ax, ay, rotation);
    return {b[0], b[1], b[2], b[3], kind, owner};
}
Point value_anchor(const SymbolDef& symbol, double ax, double ay, int rotation) {
    for (const auto& node : std::get<SexprList>(symbol.raw.v)) {
        const auto* property = std::get_if<SexprList>(&node.v);
        if (!property || property->size() <= 2) continue;
        const auto* tag = std::get_if<Sexpr::Sym>(&property->front().v);
        if (!tag || tag->name != "property") continue;
        const auto* name = std::get_if<std::string>(&(*property)[1].v);
        const auto* bare = std::get_if<Sexpr::Sym>(&(*property)[1].v);
        if ((!name || *name != "Value") && (!bare || bare->name != "Value")) continue;
        const auto* at = child(node, "at");
        if (!at) return sch_xform(0.0, 0.0, ax, ay, rotation);
        const auto& coords = std::get<SexprList>(at->v);
        if (coords.size() < 3) throw SchematicPlaceError(symbol.lib_id + ": malformed Value position");
        return sch_xform(coordinate(coords[1]), coordinate(coords[2]), ax, ay, rotation);
    }
    return {ax, ay - 3.556};
}
std::vector<VisualBox> pin_text_boxes(const SymbolDef& symbol, const SchematicPlacedPart& part) {
    std::vector<PinTextIn> pins;
    for (const auto& p : symbol.pins)
        pins.push_back({p.x, p.y, p.rotation, p.length, p.hidden, p.number, p.name});
    std::vector<VisualBox> boxes;
    for (const auto& b : schgen::pin_text_boxes(pins, part.x, part.y, part.rotation,
            symbol.pin_numbers_hidden, symbol.pin_names_hidden, CHAR_W, LINE_H, TEXT_SIZE))
        boxes.push_back(visual(b.box, b.kind, part.ref));
    return boxes;
}
const SymbolPin& pin(const SymbolDef& symbol, const std::string& number) {
    for (const auto& p : symbol.pins) if (p.number == number) return p;
    throw SchematicPlaceError("pin " + number + " not in " + symbol.lib_id);
}
std::string side_of_rotation(int rotation) {
    switch ((rotation % 360 + 360) % 360) {
        case 0: return "left";
        case 180: return "right";
        case 270: return "top";
        case 90: return "bottom";
        default: throw SchematicPlaceError("unsupported pin side rotation " + std::to_string(rotation));
    }
}

Engine::Engine(const CircuitSheetIr& circuit, SymbolLibrary& library, const SchematicSpacing& spacing)
    : c(circuit), lib(library), sp(spacing) {
    for (std::size_t i = 0; i < c.parts.size(); ++i) {
        if (!parts_.emplace(c.parts[i].ref, i).second)
            throw SchematicPlaceError("duplicate part reference " + c.parts[i].ref);
    }
    for (std::size_t i = 0; i < c.nets.size(); ++i) {
        const auto& n = c.nets[i];
        if (!nets_.emplace(n.name, i).second)
            throw SchematicPlaceError("duplicate net name " + n.name);
        for (const auto& p : n.pins) pin2net_.emplace(PinKey{p.ref, p.pin}, i);
    }
    _classify();
}
const CircuitPartIr& Engine::part(const std::string& ref) const {
    const auto found = parts_.find(ref);
    if (found == parts_.end()) throw SchematicPlaceError("unknown part " + py_quote(ref));
    return c.parts[found->second];
}
const CircuitNetIr& Engine::net(const std::string& name) const {
    const auto found = nets_.find(name);
    if (found == nets_.end()) throw SchematicPlaceError("unknown net " + py_quote(name));
    return c.nets[found->second];
}
const CircuitNetIr* Engine::net_of(const std::string& ref, const std::string& number) const {
    const auto found = pin2net_.find({ref, number});
    return found == pin2net_.end() ? nullptr : &c.nets[found->second];
}
std::string Engine::other_pin(const std::string& ref, const std::string& number) {
    auto numbers = lib.pin_numbers(part(ref).lib_id);
    numbers.erase(number);
    if (numbers.size() != 1) throw SchematicPlaceError(ref + " is not a 2-pin part");
    return *numbers.begin();
}
std::string Engine::_pin_of_net(const std::string& ref, const std::string& name) {
    for (const auto& number : lib.pin_numbers(part(ref).lib_id)) {
        const auto* n = net_of(ref, number);
        if (n && n->name == name) return number;
    }
    throw SchematicPlaceError(ref + ": no pin on net " + py_quote(name));
}
std::string Engine::_power_lib(const std::string& name) const {
    static const std::map<std::string, std::string> known{
        {"+3V3", "power:+3V3"}, {"+5V", "power:+5V"}, {"+1V8", "power:+1V8"},
        {"GND", "power:GND"}, {"VBUS", "power:VBUS"}, {"CHASSIS_GND", "schgen:CHASSIS_GND"}};
    if (const auto found = known.find(name); found != known.end()) return found->second;
    // Every remaining entry in Python POWER_LIBS is exactly schgen:<+rail>.
    if (!name.empty() && name.front() == '+') return "schgen:" + name;
    throw SchematicPlaceError("no power symbol mapped for rail " + py_quote(name));
}
Point Engine::_dodge_value_off_nc(const std::string& text, Point value, double ax, double ay) const {
    return dodge_value_off_nc(text, value.first, value.second, ax, ay,
                               U, CHAR_W, LINE_H, TEXT_SIZE, _nc_boxes(), 0.2);
}
std::size_t Engine::power(const std::string& name, double x, double y, int rotation, bool show_value) {
    ++_pwr;
    const auto id = _power_lib(name);
    const auto& symbol = lib.get(id);
    const auto ref = numbered("#PWR", _pwr);
    auto value = value_anchor(symbol, x, y, rotation);
    if (show_value) value = _dodge_value_off_nc(name, value, x, y);
    pl.powers.push_back({id, name, ref, x, y, rotation, name,
                        SchematicTextPosition{value.first, value.second, 0}, show_value});
    pl.boxes.push_back(body_box_page(symbol, x, y, rotation, "body", ref));
    if (show_value) pl.boxes.push_back(visual(centered_box(name, value.first, value.second), "value", ref));
    return pl.powers.size() - 1;
}
std::size_t Engine::flag(const std::string& name, double x, double y, int rotation) {
    ++_flg;
    const auto& symbol = lib.get("power:PWR_FLAG");
    const auto ref = numbered("#FLG", _flg);
    pl.powers.push_back({"power:PWR_FLAG", "PWR_FLAG", ref, x, y, rotation, name, std::nullopt, false});
    pl.boxes.push_back(body_box_page(symbol, x, y, rotation, "body", ref));
    return pl.powers.size() - 1;
}
void Engine::passive(const std::string& ref, double x, double y, int rotation, const std::string& side) {
    const auto& p = part(ref);
    const auto& symbol = lib.get(p.lib_id);
    const auto body = body_box_page(symbol, x, y, rotation, "body", ref);
    const double rw = text_wh(ref).first, vw = text_wh(p.value).first;
    const double rx = side == "right" ? body.x1 + 0.42 + rw / 2 : body.x0 - 0.42 - rw / 2;
    const double vx = side == "right" ? body.x1 + 0.42 + vw / 2 : body.x0 - 0.42 - vw / 2;
    const int ta = (rotation % 180 + 180) % 180 == 90 ? 90 : 0;
    const SchematicTextPosition rp{rx, y - 1.27, ta}, vp{vx, y + 1.27, ta};
    pl.parts.push_back({ref, p.lib_id, p.value, x, y, rotation, p.footprint, rp, vp});
    pl.boxes.push_back(body);
    pl.boxes.push_back(visual(centered_box(ref, rp.x, rp.y), "reference", ref));
    pl.boxes.push_back(visual(centered_box(p.value, vp.x, vp.y), "value", ref));
    _done.insert(ref);
}
void Engine::label(const std::string& name, double x, double y, int rotation, const std::string& shape) {
    x = py_round(x, 3); y = py_round(y, 3);
    pl.hlabels.push_back({name, x, y, rotation, shape});
    pl.boxes.push_back(visual(glabel_box(name, x, y, rotation), "label", "label:" + name));
}
void Engine::llabel(const std::string& name, double x, double y, int rotation) {
    x = py_round(x, 3); y = py_round(y, 3);
    pl.llabels.push_back({name, x, y, rotation});
    pl.boxes.push_back(visual(llabel_box(name, x, y, rotation), "label", "label:" + name));
}
std::vector<Box4> Engine::_boxes() const {
    std::vector<Box4> boxes;
    for (const auto& b : pl.boxes) boxes.push_back(b.bounds());
    return boxes;
}
std::vector<Box4> Engine::_plan_seg_boxes() const {
    std::vector<Box4> boxes;
    for (const auto& entry : pl.plans) for (const auto& path : entry.second) {
        for (std::size_t i = 1; i < path.size(); ++i) {
            const auto& a = path[i - 1]; const auto& b = path[i];
            boxes.push_back({std::min(a.first, b.first) - 0.127, std::min(a.second, b.second) - 0.127,
                             std::max(a.first, b.first) + 0.127, std::max(a.second, b.second) + 0.127});
        }
    }
    return boxes;
}
std::vector<Box4> Engine::_nc_boxes() const {
    std::vector<Box4> boxes;
    constexpr double half = NC_MARKER / 2;
    for (const auto& p : pl.no_connects) boxes.push_back({p.x - half, p.y - half, p.x + half, p.y + half});
    return boxes;
}
bool Engine::_spot_free(const Box4& b, double pad) const {
    return spot_free(b, pad, _boxes(), _plan_seg_boxes(), _nc_boxes());
}
Box4 Engine::_extent() const {
    std::vector<Point> points;
    for (const auto& entry : pl.plans) for (const auto& path : entry.second)
        points.insert(points.end(), path.begin(), path.end());
    return boxes_paths_extent(_boxes(), points);
}
double Engine::_band_edge(double y0, double y1, int side, double default_edge) const {
    return band_edge(y0, y1, side, default_edge, _boxes(), _plan_seg_boxes());
}

void Engine::_classify() {
    multi.clear(); multi_nets.clear(); cluster.clear(); pull.clear(); hang.clear();
    series.clear(); trunks.clear(); shunts.clear(); float_chains.clear();
    for (const auto& p : c.parts) if (lib.pin_numbers(p.lib_id).size() > 2) multi.push_back(p.ref);
    const std::set<std::string> mset(multi.begin(), multi.end());
    for (const auto& n : c.nets) for (const auto& p : n.pins) {
        if (mset.count(p.ref)) { multi_nets.insert(n.name); break; }
    }
    for (const auto& p : c.parts) {
        if (mset.count(p.ref)) continue;
        const auto pins = lib.pin_numbers(p.lib_id);
        if (pins.size() != 2) throw SchematicPlaceError(p.ref + ": " + std::to_string(pins.size())
            + "-pin part is neither a multi-pin part nor a 2-pin passive");
        const auto* n1 = net_of(p.ref, *pins.begin());
        const auto* n2 = net_of(p.ref, *std::next(pins.begin()));
        if (!n1 || !n2) throw SchematicPlaceError(p.ref + ": unnetted passive");
        const auto& a = n1->net_class; const auto& b = n2->net_class;
        if ((a == "power" && b == "ground") || (a == "ground" && b == "power")) {
            cluster[a == "power" ? n1->name : n2->name].push_back(p.ref);
        } else if (a == "power" || b == "power") {
            const auto* sig = b == "power" ? n1 : n2;
            const auto* rail = b == "power" ? n2 : n1;
            pull[sig->name].emplace_back(p.ref, rail->name);
        } else if (a == "ground" || b == "ground") {
            hang[b == "ground" ? n1->name : n2->name].push_back(p.ref);
        } else series.push_back({p.ref, n1->name, n2->name});
    }
    for (const auto& n : c.nets) {
        std::set<std::string> mp;
        for (const auto& p : n.pins) if (mset.count(p.ref)) mp.insert(p.ref);
        bool hinted = false;
        for (const auto& hint : c.hints) if (hint.net == n.name && hint.style == "trunk") hinted = true;
        if ((n.net_class == "signal" && (n.pins.size() >= 4 || hinted || (n.pins.size() >= 3 && mp.size() >= 2)))
            || (n.net_class == "port" && n.pins.size() >= 4 && mp.size() >= 2)) {
            auto trunk = std::make_shared<Trunk>(); trunk->net = n.name;
            trunks[n.name] = std::move(trunk);
        }
    }
    for (const auto& ref : multi) {
        bool has_signal = false, all_passive = true, ground = false, power = false;
        for (const auto& p : lib.get(part(ref).lib_id).pins) {
            const auto* n = net_of(ref, p.number);
            if (!n) continue;
            if (signal(*n)) { has_signal = true; if (p.etype != "passive") all_passive = false; }
            ground |= n->net_class == "ground"; power |= n->net_class == "power";
        }
        const bool clamp = !ref.empty() && ref.front() != 'J' && has_signal && all_passive && ground && !power;
        const std::size_t threshold = clamp ? 1 : 2;
        bool any_net = false, all_shared = true;
        for (const auto& n : c.nets) {
            if (!signal(n)) continue;
            bool owns = false;
            std::set<std::string> others;
            for (const auto& p : n.pins) {
                if (p.ref == ref) owns = true;
                else if (mset.count(p.ref)) others.insert(p.ref);
            }
            if (owns) { any_net = true; if (others.size() < threshold) all_shared = false; }
        }
        if (any_net && all_shared) shunts.push_back(ref);
    }
    _extract_float_chains();
}

void Engine::_extract_float_chains() {
    std::set<std::string> floating;
    for (const auto& n : c.nets)
        if (signal(n) && !multi_nets.count(n.name) && !trunks.contains(n.name)) floating.insert(n.name);
    FloatLegs legs;
    for (const auto& name : floating) legs[name];
    auto kind_of = [&](const std::string& name) -> std::string {
        const auto& cls = net(name).net_class;
        if (cls == "power") return "rail";
        if (cls == "ground") return "gnd";
        if (trunks.contains(name)) return "trunk";
        return floating.count(name) ? "float" : "pin";
    };
    for (const auto& [sig, pulls] : pull) if (floating.count(sig))
        for (const auto& [ref, rail] : pulls) legs.at(sig).push_back({ref, rail, "rail"});
    for (const auto& [sig, hangs] : hang) if (floating.count(sig)) {
        for (const auto& ref : hangs) {
            std::optional<std::string> far;
            for (const auto& number : lib.pin_numbers(part(ref).lib_id)) {
                const auto* n = net_of(ref, number);
                if (n && n->name != sig) { far = n->name; break; }
            }
            if (!far) throw SchematicPlaceError(ref + ": no far net for floating leg " + py_quote(sig));
            legs.at(sig).push_back({ref, *far, "gnd"});
        }
    }
    for (const auto& s : series) {
        if (floating.count(s.a)) legs.at(s.a).push_back({s.ref, s.b, kind_of(s.b)});
        if (floating.count(s.b)) legs.at(s.b).push_back({s.ref, s.a, kind_of(s.a)});
    }
    float_chains.clear();
    std::set<std::string> seen;
    for (const auto& f : floating) {
        if (seen.count(f) || legs.at(f).empty()) continue;
        std::set<std::string> component{f};
        Refs todo{f};
        while (!todo.empty()) {
            const auto cur = todo.back(); todo.pop_back();
            for (const auto& leg : legs.at(cur))
                if (leg.kind == "float" && component.insert(leg.far).second) todo.push_back(leg.far);
        }
        seen.insert(component.begin(), component.end());
        if (component.size() == 1 && net(f).net_class == "port" && legs.at(f).size() == 1
            && legs.at(f).front().kind == "pin") continue;
        float_chains.push_back(_linearise(component, legs));
    }
    std::set<std::string> used;
    for (const auto& chain : float_chains) {
        for (const auto& leg : chain->legs) used.insert(leg.ref);
        for (const auto& entry : chain->hangs) used.insert(entry.second.begin(), entry.second.end());
    }
    Refs empty;
    for (auto& [key, values] : pull) {
        remove_if(values, [&](const auto& v) { return used.count(v.first); });
        if (values.empty()) empty.push_back(key);
    }
    for (const auto& key : empty) pull.erase(key);
    empty.clear();
    for (auto& [key, values] : hang) {
        remove_if(values, [&](const auto& v) { return used.count(v); });
        if (values.empty()) empty.push_back(key);
    }
    for (const auto& key : empty) hang.erase(key);
    remove_if(series, [&](const auto& v) { return used.count(v.ref); });
}

ChainPtr Engine::_linearise(const std::set<std::string>& component, const FloatLegs& legs) {
    std::vector<ChainEnd> ends;
    for (const auto& n : component) for (const auto& leg : legs.at(n))
        if (leg.kind != "float") ends.push_back({leg.ref, n, leg.far, leg.kind});
    std::stable_sort(ends.begin(), ends.end(), [](const auto& a, const auto& b) {
        return priority(a.kind) < priority(b.kind);
    });
    const auto prefix = "floating nets " + component_name(component);
    if (ends.empty()) throw SchematicPlaceError(prefix + ": no rail/pin end");
    const auto top = ends.front();
    std::vector<ChainEnd> bottoms(ends.begin() + 1, ends.end());
    auto cap = [&](const std::string& ref) {
        const auto& id = part(ref).lib_id;
        return id.size() >= 2 && id.compare(id.size() - 2, 2, ":C") == 0;
    };
    std::stable_sort(bottoms.begin(), bottoms.end(), [&](const auto& a, const auto& b) {
        return std::make_pair(a.kind != "gnd", cap(a.ref)) < std::make_pair(b.kind != "gnd", cap(b.ref));
    });
    if (bottoms.empty()) return _linearise_port_strap(component, legs, ends);
    auto chain = std::make_shared<FloatChain>();
    chain->root = top.far;
    chain->legs.push_back({top.ref, top.far, top.net});
    std::set<std::string> used{top.ref};
    auto cur = top.net;
    while (true) {
        const auto& choices = legs.at(cur);
        const auto next = std::find_if(choices.begin(), choices.end(), [&](const auto& leg) {
            return !used.count(leg.ref) && leg.kind == "float";
        });
        if (next != choices.end()) {
            used.insert(next->ref); chain->legs.push_back({next->ref, cur, next->far});
            cur = next->far; continue;
        }
        const auto tail = std::find_if(bottoms.begin(), bottoms.end(), [&](const auto& end) {
            return end.net == cur && !used.count(end.ref);
        });
        if (tail == bottoms.end()) throw SchematicPlaceError(prefix + ": cannot close chain at " + py_quote(cur));
        used.insert(tail->ref); chain->legs.push_back({tail->ref, cur, tail->far});
        break;
    }
    for (const auto& n : component) for (const auto& leg : legs.at(n)) {
        if (used.count(leg.ref)) continue;
        if (leg.kind != "gnd") throw SchematicPlaceError(leg.ref + ": unsupported extra leg on floating net "
                                                         + py_quote(n) + " (" + leg.kind + ")");
        chain->hangs[n].push_back(leg.ref); used.insert(leg.ref);
    }
    if (top.kind != "trunk" && top.kind != "pin" && top.kind != "rail")
        throw SchematicPlaceError(prefix + ": no rail/pin end");
    chain->kind = top.kind;
    if (chain->kind == "trunk") trunks.at(top.far)->chains.push_back(chain);
    return chain;
}

ChainPtr Engine::_linearise_port_strap(const std::set<std::string>& component,
        const FloatLegs& legs, const std::vector<ChainEnd>& ends) {
    const auto prefix = "floating nets " + component_name(component);
    if (ends.size() != 1 || (ends.front().kind != "rail" && ends.front().kind != "gnd"))
        throw SchematicPlaceError(prefix + ": single-ended chain without a rail/GND end");
    const auto& end = ends.front();
    std::set<std::string> used{end.ref};
    auto chain = std::make_shared<FloatChain>();
    chain->kind = "port";
    chain->legs.push_back({end.ref, end.net, end.far});
    auto cur = end.net;
    while (true) {
        const auto& choices = legs.at(cur);
        const auto next = std::find_if(choices.begin(), choices.end(), [&](const auto& leg) {
            return !used.count(leg.ref) && leg.kind == "float";
        });
        if (next == choices.end()) break;
        used.insert(next->ref); chain->legs.push_back({next->ref, next->far, cur});
        cur = next->far;
    }
    chain->root = cur;
    if (net(cur).net_class != "port") throw SchematicPlaceError(prefix + ": single-ended chain tops out on non-PORT net "
        + py_quote(cur) + " — dangling internal net");
    for (const auto& n : component) for (const auto& leg : legs.at(n)) {
        if (used.count(leg.ref)) continue;
        if (leg.kind != "gnd") throw SchematicPlaceError(leg.ref + ": unsupported extra leg on floating net "
                                                         + py_quote(n) + " (" + leg.kind + ")");
        chain->hangs[n].push_back(leg.ref); used.insert(leg.ref);
    }
    std::reverse(chain->legs.begin(), chain->legs.end());
    return chain;
}

}  // namespace schematic_place
}  // namespace schgen
