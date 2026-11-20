#include "schgen/ladder_stub_rule.hpp"

#include <iostream>
#include <limits>
#include <stdexcept>

namespace {

using namespace schgen;

constexpr double pitch = 0.4, pad_width = 0.23, pad_length = 0.66, row = 1.355, normal_floor = 0.15, normal_rule = 0.2;
constexpr double widened = 0.25, nudge = 0.01, far_away = 5.0;

std::size_t checks = 0;

void require(bool ok, const std::string& why) {
    ++checks;
    if (!ok) throw std::runtime_error("ladder stub rule contract: " + why);
}

LadderStubObstacle pad_at(double u, double v, const std::string& label, bool same) {
    return {u - pad_width / 2, v - pad_length / 2, u + pad_width / 2, v + pad_length / 2, normal_rule, label, same};
}

EscapeLadderSeg column(double u, double width) {
    EscapeLadderSeg seg;
    seg.ax = u;
    seg.ay = -row;
    seg.bx = u;
    seg.by = row;
    seg.w = width;
    seg.role = "stub_column";
    return seg;
}

LadderStubEvidence fresh() {
    LadderStubEvidence evidence;
    evidence.nearest_same = evidence.nearest_other = std::numeric_limits<double>::infinity();
    return evidence;
}

}

int main() {
    try {
        const double native_gap = pitch - pad_width;
        const std::vector<LadderStubObstacle> neighbours{pad_at(-pitch, -row, "J(som).3", true), pad_at(pitch, -row, "J(som).7", true)};
        auto evidence = fresh();
        require(!ladder_stub_violation(column(0, pad_width), pad_width, native_gap, normal_floor, neighbours, evidence),
                "a stub as wide as its pad keeps the land pattern's own gap to its neighbours");
        require(std::abs(evidence.nearest_same - native_gap) < ladder_stub_constants::stub_quantum.value,
                "the evidence records the land pattern's own gap");
        evidence = fresh();
        require(ladder_stub_violation(column(0, widened), pad_width, native_gap, normal_floor, neighbours, evidence).has_value(),
                "a stub wider than the pad it joins fails");
        evidence = fresh();
        require(ladder_stub_violation(column(nudge, pad_width), pad_width, native_gap, normal_floor, neighbours, evidence).has_value(),
                "a stub closer to a same-footprint pad than the land pattern's own gap fails");
        const std::vector<LadderStubObstacle> foreign{pad_at(pitch, -row, "U(other).1", false)};
        evidence = fresh();
        require(ladder_stub_violation(column(0, pad_width), pad_width, native_gap, normal_floor, foreign, evidence).has_value(),
                "a stub inside the normal clearance of other copper fails as before");
        const std::vector<LadderStubObstacle> distant{pad_at(far_away, -row, "U(other).1", false)};
        evidence = fresh();
        require(!ladder_stub_violation(column(0, pad_width), pad_width, native_gap, normal_floor, distant, evidence),
                "a stub clear of other copper by the normal rule passes");
        EscapeLadderSeg spine = column(0, widened);
        spine.role = "spine";
        evidence = fresh();
        require(!ladder_stub_violation(spine, pad_width, native_gap, normal_floor, distant, evidence),
                "copper that joins no pad keeps its own width");
        std::cout << "PASS " << checks << " ladder stub rule checks\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 1;
    }
}
