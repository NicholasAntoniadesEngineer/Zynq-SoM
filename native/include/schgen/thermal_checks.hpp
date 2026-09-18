#pragma once

#include "schgen/power_checks.hpp"
#include "schgen/sexpr.hpp"

namespace schgen {

inline constexpr double thermal_ambient_c = 50.0, thermal_margin_c = 10.0, thermal_buck_eff = 0.85;
struct ThermalSpec {
    double rth_ja = 0.0, tj_max = 0.0, rds_on = 0.0, eff = thermal_buck_eff;
    std::string package, cite;
    std::optional<double> rth_ja_pour;
    std::string pour_cite, pour_evidence;
    double rth_eff() const { return rth_ja_pour.value_or(rth_ja); }
};
struct ThermalPourNeed {
    std::string value_prefix;
    int min_vias = 0;
    double radius_mm = 0.0;
    std::vector<std::string> pour_layers;
};
struct ThermalFootprintSpec { std::string value_prefix, footprint_contains; ThermalSpec spec; };
struct ThermalPolicy {
    double ambient_c = thermal_ambient_c, margin_c = thermal_margin_c;
    std::vector<std::pair<std::string, ThermalSpec>> specs;
    std::vector<ThermalFootprintSpec> footprint_specs;
    std::vector<std::pair<std::string, ThermalPourNeed>> pour_needs;
};
const ThermalPolicy& default_thermal_policy();
const ThermalSpec* thermal_spec_for(const std::string& value, const std::string& footprint,
    const ThermalPolicy& policy = default_thermal_policy());
double thermal_dissipation(const std::string& kind, double v_in, double v_out, double i_out, const ThermalSpec&);
std::vector<std::string> thermal_pour_layers(const ThermalPourNeed&, const std::string& footprint_layer);

struct CopperZoneEvidence {
    std::string name, net_name;
    std::vector<std::string> layers;
    bool keepout = false, filled = false;
    std::array<double, 4> bbox{};
};
struct CopperViaEvidence { double x = 0.0, y = 0.0; std::string net_name; };
struct CopperPadEvidence { std::string name; double dx = 0.0, dy = 0.0, drill = 0.0; std::string net_name; };
struct CopperFootprintEvidence {
    std::string ref, value;
    double x = 0.0, y = 0.0;
    std::string layer;
    std::vector<CopperPadEvidence> pads;
};
struct ThermalCopper {
    std::string path;
    std::vector<CopperZoneEvidence> zones;
    std::vector<CopperViaEvidence> vias;
    std::size_t segments = 0;
    std::vector<CopperFootprintEvidence> footprints;
    std::set<std::string> net_names;
    bool gnd_plane(const std::string& layer = "In1.Cu") const;
    std::vector<const CopperFootprintEvidence*> instances(const std::string& value_prefix) const;
    std::size_t gnd_vias_within(double x, double y, double radius_mm) const;
    bool pour_at(double x, double y, const std::string& layer, const std::string& net = "GND") const;
};
// Same emitted zone/footprint/via scan as copper_debt.scan_board. This does not
// infer connectivity or copper area beyond the baseline's filled-zone bbox.
ThermalCopper scan_thermal_copper(const Sexpr& board, const std::string& source = "");
ThermalCopper scan_thermal_copper(const std::filesystem::path& pcb_path);
std::pair<bool, std::string> thermal_pour_evidence(const ThermalCopper*, const ThermalPourNeed&);

struct ThermalDevice {
    std::string sheet, ref, value, package, kind, vin, vout;
    double v_in = 0.0, v_out = 0.0, i_out = 0.0, pd = 0.0, rth_ja = 0.0;
    double tj = 0.0, tj_max = 0.0, margin = 0.0;
    std::string cite;
    double rth_bare = 0.0;
    std::string pour_cite;
    bool pour_granted = false;
    std::string evidence;
    bool over() const { return margin < 0.0; }
    bool poured() const { return pour_granted && rth_ja < rth_bare; }
};
using ModelWaivers = std::vector<std::pair<std::string, std::pair<std::string, std::string>>>;
struct ThermalCheckResult {
    std::vector<ThermalDevice> devices;
    std::vector<std::string> errors, findings;
    ModelWaivers waived;
    std::vector<std::string> notes;
    double ta = thermal_ambient_c, margin = thermal_margin_c;
    std::string copper_src;
    bool ok() const { return errors.empty(); }
};
ThermalCheckResult analyze_thermal(const std::vector<ProjectCircuit>& sheets,
    const PowerCheckResult& power, const ThermalCopper* copper = nullptr, const std::string& copper_src = "",
    const ThermalPolicy& policy = default_thermal_policy(), const PowerPolicy& power_policy = default_power_policy());
ThermalCheckResult analyze_thermal(const std::vector<ProjectCircuit>& sheets,
    const ThermalCopper* copper = nullptr, const std::string& copper_src = "",
    const ThermalPolicy& policy = default_thermal_policy(), const PowerPolicy& power_policy = default_power_policy());
std::string thermal_report(const ThermalCheckResult&);
ThermalCheckResult run_thermal_checks(const std::vector<ProjectCircuit>& sheets,
    const std::filesystem::path& reports_dir, const PowerCheckResult* power = nullptr,
    const std::optional<std::filesystem::path>& pcb_path = std::nullopt,
    const std::filesystem::path& repository_root = {},
    const ThermalPolicy& policy = default_thermal_policy(), const PowerPolicy& power_policy = default_power_policy());
JsonNode thermal_result_json(const ThermalCheckResult&);
JsonNode thermal_copper_json(const ThermalCopper&);
ThermalCheckResult thermal_result_from_json(const JsonNode&);
ThermalCopper thermal_copper_from_json(const JsonNode&);

}  // namespace schgen
