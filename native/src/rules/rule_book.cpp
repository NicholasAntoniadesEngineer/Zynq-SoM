#include "schgen/rules.hpp"

namespace schgen::rules {

extern const RuleEntry module_mating, module_clearance, module_escape_corridor, tall_part_beside_module, controlled_net_needs_ground,
    termination_distance_report, regulator_loop_one_face, regulator_over_ground, input_capacitor_nearest,
    nothing_sensitive_under_inductor, protect_first_after_connector, bypass_on_pin_face_or_under,
    sense_distance_report, timing_parts_on_crystal_face;

const std::vector<RuleEntry>& rule_book() {
    static const std::vector<RuleEntry> book{
        module_mating, module_clearance, module_escape_corridor, tall_part_beside_module, controlled_net_needs_ground,
        termination_distance_report,
        regulator_loop_one_face, regulator_over_ground, input_capacitor_nearest, nothing_sensitive_under_inductor,
        protect_first_after_connector, bypass_on_pin_face_or_under, sense_distance_report,
        timing_parts_on_crystal_face};
    return book;
}

}
