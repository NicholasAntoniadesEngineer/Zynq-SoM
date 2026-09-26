#include "pcb_placement_internal.hpp"

namespace schgen::pcb_placement {
void Placer::observe_checkpoint(const std::string &stage) const {
    observe_pcb_experiment_checkpoint(ctx.in.experiment.get(), [&] {
        std::map<std::string, PcbExperimentPart> parts;
        std::map<std::string, PcbCheckFootprintPtr> resolved;
        for (const auto &[ref, key] : geometry.resolvable) {
            if (!pos.count(ref)) continue;
            const auto &p = ctx.by_ref.at(ref);
            parts.emplace(ref, PcbExperimentPart{p.sheet, p.footprint, p.value});
            resolved.emplace(ref, ctx.pool.at(key));
        }
        std::set<std::string> mounting_holes(geometry.mh_refs.begin(), geometry.mh_refs.end()), jacks;
        for (const auto &[ref, jack] : som_refs) { (void)jack; jacks.insert(ref); }
        const auto moved = out.model.stage_moves.find(stage);
        return capture_pcb_experiment_frame(
            {pos, parts, resolved, geometry.side_of, rotations, grid_placed, fixed,
             mounting_holes, jacks, pin_net, geometry.mirror_refs},
            stage, moved == out.model.stage_moves.end() ? std::nullopt : std::optional<int>(moved->second));
    });
}
} // namespace schgen::pcb_placement
