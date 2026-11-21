#pragma once

#include "schgen/link.hpp"
#include "schgen/power_checks.hpp"
#include "schgen/part_facts.hpp"
#include "schgen/execution_accounting.hpp"
#include "schgen/pcb_scan.hpp"
#include "schgen/project.hpp"
#include "schgen/sheet_roles.hpp"
#include "schgen/som_interface.hpp"

#include <map>
#include <memory>
#include <optional>
#include <set>
#include <string_view>

namespace schgen {

// Pure verification boundary. All geometry is mm. Source order is retained;
// consumers share immutable footprint snapshots, never resolve/reload a file.
struct PcbCheckFootprint {
    std::string source, bytes;
    Sexpr document;
    std::vector<std::tuple<std::string, std::string, double, double, double,
                           double, double>> pads;
    std::optional<Box4> bbox;
};
using PcbCheckFootprintPtr = std::shared_ptr<const PcbCheckFootprint>;
PcbCheckFootprintPtr pcb_check_footprint(std::string source, std::string bytes);
// For providers (including floorplan) that already parsed the exact document.
PcbCheckFootprintPtr pcb_check_footprint(std::string source, std::string bytes,
                                       Sexpr document);
struct PcbCheckInstance {
    std::string ref, value, footprint, sheet, side = "top";
    double x = 0, y = 0, rotation = 0;
    std::map<std::string, std::pair<int, std::string>> pad_nets;
    PcbCheckFootprintPtr mod;  // null is unresolved, never synthetic geometry
    bool mirror = false;      // geometry is the supplied, already mirrored mod
    std::optional<PartClass> part_class;
    std::optional<PartHeight> height;
    bool at_module = false;
    std::string module_connector;
    bool under_module = false;
    std::optional<std::string> silk_label, escape_basis;
    bool escape_escalates = false;
};
PartClass part_class_of(const PcbCheckInstance& instance);
const PartHeight& part_height_of(const PcbCheckInstance& instance);
struct PcbCheckCopper {
    std::string kind, group, conn, role, net_name, layer = "F.Cu";
    int net = 0;
    double x = 0, y = 0, x1 = 0, y1 = 0, x2 = 0, y2 = 0;
    double size = 0, drill = 0, width = 0;
};
struct PcbEscapeLane {
    int row = 0, lane = 0;
    std::string direction, net;
    double port_x = 0, port_y = 0, width = 0;
    std::optional<std::string> bus_group;
};
struct PcbEscapePair {
    std::string base, conn, si_class;
    bool same_row = false;
    int delta_lane = 0;
};
struct PcbEscapePlan {
    std::map<std::string, std::vector<PcbEscapeLane>> lanes;
    std::map<std::string, int> netted_counts;
    std::vector<PcbEscapePair> pairs;
    std::vector<std::string> genuine_pairs;
    std::string content_key;
};
struct PcbEscapePopulation {
    std::map<std::string, int> netted_contacts;
    std::optional<int> genuine_pairs;
    ModuleReturnPath return_path;
};
struct LandSpacingPolicy {
    double fab_minimum = 0.0, fab_minimum_track = 0.0, highest_volts = 0.0;
    ElectricalSpacingFact electrical;
    std::map<std::string, std::pair<std::string, LandFact>> lands;
    std::map<std::string, double> net_volts;
};
struct PcbCheckModel {
    double board_w = 0, board_h = 0, origin_x = 25, origin_y = 25;
    std::vector<PcbCheckInstance> insts;
    std::map<std::string, int> net_numbers;
    std::map<std::string, std::string> netclass_of;
    std::optional<Box4> som_core;
    std::vector<PcbCheckCopper> copper;
    std::optional<PcbEscapePlan> escape_plan;
    // nullopt means no metadata, "" means present metadata missing the hash.
    std::optional<std::string> escape_interface_sha256;
    ConnectorFacts connectors;
    std::optional<LandSpacingPolicy> land_spacing;
    IsolationFacts isolation;
    std::set<std::string> module_connectors;
    std::set<std::string> edge_sheets;
};
struct PcbCheckGeometry {
    std::optional<Box4> courtyard, pad_bbox;
    std::map<std::string, Box4> pad_boxes;
};
// An immutable prepared snapshot avoids stale geometry after source mutation.
// Re-prepare after changing poses. Footprint scans remain shared and reusable.
class PcbCheckInput {
public:
    explicit PcbCheckInput(PcbCheckModel model);
    const PcbCheckModel& model() const { return model_; }
    // Missing geometry stays explicit until an actual gate consumer requires
    // it. For example, spacing does not require unrelated nonconnector mods.
    const PcbCheckGeometry& geometry_at(std::size_t index) const;
    Box4 courtyard_at(std::size_t index) const;
    Box4 pad_bbox_at(std::size_t index) const;
private:
    PcbCheckModel model_;
    std::vector<std::optional<PcbCheckGeometry>> geometry_;
};

struct ConnectorModelRow {
    std::string ref, mpn, value;
    std::optional<double> z;
    bool ok = true;
};
struct ConnectorModelResult {
    bool ok = true;
    int n_connectors = 0;
    std::vector<ConnectorModelRow> models;
    std::vector<std::string> bad_z, missing_model, geom_conflicts, geom_checked;
    std::string summary() const;
};
// Allows unresolved models to be reported without requiring placed geometry.
ConnectorModelResult check_connector_models(const PcbCheckModel&);
ConnectorModelResult check_connector_models(const PcbCheckModel&, const ConnectorFacts&);
struct ConnectorSpacingRow {
    std::string ref_a, ref_b, family, axis;
    double gap = 0, need = 0;
    bool ok = true;
};
struct ConnectorSpacingResult {
    bool ok = true;
    double board_w = 0, board_h = 0;
    std::vector<ConnectorSpacingRow> pairs;
    std::vector<std::string> violations;
    std::string summary() const;
};
ConnectorSpacingResult check_connector_spacing(const PcbCheckInput&);
struct PlacementMechRow {
    std::string ref, mpn, edge;
    double rotation = 0, flush = 0;
    std::pair<int, int> face_dir;
    bool ok = true;
};
struct PlacementMechResult {
    bool ok = true;
    double board_w = 0, board_h = 0;
    int n_connectors = 0, n_face_top = 0;
    std::optional<Box4> som_core;
    std::vector<PlacementMechRow> connectors;
    std::vector<std::string> bad_connectors, under_som, controls_under_som,
        top_under_som, face_top_on_bottom;
    // Completed invocation's actual scalar calls, including failed verdicts.
    // Parent imports once; rendering/rechecking does not alter solver receipts.
    QuantizationCounts quantization_engagements;
    std::string summary() const;
};
PlacementMechResult check_placement_mech(const PcbCheckInput&);
struct PcbFanoutRecord {
    std::string ref, sheet, side;
    int pins = 0;
    double clearance = 0, need = 0;
    std::string nearest_ref, nearest_sheet, basis;
    double slack() const { return clearance - need; }
    bool starved() const { return clearance < need - 1e-4; }
};
struct PcbFanoutResult {
    bool ok = true;
    int n_subjects = 0, n_starved = 0;
    std::optional<int> baseline;
    std::vector<std::string> regressions;
    std::vector<PcbFanoutRecord> records;
    std::string summary() const;
};
bool pcb_is_df40_part(const std::string& module_connector, int pins);
std::set<std::string> pcb_module_sheets(const PcbCheckModel& model);
bool pcb_counts_as_crowder(const std::string& ref, const std::string& sheet,
    const std::string& module_connector, int pins, const std::string& footprint, const std::string& subject_sheet);
std::pair<double, std::string> pcb_fanout_need(int pins);
std::pair<double, std::string> pcb_escape_need(int nets);
inline constexpr const char* pcb_ground_plane_net = "GND";
inline constexpr double pcb_escape_tie_mm = 1e-3;
struct PcbEscapeSides {
    bool north = false, south = false, west = false, east = false;
};
struct PcbEscapePad {
    Box4 box;
    bool counted = false;
};
int pcb_escape_nets(const PcbCheckInstance&);
std::vector<PcbEscapePad> pcb_escape_pads(const PcbCheckInstance&, const PcbCheckGeometry&);
PcbEscapeSides pcb_escape_sides(const Box4& courtyard, const std::vector<PcbEscapePad>&, double tie);
bool pcb_crowds_escape(const Box4& subject, const PcbEscapeSides&, const Box4& crowder);
// Caller supplies a persisted ratchet. nullopt retains first-run self-pinning.
PcbFanoutResult check_fanout(const PcbCheckInput&, std::optional<int> baseline);
PcbFanoutResult check_fanout_strict(const PcbCheckInput&, std::optional<int> baseline);
int pcb_fanout_ratchet(int n_starved, std::optional<int> previous);
struct RefdesOverlapResult {
    bool ok = true;
    int n_top = 0, n_bottom = 0, bottom_pairs = 0;
    std::vector<std::pair<std::string, std::string>> top_pairs;
};
RefdesOverlapResult check_refdes_overlap(const Sexpr& pcb, bool enforce_bottom = false);

struct ReturnPathContact {
    std::string ref, pad;
    int row = 0, index = 0;
    double x = 0, y = 0;
    std::string net, klass;
};
struct ReturnPathViolation {
    std::string ref, base, net, pad;
    std::optional<int> distance;
    std::string as_line() const;
};
struct ReturnPathResult {
    bool ok = true;
    int k = 2, n_pairs = 0, n_pair_contacts = 0;
    std::vector<ReturnPathViolation> violations;
    std::map<int, int> dist_hist;
    std::map<std::string, std::pair<int, int>> per_conn;
    std::map<std::string, int> pairs_per_conn;
    std::optional<int> worst_distance;
    std::vector<std::string> connectors;
    int n_fail() const { return static_cast<int>(violations.size()); }
    std::string summary() const;
};
std::string pcb_classify_net(const std::string&);
std::optional<std::string> pcb_pair_partner(const std::string&);
std::string pcb_pair_base(const std::string&, const std::string&);
std::map<std::string, std::string> pcb_hs_pairs(const std::set<std::string>&);
std::vector<ReturnPathContact> build_return_path_contacts(const std::string& ref,
    const XdcStrings& pins, const PcbCheckFootprint&);
std::vector<ReturnPathContact> build_return_path_contacts(const std::string& ref,
    const XdcStrings& pins, const std::map<std::string,std::pair<double,double>>& positions);
ReturnPathResult check_return_path(
    const std::map<std::string, std::vector<ReturnPathContact>>&, int k = 2);
ReturnPathResult check_return_path(const SomInterface&,
    const std::map<std::string, PcbCheckFootprintPtr>& connector_footprints, int k = 2);

struct EscapeLaneResult {
    bool ok = true, genuine_stated = true;
    int n_lanes = 0, n_pairs = 0, n_genuine = 0;
    std::vector<std::string> violations;
    std::string summary() const;
};
// Exact source bytes are required for the stale-content alarm. The caller
// chooses the contract; there is no hidden carrier/default-project read.
std::string pcb_sha256(std::string_view);
std::string pcb_escape_content_key(const PcbCheckModel&, std::string_view interface_bytes);
EscapeLaneResult check_escape_lanes(const PcbCheckModel&, const PcbEscapePopulation&,
                                    std::string_view interface_bytes);
PcbEscapePlan pcb_escape_plan_from_json(const JsonNode&);
PcbEscapePopulation pcb_escape_population_from_json(const JsonNode& escape, const ModuleDefinition& module);

struct ReturnStitchClass { int rank = 0; std::string klass, function; };
struct ReturnStitchCoverage {
    int rank = 0;
    std::string klass, ref, pad, function;
    std::optional<double> distance;
};
struct ReturnStitchResult {
    bool ok = true, hash_ok = true;
    double radius = 2, worst_mm = 0;
    int n_contacts = 0, n_covered = 0, n_vias = 0;
    std::vector<std::string> violations;
    std::vector<ReturnStitchCoverage> coverage;
    std::map<std::string, std::pair<int, int>> per_conn;
    std::string v1_verdict, file_parity = "not-checked";
    std::string summary() const;
};
struct PcbEmittedBoard {
    std::string source;
    Sexpr document;
    bool exists = true;
};
// v1 and curated triage are prepared once upstream. Missing triage throws;
// classification controls presentation only, never coverage requirements.
ReturnStitchResult check_return_stitch(const PcbCheckInput&, const ReturnPathResult& v1,
    const std::map<std::string, ReturnStitchClass>& triage,
    std::string_view interface_bytes, const ModuleReturnPath& pinned, const PcbEmittedBoard* emitted = nullptr);
std::string pcb_escape_file_parity(const PcbEmittedBoard&,
                                 const std::vector<PcbCheckCopper>& escape);

inline constexpr double pcb_per_contact_a = 0.3, pcb_contact_derating = 0.8;
struct PcbRailAmpacity {
    std::string name;
    int contacts = 0;
    double current_a = 0;
    std::optional<double> volts;
    std::map<std::string, int> conns;
    double capacity_a() const { return contacts * pcb_per_contact_a * pcb_contact_derating; }
    double margin_a() const { return capacity_a() - current_a; }
    bool over() const { return current_a > capacity_a() + 1e-9; }
    double util() const;
};
struct RailAmpacityResult {
    std::vector<PcbRailAmpacity> rails;
    std::vector<std::string> errors, findings;
    double per_contact_a = pcb_per_contact_a, derating = pcb_contact_derating;
    bool ok() const { return errors.empty(); }
    std::string report() const;
};
RailAmpacityResult analyze_rail_ampacity(const std::vector<ProjectCircuit>&, const SheetRoles&,
    const SomInterface&, const LinkMapping&, const PowerPolicy&);

} // namespace schgen
