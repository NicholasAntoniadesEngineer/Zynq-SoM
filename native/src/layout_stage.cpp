#include "schgen/layout_stage.hpp"

#include "schgen/placement_integrity.hpp"

#include <algorithm>
#include <map>
#include <sstream>
#include <tuple>

namespace schgen::layout {
namespace {

inline constexpr double percent = 100;
inline constexpr std::size_t straggler_rows = 12;
inline constexpr std::size_t stuck_rows = 4;

std::vector<Box> ordered(std::vector<Box> boxes) {
    std::sort(boxes.begin(), boxes.end(), [](const Box& a, const Box& b) {
        return std::tie(a.x0, a.y0, a.x1, a.y1) < std::tie(b.x0, b.y0, b.x1, b.y1);
    });
    return boxes;
}

}

std::string squeeze_summary(const SqueezeReport& report) {
    std::size_t kept = 0, relocated = 0, pushed = 0, sunk = 0, freed = 0, ejected = 0, rehomed = 0;
    std::map<std::string, std::string> stops;
    for (const auto& attempt : report.attempts) {
        if (attempt.kept) {
            ++kept;
            relocated += attempt.relocated;
            pushed += attempt.pushed;
            sunk += attempt.sunk;
            freed += attempt.freed;
            ejected += attempt.ejected;
            rehomed += attempt.rehomed;
        } else {
            stops[attempt.scaled ? (attempt.along_x ? "width" : "height") : side_name(attempt.side)] = attempt.blocker;
        }
    }
    const double before = to_mm(report.before.width) * to_mm(report.before.height);
    const double after = to_mm(report.after.width) * to_mm(report.after.height);
    std::ostringstream text;
    text << "LAYOUT SQUEEZE: " << to_mm(report.before.width) << " x " << to_mm(report.before.height) << " mm to "
         << to_mm(report.after.width) << " x " << to_mm(report.after.height) << " mm, area " << before << " to "
         << after << " mm2 (" << percent * (after - before) / before << "%)\n"
         << "  routed airwire " << to_mm(report.routed_before) << " to " << to_mm(report.routed_after) << " mm\n"
         << "  " << kept << " of " << report.attempts.size() << " edge steps kept, " << relocated
         << " relocations, " << pushed << " pushes, " << sunk << " parts sunk to the rear, " << freed << " jams freed (" << ejected
         << " by moving neighbours aside in a chain, " << rehomed
         << " by re-seating the cluster elsewhere on the board)\n";
    for (const auto& [side, blocker] : stops) text << "  " << side << " stopped by " << blocker << "\n";
    text << "  " << report.fallen << " cluster steps taken toward the module before the edges moved\n";
    if (!report.tried.empty()) {
        text << "  best of " << report.tried.size() << " edge orders, areas mm2:";
        for (const double area : report.tried) text << " " << area;
        text << "\n";
    }
    return text.str();
}

StageResult squeeze_stage(const PcbPlacementInput& inputs, const PcbModel& model, const PcbEmitPolicy& policy,
                          const AdapterOptions& options) {
    const PcbPlacementGatePolicy gates = pcb_placement_gate_policy(inputs);
    const ModelBinding binding = bind_model(model, policy, &gates, options);
    Kernel attracted(binding.problem, binding.placement);
    const auto rear = [](const Placement& placement) {
        return static_cast<std::size_t>(std::count_if(placement.begin(), placement.end(),
            [](const Pose& pose) { return pose.face == Face::bottom; }));
    };
    StageResult result;
    result.rear_before = rear(attracted.placement());
    const SqueezeOptions settings = default_squeeze();
    result.attract = attract(attracted, settings.pitch, static_cast<Nm>(constants::sink_reach.value));
    result.order = lead_first(attracted, settings.pitch);
    Problem held = binding.problem;
    for (NetOrder& rule : net_orders_of(binding.problem))
        if (net_order_met(binding.problem, rule, attracted.placement(), rule.lead, nullptr))
            held.constraints.net_orders.push_back(std::move(rule));
    for (const PadGap& rule : binding.problem.constraints.soft_gaps)
        if (rule.same_face && pair_faced(binding.problem, attracted.board(), rule.anchor,
                                          attracted.placement()[rule.anchor], rule.member,
                                          attracted.placement()[rule.member], rule.or_under)) {
            held.constraints.face_pairs.push_back({rule.anchor, rule.member, "face of " + rule.source, rule.or_under});
            ++result.faced;
        } else if (rule.same_face) {
            ++result.unfaced;
        }
    tighten_holds(held, attracted.placement(), hold_policy());
    held.rules.tall_module_clearance = to_nm(constants::tall_module_clearance.value);
    Kernel kernel(held, attracted.placement());
    const Bundles clusters = bundle(held);
    for (const Violation& crowding : kernel.violations()) {
        if (crowding.kind != Breach::module_core) continue;
        if (!kernel.breach(crowding.part)) continue;
        if (!rehome(kernel, clusters.units[clusters.unit_of[crowding.part]]))
            throw LayoutError("layout: " + held.parts[crowding.part].reference +
                              " is taller than the module's underside and no place clears the module by the tall-part margin");
        ++result.cleared;
    }
    const auto area = [](const SqueezeReport& report) {
        return to_mm(report.after.width) * to_mm(report.after.height);
    };
    if (inputs.floorplan.project.arrange) result.arrange = arrange(kernel, settings);
    const Snapshot seated = kernel.snapshot();
    SqueezeReport plain = squeeze_best(kernel, settings);
    const Snapshot plain_state = kernel.snapshot();
    kernel.restore(seated);
    result.balance = balance_faces(kernel, settings.pitch, static_cast<Nm>(constants::sink_reach.value));
    SqueezeReport balanced = plain;
    if (result.balance.flipped == 0) kernel.restore(plain_state);
    else balanced = squeeze_best(kernel, settings);
    result.plain_area = area(plain);
    result.balanced_area = area(balanced);
    result.balanced = result.balanced_area < result.plain_area ||
                      (result.balanced_area == result.plain_area && balanced.routed_after < plain.routed_after);
    if (!result.balanced) kernel.restore(plain_state);
    result.squeeze = result.balanced ? std::move(balanced) : std::move(plain);
    for (;;) {
        const Snapshot squeezed = kernel.snapshot();
        const BalanceReport again = balance_faces(kernel, settings.pitch, static_cast<Nm>(constants::sink_reach.value));
        if (again.flipped == 0) break;
        SqueezeReport next = squeeze_best(kernel, settings);
        Rebalance pass{again, area(result.squeeze), area(next), area(next) < area(result.squeeze)};
        result.rebalances.push_back(pass);
        if (!pass.kept) {
            kernel.restore(squeezed);
            break;
        }
        result.squeeze.after = next.after;
        result.squeeze.routed_after = next.routed_after;
        result.squeeze.fallen += next.fallen;
        result.squeeze.attempts.insert(result.squeeze.attempts.end(), next.attempts.begin(), next.attempts.end());
    }
    result.reseat = attract(kernel, settings.pitch, static_cast<Nm>(constants::sink_reach.value));
    result.rear_after = rear(kernel.placement());
    kernel.verify();
    if (!kernel.violations().empty() || !kernel.outline_holds())
        throw LayoutError("layout: the squeeze left an illegal placement");
    result.model = model_with(model, binding, kernel.placement(), kernel.board());
    std::vector<Box> fields;
    for (const auto& reserve : bind_model(result.model, policy, nullptr, options).problem.reserves)
        fields.push_back(reserve.box);
    if (ordered(fields) != ordered(kernel.reserves()))
        throw LayoutError("layout: thermal fields did not follow their parts");
    std::size_t holds = 0;
    Nm held_before = 0, held_after = 0;
    for (const auto& rule : held.constraints.pad_gaps) {
        if (!rule.derived || !rule.rigid) continue;
        ++holds;
        held_before = std::max(held_before, pad_gap_length(held, rule, binding.placement));
        held_after = std::max(held_after, pad_gap_length(held, rule, kernel.placement()));
    }
    std::map<std::string, std::size_t> ties;
    for (const auto& entry : binding.problem.ownership)
        if (entry.tie != Tie::none) ++ties[tie_name(entry.tie)];
    std::size_t reached_before = 0, reached_after = 0;
    for (const auto& rule : binding.problem.constraints.soft_gaps) {
        if (pad_gap_length(binding.problem, rule, binding.placement) <= rule.reach) ++reached_before;
        if (pad_gap_length(binding.problem, rule, kernel.placement()) <= rule.reach) ++reached_after;
    }
    std::vector<std::pair<Nm, std::size_t>> stragglers;
    for (std::size_t index = 0; index < binding.problem.constraints.soft_gaps.size(); ++index) {
        const auto& rule = binding.problem.constraints.soft_gaps[index];
        const Nm gap = pad_gap_length(binding.problem, rule, kernel.placement());
        if (gap > rule.reach) stragglers.emplace_back(gap, index);
    }
    std::sort(stragglers.begin(), stragglers.end(), [](const auto& a, const auto& b) {
        return a.first != b.first ? a.first > b.first : a.second < b.second;
    });
    std::ostringstream text;
    text << "SAME FACE: " << result.faced << " parts held on the face of the pin they serve (regulator loops, timing parts); "
         << result.unfaced << " could not be brought to that face\n";
    text << "PROTECTION ORDER: " << result.order.met_after << " of " << result.order.wanted
         << " protection parts are the first part on their net after the connector pin and are held so; "
         << result.order.reseated << " were moved nearer to become so, and "
         << result.order.moved_back << " parts ahead of one were moved back\n";
    text << "TALL PARTS: " << result.cleared << " clusters moved to give parts taller than the module's underside "
         << constants::tall_module_clearance.value << " mm from the module\n";
    text << "CLUSTER ARRANGEMENT: " << result.arrange.clusters << " tied clusters; parts and module span "
         << to_mm(result.arrange.before.width()) << " x " << to_mm(result.arrange.before.height())
         << " mm as placed; squeezes to " << result.arrange.unarranged << " mm2 without rearranging\n";
    for (std::size_t index = 0; index < result.arrange.plans.size(); ++index) {
        const ArrangePlan& plan = result.arrange.plans[index];
        text << (index + 1 == result.arrange.chosen ? "  TAKEN " : "        ") << "keep " << plan.kept_sides << ": span "
             << to_mm(plan.span.width()) << " x " << to_mm(plan.span.height()) << " mm, " << plan.moved
             << " clusters moved after opening " << to_mm(plan.widened) << " mm on the kept sides, " << plan.tightened
             << " tightening moves";
        if (plan.squeezed > 0) text << ", squeezes to " << plan.squeezed << " mm2";
        text << ", " << plan.stuck.size() << " could not leave";
        for (std::size_t stuck = 0; stuck < plan.stuck.size() && stuck < stuck_rows; ++stuck)
            text << (stuck ? ", " : ": ") << plan.stuck[stuck];
        text << "\n";
    }
    text << "  span of the taken arrangement is held by: " << result.arrange.holders << "\n"
         << "  sides that cannot be cleared because a fixed or edge-bound cluster sits there: "
         << (result.arrange.anchored_sides.empty() ? "none" : result.arrange.anchored_sides) << "\n"
         << "  arranging took " << result.arrange.plan_seconds << " s for " << result.arrange.plans.size()
         << " plans and " << result.arrange.squeeze_seconds << " s to squeeze the finalists\n";
    text << "OWNERSHIP:";
    for (const auto& [tie, parts] : ties) text << " " << parts << " " << tie;
    text << "; " << binding.unresolved.size() << " off-sheet owners not found\n"
         << "  parts within reach of the pin they serve: " << reached_before << " to " << reached_after << " of "
         << binding.problem.constraints.soft_gaps.size() << "\n";
    for (std::size_t index = 0; index < stragglers.size() && index < straggler_rows; ++index) {
        const auto& rule = binding.problem.constraints.soft_gaps[stragglers[index].second];
        text << "    " << binding.problem.parts[rule.member].reference << " is " << to_mm(stragglers[index].first)
             << " mm from " << binding.problem.parts[rule.anchor].reference << " (reach " << to_mm(rule.reach) << " mm): "
             << seat_obstacles(kernel, rule, settings.pitch) << "\n";
    }
    text << "OWNER HOLDS: " << holds << " small parts held to the pin they serve; farthest " << to_mm(held_before)
         << " mm before, " << to_mm(held_after) << " mm after\n";
    text << "OWNER ATTRACTION: " << result.attract.wanted << " parts wanted a seat at the pin they serve, "
         << result.attract.seated << " seated (" << result.attract.to_rear << " to the rear, "
         << result.attract.moved_aside << " blockers moved aside, " << result.attract.together
         << " seated together with the parts they are tied to, " << result.attract.far_seated
         << " took the nearest room beyond the first search); preferences met "
         << result.attract.met_before << " to " << result.attract.met_after << " of "
         << binding.problem.constraints.soft_gaps.size() << "\n"
         << "  routed airwire " << to_mm(result.attract.routed_before) << " to "
         << to_mm(result.attract.routed_after) << " mm\n"
         << "FACE BALANCE: " << result.balance.flipped << " of " << result.balance.sets
         << " movable clusters mirrored to the rear (" << result.balance.parts << " parts); courtyard area top "
         << result.balance.top_before << " to " << result.balance.top_after << " mm2, rear "
         << result.balance.rear_before << " to " << result.balance.rear_after << " mm2\n"
         << "  squeezed area with mirroring " << result.balanced_area << " mm2, without " << result.plain_area
         << " mm2; kept the " << (result.balanced ? "mirrored" : "unmirrored") << " board\n";
    for (const Rebalance& pass : result.rebalances)
        text << "  on the squeezed board " << pass.balance.flipped << " of " << pass.balance.sets
             << " movable clusters mirrored to the rear (" << pass.balance.parts << " parts); squeezed again "
             << pass.before << " to " << pass.after << " mm2; " << (pass.kept ? "kept" : "discarded") << "\n";
    {
        const BalanceReport& last = result.rebalances.empty() ? result.balance : result.rebalances.back().balance;
        std::vector<std::pair<double, std::string>> left = last.kept_on_top;
        std::stable_sort(left.begin(), left.end(), [](const auto& a, const auto& b) { return a.first > b.first; });
        text << "  rear-capable courtyard left on top, largest clusters:\n";
        for (std::size_t index = 0; index < left.size() && index < straggler_rows; ++index)
            text << "    " << left[index].first << " mm2 " << left[index].second << "\n";
    }
    text << squeeze_summary(result.squeeze) << "RESEAT AFTER SQUEEZE: " << result.reseat.wanted
         << " parts had drifted from the pin they serve, " << result.reseat.seated << " reseated ("
         << result.reseat.to_rear << " to the rear, " << result.reseat.far_seated
         << " to the nearest room beyond the first search); preferences met " << result.reseat.met_before << " to "
         << result.reseat.met_after << "\n"
         << "FACES: top "
         << binding.placement.size() - result.rear_before << " to " << binding.placement.size() - result.rear_after
         << ", rear " << result.rear_before << " to " << result.rear_after << "\n";
    for (const Side side : {Side::north, Side::south, Side::west, Side::east}) {
        const bool along_x = side == Side::north || side == Side::south;
        std::vector<std::pair<Nm, std::size_t>> row;
        Nm bodies = 0;
        for (std::size_t part = 0; part < held.parts.size(); ++part) {
            const Part& item = held.parts[part];
            if (!item.edge || facing(item, kernel.placement()[part]) != side) continue;
            const Box gate = gate_at(held, part, kernel.placement()[part]);
            row.emplace_back(along_x ? gate.x0 : gate.y0, part);
            bodies += along_x ? gate.width() : gate.height();
        }
        std::sort(row.begin(), row.end());
        const Nm length = along_x ? kernel.board().width : kernel.board().height;
        text << "EDGE " << side_name(side) << ": " << to_mm(length) << " mm long, connector bodies " << to_mm(bodies)
             << " mm (" << percent * static_cast<double>(bodies) / static_cast<double>(length) << "%):";
        for (const auto& [at, part] : row) text << " " << held.parts[part].reference;
        text << "\n";
    }
    {
        const std::size_t count = held.parts.size();
        std::vector<std::size_t> lead(count);
        for (std::size_t part = 0; part < count; ++part) lead[part] = part;
        const auto root = [&](std::size_t part) {
            while (lead[part] != part) part = lead[part] = lead[lead[part]];
            return part;
        };
        for (const auto& pair : held.constraints.face_pairs) lead[root(pair.first)] = root(pair.second);
        std::vector<char> pinned(count, 0);
        for (std::size_t part = 0; part < count; ++part) {
            const Part& item = held.parts[part];
            if (item.fixed || item.top_only || !held.footprints[item.footprint].flippable) pinned[root(part)] = 1;
        }
        const auto kind_of = [](const Part& item) -> const char* {
            if (!item.part_class) throw LayoutError("layout: " + item.reference + " carries no part class");
            switch (*item.part_class) {
            case PartClass::test_point: return "top-only test points";
            case PartClass::led: return "top-only LEDs";
            case PartClass::control_switch: return "top-only switches";
            case PartClass::connector:
            case PartClass::header:
            case PartClass::module_connector: return "top-only connectors and headers";
            case PartClass::battery_holder: return "top-only battery holder";
            case PartClass::resistor:
            case PartClass::capacitor:
            case PartClass::inductor:
            case PartClass::ferrite:
            case PartClass::transformer:
            case PartClass::diode:
            case PartClass::transistor:
            case PartClass::integrated_circuit:
            case PartClass::crystal:
            case PartClass::mounting_hole:
            case PartClass::fiducial: return "top-only parts on controlled nets or with through holes";
            }
            throw LayoutError("layout: " + item.reference + " has a part class with no face reason");
        };
        std::map<std::string, double> top;
        double rear = 0;
        for (std::size_t part = 0; part < count; ++part) {
            const Part& item = held.parts[part];
            const Box gate = gate_at(held, part, kernel.placement()[part]);
            const double area = to_mm(gate.width()) * to_mm(gate.height());
            if (kernel.placement()[part].face == Face::bottom) {
                rear += area;
                continue;
            }
            const char* why = item.edge ? "edge connectors"
                              : item.fixed ? "fixed parts"
                              : item.top_only ? kind_of(item)
                              : !held.footprints[item.footprint].flippable ? "parts that cannot be mirrored"
                              : pinned[root(part)] ? "parts tied to the face of a top-bound part"
                              : "parts free to go to the rear";
            top[why] += area;
        }
        text << "TOP FACE courtyard area by reason (rear holds " << rear << " mm2):\n";
        for (const auto& [why, area] : top) text << "    " << area << " mm2 " << why << "\n";
    }
    text << check_placement_integrity(PcbCheckInput(result.model), result.model, options.intent).summary(rules::Stage::layout);
    result.report = text.str();
    return result;
}

}
