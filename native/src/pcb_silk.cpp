#include "pcb_emit_internal.hpp"
#include "schgen/label_seats.hpp"
#include "schgen/output_precision.hpp"

namespace schgen::pcb_emission {
namespace {
Sexpr silk_text(const std::string &s, double x, double y, double size, const std::string &id,
                QuantizationCounts* counts) {
    return emit_gr_text(s, pcb_silk_position_precision3dp(x, counts),
                        pcb_silk_position_precision3dp(y, counts), 0, "F.SilkS", id, size,
                        pcb_silk_stroke_precision3dp(std::max(.12, size * .16), counts), "");
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
                               const Sexpr &doc, QuantizationCounts* counts,
                               const labels::LabelSeating* seats) {
    std::vector<Sexpr> out;
    Box4 bounds{m.origin_x, m.origin_y, m.origin_x + m.board_w, m.origin_y + m.board_h};
    SilkBoxIndex occupied(8);
    for (const auto &i : m.insts)
        occupied.add(courtyard(i), counts);
    for (auto b : collect_emitted_text_boxes(doc, true, 1))
        occupied.add(b, counts);
    if (seats)
        for (const auto &seat : seats->seats)
            if (seat.seat != labels::Seat::hidden && seat.face == layout::Face::top)
                occupied.add({layout::to_mm(seat.box.x0), layout::to_mm(seat.box.y0), layout::to_mm(seat.box.x1),
                              layout::to_mm(seat.box.y1)},
                             counts);
    std::map<std::string, std::vector<std::string>> numbered;
    for (const auto &i : m.insts)
        if (const auto *fact = connector_fact(p.connectors, i.value); fact && fact->numbered_label)
            numbered[*fact->numbered_label].push_back(i.ref);
    std::map<std::string, std::string> ordinal;
    for (auto &[label, refs] : numbered) {
        std::sort(refs.begin(), refs.end());
        for (std::size_t n = 0; n < refs.size(); ++n)
            ordinal[refs[n]] = label + std::to_string(n);
    }
    for (const auto &i : m.insts) {
        if (!connector_fact(p.connectors, i.value))
            continue;
        if (!i.silk_label)
            continue;
        std::string desc = *i.silk_label;
        if (ordinal.count(i.ref))
            desc = ordinal.at(i.ref);
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
            if (!occupied.hits(text_box(desc, x, y, size, .15), counts)) {
                clear = true;
                break;
            }
        }
        if (!clear) {
            auto seat =
                place_clear_label(b.x0, b.y0, b.x1, b.y1, desc, size, occupied, nullptr, bounds, counts);
            x = seat.x;
            y = seat.y;
        }
        out.push_back(silk_text(desc, x, y, size, uid("conn-desc:" + i.ref), counts));
        occupied.add(text_box(desc, x, y, size, .15), counts);
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
            place_clear_label(b.x0, b.y0, b.x1, b.y1, text, size, occupied, nullptr, bounds, counts);
        if (seat.extra > 8 && text.find(':') != text.npos) {
            auto short_text = trim(text.substr(0, text.find(':')));
            double ss = label_size(short_text);
            auto short_seat = place_clear_label(b.x0, b.y0, b.x1, b.y1, short_text, ss, occupied,
                                                nullptr, bounds, counts);
            if (short_seat.extra < seat.extra) {
                text = short_text;
                size = ss;
                seat = short_seat;
            }
        }
        occupied.add(seat.box, counts);
        out.push_back(silk_text(text, seat.x, seat.y, size, uid(prefix + ":" + i.ref), counts));
    }
    return out;
}
void seat_references(const PcbModel &m, Sexpr &doc, const labels::LabelSeating &seating) {
    if (seating.seats.size() != m.insts.size())
        throw PcbEmissionError("label seats do not match the placed parts");
    std::unordered_map<std::string, const labels::LabelSeat *> seats;
    std::size_t shown = 0, applied = 0;
    for (const auto &seat : seating.seats) {
        if (!seats.emplace(seat.reference, &seat).second)
            throw PcbEmissionError(seat.reference + ": two label seats share one reference");
        if (seat.seat != labels::Seat::hidden)
            ++shown;
    }
    for (auto &footprint : std::get<SexprList>(doc.v)) {
        if (!tag(footprint, "footprint"))
            continue;
        for (auto &prop : std::get<SexprList>(footprint.v)) {
            auto *fields = std::get_if<SexprList>(&prop.v);
            if (!fields || !tag(prop, "property") || fields->size() <= 2)
                continue;
            const auto *name = std::get_if<std::string>(&(*fields)[1].v);
            const auto *ref = std::get_if<std::string>(&(*fields)[2].v);
            if (!name || *name != "Reference")
                continue;
            const auto found = ref ? seats.find(*ref) : seats.end();
            if (found == seats.end())
                throw PcbEmissionError("a placed reference has no label seat");
            const auto &seat = *found->second;
            fields->erase(std::remove_if(fields->begin(), fields->end(),
                                         [](const Sexpr &field) { return tag(field, "hide"); }),
                          fields->end());
            if (seat.seat == labels::Seat::hidden) {
                const auto layer = std::find_if(fields->begin(), fields->end(),
                                                [](const Sexpr &field) { return tag(field, "layer"); });
                if (layer == fields->end())
                    throw PcbEmissionError(seat.reference + ": reference has no layer to hide on");
                fields->insert(layer + 1, node("hide", {sym("yes")}));
                break;
            }
            auto *at = child(prop, "at");
            if (!at)
                throw PcbEmissionError(seat.reference + ": reference lost its placement");
            *at = node("at", {num(layout::to_mm(seat.local.x)), num(layout::to_mm(seat.local.y)),
                              num(seat.upright ? layout::constants::quarter_degrees.value : 0)});
            prop = set_font_size(std::move(prop), seat.height);
            if (font_size(prop, 0) != seat.height)
                throw PcbEmissionError(seat.reference + ": reference has no font to size");
            ++applied;
            break;
        }
    }
    if (applied != shown)
        throw PcbEmissionError("a seated label has no reference to carry it");
}
int declutter(const PcbModel &m, Sexpr &doc, QuantizationCounts* counts) {
    Box4 bounds{m.origin_x, m.origin_y, m.origin_x + m.board_w, m.origin_y + m.board_h};
    SilkBoxIndex top(8), bottom(8), placed_top(8), placed_bottom(8);
    std::unordered_map<std::string, Box4> courts;
    for (const auto &i : m.insts) {
        auto b = courtyard(i);
        top.add(b, counts);
        if (i.side == "bottom")
            bottom.add(b, counts);
        courts[i.ref] = b;
    }
    for (auto b : collect_gr_text_boxes(doc, 1))
        top.add(b, counts);
    auto &root = std::get<SexprList>(doc.v);
    for (const auto &n : root)
        if (tag(n, "footprint")) {
            auto [a, b] = collect_fp_silk_gfx(n);
            for (auto r : a)
                top.add(r, counts);
            for (auto r : b)
                bottom.add(r, counts);
        }
    int moved = 0;
    for (const auto &row : collect_refdes_rows(doc, courts, 1)) {
        auto &occ = row.bottom ? bottom : top;
        auto &placed = row.bottom ? placed_bottom : placed_top;
        auto move =
            place_refdes(row.court, row.ref, row.size, row.text_box, occ, placed, bounds, row.fp_x,
                         row.fp_y, row.cos_a, row.sin_a, .8, .02, 8, 1e-9, .5, {.78, .62}, counts);
        placed.add(move.add_box, counts);
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
