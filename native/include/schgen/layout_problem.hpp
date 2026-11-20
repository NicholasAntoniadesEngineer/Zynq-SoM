#pragma once

#include "schgen/layout_geometry.hpp"
#include "schgen/part_facts.hpp"

#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace schgen::layout {

inline constexpr int no_net = -1;

enum class Category : std::uint8_t { plane, power, signal };

struct PadShape {
    std::string name;
    Point centre;
    Box box;
    bool through = false;
    Nm radius = 0;
};

struct Variant {
    Box gate_box;
    std::vector<Box> court_boxes;
    std::vector<Disc> court_discs;
    std::vector<PadShape> pads;
    std::optional<Box> pad_hull;
    std::vector<std::string> names;
    std::vector<Box> name_boxes;
};

struct EdgeRule {
    Point mouth, rear_mouth;
    Nm reach = 0, seat = 0;
    Point mouth_on(Face face) const { return face == Face::top ? mouth : rear_mouth; }
};

struct CornerRule {
    bool east = false, south = false;
    Point inset;
    Nm grid = 0;
};

struct Footprint {
    std::string key;
    bool flippable = false;
    Variant top, bottom;
    const Variant& on(Face face) const { return face == Face::top ? top : bottom; }
};

struct Part {
    std::string reference, group, value, footprint_name;
    std::optional<PartClass> part_class;
    std::optional<Nm> height;
    std::size_t footprint = 0;
    std::vector<int> pad_nets;
    int fanout_pins = 0;
    Nm fanout_need = 0;
    std::array<bool, edge_count> escape_top{}, escape_bottom{};
    const std::array<bool, edge_count>& escape_on(Face face) const {
        return face == Face::top ? escape_top : escape_bottom;
    }
    bool fanout_subject = false, never_crowds = false, cluster_passive = false;
    bool fixed = false, top_only = false, core_exempt = false, cohesion_member = true;
    bool connector = false, overmold = false, module = false;
    bool field_source = false, field_sensitive = false;
    std::optional<EdgeRule> edge;
    std::optional<CornerRule> corner;
};

struct Pin {
    std::size_t part = 0, pad = 0;
};

struct Net {
    std::string name;
    Category category = Category::signal;
    Nm clearance = 0;
    std::vector<Pin> pins;
};

struct Board {
    Point origin;
    Nm width = 0, height = 0;
    std::optional<Box> module_core, module_body;
    Box outline() const { return {origin.x, origin.y, origin.x + width, origin.y + height}; }
};

struct Obstacle {
    Box box;
    std::optional<Disc> disc;
    bool top = false, bottom = false;
    int net = no_net;
};

enum class Sense : std::uint8_t { at_most, at_least };

enum class GroupMeasure : std::uint8_t { hull_gap, centre_distance };

struct PadGap {
    std::size_t anchor = 0, member = 0;
    std::vector<std::size_t> anchor_names;
    Nm limit = 0;
    Sense sense = Sense::at_most;
    std::string source;
    bool rigid = true, derived = false;
    Nm reach = 0;
    bool same_face = false, or_under = false, first = false;
};

struct NearestGap {
    std::size_t anchor = 0;
    std::vector<std::size_t> anchor_names, members;
    Nm limit = 0;
    bool same_face = false;
    std::string source;
};

struct FacePair {
    std::size_t first = 0, second = 0;
    std::string source;
    bool or_under = false;
};

struct NetOrder {
    std::size_t anchor = 0, lead = 0;
    std::vector<std::size_t> anchor_names;
    int net = no_net;
    std::vector<std::size_t> rivals;
    std::string source;
};

struct GroupGap {
    std::string first, second;
    bool second_is_core = false;
    GroupMeasure measure = GroupMeasure::hull_gap;
    Nm limit = 0;
    Sense sense = Sense::at_most;
    std::string source;
};

struct ConnectorRules {
    Nm overlap_slack = 0, overmold_gap = 0, boot_gap = 0;
    double band_share = 0;
};

enum class Tie : std::uint8_t { none, contract, authored, released, signal, rail, shared, bridge, unattached };

struct Ownership {
    Tie tie = Tie::none;
    std::optional<std::size_t> owner;
};

struct Constraints {
    std::vector<PadGap> pad_gaps, soft_gaps;
    std::vector<NearestGap> nearest_gaps;
    std::vector<FacePair> face_pairs;
    std::vector<NetOrder> net_orders;
    std::vector<GroupGap> group_gaps;
    ConnectorRules connectors;
};

struct PourRule {
    std::size_t owner = 0;
    std::array<double, 4> local{};
    double edge_back = 0;
    bool mirror = false;
};

struct Reserve {
    Box box;
    std::vector<std::size_t> members;
    std::string source;
    bool top = true, bottom = true;
    std::optional<PourRule> pour = std::nullopt;
    std::vector<std::size_t> guests = {};
};

struct Rules {
    Nm compare_guard = 0, group_guard = 0;
    Nm module_clearance = 0, module_stack_height = 0, tall_module_clearance = 0, copper_clearance = 0, edge_clearance = 0, edge_setback = 0, plane_margin = 0;
    double dispersion_limit = 0;
    std::size_t dispersion_floor = 0;
};

struct Pose {
    Point at;
    Turn turn = Turn::none;
    Face face = Face::top;
};

constexpr bool operator==(const Pose& a, const Pose& b) {
    return a.at == b.at && a.turn == b.turn && a.face == b.face;
}
constexpr bool operator!=(const Pose& a, const Pose& b) { return !(a == b); }

using Placement = std::vector<Pose>;

struct Problem {
    Board board;
    Rules rules;
    std::vector<Footprint> footprints;
    std::vector<Part> parts;
    std::vector<Net> nets;
    std::vector<Obstacle> obstacles;
    std::vector<Reserve> reserves;
    Constraints constraints;
    std::vector<Ownership> ownership;
};

inline bool counts_as_crowder(const Part& crowder, const Part& subject) {
    return !crowder.never_crowds && !(crowder.cluster_passive && crowder.group == subject.group);
}
Point corner_site(const Board& board, const CornerRule& rule);
std::optional<bool> mirrors_across_x(const Footprint& footprint);
Box gate_at(const Problem& problem, std::size_t part, const Pose& pose);
Box pour_box(const PourRule& rule, const Pose& owner, const Board& board);
bool pair_faced(const Problem& problem, const Board& board, std::size_t owner, const Pose& owner_pose,
                std::size_t member, const Pose& member_pose, bool or_under);
Box hull_at(const Problem& problem, const Placement& placement, const std::vector<std::size_t>& parts);
void index_names(Variant& variant);
struct HoldPolicy {
    Nm owner_reach = 0, hold_slack = 0, tether_slack = 0;
};
struct Claim {
    std::size_t part = 0, owner = 0;
    std::vector<std::size_t> names;
    Nm reach = 0;
    std::string role;
    bool same_face = false, or_under = false, first = false;
};
struct Intent {
    std::vector<Claim> claims;
    std::vector<std::size_t> released;
};
Nm squared_pad_gap(const Problem& problem, const PadGap& rule, const Pose& anchor, const Pose& member);
Nm pad_gap_length(const Problem& problem, const PadGap& rule, const Placement& placement);
Nm squared_net_gap(const Problem& problem, std::size_t anchor, const Pose& anchor_pose,
                   const std::vector<std::size_t>& names, std::size_t member, const Pose& member_pose, int net);
std::optional<NetOrder> net_order_of(const Problem& problem, const PadGap& claim);
std::vector<NetOrder> net_orders_of(const Problem& problem);
Nm rival_bound(const Problem& problem, const NetOrder& rule, const Placement& placement);
bool net_order_met(const Problem& problem, const NetOrder& rule, const Placement& placement, std::size_t moved,
                   const Pose* pose);
void derive_ownership(Problem& problem, const Placement& placement, const HoldPolicy& policy, const Intent& intent);
void tighten_holds(Problem& problem, const Placement& placement, const HoldPolicy& policy);
const char* tie_name(Tie tie);

void validate(const Problem& problem, const Placement& placement);

}
