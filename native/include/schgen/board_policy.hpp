#pragma once
#include "schgen/board_pipeline.hpp"
#include "schgen/floorplan_ledger_policy.hpp"

namespace schgen {
struct NativeBoardPolicyGap {
    std::string name, decision_source, action;
};
struct NativeBoardPolicy {
    std::vector<NativeLedgerDeclaration> ledger_declarations;
    ManufacturingPipelineInput pipeline_metadata;
    std::vector<CppAuditSource> audit_sources;
    std::vector<NativeBoardPolicyGap> missing_providers;
    std::vector<std::string> compiler_include_flags;
    // This describes declaration completeness only, NOT a passed source audit.
    bool providers_complete() const { return missing_providers.empty(); }
    std::string report() const;
};
// Read-only factory. Use the actual invocation's prepared FloorplanInput, not
// its recorded decisions or a fixture/default board. Scalar input parameters
// are value-owned; callbacks re-read actual compiled constants at step entry.
// No geometry, quantization, counter import, compiler or filesystem write runs.
NativeBoardPolicy make_native_board_policy(const ProjectPaths&,const FloorplanInput&);
// Explicit decision scope, independent of scanner findings; includes the host's
// minimum manifest and reviewed supporting kernels/headers. No file exemptions.
std::vector<CppAuditSource> native_board_policy_audit_sources();
ManufacturingPipelineInput native_board_pipeline_metadata();
// Atomic install of just policy fields. Existing declarations/stage metadata/
// source manifests are rejected, not overwritten. Caller compiler/target flags,
// output paths, rendering, baselines and all execution settings are retained.
// Missing providers remain omitted: the existing importer/audit MUST fail.
NativeBoardPolicy configure_native_board_policy(BoardPipelineOptions&,
    const ProjectPaths&,const FloorplanInput&);
}
