#pragma once

#include "schgen/layout_geometry.hpp"
#include "schgen/pcb_emit.hpp"

#include <array>
#include <string>
#include <vector>

namespace schgen::labels {

class LabelError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

namespace constants {
inline constexpr NamedConstant label_height{"label_height", 1.0, "mm", "policy",
    "preferred character height, the project's default silk text size; the fabricator's minimum text height raises it when larger"};
inline constexpr NamedConstant label_margin{"label_margin", 0.15, "mm", "policy",
    "clear band kept around a label, the band the silk overlap gate measures"};
inline constexpr NamedConstant label_guard{"label_guard", 1e3, "nm", "policy",
    "slack added to each label half-extent so the gate's floating-point boxes cannot touch at the limit"};
inline constexpr NamedConstant label_inset{"label_inset", 0.25e6, "nm", "policy",
    "distance kept between a label's clear band and the board edge"};
inline constexpr NamedConstant label_step{"label_step", 0.5e6, "nm", "policy",
    "pitch of the outward and sideways search for a seat"};
inline constexpr NamedConstant label_reach{"label_reach", 3e6, "nm", "policy",
    "farthest a label may sit from its part's courtyard and still read as that part's"};
inline constexpr NamedConstant title_indent{"title_indent", 1.0, "mm", "policy",
    "distance of the module title's left end from the module's left edge"};
inline constexpr NamedConstant title_rise{"title_rise", 1.2, "mm", "policy",
    "distance of the module title's baseline above the module's top edge"};
inline constexpr NamedConstant title_height{"title_height", 1.4, "mm", "policy",
    "character height of the module title"};
inline constexpr std::array label_registry{label_height, label_margin, label_guard, label_inset,
                                           label_step, label_reach, title_indent, title_rise, title_height};
}

inline constexpr const char* module_title = "Zynq SoM";
inline constexpr std::size_t face_count = 2;

enum class Seat : std::uint8_t { beside, apart, hidden };

struct LabelSeat {
    std::string reference;
    layout::Face face = layout::Face::top;
    Seat seat = Seat::hidden;
    layout::Point centre, local;
    layout::Box box;
    bool upright = false;
    double height = 0;
    std::string reason;
};

struct FaceCount {
    std::size_t beside = 0, apart = 0, hidden = 0;
};

struct LabelSeating {
    std::vector<LabelSeat> seats;
    std::array<FaceCount, face_count> faces;
    std::string report;
    const FaceCount& on(layout::Face face) const { return faces[static_cast<std::size_t>(face)]; }
};

layout::Box label_extent(const std::string& reference, double height, bool upright);
LabelSeating seat_labels(const PcbModel& model, const PcbEmitPolicy& policy);

}
