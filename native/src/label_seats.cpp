#include "schgen/label_seats.hpp"

#include "pcb_emit_internal.hpp"
#include "schgen/layout_kernel.hpp"

#include <map>
#include <numeric>
#include <optional>
#include <unordered_map>

namespace schgen::labels {
namespace {

using layout::Box;
using layout::Face;
using layout::Nm;
using layout::Point;
using layout::Turn;

enum class Block : std::uint8_t { pad, part, label, module, mark, edge, nearer };

enum class Side : std::uint8_t { above, below, right, left };

inline constexpr std::size_t block_count = 7;
inline constexpr char glyph = 'x';
inline constexpr unsigned char continuation_mask = 0xc0, continuation_bits = 0x80;
inline constexpr std::array flat_sides{Side::above, Side::below, Side::right, Side::left};
inline constexpr std::array upright_sides{Side::left, Side::right, Side::above, Side::below};
inline constexpr std::array<const char*, block_count> block_names{
    "over a pad or drill", "over a part", "over another label", "under the module",
    "over the module title", "off the board", "nearer another part"};

struct Claim {
    Box box;
    Block block = Block::pad;
    std::size_t owner = 0;
};

class Occupancy {
public:
    void add(Box box, Block block, std::size_t owner) {
        const std::size_t index = claims_.size();
        claims_.push_back({box, block, owner});
        for (Nm column = cell_of(box.x0); column <= cell_of(box.x1); ++column)
            for (Nm row = cell_of(box.y0); row <= cell_of(box.y1); ++row) cells_[key_of(column, row)].push_back(index);
    }
    template <typename Blocks>
    const Claim* first(Box box, Blocks&& blocks) const {
        for (Nm column = cell_of(box.x0); column <= cell_of(box.x1); ++column)
            for (Nm row = cell_of(box.y0); row <= cell_of(box.y1); ++row) {
                const auto cell = cells_.find(key_of(column, row));
                if (cell == cells_.end()) continue;
                for (const std::size_t index : cell->second)
                    if (layout::overlaps(claims_[index].box, box) && blocks(claims_[index])) return &claims_[index];
            }
        return nullptr;
    }

private:
    static Nm cell_of(Nm coordinate) {
        const Nm cell = static_cast<Nm>(layout::constants::hash_cell.value);
        const Nm quotient = coordinate / cell;
        return coordinate % cell < 0 ? quotient - 1 : quotient;
    }
    static std::uint64_t key_of(Nm column, Nm row) {
        const auto shift = static_cast<unsigned>(layout::constants::key_shift.value);
        return (static_cast<std::uint64_t>(static_cast<std::uint32_t>(column)) << shift) |
               static_cast<std::uint64_t>(static_cast<std::uint32_t>(row));
    }

    std::vector<Claim> claims_;
    std::unordered_map<std::uint64_t, std::vector<std::size_t>> cells_;
};

struct Subject {
    Face face = Face::top;
    Point at;
    Turn turn = Turn::none;
    Box court;
    bool silk = false, interface = false;
    std::size_t pads = 0;
};

struct Tally {
    std::size_t tried = 0;
    std::array<std::size_t, block_count> blocked{};
};

Face face_named(const PcbCheckInstance& instance) {
    if (instance.side == "top") return Face::top;
    if (instance.side == "bottom") return Face::bottom;
    throw LabelError("labels: " + instance.ref + " sits on an unknown side " + instance.side);
}

const char* face_name(Face face) { return face == Face::top ? "top" : "bottom"; }

Occupancy& on(std::array<Occupancy, face_count>& faces, Face face) { return faces[static_cast<std::size_t>(face)]; }

bool draws_reference(const Sexpr& document) {
    const auto* root = std::get_if<SexprList>(&document.v);
    if (!root) return false;
    for (const Sexpr& node : *root) {
        const auto* property = std::get_if<SexprList>(&node.v);
        if (!property || !pcb_emission::tag(node, "property") || property->size() <= 2) continue;
        const auto* name = std::get_if<std::string>(&(*property)[1].v);
        if (!name || *name != "Reference") continue;
        for (const Sexpr& field : *property) {
            const auto* layer = std::get_if<SexprList>(&field.v);
            if (!layer || !pcb_emission::tag(field, "layer") || layer->size() <= 1) continue;
            const auto* text = std::get_if<std::string>(&(*layer)[1].v);
            return text && text->find("SilkS") != std::string::npos;
        }
    }
    return false;
}

Box pad_box(const PcbCheckInstance& instance, const Subject& subject, std::size_t pad) {
    const auto& [name, type, x, y, rotation, width, height] = instance.mod->pads[pad];
    const auto half = pad_half_extent(width, height, rotation);
    const Point centre{layout::nearest_nm(x), layout::nearest_nm(y)};
    const Nm reach_x = layout::ceil_nm(half.first), reach_y = layout::ceil_nm(half.second);
    return layout::placed(Box{centre.x - reach_x, centre.y - reach_y, centre.x + reach_x, centre.y + reach_y},
                          subject.at, subject.turn);
}

bool drilled(const PcbCheckInstance& instance, std::size_t pad) {
    const std::string& type = std::get<1>(instance.mod->pads[pad]);
    return type == "thru_hole" || type == "np_thru_hole";
}

Box box_of(const Box4& box) {
    return {layout::nearest_nm(box.x0), layout::nearest_nm(box.y0), layout::nearest_nm(box.x1),
            layout::nearest_nm(box.y1)};
}

Box title_box(const Box4& core) {
    const Box4 flat = text_box(module_title, 0, 0, constants::title_height.value, constants::label_margin.value);
    const Nm margin = layout::ceil_nm(constants::label_margin.value);
    const Nm left = layout::nearest_nm(core.x0 + constants::title_indent.value) - margin;
    const Nm base = layout::nearest_nm(core.y0 - constants::title_rise.value) + margin;
    return {left, base - 2 * layout::ceil_nm(flat.y1), left + 2 * layout::ceil_nm(flat.x1), base};
}

Subject subject_of(const PcbCheckInstance& instance, const PcbEmitPolicy& policy) {
    if (!instance.mod || !instance.mod->bbox)
        throw LabelError("labels: " + instance.ref + " has no footprint courtyard to seat a label beside");
    Subject subject;
    subject.face = face_named(instance);
    subject.at = {layout::to_nm(instance.x), layout::to_nm(instance.y)};
    subject.turn = layout::turn_of(instance.rotation);
    subject.court = layout::placed(box_of(*instance.mod->bbox), subject.at, subject.turn);
    subject.silk = draws_reference(instance.mod->document);
    subject.interface = pcb_emission::interface_label_part(instance, policy);
    subject.pads = instance.mod->pads.size();
    return subject;
}

Nm side_limit(const Box& court, const Box& extent, Side side) {
    const bool along_x = side == Side::above || side == Side::below;
    return along_x ? std::max(extent.x1, court.width() / 2) : std::max(extent.y1, court.height() / 2);
}

Point seat_centre(const Box& court, const Box& extent, Side side, Nm ring, Nm slide) {
    const Nm mid_x = (court.x0 + court.x1) / 2, mid_y = (court.y0 + court.y1) / 2;
    switch (side) {
    case Side::above: return {mid_x + slide, court.y0 - ring - extent.y1};
    case Side::below: return {mid_x + slide, court.y1 + ring + extent.y1};
    case Side::right: return {court.x1 + ring + extent.x1, mid_y + slide};
    case Side::left: break;
    }
    return {court.x0 - ring - extent.x1, mid_y + slide};
}

std::optional<Block> blocker(const Occupancy& face, const Box& outline, const Box& label, std::size_t part, Nm ring) {
    if (!layout::inside(label, outline)) return Block::edge;
    if (const Claim* claim = face.first(label, [](const Claim&) { return true; })) return claim->block;
    if (ring > 0 && face.first(layout::grown(label, ring), [&](const Claim& claim) {
            return claim.block == Block::part && claim.owner != part;
        }))
        return Block::nearer;
    return std::nullopt;
}

bool seat_one(const Occupancy& face, const Box& outline, const Subject& subject, std::size_t part, LabelSeat& seat,
              Tally& tally) {
    const Nm step = static_cast<Nm>(constants::label_step.value), reach = static_cast<Nm>(constants::label_reach.value);
    const double floor = board_fabrication().profile.number(fabricator_key::silk_height);
    std::vector<double> heights{std::max(constants::label_height.value, floor)};
    if (floor < heights.front()) heights.push_back(floor);
    for (Nm ring = 0; ring <= reach; ring += step)
        for (const double height : heights)
            for (const bool upright : {false, true}) {
                const Box extent = label_extent(seat.reference, height, upright);
                const auto& sides = upright ? upright_sides : flat_sides;
                Nm widest = 0;
                for (const Side side : sides) widest = std::max(widest, side_limit(subject.court, extent, side));
                for (Nm slide = 0; slide <= widest; slide += step)
                    for (const Side side : sides) {
                        if (slide > side_limit(subject.court, extent, side)) continue;
                        for (const Nm offset : {slide, -slide}) {
                            if (slide == 0 && offset != slide) continue;
                            const Point centre = seat_centre(subject.court, extent, side, ring, offset);
                            const Box label = layout::shifted(extent, centre);
                            ++tally.tried;
                            if (const auto block = blocker(face, outline, label, part, ring)) {
                                ++tally.blocked[static_cast<std::size_t>(*block)];
                                continue;
                            }
                            seat.seat = ring == 0 ? Seat::beside : Seat::apart;
                            seat.centre = centre;
                            seat.box = label;
                            seat.upright = upright;
                            seat.height = height;
                            return true;
                        }
                    }
            }
    return false;
}

std::string unseated(const Tally& tally) {
    std::ostringstream text;
    text << "no free seat within " << layout::to_mm(static_cast<Nm>(constants::label_reach.value))
         << " mm of its part; " << tally.tried << " positions tried";
    for (std::size_t block = 0; block < block_count; ++block)
        if (tally.blocked[block] != 0) text << ", " << tally.blocked[block] << " " << block_names[block];
    return text.str();
}

Turn inverse(Turn turn) {
    return static_cast<Turn>((layout::turn_count - static_cast<int>(turn)) % layout::turn_count);
}

std::string summary(const LabelSeating& seating) {
    std::ostringstream text;
    FaceCount all;
    for (const FaceCount& face : seating.faces) {
        all.beside += face.beside;
        all.apart += face.apart;
        all.hidden += face.hidden;
    }
    text << "reference labels: " << seating.seats.size() << " parts; " << all.beside << " seated beside their part, "
         << all.apart << " seated farther out, " << all.hidden << " hidden\n";
    for (const Face face : {Face::top, Face::bottom}) {
        const FaceCount& count = seating.on(face);
        text << "  " << face_name(face) << ": " << count.beside << " beside, " << count.apart << " farther out, "
             << count.hidden << " hidden\n";
    }
    for (const LabelSeat& seat : seating.seats)
        if (seat.seat == Seat::hidden)
            text << "  hidden " << seat.reference << " (" << face_name(seat.face) << "): " << seat.reason << "\n";
    return text.str();
}

}

Box label_extent(const std::string& reference, double height, bool upright) {
    std::size_t count = 0;
    for (const unsigned char byte : reference)
        if ((byte & continuation_mask) != continuation_bits) ++count;
    if (count == 0) throw LabelError("labels: a part has an empty reference");
    const Box4 flat = text_box(std::string(count, glyph), 0, 0, height, constants::label_margin.value);
    const Nm guard = static_cast<Nm>(constants::label_guard.value);
    const Nm wide = layout::ceil_nm(flat.x1) + guard, high = layout::ceil_nm(flat.y1) + guard;
    return upright ? Box{-high, -wide, high, wide} : Box{-wide, -high, wide, high};
}

LabelSeating seat_labels(const PcbModel& model, const PcbEmitPolicy& policy) {
    const Box board = box_of({model.origin_x, model.origin_y, model.origin_x + model.board_w,
                              model.origin_y + model.board_h});
    const Box outline = layout::grown(board, -static_cast<Nm>(constants::label_inset.value));
    std::array<Occupancy, face_count> faces;
    std::vector<Subject> subjects;
    std::map<std::string, std::size_t> known;
    for (std::size_t part = 0; part < model.insts.size(); ++part) {
        const PcbCheckInstance& instance = model.insts[part];
        if (!known.emplace(instance.ref, part).second)
            throw LabelError("labels: two parts share the reference " + instance.ref);
        subjects.push_back(subject_of(instance, policy));
        const Subject& subject = subjects.back();
        on(faces, subject.face).add(subject.court, Block::part, part);
        for (std::size_t pad = 0; pad < subject.pads; ++pad) {
            const Box box = pad_box(instance, subject, pad);
            on(faces, subject.face).add(box, Block::pad, part);
            if (drilled(instance, pad)) on(faces, layout::opposite(subject.face)).add(box, Block::pad, part);
        }
    }
    for (const PcbCheckCopper& copper : model.copper) {
        if (copper.kind != "via") continue;
        const Point centre{layout::nearest_nm(copper.x), layout::nearest_nm(copper.y)};
        const Nm reach = layout::ceil_nm(copper.size / 2);
        for (Occupancy& face : faces)
            face.add({centre.x - reach, centre.y - reach, centre.x + reach, centre.y + reach}, Block::pad,
                     model.insts.size());
    }
    for (const auto& body : {model.som_keepout, model.som_core})
        if (body) on(faces, Face::top).add(box_of(*body), Block::module, model.insts.size());
    if (model.som_core) on(faces, Face::top).add(title_box(*model.som_core), Block::mark, model.insts.size());

    std::vector<std::size_t> order(model.insts.size());
    std::iota(order.begin(), order.end(), std::size_t{0});
    std::sort(order.begin(), order.end(), [&](std::size_t a, std::size_t b) {
        if (subjects[a].interface != subjects[b].interface) return subjects[a].interface;
        if (subjects[a].pads != subjects[b].pads) return subjects[a].pads > subjects[b].pads;
        return model.insts[a].ref < model.insts[b].ref;
    });

    LabelSeating seating;
    seating.seats.resize(model.insts.size());
    for (const std::size_t part : order) {
        const Subject& subject = subjects[part];
        LabelSeat& seat = seating.seats[part];
        seat.reference = model.insts[part].ref;
        seat.face = subject.face;
        FaceCount& count = seating.faces[static_cast<std::size_t>(subject.face)];
        Tally tally;
        if (!subject.silk) {
            seat.reason = "its footprint draws no reference on the silk layer";
        } else if (seat_one(on(faces, subject.face), outline, subject, part, seat, tally)) {
            seat.local = layout::turned(Point{seat.centre.x - subject.at.x, seat.centre.y - subject.at.y},
                                        inverse(subject.turn));
            if (layout::placed(seat.local, subject.at, subject.turn) != seat.centre)
                throw LabelError("labels: the seat of " + seat.reference + " does not survive its part's rotation");
            on(faces, subject.face).add(seat.box, Block::label, part);
        } else {
            seat.reason = unseated(tally);
        }
        if (seat.seat == Seat::beside) ++count.beside;
        else if (seat.seat == Seat::apart) ++count.apart;
        else ++count.hidden;
    }
    seating.report = summary(seating);
    return seating;
}

}
