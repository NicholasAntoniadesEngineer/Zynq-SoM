#include "schgen/diagram.hpp"
#include "gallery_diagram_internal.hpp"
#include "schgen/occupancy.hpp"
#include <array>
#include <numeric>
#include <set>
#include <tuple>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace schgen {
namespace {
using namespace document_detail;
using Items = std::vector<std::pair<std::string, std::string>>;
struct Style {
    std::string colour;
    double width;
    std::string label;
};
const std::map<std::string, Style> styles{
    {"power", {"#b45309", 2.6, "power rail"}},    {"diff_pair", {"#7c3aed", 2.0, "diff pair"}},
    {"tmds_pair", {"#db2777", 2.0, "TMDS pair"}}, {"usb_hs_pair", {"#0891b2", 2.0, "USB HS pair"}},
    {"i2c", {"#16a34a", 1.7, "I2C bus"}},         {"sd_bus", {"#ca8a04", 1.9, "SD bus"}},
    {"single", {"#2563eb", 1.4, "signal"}}};
struct Cluster {
    std::string name, title, fill, stroke;
};
const std::array<Cluster, 6> clusters{{{"power", "Power & bring-up", "#fff7ed", "#fdba74"},
                                       {"som", "SoM connectors", "#fffbeb", "#fcd34d"},
                                       {"video", "Video / display", "#faf5ff", "#d8b4fe"},
                                       {"storage", "Storage & USB", "#ecfeff", "#67e8f9"},
                                       {"net", "Networking", "#f0fdf4", "#86efac"},
                                       {"io", "FMC / user IO", "#eff6ff", "#93c5fd"}}};
const std::map<std::string, std::pair<int, int>> roles{{"pd_input", {0, 0}},
                                                       {"power", {0, 0}},
                                                       {"power_mon", {0, 0}},
                                                       {"bringup_rails", {0, 0}},
                                                       {"bringup_en", {0, 0}},
                                                       {"bringup_en_modules", {0, 0}},
                                                       {"bringup_modules", {0, 0}},
                                                       {"som_j1", {1, 1}},
                                                       {"som_j2", {1, 1}},
                                                       {"som_j3", {1, 1}},
                                                       {"hdmi_tx", {2, 2}},
                                                       {"hdmi_rx", {2, 2}},
                                                       {"lcd", {2, 2}},
                                                       {"camera", {2, 2}},
                                                       {"microsd", {3, 2}},
                                                       {"usbc_otg", {3, 2}},
                                                       {"usb_pd", {3, 2}},
                                                       {"uart_bridge", {3, 2}},
                                                       {"ethernet", {4, 2}},
                                                       {"fmc", {5, 2}},
                                                       {"pmod", {5, 2}},
                                                       {"user_io", {5, 2}},
                                                       {"debug_boot", {5, 2}},
                                                       {"hdmi_rx_term", {2, 3}},
                                                       {"rj45_connector", {4, 3}},
                                                       {"usb_uart_connector", {3, 3}}};
const std::string spine("\0SoM", 4), later("\0LATER", 6);
constexpr double box_w = 172, box_h = 56, col_gap = 128, row_gap = 36, col0 = 150, top = 120,
                 som_w = 168, pad = 15;
std::string net_word(std::size_t n) { return n == 1 ? "net" : "nets"; }
std::pair<std::string, std::string> edge_label(const Items &items) {
    std::map<std::string, std::size_t> counts;
    for (const auto &item : items)
        ++counts[item.second];
    std::vector<std::pair<std::string, std::size_t>> ranked(counts.begin(), counts.end());
    std::sort(ranked.begin(), ranked.end(), [](const auto &a, const auto &b) {
        return a.second == b.second ? a.first < b.first : a.second > b.second;
    });
    std::string kind = "single";
    for (const auto &kv : ranked)
        if (kv.first != "single") {
            kind = kv.first;
            break;
        }
    return {std::to_string(items.size()) + " " + net_word(items.size()) + " · " +
                styles.at(kind).label,
            kind};
}
std::vector<std::string> words(const std::string &text) {
    std::vector<std::string> out;
    std::string word;
    std::size_t offset = 0;
    for (const auto cp : codepoints(text)) {
        const std::size_t n = cp < 0x80 ? 1 : cp < 0x800 ? 2 : cp < 0x10000 ? 3 : 4;
        if (space(cp)) {
            if (!word.empty()) {
                out.push_back(word);
                word.clear();
            }
        } else
            word += text.substr(offset, n);
        offset += n;
    }
    if (!word.empty())
        out.push_back(word);
    return out;
}
void legend(std::vector<std::string> &e, const std::string &width) {
    std::vector<Style> items;
    for (const auto *key :
         {"power", "diff_pair", "tmds_pair", "usb_hs_pair", "sd_bus", "i2c", "single"})
        items.push_back(styles.at(key));
    items.push_back({"#1d4ed8", 2.0, "SoM contract"});
    items.push_back({"#9ca3af", 1.4, "deferred"});
    const int lx = std::stoi(width) - 522 - 26, ly = 18;
    e.push_back("<rect x=\"" + std::to_string(lx) +
                "\" y=\"18\" width=\"522\" height=\"89\" rx=\"8\" fill=\"#f8fafc\" "
                "stroke=\"#cbd5e1\" stroke-width=\"1\"/>");
    e.push_back("<text x=\"" + std::to_string(lx + 12) +
                "\" y=\"35\" font-size=\"13\" font-weight=\"700\" fill=\"#334155\">legend</text>");
    for (std::size_t i = 0; i < items.size(); ++i) {
        const auto &it = items[i];
        const int ix = lx + 12 + static_cast<int>(i % 3) * 168,
                  iy = ly + 36 + static_cast<int>(i / 3) * 21;
        const auto dash = it.label == "deferred" ? " stroke-dasharray=\"5,4\"" : "";
        e.push_back("<line x1=\"" + std::to_string(ix) + "\" y1=\"" + std::to_string(iy - 4) +
                    "\" x2=\"" + std::to_string(ix + 28) + "\" y2=\"" + std::to_string(iy - 4) +
                    "\" stroke=\"" + it.colour + "\" stroke-width=\"" + pyfloat(it.width + 0.4) +
                    "\"" + dash + "/>");
        e.push_back("<text x=\"" + std::to_string(ix + 34) + "\" y=\"" + std::to_string(iy) +
                    "\" font-size=\"12.5\" fill=\"#475569\">" + xml(it.label) + "</text>");
    }
}
struct Column {
    std::vector<std::string> members;
    bool spine = false;
};
struct ClusterRect {
    int cluster;
    double x, y, w, h;
};
struct Edge {
    std::string left, right;
    Items items;
    std::string colour;
    double width;
    std::string role, dash;
    bool right_spine = false, left_spine = false;
};
struct Label {
    double x, y;
    std::string text, colour, anchor;
    double lo, hi;
};
} // namespace

std::string render_block_diagram(const LinkResult &link, const LinkSomNets &som_nets) {
    std::vector<std::string> sheets;
    for (const auto &sheet : link.sheets) {
        (void)codepoints(sheet.name);
        sheets.push_back(sheet.name);
    }
    std::sort(sheets.begin(), sheets.end());
    std::map<std::string, Items> som_bound;
    std::map<std::string, std::vector<std::string>> deferred;
    std::map<std::pair<std::string, std::string>, Items> peer;
    auto bindings = link.bindings;
    std::stable_sort(bindings.begin(), bindings.end(), [](const auto &a, const auto &b) {
        return std::tie(a.sheet, a.net) < std::tie(b.sheet, b.net);
    });
    for (const auto &b : bindings) {
        if (b.status == "deferred") {
            deferred[b.sheet].push_back(b.net);
            continue;
        }
        for (const auto &t : b.targets) {
            if (t.compare(0, 4, "SoM ") == 0)
                som_bound[b.sheet].emplace_back(b.net, b.ptype.kind);
            else if (t.compare(0, 6, "sheet ") == 0) {
                const auto tokens = words(t);
                if (tokens.size() < 2)
                    throw ProjectError("diagram: malformed sheet target");
                const auto pk = tokens[1].substr(0, tokens[1].find(':'));
                auto a = b.sheet, c = pk;
                if (c < a)
                    std::swap(a, c);
                peer[{a, c}].emplace_back(b.net, b.ptype.kind);
            }
        }
    }
    for (auto &[key, items] : peer) {
        (void)key;
        std::sort(items.begin(), items.end());
        items.erase(std::unique(items.begin(), items.end()), items.end());
    }
    std::set<std::string> rails;
    for (const auto &r : link.rail_bindings)
        if (r.find("SoM") != r.npos)
            rails.insert(r.substr(0, r.find(' ')));
    std::map<std::string, int> degree;
    for (const auto &[key, v] : peer) {
        (void)v;
        ++degree[key.first];
        ++degree[key.second];
    }
    for (const auto &[s, v] : som_bound) {
        (void)v;
        ++degree[s];
    }
    for (const auto &[s, v] : deferred) {
        (void)v;
        ++degree[s];
    }
    std::vector<std::string> isolated, laid;
    std::map<std::string, int> cluster_of, layer_of;
    std::set<int> layers;
    for (const auto &s : sheets) {
        const auto r = roles.find(s);
        const auto role = r == roles.end() ? std::pair<int, int>{5, 2} : r->second;
        cluster_of[s] = role.first;
        layer_of[s] = role.second;
        if (!degree[s])
            isolated.push_back(s);
        else {
            laid.push_back(s);
            layers.insert(role.second);
        }
    }
    std::vector<Column> columns;
    int spine_col = -1;
    for (int lv : layers) {
        std::array<std::vector<std::string>, 6> by_cluster;
        for (const auto &s : laid)
            if (layer_of.at(s) == lv)
                by_cluster[cluster_of.at(s)].push_back(s);
        std::vector<std::string> cur;
        for (const auto &run : by_cluster) {
            if (run.empty())
                continue;
            if (run.size() > 12) {
                if (!cur.empty()) {
                    columns.push_back({cur, false});
                    cur.clear();
                }
                const std::size_t parts = (run.size() + 11) / 12,
                                  size = (run.size() + parts - 1) / parts;
                for (std::size_t i = 0; i < run.size(); i += size)
                    columns.push_back({{run.begin() + static_cast<std::ptrdiff_t>(i),
                                        run.begin() + static_cast<std::ptrdiff_t>(
                                                          std::min(i + size, run.size()))},
                                       false});
                continue;
            }
            if (!cur.empty() && cur.size() + run.size() > 12) {
                columns.push_back({cur, false});
                cur.clear();
            }
            cur.insert(cur.end(), run.begin(), run.end());
        }
        if (!cur.empty())
            columns.push_back({cur, false});
        if (lv == 1) {
            spine_col = static_cast<int>(columns.size());
            columns.push_back({{}, true});
        }
    }
    if (spine_col < 0) {
        spine_col = 0;
        columns.insert(columns.begin(), {{}, true});
    }
    std::map<std::string, int> col_of;
    for (std::size_t i = 0; i < columns.size(); ++i)
        for (const auto &s : columns[i].members)
            col_of[s] = static_cast<int>(i);
    std::map<std::string, std::vector<std::string>> adj;
    for (const auto &[key, v] : peer) {
        (void)v;
        adj[key.first].push_back(key.second);
        adj[key.second].push_back(key.first);
    }
    for (const auto &[s, v] : som_bound) {
        (void)v;
        adj[s].push_back(spine);
        adj[spine].push_back(s);
    }
    std::map<std::string, double> pos;
    const auto reindex = [&] {
        for (const auto &col : columns)
            for (std::size_t i = 0; i < col.members.size(); ++i)
                pos[col.members[i]] = static_cast<double>(i);
        double sum = 0;
        std::size_t count = 0;
        for (const auto &[s, v] : som_bound) {
            (void)v;
            if (pos.count(s)) {
                sum += pos.at(s);
                ++count;
            }
        }
        pos[spine] = count ? sum / static_cast<double>(count) : 0;
    };
    reindex();
    const auto barycentre = [&](const std::string &s) {
        const auto &ns = adj[s];
        double sum = 0;
        for (const auto &n : ns)
            sum += pos.count(n) ? pos.at(n) : 0;
        return ns.empty() ? (pos.count(s) ? pos.at(s) : 0) : sum / static_cast<double>(ns.size());
    };
    for (int pass = 0; pass < 3; ++pass)
        for (auto &col : columns) {
            if (col.members.size() < 2)
                continue;
            auto keyed = col.members;
            std::stable_sort(keyed.begin(), keyed.end(), [&](const auto &a, const auto &b) {
                return std::make_pair(barycentre(a), a) < std::make_pair(barycentre(b), b);
            });
            std::map<int, std::vector<std::string>> members;
            for (const auto &s : keyed)
                members[cluster_of.at(s)].push_back(s);
            std::vector<std::pair<double, int>> order;
            for (const auto &[cl, ms] : members) {
                double sum = 0;
                for (const auto &s : ms)
                    sum += std::distance(keyed.begin(), std::find(keyed.begin(), keyed.end(), s));
                order.emplace_back(sum / static_cast<double>(ms.size()), cl);
            }
            std::sort(order.begin(), order.end());
            col.members.clear();
            for (const auto &item : order) {
                const auto &ms = members.at(item.second);
                col.members.insert(col.members.end(), ms.begin(), ms.end());
            }
            reindex();
        }
    std::map<std::string, std::pair<double, double>> xy;
    std::vector<ClusterRect> rects;
    std::vector<double> col_x, heights, widths;
    double x = col0;
    for (const auto &col : columns) {
        col_x.push_back(x);
        double y = top + 18;
        for (std::size_t i = 0; i < col.members.size();) {
            const int cl = cluster_of.at(col.members[i]);
            const double run_top = y;
            do {
                xy[col.members[i]] = {x, y};
                y += box_h + row_gap;
                ++i;
            } while (i < col.members.size() && cluster_of.at(col.members[i]) == cl);
            const double bottom = y - row_gap;
            rects.push_back(
                {cl, x - pad, run_top - 22, box_w + 2 * pad, (bottom - run_top) + 22 + pad});
            y += 26;
        }
        heights.push_back(y);
        widths.push_back(col.spine ? som_w : box_w);
        x += widths.back() + col_gap;
    }
    const double total_w = x - col_gap + col0,
                 body_h = *std::max_element(heights.begin(), heights.end());
    std::vector<std::pair<double, double>> gutters;
    for (std::size_t i = 0; i < columns.size(); ++i) {
        const double lo = col_x[i] + widths[i] + 6;
        gutters.emplace_back(lo, i + 1 < columns.size() ? col_x[i + 1] - 6 : lo + col_gap * 0.6);
    }
    const double spine_x = col_x[spine_col], spine_top = top + 18;
    const double spine_h =
        std::max(body_h - top - 40,
                 static_cast<double>(std::max<std::size_t>(1, som_bound.size())) * 30 + 60);
    const double spine_bottom = spine_top + spine_h,
                 content_h = std::max(body_h, spine_bottom + 56);
    std::size_t n_span2 = 0;
    for (const auto &[key, v] : peer) {
        (void)v;
        if (std::abs(col_of.at(key.first) - col_of.at(key.second)) >= 2)
            ++n_span2;
    }
    const double hw_top = content_h + 16,
                 hw_h = n_span2 ? 24 + static_cast<double>(n_span2) * 7.5 + 10 : 0;
    const double iso_top = (n_span2 ? hw_top + hw_h : content_h) + 30;
    std::map<std::string, std::pair<double, double>> iso_xy;
    double iso_bottom = content_h;
    if (!isolated.empty()) {
        const auto per_row = static_cast<std::size_t>(
            std::max(1.0, std::floor((total_w - 2 * col0 + 28) / (box_w + 28))));
        for (std::size_t i = 0; i < isolated.size(); ++i)
            iso_xy[isolated[i]] = {col0 + static_cast<double>(i % per_row) * (box_w + 28),
                                   iso_top + 24 + static_cast<double>(i / per_row) * (box_h + 22)};
        const auto rows = (isolated.size() + per_row - 1) / per_row;
        iso_bottom = iso_top + 24 + static_cast<double>(rows) * (box_h + 22);
    }
    const auto W = fixed(py_round(total_w, 0)),
               H = fixed(py_round(std::max(content_h, iso_bottom) + 24, 0));
    std::vector<std::string> e{
        "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 " + W + " " + H + "\" width=\"" +
            W + "\" height=\"" + H +
            "\" font-family=\"Segoe UI, Helvetica, Arial, sans-serif\" font-size=\"13\">",
        "<rect width=\"" + W + "\" height=\"" + H + "\" fill=\"#ffffff\"/>",
        "<text x=\"30\" y=\"38\" font-size=\"26\" font-weight=\"700\" fill=\"#0f172a\">Zynq "
        "carrier — linked port graph</text>",
        "<text x=\"30\" y=\"62\" font-size=\"15\" fill=\"#64748b\">" +
            std::to_string(sheets.size()) + " sheets · " + std::to_string(som_nets.size()) +
            " SoM contract nets · left-to-right by role; edges aggregated per sheet-pair "
            "(count · dominant kind); long cross-board links in the bottom channel</text>"};
    legend(e, W);
    std::stable_sort(rects.begin(), rects.end(), [](const auto &a, const auto &b) {
        return std::tie(a.x, a.y) < std::tie(b.x, b.y);
    });
    for (const auto &r : rects) {
        const auto &c = clusters[r.cluster];
        e.push_back("<rect x=\"" + fixed(r.x) + "\" y=\"" + fixed(r.y) + "\" width=\"" +
                    fixed(r.w) + "\" height=\"" + fixed(r.h) + "\" rx=\"12\" fill=\"" + c.fill +
                    "\" stroke=\"" + c.stroke + "\" stroke-width=\"1.3\"/>");
        e.push_back("<text x=\"" + fixed(r.x + 11) + "\" y=\"" + fixed(r.y + 16) +
                    "\" font-size=\"14\" font-weight=\"700\" fill=\"" + c.stroke + "\">" +
                    xml(c.title) + "</text>");
    }
    if (n_span2) {
        e.push_back("<rect x=\"" + fixed(col0 - pad) + "\" y=\"" + fixed(hw_top) + "\" width=\"" +
                    fixed(total_w - 2 * (col0 - pad)) + "\" height=\"" + fixed(hw_h) +
                    "\" rx=\"12\" fill=\"#f8fafc\" stroke=\"#e2e8f0\" stroke-width=\"1.2\"/>");
        e.push_back("<text x=\"" + fixed(col0 - pad + 12) + "\" y=\"" + fixed(hw_top + 14) +
                    "\" font-size=\"12\" font-weight=\"700\" fill=\"#94a3b8\">cross-board links (" +
                    std::to_string(n_span2) +
                    " edges spanning &#8805;2 columns, routed clear of the centre)</text>");
    }
    std::vector<Edge> edges;
    for (const auto &[key, items] : peer) {
        const bool lr = col_of.at(key.first) <= col_of.at(key.second);
        const auto &style = styles.at(edge_label(items).second);
        edges.push_back({lr ? key.first : key.second, lr ? key.second : key.first, items,
                         style.colour, style.width, "peer", "", false, false});
    }
    for (const auto &[s, items] : som_bound) {
        const bool lr = col_of.at(s) < spine_col;
        edges.push_back(
            {lr ? s : spine, lr ? spine : s, items, "#1d4ed8", 2.0, "som", "", lr, !lr});
    }
    for (const auto &[s, nets] : deferred) {
        auto sorted = nets;
        std::sort(sorted.begin(), sorted.end());
        Items items;
        for (const auto &n : sorted)
            items.emplace_back(n, "single");
        edges.push_back({s, later, items, "#9ca3af", 1.4, "defer", "5,4", true, false});
    }
    using Ids = std::vector<std::size_t>;
    std::map<std::string, Ids> right_groups, left_groups;
    for (std::size_t i = 0; i < edges.size(); ++i) {
        const auto &ed = edges[i];
        if (!ed.left_spine)
            right_groups[ed.left].push_back(i);
        if (!ed.right_spine && ed.right != later)
            left_groups[ed.right].push_back(i);
    }
    const auto partner_y = [&](std::size_t id, bool left) {
        const auto &other = left ? edges[id].right : edges[id].left;
        return other == later || other == spine ? spine_top + spine_h / 2
                                                : xy.at(other).second + box_h / 2;
    };
    std::vector<double> exit_y(edges.size()), entry_y(edges.size());
    const auto slot = [&](const auto &groups, bool left, auto &dest) {
        for (const auto &[box, ids] : groups) {
            auto order = ids;
            std::stable_sort(order.begin(), order.end(), [&](auto a, auto b) {
                return partner_y(a, left) < partner_y(b, left);
            });
            const double lo = xy.at(box).second + 10, hi = xy.at(box).second + box_h - 10;
            for (std::size_t i = 0; i < order.size(); ++i) {
                const double frac =
                    static_cast<double>(i + 1) / static_cast<double>(order.size() + 1);
                dest[order[i]] = lo + (hi - lo) * frac;
            }
        }
    };
    slot(right_groups, true, exit_y);
    slot(left_groups, false, entry_y);
    std::map<std::string, double> spine_anchor;
    if (!som_bound.empty()) {
        const double step = spine_h / static_cast<double>(som_bound.size() + 1);
        std::size_t i = 0;
        for (const auto &[s, v] : som_bound) {
            (void)v;
            spine_anchor[s] = spine_top + step * static_cast<double>(++i);
        }
    }
    const auto endpoints = [&](std::size_t id) {
        const auto &ed = edges[id];
        const double x0 = ed.left_spine ? spine_x + som_w : xy.at(ed.left).first + box_w;
        const double y0 = ed.left_spine ? spine_anchor.at(ed.right) : exit_y[id];
        const double x1 = ed.right_spine ? (ed.right == later ? spine_x + som_w / 2 : spine_x)
                                         : xy.at(ed.right).first;
        const double y1 = ed.right_spine
                              ? (ed.right == later ? spine_bottom + 30 : spine_anchor.at(ed.left))
                              : entry_y[id];
        return std::array<double, 4>{x0, y0, x1, y1};
    };
    const auto edge_gutter = [&](std::size_t id) {
        const auto &ed = edges[id];
        const int l = (ed.left == spine || ed.left == later) ? spine_col : col_of.at(ed.left);
        const int r = (ed.right == spine || ed.right == later) ? spine_col : col_of.at(ed.right);
        return std::make_pair(std::min(l, r), l == r);
    };
    Ids ordered(edges.size());
    std::iota(ordered.begin(), ordered.end(), 0);
    std::stable_sort(ordered.begin(), ordered.end(), [&](auto a, auto b) {
        const auto &l = edges[a];
        const auto &r = edges[b];
        return std::tie(l.role, l.left, l.right) < std::tie(r.role, r.left, r.right);
    });
    std::set<std::size_t> highways;
    std::map<int, Ids> by_gutter;
    for (auto id : ordered) {
        const auto &ed = edges[id];
        if (ed.role == "peer" && std::abs(col_of.at(ed.left) - col_of.at(ed.right)) >= 2)
            highways.insert(id);
        else
            by_gutter[edge_gutter(id).first].push_back(id);
    }
    std::vector<double> lane_x(edges.size()), hw_lane_y(edges.size()), hw_src_x(edges.size()),
        hw_dst_x(edges.size());
    for (const auto &[g, ids] : by_gutter) {
        auto sorted = ids;
        std::stable_sort(sorted.begin(), sorted.end(), [&](auto a, auto b) {
            const auto x = endpoints(a), y = endpoints(b);
            return (x[1] + x[3]) / 2 < (y[1] + y[3]) / 2;
        });
        const auto [lo, hi] = gutters.at(g);
        for (std::size_t i = 0; i < sorted.size(); ++i) {
            const double frac = static_cast<double>(i + 1) / static_cast<double>(sorted.size() + 1);
            lane_x[sorted[i]] = lo + (hi - lo) * frac;
        }
    }
    const auto ep_cols = [&](auto id) {
        const int l = col_of.at(edges[id].left), r = col_of.at(edges[id].right);
        return std::make_pair(std::min(l, r), std::max(l, r));
    };
    Ids hw_sorted;
    for (auto id : ordered)
        if (highways.count(id))
            hw_sorted.push_back(id);
    std::stable_sort(hw_sorted.begin(), hw_sorted.end(), [&](auto a, auto b) {
        return std::make_tuple(ep_cols(a).first, endpoints(a)[1], edges[a].left, edges[a].right) <
               std::make_tuple(ep_cols(b).first, endpoints(b)[1], edges[b].left, edges[b].right);
    });
    std::map<int, Ids> src_gutter, dst_gutter;
    for (auto id : hw_sorted) {
        src_gutter[ep_cols(id).first].push_back(id);
        dst_gutter[ep_cols(id).second - 1].push_back(id);
    }
    const auto highway_slots = [&](const auto &groups, auto &dest) {
        for (const auto &[g, ids] : groups) {
            const auto [lo, hi] = gutters.at(g);
            for (std::size_t i = 0; i < ids.size(); ++i)
                dest[ids[i]] = lo + (hi - lo) * static_cast<double>(i + 1) /
                                        static_cast<double>(ids.size() + 1);
        }
    };
    highway_slots(src_gutter, hw_src_x);
    highway_slots(dst_gutter, hw_dst_x);
    for (std::size_t i = 0; i < hw_sorted.size(); ++i)
        hw_lane_y[hw_sorted[i]] = hw_top + 24 + static_cast<double>(i) * 7.5;
    std::vector<Label> labels;
    for (auto id : ordered) {
        const auto &ed = edges[id];
        const auto p = endpoints(id);
        const auto [x0, y0, x1, y1] = p;
        std::string d = "M" + fixed(x0, 1) + "," + fixed(y0, 1) + " H";
        if (highways.count(id))
            d += fixed(hw_src_x[id], 1) + " V" + fixed(hw_lane_y[id], 1) + " H" +
                 fixed(hw_dst_x[id], 1) + " V" + fixed(y1, 1) + " H" + fixed(x1, 1);
        else {
            double mx = lane_x[id];
            if (edge_gutter(id).second) {
                std::uint64_t sum = 0;
                for (auto cp : codepoints(ed.left + ed.right))
                    sum += cp;
                mx = std::max(x0, x1) + 14 + static_cast<double>(sum % 5) * 7;
            }
            d += fixed(mx, 1) + " V" + fixed(y1, 1) + " H" + fixed(x1, 1);
        }
        const auto dash = ed.dash.empty() ? "" : " stroke-dasharray=\"" + ed.dash + "\"";
        std::vector<std::string> names;
        for (const auto &item : ed.items)
            names.push_back(item.first);
        const auto ln = ed.left == spine ? "SoM" : xml(ed.left), rn = ed.right == spine ? "SoM"
                                                                      : ed.right == later
                                                                          ? "later"
                                                                          : xml(ed.right);
        e.push_back("<path d=\"" + d + "\" fill=\"none\" stroke=\"" + ed.colour +
                    "\" stroke-width=\"" + pyfloat(ed.width) +
                    "\" stroke-linejoin=\"round\" stroke-opacity=\"0.72\"" + dash + "><title>" +
                    ln + " ↔ " + rn + ": " + xml(join(names, ", ")) + "</title></path>");
        if (ed.right == spine)
            e.push_back("<circle cx=\"" + fixed(x1, 1) + "\" cy=\"" + fixed(y1, 1) +
                        "\" r=\"2.6\" fill=\"" + ed.colour + "\"/>");
        if (ed.left_spine)
            e.push_back("<circle cx=\"" + fixed(x0, 1) + "\" cy=\"" + fixed(y0, 1) +
                        "\" r=\"2.6\" fill=\"" + ed.colour + "\"/>");
        const auto text = ed.role == "defer" ? std::to_string(ed.items.size()) + " " +
                                                   net_word(ed.items.size()) + " deferred"
                                             : edge_label(ed.items).first;
        if (ed.right == spine)
            labels.push_back({x1 - 6, y1, text, ed.colour, "end", spine_top + 6, spine_bottom - 6});
        else if (ed.left_spine)
            labels.push_back(
                {x0 + 6, y0, text, ed.colour, "start", spine_top + 6, spine_bottom - 6});
        else if (ed.right == later)
            labels.push_back({x0 + 8, y0, text, ed.colour, "start", y0 - 6, y0 + 30});
        else
            labels.push_back({x1 - 6, y1, text, ed.colour, "end", y1 - 40, y1 + 40});
    }
    std::stable_sort(labels.begin(), labels.end(), [](const auto &a, const auto &b) {
        return std::make_tuple(py_round(a.x, 0), a.y, a.text) <
               std::make_tuple(py_round(b.x, 0), b.y, b.text);
    });
    std::vector<std::array<double, 3>> placed;
    for (const auto &label : labels) {
        const double w = 6.7 * static_cast<double>(codepoints(label.text).size()) + 12,
                     half = w / 2;
        const double cx = label.anchor == "end" ? label.x - half : label.x + half;
        double yy = label.y;
        bool found = false;
        for (int step = 0; step < 48 && !found; ++step) {
            const std::vector<int> signs =
                step == 0 ? std::vector<int>{0} : std::vector<int>{-1, 1};
            for (int sign : signs) {
                const double cand = label.y + sign * step * 8;
                if (cand < label.lo || cand > label.hi)
                    continue;
                const bool clash = std::any_of(placed.begin(), placed.end(), [&](const auto &p) {
                    return std::abs(p[0] - cx) < half + p[2] && std::abs(p[1] - cand) < 16;
                });
                if (!clash) {
                    yy = cand;
                    found = true;
                    break;
                }
            }
        }
        if (!found)
            continue;
        placed.push_back({cx, yy, half});
        const auto anchor = label.anchor == "start" ? "" : " text-anchor=\"" + label.anchor + "\"";
        e.push_back("<rect x=\"" + fixed(cx - half, 1) + "\" y=\"" + fixed(yy - 9.5, 1) +
                    "\" width=\"" + fixed(w, 1) +
                    "\" height=\"17\" rx=\"5\" fill=\"#ffffff\" fill-opacity=\"0.97\" stroke=\"" +
                    label.colour + "\" stroke-opacity=\"0.5\" stroke-width=\"0.8\"/>");
        e.push_back("<text x=\"" + fixed(label.x, 1) + "\" y=\"" + fixed(yy + 3.5, 1) + "\"" +
                    anchor + " font-size=\"13\" font-weight=\"600\" fill=\"" + label.colour +
                    "\">" + xml(label.text) + "</text>");
    }
    const auto centre = fixed(spine_x + som_w / 2);
    e.push_back("<rect x=\"" + fixed(spine_x) + "\" y=\"" + fixed(spine_top) +
                "\" width=\"168\" height=\"" + fixed(spine_h) +
                "\" rx=\"12\" fill=\"#fef3c7\" stroke=\"#b45309\" stroke-width=\"2.4\"/>");
    e.push_back("<text x=\"" + centre + "\" y=\"" + fixed(spine_top + 26) +
                "\" text-anchor=\"middle\" font-size=\"15\" font-weight=\"700\" "
                "fill=\"#78350f\">Zynq SoM</text>");
    e.push_back(
        "<text x=\"" + centre + "\" y=\"" + fixed(spine_top + 44) +
        "\" text-anchor=\"middle\" font-size=\"11\" fill=\"#92400e\">J1 / J2 / J3 contract</text>");
    e.push_back("<text x=\"" + centre + "\" y=\"" + fixed(spine_top + 62) +
                "\" text-anchor=\"middle\" font-size=\"11\" fill=\"#92400e\">" +
                std::to_string(som_nets.size()) + " nets</text>");
    double ry = spine_top + 86;
    e.push_back("<text x=\"" + centre + "\" y=\"" + fixed(ry) +
                "\" text-anchor=\"middle\" font-size=\"10.5\" font-weight=\"600\" "
                "fill=\"#78350f\">rails</text>");
    for (const auto &r : rails) {
        ry += 15;
        e.push_back("<text x=\"" + centre + "\" y=\"" + fixed(ry) +
                    "\" text-anchor=\"middle\" font-size=\"10.5\" fill=\"#92400e\">" + xml(r) +
                    "</text>");
    }
    e.push_back("<text x=\"" + centre + "\" y=\"" + fixed(spine_bottom - 10) +
                "\" text-anchor=\"middle\" font-size=\"10\" fill=\"#a16207\">" +
                std::to_string(link.unbound_som.size()) + " unbound (later)</text>");
    if (!deferred.empty()) {
        std::size_t count = 0;
        for (const auto &[s, n] : deferred) {
            (void)s;
            count += n.size();
        }
        const double lx = spine_x + som_w / 2, ly = spine_bottom + 30;
        e.push_back("<rect x=\"" + fixed(lx - 58) + "\" y=\"" + fixed(ly - 13) +
                    "\" width=\"116\" height=\"26\" rx=\"8\" fill=\"#ffffff\" stroke=\"#9ca3af\" "
                    "stroke-width=\"1.3\" stroke-dasharray=\"5,4\"/>");
        e.push_back("<text x=\"" + fixed(lx) + "\" y=\"" + fixed(ly + 4) +
                    "\" text-anchor=\"middle\" font-size=\"11\" fill=\"#6b7280\">later waves · " +
                    std::to_string(count) + "</text>");
    }
    for (const auto &s : laid) {
        const auto [bx, by] = xy.at(s);
        const auto &cl = clusters[cluster_of.at(s)];
        const std::size_t nb = som_bound.count(s) ? som_bound.at(s).size() : 0,
                          nd = deferred.count(s) ? deferred.at(s).size() : 0;
        std::size_t np = 0;
        for (const auto &[key, v] : peer)
            if (s == key.first || s == key.second)
                np += v.size();
        e.push_back("<rect x=\"" + fixed(bx) + "\" y=\"" + fixed(by) +
                    "\" width=\"172\" height=\"56\" rx=\"8\" fill=\"#ffffff\" stroke=\"" +
                    cl.stroke + "\" stroke-width=\"1.8\"/>");
        e.push_back("<text x=\"" + fixed(bx + 11) + "\" y=\"" + fixed(by + 23) +
                    "\" font-size=\"15.5\" font-weight=\"700\" fill=\"#0f172a\">" + xml(s) +
                    "</text>");
        std::vector<std::string> sub;
        if (nb)
            sub.push_back(std::to_string(nb) + " SoM");
        if (np)
            sub.push_back(std::to_string(np) + " peer");
        if (nd)
            sub.push_back(std::to_string(nd) + " deferred");
        e.push_back("<text x=\"" + fixed(bx + 11) + "\" y=\"" + fixed(by + 43) +
                    "\" font-size=\"12.5\" fill=\"#64748b\">" +
                    xml(sub.empty() ? "—" : join(sub, " · ")) + "</text>");
    }
    if (!isolated.empty()) {
        e.push_back("<text x=\"150\" y=\"" + fixed(iso_top + 6) +
                    "\" font-size=\"13\" font-weight=\"700\" fill=\"#475569\">unconnected sheets "
                    "(no inter-sheet nets)</text>");
        for (const auto &s : isolated) {
            const auto [bx, by] = iso_xy.at(s);
            const auto &cl = clusters[cluster_of.at(s)];
            e.push_back("<rect x=\"" + fixed(bx) + "\" y=\"" + fixed(by) +
                        "\" width=\"172\" height=\"56\" rx=\"8\" fill=\"#f8fafc\" stroke=\"" +
                        cl.stroke + "\" stroke-width=\"1.6\"/>");
            e.push_back("<text x=\"" + fixed(bx + 11) + "\" y=\"" + fixed(by + 23) +
                        "\" font-size=\"15.5\" font-weight=\"700\" fill=\"#334155\">" + xml(s) +
                        "</text>");
            e.push_back("<text x=\"" + fixed(bx + 11) + "\" y=\"" + fixed(by + 43) +
                        "\" font-size=\"12.5\" fill=\"#94a3b8\">—</text>");
        }
    }
    e.push_back("</svg>");
    return join(e, "\n") + "\n";
}
std::filesystem::path write_block_diagram(const LinkResult &link, const LinkSomNets &nets,
                                          const std::filesystem::path &path) {
    const auto svg = render_block_diagram(link, nets);
    if (!path.parent_path().empty())
        fs::create_directories(path.parent_path());
    publish(path, svg);
    return path;
}
} // namespace schgen
