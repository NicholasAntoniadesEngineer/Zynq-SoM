#pragma once

#include "schgen/pcb_model.hpp"

namespace schgen {

struct PlacementIntegrityResult {
    bool ok = true;
    int controlled_parts = 0, corridors = 0, corridor_subjects = 0;
    std::vector<std::string> unreferenced_controlled, corridor_intrusions, unresolved;
    std::string summary() const;
};

PlacementIntegrityResult check_placement_integrity(const PcbCheckInput& input, const PcbModel& model);

}
