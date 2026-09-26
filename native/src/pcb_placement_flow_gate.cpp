#include "pcb_placement_gates_internal.hpp"

namespace schgen::placement_gates {
FinalGeometry::FinalGeometry(const PcbCheckInput &in) : input(in) {
    std::map<std::string, std::tuple<double, double, double>> sums;
    for (std::size_t k = 0; k < in.model().insts.size(); ++k) {
        const auto &i = in.model().insts[k];
        auto &[x, y, n] = sums[i.sheet];
        x += i.x;
        y += i.y;
        n += 1.;
        if (!i.mod)
            continue;
        for (const auto &[name, b] : in.geometry_at(k).pad_boxes) {
            (void)name;
            auto [p, fresh] = bboxes.emplace(i.sheet, b);
            if (!fresh)
                p->second = united(p->second, b);
        }
    }
    for (const auto &[s, v] : sums) {
        const auto &[x, y, n] = v;
        if (n > 0)
            centroids[s] = {py_round(x / n, 4), py_round(y / n, 4)};
    }
    for (auto &[s, b] : bboxes) {
        (void)s;
        b = round_box(b, 4);
    }
}
std::optional<Point> FinalGeometry::centroid(const std::string &name) const {
    if (name == "@som") {
        if (!input.model().som_core)
            return {};
        const auto b = *input.model().som_core;
        return Point{py_round((b.x0 + b.x1) / 2, 4), py_round((b.y0 + b.y1) / 2, 4)};
    }
    auto p = centroids.find(name);
    return p == centroids.end() ? std::nullopt : std::optional<Point>(p->second);
}
std::optional<Box4> FinalGeometry::bbox(const std::string &name) const {
    if (name == "@som")
        return input.model().som_core;
    auto p = bboxes.find(name);
    return p == bboxes.end() ? std::nullopt : std::optional<Box4>(p->second);
}
std::optional<Point> FinalGeometry::members(const std::string &sheet,
                                            const std::set<std::string> &refs) const {
    std::vector<Point> points;
    for (const auto &i : input.model().insts)
        if (i.sheet == sheet && refs.count(i.ref))
            points.emplace_back(i.x, i.y);
    return points.empty() ? std::nullopt : std::optional<Point>(rounded_centroid(points, 4));
}
} // namespace schgen::placement_gates

namespace schgen {
using namespace placement_gates;
PcbPlacementFlowResult check_pcb_placement_flow(const PcbCheckInput &in,
                                                const PcbPlacementGatePolicy &policy,
                                                const std::map<std::string, JsonNode> *selected) {
    PcbPlacementFlowResult res;
    const auto &model = in.model();
    FinalGeometry geom(in);
    res.board_area = std::max(model.board_w * model.board_h, 1.);
    const double budget = flow_budget(model.board_w, model.board_h, model.som_core);
    res.flow_budget_mm = py_round(budget, 4);
    const double inf = std::numeric_limits<double>::infinity();
    std::map<std::string, JsonNode> implicit;
    if (!selected) {
        std::set<std::string> placed;
        for (const auto &i : model.insts)
            placed.insert(i.sheet);
        for (const auto &s : placed)
            if (policy.wired_sheets.count(s)) {
                auto c = policy.contracts.find(s);
                if (c != policy.contracts.end())
                    implicit.emplace(*c);
            }
        selected = &implicit;
    }
    auto foreign = [&](const std::vector<std::string> &names) {
        std::vector<std::string> out;
        for (const auto &n : names)
            if (n != "@som" && !policy.project_zones.count(root(n)))
                out.push_back(n);
        return out;
    };
    auto add = [&](const std::string &s) { res.violations.push_back(s); };
    for (const auto &[sheet, c] : *selected) {
        const auto &ext = opt(c, "external");
        if (!truth(ext))
            continue;
        ++res.n_contracts;
        auto chain = strings(opt(ext, "flow"));
        for (std::size_t k = 1; k < chain.size(); ++k) {
            const auto &a = chain[k - 1];
            const auto &b = chain[k];
            auto gone = foreign({a, b});
            if (!gone.empty()) {
                res.na.push_back("flow " + a + "->" + b + ": n/a — " + join(gone, "/") +
                                 " not a subsystem of this project");
                continue;
            }
            ++res.flow_checked;
            auto ca = geom.centroid(a), cb = geom.centroid(b);
            if (!ca || !cb) {
                std::vector<std::string> names;
                if (!ca)
                    names.push_back(a);
                if (!cb)
                    names.push_back(b);
                unique_add(res.unresolved,
                           sheet + ": flow zone " + join(names, "/") + " not placed");
                ++res.flow_fail;
                add("flow " + a + "->" + b + ": zone(s) not placed [" + str(c, "contract", "?") +
                    "]");
                res.terms.push_back({"flow", a, b, inf, py_round(budget, 4), false, ""});
                continue;
            }
            auto d = hypot_xy(ca->first, ca->second, cb->first, cb->second);
            res.detail.push_back("flow " + a + "->" + b + ": " + f(d, 2) + "mm / " + f(budget, 1) +
                                 "mm budget");
            res.terms.push_back({"flow", a, b, d, py_round(budget, 4), d <= budget, ""});
            if (d > budget) {
                ++res.flow_fail;
                add("flow " + a + "->" + b + ": " + f(d, 2) + "mm > " + f(budget, 1) +
                    "mm budget (FLOW_K=0.35 free + SoM detour)");
            }
        }
        auto downstream = str(ext, "downstream");
        auto role_list = strings(opt(ext, "output_roles"));
        std::set<std::string> roles(role_list.begin(), role_list.end());
        if (!downstream.empty() && !roles.empty()) {
            if (!foreign({downstream}).empty())
                res.na.push_back("facing " + sheet + "->" + downstream + ": n/a — " +
                                 repr(downstream) + " not a subsystem of this project");
            else {
                ++res.facing_checked;
                std::vector<std::string> libs;
                for (const auto &[r, v] : opt(c, "roles").object_value)
                    if (roles.count(jstr(v)))
                        libs.push_back(r);
                if (libs.empty()) {
                    auto rs = list_repr(std::vector<std::string>(roles.begin(), roles.end()));
                    unique_add(res.unresolved,
                               sheet + ": facing output_roles " + rs + " match no role");
                    ++res.facing_fail;
                    add("facing " + sheet + ": no output-role parts declared for " + rs + " [" +
                        str(c, "contract", "?") + "]");
                    res.terms.push_back(
                        {"facing", sheet, downstream, inf, 90, false, str(c, "contract", "?")});
                } else {
                    std::set<std::string> brefs;
                    const auto &map = refs(policy, sheet);
                    for (const auto &r : libs) {
                        auto p = map.find(r);
                        if (p != map.end())
                            brefs.insert(p->second);
                    }
                    auto a = geom.centroid(sheet), b = geom.centroid(downstream),
                         o = geom.members(sheet, brefs);
                    if (!a || !b || !o) {
                        std::vector<std::string> missing;
                        if (!a)
                            missing.push_back(sheet);
                        if (!b)
                            missing.push_back(downstream);
                        if (!o)
                            missing.push_back(sheet + ".output_parts");
                        unique_add(res.unresolved,
                                   sheet + ": facing needs placed " + list_repr(missing));
                        ++res.facing_fail;
                        add("facing " + sheet + "->" + downstream + ": UNRESOLVED (not placed: " +
                            list_repr(missing) + ") [" + str(c, "contract", "?") + "]");
                        res.terms.push_back(
                            {"facing", sheet, downstream, inf, 90, false, str(c, "contract", "?")});
                    } else {
                        auto [dot, angle] = facing_dot(a->first, a->second, o->first, o->second,
                                                       b->first, b->second);
                        res.detail.push_back("facing " + sheet + "->" + downstream +
                                             ": dot=" + sign(dot, 2) + " angle=" + f(angle, 1) +
                                             "deg (output@" + point_repr(*o) + " zone@" +
                                             point_repr(*a) + " down@" + point_repr(*b) + ")");
                        res.terms.push_back({"facing", sheet, downstream, angle, 90, dot > 0,
                                             str(c, "contract", "?")});
                        if (dot <= 0) {
                            ++res.facing_fail;
                            add("facing " + sheet + "->" + downstream +
                                ": output parts face AWAY (dot=" + sign(dot, 2) + " <= 0, angle=" +
                                f(angle, 1) + "deg) [" + str(c, "contract", "?") + "]");
                        }
                    }
                }
            }
        }
        for (const auto &far : array(opt(ext, "far"))) {
            auto what = str(far, "what", "?"), basis = str(far, "basis"), zone = root(what);
            auto mm = num(far, "min_mm");
            if (!foreign({zone}).empty()) {
                res.na.push_back("far " + sheet + " vs " + what + ": n/a — " + repr(zone) +
                                 " not a subsystem of this project");
                continue;
            }
            ++res.far_checked;
            // Original far checks zone centroids only; unlike flow/near, @som
            // is not resolved to the SoM rectangle here.
            auto a = geom.centroids.find(sheet), b = geom.centroids.find(zone);
            if (a == geom.centroids.end() || b == geom.centroids.end()) {
                unique_add(res.unresolved, sheet + ": far target " + repr(what) + " (zone " +
                                               repr(zone) + ") not placed");
                ++res.far_fail;
                add("far " + sheet + " vs " + what + ": UNRESOLVED (zone " + repr(zone) +
                    " not placed) [" + basis + "]");
                res.terms.push_back({"far", sheet, what, inf, mm, false, basis});
                continue;
            }
            auto d = hypot_xy(a->second.first, a->second.second, b->second.first, b->second.second);
            res.detail.push_back("far " + sheet + " vs " + what + ": " + f(d, 2) +
                                 "mm / >= " + g(mm) + "mm");
            res.terms.push_back({"far", sheet, what, d, mm, d >= mm, basis});
            if (d < mm) {
                ++res.far_fail;
                add("far " + sheet + " vs " + what + ": " + f(d, 2) + "mm < " + g(mm) + "mm [" +
                    basis + "]");
            }
        }
        for (const auto &near : array(opt(ext, "near_max"))) {
            auto other = str(near, "other", "?"), basis = str(near, "basis");
            auto mm = num(near, "max_mm");
            if (!foreign({other}).empty()) {
                res.na.push_back("near_max " + sheet + " to " + other + ": n/a — " + repr(other) +
                                 " not a subsystem of this project");
                continue;
            }
            ++res.near_max_checked;
            auto a = geom.bboxes.find(sheet);
            auto b = geom.bbox(other);
            if (a == geom.bboxes.end() || !b) {
                unique_add(res.unresolved,
                           sheet + ": near_max target " + repr(other) + " not placed");
                ++res.near_max_fail;
                add("near_max " + sheet + " to " + other + ": UNRESOLVED (" + repr(other) +
                    " not placed) [" + basis + "]");
                res.terms.push_back({"near_max", sheet, other, inf, mm, false, basis});
                continue;
            }
            auto d = box_gap(a->second, *b);
            res.detail.push_back("near_max " + sheet + " to " + other + ": " + f(d, 2) +
                                 "mm gap / <= " + g(mm) + "mm");
            res.terms.push_back({"near_max", sheet, other, d, mm, d <= mm, basis});
            if (d > mm) {
                ++res.near_max_fail;
                add("near_max " + sheet + " to " + other + ": " + f(d, 2) + "mm gap > " + g(mm) +
                    "mm [" + basis + "]");
            }
        }
    }
    res.ok = res.violations.empty() && res.unresolved.empty();
    return res;
}
std::string PcbPlacementFlowResult::summary() const {
    std::vector<std::string> lines{
        "PLACEMENT-FLOW GATE: " + verdict(ok) + " (" + std::to_string(n_contracts) +
            " external contract(s); board_area=" + f(board_area, 0) +
            "mm^2, flow_budget=" + f(flow_budget_mm, 1) + "mm)",
        "  fails: flow=" + std::to_string(flow_fail) + "/" + std::to_string(flow_checked) +
            " facing=" + std::to_string(facing_fail) + "/" + std::to_string(facing_checked) +
            " far=" + std::to_string(far_fail) + "/" + std::to_string(far_checked) +
            " near_max=" + std::to_string(near_max_fail) + "/" + std::to_string(near_max_checked)};
    auto append = [&](const std::string &heading, std::vector<std::string> values,
                      const std::string &prefix = "") {
        lines.push_back("  " + heading + ": " + std::to_string(values.size()));
        std::sort(values.begin(), values.end());
        for (const auto &v : values)
            lines.push_back("    " + prefix + v);
    };
    append("unresolved", unresolved, "UNRESOLVED ");
    if (!na.empty())
        append("n/a (subsystem not in this project)", na);
    append("violations", violations);
    append("detail", detail);
    return join(lines);
}
} // namespace schgen
