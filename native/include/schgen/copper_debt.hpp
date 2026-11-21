#pragma once
#include "schgen/component_basis.hpp"
#include "schgen/pcb_emit.hpp"

namespace schgen {
class CopperProvenanceError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};
struct CopperPinNet {
    std::string pin, net, net_prefix;
};
struct CopperNeed {
    int min_vias = 0;
    double radius_mm = 0.0;
    std::vector<std::string> pour_layers;
};
struct CopperCheck {
    std::string kind, sheet, net, section, part, layer, pour_evidence;
    std::vector<std::string> scopes, refs;
    bool all_parts = false;
    std::optional<std::string> lib_id, footprint, value_prefix;
    std::vector<std::pair<std::string, std::string>> fields, net_pins;
    std::vector<CopperPinNet> pins;
    int count = 0, impedance = 0;
    double rth_ja = 0.0, size_mm = 0.0, drill_mm = 0.0;
    std::optional<double> rth_ja_pour;
    CopperNeed need;
};
struct CopperMeasure {
    std::string kind;
    std::map<std::string, std::string> text;
    int min_voids = 0;
};
struct CopperClaim {
    std::string id, title, assumes, risk;
    std::vector<CopperCheck> checks;
    CopperMeasure measure;
};
struct CopperPlane {
    std::string net, layer;
};
struct CopperClaims {
    std::string reference;
    CopperPlane plane;
    std::string inventory_with, inventory_without, inventory_emits;
    std::vector<CopperClaim> claims;
};
// The ledger records global engineering claims, including claims whose devices
// are absent on a particular board. The caller supplies the live authoring
// universe plus the actual thermal/emitter/stackup policies used for its board.
// At a pipeline boundary, replace matching project sheets with the IR actually
// supplied to netlisting. Never reload their stored circuit.json as evidence.
struct CopperDebtSources {
    CopperClaims claims;
    std::vector<ComponentBasisInput> circuits;
    ComponentBasisPolicy basis;
    std::set<std::string> basis_scopes;
    ThermalPolicy thermal;
    PcbEmitPolicy emission;
    RegulatorFacts regulators;
    EpViaFacts ep_vias;
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
CopperClaims parse_copper_claims(const JsonNode& document, const std::string& file);
CopperClaims load_copper_claims(const std::filesystem::path& repository);
CopperDebtSources author_copper_debt_sources(const std::filesystem::path& repository);
CopperDebtSources author_copper_debt_sources(const std::filesystem::path& repository, const ComponentBasisBoards& boards);
void verify_copper_debt_sources(const CopperDebtSources&);
// Hard-fails missing or inconsistent claim provenance even without a PCB.
// Copper debt itself remains report-only; thermal credit is a separate gate.
CopperDebtResult analyze_copper_debt(const ThermalCopper*, const CopperDebtSources&);
std::string copper_debt_report(const CopperDebtResult&);
JsonNode copper_debt_result_json(const CopperDebtResult&);
CopperDebtResult copper_debt_result_from_json(const JsonNode&);
} // namespace schgen
