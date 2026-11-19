#include "schgen/layout_kernel.hpp"

#include <algorithm>
#include <array>
#include <cmath>
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

enum Slot : std::size_t { north_slot, south_slot, west_slot, east_slot };

bool beside_escape(const std::array<bool, edge_count>& escape, Box subject, Box crowder, Nm guard) {
    const bool beside = std::min(subject.x1, crowder.x1) - std::max(subject.x0, crowder.x0) <= guard;
    const bool above = std::min(subject.y1, crowder.y1) - std::max(subject.y0, crowder.y0) <= guard;
    if (!beside && !above) return true;
    return (beside && escape[crowder.x0 + crowder.x1 >= subject.x0 + subject.x1 ? east_slot : west_slot]) ||
           (above && escape[crowder.y0 + crowder.y1 >= subject.y0 + subject.y1 ? south_slot : north_slot]);
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
    case Breach::contract: return "contract";
    case Breach::group_bound: return "group_bound";
    case Breach::edge_mount: return "edge_mount";
    case Breach::connector_gap: return "connector_gap";
    case Breach::reserved: return "reserved";
    case Breach::locked: return "locked";
    case Breach::corner: return "corner";
    case Breach::under_inductor: return "under_inductor";
    }
    return "unknown";
}

Kernel::Kernel(const Problem& problem, Placement placement)
    : problem_(problem), board_(problem.board), placement_(std::move(placement)) {
    validate(problem_, placement_);
    for (const auto& part : problem_.parts)
        if (part.fanout_subject) reach_ = std::max(reach_, part.fanout_need);
    fields_.resize(placement_.size());
    for (std::size_t reserve = 0; reserve < problem_.reserves.size(); ++reserve) {
        reserve_boxes_.push_back(problem_.reserves[reserve].box);
        for (const std::size_t member : problem_.reserves[reserve].members) fields_.at(member).push_back(reserve);
    }
    for (std::size_t part = 0; part < placement_.size(); ++part) {
        if (problem_.parts[part].cohesion_member) groups_[problem_.parts[part].group].push_back(part);
        members_[problem_.parts[part].group].push_back(part);
        if (problem_.parts[part].connector) connectors_.push_back(part);
    }
    const Constraints& rules = problem_.constraints;
    pad_rules_.resize(placement_.size());
    nearest_rules_.resize(placement_.size());
    face_rules_.resize(placement_.size());
    for (std::size_t rule = 0; rule < rules.pad_gaps.size(); ++rule) {
        pad_rules_[rules.pad_gaps[rule].anchor].push_back(rule);
        if (rules.pad_gaps[rule].member != rules.pad_gaps[rule].anchor)
            pad_rules_[rules.pad_gaps[rule].member].push_back(rule);
    }
    for (std::size_t rule = 0; rule < rules.nearest_gaps.size(); ++rule) {
        std::vector<std::size_t> touched = rules.nearest_gaps[rule].members;
        touched.push_back(rules.nearest_gaps[rule].anchor);
        std::sort(touched.begin(), touched.end());
        touched.erase(std::unique(touched.begin(), touched.end()), touched.end());
        for (const std::size_t part : touched) nearest_rules_[part].push_back(rule);
    }
    for (std::size_t rule = 0; rule < rules.face_pairs.size(); ++rule) {
        face_rules_[rules.face_pairs[rule].first].push_back(rule);
        face_rules_[rules.face_pairs[rule].second].push_back(rule);
    }
    for (std::size_t rule = 0; rule < rules.group_gaps.size(); ++rule) {
        group_rules_[rules.group_gaps[rule].first].push_back(rule);
        if (!rules.group_gaps[rule].second_is_core && rules.group_gaps[rule].second != rules.group_gaps[rule].first)
            group_rules_[rules.group_gaps[rule].second].push_back(rule);
    }
    rebuild();
}

void Kernel::rebuild() {
    shapes_.clear();
    cells_.clear();
    shapes_.reserve(placement_.size());
    for (std::size_t part = 0; part < placement_.size(); ++part) {
        shapes_.push_back(shape_of(part, placement_[part]));
        insert(part);
    }
    routed_ = 0;
    net_lengths_.assign(problem_.nets.size(), 0);
    for (std::size_t net = 0; net < problem_.nets.size(); ++net) {
        if (problem_.nets[net].category == Category::plane) continue;
        net_lengths_[net] = net_length(net, placement_.size(), nullptr);
        routed_ += net_lengths_[net];
    }
}

void Kernel::restore(const Snapshot& snapshot) {
    board_ = snapshot.board;
    reserve_boxes_ = snapshot.reserves;
    std::vector<Move> changed;
    for (std::size_t part = 0; part < placement_.size(); ++part)
        if (placement_[part] != snapshot.placement[part]) changed.push_back({part, snapshot.placement[part]});
    for (const Move& move : changed) place(move.part, move.pose);
    refresh_nets(changed);
}

void Kernel::place(std::size_t part, const Pose& pose) {
    remove(part);
    placement_[part] = pose;
    shapes_[part] = shape_of(part, pose);
    insert(part);
}

void Kernel::refresh_nets(const std::vector<Move>& moves) {
    std::vector<std::size_t> nets;
    for (const auto& move : moves)
        for (const std::size_t net : routed_nets(move.part)) nets.push_back(net);
    std::sort(nets.begin(), nets.end());
    nets.erase(std::unique(nets.begin(), nets.end()), nets.end());
    for (const std::size_t net : nets) {
        routed_ -= net_lengths_[net];
        net_lengths_[net] = net_length(net, placement_.size(), nullptr);
        routed_ += net_lengths_[net];
    }
}

bool Kernel::owns(std::size_t reserve, std::size_t part) const {
    const auto& fields = fields_[part];
    return std::find(fields.begin(), fields.end(), reserve) != fields.end();
}

void Kernel::set_board(const Board& board) {
    board_ = board;
    for (std::size_t reserve = 0; reserve < problem_.reserves.size(); ++reserve) {
        const std::optional<PourRule>& pour = problem_.reserves[reserve].pour;
        if (pour) reserve_boxes_[reserve] = pour_box(*pour, placement_[pour->owner], board_);
    }
}

bool Kernel::reserves_follow(const std::vector<Move>& moves, const std::vector<char>& moved,
                             std::vector<Box>& boxes, std::vector<std::size_t>& carried) const {
    for (std::size_t reserve = 0; reserve < problem_.reserves.size(); ++reserve) {
        const auto& members = problem_.reserves[reserve].members;
        const auto count = static_cast<std::size_t>(std::count_if(members.begin(), members.end(),
            [&](std::size_t member) { return moved[member] != 0; }));
        if (count == 0) continue;
        if (count != members.size()) return false;
        const std::optional<PourRule>& pour = problem_.reserves[reserve].pour;
        std::optional<Turn> swing;
        std::optional<Pose> owner;
        Point from{}, to{};
        for (const auto& move : moves) {
            if (!owns(reserve, move.part)) continue;
            const Pose& before = placement_[move.part];
            if (move.pose.face != before.face) return false;
            const Turn turn = static_cast<Turn>(
                (static_cast<int>(move.pose.turn) + turn_count - static_cast<int>(before.turn)) % turn_count);
            if (pour && pour->owner == move.part) owner = move.pose;
            if (!swing) {
                swing = turn;
                from = before.at;
                to = move.pose.at;
                continue;
            }
            const Point arm{before.at.x - from.x, before.at.y - from.y};
            if (turn != *swing || shifted(to, turned(arm, *swing)) != move.pose.at) return false;
        }
        if (pour) {
            if (!owner) return false;
            boxes[reserve] = pour_box(*pour, *owner, board_);
        } else {
            if (*swing != Turn::none) return false;
            boxes[reserve] = shifted(boxes[reserve], Point{to.x - from.x, to.y - from.y});
        }
        carried.push_back(reserve);
    }
    return true;
}

bool Kernel::force(const std::vector<Move>& moves) {
    std::vector<char> moved(placement_.size(), 0);
    for (const auto& move : moves) moved.at(move.part) = 1;
    std::vector<Box> boxes = reserve_boxes_;
    std::vector<std::size_t> carried;
    if (!reserves_follow(moves, moved, boxes, carried)) return false;
    for (const auto& move : moves) place(move.part, move.pose);
    reserve_boxes_ = std::move(boxes);
    refresh_nets(moves);
    return true;
}

std::optional<Violation> Kernel::breach_at(std::size_t part, Nm guard, const std::vector<char>* moved) const {
    const Part& item = problem_.parts[part];
    const Shape& shape = shapes_[part];
    const Pose& pose = placement_[part];
    if (const auto breach = self_breach(part, shape, pose)) return Violation{*breach, part, part};
    for (const std::size_t other : neighbours(shape.bound, part))
        if (const auto breach = pair_breach(part, shape, pose.face, other, shapes_[other], placement_[other].face, guard))
            return Violation{*breach, part, other};
    if (item.cohesion_member && group_dispersed(item.group, placement_.size(), nullptr))
        return Violation{Breach::dispersion, part, part};
    std::size_t other = part;
    if (const auto breach = rule_breach(part, shape, pose, guard, &other, moved)) return Violation{*breach, part, other};
    return std::nullopt;
}

bool Kernel::attempt(const std::vector<Move>& moves, std::vector<std::size_t>* blockers, bool keep) {
    std::vector<char> moved(placement_.size(), 0);
    for (const auto& move : moves) {
        const Part& item = problem_.parts.at(move.part);
        if (item.fixed || moved[move.part]) return false;
        if (move.pose.face != placement_[move.part].face && !problem_.footprints[item.footprint].flippable)
            return false;
        moved[move.part] = 1;
    }
    std::vector<Box> boxes = reserve_boxes_;
    std::vector<std::size_t> carried;
    if (!reserves_follow(moves, moved, boxes, carried)) return false;
    std::vector<Pose> before;
    std::vector<Shape> shapes_before;
    before.reserve(moves.size());
    shapes_before.reserve(moves.size());
    for (const auto& move : moves) {
        before.push_back(placement_[move.part]);
        remove(move.part);
        shapes_before.push_back(std::move(shapes_[move.part]));
        placement_[move.part] = move.pose;
        shapes_[move.part] = shape_of(move.part, move.pose);
        insert(move.part);
    }
    std::swap(reserve_boxes_, boxes);
    bool sound = true;
    for (std::size_t index = 0; sound && index < moves.size(); ++index) {
        const std::size_t part = moves[index].part;
        const Part& item = problem_.parts[part];
        const Shape& shape = shapes_[part];
        const Pose& pose = placement_[part];
        if (self_breach(part, shape, pose)) sound = false;
        for (const std::size_t other : neighbours(shape.bound, part)) {
            if (!sound) break;
            if (!pair_breach(part, shape, pose.face, other, shapes_[other], placement_[other].face,
                             problem_.rules.compare_guard))
                continue;
            if (!blockers || moved[other] || problem_.parts[other].fixed) sound = false;
            else blockers->push_back(other);
        }
        if (sound && item.cohesion_member && group_dispersed(item.group, placement_.size(), nullptr)) sound = false;
        if (sound && rule_breach(part, shape, pose, problem_.rules.compare_guard, nullptr, &moved)) sound = false;
    }
    for (std::size_t index = 0; sound && index < carried.size(); ++index) {
        const Box field = reserve_boxes_[carried[index]];
        for (const std::size_t other : neighbours(field, placement_.size())) {
            if (moved[other] || owns(carried[index], other) || !overlaps(shapes_[other].bound, field)) continue;
            if (!blockers || problem_.parts[other].fixed) {
                sound = false;
                break;
            }
            blockers->push_back(other);
        }
    }
    if (sound && keep) {
        refresh_nets(moves);
        return true;
    }
    for (std::size_t index = 0; index < moves.size(); ++index) {
        const std::size_t part = moves[index].part;
        remove(part);
        placement_[part] = before[index];
        shapes_[part] = std::move(shapes_before[index]);
        insert(part);
    }
    std::swap(reserve_boxes_, boxes);
    return sound;
}

Probe Kernel::probe(const std::vector<Move>& moves) {
    Probe result;
    result.placeable = attempt(moves, &result.blockers, false);
    if (!result.placeable) result.blockers.clear();
    std::sort(result.blockers.begin(), result.blockers.end());
    result.blockers.erase(std::unique(result.blockers.begin(), result.blockers.end()), result.blockers.end());
    return result;
}

bool Kernel::outline_holds() const {
    const Box outline = board_.outline();
    if (board_.module_core && !inside(*board_.module_core, outline)) return false;
    if (board_.module_body && !inside(*board_.module_body, outline)) return false;
    const Box copper = grown(outline, -problem_.rules.edge_clearance);
    return std::all_of(problem_.obstacles.begin(), problem_.obstacles.end(),
                       [&](const Obstacle& obstacle) { return inside(obstacle.box, copper); });
}

Kernel::Shape Kernel::shape_of(std::size_t part, const Pose& pose) const {
    const Variant& variant = problem_.footprints[problem_.parts[part].footprint].on(pose.face);
    Shape shape;
    shape.gate = placed(variant.gate_box, pose.at, pose.turn);
    shape.bound = shape.gate;
    const std::array<Point, edge_count> sides{Point{0, -1}, Point{0, 1}, Point{-1, 0}, Point{1, 0}};
    const auto& escape = problem_.parts[part].escape_on(pose.face);
    for (std::size_t side = 0; side < edge_count; ++side) {
        if (!escape[side]) continue;
        const Point out = turned(sides[side], pose.turn);
        shape.escape[out.y < 0 ? north_slot : out.y > 0 ? south_slot : out.x < 0 ? west_slot : east_slot] = true;
    }
    for (const auto& box : variant.court_boxes) shape.courts.push_back(placed(box, pose.at, pose.turn));
    for (const auto& disc : variant.court_discs) shape.discs.push_back(placed(disc, pose.at, pose.turn));
    const auto& nets = problem_.parts[part].pad_nets;
    for (std::size_t pad = 0; pad < variant.pads.size(); ++pad) {
        const Box box = placed(variant.pads[pad].box, pose.at, pose.turn);
        shape.lands.push_back({box, nets[pad], variant.pads[pad].through,
                               {placed(variant.pads[pad].centre, pose.at, pose.turn), variant.pads[pad].radius}});
        if (variant.pads[pad].through) shape.holes.push_back(box);
    }
    for (const auto& box : variant.name_boxes) shape.named.push_back(placed(box, pose.at, pose.turn));
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
    const Box box = shapes_[part].bound;
    for (Nm column = cell_of(box.x0); column <= cell_of(box.x1); ++column)
        for (Nm row = cell_of(box.y0); row <= cell_of(box.y1); ++row) cells_[key_of(column, row)].push_back(part);
}

void Kernel::remove(std::size_t part) {
    const Box box = shapes_[part].bound;
    for (Nm column = cell_of(box.x0); column <= cell_of(box.x1); ++column)
        for (Nm row = cell_of(box.y0); row <= cell_of(box.y1); ++row) {
            const auto cell = cells_.find(key_of(column, row));
            if (cell == cells_.end()) continue;
            auto& members = cell->second;
            members.erase(std::remove(members.begin(), members.end(), part), members.end());
        }
}

std::vector<std::size_t> Kernel::neighbours(Box box, std::size_t self) const {
    std::vector<std::size_t> found;
    const Box reach = grown(box, reach_);
    for (Nm column = cell_of(reach.x0); column <= cell_of(reach.x1); ++column)
        for (Nm row = cell_of(reach.y0); row <= cell_of(reach.y1); ++row) {
            const auto cell = cells_.find(key_of(column, row));
            if (cell == cells_.end()) continue;
            for (const std::size_t part : cell->second)
                if (part != self) found.push_back(part);
        }
    std::sort(found.begin(), found.end());
    found.erase(std::unique(found.begin(), found.end()), found.end());
    return found;
}

bool Kernel::crowds(const Part& crowder, const Part& subject) const {
    return counts_as_crowder(crowder, subject);
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
    if (shape.pads && !inside(*shape.pads, grown(board_.outline(), -problem_.rules.edge_clearance)))
        return Breach::off_board;
    if (!item.edge && problem_.rules.edge_setback > 0 &&
        !inside(shape.gate, grown(board_.outline(), -problem_.rules.edge_setback)))
        return Breach::off_board;
    if (item.corner && pose.at != corner_site(board_, *item.corner)) return Breach::corner;
    if (!item.fixed && !copper_clear(shape, pose.face)) return Breach::copper;
    for (std::size_t reserve = 0; reserve < reserve_boxes_.size(); ++reserve) {
        const Reserve& field = problem_.reserves[reserve];
        const bool faced = pose.face == Face::top ? field.top : field.bottom;
        if ((!faced && shape.holes.empty()) || owns(reserve, part)) continue;
        if (overlaps(shape.bound, reserve_boxes_[reserve])) return Breach::reserved;
    }
    if (!item.fixed && problem_.rules.plane_margin > 0) {
        const Box outline = board_.outline();
        Box relief = grown(outline, -problem_.rules.plane_margin);
        if (item.edge)
            relief = turned(item.edge->mouth_on(pose.face), pose.turn).y != 0 ? Box{relief.x0, outline.y0, relief.x1, outline.y1}
                                                               : Box{outline.x0, relief.y0, outline.x1, relief.y1};
        for (const auto& land : shape.lands)
            if (land.through && land.net != no_net &&
                problem_.nets[static_cast<std::size_t>(land.net)].category == Category::plane &&
                !inside(land.box, relief))
                return Breach::off_board;
    }
    if (pose.face == Face::bottom && item.top_only) return Breach::bottom_face;
    if (board_.module_body && pose.face == Face::top && !item.core_exempt &&
        !gap_at_least(shape.bound, *board_.module_body, problem_.rules.module_clearance))
        return Breach::module_core;
    return std::nullopt;
}

std::optional<Breach> Kernel::pair_breach(std::size_t first, const Shape& first_shape, Face first_face,
                                          std::size_t second, const Shape& second_shape,
                                          Face second_face, Nm guard) const {
    if (first_face != second_face) {
        const Part& above = problem_.parts[first];
        const Part& below = problem_.parts[second];
        if (((above.field_source && below.field_sensitive) || (below.field_source && above.field_sensitive)) &&
            courts_overlap(first_shape.courts, first_shape.discs, second_shape.courts, second_shape.discs))
            return Breach::under_inductor;
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
    if (a.fanout_subject && crowds(b, a) && !gap_at_least(first_shape.gate, second_shape.gate, a.fanout_need) &&
        beside_escape(first_shape.escape, first_shape.gate, second_shape.gate, guard))
        return Breach::fanout;
    if (b.fanout_subject && crowds(a, b) && !gap_at_least(first_shape.gate, second_shape.gate, b.fanout_need) &&
        beside_escape(second_shape.escape, second_shape.gate, first_shape.gate, guard))
        return Breach::fanout;
    return std::nullopt;
}

Nm Kernel::named_gap(const Shape& anchor, const std::vector<std::size_t>& names, const Shape& member) const {
    Nm best = std::numeric_limits<Nm>::max();
    const auto scan = [&](const Box& box) {
        for (const auto& other : member.named) best = std::min(best, squared_gap(box, other));
    };
    if (names.empty())
        for (const auto& box : anchor.named) scan(box);
    else
        for (const std::size_t name : names) scan(anchor.named[name]);
    return best;
}

bool Kernel::pad_gap_met(const PadGap& rule, const Shape& anchor, const Shape& member, Nm guard) const {
    const Nm gap = named_gap(anchor, rule.anchor_names, member);
    if (rule.sense == Sense::at_least) return gap >= squared(rule.limit + guard);
    return rule.limit >= guard && gap <= squared(rule.limit - guard);
}

bool Kernel::nearest_met(const NearestGap& rule, std::size_t moved, const Shape* shape, const Pose* pose,
                         Nm guard) const {
    const auto shape_of_part = [&](std::size_t part) -> const Shape& {
        return shape && part == moved ? *shape : shapes_[part];
    };
    const auto face_of_part = [&](std::size_t part) {
        return pose && part == moved ? pose->face : placement_[part].face;
    };
    Nm best = std::numeric_limits<Nm>::max();
    for (const std::size_t member : rule.members) {
        if (rule.same_face && face_of_part(member) != face_of_part(rule.anchor)) continue;
        best = std::min(best, named_gap(shape_of_part(rule.anchor), rule.anchor_names, shape_of_part(member)));
    }
    return rule.limit >= guard && best <= squared(rule.limit - guard);
}

Kernel::GroupSummary Kernel::summarise(const GroupGap& rule, bool second, std::size_t moved, const Shape* shape,
                                       const Pose* pose) const {
    GroupSummary summary;
    if (second && rule.second_is_core) {
        if (!board_.module_core) return summary;
        summary.hull = board_.module_core;
        summary.x = static_cast<double>(summary.hull->x0 + summary.hull->x1) / 2;
        summary.y = static_cast<double>(summary.hull->y0 + summary.hull->y1) / 2;
        summary.count = 1;
        return summary;
    }
    const auto found = members_.find(second ? rule.second : rule.first);
    if (found == members_.end()) return summary;
    for (const std::size_t part : found->second) {
        const Shape& item = shape && part == moved ? *shape : shapes_[part];
        const Point at = pose && part == moved ? pose->at : placement_[part].at;
        if (item.pads) summary.hull = summary.hull ? united(*summary.hull, *item.pads) : *item.pads;
        summary.x += static_cast<double>(at.x);
        summary.y += static_cast<double>(at.y);
        summary.count += 1;
    }
    summary.x /= summary.count;
    summary.y /= summary.count;
    return summary;
}

std::optional<double> Kernel::group_distance(const GroupGap& rule, std::size_t moved, const Shape* shape,
                                             const Pose* pose) const {
    const GroupSummary first = summarise(rule, false, moved, shape, pose);
    const GroupSummary second = summarise(rule, true, moved, shape, pose);
    if (rule.measure == GroupMeasure::hull_gap) {
        if (!first.hull || !second.hull) return std::nullopt;
        return std::sqrt(static_cast<double>(squared_gap(*first.hull, *second.hull)));
    }
    if (first.count == 0 || second.count == 0) return std::nullopt;
    return std::hypot(first.x - second.x, first.y - second.y);
}

bool Kernel::group_gap_met(const GroupGap& rule, std::size_t moved, const Shape* shape, const Pose* pose,
                           Nm guard) const {
    const GroupSummary first = summarise(rule, false, moved, shape, pose);
    const GroupSummary second = summarise(rule, true, moved, shape, pose);
    if (rule.measure == GroupMeasure::hull_gap) {
        if (!first.hull || !second.hull) return false;
        const Nm gap = squared_gap(*first.hull, *second.hull);
        if (rule.sense == Sense::at_least) return gap >= squared(rule.limit + guard);
        return rule.limit >= guard && gap <= squared(rule.limit - guard);
    }
    if (first.count == 0 || second.count == 0) return false;
    const double distance = std::hypot(first.x - second.x, first.y - second.y);
    if (rule.sense == Sense::at_least) return distance >= static_cast<double>(rule.limit + guard);
    return distance <= static_cast<double>(rule.limit - guard);
}

std::vector<Margin> Kernel::margins() const {
    std::vector<Margin> out;
    const Constraints& rules = problem_.constraints;
    const auto signed_margin = [](Sense sense, Nm limit, double measured) {
        return sense == Sense::at_most ? static_cast<double>(limit) - measured : measured - static_cast<double>(limit);
    };
    const auto length = [](Nm squared_length) {
        return squared_length == std::numeric_limits<Nm>::max() ? std::numeric_limits<double>::infinity()
                                                                 : std::sqrt(static_cast<double>(squared_length));
    };
    for (const auto& rule : rules.pad_gaps)
        out.push_back({"pad_gap", rule.source, signed_margin(rule.sense, rule.limit,
            length(named_gap(shapes_[rule.anchor], rule.anchor_names, shapes_[rule.member])))});
    for (const auto& rule : rules.soft_gaps)
        out.push_back({"soft_gap", rule.source, signed_margin(rule.sense, rule.limit,
            length(named_gap(shapes_[rule.anchor], rule.anchor_names, shapes_[rule.member])))});
    for (const auto& rule : rules.nearest_gaps) {
        Nm best = std::numeric_limits<Nm>::max();
        for (const std::size_t member : rule.members)
            if (!rule.same_face || placement_[member].face == placement_[rule.anchor].face)
                best = std::min(best, named_gap(shapes_[rule.anchor], rule.anchor_names, shapes_[member]));
        out.push_back({"nearest_gap", rule.source, signed_margin(Sense::at_most, rule.limit, length(best))});
    }
    for (const auto& rule : rules.group_gaps) {
        const auto distance = group_distance(rule, placement_.size(), nullptr, nullptr);
        out.push_back({"group_gap", rule.source,
                       distance ? signed_margin(rule.sense, rule.limit, *distance)
                                : -std::numeric_limits<double>::infinity()});
    }
    return out;
}

bool Kernel::edge_met(const Part& item, const Shape& shape, const Pose& pose) const {
    const Box outline = board_.outline();
    const std::array<Nm, edge_count> distance{shape.gate.y0 - outline.y0, outline.y1 - shape.gate.y1,
                                              shape.gate.x0 - outline.x0, outline.x1 - shape.gate.x1};
    const std::array<Point, edge_count> outward{Point{0, -1}, Point{0, 1}, Point{-1, 0}, Point{1, 0}};
    const std::array<Nm, edge_count> seat{pose.at.y - outline.y0, outline.y1 - pose.at.y,
                                          pose.at.x - outline.x0, outline.x1 - pose.at.x};
    const auto nearest = static_cast<std::size_t>(std::min_element(distance.begin(), distance.end()) - distance.begin());
    return distance[nearest] <= item.edge->reach &&
           turned(item.edge->mouth_on(pose.face), pose.turn) == outward[nearest] &&
           seat[nearest] == item.edge->seat;
}

bool Kernel::connectors_met(std::size_t part, const Shape& shape, std::size_t other, const Shape& other_shape,
                            Nm guard) const {
    if (!shape.pads || !other_shape.pads) return true;
    const ConnectorRules& rules = problem_.constraints.connectors;
    const Box& a = *shape.pads;
    const Box& b = *other_shape.pads;
    const Nm cross_x = std::min(a.x1, b.x1) - std::max(a.x0, b.x0);
    const Nm cross_y = std::min(a.y1, b.y1) - std::max(a.y0, b.y0);
    if (cross_x > rules.overlap_slack && cross_y > rules.overlap_slack) return false;
    const bool first_boot = problem_.parts[part].overmold, second_boot = problem_.parts[other].overmold;
    if (!first_boot && !second_boot) return true;
    const Nm width = std::min(a.width(), b.width()), height = std::min(a.height(), b.height());
    const bool same_x = width > 0 && static_cast<double>(cross_x) >= rules.band_share * static_cast<double>(width);
    const bool same_y = height > 0 && static_cast<double>(cross_y) >= rules.band_share * static_cast<double>(height);
    if (same_x == same_y) return true;
    const Nm gap = same_y ? std::max(a.x0, b.x0) - std::min(a.x1, b.x1) : std::max(a.y0, b.y0) - std::min(a.y1, b.y1);
    return gap >= (first_boot && second_boot ? rules.overmold_gap : rules.boot_gap) + guard;
}

std::optional<Breach> Kernel::rule_breach(std::size_t part, const Shape& shape, const Pose& pose, Nm guard,
                                          std::size_t* other, const std::vector<char>* moved) const {
    const auto guard_for = [&](std::size_t peer) { return moved && (*moved)[peer] ? Nm{0} : guard; };
    const Part& item = problem_.parts[part];
    const Constraints& rules = problem_.constraints;
    if (item.edge && !edge_met(item, shape, pose)) return Breach::edge_mount;
    if (item.connector)
        for (const std::size_t peer : connectors_)
            if (peer != part && !connectors_met(part, shape, peer, shapes_[peer], guard)) {
                if (other) *other = peer;
                return Breach::connector_gap;
            }
    for (const std::size_t index : pad_rules_[part]) {
        const PadGap& rule = rules.pad_gaps[index];
        const Shape& anchor = rule.anchor == part ? shape : shapes_[rule.anchor];
        const Shape& member = rule.member == part ? shape : shapes_[rule.member];
        if (!pad_gap_met(rule, anchor, member, guard_for(rule.anchor == part ? rule.member : rule.anchor))) {
            if (other) *other = rule.anchor == part ? rule.member : rule.anchor;
            return Breach::contract;
        }
    }
    for (const std::size_t index : nearest_rules_[part])
        if (!nearest_met(rules.nearest_gaps[index], part, &shape, &pose, guard)) {
            if (other) *other = rules.nearest_gaps[index].anchor;
            return Breach::contract;
        }
    for (const std::size_t index : face_rules_[part]) {
        const FacePair& rule = rules.face_pairs[index];
        const std::size_t peer = rule.first == part ? rule.second : rule.first;
        if (peer != part && placement_[peer].face != pose.face) {
            if (other) *other = peer;
            return Breach::contract;
        }
    }
    const auto found = group_rules_.find(item.group);
    if (found != group_rules_.end())
        for (const std::size_t index : found->second)
            if (!group_gap_met(rules.group_gaps[index], part, &shape, &pose,
                               guard > 0 ? problem_.rules.group_guard : 0))
                return Breach::group_bound;
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
                                                shapes_[other], placement_[other].face, 0))
                found.push_back({*breach, part, other});
        }
    }
    for (const auto& [group, members] : groups_)
        if (group_dispersed(group, placement_.size(), nullptr))
            found.push_back({Breach::dispersion, members.front(), members.front()});
    const Constraints& rules = problem_.constraints;
    for (std::size_t part = 0; part < placement_.size(); ++part) {
        const Part& item = problem_.parts[part];
        if (item.edge && !edge_met(item, shapes_[part], placement_[part]))
            found.push_back({Breach::edge_mount, part, part});
        if (item.connector)
            for (const std::size_t peer : connectors_)
                if (peer > part && !connectors_met(part, shapes_[part], peer, shapes_[peer], 0))
                    found.push_back({Breach::connector_gap, part, peer});
    }
    for (const auto& rule : rules.pad_gaps)
        if (!pad_gap_met(rule, shapes_[rule.anchor], shapes_[rule.member], 0))
            found.push_back({Breach::contract, rule.anchor, rule.member});
    for (const auto& rule : rules.nearest_gaps)
        if (!nearest_met(rule, placement_.size(), nullptr, nullptr, 0))
            found.push_back({Breach::contract, rule.anchor, rule.anchor});
    for (const auto& rule : rules.face_pairs)
        if (placement_[rule.first].face != placement_[rule.second].face)
            found.push_back({Breach::contract, rule.first, rule.second});
    for (const auto& rule : rules.group_gaps)
        if (!group_gap_met(rule, placement_.size(), nullptr, nullptr, 0)) {
            const auto members = members_.find(rule.first);
            const std::size_t part = members == members_.end() ? 0 : members->second.front();
            found.push_back({Breach::group_bound, part, part});
        }
    return found;
}

std::optional<Violation> Kernel::rejection(std::size_t part, const Pose& pose) const {
    const Part& item = problem_.parts.at(part);
    if (item.fixed || !fields_[part].empty()) return Violation{Breach::locked, part, part};
    if (pose.face != placement_[part].face && !problem_.footprints[item.footprint].flippable)
        return Violation{Breach::locked, part, part};
    const Shape shape = shape_of(part, pose);
    if (const auto breach = self_breach(part, shape, pose)) return Violation{*breach, part, part};
    for (const std::size_t other : neighbours(shape.bound, part))
        if (const auto breach = pair_breach(part, shape, pose.face, other, shapes_[other],
                                            placement_[other].face, problem_.rules.compare_guard))
            return Violation{*breach, part, other};
    if (item.cohesion_member && group_dispersed(item.group, part, &shape))
        return Violation{Breach::dispersion, part, part};
    std::size_t other = part;
    if (const auto breach = rule_breach(part, shape, pose, problem_.rules.compare_guard, &other, nullptr))
        return Violation{*breach, part, other};
    return std::nullopt;
}

bool Kernel::move(std::size_t part, const Pose& pose) { return move_many({{part, pose}}); }

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
    const auto occupied = static_cast<std::size_t>(std::count_if(cells_.begin(), cells_.end(), [](const auto& cell) {
        return !cell.second.empty();
    }));
    if (cells.size() != occupied) throw LayoutError("layout: spatial hash differs from a full recompute");
    for (auto& [key, members] : cells) {
        auto stored = cells_.at(key);
        std::sort(stored.begin(), stored.end());
        std::sort(members.begin(), members.end());
        if (stored != members) throw LayoutError("layout: spatial hash cell differs from a full recompute");
    }
}

}
