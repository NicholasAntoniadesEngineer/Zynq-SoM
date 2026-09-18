#pragma once

#include "schgen/schematic_route.hpp"

#include <stdexcept>

namespace schgen {

class SchematicPlaceError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

struct SchematicSpacing {
    double port_run = 10.16;
    double label_tap_gap = 2.54;
    double hang_stub = 2.54;
    double stagger_extra = 1.27;
    double cap_pitch = 10.16;
    double cluster_dx = 38.10;
    double cluster_dy = 20.32;
    double flags_dy = 16.51;
    double flag_pitch = 10.16;
    SchematicSpacing expanded() const;
};

// Same ordered primitive/plan records consumed by route_schematic; no parallel
// emitter or geometry model. Plan coordinates use Python round(value, 3).
struct SchematicPlacement : SchematicRoutePlacement {
    std::string paper = "A4";
    void plan(const std::string& net, const std::vector<RoutePoint>& points);
};

struct SchematicPlacedPage {
    CircuitSheetIr circuit;
    SchematicPlacement placement;
    SchematicRoutedSheet routed;
    SheetGeometry geometry;
};

// FOUNDATION/WIP: declarations reserve the end-to-end typed interface. These
// are intentionally NOT defined by schematic_place_core.cpp. Link them only
// when the template, fanout/chain and probes/pagination slices are complete.
// No placeholder success, fallback interpreter, board/CLI or manual geometry.
SchematicPlacement build_schematic_placement(const CircuitSheetIr& circuit,
    SymbolLibrary& library, const SchematicSpacing& spacing = {});
SchematicPlacedPage place_and_route_schematic(const CircuitSheetIr& circuit,
    SymbolLibrary& library, const SchematicSpacing& spacing = {}, int max_attempts = 8);
std::vector<SchematicPlacedPage> paginate_and_route_schematic(const CircuitSheetIr& circuit,
    SymbolLibrary& library, const SchematicSpacing& spacing = {}, int max_attempts = 8);

}  // namespace schgen
