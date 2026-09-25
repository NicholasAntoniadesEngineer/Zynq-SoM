#pragma once
#include "schgen/constraints.hpp"
#include "schgen/bringup_facts.hpp"
#include "schgen/power_checks.hpp"
#include <map>
#include <set>

namespace schgen {
using SiPairKey = std::set<std::string>;
struct SiDeclaration { std::string sheet, kind; int impedance = 0; };
struct SiLengthGroup { std::string gid, interface; std::vector<PairSignalSpec> members; double tol_mil = 0; };
struct SiConstraintsModel {
    std::vector<PairSignalSpec> pairs, missing_in_schematic;
    std::vector<SiLengthGroup> groups;
    std::map<SiPairKey, SiDeclaration> declared;
    std::vector<SiPairKey> missing_in_spec;
};
struct SiConstraintsVerdict {
    bool ok = true; std::size_t n_pairs = 0, n_groups = 0;
    std::vector<SiPairKey> uncovered;
    std::vector<std::tuple<std::string,int,int>> z_divergent;
    std::string summary() const;
};
std::string si_group_id(const std::string&);
SiConstraintsModel build_si_constraints(const std::vector<ProjectCircuit>&,
    const std::vector<PairSignalSpec>&);
// Missing spec is permitted only when no typed differential pair is declared.
SiConstraintsModel load_si_constraints(const std::vector<ProjectCircuit>&,
    const std::filesystem::path& spec_path);
SiConstraintsVerdict check_si_constraints(const SiConstraintsModel&);
std::string render_si_design_rules(const SiConstraintsModel&,
    std::string base = "(version 1)\n");
std::string render_si_markdown(const SiConstraintsModel&);

struct ManufacturingXdc { std::size_t count = 0; std::vector<int> banks; std::optional<std::string> device; };
struct ManufacturingCoverage { std::size_t covered = 0, required = 0, waived = 0; };
struct ManufacturingPreflight { std::optional<double> cost; std::optional<long long> extended; };
struct ManufacturingManifestInput {
    std::vector<ProjectCircuit> sheets;
    PowerCheckResult power;
    Stm32PinMap stm32;
    ManufacturingCoverage coverage;
    std::optional<ManufacturingXdc> xdc;
    std::optional<std::string> device;
    ManufacturingPreflight preflight;
    std::vector<ProjectArtifact> artifacts;
};
// Selection and content hashing are separate from pure manifest rendering.
std::vector<ProjectArtifact> manufacturing_artifacts(const std::filesystem::path& project_root,
    const std::filesystem::path& output_path);
std::optional<std::string> manufacturing_xdc_device(const std::filesystem::path&);
JsonNode manufacturing_manifest(const ManufacturingManifestInput&,
    const PowerPolicy& = default_power_policy());
// Text rendering preserves all signed 64-bit extended counts. The JsonNode
// API rejects extended values that would lose precision in its double storage.
std::string render_manufacturing_manifest(const ManufacturingManifestInput&,
    const PowerPolicy& = default_power_policy());
struct ManufacturingSiRun {
    std::filesystem::path dru, md;
    SiConstraintsModel model;
    SiConstraintsVerdict verdict;
};
ManufacturingSiRun run_si_constraints(const std::vector<ProjectCircuit>&,
    const std::filesystem::path& spec, const std::filesystem::path& dru,
    const std::filesystem::path& markdown);
// Explicit prepared input; artifacts are always selected/hashed from disk at
// publication time and the manifest excludes its own destination.
std::filesystem::path run_manufacturing_manifest(ManufacturingManifestInput,
    const std::filesystem::path& project_root, const std::filesystem::path& output,
    const PowerPolicy& = default_power_policy());
// Complete native analysis wrapper: no caller-precomputed power/coverage needed.
ManufacturingManifestInput prepare_manufacturing_manifest(
    std::vector<ProjectCircuit>, Stm32PinMap,
    std::optional<ManufacturingXdc> xdc = std::nullopt,
    std::optional<std::string> device = std::nullopt,
    ManufacturingPreflight preflight = {},
    const PowerPolicy& = default_power_policy());

struct ManufacturingPipelineStage {
    std::string name, domain, validated_by, desc;
    bool may_move = false, tracked = false;
};
struct ManufacturingQuantization { std::string name, value, klass, basis; };
struct ManufacturingFallback { std::string name, stage, meaning; };
using ManufacturingCounts = std::map<std::string,long long>;
using ManufacturingBaselines = std::map<std::string,ManufacturingCounts>;
struct ManufacturingPipelineInput {
    std::vector<ManufacturingPipelineStage> stages;
    std::vector<ManufacturingQuantization> quantization;
    std::vector<ManufacturingFallback> fallbacks;
    ManufacturingBaselines baselines;
};
// Registries are caller-owned live metadata, never parsed from Python source.
ManufacturingPipelineInput manufacturing_pipeline_from_json(const JsonNode&);
ManufacturingBaselines manufacturing_pipeline_baselines(const std::filesystem::path& repository_root);
std::string render_manufacturing_pipeline(const ManufacturingPipelineInput&);
std::pair<std::filesystem::path,bool> run_manufacturing_pipeline(
    const ManufacturingPipelineInput&, const std::filesystem::path& output);
std::pair<std::filesystem::path,bool> run_manufacturing_pipeline(
    ManufacturingPipelineInput, const std::filesystem::path& repository_root,
    const std::filesystem::path& output);
} // namespace schgen
