#pragma once

#include "schgen/firmware_docs.hpp"

namespace schgen {
struct DocConsistencyInput {
    std::vector<ProjectCircuit> sheets;
    std::optional<std::string> design_spec, compliance;
    PowerCheckResult power;
    PowerSequence sequence, repeated_sequence;
    std::string svg, repeated_svg;
};
struct DocConsistencyIssue { std::string family, detail; };
struct DocConsistencyResult {
    std::vector<std::string> checked_families, known_rails, table_rails, cited_sheets;
    std::vector<DocConsistencyIssue> issues;
    std::size_t svg_rectangles = 0;
    bool ok() const { return issues.empty(); }
};

// Exact nine original Python test names, in declaration order; stable coverage
// identifiers for caller reports. These are authored carrier-document policies.
const std::vector<std::string>& doc_consistency_families();

// Reuse the actual native power analysis and sequence/SVG renderers. Perform two
// independent analyses/builds/renders, not a copied output masquerading as a
// determinism check. No file writes, fixtures, subprocess, or hardware changes.
DocConsistencyInput build_doc_consistency_input(std::vector<ProjectCircuit> sheets,
    std::optional<std::string> design_spec, std::optional<std::string> compliance,
    const PowerPolicy& policy = default_power_policy());

// Read actual canonical authored sheets + docs/DESIGN_SPEC.md and COMPLIANCE.md.
// Absent/non-file documents remain null for an explicit packet-file failure;
// unreadable inputs or malformed circuit IR throw. No generated-doc substitution.
DocConsistencyInput load_doc_consistency_input(const ProjectPaths& paths,
    const PowerPolicy& policy = default_power_policy());

// Validate supplied observations without regenerating/repairing them. Preserve
// original rail/citation selection, required literal strings, partition/source/
// load-switch rules, ordering, and byte determinism. SVG is parsed natively with
// no external entity/DTD loading; require an SVG root and count actual SVG rect
// elements rather than comment text. These explicit parser hardenings reject
// malformed/spoofed documents without changing production renderer output.
DocConsistencyResult check_doc_consistency(const DocConsistencyInput& input,
    const PowerPolicy& policy = default_power_policy());
} // namespace schgen
