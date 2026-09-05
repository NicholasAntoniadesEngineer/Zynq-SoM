#include "schgen/cc.hpp"

#include "schgen/occupancy.hpp"
#include "schgen/pack.hpp"

#include <cmath>
#include <cstddef>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <utility>
#include <vector>

namespace schgen {
namespace {

constexpr double kGeomQuant = 1000.0;

int quantized_axis(double world) {
    const double rounded = py_round(world * kGeomQuant, 0);
    if (!std::isfinite(rounded)) {
        throw std::runtime_error("geom_key: quantized axis is not finite");
    }
    const double max_int = static_cast<double>(std::numeric_limits<int>::max());
    const double min_int = static_cast<double>(std::numeric_limits<int>::min());
    if (rounded > max_int || rounded < min_int) {
        throw std::runtime_error("geom_key: quantized axis exceeds int range");
    }
    return static_cast<int>(rounded);
}

class GeomUnionFind {
public:
    GeomKey find(const GeomKey& key) {
        parent_.emplace(key, key);
        GeomKey root = key;
        while (parent_.at(root) != root) {
            root = parent_.at(root);
        }
        GeomKey walk = key;
        while (parent_.at(walk) != root) {
            const GeomKey next = parent_.at(walk);
            parent_.at(walk) = root;
            walk = next;
        }
        return root;
    }

    GeomKey unite(const GeomKey& key_a, const GeomKey& key_b) {
        const GeomKey root_a = find(key_a);
        const GeomKey root_b = find(key_b);
        if (root_a == root_b) {
            return root_a;
        }
        const GeomKey low_root = (root_a < root_b) ? root_a : root_b;
        const GeomKey high_root = (root_a < root_b) ? root_b : root_a;
        parent_.at(high_root) = low_root;
        return low_root;
    }

private:
    std::map<GeomKey, GeomKey> parent_;
};

}  // namespace

GeomKey geom_key(double x, double y) {
    return GeomKey{quantized_axis(x), quantized_axis(y)};
}

std::vector<GeomKey> seed_geometry_unions(
    const std::vector<GeomNode>& nodes, const std::vector<GeomSeg>& segs,
    const std::vector<GeomBond>& bonds) {
    std::map<GeomKey, std::size_t> node_by_key;
    for (std::size_t node_index = 0; node_index < nodes.size(); ++node_index) {
        node_by_key.emplace(GeomKey{nodes[node_index].kx, nodes[node_index].ky},
                            node_index);
    }

    GeomUnionFind union_find;
    for (const GeomNode& geom_node : nodes) {
        union_find.find(GeomKey{geom_node.kx, geom_node.ky});
    }

    for (const GeomSeg& geom_seg : segs) {
        union_find.unite(geom_key(geom_seg.x0, geom_seg.y0),
                         geom_key(geom_seg.x1, geom_seg.y1));
    }

    for (const GeomSeg& geom_seg : segs) {
        const GeomKey start_key = geom_key(geom_seg.x0, geom_seg.y0);
        const GeomKey end_key = geom_key(geom_seg.x1, geom_seg.y1);
        for (const GeomNode& geom_node : nodes) {
            const GeomKey node_key{geom_node.kx, geom_node.ky};
            if (node_key == start_key || node_key == end_key) {
                continue;
            }
            if (point_on_seg(geom_node.x, geom_node.y, geom_seg.x0, geom_seg.y0,
                             geom_seg.x1, geom_seg.y1, false)) {
                union_find.unite(node_key, start_key);
            }
        }
    }

    std::vector<std::pair<GeomKey, std::size_t>> endpoint_owners;
    std::set<GeomKey> seen_keys;
    for (std::size_t seg_index = 0; seg_index < segs.size(); ++seg_index) {
        const GeomKey start_key =
            geom_key(segs[seg_index].x0, segs[seg_index].y0);
        if (seen_keys.insert(start_key).second) {
            endpoint_owners.emplace_back(start_key, seg_index);
        }
    }
    for (std::size_t seg_index = 0; seg_index < segs.size(); ++seg_index) {
        const GeomKey end_key = geom_key(segs[seg_index].x1, segs[seg_index].y1);
        if (seen_keys.insert(end_key).second) {
            endpoint_owners.emplace_back(end_key, seg_index);
        }
    }

    for (const auto& endpoint : endpoint_owners) {
        const GeomKey endpoint_key = endpoint.first;
        const std::size_t owner_index = endpoint.second;
        const auto found = node_by_key.find(endpoint_key);
        if (found == node_by_key.end()) {
            throw std::runtime_error(
                "seed_geometry_unions: endpoint key missing from nodes");
        }
        const GeomNode& endpoint_node = nodes[found->second];
        for (std::size_t seg_index = 0; seg_index < segs.size(); ++seg_index) {
            if (seg_index == owner_index) {
                continue;
            }
            const GeomSeg& geom_seg = segs[seg_index];
            if (point_on_seg(endpoint_node.x, endpoint_node.y, geom_seg.x0,
                             geom_seg.y0, geom_seg.x1, geom_seg.y1, false)) {
                union_find.unite(endpoint_key,
                                 geom_key(geom_seg.x0, geom_seg.y0));
            }
        }
    }

    for (const GeomBond& geom_bond : bonds) {
        union_find.unite(geom_key(geom_bond.ax, geom_bond.ay),
                         geom_key(geom_bond.bx, geom_bond.by));
    }

    std::vector<GeomKey> node_roots;
    node_roots.reserve(nodes.size());
    for (const GeomNode& geom_node : nodes) {
        node_roots.push_back(
            union_find.find(GeomKey{geom_node.kx, geom_node.ky}));
    }
    return node_roots;
}

}  // namespace schgen
