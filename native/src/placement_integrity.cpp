#include "schgen/placement_integrity.hpp"

#include "schgen/pcb_scan.hpp"
#include "schgen/stackup.hpp"

#include <filesystem>
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
    const std::string name = std::filesystem::path(instance.mod->source).filename().string();
    const auto starts = [](const std::string& text, const char* head) { return text.rfind(head, 0) == 0; };
    return starts(name, "MountingHole") || starts(name, "Fiducial") || starts(instance.sheet, "som_j");
}

PlacementIntegrityResult check_placement_integrity(const PcbCheckInput& input, const PcbModel& model,
                                                   const layout::AuthoredIntent& intent) {
    PlacementIntegrityResult result;
    const rules::RuleContext context(input, model, board_stackup(), intent);
    for (const auto& entry : rules::rule_book()) {
        result.rules.push_back(entry.check(context));
        const rules::RuleResult& judged = result.rules.back();
        if (judged.rule->enforcement == rules::Enforcement::gate && !judged.findings.empty()) result.ok = false;
    }
    return result;
}

const rules::RuleResult& PlacementIntegrityResult::of(std::string_view id) const {
    for (const auto& judged : rules)
        if (judged.rule->id == id) return judged;
    throw std::out_of_range("placement integrity: no rule named " + std::string(id));
}

std::string PlacementIntegrityResult::summary() const {
    std::ostringstream text;
    text << "PLACEMENT INTEGRITY GATE: " << (ok ? "PASS" : "FAIL") << "\n";
    for (const auto& judged : rules)
        text << "  " << judged.rule->area << "/" << judged.rule->id << ": checked " << judged.checked << ", findings "
             << judged.findings.size() << " [" << rules::enforcement_name(judged.rule->enforcement) << "]\n";
    for (const auto& judged : rules) {
        const bool gate = judged.rule->enforcement == rules::Enforcement::gate;
        for (const auto& finding : judged.findings)
            text << "    " << (gate ? "FAIL " : "FOUND ") << judged.rule->id << ": " << finding.subject << " "
                 << finding.detail << "\n";
    }
    for (const auto& judged : rules)
        for (const auto& row : judged.measurements) text << "    NOTE " << judged.rule->id << ": " << row << "\n";
    return text.str();
}

}
