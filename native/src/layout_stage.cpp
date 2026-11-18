#include "schgen/layout_stage.hpp"

#include <algorithm>
#include <map>
#include <sstream>
#include <tuple>

namespace schgen::layout {
namespace {

inline constexpr double percent = 100;
inline constexpr std::size_t straggler_rows = 12;

std::vector<Box> ordered(std::vector<Box> boxes) {
    std::sort(boxes.begin(), boxes.end(), [](const Box& a, const Box& b) {
        return std::tie(a.x0, a.y0, a.x1, a.y1) < std::tie(b.x0, b.y0, b.x1, b.y1);
    });
    return boxes;
}

}

std::string squeeze_summary(const SqueezeReport& report) {
    std::size_t kept = 0, relocated = 0, pushed = 0, sunk = 0;
    std::map<std::string, std::string> stops;
    for (const auto& attempt : report.attempts) {
        if (attempt.kept) {
            ++kept;
            relocated += attempt.relocated;
            pushed += attempt.pushed;
            sunk += attempt.sunk;
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
         << " relocations, " << pushed << " pushes, " << sunk << " parts sunk to the rear\n";
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
    Problem held = binding.problem;
    tighten_holds(held, attracted.placement(), hold_policy());
    Kernel kernel(held, attracted.placement());
    const auto area = [](const SqueezeReport& report) {
        return to_mm(report.after.width) * to_mm(report.after.height);
    };
    const Snapshot seated = kernel.snapshot();
    SqueezeReport plain = squeeze_best(kernel, settings);
    const Snapshot plain_state = kernel.snapshot();
    kernel.restore(seated);
    result.balance = balance_faces(kernel, settings.pitch, static_cast<Nm>(constants::sink_reach.value));
    SqueezeReport balanced = squeeze_best(kernel, settings);
    result.plain_area = area(plain);
    result.balanced_area = area(balanced);
    result.balanced = result.balanced_area < result.plain_area ||
                      (result.balanced_area == result.plain_area && balanced.routed_after < plain.routed_after);
    if (!result.balanced) kernel.restore(plain_state);
    result.squeeze = result.balanced ? std::move(balanced) : std::move(plain);
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
    text << "OWNERSHIP:";
    for (const auto& [tie, parts] : ties) text << " " << parts << " " << tie;
    text << "; " << binding.unresolved.size() << " off-sheet owners not found\n"
         << "  parts within reach of the pin they serve: " << reached_before << " to " << reached_after << " of "
         << binding.problem.constraints.soft_gaps.size() << "\n";
    for (std::size_t index = 0; index < stragglers.size() && index < straggler_rows; ++index) {
        const auto& rule = binding.problem.constraints.soft_gaps[stragglers[index].second];
        text << "    " << binding.problem.parts[rule.member].reference << " is " << to_mm(stragglers[index].first)
             << " mm from " << binding.problem.parts[rule.anchor].reference << " (reach " << to_mm(rule.reach) << " mm)\n";
    }
    text << "OWNER HOLDS: " << holds << " small parts held to the pin they serve; farthest " << to_mm(held_before)
         << " mm before, " << to_mm(held_after) << " mm after\n";
    text << "OWNER ATTRACTION: " << result.attract.wanted << " parts wanted a seat at the pin they serve, "
         << result.attract.seated << " seated (" << result.attract.to_rear << " to the rear, "
         << result.attract.moved_aside << " blockers moved aside); preferences met "
         << result.attract.met_before << " to " << result.attract.met_after << " of "
         << binding.problem.constraints.soft_gaps.size() << "\n"
         << "  routed airwire " << to_mm(result.attract.routed_before) << " to "
         << to_mm(result.attract.routed_after) << " mm\n"
         << "FACE BALANCE: " << result.balance.flipped << " of " << result.balance.sets
         << " movable clusters mirrored to the rear (" << result.balance.parts << " parts); courtyard area top "
         << result.balance.top_before << " to " << result.balance.top_after << " mm2, rear "
         << result.balance.rear_before << " to " << result.balance.rear_after << " mm2\n"
         << "  squeezed area with mirroring " << result.balanced_area << " mm2, without " << result.plain_area
         << " mm2; kept the " << (result.balanced ? "mirrored" : "unmirrored") << " board\n"
         << squeeze_summary(result.squeeze) << "FACES: top "
         << binding.placement.size() - result.rear_before << " to " << binding.placement.size() - result.rear_after
         << ", rear " << result.rear_before << " to " << result.rear_after << "\n";
    result.report = text.str();
    return result;
}

}
