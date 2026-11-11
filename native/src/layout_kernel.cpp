#include "schgen/layout_kernel.hpp"

#include <algorithm>
#include <limits>

namespace schgen::layout {
namespace {

Nm cell_of(Nm coordinate) {
    const Nm cell = static_cast<Nm>(constants::hash_cell.value);
    const Nm quotient = coordinate / cell;
    return coordinate % cell < 0 ? quotient - 1 : quotient;
}

std::uint64_t key_of(Nm column, Nm row) {
    const auto shift = static_cast<unsigned>(constants::key_shift.value);
    return (static_cast<std::uint64_t>(static_cast<std::uint32_t>(column)) << shift) |
           static_cast<std::uint64_t>(static_cast<std::uint32_t>(row));
}

bool courts_overlap(const std::vector<Box>& boxes, const std::vector<Disc>& discs,
                    const std::vector<Box>& other_boxes, const std::vector<Disc>& other_discs) {
    for (const auto& box : boxes) {
        for (const auto& other : other_boxes)
            if (overlaps(box, other)) return true;
        for (const auto& other : other_discs)
            if (overlaps(box, other)) return true;
    }
    for (const auto& disc : discs) {
        for (const auto& other : other_boxes)
            if (overlaps(other, disc)) return true;
        for (const auto& other : other_discs)
            if (overlaps(disc, other)) return true;
    }
    return false;
}

double area_of(Box box) {
    return static_cast<double>(box.width()) * static_cast<double>(box.height());
}

}

const char* breach_name(Breach breach) {
    switch (breach) {
    case Breach::overlap: return "overlap";
    case Breach::off_board: return "off_board";
    case Breach::fanout: return "fanout";
    case Breach::module_core: return "module_core";
    case Breach::bottom_face: return "bottom_face";
    case Breach::dispersion: return "dispersion";
    case Breach::copper: return "copper";
    case Breach::locked: return "locked";
    }
    return "unknown";
}

Kernel::Kernel(const Problem& problem, Placement placement)
    : problem_(problem), placement_(std::move(placement)) {
    validate(problem_, placement_);
    for (const auto& part : problem_.parts)
        if (part.fanout_subject) reach_ = std::max(reach_, part.fanout_need);
    shapes_.reserve(placement_.size());
    for (std::size_t part = 0; part < placement_.size(); ++part) {
        shapes_.push_back(shape_of(part, placement_[part]));
        insert(part);
        if (problem_.parts[part].cohesion_member) groups_[problem_.parts[part].group].push_back(part);
    }
    net_lengths_.assign(problem_.nets.size(), 0);
    for (std::size_t net = 0; net < problem_.nets.size(); ++net) {
        if (problem_.nets[net].category == Category::plane) continue;
        net_lengths_[net] = net_length(net, placement_.size(), nullptr);
        routed_ += net_lengths_[net];
    }
}

Kernel::Shape Kernel::shape_of(std::size_t part, const Pose& pose) const {
    const Variant& variant = problem_.footprints[problem_.parts[part].footprint].on(pose.face);
    Shape shape;
    shape.gate = placed(variant.gate_box, pose.at, pose.turn);
    shape.bound = shape.gate;
    for (const auto& box : variant.court_boxes) shape.courts.push_back(placed(box, pose.at, pose.turn));
    for (const auto& disc : variant.court_discs) shape.discs.push_back(placed(disc, pose.at, pose.turn));
    const auto& nets = problem_.parts[part].pad_nets;
    for (std::size_t pad = 0; pad < variant.pads.size(); ++pad) {
        const Box box = placed(variant.pads[pad].box, pose.at, pose.turn);
        shape.lands.push_back({box, nets[pad], variant.pads[pad].through,
                               {placed(variant.pads[pad].centre, pose.at, pose.turn), variant.pads[pad].radius}});
        if (variant.pads[pad].through) shape.holes.push_back(box);
    }
    if (variant.pad_hull) {
        shape.pads = placed(*variant.pad_hull, pose.at, pose.turn);
        shape.bound = united(shape.bound, *shape.pads);
    }
    return shape;
}

Nm Kernel::net_length(std::size_t net, std::size_t moved, const Pose* pose) const {
    const auto& pins = problem_.nets[net].pins;
    const std::size_t count = pins.size();
    if (count < 2) return 0;
    std::vector<Point> points;
    points.reserve(count);
    for (const auto& pin : pins) {
        const Pose& at = pose && pin.part == moved ? *pose : placement_[pin.part];
        const Variant& variant = problem_.footprints[problem_.parts[pin.part].footprint].on(at.face);
        points.push_back(placed(variant.pads[pin.pad].centre, at.at, at.turn));
    }
    std::vector<Nm> best(count, std::numeric_limits<Nm>::max());
    std::vector<char> used(count, 0);
    best.front() = 0;
    Nm total = 0;
    for (std::size_t step = 0; step < count; ++step) {
        std::size_t pick = count;
        for (std::size_t index = 0; index < count; ++index)
            if (!used[index] && (pick == count || best[index] < best[pick])) pick = index;
        used[pick] = 1;
        total += best[pick];
        for (std::size_t index = 0; index < count; ++index) {
            if (used[index]) continue;
            const Nm dx = points[pick].x - points[index].x, dy = points[pick].y - points[index].y;
            const Nm length = (dx < 0 ? -dx : dx) + (dy < 0 ? -dy : dy);
            best[index] = std::min(best[index], length);
        }
    }
    return total;
}

std::vector<std::size_t> Kernel::routed_nets(std::size_t part) const {
    std::vector<std::size_t> nets;
    for (const int net : problem_.parts[part].pad_nets)
        if (net != no_net && problem_.nets[static_cast<std::size_t>(net)].category != Category::plane)
            nets.push_back(static_cast<std::size_t>(net));
    std::sort(nets.begin(), nets.end());
    nets.erase(std::unique(nets.begin(), nets.end()), nets.end());
    return nets;
}

std::vector<Kernel::Key> Kernel::keys_of(Box box) const {
    std::vector<Key> keys;
    for (Nm column = cell_of(box.x0); column <= cell_of(box.x1); ++column)
        for (Nm row = cell_of(box.y0); row <= cell_of(box.y1); ++row) keys.push_back(key_of(column, row));
    return keys;
}

void Kernel::insert(std::size_t part) {
    for (const Key key : keys_of(shapes_[part].bound)) cells_[key].push_back(part);
}

void Kernel::remove(std::size_t part) {
    for (const Key key : keys_of(shapes_[part].bound)) {
        auto& members = cells_[key];
        members.erase(std::remove(members.begin(), members.end(), part), members.end());
        if (members.empty()) cells_.erase(key);
    }
}

std::vector<std::size_t> Kernel::neighbours(Box box, std::size_t self) const {
    std::vector<std::size_t> found;
    for (const Key key : keys_of(grown(box, reach_))) {
        const auto cell = cells_.find(key);
        if (cell == cells_.end()) continue;
        for (const std::size_t part : cell->second)
            if (part != self) found.push_back(part);
    }
    std::sort(found.begin(), found.end());
    found.erase(std::unique(found.begin(), found.end()), found.end());
    return found;
}

bool Kernel::crowds(const Part& crowder, const Part& subject) const {
    return !crowder.never_crowds && !(crowder.cluster_passive && crowder.group == subject.group);
}

bool Kernel::copper_clear(const Shape& shape, Face face) const {
    const Nm need = problem_.rules.copper_clearance;
    for (const auto& obstacle : problem_.obstacles) {
        if (!gap_at_least(shape.bound, obstacle.box, need + 1)) {
            for (const auto& land : shape.lands) {
                const bool shares = land.through || (face == Face::top ? obstacle.top : obstacle.bottom);
                if (!shares || (land.net != no_net && land.net == obstacle.net)) continue;
                const bool clear = obstacle.disc ? gap_at_least(land.box, *obstacle.disc, need)
                                                 : gap_at_least(land.box, obstacle.box, need);
                if (!clear) return false;
            }
        }
    }
    return true;
}

Nm Kernel::land_clearance(int net) const {
    return net == no_net ? problem_.rules.copper_clearance : problem_.nets[static_cast<std::size_t>(net)].clearance;
}

bool Kernel::lands_clear(const Shape& first, Face first_face, const Shape& second, Face second_face) const {
    if (gap_at_least(first.bound, second.bound, problem_.rules.copper_clearance)) return true;
    for (const auto& a : first.lands)
        for (const auto& b : second.lands) {
            if (first_face != second_face && !a.through && !b.through) continue;
            if (a.net != no_net && a.net == b.net) continue;
            const Nm need = std::max(land_clearance(a.net), land_clearance(b.net));
            const bool apart = a.disc.radius > 0 && b.disc.radius > 0 ? gap_at_least(a.disc, b.disc, need)
                               : a.disc.radius > 0                    ? gap_at_least(b.box, a.disc, need)
                               : b.disc.radius > 0                    ? gap_at_least(a.box, b.disc, need)
                                                                      : gap_at_least(a.box, b.box, need);
            if (!apart) return false;
        }
    return true;
}

std::optional<Breach> Kernel::self_breach(std::size_t part, const Shape& shape, const Pose& pose) const {
    const Part& item = problem_.parts[part];
    if (shape.pads && !inside(*shape.pads, grown(problem_.board.outline(), -problem_.rules.edge_clearance)))
        return Breach::off_board;
    if (!item.fixed && !copper_clear(shape, pose.face)) return Breach::copper;
    if (!item.fixed && problem_.rules.plane_margin > 0) {
        const Box relief = grown(problem_.board.outline(), -problem_.rules.plane_margin);
        for (const auto& land : shape.lands)
            if (land.through && land.net != no_net &&
                problem_.nets[static_cast<std::size_t>(land.net)].category == Category::plane &&
                !inside(land.box, relief))
                return Breach::off_board;
    }
    if (pose.face == Face::bottom && item.top_only) return Breach::bottom_face;
    if (problem_.board.module_core && pose.face == Face::top && !item.core_exempt &&
        overlap_area(shape.gate, *problem_.board.module_core) > problem_.rules.core_tolerance)
        return Breach::module_core;
    return std::nullopt;
}

std::optional<Breach> Kernel::pair_breach(std::size_t first, const Shape& first_shape, Face first_face,
                                          std::size_t second, const Shape& second_shape,
                                          Face second_face) const {
    if (first_face != second_face) {
        if (courts_overlap(first_shape.holes, {}, second_shape.courts, second_shape.discs) ||
            courts_overlap(second_shape.holes, {}, first_shape.courts, first_shape.discs))
            return Breach::overlap;
        if (!lands_clear(first_shape, first_face, second_shape, second_face)) return Breach::copper;
        return std::nullopt;
    }
    if (courts_overlap(first_shape.courts, first_shape.discs, second_shape.courts, second_shape.discs))
        return Breach::overlap;
    if (!lands_clear(first_shape, first_face, second_shape, second_face)) return Breach::copper;
    const Part& a = problem_.parts[first];
    const Part& b = problem_.parts[second];
    if (a.fanout_subject && crowds(b, a) &&
        !gap_at_least(first_shape.gate, second_shape.gate, a.fanout_need))
        return Breach::fanout;
    if (b.fanout_subject && crowds(a, b) &&
        !gap_at_least(first_shape.gate, second_shape.gate, b.fanout_need))
        return Breach::fanout;
    return std::nullopt;
}

bool Kernel::group_dispersed(const std::string& group, std::size_t moved, const Shape* shape) const {
    const auto members = groups_.find(group);
    if (members == groups_.end() || members->second.size() <= problem_.rules.dispersion_floor) return false;
    const auto gate_of = [&](std::size_t part) { return shape && part == moved ? shape->gate : shapes_[part].gate; };
    Box hull = gate_of(members->second.front());
    double total = 0;
    for (const std::size_t part : members->second) {
        hull = united(hull, gate_of(part));
        total += area_of(gate_of(part));
    }
    return area_of(hull) > problem_.rules.dispersion_limit * total;
}

std::vector<Violation> Kernel::violations() const {
    std::vector<Violation> found;
    for (std::size_t part = 0; part < placement_.size(); ++part) {
        if (const auto breach = self_breach(part, shapes_[part], placement_[part]))
            found.push_back({*breach, part, part});
        for (const std::size_t other : neighbours(shapes_[part].bound, part)) {
            if (other < part) continue;
            if (const auto breach = pair_breach(part, shapes_[part], placement_[part].face, other,
                                                shapes_[other], placement_[other].face))
                found.push_back({*breach, part, other});
        }
    }
    for (const auto& [group, members] : groups_)
        if (group_dispersed(group, placement_.size(), nullptr))
            found.push_back({Breach::dispersion, members.front(), members.front()});
    return found;
}

std::optional<Violation> Kernel::rejection(std::size_t part, const Pose& pose) const {
    const Part& item = problem_.parts.at(part);
    if (item.fixed) return Violation{Breach::locked, part, part};
    if (pose.face != placement_[part].face && !problem_.footprints[item.footprint].flippable)
        return Violation{Breach::locked, part, part};
    const Shape shape = shape_of(part, pose);
    if (const auto breach = self_breach(part, shape, pose)) return Violation{*breach, part, part};
    for (const std::size_t other : neighbours(shape.bound, part))
        if (const auto breach = pair_breach(part, shape, pose.face, other, shapes_[other],
                                            placement_[other].face))
            return Violation{*breach, part, other};
    if (item.cohesion_member && group_dispersed(item.group, part, &shape))
        return Violation{Breach::dispersion, part, part};
    return std::nullopt;
}

bool Kernel::move(std::size_t part, const Pose& pose) {
    if (rejection(part, pose)) return false;
    const auto nets = routed_nets(part);
    remove(part);
    placement_[part] = pose;
    shapes_[part] = shape_of(part, pose);
    insert(part);
    for (const std::size_t net : nets) {
        routed_ -= net_lengths_[net];
        net_lengths_[net] = net_length(net, placement_.size(), nullptr);
        routed_ += net_lengths_[net];
    }
    return true;
}

Wirelength Kernel::measured_wirelength() const {
    Wirelength total;
    for (std::size_t net = 0; net < problem_.nets.size(); ++net) {
        const Nm length = net_length(net, placement_.size(), nullptr);
        switch (problem_.nets[net].category) {
        case Category::plane: total.plane += length; break;
        case Category::power: total.power += length; break;
        case Category::signal: total.signal += length; break;
        }
    }
    return total;
}

void Kernel::verify() const {
    const Wirelength measured = measured_wirelength();
    if (measured.power + measured.signal != routed_)
        throw LayoutError("layout: incremental airwire differs from a full recompute");
    std::unordered_map<Key, std::vector<std::size_t>> cells;
    for (std::size_t part = 0; part < placement_.size(); ++part) {
        const Shape shape = shape_of(part, placement_[part]);
        if (shape.gate != shapes_[part].gate || shape.bound != shapes_[part].bound)
            throw LayoutError("layout: stored shape differs from a full recompute");
        for (const Key key : keys_of(shape.bound)) cells[key].push_back(part);
    }
    if (cells.size() != cells_.size())
        throw LayoutError("layout: spatial hash differs from a full recompute");
    for (auto& [key, members] : cells) {
        auto stored = cells_.at(key);
        std::sort(stored.begin(), stored.end());
        std::sort(members.begin(), members.end());
        if (stored != members) throw LayoutError("layout: spatial hash cell differs from a full recompute");
    }
}

}
