#include "pack_search_precision_fixture.hpp"
#include "floorplan_precision_fixture.hpp"
#include "connector_precision_fixture.hpp"
#include <sstream>
#include <stdexcept>
int main(){
    using namespace schgen;
    const QuantizationCounts prior{{"fixed_part_grid",3},{"legalize_pose_quantum",5},
        {"seat_lower_index_typo",7},{"fallback_future",11},{"seat_future",17}};
    auto mixed=prior;for(const auto& n:pack_search_precision_fixture::names)mixed[n]=13;
    auto require=[](bool ok){if(!ok)throw std::runtime_error("Search9 exact adapter lost old/unknown names");};
    require(pack_search_precision_fixture::select(mixed,false)==prior);
    require(pack_geometry_precision_fixture::select(mixed,false)==prior);
    require(pack_precision_fixture::select(mixed,false)==prior);
    require(output_precision_fixture::select(mixed,false)==prior);
    require(placement_precision_fixture::select(mixed,false)==prior);
    require(stage_precision_fixture::select(mixed,false)==prior);
    require(legalize_precision_fixture::select(mixed,false)==prior);
    require(occupancy_precision_fixture::select(mixed,false)==prior);
    require(floorplan_precision_fixture::select(mixed,false)==prior);
    std::ostringstream a,b;connector_fixture::counts(a,"TEST",prior);connector_fixture::counts(b,"TEST",mixed);
    require(a.str()==b.str());
    QuantizationCounts search;for(const auto& n:pack_search_precision_fixture::names)search[n]=13;
    require(pack_search_precision_fixture::select(mixed)==search);
    return 0;
}
