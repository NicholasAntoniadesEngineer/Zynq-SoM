#pragma once
#include "schgen/circuit.hpp"
#include <optional>
#include <stdexcept>

namespace schgen {
class CircuitAuthoringError : public std::runtime_error {
public: using std::runtime_error::runtime_error;
};
void validate_mounting_hole_net(const CircuitSheetIr&, const std::string& net);
// Circuit.mounting_hole's public authoring guard and typed mutation. The net
// must already be GROUND; no inferred promotion, waiver or rail short. A caller
// retaining Python's authoring counters supplies its selected ref explicitly;
// nullopt selects the first unused H reference in this IR snapshot.
CircuitPartIr add_mounting_hole(CircuitSheetIr&, const std::string& net = "CHASSIS_GND",
    const std::optional<std::string>& ref = std::nullopt);
} // namespace schgen
