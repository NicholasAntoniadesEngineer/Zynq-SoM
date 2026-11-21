#include "schgen/placement_integrity.hpp"

#include <algorithm>

#include "schgen/pcb_scan.hpp"
#include "schgen/stackup.hpp"

#include <sstream>
#include <stdexcept>

namespace schgen {

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
    const PartClass part_class = part_class_of(instance);
    return part_class == PartClass::mounting_hole || part_class == PartClass::fiducial ||
           part_class == PartClass::module_connector;
}

PlacementIntegrityResult check_placement_integrity(const PcbCheckInput& input, const PcbModel& model,
                                                   const layout::AuthoredIntent& intent) {
    PlacementIntegrityResult result;
    const rules::RuleContext context(input, model, board_stackup(), intent);
    for (const auto& entry : rules::rule_book()) {
        result.rules.push_back(entry.check(context));
        const rules::RuleResult& judged = result.rules.back();
        if (judged.rule->enforcement != rules::Enforcement::gate || judged.findings.empty()) continue;
        result.ok = false;
        if (judged.rule->met_by == rules::Stage::placement) result.placement_ok = false;
    }
    return result;
}

const rules::RuleResult& PlacementIntegrityResult::of(std::string_view id) const {
    for (const auto& judged : rules)
        if (judged.rule->id == id) return judged;
    throw std::out_of_range("placement integrity: no rule named " + std::string(id));
}

std::vector<std::string> breach_provenance(const PlacementIntegrityResult& entry, const PlacementIntegrityResult& final,
                                           const std::string& earlier_step, const std::string& this_step) {
    std::vector<std::string> lines;
    for (const auto& judged : final.rules) {
        if (judged.rule->enforcement != rules::Enforcement::gate) continue;
        const auto before = std::find_if(entry.rules.begin(), entry.rules.end(),
                                         [&](const rules::RuleResult& row) { return row.rule == judged.rule; });
        for (const auto& finding : judged.findings) {
            const bool inherited = before != entry.rules.end() &&
                std::any_of(before->findings.begin(), before->findings.end(),
                            [&](const rules::Finding& row) { return row.subject == finding.subject; });
            lines.push_back(std::string(judged.rule->id) + ": " + finding.subject + " " +
                            (inherited ? "already breached when " + earlier_step + " handed over the placement"
                                       : "introduced by " + this_step));
        }
    }
    return lines;
}

std::string PlacementIntegrityResult::summary(rules::Stage reached) const {
    std::ostringstream text;
    const bool laid_out = reached == rules::Stage::layout;
    text << "PLACEMENT INTEGRITY GATE" << (laid_out ? "" : " (starting placement; rules the layout stage meets are listed, not judged)")
         << ": " << (ok_at(reached) ? "PASS" : "FAIL") << "\n";
    for (const auto& judged : rules)
        text << "  " << judged.rule->area << "/" << judged.rule->id << ": checked " << judged.checked << ", findings "
             << judged.findings.size() << " [" << rules::enforcement_name(judged.rule->enforcement) << "]\n";
    for (const auto& judged : rules) {
        const bool gate = judged.rule->enforcement == rules::Enforcement::gate &&
                          (laid_out || judged.rule->met_by == rules::Stage::placement);
        for (const auto& finding : judged.findings)
            text << "    " << (gate ? "FAIL " : "FOUND ") << judged.rule->id << ": " << finding.subject << " "
                 << finding.detail << "\n";
    }
    for (const auto& judged : rules)
        for (const auto& row : judged.measurements) text << "    NOTE " << judged.rule->id << ": " << row << "\n";
    return text.str();
}

}
