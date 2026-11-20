#include "schgen/label_seats.hpp"

#include "schgen/pcb_checks.hpp"
#include "schgen/pcb_scan.hpp"
#include "schgen/run_config.hpp"
#include "schgen/sexpr.hpp"

#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <string>

namespace {

using namespace schgen;
using namespace schgen::labels;
using layout::Box;
using layout::Face;
using layout::Nm;
using layout::Point;

namespace expected {
constexpr double board_origin = 25, wide_board = 40, part_x = 45, part_y = 45;
constexpr double tight_width = 3.4, tight_height = 2.0, tight_x = 26.7, tight_y = 26.0;
constexpr Box chip_court{-1500000, -800000, 1500000, 800000};
constexpr Box chip_pad{-450000, -475000, 450000, 475000};
constexpr Nm chip_pad_offset = 800000;
constexpr double row_pitch = 3.2, row_start = 31;
constexpr std::size_t row_parts = 8;
constexpr double post_x = 45, post_y = 43.25;
constexpr Box post_pad{-1000000, -1000000, 1000000, 1000000};
constexpr double quarter = 90, half = 180;
constexpr double via_size = 0.6, via_drill = 0.3;
constexpr double text_default = 1;
constexpr Nm centre_tolerance = 1;
}

const char* chip_text = R"((footprint "fixture:chip" (layer "F.Cu")
  (property "Reference" "REF**" (at 0 -1.6 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
  (property "Value" "chip" (at 0 1.6 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
  (fp_rect (start -1.5 -0.8) (end 1.5 0.8) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))
  (pad "1" smd rect (at -0.8 0) (size 0.9 0.95) (layers "F.Cu" "F.Paste" "F.Mask"))
  (pad "2" smd rect (at 0.8 0) (size 0.9 0.95) (layers "F.Cu" "F.Paste" "F.Mask"))))";

const char* post_text = R"((footprint "fixture:post" (layer "F.Cu")
  (property "Reference" "REF**" (at 0 -2 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
  (property "Value" "post" (at 0 2 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
  (fp_rect (start -1.2 -1.2) (end 1.2 1.2) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))
  (pad "1" thru_hole circle (at 0 0) (size 2 2) (drill 1) (layers "*.Cu" "*.Mask"))))";

const char* bare_text = R"((footprint "fixture:bare" (layer "F.Cu")
  (property "Reference" "REF**" (at 0 -1.6 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
  (fp_rect (start -1.5 -0.8) (end 1.5 0.8) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))
  (pad "1" smd rect (at 0 0) (size 0.9 0.95) (layers "F.Cu" "F.Paste" "F.Mask"))))";

void require(bool condition, const std::string& what) {
    if (!condition) throw std::runtime_error("label seat contract failed: " + what);
}

PcbModel board(double width, double height) {
    PcbModel model;
    model.origin_x = expected::board_origin;
    model.origin_y = expected::board_origin;
    model.board_w = width;
    model.board_h = height;
    return model;
}

void add(PcbModel& model, const std::string& reference, const char* text, const std::string& name, double x, double y,
         double rotation, const std::string& side) {
    PcbFootprintInst part;
    part.ref = reference;
    part.value = name;
    part.footprint = name;
    part.side = side;
    part.x = x;
    part.y = y;
    part.rotation = rotation;
    part.mod = pcb_check_footprint(name, text);
    model.insts.push_back(std::move(part));
}

Box court_of(const PcbCheckInstance& part, Box local) {
    return layout::placed(local, {layout::to_nm(part.x), layout::to_nm(part.y)}, layout::turn_of(part.rotation));
}

std::vector<Box> chip_pads(const PcbCheckInstance& part) {
    std::vector<Box> pads;
    for (const Nm offset : {-expected::chip_pad_offset, expected::chip_pad_offset})
        pads.push_back(court_of(part, layout::shifted(expected::chip_pad, Point{offset, 0})));
    return pads;
}

void a_free_part_is_labelled_beside_itself() {
    PcbModel model = board(expected::wide_board, expected::wide_board);
    add(model, "R1", chip_text, "fixture:chip", expected::part_x, expected::part_y, 0, "top");
    const LabelSeating seating = seat_labels(model, default_pcb_emit_policy());
    const LabelSeat& seat = seating.seats.front();
    const Box court = court_of(model.insts.front(), expected::chip_court);
    require(seating.seats.size() == 1 && seat.reference == "R1" && seat.seat == Seat::beside, "a free part is seated beside");
    require(!seat.upright && seat.height == constants::label_height.value, "the first seat is flat at the preferred height");
    require(seat.box.y1 == court.y0 && seat.centre.x == (court.x0 + court.x1) / 2, "the first seat is centred above the part");
    require(!layout::overlaps(seat.box, court), "a label stays off its own part");
    require(seat.box == layout::shifted(label_extent("R1", seat.height, false), seat.centre), "the seat claims its own extent");
    require(seating.on(Face::top).beside == 1 && seating.on(Face::top).hidden == 0 && seating.on(Face::bottom).beside == 0,
            "the face tally counts the seat");
    require(seating.report.find("1 seated beside their part") != std::string::npos, "the report counts the seat");
}

void a_part_with_no_room_is_hidden_and_reported() {
    PcbModel model = board(expected::tight_width, expected::tight_height);
    add(model, "R1", chip_text, "fixture:chip", expected::tight_x, expected::tight_y, 0, "top");
    add(model, "R2", bare_text, "fixture:bare", expected::tight_x, expected::tight_y, 0, "bottom");
    const LabelSeating seating = seat_labels(model, default_pcb_emit_policy());
    const LabelSeat& crowded = seating.seats[0];
    const LabelSeat& silent = seating.seats[1];
    require(crowded.seat == Seat::hidden && crowded.reason.find("off the board") != std::string::npos,
            "a part with no room has its label hidden with the reason");
    require(silent.seat == Seat::hidden && silent.reason.find("no reference on the silk layer") != std::string::npos,
            "a footprint without a silk reference is hidden with the reason");
    require(seating.on(Face::top).hidden == 1 && seating.on(Face::bottom).hidden == 1, "hidden labels are tallied per face");
    require(seating.report.find("hidden R1 (top)") != std::string::npos &&
                seating.report.find("hidden R2 (bottom)") != std::string::npos,
            "the report lists every hidden label");
    const PcbEmissionResult emitted = render_pcb(model, default_pcb_emit_policy(), nullptr, &seating);
    require(collect_refdes_props(emitted.document, expected::text_default).empty(), "hidden labels are hidden on the silk");
}

void a_label_never_covers_a_pad_or_a_drill() {
    PcbModel model = board(expected::wide_board, expected::wide_board);
    add(model, "R1", chip_text, "fixture:chip", expected::part_x, expected::part_y, 0, "top");
    add(model, "J1", post_text, "fixture:post", expected::post_x, expected::post_y, 0, "bottom");
    const LabelSeating seating = seat_labels(model, default_pcb_emit_policy());
    const Box drill = court_of(model.insts[1], expected::post_pad);
    const Box above = layout::shifted(label_extent("R1", constants::label_height.value, false),
                                      Point{layout::to_nm(expected::part_x),
                                            court_of(model.insts[0], expected::chip_court).y0 -
                                                label_extent("R1", constants::label_height.value, false).y1});
    require(layout::overlaps(above, drill), "the fixture drill covers the first seat");
    for (const LabelSeat& seat : seating.seats) {
        require(seat.seat != Seat::hidden, "both labels find a seat");
        require(!layout::overlaps(seat.box, drill), "no label covers a drill on either face");
        for (const Box& pad : chip_pads(model.insts[0]))
            require(seat.face == Face::bottom || !layout::overlaps(seat.box, pad), "no label covers a pad on its face");
    }
    require(seating.seats[0].box != above, "the covered seat is passed over");
}

void a_label_never_covers_a_via() {
    PcbModel model = board(expected::wide_board, expected::wide_board);
    add(model, "R1", chip_text, "fixture:chip", expected::part_x, expected::part_y, 0, "top");
    const Box court = court_of(model.insts.front(), expected::chip_court);
    const Box extent = label_extent("R1", constants::label_height.value, false);
    const Box above = layout::shifted(extent, Point{layout::to_nm(expected::part_x), court.y0 - extent.y1});
    PcbCheckCopper via;
    via.kind = "via";
    via.x = expected::part_x;
    via.y = layout::to_mm((above.y0 + above.y1) / 2);
    via.size = expected::via_size;
    via.drill = expected::via_drill;
    model.copper.push_back(via);
    const Nm reach = layout::ceil_nm(via.size / 2);
    const Point where{layout::nearest_nm(via.x), layout::nearest_nm(via.y)};
    const Box barrel{where.x - reach, where.y - reach, where.x + reach, where.y + reach};
    require(layout::overlaps(above, barrel), "the fixture via covers the first seat");
    const LabelSeating seating = seat_labels(model, default_pcb_emit_policy());
    require(seating.seats.front().seat != Seat::hidden, "the label finds a seat past the via");
    require(!layout::overlaps(seating.seats.front().box, barrel), "no label covers a via");
    require(seating.seats.front().box != above, "the seat over the via is passed over");
}

void crowded_labels_keep_apart_and_pass_the_gate() {
    PcbModel model = board(expected::wide_board, expected::wide_board);
    for (std::size_t index = 0; index < expected::row_parts; ++index) {
        const double rotation = index % 2 == 0 ? 0 : expected::quarter;
        add(model, "C" + std::to_string(index + 1), chip_text, "fixture:chip",
            expected::row_start + expected::row_pitch * static_cast<double>(index), expected::part_y, rotation,
            index % 2 == 0 ? "top" : "bottom");
        add(model, "R" + std::to_string(index + 1), chip_text, "fixture:chip",
            expected::row_start + expected::row_pitch * static_cast<double>(index), expected::part_y, expected::half,
            index % 2 == 0 ? "bottom" : "top");
    }
    const LabelSeating seating = seat_labels(model, default_pcb_emit_policy());
    std::size_t seated = 0, top = 0;
    for (std::size_t first = 0; first < seating.seats.size(); ++first) {
        const LabelSeat& seat = seating.seats[first];
        if (seat.seat == Seat::hidden) continue;
        ++seated;
        if (seat.face == Face::top) ++top;
        for (std::size_t second = 0; second < seating.seats.size(); ++second) {
            const LabelSeat& other = seating.seats[second];
            if (model.insts[second].side == model.insts[first].side) {
                require(!layout::overlaps(seat.box, court_of(model.insts[second], expected::chip_court)),
                        "no label covers a part on its face");
                for (const Box& pad : chip_pads(model.insts[second]))
                    require(!layout::overlaps(seat.box, pad), "no label covers a pad in the row");
            }
            if (second != first && other.seat != Seat::hidden && other.face == seat.face)
                require(!layout::overlaps(seat.box, other.box), "no two labels on a face overlap");
        }
    }
    require(seated != 0, "the row seats labels");
    const PcbEmissionResult emitted = render_pcb(model, default_pcb_emit_policy(), nullptr, &seating);
    const RefdesOverlapResult gate = check_refdes_overlap(emitted.document, true);
    require(gate.ok && gate.top_pairs.empty() && gate.bottom_pairs == 0, "the silk overlap gate passes on seated labels");
    require(static_cast<std::size_t>(gate.n_top + gate.n_bottom) == seated && static_cast<std::size_t>(gate.n_top) == top,
            "the gate sees every seated label on its own face");
    const PcbEmissionResult plain = render_pcb(model, default_pcb_emit_policy());
    const auto poses = [](const Sexpr& document) {
        std::vector<std::string> out;
        for (const Sexpr& node : std::get<SexprList>(document.v)) {
            const auto* footprint = std::get_if<SexprList>(&node.v);
            if (!footprint || footprint->empty() || !std::holds_alternative<Sexpr::Sym>(footprint->front().v) ||
                std::get<Sexpr::Sym>(footprint->front().v).name != "footprint")
                continue;
            for (const Sexpr& field : *footprint) {
                const auto* at = std::get_if<SexprList>(&field.v);
                if (at && !at->empty() && std::holds_alternative<Sexpr::Sym>(at->front().v) &&
                    std::get<Sexpr::Sym>(at->front().v).name == "at")
                    out.push_back(sexpr_dumps(field));
            }
        }
        return out;
    };
    require(poses(plain.document) == poses(emitted.document) && !poses(plain.document).empty(),
            "seating labels moves no part");
    for (const RefdesProp& shown : collect_refdes_props(emitted.document, expected::text_default)) {
        const auto found = std::find_if(seating.seats.begin(), seating.seats.end(),
                                        [&](const LabelSeat& seat) { return seat.reference == shown.ref; });
        require(found != seating.seats.end() && found->seat != Seat::hidden, "only seated labels are shown");
        const double x = shown.fp_x + shown.local_x * shown.cos_a + shown.local_y * shown.sin_a;
        const double y = shown.fp_y - shown.local_x * shown.sin_a + shown.local_y * shown.cos_a;
        require(std::llabs(layout::nearest_nm(x) - found->centre.x) <= expected::centre_tolerance &&
                    std::llabs(layout::nearest_nm(y) - found->centre.y) <= expected::centre_tolerance,
                "an emitted label lands on its seat whatever its part's rotation");
        require(shown.size == found->height, "an emitted label has its seated height");
    }
}

void seats_are_repeatable() {
    PcbModel model = board(expected::wide_board, expected::wide_board);
    for (std::size_t index = 0; index < expected::row_parts; ++index)
        add(model, "C" + std::to_string(index + 1), chip_text, "fixture:chip",
            expected::row_start + expected::row_pitch * static_cast<double>(index), expected::part_y, 0, "top");
    const LabelSeating first = seat_labels(model, default_pcb_emit_policy());
    const LabelSeating second = seat_labels(model, default_pcb_emit_policy());
    require(first.report == second.report, "two seatings report the same");
    for (std::size_t index = 0; index < first.seats.size(); ++index)
        require(first.seats[index].centre == second.seats[index].centre &&
                    first.seats[index].seat == second.seats[index].seat,
                "two seatings agree exactly");
    add(model, "C1", chip_text, "fixture:chip", expected::part_x, expected::part_x, 0, "top");
    try {
        seat_labels(model, default_pcb_emit_policy());
    } catch (const LabelError&) {
        return;
    }
    throw std::runtime_error("label seat contract failed: accepted two parts with one reference");
}

}

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: label_seats_contracts REPOSITORY");
        apply_run_config(std::filesystem::path(argv[1]) / run_config_file, "devkit_mini");
        a_free_part_is_labelled_beside_itself();
        a_part_with_no_room_is_hidden_and_reported();
        a_label_never_covers_a_pad_or_a_drill();
        a_label_never_covers_a_via();
        crowded_labels_keep_apart_and_pass_the_gate();
        seats_are_repeatable();
        std::cout << "label seat contracts ok\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 1;
    }
}
