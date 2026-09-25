#pragma once

#include "schgen/pack.hpp"
#include "schgen/pcb_model.hpp"

namespace schgen {

class PcbEscapeError : public std::runtime_error {
  public:
    using std::runtime_error::runtime_error;
};
struct PcbEscapeSignalClass {
    std::string net, function, klass, basis;
    int rank() const; // GENUINE=0, MODERATE=1, LOW=2; unknown is an error
};
// Exact curated si_triage policy with caller-owned FUNCTION_MAP + PUDC_STRAPS.
// No default for an uncurated signal, no loader, no mutable classifier cache.
PcbEscapeSignalClass classify_pcb_escape_signal(const std::string &net,
                                                const ProjectStrings &function_map);

// A value-owned invocation snapshot. Geometry is prepared once and shared by
// obstacle collection, coexistence and checks. Nothing reads model.copper or
// model.escape_* as a shortcut: mutated inputs are always recomputed.
class PcbEscapeInput {
  public:
    PcbEscapeInput(const PcbModel &, ReturnPathResult,
                   std::map<std::string, PcbEscapeSignalClass> triage, std::string interface_bytes);
    const PcbCheckInput &geometry() const { return geometry_; }
    const PcbCheckModel &model() const { return geometry_.model(); }
    const std::optional<Box4> &keepout() const { return keepout_; }
    const std::map<std::string, std::optional<DifferentialGeometry>> &classes() const {
        return classes_;
    }
    const ReturnPathResult &return_path() const { return return_path_; }
    const PcbEscapeSignalClass &classify(const std::string &) const;
    const std::string &interface_bytes() const { return interface_bytes_; }

  private:
    PcbCheckInput geometry_;
    std::optional<Box4> keepout_;
    std::map<std::string, std::optional<DifferentialGeometry>> classes_;
    ReturnPathResult return_path_;
    std::map<std::string, PcbEscapeSignalClass> triage_;
    std::string interface_bytes_;
};

struct PcbEscapeLaneRecord : PcbEscapeLane {
    std::string pad, layer = "F.Cu", si_class;
};
struct PcbEscapePairRecord : PcbEscapePair {
    std::vector<std::string> halves;
    std::string convergence;
};
struct PcbEscapeCorridor {
    Box4 rect;
    std::string purpose;
};
struct PcbEscapePlanResult {
    std::string schema = "escape/v1", content_key;
    std::map<std::string, std::vector<PcbEscapeLaneRecord>> lanes;
    std::map<std::string, int> netted_counts;
    std::vector<PcbEscapePairRecord> pairs;
    std::vector<std::string> genuine_pairs;
    std::map<std::string, PcbEscapeCorridor> corridors;
    std::string consumer;
    PcbEscapePlan for_checks() const;
    JsonNode json() const;
};
struct PcbEscapeCoexistence {
    std::string conn, ref, sheet, verdict, basis;
};
struct PcbEscapeMetadata {
    ReturnPathResult v1;
    std::map<std::string, PcbEscapeSignalClass> triage; // connector.pad -> class
    std::map<std::string, std::map<std::string, double>> coverage_mm;
    double worst_cover_mm = 0;
    std::map<std::string, int> vias;
    // seat/split_u/split_row plus redundant_via, preserving execution order.
    std::vector<SeatLedger> ledger;
    Box4 escape_region, plane;
    std::vector<std::string> voids_checked;
    std::vector<PcbEscapeCoexistence> coexistence;
    std::string som_interface_sha256;
    JsonNode json() const;
};
struct PcbEscapeCopperResult {
    std::vector<PcbCheckCopper> copper;
    PcbEscapeMetadata meta;
    JsonNode copper_json() const;
};

// Public policy orchestration for escape.py. Fixed researched thresholds are
// retained, not caller-overridable relaxations. Primitive geometry/ladder/seat
// APIs are the existing native pack.hpp functions.
ContactGeom pcb_escape_contact_geometry(const PcbCheckFootprint &);
Box4 pcb_escape_corridor_local(const PcbCheckFootprint &);
Box4 pcb_escape_corridor_board(const PcbCheckFootprint &, double x, double y, double rotation);
PcbEscapeCopperResult build_pcb_escape_copper(const PcbEscapeInput &);
PcbEscapePlanResult build_pcb_escape_plan(const PcbEscapeInput &);
// Exact emitted escape_block.json (indent=1, sorted keys, ASCII escapes, LF).
// Renders the supplied results without recomputing caller state.
std::string render_pcb_escape_block(const PcbEscapePlanResult &, const PcbEscapeMetadata &);

} // namespace schgen
