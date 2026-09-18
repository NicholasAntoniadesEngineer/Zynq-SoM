#pragma once

#include "schgen/thermal_checks.hpp"

namespace schgen {

struct PartRatings {
    std::string kind;
    std::optional<double> v_max, i_max, p_max;
    std::optional<std::string> tol, dielectric;
    std::optional<double> temp_max, vin_max;
    std::string source;
};
using PartRatingsTable = std::vector<std::pair<std::string, PartRatings>>;
const PartRatingsTable& default_part_ratings();
// Data-only replacement for from_part_module: receive RATINGS itself. No
// execution/import. Null/non-object/missing-or-empty kind returns no rating.
std::optional<PartRatings> part_ratings_from_json(const JsonNode&);
const PartRatings* ratings_for_part(const CircuitPartIr&, const PartRatingsTable& = default_part_ratings());
std::optional<double> parse_resistor_ohms(const std::string&);
struct PartRulePolicy { double derate_mlcc = 2.0, derate_c0g = 1.5, derate_elec = 1.5, derate_res = 2.0; };
inline constexpr PartRulePolicy default_part_rule_policy{};
double capacitor_derating(const PartRatings&, const PartRulePolicy& = default_part_rule_policy);
struct PartCheckResult {
    std::vector<std::string> findings, notes, unspecced;
    ModelWaivers waived;
    std::size_t checked = 0;
    bool ok() const { return findings.empty(); }
};
PartCheckResult analyze_part_rules(const std::vector<ProjectCircuit>& sheets, const PowerCheckResult& power,
    const PartRatingsTable& ratings = default_part_ratings(), const PartRulePolicy& policy = default_part_rule_policy,
    const PowerPolicy& power_policy = default_power_policy());
PartCheckResult analyze_part_rules(const std::vector<ProjectCircuit>& sheets,
    const PartRatingsTable& ratings = default_part_ratings(), const PartRulePolicy& policy = default_part_rule_policy,
    const PowerPolicy& power_policy = default_power_policy());
std::string part_rules_report(const PartCheckResult&, const PartRulePolicy& = default_part_rule_policy);
PartCheckResult run_part_checks(const std::vector<ProjectCircuit>& sheets, const std::filesystem::path& reports_dir,
    const PowerCheckResult* power = nullptr, const PartRatingsTable& ratings = default_part_ratings(),
    const PartRulePolicy& policy = default_part_rule_policy, const PowerPolicy& power_policy = default_power_policy());
JsonNode part_result_json(const PartCheckResult&);
PartCheckResult part_result_from_json(const JsonNode&);
JsonNode part_ratings_json(const PartRatings&);

}  // namespace schgen
