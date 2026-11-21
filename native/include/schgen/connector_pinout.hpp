#pragma once

#include "schgen/part_facts.hpp"
#include "schgen/project.hpp"

#include <string>
#include <vector>

namespace schgen {

inline constexpr const char* connector_pinout_empty_cell = "-";
inline constexpr const char* connector_pinout_declared_open = "nc";

struct PinoutProtector {
    std::string board_ref, part;
};

struct ConnectorPinRow {
    std::string sheet, ref, board_ref, part, pin, pin_name, net, net_type, port_kind, route_class, impedance, declared;
    std::vector<PinoutProtector> protectors;
};

struct ConnectorPinout {
    std::vector<ConnectorPinRow> rows;
    std::string text() const;
};

ConnectorPinout build_connector_pinout(const std::vector<CircuitSheetIr>& sheets, const SheetIndex& index, const PartFacts& facts);

std::vector<std::string> verify_connector_pinout(const ConnectorPinout& pinout, const std::vector<CircuitSheetIr>& sheets, const SheetIndex& index, const PartFacts& facts);

}
