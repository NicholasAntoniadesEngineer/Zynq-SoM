#pragma once

#include "schgen/named_constant.hpp"
#include "schgen/pack.hpp"

#include <array>
#include <optional>
#include <string>
#include <vector>

namespace schgen {

namespace ladder_stub_constants {
inline constexpr NamedConstant stub_quantum{"stub_quantum", 1e-4, "mm", "physical",
    "emitted copper carries four decimals, so a stub that matches its land pattern before emission differs by at most this much after it"};
inline constexpr std::array ladder_stub_registry{stub_quantum};
}

struct LadderStubObstacle {
    double x0 = 0.0, y0 = 0.0, x1 = 0.0, y1 = 0.0, rule = 0.0;
    std::string label;
    bool same_footprint = false;
};

struct LadderStubEvidence {
    std::string connector;
    double pad_width = 0.0, native_gap = 0.0, fab_minimum = 0.0, nearest_same = 0.0, nearest_other = 0.0;
    std::size_t kept = 0;
    std::vector<std::string> dropped;
};

bool ladder_stub_joins_pad(const EscapeLadderSeg& seg);
std::optional<std::string> ladder_stub_violation(const EscapeLadderSeg& seg, double pad_width, double native_gap,
                                                 double normal_floor, const std::vector<LadderStubObstacle>& obstacles,
                                                 LadderStubEvidence& evidence);
std::string ladder_stub_report(const LadderStubEvidence& evidence);

}
