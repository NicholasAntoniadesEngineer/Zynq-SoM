#include "pcb_stage_internal.hpp"
#include "schgen/precision_ops.hpp"
#include "native_audit_quantize_internal.hpp"

namespace schgen::pcb_stage {
const JsonNode &field(const JsonNode &n, const std::string &k) {
    auto p = object_field(n, k);
    if (!p)
        throw PcbZoneInfeasible("contract field missing: " + k);
    return *p;
}
const JsonNode &optional(const JsonNode &n, const std::string &k) {
    static const JsonNode nil;
    if (n.kind == JsonKind::Null)
        return nil;
    auto p = object_field(n, k);
    return p ? *p : nil;
}
std::string text(const JsonNode &n, const std::string &k, const std::string &fallback) {
    const auto &p = optional(n, k);
    return p.kind == JsonKind::String ? p.string_value : fallback;
}
double number(const JsonNode &n, const std::string &k, double fallback) {
    const auto &p = optional(n, k);
    return p.kind == JsonKind::Number ? p.number_value : fallback;
}
std::vector<std::string> strings(const JsonNode &n) {
    if (n.kind == JsonKind::String)
        return {n.string_value};
    std::vector<std::string> v;
    for (const auto &x : n.array_value)
        v.push_back(x.string_value);
    return v;
}
std::vector<std::string> strings(const JsonNode &n, const std::string &k) {
    return strings(optional(n, k));
}
std::vector<Box4> values(const NamedBoxes &n) {
    std::vector<Box4> v;
    for (const auto &[k, b] : n) {
        (void)k;
        v.push_back(b);
    }
    return v;
}
const Box4 &at(const NamedBoxes &n, const std::string &key) {
    auto p = std::find_if(n.begin(), n.end(), [&](const auto &x) { return x.first == key; });
    if (p == n.end())
        throw PcbZoneInfeasible("contract pad missing: " + key);
    return p->second;
}
Box4 pinbox(const NamedBoxes &n, const std::vector<std::string> &pins) {
    std::vector<Box4> boxes;
    for (const auto &[name, b] : n)
        if (pins.empty() || std::find(pins.begin(), pins.end(), name) != pins.end())
            boxes.push_back(b);
    auto hit = boxes_union(boxes);
    if (!hit)
        throw PcbZoneInfeasible("pin box: no pads");
    return *hit;
}
double distance(const NamedBoxes &a, const NamedBoxes &b, const std::vector<std::string> &pins) {
    double d = std::numeric_limits<double>::infinity();
    for (const auto &[name, x] : a)
        if (pins.empty() || std::find(pins.begin(), pins.end(), name) != pins.end())
            for (const auto &[key, y] : b) {
                (void)key;
                d = std::min(d, box_gap(x, y));
            }
    return d;
}
std::optional<FloorplanPoint> direction(const std::string &input) {
    std::string s = input;
    for (auto &ch : s)
        if (ch >= 'a' && ch <= 'z')
            ch = static_cast<char>(ch - 'a' + 'A');
    if (s == "N")
        return {{0, -1}};
    if (s == "S")
        return {{0, 1}};
    if (s == "E")
        return {{1, 0}};
    if (s == "W")
        return {{-1, 0}};
    return {};
}
bool connector_value(const std::string &value) {
    static const std::set<std::string> names{"TYPE-C-31-M-12", "HDMI-019S",    "AFC07-S40FCA-00",
                                             "KH-5224-8P8C-D", "TF-01A",       "SFW15R-1STE1LF",
                                             "ZX-SH1.0-4PWT",  "DS1024-2x6R2", "XT60PW-M"};
    return names.count(value) != 0;
}
bool connector(const PcbCheckFootprint &fp) {
    return connector_value(std::filesystem::path(fp.source).stem().string());
}
namespace {
double connector_rotation_impl(const std::string &value, const std::string &edge,
                               QuantizationCounts* counts) {
    auto d = direction(edge);
    if (!d)
        return 0;
    const auto component = [&](double value) {
        static const std::string name = "stage_direction_component";
        if (counts) checked_quantization_add(*counts, name);
        return stage_direction_component(value);
    };
    bool x = value == "XT60PW-M";
    for (double rot : {0., 90., 180., 270.}) {
        auto v = turn_point(x ? 1 : 0, x ? 0 : 1, rot);
        if (component(v.first) == d->first && component(v.second) == d->second)
            return rot;
    }
    return 0;
}
} // namespace
double connector_rotation(const std::string &value, const std::string &edge) {
    return connector_rotation_impl(value, edge, nullptr);
}
double connector_rotation(const std::string &value, const std::string &edge,
                          QuantizationCounts& counts) {
    return connector_rotation_impl(value, edge, &counts);
}
double connector_rotation(const PcbCheckFootprint &fp, const std::string &edge,
                          QuantizationCounts& counts) {
    return connector_rotation(std::filesystem::path(fp.source).stem().string(), edge, counts);
}
double connector_rotation(const PcbCheckFootprint &fp, const std::string &edge) {
    return connector_rotation(std::filesystem::path(fp.source).stem().string(), edge);
}
double need(int pins) { return pins <= 2 ? .2 : pins <= 8 ? 1.5 : 2.; }
bool passive(const std::string &ref, int pins) {
    return is_cluster_passive(ref, pins, {"RS", "RJ", "RN", "LED"}, {"R", "C", "L"}) ||
           is_testpoint_ref(ref);
}
double normalize(double r) {
    r = std::fmod(r, 360);
    return r < 0 ? r + 360 : r;
}
const NamedBoxes &Engine::pads(const PcbCheckFootprintPtr &fp, double rot) {
    if (!fp)
        throw PcbZoneInfeasible("unresolved stage footprint");
    auto key = std::make_pair(fp.get(), rot);
    auto i = pad_cache.find(key);
    if (i != pad_cache.end())
        return i->second;
    std::vector<std::tuple<std::string, double, double, double, double, double>> rows;
    for (const auto &[name, type, x, y, r, w, h] : fp->pads) {
        (void)type;
        rows.emplace_back(name, x, y, r, w, h);
    }
    NamedBoxes result;
    for (const auto &[name, x0, y0, x1, y1] : pad_boxes_named(rows, rot))
        result.push_back({name, {x0, y0, x1, y1}});
    return pad_cache.emplace(key, std::move(result)).first->second;
}
NamedBoxes Engine::pads(const Part &p) {
    auto result = pads(p.mod, p.rot);
    for (auto &[name, b] : result) {
        (void)name;
        b = offset_rect(b, p.x, p.y);
    }
    return result;
}
Part Engine::part(const std::string &ref, double rot, double x, double y) const {
    auto p = in.footprints.find(ref);
    if (p == in.footprints.end() || !p->second)
        throw PcbZoneInfeasible("unresolvable contract member: " + ref);
    return {ref, p->second, rot, x, y};
}
Box4 Engine::body(const Part &p) const {
    auto b = in.bbox_of.find(p.ref);
    return offset_turned_box(b == in.bbox_of.end() ? footprint_bbox(p.mod->document, 3) : b->second,
                             p.rot, p.x, p.y);
}
std::vector<Box4> Engine::bodies(const Parts &parts) const {
    std::vector<Box4> v;
    for (const auto &p : parts)
        v.push_back(body(p));
    return v;
}
bool Engine::overlap(const Parts &parts) const { return any_boxes_overlap(bodies(parts), clear); }
Box4 Engine::extent(const Parts &parts) const {
    auto x = boxes_union(bodies(parts));
    if (!x)
        throw PcbZoneInfeasible("empty stage extent");
    return *x;
}
FloorplanPoint Engine::row_extent(const Parts &parts) const {
    return schgen::row_extent(bodies(parts), zone_pad);
}
std::string Engine::bref(const std::string &lib) const {
    auto b = in.board_refs.find(lib);
    if (b == in.board_refs.end() ||
        std::find(in.refs.begin(), in.refs.end(), b->second) == in.refs.end() ||
        !in.footprints.count(b->second))
        return {};
    return b->second;
}
Part Engine::beside(const std::string &ref, double rot, Box4 target, const std::string &dir,
                    double gap, std::optional<double> along) {
    auto p = part(ref, rot);
    auto b = body(p);
    auto xy = beside_offset((b.x1 - b.x0) / 2, (b.y1 - b.y0) / 2, target, dir, gap, along);
    p.x = xy.first;
    p.y = xy.second;
    return p;
}
Parts Engine::turn(const Parts &parts, double deg, bool renormalize, bool exact_half, bool account_refit) {
    if (std::abs(normalize(deg)) < 1e-6)
        return parts;
    std::vector<Box4> all;
    for (const auto &p : parts) {
        auto v = values(pads(p));
        all.insert(all.end(), v.begin(), v.end());
    }
    auto [cx, cy] = boxes_span_center(all);
    Parts out;
    for (auto p : parts) {
        auto old = boxes_span_center(values(pads(p.mod, p.rot)));
        auto nr = normalize(p.rot + deg);
        auto next = boxes_span_center(values(pads(p.mod, nr)));
        // Same expression and evaluation order as turn_origin_180(..., 4).
        // Count trial coordinates here, before the facing/airwire acceptance gate.
        FloorplanPoint xy;
        if (exact_half && account_refit) {
            checked_quantization_add(quantization, "refit_pose_precision");
            xy.first = native_refit_pose_precision(2.0 * cx - (old.first + p.x) - next.first);
            checked_quantization_add(quantization, "refit_pose_precision");
            xy.second = native_refit_pose_precision(2.0 * cy - (old.second + p.y) - next.second);
        } else xy = exact_half
            ? turn_origin_180(cx, cy, old.first + p.x, old.second + p.y, next.first, next.second, 4)
            : rotate_origin(cx, cy, old.first + p.x, old.second + p.y, next.first, next.second, deg, 4);
        p.rot = nr;
        p.x = xy.first;
        p.y = xy.second;
        out.push_back(p);
    }
    if (renormalize) {
        all.clear();
        for (const auto &p : out) {
            auto v = values(pads(p));
            all.insert(all.end(), v.begin(), v.end());
        }
        auto b = boxes_union(all);
        out = shifted(out, zone_pad - b->x0, zone_pad - b->y0);
    }
    return out;
}
Parts Engine::face(const Parts &parts, const std::set<std::string> &refs, bool media) {
    auto d = direction(in.facing);
    if (!d)
        return parts;
    auto dot = [&](const Parts &ps) {
        std::vector<FloorplanPoint> all, own;
        for (const auto &p : ps) {
            auto c = boxes_span_center(values(pads(p)));
            all.push_back(c);
            if (refs.count(p.ref))
                own.push_back(c);
        }
        if (own.empty())
            return 0.;
        auto a = points_centroid(all), b = points_centroid(own);
        return facing_align_dot(a.first, a.second, b.first, b.second, d->first, d->second);
    };
    Parts best = parts;
    double score = dot(parts);
    if (!media && score > 0)
        return parts;
    for (double deg : media ? std::vector<double>{90, 180, 270} : std::vector<double>{180}) {
        auto next = turn(parts, deg, true, !media);
        auto s = dot(next);
        if (s > score + (media ? 1e-6 : 0)) {
            score = s;
            best = std::move(next);
        }
    }
    return best;
}
std::set<std::string> Engine::output_refs() const {
    auto roles = strings(optional(in.contract, "external"), "output_roles");
    if (optional(optional(in.contract, "external"), "output_roles").kind == JsonKind::Null)
        roles = {"cout_bulk"};
    std::set<std::string> out;
    for (const auto &[ref, v] : optional(in.contract, "roles").object_value)
        if (std::find(roles.begin(), roles.end(), v.string_value) != roles.end()) {
            auto b = bref(ref);
            if (!b.empty())
                out.insert(b);
        }
    return out;
}
std::pair<ShelfPacked, ShelfPacked> Engine::leftover(const std::vector<std::string> &refs,
                                                     double width) const {
    std::vector<ShelfItem> top, bottom;
    for (const auto &r : refs) {
        auto side = in.side_of.find(r);
        auto b = in.bbox_of.at(r);
        ShelfItem s{r, grow_rect(b, in.place_clear / 2), 0, false};
        (side != in.side_of.end() && side->second == "bottom" ? bottom : top).push_back(s);
    }
    auto t = shelf_pack(top, width, {}, zone_pad);
    std::vector<ShelfOcc> blockers;
    for (const auto &[r, x, y] : t.placed)
        if (has_thru_pads_from_text(in.footprints.at(r)->bytes))
            blockers.push_back(
                {grow_rect(offset_rect(in.bbox_of.at(r), x, y), clear / 2), 0, false});
    return {t, shelf_pack(bottom, width, blockers, zone_pad)};
}
} // namespace schgen::pcb_stage

namespace schgen {
std::set<std::string> pcb_contract_members(const PcbStageInput &in) {
    using namespace pcb_stage;
    std::set<std::string> libs, out;
    for (const auto &[lib, v] : optional(in.contract, "roles").object_value) {
        (void)v;
        libs.insert(lib);
    }
    for (const auto &s : optional(in.contract, "structures").array_value) {
        for (auto key : {"members", "caps", "cap", "resistor", "inductor", "cin", "cout"})
            for (const auto &r : strings(s, key))
                libs.insert(r);
    }
    for (const auto &lib : libs) {
        auto b = in.board_refs.find(lib);
        if (b != in.board_refs.end() && in.footprints.count(b->second))
            out.insert(b->second);
    }
    return out;
}
PcbStageResult build_pcb_stage_zone(const PcbStageInput &in) {
    using namespace pcb_stage;
    if (in.contract.kind != JsonKind::Object)
        throw PcbZoneInfeasible(in.sheet + ": build_zone called without a contract");
    if (!std::isfinite(in.place_clear) || in.place_clear <= 0)
        throw PcbZoneInfeasible("stage clearance must be positive and finite");
    for (const auto &[ref, b] : in.bbox_of)
        if (!std::isfinite(b.x0) || !std::isfinite(b.y0) || !std::isfinite(b.x1) ||
            !std::isfinite(b.y1) || b.x1 < b.x0 || b.y1 < b.y0)
            throw PcbZoneInfeasible("invalid stage bounds: " + ref);
    Engine e(in);
    bool hot = false, prox = false;
    for (const auto &s : optional(in.contract, "structures").array_value) {
        hot |= text(s, "type") == "hot_loop";
        prox |= text(s, "type") == "proximity";
    }
    if (!hot && !prox)
        throw PcbZoneInfeasible(in.sheet + ": contract has no hot_loop/proximity structure");
    auto result = hot ? e.hot_zone() : e.proximity_zone();
    result.fallback_events = std::move(e.events);
    result.quantization_engagements = std::move(e.quantization);
    return result;
}
} // namespace schgen
