#include "schgen/placement_integrity.hpp"

#include "schgen/layout_adapter.hpp"

#include "schgen/named_constant.hpp"
#include "schgen/pack.hpp"
#include "schgen/pcb_escape.hpp"
#include "schgen/pcb_scan.hpp"
#include "schgen/stackup.hpp"

#include <algorithm>
#include <filesystem>
#include <sstream>

namespace schgen {
namespace {

inline constexpr NamedConstant corridor_tolerance{"corridor_tolerance", 1e-3, "mm", "policy",
    "an escape-corridor intrusion shallower than this is below fabrication resolution and is not judged"};

double intrusion(const Box4& part, const Box4& corridor) {
    return std::min({part.x1 - corridor.x0, corridor.x1 - part.x0, part.y1 - corridor.y0, corridor.y1 - part.y0});
}

}

std::string controlled_net(const PcbCheckInstance& instance, const PcbModel& model) {
    for (const auto& [pad, net] : instance.pad_nets) {
        const auto klass = model.netclass_of.find(net.second);
        if (klass == model.netclass_of.end()) continue;
        const auto geometry = model.classes.find(klass->second);
        if (geometry != model.classes.end() && geometry->second.has_value())
            return net.second + " (class " + klass->second + ")";
    }
    return {};
}

bool drilled_part(const PcbCheckInstance& instance) {
    return instance.mod && has_thru_pads_from_text(instance.mod->bytes);
}

bool module_clearance_exempt(const PcbCheckInstance& instance) {
    if (!instance.mod) return false;
    const std::string name = std::filesystem::path(instance.mod->source).filename().string();
    const auto starts = [](const std::string& text, const char* head) { return text.rfind(head, 0) == 0; };
    return starts(name, "MountingHole") || starts(name, "Fiducial") || starts(instance.sheet, "som_j");
}

PlacementIntegrityResult check_placement_integrity(const PcbCheckInput& input, const PcbModel& model) {
    PlacementIntegrityResult result;
    const Stackup& stackup = board_stackup();
    const auto& parts = input.model().insts;
    const auto module_connector = [](const PcbCheckInstance& instance) {
        return pcb_is_df40_part(instance.sheet, static_cast<int>(instance.pad_nets.size()));
    };
    std::vector<std::pair<std::string, Box4>> corridors;
    for (const auto& instance : parts) {
        if (!module_connector(instance)) continue;
        if (!instance.mod) {
            result.unresolved.push_back(instance.ref + ": module connector has no footprint, its escape corridor is unknown");
            continue;
        }
        corridors.emplace_back(instance.ref,
                               pcb_escape_corridor_board(*instance.mod, instance.x, instance.y, instance.rotation));
    }
    result.corridors = static_cast<int>(corridors.size());
    for (std::size_t index = 0; index < parts.size(); ++index) {
        const auto& instance = parts[index];
        const bool rear = instance.side == "bottom";
        const std::string net = controlled_net(instance, model);
        if (!net.empty()) {
            ++result.controlled_parts;
            if (!stackup.ground_referenced(rear)) {
                const CopperLayer& reference = stackup.reference_of(rear);
                result.unreferenced_controlled.push_back(
                    instance.ref + " (" + instance.sheet + ") carries impedance-controlled net " + net + " on the " +
                    (rear ? "rear" : "top") + " copper, whose neighbour " + reference.name + " is a " +
                    copper_role_name(reference.role) + " layer, not a ground plane");
            }
        }
        if (module_connector(instance)) continue;
        if (!instance.mod) {
            result.unresolved.push_back(instance.ref + ": no footprint, corridor clearance cannot be judged");
            continue;
        }
        const bool through = drilled_part(instance);
        const Box4 footprint{std::min(input.courtyard_at(index).x0, input.pad_bbox_at(index).x0),
                             std::min(input.courtyard_at(index).y0, input.pad_bbox_at(index).y0),
                             std::max(input.courtyard_at(index).x1, input.pad_bbox_at(index).x1),
                             std::max(input.courtyard_at(index).y1, input.pad_bbox_at(index).y1)};
        if (!rear && model.som_keepout && !module_clearance_exempt(instance)) {
            const Box4& module = *model.som_keepout;
            const double apart = std::max({module.x0 - footprint.x1, footprint.x0 - module.x1, module.y0 - footprint.y1,
                                           footprint.y0 - module.y1});
            if (apart < layout::constants::module_clearance.value - corridor_tolerance.value) {
                std::ostringstream row;
                row << instance.ref << " (" << instance.sheet << ") is " << apart << " mm from the module body; "
                    << layout::constants::module_clearance.value << " mm is required";
                result.module_intrusions.push_back(row.str());
            }
        }
        if (!rear && !through) continue;
        ++result.corridor_subjects;
        const Box4 court = input.courtyard_at(index), pads = input.pad_bbox_at(index);
        const Box4 body{std::min(court.x0, pads.x0), std::min(court.y0, pads.y0), std::max(court.x1, pads.x1),
                        std::max(court.y1, pads.y1)};
        for (const auto& [owner, corridor] : corridors) {
            const double depth = intrusion(body, corridor);
            if (depth <= corridor_tolerance.value) continue;
            std::ostringstream row;
            row << instance.ref << " (" << instance.sheet << ") " << (through ? "through-hole" : "rear") << " part reaches "
                << depth << " mm into the escape corridor of " << owner;
            result.corridor_intrusions.push_back(row.str());
        }
    }
    result.ok = result.unreferenced_controlled.empty() && result.corridor_intrusions.empty() &&
                result.module_intrusions.empty() && result.unresolved.empty();
    return result;
}

std::string PlacementIntegrityResult::summary() const {
    std::ostringstream text;
    text << "PLACEMENT INTEGRITY GATE: " << (ok ? "PASS" : "FAIL") << "\n"
         << "  parts on impedance-controlled nets: " << controlled_parts << " (" << unreferenced_controlled.size()
         << " on a face with no ground plane beneath it)\n"
         << "  module escape corridors: " << corridors << "; rear and through-hole parts judged: " << corridor_subjects
         << " (" << corridor_intrusions.size() << " intruding)\n";
    text << "  top-face parts closer to the module body than its clearance: " << module_intrusions.size() << "\n";
    for (const auto* rows : {&unreferenced_controlled, &corridor_intrusions, &module_intrusions, &unresolved})
        for (const auto& row : *rows) text << "    FAIL " << row << "\n";
    return text.str();
}

}
