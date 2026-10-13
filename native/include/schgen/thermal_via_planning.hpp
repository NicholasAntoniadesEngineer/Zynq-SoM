#pragma once
#include "schgen/pack.hpp"
#include "schgen/pcb_checks.hpp"

namespace schgen {
struct PcbEmitPolicy;
struct PreferredThermalField {
    std::string ref;
    std::size_t requested = 0;
    ViaSelection sites;
};
// Exact emission geometry, without lattice search, serialization or a claim of
// thermal adequacy. Recompute for each immutable candidate; no pose/path cache.
// Only supplied copper and previously chosen preferred sites are obstacles;
// later escape/lattice vias still require final emission and qualification.
std::vector<PreferredThermalField> plan_preferred_thermal_vias(
    const PcbCheckModel&, const PcbEmitPolicy&, QuantizationCounts* = nullptr);
// A subject's loss cannot be paid for by another subject's improvement.
bool preserves_preferred_thermal_vias(const std::vector<PreferredThermalField>& before,
                                      const std::vector<PreferredThermalField>& after);
}
