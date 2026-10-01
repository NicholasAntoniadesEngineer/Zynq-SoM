#include "schgen/pack.hpp"
#include <array>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {
using namespace schgen;
void require(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(message);
}
template<class F> void rejects(F f) {
    bool caught = false;
    try { f(); } catch (const std::exception&) { caught = true; }
    require(caught, "negative occupancy contract accepted");
}
void shared_cells(BreatheGrid::Mode mode) {
    BreatheGrid grid(8, 8, 1, 0, 0, nullptr, mode);
    const Box4 keepout{1, 1, 3, 3}, member{2, 2, 4, 4};
    grid.stamp(keepout, 1);
    grid.stamp(member, 1);
    grid.stamp(member, 0);
    require(!grid.free({2, 2, 3, 3}), "removing member erased overlapping keepout");
    require(grid.free({4, 4, 4, 4}), "removed member retained its exclusive cell");
    grid.stamp(keepout, 0);
    require(grid.free({1, 1, 4, 4}), "balanced removals did not release cells");
    // More than 255 simultaneously overlapping halos must not wrap a byte.
    for (int i = 0; i < 300; ++i) grid.stamp(member, 1);
    for (int i = 0; i < 299; ++i) grid.stamp(member, 0);
    require(!grid.free(member), "occupancy multiplicity wrapped or was lost");
    grid.stamp(member, 0);
    require(grid.free(member), "last owner not removed");
}
void atomic_removal_and_clipping() {
    BreatheGrid grid(8, 8, 1, 0, 0, nullptr, BreatheGrid::Mode::Counted);
    grid.stamp({1, 1, 1, 1}, 1);
    auto copy = grid;
    copy.stamp({1, 1, 1, 1}, 0);
    require(!grid.free({1, 1, 1, 1}) && copy.free({1, 1, 1, 1}),
            "trial occupancy copy altered its incumbent");
    rejects([&] { grid.stamp({1, 1, 1, 1}, 2); });
    rejects([&] { grid.stamp({1, 1, 2, 1}, 0); });
    require(!grid.free({1, 1, 1, 1}), "underflow partially removed earlier cells");
    require(grid.free({2, 1, 2, 1}), "underflow created occupancy");
    grid.stamp({1, 1, 1, 1}, 0);
    grid.stamp({-2, -2, 0, 0}, 1);
    grid.stamp({0, 0, 0, 0}, 1);
    grid.stamp({-2, -2, 0, 0}, 0);
    require(!grid.free({0, 0, 0, 0}), "clipped removal erased another owner");
    grid.stamp({0, 0, 0, 0}, 0);
    grid.stamp({-4, -4, -3, -3}, 0); // No in-grid cells to remove.
    require(grid.free({0, 0, 7, 7}), "clipped stamps left occupancy behind");
}
void independent_raster() {
    BreatheGrid grid(8, 8, 1, 0, 0, nullptr, BreatheGrid::Mode::Counted);
    std::array<std::array<unsigned, 8>, 8> expected{};
    std::vector<Box4> boxes;
    for (int i = 0; i < 41; ++i) {
        const int x = (i * 3) % 6, y = (i * 5) % 6;
        boxes.push_back({double(x), double(y), double(x + 1), double(y + 2)});
    }
    auto change = [&](const Box4& b, bool add) {
        grid.stamp(b, add ? 1 : 0);
        for (int y = int(b.y0); y <= int(b.y1); ++y)
            for (int x = int(b.x0); x <= int(b.x1); ++x) {
                if (add) ++expected[y][x]; else --expected[y][x];
            }
        for (int y = 0; y < 8; ++y) for (int x = 0; x < 8; ++x)
            require(grid.free({double(x), double(y), double(x), double(y)}) ==
                        (expected[y][x] == 0), "counted grid differs from independent raster");
    };
    for (const auto& b : boxes) change(b, true);
    for (std::size_t i = 0; i < boxes.size(); i += 2) change(boxes[i], false);
    for (std::size_t i = 1; i < boxes.size(); i += 2) change(boxes[i], false);
}
void legacy_assignment() {
    BreatheGrid grid(8, 8, 1, 0, 0);
    const Box4 b{1, 1, 2, 2};
    grid.stamp(b, 1); grid.stamp(b, 1); grid.stamp(b, 0);
    require(grid.free(b), "default assignment API changed");
}
}
int main() {
    try {
        shared_cells(BreatheGrid::Mode::Counted);
        // The original binary-assignment implementation must fail this oracle.
        rejects([] { shared_cells(BreatheGrid::Mode::Assignment); });
        atomic_removal_and_clipping(); independent_raster(); legacy_assignment();
        std::cout << "breathe overlap ownership contracts PASS\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n'; return 1;
    }
}
