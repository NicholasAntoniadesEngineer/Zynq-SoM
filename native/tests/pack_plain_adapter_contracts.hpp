#pragma once
#include "pack_geometry_adapter_contracts.hpp"
#include "pack_plain_precision_fixture.hpp"
namespace pack_plain_adapter_contracts {
inline void run() {
    using schgen::QuantizationCounts;
    const QuantizationCounts prior{{"fixed_part_grid",3},{"unknown_plain_operation",7},
        {"pack_xy_coordinate_precision_typo",11},{"pack_future_geometry",13}};
    auto mixed=prior;
    for(const auto& name:pack_plain_precision_fixture::names)mixed[name]=17;
    auto demand=[](bool ok){if(!ok)throw std::runtime_error("plain18 adapter dropped historical/unknown name");};
    demand(pack_plain_precision_fixture::select(mixed,false)==prior);
    demand(pack_geometry_precision_fixture::select(mixed,false)==prior);
    demand(placement_precision_fixture::select(mixed,false)==prior);
    demand(output_precision_fixture::select(mixed,false)==prior);
    demand(pack_precision_fixture::select(mixed,false)==prior);
    demand(stage_precision_fixture::select(mixed,false)==prior);
    demand(legalize_precision_fixture::select(mixed,false)==prior);
    demand(occupancy_precision_fixture::select(mixed,false)==prior);
    demand(floorplan_precision_fixture::select(mixed,false)==prior);
    std::ostringstream expected,actual;
    connector_fixture::counts(expected,"TEST",prior);
    connector_fixture::counts(actual,"TEST",mixed);
    demand(actual.str()==expected.str());
}
}
