#pragma once

#include "schgen/named_constant.hpp"

#include <string>
#include <string_view>
#include <vector>

namespace schgen::layout::constants {
inline constexpr NamedConstant bypass_reach{"bypass_reach", 2.0, "mm", "policy",
    "a bypass capacitor's loop inductance rises about 1 nH per mm; beyond a few mm it no longer serves its pin"};
inline constexpr NamedConstant reservoir_reach{"reservoir_reach", 6.0, "mm", "policy",
    "bulk capacitance works at lower frequency and still serves a pin several mm away"};
inline constexpr NamedConstant pull_reach{"pull_reach", 12.0, "mm", "policy",
    "a pull resistor only sets a level; distance costs stub length, not function"};
inline constexpr NamedConstant series_reach{"series_reach", 4.0, "mm", "policy",
    "a series element belongs at the source so the trace beyond it is the damped line"};
inline constexpr NamedConstant terminate_reach{"terminate_reach", 3.0, "mm", "policy",
    "a termination more than a few mm from its receiver leaves an unterminated stub"};
inline constexpr NamedConstant filter_reach{"filter_reach", 4.0, "mm", "policy",
    "a filter element works on the node it touches; trace beyond it re-admits the noise"};
inline constexpr NamedConstant feedback_reach{"feedback_reach", 4.0, "mm", "policy",
    "feedback and compensation nodes are high impedance; short traces keep switching noise out"};
inline constexpr NamedConstant switching_reach{"switching_reach", 3.0, "mm", "policy",
    "the area of a switching power loop sets its ringing and radiated noise"};
inline constexpr NamedConstant timing_reach{"timing_reach", 3.0, "mm", "policy",
    "crystal traces add load capacitance and pick up noise"};
inline constexpr NamedConstant protect_reach{"protect_reach", 6.0, "mm", "policy",
    "a clamp must meet the surge before the pin it protects does"};
inline constexpr NamedConstant sense_reach{"sense_reach", 6.0, "mm", "policy",
    "sense traces carry small differential voltages; length adds error and pickup"};
inline constexpr NamedConstant indicate_reach{"indicate_reach", 15.0, "mm", "policy",
    "an indicator carries a slow signal and may sit where it is visible"};
inline constexpr NamedConstant set_reach{"set_reach", 6.0, "mm", "policy",
    "a programming element sets a quiet node; short traces keep the setting accurate"};
}

namespace schgen::rules {

struct RoleRule {
    std::string_view name;
    const NamedConstant* reach = nullptr;
    bool owner_face = false;
    bool loop_member = false;
    bool loop_capacitor = false;
    bool marks_regulator = false;
    bool field_sensitive = false;
    bool field_reported = false;
    bool protects_connector = false;
    bool terminates_line = false;
    bool senses = false;
    bool bypasses_pin = false;
};

const std::vector<RoleRule>& role_catalogue();
const RoleRule& role_rule(std::string_view name);
std::vector<std::string_view> roles_with(bool RoleRule::*trait);
bool keeps_owner_face(const RoleRule& role, bool owner_is_regulator, bool owner_is_loop_inductor);

}
