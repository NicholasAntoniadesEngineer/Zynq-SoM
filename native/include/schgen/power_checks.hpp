#pragma once

#include "schgen/project.hpp"

#include <map>
#include <optional>

namespace schgen {

class ModelCheckError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

struct PowerSource { double volts = 0.0, amps = 0.0; std::string note; };
struct PowerRail { std::optional<double> volts; std::string basis; };
struct PowerInlet { std::string rail, bulk; };
struct PowerPolicy {
    RegulatorFacts regulators;
    ZenerFacts zeners;
    ReferencePinFacts reference_pins;
    std::vector<std::pair<std::string, PowerSource>> sources;
    std::vector<std::pair<std::string, PowerRail>> rails;
    std::optional<PowerInlet> inlet;
    std::vector<std::string> module_sheets, module_rails;
    std::string module_rails_basis;
    ProjectStrings known_deferred;
};
const PowerPolicy& default_power_policy();
std::string catalogue_part_number(const CircuitPartIr& part);
std::optional<double> parse_si_value(const std::string& text);
std::optional<double> rail_volts(const std::string& name, const PowerPolicy& policy);

struct FeedbackDivider {
    std::string top_ref, bottom_ref;
    double top_ohms = 0.0, bottom_ohms = 0.0, volts = 0.0;
};
std::optional<FeedbackDivider> feedback_divider(const CircuitSheetIr& circuit, const std::string& ref,
    const std::string& vout, double vref);

struct PowerReg {
    int n = 0;
    std::string sheet, ref, value, kind, vin, vout;
    double limit_a = 0.0, eff = 1.0;
    std::string note;
    double i_out = 0.0, i_in = 0.0;
};
struct PowerDraw { std::string sheet; double amps = 0.0; std::string note; };
struct PowerBridge { std::string sheet, ref, from, to; };
struct PowerCheckResult {
    std::vector<PowerReg> regs;
    std::vector<std::pair<std::string, double>> rails;
    std::vector<std::pair<std::string, std::vector<PowerDraw>>> draws;
    std::vector<PowerBridge> bridges;
    std::vector<std::string> errors, warnings, findings, notes;
    std::vector<std::pair<std::string, double>> source_load;
    bool ok() const { return errors.empty(); }
};

// Caller-owned sheet names, circuits and metadata are authoritative. No part
// catalog, authoring module, library lookup, global project or file is consulted.
// Detection only: regs (zero i_out/i_in), detection errors and bridges; all
// other result fields remain empty. Does not visit loads or run rail/audit work.
PowerCheckResult detect_power_regulators(const std::vector<ProjectCircuit>& sheets,
    const PowerPolicy& policy = default_power_policy());
PowerCheckResult analyze_power(const std::vector<ProjectCircuit>& sheets,
    const PowerPolicy& policy);
std::string power_report(const PowerCheckResult&, const std::string& board,
    const PowerPolicy& policy);  // No final newline.
std::string power_svg(const PowerCheckResult&, const std::string& board,
    const PowerPolicy& policy);  // One final newline.
// Report publication is separate from analysis and uses explicit destinations.
PowerCheckResult run_power_checks(const std::vector<ProjectCircuit>& sheets, const std::string& board,
    const std::filesystem::path& reports_dir, const std::filesystem::path& docs_dir,
    const PowerPolicy& policy);
JsonNode power_result_json(const PowerCheckResult&);
// Strict, data-only inverse transport. Does not recompute any caller values.
PowerCheckResult power_result_from_json(const JsonNode&);

}  // namespace schgen
