#include "schgen/occupancy.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <optional>
#include <random>
#include <stdexcept>
#include <tuple>
#include <vector>

int main() {
    try {
        std::mt19937 rng(314159);
        const schgen::Halo zero{};
        for (int trial = 0; trial < 240; ++trial) {
            schgen::Occupancy occ(24, 22, 0.3, 8, 4, 1, 0.05);
            for (int n = 0; n < 5; ++n) {
                occ.add(rng() % 20, rng() % 18, 1 + rng() % 8,
                        1 + rng() % 8, zero, zero, 3, {});
            }
            const double ax = (static_cast<int>(rng() % 700) - 100) / 20.0;
            const double ay = (static_cast<int>(rng() % 600) - 100) / 20.0;
            const double w = 1 + rng() % 30, h = 1 + rng() % 28;
            const double x0 = trial % 3 == 0 ? 4 : -24;
            const double x1 = trial % 3 == 0 ? 14 : 48;
            std::vector<std::tuple<double, double, double>> ranked;
            for (int x = 0; x <= 24; ++x) {
                if (x < x0 || x > x1) continue;
                for (int y = 0; y <= 22; ++y) {
                    ranked.emplace_back(schgen::py_round(
                        std::abs(x + w / 2 - ax) + std::abs(y + h / 2 - ay), 1), x, y);
                }
            }
            std::sort(ranked.begin(), ranked.end());
            std::optional<std::pair<double, double>> expected;
            for (const auto& [distance, x, y] : ranked) {
                (void)distance;
                if (occ.fits_hashed(x, y, w, h, zero, zero, 3, {})) {
                    expected = {x, y};
                    break;
                }
            }
            const auto got = occ.place_near(ax, ay, w, h, zero, zero, 3, {},
                                             x0, x1, -22, 44);
            if (bool(got) != bool(expected)
                || (got && (got->x != expected->first || got->y != expected->second))) {
                throw std::runtime_error("placement differs from exhaustive ordered search");
            }
        }
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << exc.what() << '\n';
        return 1;
    }
}
