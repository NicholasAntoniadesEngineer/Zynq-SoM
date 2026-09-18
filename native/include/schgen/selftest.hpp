#pragma once

#include "schgen/schematic_place.hpp"

#include <string>

namespace schgen {

struct PlacerMutationProof {
    bool baseline_ok = false;
    bool mutation_killed = false;
    // Same descriptive report text as the former Python model-gate runner.
    std::string diagnostic;
    // Untruncated underlying failure, for native diagnostics/regression tests.
    std::string baseline_failure, mutation_failure;
    std::size_t mutation_attempts = 0;
};

// Canonical typed selftest fixtures; no project reload, Python builder, catalog
// or external filesystem is needed to construct them. Symbol lookup still uses
// the caller's actual library, including custom paths/definitions.
CircuitSheetIr selftest_rail_decoupling_fixture();
CircuitSheetIr selftest_esd_clamp_fixture();

// Test-local mutations only. These functions cannot change any production
// Engine policy: each owns a fresh Engine and runs the ordinary completeness,
// missing-part, routing and visual gates. Only SchematicPlaceError is counted
// as a placement failure; validation/resolver/resource errors are not credited
// as killed mutations. Existing validation may contextualize resolver errors.
PlacerMutationProof selftest_rail_decoup_dropped(SymbolLibrary& library);
PlacerMutationProof selftest_clamp_thresh_strict(SymbolLibrary& library);

// Explicit fixture overloads preserve caller edits and enable regression tests
// to prove an unclean baseline or non-applicable mutation cannot count as a
// successful proof. No input is mutated and no source file is reloaded.
PlacerMutationProof selftest_rail_decoup_dropped(const CircuitSheetIr& fixture,
                                               SymbolLibrary& library);
PlacerMutationProof selftest_clamp_thresh_strict(const CircuitSheetIr& fixture,
                                               SymbolLibrary& library);

}  // namespace schgen
