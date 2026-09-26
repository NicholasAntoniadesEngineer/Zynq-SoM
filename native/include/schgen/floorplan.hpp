#pragma once
#include "schgen/board_decision_policy.hpp"

#include "schgen/circuit.hpp"
#include "schgen/execution_accounting.hpp"
#include "schgen/constraints.hpp"
#include "schgen/json.hpp"
#include "schgen/link.hpp"
#include "schgen/occupancy.hpp"
#include "schgen/pcb_scan.hpp"
#include "schgen/power_checks.hpp"
#include "schgen/project.hpp"

#include <map>
#include <memory>
#include <filesystem>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace schgen {
struct FloorplanExperiment;

// Millimetres throughout. Box4 is x0,y0,x1,y1; Pose is x,y,width,height.
// Zone offsets are board-local until translated by the selected block pose.
// Containers whose source order affects ties use vectors; maps are sorted keys.
using FloorplanPoint = std::pair<double, double>;
using FloorplanOffsets = std::map<std::string, FloorplanPoint>;
using FloorplanRotations = std::map<std::string, double>;
using FloorplanShapeKey = std::pair<std::string, int>;

struct FloorplanPull {
    std::string to;
    double weight = 0.0;
    std::string face = "center";
    bool exclusive = false;
    std::string basis;
    // Keep omitted optional fields omitted when exporting a declarative seed.
    bool face_present = false, exclusive_present = false;
};
struct FloorplanAnchor {
    std::optional<std::string> side, near, layer;
    std::optional<FloorplanPull> pull;
};
struct FloorplanSpec {
    std::optional<FloorplanPoint> outline;  // nullopt == "auto"
    std::map<std::string, std::vector<std::string>> edges, ordered_edges;
    std::map<std::string, FloorplanAnchor> interior;
    std::string source;
    std::map<std::string, std::string> edge_of() const;
    std::map<std::string, int> edge_order() const;
    std::map<std::string, std::string> layer_of() const;
    std::set<std::string> names() const;
};
class FloorplanError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};
class FloorplanSpecError : public FloorplanError {
public:
    using FloorplanError::FloorplanError;
};

// A resolved footprint is parsed once. Providers retain the exact document,
// including duplicate/unnumbered pads and mirrored variants; consumers must not
// reconstruct copper from courtyard dimensions. Keys are opaque stable IDs
// (normally source paths), never interpreted as instructions or Python modules.
struct FloorplanFootprint {
    std::string source;
    Sexpr document;
};
struct FloorplanZoneShape {
    double w = 0.0, h = 0.0;
    FloorplanOffsets top_off, bot_off;
    FloorplanRotations extra_rot;
    std::string tag, side = "top";
    std::map<std::string, std::string> mirror;  // board ref -> footprint key
};
struct FloorplanZoneGeometry {
    std::map<std::string, FloorplanPoint> zone_box;
    std::map<std::string, FloorplanOffsets> top_off, bot_off;
    std::map<std::string, std::string> side_of, resolvable;
    std::map<std::string, Box4> bbox_of;
    std::map<std::string, std::vector<std::string>> refs_by_sheet;
    std::vector<std::string> mh_refs, deferred;
    FloorplanRotations conn_rot, zone_extra_rot;
    std::map<std::string, std::string> conn_edge;
    std::map<std::string, std::vector<FloorplanZoneShape>> shapes;
    std::set<std::string> mirror_refs;
};

// Shared contract transport for the compose stage. Domain logic stays native;
// JSON is only an input/report boundary, not a callback/evaluator escape hatch.
struct FloorplanTerm {
    std::string kind, sheet, subject, target_raw;
    std::optional<double> bound;
    std::string basis;
    bool enforced = false;
    std::vector<std::string> output_roles, out_refs;
    std::string target() const;
};
struct FloorplanTermIndex {
    std::vector<FloorplanTerm> hard, soft, na;
};
struct FloorplanLocalMetrics {
    std::vector<std::tuple<std::string, double, double>> offsets;
    std::vector<std::tuple<std::string, double, double, double, double>> pad_union;
    FloorplanPoint zone_wh{};
};
struct FloorplanTermEval {
    FloorplanTerm term;
    double measured = 0.0, bound = 0.0, margin = 0.0;
    bool ok = false;
    std::string note;
};
struct FloorplanComposeInput {
    FloorplanTermIndex index;
    std::map<std::string, FloorplanLocalMetrics> metrics;
    std::map<FloorplanShapeKey, FloorplanLocalMetrics> shape_metrics;
    std::map<std::pair<std::string, std::string>, int> channel_demand;
    std::vector<std::pair<std::string, Box4>> corridors;
    std::set<std::string> wired_participants;
};
struct FloorplanLegalizeVar {
    std::string name;
    double w = 0.0, h = 0.0;
    FloorplanPoint seed{};
    double x = 0.0, y = 0.0;
};
struct FloorplanLegalizeInput {
    double board_w = 0.0, board_h = 0.0;
    Box4 som_core_page;
    std::vector<std::pair<std::string, Box4>> fixed_rects;
    FloorplanTermIndex index;
    std::map<std::string, FloorplanLocalMetrics> metrics;
    std::map<std::string, FloorplanPoint> fixed_poses;
    std::map<std::pair<std::string, std::string>, int> channel_demand;
    std::map<std::string, Box4> som_j_rects;
    double clear = board_decision_policy::floorplan::clear;
    bool compact = false;
    FloorplanPoint origin{25.0, 25.0};
};

// Compose consumes resolved, selected-shape metrics. A rejected candidate
// leaves movable values intact and appends its reason to log. Malformed
// typed input throws; it must never be interpreted as a feasible candidate.
bool floorplan_legalize_compact(const FloorplanLegalizeInput& input,
    std::vector<FloorplanLegalizeVar>& movable, std::vector<std::string>& log);
bool floorplan_legalize_compact_accounted(const FloorplanLegalizeInput& input,
    std::vector<FloorplanLegalizeVar>& movable, std::vector<std::string>& log,
    QuantizationCounts& counts);
std::vector<FloorplanTermEval> floorplan_evaluate_terms(
    const FloorplanLegalizeInput& input, const FloorplanOffsets& poses);

using FloorplanRegulator = PowerReg;
using FloorplanSiPair = PairSignalSpec;
struct FloorplanConnector {
    std::string ref, value;
    double w = 0.0, h = 0.0;
};
struct FloorplanBlock {
    std::string name, kind;
    double x = 0.0, y = 0.0, w = 0.0, h = 0.0;
    std::string edge;
    std::vector<FloorplanConnector> conns;
    std::vector<std::string> reserved;
    int n_parts = 0;
    double area = 0.0;
    std::vector<std::pair<std::string, int>> j_aff;
    std::string zone;
    std::vector<int> notes;
    std::optional<int> order_hint;
    bool pinned = false;
    std::optional<FloorplanPull> pull;
    int shape_idx = 0;
    std::string side = "top", layer_pref = "top";
    Halo fanout_reach, fanout_inset;
    double cx() const { return x + w / 2; }
    double cy() const { return y + h / 2; }
};
struct FloorplanNote {
    int n = 0;
    std::string block, short_text, long_text;
};
struct FloorplanDecision {
    std::string step, kind, name;
    JsonNode value;  // heterogeneous diagnostic scalar, never executable
    std::vector<std::pair<std::string, JsonNode>> inputs;
    // Registered explanatory text, including formula/source and indentation.
    // Kept with the value so a replay never needs a process-global registry.
    int depth;  // Every decision construction supplies its nesting depth.
    std::string text;
};
struct FloorplanAccounting {
    std::vector<FloorplanDecision> decisions;
    std::vector<std::string> fallback_events;  // ordered, snapshot/replay exact
    std::map<std::string, std::size_t> quantization_engagements;
};
struct FloorplanPlan {
    SomOutline som;
    std::string som_source;
    double board_w = 0.0, board_h = 0.0, som_x = 0.0, som_y = 0.0;
    std::string outline_note;
    std::vector<FloorplanBlock> edge_blocks, interior_blocks;
    double factor = board_decision_policy::floorplan::small_part_routing_factor;
    std::vector<std::string> spilled, composition;
    int dec_count = 0;
    double dec_radius = 0.0;
    bool punch_free = true;
    FloorplanAccounting accounting;
};

// The PCB provider resolves each source footprint once and supplies both the
// zone model and fixed-part footprints. Missing resolutions remain explicit;
// missing keys referenced by geometry are errors, not guessed dimensions.
struct FloorplanInput {
    std::vector<CircuitSheetIr> sheets;
    LinkResult link;
    std::vector<FloorplanRegulator> regulators;
    // Researched per-net SI data for Markdown reporting. No per-kind fallback.
    std::vector<FloorplanSiPair> si_pairs;
    std::string si_source;
    SomOutline som;
    std::string som_source;
    std::optional<FloorplanSpec> spec;
    ProjectConfig project;
    SheetIndex sheet_index;
    FloorplanZoneGeometry geometry;
    std::map<std::string, FloorplanFootprint> footprints;
    std::map<std::string, std::string> footprint_of;  // source footprint -> key
    std::map<std::string, FloorplanPoint> courtyard_dims; // part library -> w,h
    std::map<std::string, std::string> impedance_net_classes; // net -> class
    FloorplanComposeInput compose;
    FloorplanPoint origin{25.0, 25.0};
    std::optional<FloorplanPoint> module_offset;  // explicit env/CLI override
    double cross_budget_k = 3.0;
    double place_clear = 0.5;  // explicit SCHGEN_PLACE_CLEAR equivalent
    // Prior native zone-stage accounting is retained, not reset by sizing.
    FloorplanAccounting accounting;
    // Null by default: no observation snapshots or experiment parameter changes.
    std::shared_ptr<const FloorplanExperiment> experiment;
};

FloorplanSpec floorplan_spec_from_json(
    const JsonNode& raw, const std::string& source,
    const std::optional<std::set<std::string>>& valid_names = std::nullopt);
std::optional<FloorplanSpec> load_floorplan_spec(
    const std::string& path,
    const std::optional<std::set<std::string>>& valid_names = std::nullopt);
JsonNode export_floorplan_spec(const FloorplanPlan& plan);
// Declarative seed bytes: Python-compatible indent=2, ASCII escapes, final LF.
// Pull weights are typed doubles and are emitted with float spelling.
std::string render_floorplan_spec_json(const FloorplanPlan& plan);
std::filesystem::path write_floorplan_spec(const FloorplanPlan& plan,
                                         const std::filesystem::path& path);
FloorplanPlan build_floorplan(const FloorplanInput& input);
std::vector<FloorplanNote> build_floorplan_notes(
    const FloorplanPlan& plan, const FloorplanInput& input);
std::string render_floorplan_svg(const FloorplanPlan& plan,
                                 const std::vector<FloorplanNote>& notes);
std::string render_floorplan_md(const FloorplanPlan& plan,
                                const std::vector<FloorplanNote>& notes,
                                const FloorplanInput& input);
std::string render_floorplan_ledger(const FloorplanPlan& plan);
JsonNode floorplan_plan_json(const FloorplanPlan& plan);

// Report reuse is explicit and value-owned: no board globals, source reload,
// solver callback, or mutable process-wide render context. A PCB invocation
// retains this stage before mutating its downstream instance placement.
struct FloorplanDocuments {
    std::vector<FloorplanNote> notes;
    std::string svg, markdown;
};
struct FloorplanStage {
    FloorplanPlan plan;
    FloorplanDocuments documents;
};
FloorplanDocuments render_floorplan_documents(const FloorplanPlan& plan,
                                               const FloorplanInput& input);
FloorplanStage generate_floorplan(const FloorplanInput& input);
// Explicit publication boundary; render all documents before calling it.
// Each file is replaced atomically, not a multi-file filesystem transaction.
std::vector<std::filesystem::path> write_floorplan_documents(
    const FloorplanDocuments& documents, const std::filesystem::path& directory);

}  // namespace schgen
