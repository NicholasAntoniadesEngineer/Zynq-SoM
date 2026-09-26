#pragma once
// Codec matching the independently captured pre-extraction native output bytes.
#include "pcb_placement_fixture.hpp"
#include "floorplan_precision_fixture.hpp"
#include "pcb_stage_internal.hpp"
#include <iomanip>
#include <sstream>
#include <ostream>

namespace connector_fixture {
using namespace schgen;
inline void counts(std::ostream& stream, const char* owner, const QuantizationCounts& values) {
    stream << owner << '\n';
    // Separate additive contracts prove connector, floorplan, occupancy and legalizer additions.
    for (const auto& [name, count] : values)
        if(name!="mechanical_direction_component" && name!="stage_direction_component" && !floorplan_precision_fixture::added(name) && !occupancy_precision_fixture::added(name) && !legalize_precision_fixture::added(name)&&!stage_precision_fixture::added(name)&&!placement_precision_fixture::added(name))
        stream << std::quoted(name) << ' ' << count << '\n';
}
inline void mechanical(std::ostream& stream, const PlacementMechResult& result) {
    stream << "MECHANICAL " << result.ok << ' ' << result.board_w << ' '
              << result.board_h << ' ' << result.n_connectors << ' '
              << result.n_face_top << '\n';
    if (result.som_core) {
        const auto& b = *result.som_core;
        stream << "CORE " << b.x0 << ' ' << b.y0 << ' ' << b.x1 << ' ' << b.y1 << '\n';
    }
    for (const auto& row : result.connectors)
        stream << "CONNECTOR " << std::quoted(row.ref) << ' ' << std::quoted(row.mpn)
                  << ' ' << std::quoted(row.edge) << ' ' << row.rotation << ' ' << row.flush
                  << ' ' << row.face_dir.first << ' ' << row.face_dir.second << ' ' << row.ok << '\n';
    for (const auto* rows : {&result.bad_connectors, &result.under_som,
             &result.controls_under_som, &result.top_under_som, &result.face_top_on_bottom}) {
        stream << "FINDINGS " << rows->size() << '\n';
        for (const auto& row : *rows) stream << std::quoted(row) << '\n';
    }
    stream << "SUMMARY\n" << result.summary() << "\nEND SUMMARY\n";
}
}
