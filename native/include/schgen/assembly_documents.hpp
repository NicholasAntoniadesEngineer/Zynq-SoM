#pragma once
#include "schgen/pcb_emit.hpp"
#include "schgen/power_checks.hpp"

namespace schgen {
// Indices refer to the immutable caller-supplied PcbModel::insts, never paths
// or process-global placement state. Empty stages remain visible in documents.
struct AssemblyStep {
    int n = 0; std::string slug, title;
    std::vector<std::size_t> insts; std::vector<std::string> notes;
};
struct AssemblyPhase {
    int n = 0; std::string slug, title;
    std::vector<std::string> sheets; std::vector<std::size_t> insts;
    std::vector<std::string> checkpoints; std::string lead;
};
struct AssemblyPlan { std::vector<AssemblyStep> steps; std::vector<AssemblyPhase> phases; };
std::string assembly_joint(const PcbCheckFootprint&);
std::vector<AssemblyStep> assembly_process_steps(const PcbModel&,
    const PcbEmitPolicy& = default_pcb_emit_policy());
std::vector<AssemblyPhase> assembly_bringup_phases(const PcbModel&,
    const PowerCheckResult&, const PcbEmitPolicy& = default_pcb_emit_policy());
AssemblyPlan assembly_plan(const PcbModel&, const PowerCheckResult&,
    const PcbEmitPolicy& = default_pcb_emit_policy());
std::string render_assembly_markdown(const PcbModel&, const AssemblyPlan&, const std::string& name);
struct AssemblyImage { std::string filename; std::string png; };
std::string render_assembly_stage_image(const PcbModel&,
    const std::vector<std::size_t>& done, const std::vector<std::size_t>& current,
    const std::string& caption, const std::optional<Box4>& mate = std::nullopt);
std::vector<AssemblyImage> render_assembly_images(const PcbModel&, const AssemblyPlan&);
// Transport verdict accepts absent/incomplete generation results explicitly.
std::pair<bool,std::string> assembly_verdict(const JsonNode& result,
    const std::filesystem::path& repository_root);
// Render everything before publication; throws on failures, never returns a
// successful result with missing/stale documents. Destinations are explicit.
JsonNode run_assembly_documents(const PcbModel&, const PowerCheckResult&,
    const std::string& name, const std::filesystem::path& markdown_path,
    const std::filesystem::path& png_directory,
    const PcbEmitPolicy& = default_pcb_emit_policy());
} // namespace schgen
