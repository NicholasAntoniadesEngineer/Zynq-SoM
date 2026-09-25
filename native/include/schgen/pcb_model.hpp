#pragma once

#include "schgen/constraints.hpp"
#include "schgen/pcb_checks.hpp"

namespace schgen {

// A shared placed-board model, not a second geometry implementation. Floorplan
// providers supply immutable exact source documents in PcbCheckInstance::mod;
// checkers accept the base snapshot directly. No global library/path lookup.
using PcbFootprintInst = PcbCheckInstance;
struct PcbModel : PcbCheckModel {
    std::map<std::string, std::optional<DifferentialGeometry>> classes;
    int placed = 0, n_top = 0, n_bottom = 0;
    std::vector<std::string> deferred;
    bool two_side = true;
    std::optional<Box4> som_keepout;
    JsonNode escape_meta;
    // Preserve complete diagnostic metadata beyond the checker's typed subset.
    std::optional<JsonNode> escape_plan_record;
    std::map<std::string, int> stage_moves;
    // Emission-only overrides indexed into the shared copper vector. Escape
    // vias default to locked (Python c.get("locked", True)); segments ignore
    // locks. Keep these indices aligned when replacing/reordering copper.
    // The check model deliberately has no editor-state fields.
    std::map<std::size_t, bool> copper_locks;
};

using PcbFootprintPool = std::map<std::string, PcbCheckFootprintPtr>;
// Strict boundary for an already placed model. mod_path is an opaque pool key;
// missing entries fail explicitly. It never opens a file or executes authoring.
PcbModel pcb_model_from_json(const JsonNode &, const PcbFootprintPool &);
JsonNode pcb_model_json(const PcbModel &);

} // namespace schgen
