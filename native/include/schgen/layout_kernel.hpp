#pragma once

#include "schgen/layout_problem.hpp"

#include <map>
#include <unordered_map>

namespace schgen::layout {

namespace constants {
inline constexpr NamedConstant hash_cell{"hash_cell", 4e6, "nm", "policy",
    "edge length of one spatial-hash cell"};
inline constexpr NamedConstant key_shift{"key_shift", 32.0, "bits", "standard",
    "bits given to each axis in a spatial-hash key"};
inline constexpr std::array kernel_registry{hash_cell, key_shift};
}

enum class Breach : std::uint8_t {
    overlap, off_board, fanout, module_core, bottom_face, dispersion, copper, contract, group_bound,
    edge_mount, connector_gap, reserved, locked
};

struct Violation {
    Breach kind = Breach::overlap;
    std::size_t part = 0, other = 0;
};

struct Margin {
    std::string kind, source;
    double value = 0;
};

struct Wirelength {
    Nm plane = 0, power = 0, signal = 0;
};

const char* breach_name(Breach breach);

class Kernel {
public:
    Kernel(const Problem& problem, Placement placement);
    const Problem& problem() const { return problem_; }
    const Placement& placement() const { return placement_; }
    std::vector<Violation> violations() const;
    std::optional<Violation> rejection(std::size_t part, const Pose& pose) const;
    bool move(std::size_t part, const Pose& pose);
    Nm routed_length() const { return routed_; }
    Wirelength measured_wirelength() const;
    void verify() const;
    std::vector<Margin> margins() const;

private:
    struct Land {
        Box box;
        int net = no_net;
        bool through = false;
        Disc disc;
    };
    struct Shape {
        Box gate, bound;
        std::vector<Land> lands;
        std::vector<Box> named;
        std::vector<Box> courts, holes;
        std::vector<Disc> discs;
        std::optional<Box> pads;
    };
    struct GroupSummary {
        std::optional<Box> hull;
        double x = 0, y = 0, count = 0;
    };
    using Key = std::uint64_t;

    Shape shape_of(std::size_t part, const Pose& pose) const;
    Nm net_length(std::size_t net, std::size_t moved, const Pose* pose) const;
    std::vector<std::size_t> routed_nets(std::size_t part) const;
    std::vector<Key> keys_of(Box box) const;
    std::vector<std::size_t> neighbours(Box box, std::size_t self) const;
    std::optional<Breach> self_breach(std::size_t part, const Shape& shape, const Pose& pose) const;
    std::optional<Breach> pair_breach(std::size_t first, const Shape& first_shape, Face first_face,
                                      std::size_t second, const Shape& second_shape, Face second_face) const;
    bool crowds(const Part& crowder, const Part& subject) const;
    bool copper_clear(const Shape& shape, Face face) const;
    Nm land_clearance(int net) const;
    bool lands_clear(const Shape& first, Face first_face, const Shape& second, Face second_face) const;
    bool group_dispersed(const std::string& group, std::size_t moved, const Shape* shape) const;
    Nm named_gap(const Shape& anchor, const std::vector<std::size_t>& names, const Shape& member) const;
    bool pad_gap_met(const PadGap& rule, const Shape& anchor, const Shape& member, Nm guard) const;
    bool nearest_met(const NearestGap& rule, std::size_t moved, const Shape* shape, const Pose* pose, Nm guard) const;
    bool group_gap_met(const GroupGap& rule, std::size_t moved, const Shape* shape, const Pose* pose, Nm guard) const;
    GroupSummary summarise(const GroupGap& rule, bool second, std::size_t moved, const Shape* shape,
                           const Pose* pose) const;
    std::optional<double> group_distance(const GroupGap& rule, std::size_t moved, const Shape* shape,
                                         const Pose* pose) const;
    bool edge_met(const Part& item, const Shape& shape, const Pose& pose) const;
    bool connectors_met(std::size_t part, const Shape& shape, std::size_t other, const Shape& other_shape, Nm guard) const;
    std::optional<Breach> rule_breach(std::size_t part, const Shape& shape, const Pose& pose, Nm guard,
                                      std::size_t* other) const;
    void insert(std::size_t part);
    void remove(std::size_t part);

    const Problem& problem_;
    Placement placement_;
    std::vector<Shape> shapes_;
    std::unordered_map<Key, std::vector<std::size_t>> cells_;
    std::map<std::string, std::vector<std::size_t>> groups_, members_;
    std::map<std::string, std::vector<std::size_t>> group_rules_;
    std::vector<std::vector<std::size_t>> pad_rules_, nearest_rules_, face_rules_;
    std::vector<std::size_t> connectors_;
    std::vector<Nm> net_lengths_;
    Nm routed_ = 0, reach_ = 0;
};

}
