#include "pcb_emit_internal.hpp"

namespace schgen::pcb_emission {
namespace {
Sexpr silk_text(const std::string &s, double x, double y, double size, const std::string &id) {
    return emit_gr_text(s, py_round(x, 3), py_round(y, 3), 0, "F.SilkS", id, size,
                        py_round(std::max(.12, size * .16), 3), "");
}
double label_size(const std::string &s) {
    std::size_t n = 0;
    for (unsigned char c : s)
        if ((c & 0xc0) != 0x80)
            ++n;
    return n <= 8 ? 1.1 : n <= 16 ? .95 : n <= 24 ? .85 : .78;
}
std::string trim(std::string s) {
    // Python str.strip uses Unicode whitespace, including the four ASCII
    // information separators. Match UTF-8 tokens without changing label bytes.
    static constexpr std::string_view spaces[] = {" ",
                                                  "\t",
                                                  "\n",
                                                  "\r",
                                                  "\f",
                                                  "\v",
                                                  "\x1c",
                                                  "\x1d",
                                                  "\x1e",
                                                  "\x1f",
                                                  "\xc2\x85",
                                                  "\xc2\xa0",
                                                  "\xe1\x9a\x80",
                                                  "\xe2\x80\x80",
                                                  "\xe2\x80\x81",
                                                  "\xe2\x80\x82",
                                                  "\xe2\x80\x83",
                                                  "\xe2\x80\x84",
                                                  "\xe2\x80\x85",
                                                  "\xe2\x80\x86",
                                                  "\xe2\x80\x87",
                                                  "\xe2\x80\x88",
                                                  "\xe2\x80\x89",
                                                  "\xe2\x80\x8a",
                                                  "\xe2\x80\xa8",
                                                  "\xe2\x80\xa9",
                                                  "\xe2\x80\xaf",
                                                  "\xe2\x81\x9f",
                                                  "\xe3\x80\x80"};
    std::string_view text(s);
    auto remove_space = [&](bool front) {
        for (auto space : spaces) {
            if (text.size() < space.size())
                continue;
            if (text.substr(front ? 0 : text.size() - space.size(), space.size()) == space) {
                if (front)
                    text.remove_prefix(space.size());
                else
                    text.remove_suffix(space.size());
                return true;
            }
        }
        return false;
    };
    while (remove_space(true)) {
    }
    while (remove_space(false)) {
    }
    return std::string(text);
}
} // namespace
std::vector<Sexpr> descriptors(const PcbModel &m, const PcbEmitPolicy &p, const Uid &uid,
                               const Sexpr &doc) {
    std::vector<Sexpr> out;
    Box4 bounds{m.origin_x, m.origin_y, m.origin_x + m.board_w, m.origin_y + m.board_h};
    SilkBoxIndex occupied(8);
    for (const auto &i : m.insts)
        occupied.add(courtyard(i));
    for (auto b : collect_emitted_text_boxes(doc, true, 1))
        occupied.add(b);
    std::vector<std::string> pmods;
    for (const auto &i : m.insts)
        if (i.value == "DS1024-2x6R2")
            pmods.push_back(i.ref);
    std::sort(pmods.begin(), pmods.end());
    std::map<std::string, int> ordinal;
    for (std::size_t n = 0; n < pmods.size(); ++n)
        ordinal[pmods[n]] = static_cast<int>(n);
    for (const auto &i : m.insts) {
        if (!lookup(p.connector_mating_faces, i.value))
            continue;
        auto text = lookup(p.connector_descriptions, i.sheet);
        if (!text)
            continue;
        std::string desc = *text;
        if (ordinal.count(i.ref))
            desc = "PMOD" + std::to_string(ordinal.at(i.ref));
        auto b = courtyard(i);
        std::array<double, 4> distances{b.y0 - bounds.y0, bounds.y1 - b.y1, b.x0 - bounds.x0,
                                        bounds.x1 - b.x1};
        auto edge = std::min_element(distances.begin(), distances.end());
        if (*edge > 12)
            continue;
        int direction = static_cast<int>(edge - distances.begin());
        double mx = (b.x0 + b.x1) / 2, my = (b.y0 + b.y1) / 2, x = mx, y = my, size = 1.1;
        bool clear = false;
        for (double gap : {1.8, 3.2, 4.6, 6., 7.6, 9.4}) {
            if (direction == 0) {
                x = mx;
                y = b.y1 + gap;
            } else if (direction == 1) {
                x = mx;
                y = b.y0 - gap;
            } else if (direction == 2) {
                x = b.x1 + gap;
                y = my;
            } else {
                x = b.x0 - gap;
                y = my;
            }
            if (!occupied.hits(text_box(desc, x, y, size, .15))) {
                clear = true;
                break;
            }
        }
        if (!clear) {
            auto seat =
                place_clear_label(b.x0, b.y0, b.x1, b.y1, desc, size, occupied, nullptr, bounds);
            x = seat.x;
            y = seat.y;
        }
        out.push_back(silk_text(desc, x, y, size, uid("conn-desc:" + i.ref)));
        occupied.add(text_box(desc, x, y, size, .15));
    }
    for (const auto &i : m.insts) {
        auto label = lookup(p.header_descriptions, i.ref);
        std::string prefix = "conn-desc";
        if (!label) {
            label = lookup(p.switch_descriptions, i.ref);
            prefix = "sw-desc";
        }
        if (!label)
            continue;
        auto b = courtyard(i);
        std::string text = *label;
        double size = label_size(text);
        auto seat =
            place_clear_label(b.x0, b.y0, b.x1, b.y1, text, size, occupied, nullptr, bounds);
        if (seat.extra > 8 && text.find(':') != text.npos) {
            auto short_text = trim(text.substr(0, text.find(':')));
            double ss = label_size(short_text);
            auto short_seat = place_clear_label(b.x0, b.y0, b.x1, b.y1, short_text, ss, occupied,
                                                nullptr, bounds);
            if (short_seat.extra < seat.extra) {
                text = short_text;
                size = ss;
                seat = short_seat;
            }
        }
        occupied.add(seat.box);
        out.push_back(silk_text(text, seat.x, seat.y, size, uid(prefix + ":" + i.ref)));
    }
    return out;
}
int declutter(const PcbModel &m, Sexpr &doc) {
    Box4 bounds{m.origin_x, m.origin_y, m.origin_x + m.board_w, m.origin_y + m.board_h};
    SilkBoxIndex top(8), bottom(8), placed_top(8), placed_bottom(8);
    std::unordered_map<std::string, Box4> courts;
    for (const auto &i : m.insts) {
        auto b = courtyard(i);
        top.add(b);
        if (i.side == "bottom")
            bottom.add(b);
        courts[i.ref] = b;
    }
    for (auto b : collect_gr_text_boxes(doc, 1))
        top.add(b);
    auto &root = std::get<SexprList>(doc.v);
    for (const auto &n : root)
        if (tag(n, "footprint")) {
            auto [a, b] = collect_fp_silk_gfx(n);
            for (auto r : a)
                top.add(r);
            for (auto r : b)
                bottom.add(r);
        }
    int moved = 0;
    for (const auto &row : collect_refdes_rows(doc, courts, 1)) {
        auto &occ = row.bottom ? bottom : top;
        auto &placed = row.bottom ? placed_bottom : placed_top;
        auto move =
            place_refdes(row.court, row.ref, row.size, row.text_box, occ, placed, bounds, row.fp_x,
                         row.fp_y, row.cos_a, row.sin_a, .8, .02, 8, 1e-9, .5, {.78, .62});
        placed.add(move.add_box);
        if (move.moved) {
            auto &prop = std::get<SexprList>(root.at(row.footprint_index).v).at(row.property_index);
            auto at = child(prop, "at");
            if (!at)
                throw PcbEmissionError("reference lost its placement");
            auto &xy = std::get<SexprList>(at->v);
            xy.at(1) = num(move.local_x);
            xy.at(2) = num(move.local_y);
            if (move.size != row.size)
                prop = set_font_size(std::move(prop), move.size);
            ++moved;
        }
    }
    return moved;
}
} // namespace schgen::pcb_emission
