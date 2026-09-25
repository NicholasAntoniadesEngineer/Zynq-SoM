#include "floorplan_internal.hpp"

#include <algorithm>
#include <charconv>
#include <cmath>

namespace schgen {
namespace {
constexpr double guard_mm = 4.0;
constexpr int repair_max = 16, median_passes = 8, channel_min_nets = 6;
constexpr double channel_floor = 2.0, channel_per_net = .2;
constexpr double hop_weight = 1.0, seed_weight = .05;

void finite(double value, const std::string& where) {
    if (!std::isfinite(value))
        throw FloorplanError("floorplan compose: non-finite " + where);
}
void point(FloorplanPoint p, const std::string& where) {
    finite(p.first, where); finite(p.second, where);
}
void rectangle(const Box4& r, const std::string& where) {
    point({r.x0, r.y0}, where); point({r.x1, r.y1}, where);
    if (r.x0 > r.x1 || r.y0 > r.y1)
        throw FloorplanError("floorplan compose: inverted rectangle " + where);
}
void validate(const FloorplanLegalizeInput& in) {
    finite(in.board_w, "board width"); finite(in.board_h, "board height");
    finite(in.clear, "clearance"); point(in.origin, "origin");
    if (in.board_w <= 0 || in.board_h <= 0 || in.clear < 0)
        throw FloorplanError("floorplan compose: invalid board dimensions/clearance");
    rectangle(in.som_core_page, "SoM core");
    std::set<std::string> fixed_names;
    for (const auto& [name, r] : in.fixed_rects) {
        if (name.empty() || name.front() == '#' || !fixed_names.insert(name).second)
            throw FloorplanError("floorplan compose: invalid or duplicate fixed name " + name);
        rectangle(r, name);
    }
    for (const auto& [name, r] : in.som_j_rects) rectangle(r, name);
    for (const auto& [name, p] : in.fixed_poses) point(p, name);
    for (const auto& [name, m] : in.metrics) {
        point(m.zone_wh, name);
        std::set<std::string> refs;
        for (const auto& [ref, x, y] : m.offsets) {
            point({x, y}, name + "/" + ref);
            if (!refs.insert(ref).second)
                throw FloorplanError("floorplan compose: duplicate metric offset " + name + "/" + ref);
        }
        for (const auto& [ref, x0, y0, x1, y1] : m.pad_union) {
            rectangle({x0, y0, x1, y1}, name + "/" + ref);
            if (!refs.count(ref))
                throw FloorplanError("floorplan compose: pad union has no offset " + name + "/" + ref);
        }
    }
    const std::set<std::string> kinds{"flow_hop", "near_max", "near_intent", "far_min", "facing"};
    for (const auto* terms : {&in.index.hard, &in.index.soft}) for (const auto& t : *terms) {
        if (!kinds.count(t.kind))
            throw FloorplanError("floorplan compose: unknown term kind " + t.kind);
        if (t.subject.empty() || t.target().empty())
            throw FloorplanError("floorplan compose: empty term endpoint");
        if (t.bound) finite(*t.bound, "term bound");
    }
    for (const auto& [pair, demand] : in.channel_demand) {
        (void)pair;
        if (demand < 0) throw FloorplanError("floorplan compose: negative channel demand");
    }
}

std::vector<FloorplanTermEval> evaluate(const FloorplanLegalizeInput& in,
                                       const FloorplanOffsets& poses) {
    std::vector<const FloorplanTerm*> terms;
    std::vector<EvalTermIn> rows;
    for (const auto* group : {&in.index.hard, &in.index.soft}) for (const auto& t : *group) {
        terms.push_back(&t);
        rows.push_back({t.kind, t.subject, t.target(), t.bound.value_or(0), t.bound.has_value(), t.out_refs});
    }
    std::vector<EvalMetric> metrics;
    for (const auto& [name, m] : in.metrics) metrics.push_back({name, m.offsets, m.pad_union});
    const auto values = evaluate_terms(in.board_w, in.board_h, in.som_core_page,
        {poses.begin(), poses.end()}, metrics, rows, {{"ethernet", 14}, {"power_som", 25}},
        {in.som_j_rects.begin(), in.som_j_rects.end()}, in.origin.first, in.origin.second);
    std::vector<FloorplanTermEval> out;
    for (std::size_t i = 0; i < values.size(); ++i) {
        const auto& e = values[i];
        out.push_back({*terms[i], e.measured, e.bound, e.margin, e.ok, e.note});
    }
    return out;
}

std::string float_text(double value) {
    if (std::isinf(value)) return value < 0 ? "-inf" : "inf";
    char buffer[64];
    const auto r = std::to_chars(buffer, buffer + sizeof(buffer), value);
    if (r.ec != std::errc{}) throw FloorplanError("floorplan compose: cannot format margin");
    std::string s(buffer, r.ptr);
    if (s.find_first_of(".eE") == std::string::npos) s += ".0";
    return s;
}

struct TaggedEdge {
    NamedEdge edge;
    std::string kind;
};

class Composer {
public:
    Composer(const FloorplanLegalizeInput& input,
             const std::vector<FloorplanLegalizeVar>& variables,
             std::vector<std::string>& output_log) : in(input), log(output_log), fixed(input.fixed_poses) {
        for (const auto& v : variables) {
            if (v.name.empty() || v.name.front() == '#' || !by_name.emplace(v.name, &v).second)
                throw FloorplanError("floorplan compose: invalid or duplicate movable name " + v.name);
            for (double x : {v.w, v.h, v.x, v.y}) finite(x, v.name);
            point(v.seed, v.name + " seed");
            if (v.w <= 0 || v.h <= 0)
                throw FloorplanError("floorplan compose: nonpositive movable dimensions " + v.name);
            seed_rect[v.name] = {v.x, v.y, v.x + v.w, v.y + v.h};
        }
        for (const auto& [name, r] : in.fixed_rects) {
            if (by_name.count(name))
                throw FloorplanError("floorplan compose: name is both fixed and movable " + name);
            frect[name] = r;
        }
        for (const auto& [name, r] : in.som_j_rects) fixed[name] = {r.x0, r.y0};
        for (const auto& [name, v] : by_name) {
            names.push_back(name); pos_x.push_back(v->x); pos_y.push_back(v->y);
        }
    }

    bool run(std::vector<FloorplanLegalizeVar>& movable) {
        if (in.index.hard.empty() || movable.empty()) return true;
        std::vector<Box4> seeds, fixed_boxes;
        std::vector<std::string> fixed_names;
        for (const auto& name : names) seeds.push_back(seed_rect.at(name));
        for (const auto& [name, r] : frect) { fixed_names.push_back(name); fixed_boxes.push_back(r); }
        std::vector<std::tuple<std::string, std::string, int>> demand;
        for (const auto& [pair, n] : in.channel_demand) demand.emplace_back(pair.first, pair.second, n);
        std::vector<std::pair<std::string, std::string>> near;
        for (const auto& t : in.index.hard) if (t.kind == "near_max") near.emplace_back(t.subject, t.target());
        for (const auto& s : legalize_build_seps(names, seeds, fixed_names, fixed_boxes, demand, near,
                                                in.clear, channel_min_nets, channel_floor, channel_per_net))
            seps.push_back({s.axis == "x", s.lo, s.hi, s.gap, s.flippable});
        if (!edges_ok(true, pos_x) || !edges_ok(false, pos_y)) {
            if (!repair(true, pos_x) || !repair(false, pos_y)) return false;
            descend(true);
            for (bool x : {true, false}) for (const auto& e : edges(x)) {
                if (violated(e.edge, x ? pos_x : pos_y)) {
                    log.push_back(std::string("REJECT: ") + (x ? "x" : "y") +
                        "-edge unsatisfied after axis solve (" + e.kind + " " + e.edge.src + "|" +
                        e.edge.dst + ") — repair flip landed on an already-solved axis");
                    return false;
                }
            }
        }
        const auto red = reds();
        if (!red.empty()) {
            std::string message = "REJECT: hard red after legalization: ";
            for (std::size_t i = 0; i < std::min<std::size_t>(4, red.size()); ++i) {
                const auto& e = red[i];
                if (i) message += "; ";
                message += e.term.kind + " " + e.term.subject + "->" + e.term.target_raw +
                    " margin " + float_text(e.margin);
            }
            log.push_back(std::move(message)); return false;
        }
        if (in.compact) {
            const auto keep_x = pos_x, keep_y = pos_y;
            descend(false);
            if (!reds().empty() || !edges_ok(true, pos_x) || !edges_ok(false, pos_y)) {
                pos_x = keep_x; pos_y = keep_y;
                log.push_back("compaction REVERTED (would break a hard term or separation)");
            } else log.push_back("compacted (wired hop pulls applied)");
        }
        std::vector<Box4> boxes;
        for (std::size_t i = 0; i < names.size(); ++i) {
            const double x = py_round(pos_x[i], 4), y = py_round(pos_y[i], 4);
            const auto& v = *by_name.at(names[i]);
            boxes.push_back({x, y, x + v.w, y + v.h});
        }
        for (std::size_t i = 0; i < boxes.size(); ++i) {
            std::vector<Box4> others(boxes.begin() + static_cast<std::ptrdiff_t>(i + 1), boxes.end());
            others.insert(others.end(), fixed_boxes.begin(), fixed_boxes.end());
            if (rects_overlap_any({boxes[i]}, others, 1e-6)) {
                log.push_back("REJECT: final rect overlap"); return false;
            }
        }
        for (auto& v : movable) {
            const auto i = static_cast<std::size_t>(std::lower_bound(names.begin(), names.end(), v.name) - names.begin());
            v.x = boxes[i].x0; v.y = boxes[i].y0;
        }
        log.push_back("accept: all hard terms green"); return true;
    }

private:
    const FloorplanLegalizeInput& in;
    std::vector<std::string>& log;
    FloorplanOffsets fixed;
    std::map<std::string, const FloorplanLegalizeVar*> by_name;
    std::map<std::string, Box4> seed_rect, frect;
    std::vector<std::string> names;
    std::vector<double> pos_x, pos_y;
    std::vector<RepairSep> seps;

    std::vector<double> sizes(bool x) const {
        std::vector<double> out;
        for (const auto& n : names) out.push_back(x ? by_name.at(n)->w : by_name.at(n)->h);
        return out;
    }
    std::optional<Box4> hull(const std::string& name) const {
        const auto m = in.metrics.find(name);
        return m == in.metrics.end() ? std::nullopt : pad_union_hull(m->second.pad_union);
    }
    FloorplanPoint fixed_pose(const std::string& name) const {
        const auto p = fixed.find(name);
        if (p == fixed.end()) throw FloorplanError("floorplan compose: missing fixed pose " + name);
        return p->second;
    }
    Box4 seed_or_fixed(const std::string& name, const Box4& h) const {
        const auto s = seed_rect.find(name);
        if (s != seed_rect.end()) return s->second;
        const auto p = fixed_pose(name);
        return {p.first + h.x0, p.second + h.y0, p.first + h.x1, p.second + h.y1};
    }
    std::vector<TaggedEdge> extra(bool x) const {
        std::vector<TaggedEdge> out;
        for (const auto& t : in.index.hard) {
            if (t.kind != "near_max") continue;
            const auto s = t.subject, g = t.target();
            const auto jr = floorplan_detail::starts(g, "som_j") ? in.som_j_rects.find(g) : in.som_j_rects.end();
            const auto hs = hull(s);
            const auto hg = jr == in.som_j_rects.end() ? hull(g) :
                std::optional<Box4>{{0, 0, jr->second.x1 - jr->second.x0, jr->second.y1 - jr->second.y0}};
            const double bound = t.bound.value_or(0) - guard_mm;
            const bool sm = by_name.count(s), gm = by_name.count(g);
            if (!hs || !hg || bound < 0 || (!sm && !gm)) continue;
            const auto sr = seed_or_fixed(s, *hs);
            const auto gr = jr == in.som_j_rects.end() ? seed_or_fixed(g, *hg) : jr->second;
            const auto sp = sm ? std::nullopt : std::optional<FloorplanPoint>{fixed_pose(s)};
            const auto gp = gm ? std::nullopt : std::optional<FloorplanPoint>{fixed_pose(g)};
            for (const auto& e : near_max_edges(s, g, bound, x, *hs, *hg, sr, gr, sm, gm, sp, gp))
                out.push_back({{e.src, e.dst, e.cost}, e.perp ? "near_max-perp" : "near_max"});
        }
        return out;
    }
    std::vector<TaggedEdge> edges(bool x) const {
        std::vector<SepSpec> spec;
        for (const auto& s : seps) spec.push_back({s.axis_x, s.lo, s.hi, s.gap});
        std::vector<TaggedEdge> out;
        for (const auto& e : wall_sep_edges(x, names, sizes(x), x ? in.board_w : in.board_h,
                                           in.clear, spec, {frect.begin(), frect.end()}))
            out.push_back({{e.src, e.dst, e.cost}, e.kind});
        const auto more = extra(x); out.insert(out.end(), more.begin(), more.end());
        return out;
    }
    bool violated(const NamedEdge& e, const std::vector<double>& pos) const {
        auto value = [&](const std::string& name) {
            if (name == "#0") return 0.0;
            const auto n = std::lower_bound(names.begin(), names.end(), name);
            if (n == names.end() || *n != name)
                throw FloorplanError("floorplan compose: unknown constraint endpoint " + name);
            return pos.at(static_cast<std::size_t>(n - names.begin()));
        };
        return value(e.dst) - value(e.src) > e.cost + 1e-9;
    }
    bool edges_ok(bool x, const std::vector<double>& pos) const {
        for (const auto& e : edges(x)) if (violated(e.edge, pos)) return false;
        return true;
    }
    bool repair(bool x, std::vector<double>& pos) {
        std::vector<NamedEdge> additional;
        for (const auto& e : extra(x)) additional.push_back(e.edge);
        auto r = legalize_repair_axis(x, names, sizes(x), x ? in.board_w : in.board_h,
            in.clear, seps, {frect.begin(), frect.end()}, additional, repair_max);
        seps = std::move(r.seps);
        if (!r.ok) {
            log.push_back(std::string("INFEASIBLE ") + (x ? "x" : "y") +
                (r.fail == "exhausted" ? ": REPAIR_MAX exhausted" : ": negative cycle"));
            return false;
        }
        pos = std::move(r.pos);
        for (const auto& [lo, hi, was_x] : r.flips)
            log.push_back("repair: flip " + lo + "|" + hi + " off " + (was_x ? "x" : "y"));
        return true;
    }
    FloorplanPoint cent_off(const std::string& name) const {
        const auto m = in.metrics.find(name);
        if (m != in.metrics.end() && !m->second.offsets.empty())
            return centroid_offset(m->second.offsets, 0, 0);
        const auto v = by_name.find(name);
        return v == by_name.end() ? FloorplanPoint{0, 0} : FloorplanPoint{v->second->w / 2, v->second->h / 2};
    }
    void descend(bool seed_only) {
        std::vector<NamedEdge> ex, ey;
        for (const auto& e : edges(true)) ex.push_back(e.edge);
        for (const auto& e : edges(false)) ey.push_back(e.edge);
        std::vector<double> sx, sy;
        std::vector<std::pair<std::string, FloorplanPoint>> centers;
        for (const auto& n : names) {
            const auto& seed = by_name.at(n)->seed;
            sx.push_back(seed.first); sy.push_back(seed.second); centers.emplace_back(n, cent_off(n));
        }
        for (const auto& [n, r] : frect) { (void)r; centers.emplace_back(n, cent_off(n)); }
        std::vector<std::pair<std::string, std::string>> hops;
        if (!seed_only) for (const auto& t : in.index.hard)
            if (t.kind == "flow_hop") hops.emplace_back(t.subject, t.target());
        const auto& core = in.som_core_page;
        auto result = legalize_descend_passes(names, pos_x, pos_y, sx, sy, ex, ey, hops, centers,
            {fixed.begin(), fixed.end()}, (core.x0 + core.x1) / 2 - in.origin.first,
            (core.y0 + core.y1) / 2 - in.origin.second, true, seed_only, hop_weight, seed_weight, median_passes);
        pos_x = std::move(result.first); pos_y = std::move(result.second);
    }
    std::vector<FloorplanTermEval> reds() const {
        auto poses = fixed;
        for (std::size_t i = 0; i < names.size(); ++i)
            poses[names[i]] = {py_round(pos_x[i], 4), py_round(pos_y[i], 4)};
        auto out = evaluate(in, poses);
        out.erase(std::remove_if(out.begin(), out.end(), [](const auto& e) { return !e.term.enforced || e.ok; }), out.end());
        return out;
    }
};
}  // namespace

std::vector<FloorplanTermEval> floorplan_evaluate_terms(
        const FloorplanLegalizeInput& input, const FloorplanOffsets& poses) {
    validate(input);
    for (const auto& [name, p] : poses) point(p, name);
    return evaluate(input, poses);
}

bool floorplan_legalize_compact(const FloorplanLegalizeInput& input,
        std::vector<FloorplanLegalizeVar>& movable, std::vector<std::string>& log) {
    validate(input);
    return Composer(input, movable, log).run(movable);
}
}  // namespace schgen
