#pragma once
#include "schgen/component_basis.hpp"
#include "schgen/pcb_emit.hpp"

namespace schgen {
class CopperProvenanceError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};
// The ledger records global engineering claims, including claims whose devices
// are absent on a particular board. The caller supplies the live authoring
// universe plus the actual thermal/emitter/stackup policies used for its board.
// At a pipeline boundary, replace matching project sheets with the IR actually
// supplied to netlisting. Never reload their stored circuit.json as evidence.
struct CopperDebtSources {
    std::vector<ComponentBasisInput> circuits;
    ThermalPolicy thermal;
    PcbEmitPolicy emission;
    std::vector<DifferentialGeometry> geometry;
};
struct CopperDebtEntry {
    std::string eid, title, assumes;
    std::vector<std::string> where;
    std::string emits, status, risk;
};
struct CopperDebtResult {
    std::vector<CopperDebtEntry> entries;
    std::string inventory;
};
CopperDebtSources author_copper_debt_sources(const std::filesystem::path& repository);
// Hard-fails missing or inconsistent claim provenance even without a PCB.
// Copper debt itself remains report-only; thermal credit is a separate gate.
CopperDebtResult analyze_copper_debt(const ThermalCopper*, const CopperDebtSources&);
std::string copper_debt_report(const CopperDebtResult&);
JsonNode copper_debt_result_json(const CopperDebtResult&);
CopperDebtResult copper_debt_result_from_json(const JsonNode&);
} // namespace schgen
