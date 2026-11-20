#pragma once

#include "schgen/pcb_model.hpp"
#include "schgen/execution_accounting.hpp"
#include "schgen/thermal_checks.hpp"

namespace schgen {

namespace labels {
struct LabelSeating;
}

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
struct PcbEmitPolicy {
    bool interface_reference_labels_only = false, labels = true;
    FootprintAliasFacts footprint_aliases;
    ConnectorFacts connectors;
    ProjectStrings connector_descriptions, header_descriptions, switch_descriptions;
    ThermalCopperFacts thermal_copper;
    RegulatorFacts regulators;
    std::vector<ThermalPourNeed> thermal_credit_needs;
    IsolationFacts isolation;
    double gnd_plane_edge_back = 0.5, gnd_plane_clearance = 0.3;
    double pour_clearance = 0.2, zone_min_thickness = 0.25;
    double thermal_via_size = 0.6, thermal_via_drill = 0.3;
    double thermal_via_clear = 0.25, hole_samenet_pad = 0.1;
    double thermal_via_h2h = 0.45, thermal_via_edge = 1.0;
    double thermal_via_spacing = 0.8, thermal_lattice_pitch = 0.25;
    double default_track = 0.2032, default_clearance = 0.15;
    double power_track = 0.4, power_clearance = 0.2, minimum_hole_to_hole = 0.25;
    double stack_thickness = 1.6;
    std::string ground_layer = "In1.Cu", power_class = "POWER", board_stem;
    ModelOverrideFacts model_overrides;
};
// Default constants are project independent. Header/switch descriptions are
// taken only from the explicitly supplied project's already-parsed metadata.
const PcbEmitPolicy &default_pcb_emit_policy();
PcbEmitPolicy pcb_emit_policy(const ProjectConfig &);
std::optional<PcbThermalCopperSpec> thermal_copper_spec(const PcbEmitPolicy &, const std::string &value);

struct PcbEmissionResult {
    Sexpr document;
    std::string pcb;
    std::vector<std::string> diagnostics;
    // One record per actual fallback engagement, in source order. Caller may
    // merge these into its explicit ledger/census; no process-global counters.
    std::vector<std::string> fallback_events;
    int hidden_bottom_references = 0, moved_references = 0;
    QuantizationCounts quantization_engagements;
};
// Complete board assembly: outline/stackup, thermal/isolation copper, embedded
// footprints, descriptors/refdes placement and actual model escape copper.
// Reuses native emit/embed_fp/pcb_scan/turn/pack/UUID kernels throughout.
// With an external sink, it owns precision observations (including a throwing
// prefix); the returned precision receipt is empty to prevent double imports.
PcbEmissionResult render_pcb(const PcbModel &, const PcbEmitPolicy & = default_pcb_emit_policy(),
                            QuantizationCounts* = nullptr, const labels::LabelSeating* = nullptr);
PcbEmissionResult write_pcb(const PcbModel &, const std::filesystem::path &,
                            const PcbEmitPolicy & = default_pcb_emit_policy(),
                            QuantizationCounts* = nullptr);

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
                               const PcbEmitPolicy & = default_pcb_emit_policy(),
                               QuantizationCounts* = nullptr);
void write_pcb_project(const PcbModel &, const std::filesystem::path &,
                       const PcbEmitPolicy & = default_pcb_emit_policy(),
                       QuantizationCounts* = nullptr);
std::string render_pcb_design_rules(const PcbModel &,
                                    const PcbEmitPolicy & = default_pcb_emit_policy());
void write_pcb_design_rules(const PcbModel &, const std::filesystem::path &,
                            const PcbEmitPolicy & = default_pcb_emit_policy());

Box4 ground_plane_box(double origin_x, double origin_y, double width, double height, double edge_back);
Box4 thermal_pour_local(const Box4& pour, bool mirror);
std::vector<std::pair<double, double>> thermal_pour_corners(const Box4& local, double rotation, double x, double y,
                                                            const Box4& plane);
Box4 thermal_pour_extent(const Box4& pour, bool mirror, double rotation, double x, double y, const Box4& plane);
} // namespace schgen
