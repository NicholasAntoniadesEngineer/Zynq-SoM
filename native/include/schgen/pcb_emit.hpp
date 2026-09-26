#pragma once

#include "schgen/pcb_model.hpp"
#include "schgen/thermal_checks.hpp"

namespace schgen {

class PcbEmissionError : public std::runtime_error {
  public:
    using std::runtime_error::runtime_error;
};
struct PcbThermalCopperSpec {
    std::vector<std::pair<double, double>> via_sites;
    std::size_t max_vias = 0;
    Box4 pour;
    std::vector<std::string> pour_layers;
    std::string cite;
};
struct PcbModelOverride {
    std::string value, footprint, path;
    double rotation_z = 0;
};
struct PcbEmitPolicy {
    ProjectStrings footprint_aliases, connector_mating_faces;
    ProjectStrings connector_descriptions, header_descriptions, switch_descriptions;
    std::vector<std::pair<std::string, PcbThermalCopperSpec>> thermal_copper;
    std::vector<ThermalPourNeed> thermal_credit_needs;
    std::vector<std::string> isolation_prefixes;
    double gnd_plane_edge_back = 0.5, gnd_plane_clearance = 0.3;
    double pour_clearance = 0.2, zone_min_thickness = 0.25, isolation_margin = 0.6;
    double thermal_via_size = 0.6, thermal_via_drill = 0.3;
    double thermal_via_clear = 0.25, hole_samenet_pad = 0.1;
    double thermal_via_h2h = 0.45, thermal_via_edge = 1.0;
    double thermal_via_spacing = 0.8, thermal_lattice_pitch = 0.25;
    double default_track = 0.2032, default_clearance = 0.15;
    double power_track = 0.4, power_clearance = 0.2, minimum_hole_to_hole = 0.25;
    double stack_thickness = 1.6;
    std::string ground_layer = "In1.Cu", power_class = "POWER";
    std::vector<PcbModelOverride> model_overrides;
};
const std::vector<PcbModelOverride>& project_pcb_model_overrides();
// Default constants are project independent. Header/switch descriptions are
// taken only from the explicitly supplied project's already-parsed metadata.
const PcbEmitPolicy &default_pcb_emit_policy();
PcbEmitPolicy pcb_emit_policy(const ProjectConfig &);

struct PcbEmissionResult {
    Sexpr document;
    std::string pcb;
    std::vector<std::string> diagnostics;
    // One record per actual fallback engagement, in source order. Caller may
    // merge these into its explicit ledger/census; no process-global counters.
    std::vector<std::string> fallback_events;
    int hidden_bottom_references = 0, moved_references = 0;
};
// Complete board assembly: outline/stackup, thermal/isolation copper, embedded
// footprints, descriptors/refdes placement and actual model escape copper.
// Reuses native emit/embed_fp/pcb_scan/turn/pack/UUID kernels throughout.
PcbEmissionResult render_pcb(const PcbModel &, const PcbEmitPolicy & = default_pcb_emit_policy());
PcbEmissionResult write_pcb(const PcbModel &, const std::filesystem::path &,
                            const PcbEmitPolicy & = default_pcb_emit_policy());

// JsonNode stores all numbers as doubles. Preserve number-token metadata so
// unrelated project fields retain Python's integer/float spelling, including
// integer values beyond double's exact range. Clear a path's integer token if
// editing that value through data (or supply a new document without metadata).
struct PcbProjectDocument {
    JsonNode data;
    std::set<std::string> float_paths; // JSON Pointer paths; explicit metadata
    std::map<std::string, std::string> integer_tokens;
};
PcbProjectDocument read_pcb_project(const std::filesystem::path &);
std::string render_pcb_project(const PcbModel &, const std::string &filename,
                               const PcbProjectDocument *existing = nullptr,
                               const PcbEmitPolicy & = default_pcb_emit_policy());
void write_pcb_project(const PcbModel &, const std::filesystem::path &,
                       const PcbEmitPolicy & = default_pcb_emit_policy());
std::string render_pcb_design_rules(const PcbModel &,
                                    const PcbEmitPolicy & = default_pcb_emit_policy());
void write_pcb_design_rules(const PcbModel &, const std::filesystem::path &,
                            const PcbEmitPolicy & = default_pcb_emit_policy());

} // namespace schgen
