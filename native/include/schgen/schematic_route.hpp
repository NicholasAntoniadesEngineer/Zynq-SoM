#pragma once

#include "schgen/route.hpp"
#include "schgen/schematic.hpp"
#include "schgen/validation.hpp"

#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace schgen {

struct SchematicRoutePlacement {
    std::vector<SchematicPlacedPart> parts;
    std::vector<SchematicPlacedPower> powers;
    std::vector<SchematicHierLabel> hlabels;
    std::vector<SchematicLocalLabel> llabels;
    // Carried for placement/emission compatibility. Python route() claims all
    // unassigned symbol pin stems, independently of the drawn NC marker list.
    std::vector<SchematicNoConnect> no_connects;
    // Ordered dictionary: net -> ordered polylines -> ordered page-space points.
    std::vector<std::pair<std::string, std::vector<std::vector<RoutePoint>>>> plans;
    std::vector<VisualBox> boxes;
    std::set<std::string> label_bridged;
};

struct SchematicRoutedSheet {
    std::vector<VisualSegment> segs;
    std::vector<VisualJunction> junctions;
};

class SchematicRouteError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

// Complete layout/route.py orchestration on the fixed 1.27 mm schematic grid:
// claim stems/power/labels/boxes/plans, split and deduplicate planned legs,
// validate islands, join signal components, and emit degree>=3 junctions.
// Circuit and plan vectors retain Python insertion order. Numeric point sets
// preserve the 64-bit CPython baseline's component/BFS tie order, without a
// Python runtime. Caller-owned inputs and immutable symbols are never changed.
// Nonfinite/unrepresentable coordinates and joins that make no graph progress
// throw explicitly, rather than entering undefined casts or an infinite loop.
SchematicRoutedSheet route_schematic(const CircuitSheetIr& circuit,
                                    const SchematicRoutePlacement& placement,
                                    const SchematicSymbolResolver& symbols);
SchematicRoutedSheet route_schematic(const CircuitSheetIr& circuit,
                                    const SchematicRoutePlacement& placement,
                                    SymbolLibrary& library);

// Compatibility/diagnostic entry points use the same graph walk and normalized
// BFS starts as route_schematic, with no interpreter-owned geometry or fallback.
// Point vectors represent insertion order; returned component points are unique.
std::vector<std::vector<RoutePoint>> schematic_route_components(
    const std::vector<std::pair<RoutePoint, RoutePoint>>& legs,
    const std::vector<RoutePoint>& pin_points,
    const std::vector<RoutePoint>& power_points,
    const std::vector<RoutePoint>& label_points,
    const std::vector<std::pair<RoutePoint, RoutePoint>>& bonds);
std::vector<RoutePoint> schematic_route_join(const RouteGrid& grid,
    const std::string& net, const std::vector<RoutePoint>& first,
    const std::vector<RoutePoint>& second);

SheetGeometry schematic_route_geometry(const SchematicRoutePlacement& placement,
                                        const SchematicRoutedSheet& routed);
// Replaces only wires/junctions; all other emission fields retain their values.
void apply_schematic_route(SchematicDesign& design, const SchematicRoutedSheet& routed);

}  // namespace schgen
