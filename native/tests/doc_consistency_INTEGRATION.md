# Native authored-document consistency: stable handoff

New files only: `include/schgen/doc_consistency.hpp`, `src/doc_consistency.cpp`,
`tests/doc_consistency_contracts.cpp`, and
`tests/data/doc_consistency/python_reference.json`. No existing firmware, power,
sequence, model, CMake, CLI, registry, document, or shared binary was edited.

Production read-only path:

```cpp
const auto input = schgen::load_doc_consistency_input(paths);
const auto result = schgen::check_doc_consistency(input);
// result.ok(), issues with original test-family names, observed rails/sheets.
```

Callers with freshly authored IR can use `build_doc_consistency_input` directly.
It calls existing power analysis, sequence building, and SVG rendering twice
independently. The validator checks supplied observations without recomputing or
repairing them. Filesystem loading reads real canonical IR and authored documents;
there are no fixture substitutions, Python imports/processes, generated artifacts,
or source writes in production. Missing/non-file documents are explicit failures;
unreadable input or malformed IR throws.

## Exact nine-family coverage

The result exposes the original Python test names in declaration order:

1. `test_packet_files_present`: DESIGN_SPEC and COMPLIANCE must be real files.
   Missing and directory-as-document cases are tested.
2. `test_design_spec_rail_table_rails_are_real`: first-column rail tokens from
   actual authored tables must be nonempty and belong to the dynamic union of
   policy sources, analyzed rails, regulator inputs/outputs, and bridge endpoints.
   Unknown rails fail; later-column tokens remain excluded as before.
3. `test_design_spec_core_rails_documented`: preserve all seven required literal
   rail mentions from the original carrier policy.
4. `test_compliance_cited_sheets_exist`: exact `## ` headers containing `sheet`
   must cite nonempty, existing authored sheet names. Ignored heading forms and
   Unicode/Python splitlines behavior are tested.
5. `test_compliance_covers_every_required_interface`: preserve all six required
   interface strings, including USB 2.0 and bank-35 IO.
6. `test_power_sequence_partitions_every_regulator`: every live regulator output
   is placed; every supplied policy source is in stage-0; load switches are
   excluded from stage-0 and the rail chain. Each failure mode is mutated.
7. `test_power_sequence_build_is_deterministic`: two independently analyzed/built
   sequences preserve stage-0 order and chain/module output order. All three
   orderings have independent negative cases.
8. `test_power_sequence_svg_byte_deterministic`: two renders and private output
   files are byte-identical, XML parses, and rail-box coverage meets the live
   regulator count. The original immutable SVG is also compared byte-for-byte.
9. `test_design_spec_references_the_three_diagrams`: block diagram, power tree,
   and power sequence references are all retained. Missing-link mutation fails.

The existing sequence math is reused unchanged, including its independent legacy
stage-0/chain/module fixture. This suite adds missing authored-document checks and
explicitly joins them to those existing power/sequence proofs; it does not replace
or weaken the older firmware/power contract suites.

## Independent reference and explicit SVG hardening

Before implementing the validator, the unmodified nine original Python test
functions were executed through their AST against actual authored documents and
sheet names, with the previously captured independent legacy power/sequence/SVG
outputs supplying the analysis transport. No new native validator was involved.
The immutable reference records all nine outcomes for 24 baseline/mutation cases,
the source digest, and extracted rail/citation inventories. Native tests compare
the complete set of failing families for every case, not just selected positives.
Every one of the nine families is killed by at least one captured negative case.

Reference SHA-256:
`269a63e39c706717f1efb7ac4fa209c3e13a82b416e263ea79268709816446a4`.

Explicit additional parser hardening, beyond the original raw `<rect` substring
count: native libxml2 parsing requires an SVG root/namespace, forbids DTDs, does
not load external entities/resources, and counts actual SVG rectangle elements.
Wrong-root XML, comment-spoofed rectangles, foreign-namespace rectangles, and
external-entity declarations fail. Valid prefixed/nested SVG succeeds. These
negative contracts do not modify or bless production output bytes.

## Proof

**308 assertions PASS; all nine families; 24 independent Python mutation cases.**
The real carrier provides 27 known rails, 12 cited sheets, 20 regulators, and
24 parsed SVG rectangles. All registered carrier C++ factories are also executed
afresh and yield the identical independently verified SVG. A private JSON-only
project mirror proves the loader needs no Python constructors or generated cache.

The suite also passes from a private working directory with `PATH=/nonexistent`.
No runtime compiler, KiCad executable, Python, or external process is required.
Only the existing read-only part catalog and symbol assets are needed for the
fresh-authoring portion. Immutable firmware/power fixtures remain unchanged.

Private executable: `/private/tmp/doc-consistency.TJyleu/contracts`.
Invocation: `contracts REPOSITORY PRIVATE_SCRATCH`; repeated invocations use
unique child directories and preserve proof outputs. Compilation is C++17 with
`-Wall -Wextra -Wpedantic -Werror -ffp-contract=off`, deployment target 26.6,
the existing archive, libxml2, and pthread. No shared build was invoked.

## Exact parent CMake registration

Add `src/doc_consistency.cpp` to `schgen_core` with the normal strict flags.
The core already publicly links `LibXml2::LibXml2` and existing power/firmware/
authoring APIs; no new external dependency or public-layout change is needed.

```cmake
add_executable(schgen_doc_consistency_contracts tests/doc_consistency_contracts.cpp)
target_link_libraries(schgen_doc_consistency_contracts PRIVATE schgen_core)
target_compile_options(schgen_doc_consistency_contracts PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
add_test(NAME native_doc_consistency_contracts COMMAND schgen_doc_consistency_contracts
    "${CMAKE_CURRENT_SOURCE_DIR}/.."
    "${CMAKE_CURRENT_BINARY_DIR}/doc-consistency-contract-output")
```

The normal `schgen_catalogs` build must precede tests requiring fresh authoring,
as it does for existing authoring suites. Target-only workflows may explicitly
depend on `schgen_catalogs`; do not generate a catalog inside this test. The same
catalog prerequisite applies to the already-handed-off net-contract suite.

No main/module/project-CLI binding is required for this CTest registration.
This family is frozen for parent integration; subsequent geometry-CLI work is
confined to its own new files.
