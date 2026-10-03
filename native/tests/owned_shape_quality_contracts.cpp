#include "schgen/owned_shape_quality.hpp"
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {
using namespace schgen;
int checks = 0;
void require(bool ok, const char* why) { ++checks; if (!ok) throw std::runtime_error(why); }
OwnedShapeQuality quality() {
    OwnedShapeQuality q; q.state = OwnedShapeQualityState::Measured; q.fanout_starved = 0;
    q.bypass_pad_gaps = {{"C1", 8}, {"C2", 6}}; q.bulk_pad_gaps = {{"C3", 9}};
    for (const auto* cap : {"C1", "C2", "C3"})
        q.subjects[cap] = {"U1", "5", "1", "2", "VCC", "GND", "top", "bottom",
            std::string(cap) == "C3" ? OwnedShapeRole::OutputBulk : OwnedShapeRole::Bypass};
    return q;
}
}
int main() {
    using namespace schgen;
    try {
        const auto base = quality(); auto better = base; better.bypass_pad_gaps["C1"] = 7;
        require(owned_shape_pareto_dominates(better, base), "strict per-cap improvement");
        require(!owned_shape_pareto_dominates(base, better), "reverse improvement");
        require(!owned_shape_pareto_dominates(base, base), "equal quality must keep incumbent");
        auto mixed = better; mixed.bypass_pad_gaps["C2"] = 7;
        require(!owned_shape_pareto_dominates(mixed, base) && !owned_shape_pareto_dominates(base, mixed), "tradeoffs are incomparable; do not sum gaps");
        for (auto state : {OwnedShapeQualityState::NotApplicable, OwnedShapeQualityState::Rejected}) {
            auto bad = better; bad.state = state;
            require(!owned_shape_pareto_dominates(bad, base) && !owned_shape_pareto_dominates(base, bad), "invalid evidence state");
        }
        for (int change = 0; change != 18; ++change) {
            auto bad = better; auto& s = bad.subjects.at("C1");
            switch (change) {
                case 0: s.owner = "U2"; break;
                case 1: s.owner_pin = "6"; break;
                case 2: s.cap_pin = "2"; break;
                case 3: s.return_pin = "3"; break;
                case 4: s.rail = "VDD"; break;
                case 5: s.return_net = "AGND"; break;
                case 6: s.owner_side = "bottom"; break;
                case 7: s.cap_side = "top"; break;
                case 8: s.role = OwnedShapeRole::OutputBulk; break;
                case 9: bad.subjects.erase("C2"); break;
                case 10: bad.bypass_pad_gaps.erase("C2"); break;
                case 11: bad.bypass_pad_gaps["extra"] = 0; break;
                case 12: bad.bulk_pad_gaps["C1"] = 0; break;
                case 13: bad.fanout_starved.reset(); break;
                case 14: bad.fanout_starved = 1; break;
                case 15: bad.fanout_starved = -1; break;
                case 16: bad.bulk_pad_gaps["C3"] = 8; break;
                case 17: bad.bulk_pad_gaps["C3"] = 10; break;
            }
            require(!owned_shape_pareto_dominates(bad, base), "different subject/coverage/side/role/fanout/bulk accepted");
        }
        for (double value : {-1., std::numeric_limits<double>::infinity(), std::numeric_limits<double>::quiet_NaN()}) {
            auto bad = better; bad.bypass_pad_gaps["C1"] = value;
            require(!owned_shape_pareto_dominates(bad, base), "invalid bypass metric");
            bad = better; bad.bulk_pad_gaps["C3"] = value;
            require(!owned_shape_pareto_dominates(bad, base), "invalid bulk metric");
        }
        auto malformed = base; malformed.subjects["C1"].cap_side = "invalid";
        auto malformed_better = malformed; malformed_better.bypass_pad_gaps["C1"] = 7;
        require(!owned_shape_pareto_dominates(malformed_better, malformed), "equally malformed subjects are not comparable");
        auto tiny = base; tiny.bypass_pad_gaps["C1"] = std::nextafter(8., 0.);
        require(owned_shape_pareto_dominates(tiny, base), "no arbitrary quality threshold");

        OwnedShapeQualityTable data{{{"sheet", 0}, base}, {{"sheet", 9}, better}};
        const OwnedShapeTieRank incumbent{0, true, 20, 30, 10, 4, "top"};
        auto challenger = incumbent; challenger.index = 9;
        require(owned_shape_tie_dominates(true, data, "sheet", challenger, incumbent), "same-size later index not selectable");
        require(!owned_shape_tie_dominates(false, data, "sheet", challenger, incumbent), "default changed");
        require(!owned_shape_tie_dominates(true, data, "missing", challenger, incumbent), "missing metadata became zero quality");
        for (int change = 0; change != 11; ++change) {
            auto bad = challenger;
            switch (change) {
                case 0: bad.feasible = false; break;
                case 1: bad.w = 21; break;
                case 2: bad.w = 30; bad.h = 20; break; // even equal area is insufficient
                case 3: bad.estimator = std::nextafter(10., 11.); break;
                case 4: bad.estimator = std::nextafter(10., 9.); break;
                case 5: bad.distance_key = 5; break;
                case 6: bad.side = "bottom"; break;
                case 7: bad.index = 0; break;
                case 8: bad.index = -1; break;
                case 9: bad.w = std::numeric_limits<double>::infinity(); break;
                case 10: bad.estimator = std::numeric_limits<double>::quiet_NaN(); break;
            }
            require(!owned_shape_tie_dominates(true, data, "sheet", bad, incumbent), "tie-break overrides earlier ranking or feasibility");
        }
        data.at({"sheet", 9}) = base;
        require(!owned_shape_tie_dominates(true, data, "sheet", challenger, incumbent), "equal quality must preserve stable index");
        data.at({"sheet", 9}) = mixed;
        require(!owned_shape_tie_dominates(true, data, "sheet", challenger, incumbent), "incomparable quality must preserve stable index");
        // Regression for the non-transitive dominance-else-index relation:
        // A=(0,1),idx3; B=(1,2),idx1; C=(2,0),idx2. Only A dominates B.
        OwnedShapeQualityTable cycle;
        const auto put = [&](int index, double x, double y) {
            auto q = base; q.bypass_pad_gaps = {{"C1", x}, {"C2", y}};
            cycle[{"sheet", index}] = q;
        };
        put(3, 0, 1); put(1, 1, 2); put(2, 2, 0);
        const auto rank = [&](int index) { auto r = incumbent; r.index = index; return r; };
        const auto unsafe_relation = [&](int a, int b) {
            if (owned_shape_pareto_dominates(cycle.at({"sheet", a}), cycle.at({"sheet", b}))) return true;
            if (owned_shape_pareto_dominates(cycle.at({"sheet", b}), cycle.at({"sheet", a}))) return false;
            return a < b;
        };
        require(unsafe_relation(3, 1) && unsafe_relation(1, 2) && unsafe_relation(2, 3), "cycle fixture must reproduce invalid comparator");
        std::vector<int> order{1, 2, 3}; int permutations = 0;
        do {
            std::vector<OwnedShapeTieRank> bucket;
            for (int index : order) bucket.push_back(rank(index));
            require(owned_shape_nondominated_indices(true, cycle, "sheet", bucket) == std::vector<int>({2, 3}), "three-way frontier depends on permutation");
            require(owned_shape_select_tied_bucket(true, cycle, "sheet", bucket) == 2, "three-way winner depends on permutation");
            require(owned_shape_select_tied_bucket(false, cycle, "sheet", bucket) == 1, "default must retain stable index");
            require(owned_shape_select_tied_bucket(true, {}, "sheet", bucket) == 1, "missing quality must retain stable index");
            auto equal = cycle;
            for (auto& entry : equal) entry.second = base;
            require(owned_shape_select_tied_bucket(true, equal, "sheet", bucket) == 1, "equal quality must retain stable index");
            auto absent = cycle; absent.erase({"sheet", 1});
            require(owned_shape_select_tied_bucket(true, absent, "sheet", bucket) == 1, "missing metric candidate was fabricated or discarded");
            auto incompatible = cycle; incompatible.at({"sheet", 1}).subjects.at("C1").owner_side = "bottom";
            require(owned_shape_select_tied_bucket(true, incompatible, "sheet", bucket) == 1, "different sides must be incomparable");
            auto invalid = cycle; invalid.at({"sheet", 1}).bypass_pad_gaps.at("C1") = std::numeric_limits<double>::quiet_NaN();
            require(owned_shape_select_tied_bucket(true, invalid, "sheet", bucket) == 1, "nonfinite quality must be incomparable");
            ++permutations;
        } while (std::next_permutation(order.begin(), order.end()));
        require(permutations == 6, "all three-way permutations tested");
        put(4, 0, 0); order = {1, 2, 3, 4}; permutations = 0;
        do {
            std::vector<OwnedShapeTieRank> bucket;
            for (int index : order) bucket.push_back(rank(index));
            require(owned_shape_nondominated_indices(true, cycle, "sheet", bucket) == std::vector<int>({4}), "complete frontier failed to eliminate dominated candidates");
            require(owned_shape_select_tied_bucket(true, cycle, "sheet", bucket) == 4, "later dominating index not selectable");
            ++permutations;
        } while (std::next_permutation(order.begin(), order.end()));
        require(permutations == 24, "all four-way permutations tested");
        require(!owned_shape_select_tied_bucket(true, cycle, "sheet", {}), "empty bucket winner");
        require(owned_shape_select_tied_bucket(true, cycle, "sheet", {rank(3)}) == 3, "singleton bucket");
        for (int change = 0; change != 5; ++change) {
            auto bad = rank(2);
            if (change == 0) bad.index = 1;
            if (change == 1) bad.estimator = std::nextafter(bad.estimator, 11.);
            if (change == 2) bad.w += 1;
            if (change == 3) bad.feasible = false;
            if (change == 4) bad.distance_key = std::numeric_limits<double>::infinity();
            bool rejected = false;
            try { (void)owned_shape_select_tied_bucket(true, cycle, "sheet", {rank(1), bad}); }
            catch (const std::invalid_argument&) { rejected = true; }
            require(rejected, "malformed/mixed-primary bucket accepted");
        }
        std::cout << "PASS " << checks << " neutral Pareto/tie precedence checks\n";
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
