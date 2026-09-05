#pragma once

#include <utility>
#include <vector>

namespace schgen {

using GeomKey = std::pair<int, int>;

struct GeomNode {
    int kx = 0;
    int ky = 0;
    double x = 0.0;
    double y = 0.0;
};

struct GeomSeg {
    double x0 = 0.0;
    double y0 = 0.0;
    double x1 = 0.0;
    double y1 = 0.0;
};

struct GeomBond {
    double ax = 0.0;
    double ay = 0.0;
    double bx = 0.0;
    double by = 0.0;
};

GeomKey geom_key(double x, double y);

std::vector<GeomKey> seed_geometry_unions(
    const std::vector<GeomNode>& nodes, const std::vector<GeomSeg>& segs,
    const std::vector<GeomBond>& bonds);

}  // namespace schgen
