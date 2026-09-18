#pragma once
#include "schgen/power_checks.hpp"
#include <chrono>

namespace schgen {
struct SpiceCheck {
    std::string name, sheet, kind, detail;
    double value = 0;
    std::string unit;
    std::optional<double> lo, hi;
    std::string engine = "analytic";
    std::optional<double> spice_value;
    bool ok() const;
};
struct SpiceResult {
    std::vector<SpiceCheck> checks;
    std::vector<std::string> notes;
    std::string engine = "analytic (closed-form linear solutions)";
    std::vector<std::string> errors() const;
    bool ok() const;
};
SpiceResult extract_spice_checks(const std::vector<ProjectCircuit>&,
    const PowerPolicy& = default_power_policy());
std::optional<std::filesystem::path> ngspice_available();
struct SpiceRunOptions {
    bool allow_ngspice = true;
    // nullopt searches PATH; an explicit executable is never a shell command.
    std::optional<std::filesystem::path> executable;
    std::chrono::milliseconds timeout{30000};
};
void run_ngspice_crosschecks(SpiceResult&, const SpiceRunOptions& = {});
std::string spice_report(const SpiceResult&, bool ngspice_present);
SpiceResult run_spice_checks(const std::vector<ProjectCircuit>&,
    const std::filesystem::path& report_dir, const SpiceRunOptions& = {},
    const PowerPolicy& = default_power_policy());
JsonNode spice_result_json(const SpiceResult&);
}  // namespace schgen
