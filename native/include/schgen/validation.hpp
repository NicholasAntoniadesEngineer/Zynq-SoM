#pragma once

#include "schgen/circuit.hpp"
#include "schgen/project.hpp"
#include "schgen/seat.hpp"
#include "schgen/symbols.hpp"

#include <cstddef>
#include <stdexcept>
#include <string>
#include <vector>

namespace schgen {

class ValidationError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

struct PartPinCoverage {
    std::string ref, lib_id;
    // Unique actual library pin numbers, including hidden/all-unit pins.
    // Pin order is lexical for deterministic reports; parts retain IR order.
    std::vector<std::string> symbol_pins, assigned_pins, nc_pins, unassigned_pins;
};

struct ElectricalValidationResult {
    std::string circuit;
    std::vector<std::string> completeness_errors;
    std::vector<std::string> input_driver_errors;
    std::vector<PartPinCoverage> coverage;
    bool ok() const { return completeness_errors.empty() && input_driver_errors.empty(); }
    std::string completeness_summary() const;
    std::string summary() const;
};

// Resolve every part against the real symbol library. IR pin metadata is never
// a fallback for an unavailable symbol. Symbol errors throw ValidationError
// with circuit/ref/lib_id context. Neither circuits nor libraries are rewritten.
ElectricalValidationResult check_circuit_electrical(const CircuitSheetIr& circuit,
                                                    SymbolLibrary& library);
std::vector<std::string> check_circuit_completeness(const CircuitSheetIr& circuit,
                                                  SymbolLibrary& library);
// Python Circuit.validate equivalent, throwing on completeness errors. Also
// rejects invalid NC pins and conflicting ownership in caller-edited IR.
void validate_circuit(const CircuitSheetIr& circuit, SymbolLibrary& library);
// Python _check_inputs_driven: only internal SIGNAL nets; all seven driver
// etypes retained. Public POWER/GROUND/PORT nets are intentionally exempt.
std::vector<std::string> check_inputs_driven(const CircuitSheetIr& circuit,
                                           SymbolLibrary& library);

// Emitter-independent page-space geometry in millimetres. Box coordinates
// must be finite/ordered; segment endpoints may be reversed. The five text
// kinds are pin_name, pin_number, reference, value, label. Other kinds retain
// the Python gate's ordinary non-text behavior (e.g. body). Owners are exact
// identity strings: part ref, label:<net>, or net:<net> for power symbols.
// Both kind and owner are required; empty owners cannot claim exemptions.
struct VisualBox {
    double x0 = 0.0, y0 = 0.0, x1 = 0.0, y1 = 0.0;
    std::string kind, owner;
    Box4 bounds() const { return {x0, y0, x1, y1}; }
    bool intersects(const VisualBox& other, double pad = 0.0) const;
};

struct VisualSegment {
    double x0 = 0.0, y0 = 0.0, x1 = 0.0, y1 = 0.0;
    std::string net;
    bool horizontal() const;
    bool vertical() const;
};

struct VisualJunction {
    double x = 0.0, y = 0.0;
};

struct SheetGeometry {
    std::vector<VisualBox> boxes;
    std::vector<VisualSegment> wires;
    std::vector<VisualJunction> junctions;
};

struct VisualResult {
    bool ok = true;
    std::vector<std::string> findings;
    std::string summary() const;
};

// Full visual_gate.check semantics and finding order, using shared native
// geometry predicates. Interior crossings fail even for the same net or with
// a junction. Same-net T/end touches remain legal; overlaps never do.
// Rejects nonfinite/inverted geometry and diagonal/zero-length wires rather
// than allowing malformed geometry to evade predicates. A negative/nonfinite
// clearance is also an input error; these cases throw ValidationError.
VisualResult check_visual_geometry(
    const SheetGeometry& geometry,
    double clearance_mm = default_engine_config.visual_clearance_mm);

}  // namespace schgen
