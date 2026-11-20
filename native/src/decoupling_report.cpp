#include "schgen/decoupling_report.hpp"

#include "schgen/placement_report.hpp"
#include "schgen/project.hpp"

#include <algorithm>
#include <iterator>
#include <tuple>

namespace schgen {
namespace {

std::vector<std::string_view> decoupling_roles() {
    std::vector<std::string_view> roles = rules::roles_with(&rules::RoleRule::bypasses_pin);
    for (const rules::RoleRule& row : rules::role_catalogue())
        if (row.loop_capacitor && std::find(roles.begin(), roles.end(), row.name) == roles.end()) roles.push_back(row.name);
    return roles;
}

bool bypass_role(const std::string& role) { return rules::role_rule(role).bypasses_pin; }

std::string join_pads(const std::vector<std::string>& pads) {
    std::string out;
    for (const std::string& pad : pads) out += (out.empty() ? "" : "+") + pad;
    return out;
}

std::vector<std::pair<std::string, std::string>> intent_keys(const layout::AuthoredIntent& intent) {
    const auto roles = decoupling_roles();
    std::vector<std::pair<std::string, std::string>> keys;
    for (const layout::ServiceInput& service : intent.services)
        if (std::find(roles.begin(), roles.end(), service.role) != roles.end()) keys.emplace_back(service.part, service.role);
    std::sort(keys.begin(), keys.end());
    return keys;
}

auto row_key(const DecouplingRow& row) { return std::tie(row.sheet, row.cap, row.role, row.owner, row.pin); }

}

std::size_t DecouplingReport::failures(std::string_view role) const {
    return static_cast<std::size_t>(std::count_if(rows.begin(), rows.end(), [&](const DecouplingRow& row) { return row.judged && row.role == role && !row.pass; }));
}

std::size_t DecouplingReport::failures() const {
    return static_cast<std::size_t>(std::count_if(rows.begin(), rows.end(), [](const DecouplingRow& row) { return row.judged && !row.pass; }));
}

DecouplingReport build_decoupling_report(const rules::RuleContext& context) {
    const auto roles = decoupling_roles();
    const auto unresolved = context.unresolved(roles);
    if (!unresolved.empty()) {
        std::string why = "decoupling report: unresolved purpose rows:";
        for (const rules::Finding& finding : unresolved) why += " " + finding.subject + " " + finding.detail + ";";
        throw ProjectError(why);
    }
    DecouplingReport report;
    for (const rules::Service* service : context.serving(roles)) {
        const PcbCheckInstance& cap = context.parts()[service->part];
        const PcbCheckInstance& owner = context.parts()[service->owner];
        DecouplingRow row{cap.sheet, owner.ref, join_pads(service->pads), context.net_at(service->owner, service->pads.front()),
                          cap.ref, cap.value, service->role, 0, rules::role_rule(service->role).reach->value, false, false, false, false};
        if (bypass_role(service->role)) {
            const rules::BypassVerdict verdict = rules::bypass_verdict(context, *service);
            row.gap = verdict.gap;
            row.beside = verdict.beside;
            row.under = verdict.under;
            row.judged = true;
            row.pass = !verdict.finding.has_value();
        } else {
            row.gap = *context.pad_gap(service->owner, service->pads, service->part);
        }
        report.rows.push_back(std::move(row));
    }
    std::sort(report.rows.begin(), report.rows.end(), [](const DecouplingRow& a, const DecouplingRow& b) {
        return std::tie(a.sheet, a.owner, a.pin, a.cap, a.role) < std::tie(b.sheet, b.owner, b.pin, b.cap, b.role);
    });
    return report;
}

std::string DecouplingReport::text() const {
    std::string out = "decoupling\torder=sheet,owner,pin,cap\n" +
                      placement_report_row({"sheet", "owner", "pin", "net", "cap", "value", "role", "gap", "reach", "verdict"}) + "\n";
    for (const DecouplingRow& row : rows)
        out += placement_report_row({row.sheet, row.owner, row.pin, row.net, row.cap, row.value, row.role,
                                     placement_report_number(row.gap), placement_report_number(row.reach), !row.judged ? "unjudged" : row.pass ? "PASS" : "FAIL"}) + "\n";
    return out;
}

std::vector<std::string> verify_decoupling_report(const DecouplingReport& report, const rules::RuleContext& context,
                                                  const layout::AuthoredIntent& intent, const rules::RuleResult& bypass_rule) {
    std::vector<std::string> errors;
    std::vector<std::pair<std::string, std::string>> listed;
    for (const DecouplingRow& row : report.rows) listed.emplace_back(row.cap, row.role);
    std::sort(listed.begin(), listed.end());
    const auto wanted = intent_keys(intent);
    std::vector<std::pair<std::string, std::string>> missing, extra;
    std::set_difference(wanted.begin(), wanted.end(), listed.begin(), listed.end(), std::back_inserter(missing));
    std::set_difference(listed.begin(), listed.end(), wanted.begin(), wanted.end(), std::back_inserter(extra));
    for (const auto& [cap, role] : missing) errors.push_back("purpose row " + cap + " " + role + " is missing from the report");
    for (const auto& [cap, role] : extra) errors.push_back("report row " + cap + " " + role + " has no purpose row");
    for (std::size_t first = 0; first < report.rows.size(); ++first)
        for (std::size_t second = first + 1; second < report.rows.size(); ++second)
            if (row_key(report.rows[first]) == row_key(report.rows[second]))
                errors.push_back("report row " + report.rows[first].cap + " " + report.rows[first].role + " on " + report.rows[first].owner + "." +
                                 report.rows[first].pin + " appears twice");
    const auto roles = decoupling_roles();
    std::vector<rules::BypassVerdict> measured;
    const auto serving = context.serving(roles);
    for (const DecouplingRow& row : report.rows) {
        const rules::Service* service = nullptr;
        for (const rules::Service* candidate : serving)
            if (context.parts()[candidate->part].ref == row.cap && context.parts()[candidate->part].sheet == row.sheet && candidate->role == row.role &&
                context.parts()[candidate->owner].ref == row.owner && join_pads(candidate->pads) == row.pin)
                service = candidate;
        if (!service) {
            errors.push_back("report row " + row.cap + " " + row.role + " on " + row.owner + "." + row.pin + " matches no serving capacitor");
            continue;
        }
        const double gap = *context.pad_gap(service->owner, service->pads, service->part);
        if (gap != row.gap) errors.push_back("report row " + row.cap + " on " + row.owner + "." + row.pin + " has gap " + placement_report_number(row.gap) +
                                             " where the rule measured " + placement_report_number(gap));
        if (bypass_role(row.role)) measured.push_back({row.gap, row.beside, row.under, std::nullopt});
    }
    const std::size_t bypass_rows = measured.size();
    if (bypass_rows != bypass_rule.checked)
        errors.push_back("report has " + std::to_string(bypass_rows) + " bypass rows where the rule checked " + std::to_string(bypass_rule.checked));
    std::size_t bypass_failures = 0;
    std::vector<std::string> failed_labels;
    for (const DecouplingRow& row : report.rows)
        if (bypass_role(row.role) && !row.pass) {
            ++bypass_failures;
            failed_labels.push_back(row.cap + " (" + row.sheet + ")");
        }
    if (bypass_failures != bypass_rule.findings.size())
        errors.push_back("report has " + std::to_string(bypass_failures) + " failing bypass rows where the rule found " + std::to_string(bypass_rule.findings.size()));
    std::vector<std::string> rule_labels;
    for (const rules::Finding& finding : bypass_rule.findings) rule_labels.push_back(finding.subject);
    std::sort(failed_labels.begin(), failed_labels.end());
    std::sort(rule_labels.begin(), rule_labels.end());
    if (failed_labels != rule_labels) errors.push_back("failing bypass rows differ from the rule's findings");
    const std::string note = measured.empty() ? std::string() : rules::bypass_note(measured, rules::role_rule(rules::roles_with(&rules::RoleRule::bypasses_pin).front()).reach->value);
    const std::string rule_note = bypass_rule.measurements.empty() ? std::string() : bypass_rule.measurements.front();
    if (note != rule_note) errors.push_back("bypass distances differ from the rule's measurement: report '" + note + "' rule '" + rule_note + "'");
    return errors;
}

}
