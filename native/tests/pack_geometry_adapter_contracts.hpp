#pragma once
#include "floorplan_precision_fixture.hpp"
#include "connector_precision_fixture.hpp"
#include "pack_geometry_precision_fixture.hpp"

namespace pack_geometry_adapter_contracts {
inline void demand(bool ok){if(!ok)throw std::runtime_error("geometry14 exact-family adapter lost historical or unknown names");}
inline void run(){
    using schgen::QuantizationCounts;
    const QuantizationCounts prior{{"fixed_part_grid",3},{"legalize_pose_quantum",5},
        {"pack_pair_gap_precision4dp_typo",7},{"pack_geometry_future",11}};
    auto mixed=prior;for(const auto& name:pack_geometry_precision_fixture::names)mixed[name]=13;
    demand(pack_geometry_precision_fixture::select(mixed,false)==prior);
    demand(placement_precision_fixture::select(mixed,false)==prior);
    demand(output_precision_fixture::select(mixed,false)==prior);
    demand(pack_precision_fixture::select(mixed,false)==prior);
    demand(stage_precision_fixture::select(mixed,false)==prior);
    demand(legalize_precision_fixture::select(mixed,false)==prior);
    demand(occupancy_precision_fixture::select(mixed,false)==prior);
    demand(floorplan_precision_fixture::select(mixed,false)==prior);
    std::ostringstream expected,actual;
    connector_fixture::counts(expected,"TEST",prior);connector_fixture::counts(actual,"TEST",mixed);
    demand(actual.str()==expected.str());
    for(const auto& name:placement_precision_fixture::names)mixed[name]=17;
    for(const auto& name:output_precision_fixture::names)mixed[name]=19;
    for(const auto& name:pack_precision_fixture::names)mixed[name]=23;
    demand(placement_precision_fixture::select(pack_geometry_precision_fixture::select(mixed,false),false)==prior);
    QuantizationCounts geometry;
    for(const auto& name:pack_geometry_precision_fixture::names)geometry[name]=13;
    demand(pack_geometry_precision_fixture::select(mixed)==geometry);
}
}
