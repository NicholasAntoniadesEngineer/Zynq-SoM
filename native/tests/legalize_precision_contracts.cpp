#include "schgen/legalize.hpp"
#include "schgen/json.hpp"
#include "accurate_norm.hpp"
#include <iostream>
#include <limits>

namespace {
const schgen::JsonNode& field(const schgen::JsonNode& node, const std::string& key) {
    const auto* value = schgen::object_field(node, key);
    if (!value) throw std::runtime_error("missing precision fixture field " + key);
    return *value;
}
void require(bool value, const std::string& why) { if (!value) throw std::runtime_error(why); }
}
int main(int argc, char** argv) {
    using namespace schgen;
    try {
        require(argc == 2, "expected immutable kernel fixture");
        const auto fixture = parse_json_file(argv[1]);
        for (const auto& row : field(fixture, "channel").array_value)
            require(channel_demand_mm(static_cast<int>(field(row,"n").number_value),6,2,.2) == field(row,"expected").number_value,
                "channel demand rounded differently");
        for (const auto& row : field(fixture, "facing").array_value) {
            const auto& zone = field(row,"zone").array_value;
            const auto& output = field(row,"output").array_value;
            const auto& down = field(row,"down").array_value;
            const auto& expected = field(row,"expected").array_value;
            const auto value = accurate_facing_dot(zone[0].number_value,zone[1].number_value,
                output[0].number_value,output[1].number_value,down[0].number_value,down[1].number_value);
            require(value.first == expected[0].number_value, "facing dot rounded differently");
            require(value.second == expected[1].number_value, "facing angle rounded differently");
        }
        require(accurate_hypot2(3,4) == 5 && accurate_hypot2(-3,-4) == 5, "norm signs");
        require(accurate_hypot2(0,-0.0) == 0 && !std::signbit(accurate_hypot2(0,-0.0)), "norm zero");
        const double inf = std::numeric_limits<double>::infinity(), nan = std::numeric_limits<double>::quiet_NaN();
        require(std::isinf(accurate_hypot2(inf,nan)) && std::isnan(accurate_hypot2(1,nan)), "norm nonfinite");
        const double tiny = std::numeric_limits<double>::denorm_min();
        require(accurate_hypot2(tiny,0) == tiny && accurate_hypot2(3*tiny,4*tiny) == 5*tiny, "subnormal norm");
        std::cout << "Exact independent legalizer precision contracts PASS\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
