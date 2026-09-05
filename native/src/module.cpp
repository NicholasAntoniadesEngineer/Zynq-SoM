#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <tuple>
#include <utility>

#include <nanobind/nanobind.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/tuple.h>
#include <nanobind/stl/vector.h>

#include "schgen/emit.hpp"
#include "schgen/legalize.hpp"
#include "schgen/occupancy.hpp"
#include "schgen/route.hpp"
#include "schgen/seat.hpp"
#include "schgen/sexpr.hpp"

namespace nb = nanobind;

namespace {

schgen::Halo as_halo(const std::tuple<double, double, double, double>& t) {
    return schgen::Halo{std::get<0>(t), std::get<1>(t), std::get<2>(t),
                        std::get<3>(t)};
}

std::vector<schgen::Comp> as_comps(
    const std::vector<std::tuple<double, double, double, double, int>>& raw) {
    std::vector<schgen::Comp> out;
    out.reserve(raw.size());
    for (const auto& t : raw) {
        out.push_back(schgen::Comp{std::get<0>(t), std::get<1>(t),
                                   std::get<2>(t), std::get<3>(t),
                                   std::get<4>(t)});
    }
    return out;
}

using BoxTup = std::tuple<double, double, double, double>;

schgen::Box4 as_box(const BoxTup& t) {
    return schgen::Box4{std::get<0>(t), std::get<1>(t), std::get<2>(t),
                        std::get<3>(t)};
}

std::vector<schgen::Box4> as_boxes(const std::vector<BoxTup>& raw) {
    std::vector<schgen::Box4> out;
    out.reserve(raw.size());
    for (const auto& t : raw) {
        out.push_back(as_box(t));
    }
    return out;
}

std::vector<schgen::Seg2> as_segs(const std::vector<BoxTup>& raw) {
    std::vector<schgen::Seg2> out;
    out.reserve(raw.size());
    for (const auto& t : raw) {
        out.push_back(schgen::Seg2{std::get<0>(t), std::get<1>(t),
                                   std::get<2>(t), std::get<3>(t)});
    }
    return out;
}

using PtTup = std::tuple<double, double>;

std::vector<std::pair<double, double>> as_pts(const std::vector<PtTup>& raw) {
    std::vector<std::pair<double, double>> out;
    out.reserve(raw.size());
    for (const auto& t : raw) {
        out.emplace_back(std::get<0>(t), std::get<1>(t));
    }
    return out;
}

nb::object sexpr_to_tagged(const schgen::Sexpr& node) {
    if (std::holds_alternative<schgen::Sexpr::Sym>(node.v)) {
        return nb::make_tuple("sym", std::get<schgen::Sexpr::Sym>(node.v).name);
    }
    if (std::holds_alternative<std::string>(node.v)) {
        return nb::make_tuple("str", std::get<std::string>(node.v));
    }
    if (std::holds_alternative<bool>(node.v)) {
        return nb::make_tuple("bool", std::get<bool>(node.v));
    }
    if (std::holds_alternative<double>(node.v)) {
        return nb::make_tuple("num", std::get<double>(node.v));
    }
    nb::list children;
    for (const auto& child : std::get<schgen::SexprList>(node.v)) {
        children.append(sexpr_to_tagged(child));
    }
    return nb::make_tuple("list", children);
}

schgen::Sexpr sexpr_from_py(nb::handle handle) {
    if (nb::isinstance<nb::list>(handle)) {
        schgen::SexprList lst;
        for (nb::handle child : nb::borrow<nb::list>(handle)) {
            lst.push_back(sexpr_from_py(child));
        }
        return schgen::Sexpr{std::move(lst)};
    }
    if (nb::isinstance<nb::bool_>(handle)) {
        return schgen::Sexpr{nb::cast<bool>(handle)};
    }
    if (nb::isinstance<nb::int_>(handle)) {
        return schgen::Sexpr{
            static_cast<double>(nb::cast<std::int64_t>(handle))};
    }
    if (nb::isinstance<nb::float_>(handle)) {
        return schgen::Sexpr{nb::cast<double>(handle)};
    }
    if (nb::isinstance<nb::str>(handle)) {
        const std::string text = nb::cast<std::string>(handle);
        const std::string type_name =
            nb::cast<std::string>(handle.type().attr("__name__"));
        if (type_name == "Sym") {
            return schgen::Sexpr{schgen::Sexpr::Sym{text}};
        }
        return schgen::Sexpr{text};
    }
    throw std::runtime_error("sexpr: cannot serialise this Python object");
}

}  // namespace

NB_MODULE(_geom, m) {
    m.doc() = "schgen native kernels — occupancy, seat, sexpr";
    m.def("fanout_sep",
          [](const std::tuple<double, double, double, double>& ar,
             const std::tuple<double, double, double, double>& ai,
             const std::tuple<double, double, double, double>& br,
             const std::tuple<double, double, double, double>& bi,
             const char* axis) {
              if (axis == nullptr || axis[0] == '\0') {
                  throw std::runtime_error("_geom.fanout_sep: axis required");
              }
              return schgen::fanout_sep(as_halo(ar), as_halo(ai), as_halo(br),
                                        as_halo(bi), axis[0]);
          });
    m.def("boxes_separated", &schgen::boxes_separated);
    m.def("pairs_hold",
          [](const std::vector<std::vector<std::tuple<
                 double, double, double, double,
                 std::tuple<double, double, double, double>,
                 std::tuple<double, double, double, double>,
                 int, int, bool>>>& groups,
             int subject_count, double clear) {
              if (subject_count < 0) {
                  throw std::runtime_error("pairs_hold: subject_count required");
              }
              std::vector<std::vector<schgen::Rect>> rows;
              rows.reserve(groups.size());
              for (const auto& group : groups) {
                  std::vector<schgen::Rect> row;
                  row.reserve(group.size());
                  for (const auto& t : group) {
                      schgen::Rect r;
                      r.x = std::get<0>(t);
                      r.y = std::get<1>(t);
                      r.w = std::get<2>(t);
                      r.h = std::get<3>(t);
                      r.reach = as_halo(std::get<4>(t));
                      r.inset = as_halo(std::get<5>(t));
                      r.mask = std::get<6>(t);
                      r.pmask = std::get<7>(t);
                      r.main = std::get<8>(t);
                      row.push_back(r);
                  }
                  rows.push_back(std::move(row));
              }
              return schgen::pairs_hold(rows,
                                        static_cast<std::size_t>(subject_count),
                                        clear);
          });
    m.def("py_round", &schgen::py_round);
    m.def("pair_axis",
          [](const std::tuple<double, double, double, double>& a,
             const std::tuple<double, double, double, double>& b) {
              auto hit = schgen::pair_axis(as_box(a), as_box(b));
              return std::make_tuple(hit.axis_x ? "x" : "y", hit.a_first);
          });
    m.def("bellman_ford",
          [](int node_count, const std::vector<int>& src,
             const std::vector<int>& dst, const std::vector<double>& cost) {
              if (node_count <= 0) {
                  throw std::runtime_error("bellman_ford: node_count required");
              }
              auto hit = schgen::bellman_ford(
                  static_cast<std::size_t>(node_count), src, dst, cost);
              return std::make_tuple(hit.feasible, hit.dist, hit.cycle_edges);
          });
    m.def("boxes_overlap",
          [](const std::tuple<double, double, double, double>& a,
             const std::tuple<double, double, double, double>& b,
             double halo) {
              return schgen::boxes_overlap(
                  schgen::Box4{std::get<0>(a), std::get<1>(a),
                               std::get<2>(a), std::get<3>(a)},
                  schgen::Box4{std::get<0>(b), std::get<1>(b),
                               std::get<2>(b), std::get<3>(b)},
                  halo);
          });
    m.def("spot_free",
          [](const std::tuple<double, double, double, double>& bx, double pad,
             const std::vector<std::tuple<double, double, double, double>>& parts,
             const std::vector<std::tuple<double, double, double, double>>& segs,
             const std::vector<std::tuple<double, double, double, double>>& ncs) {
              auto as_box = [](const auto& t) {
                  return schgen::Box4{std::get<0>(t), std::get<1>(t),
                                      std::get<2>(t), std::get<3>(t)};
              };
              std::vector<schgen::Box4> p, s, n;
              for (const auto& t : parts) p.push_back(as_box(t));
              for (const auto& t : segs) s.push_back(as_box(t));
              for (const auto& t : ncs) n.push_back(as_box(t));
              return schgen::spot_free(as_box(bx), pad, p, s, n);
          });
    m.def("seat_scan",
          [](double tcx, double tcy, int n, double step, double halo,
             double net_w, int cap,
             const std::vector<std::tuple<double, double, double, double>>& placed,
             const std::vector<std::tuple<double, double, double, double>>& forbid,
             const std::vector<std::tuple<std::tuple<double, double, double, double>,
                                          double>>& subjects,
             const std::vector<std::tuple<
                 std::vector<std::tuple<double, double, double, double>>,
                 double>>& attract,
             const std::vector<std::tuple<
                 std::vector<std::tuple<double, double, double, double>>,
                 double>>& repulse,
             const std::vector<double>& rots,
             const std::vector<std::vector<
                 std::tuple<double, double, double, double>>>& rel_pads,
             const std::vector<std::tuple<double, double, double, double>>& body,
             const std::vector<std::vector<std::tuple<
                 double, double,
                 std::vector<std::tuple<double, double>>>>>& align) {
              auto as_box = [](const auto& t) {
                  return schgen::Box4{std::get<0>(t), std::get<1>(t),
                                      std::get<2>(t), std::get<3>(t)};
              };
              std::vector<schgen::Box4> pl, fb, bd;
              for (const auto& t : placed) pl.push_back(as_box(t));
              for (const auto& t : forbid) fb.push_back(as_box(t));
              for (const auto& t : body) bd.push_back(as_box(t));
              std::vector<schgen::Subject> subj;
              for (const auto& t : subjects) {
                  subj.push_back(schgen::Subject{as_box(std::get<0>(t)),
                                                 std::get<1>(t)});
              }
              std::vector<schgen::BoundGroup> att, rep;
              for (const auto& t : attract) {
                  schgen::BoundGroup g;
                  g.limit = std::get<1>(t);
                  for (const auto& b : std::get<0>(t)) g.boxes.push_back(as_box(b));
                  att.push_back(std::move(g));
              }
              for (const auto& t : repulse) {
                  schgen::BoundGroup g;
                  g.limit = std::get<1>(t);
                  for (const auto& b : std::get<0>(t)) g.boxes.push_back(as_box(b));
                  rep.push_back(std::move(g));
              }
              std::vector<std::vector<schgen::Box4>> rel;
              for (const auto& rot_pads : rel_pads) {
                  std::vector<schgen::Box4> row;
                  for (const auto& b : rot_pads) row.push_back(as_box(b));
                  rel.push_back(std::move(row));
              }
              std::vector<std::vector<schgen::AlignTerm>> aln;
              for (const auto& rot_al : align) {
                  std::vector<schgen::AlignTerm> row;
                  for (const auto& t : rot_al) {
                      schgen::AlignTerm a;
                      a.rxc = std::get<0>(t);
                      a.ryc = std::get<1>(t);
                      for (const auto& p : std::get<2>(t)) {
                          a.pts.emplace_back(std::get<0>(p), std::get<1>(p));
                      }
                      row.push_back(std::move(a));
                  }
                  aln.push_back(std::move(row));
              }
              auto got = schgen::seat_scan(tcx, tcy, n, step, halo, net_w, cap,
                                           pl, fb, subj, att, rep, rots, rel,
                                           bd, aln);
              std::vector<std::tuple<double, double, double, double, double, double>>
                  out;
              for (const auto& h : got.hits) {
                  out.emplace_back(h.score, h.abs_x, h.abs_y, h.rot, h.cx, h.cy);
              }
              return std::make_tuple(out, got.truncated);
          });
    m.def("box_gap",
          [](const std::tuple<double, double, double, double>& a,
             const std::tuple<double, double, double, double>& b) {
              return schgen::box_gap(as_box(a), as_box(b));
          });
    m.def("seat_candidates",
          [](
              double tcx, double tcy, int n, double step, double halo,
              double bound_eff, double keep_min, bool forbid_plus_x, int cap,
              const std::tuple<double, double, double, double>& icb,
              const std::vector<std::tuple<double, double, double, double>>&
                  skeleton,
              const std::vector<double>& rots,
              const std::vector<std::tuple<double, double, double, double>>&
                  bodies,
              const std::vector<std::vector<
                  std::tuple<double, double, double, double>>>& rel_pads,
              const std::vector<std::tuple<double, double, double, double>>&
                  target_pins,
              const std::vector<std::tuple<double, double, double, double>>&
                  keep_pins) {
              std::vector<std::vector<schgen::Box4>> rel;
              for (const auto& row : rel_pads) {
                  rel.push_back(as_boxes(row));
              }
              auto got = schgen::seat_candidates(
                  tcx, tcy, n, step, halo, bound_eff, keep_min, forbid_plus_x,
                  cap, as_box(icb), as_boxes(skeleton), rots, as_boxes(bodies),
                  rel, as_boxes(target_pins), as_boxes(keep_pins));
              std::vector<std::tuple<double, double, double, double, double,
                                     double, double, double, double, double>>
                  hits;
              for (const auto& h : got.hits) {
                  hits.emplace_back(h.dist, h.abs_x, h.abs_y, h.rot, h.cx,
                                    h.cy, h.body.x0, h.body.y0, h.body.x1,
                                    h.body.y1);
              }
              return std::make_tuple(hits, got.truncated);
          });
    m.def("seat_dfs",
          [](
              const std::vector<std::vector<
                  std::tuple<double, double, double, double>>>& cand_boxes,
              const std::vector<std::tuple<double, double, double, double>>&
                  skeleton,
              double halo, int node_budget) {
              std::vector<std::vector<schgen::Box4>> rows;
              for (const auto& row : cand_boxes) {
                  rows.push_back(as_boxes(row));
              }
              auto r = schgen::seat_dfs(rows, as_boxes(skeleton), halo,
                                        node_budget);
              return std::make_tuple(r.solved, r.budget_hit, r.nodes, r.pick);
          });
    m.def("corridor_free",
          [](
              double y, double xa, double xb,
              const std::vector<std::tuple<double, double, double, double>>&
                  boxes,
              const std::vector<std::tuple<double, double, double, double>>&
                  segs,
              double seg_pad) {
              return schgen::corridor_free(y, xa, xb, as_boxes(boxes),
                                           as_segs(segs), seg_pad);
          });
    m.def("corridor_clear_vert",
          [](
              double x, double y_pin, double ty,
              const std::vector<std::tuple<double, double, double, double>>&
                  boxes,
              const std::vector<std::tuple<double, double, double, double>>&
                  segs,
              double seg_pad) {
              return schgen::corridor_clear_vert(x, y_pin, ty, as_boxes(boxes),
                                                 as_segs(segs), seg_pad);
          });
    m.def("cell_free_point",
          [](
              double x, double y,
              const std::vector<std::tuple<double, double, double, double>>&
                  boxes,
              const std::vector<std::tuple<double, double, double, double>>&
                  segs,
              double seg_pad) {
              return schgen::cell_free_point(x, y, as_boxes(boxes),
                                             as_segs(segs), seg_pad);
          });
    m.def("sexpr_fmt_num", &schgen::sexpr_fmt_num);
    m.def("sexpr_roundtrip", [](const char* text) {
        if (text == nullptr) {
            throw std::runtime_error("sexpr_roundtrip: text required");
        }
        return schgen::sexpr_dumps(schgen::sexpr_loads(text));
    });
    m.def("sexpr_loads_tagged", [](const char* text) {
        if (text == nullptr) {
            throw std::runtime_error("sexpr_loads_tagged: text required");
        }
        return sexpr_to_tagged(schgen::sexpr_loads(text));
    });
    m.def("sexpr_dumps_py", [](nb::handle node, int indent) {
        return schgen::sexpr_dumps(sexpr_from_py(node), indent);
    });
    m.def("emit_via",
          [](double x, double y, double size, double drill, double net,
             const char* uuid, bool locked) {
              if (uuid == nullptr) {
                  throw std::runtime_error("emit_via: uuid required");
              }
              return sexpr_to_tagged(
                  schgen::emit_via(x, y, size, drill, net, uuid, locked));
          });
    m.def("emit_segment",
          [](double x1, double y1, double x2, double y2, double width,
             const char* layer, double net, const char* uuid) {
              if (layer == nullptr || uuid == nullptr) {
                  throw std::runtime_error("emit_segment: layer and uuid required");
              }
              return sexpr_to_tagged(schgen::emit_segment(
                  x1, y1, x2, y2, width, layer, net, uuid));
          });
    m.def("emit_gr_line",
          [](double ax, double ay, double bx, double by, double width,
             const char* layer, const char* uuid) {
              if (layer == nullptr || uuid == nullptr) {
                  throw std::runtime_error("emit_gr_line: layer and uuid required");
              }
              return sexpr_to_tagged(schgen::emit_gr_line(
                  ax, ay, bx, by, width, layer, uuid));
          });
    m.def("emit_edge_line",
          [](double ax, double ay, double bx, double by, const char* uuid) {
              if (uuid == nullptr) {
                  throw std::runtime_error("emit_edge_line: uuid required");
              }
              return sexpr_to_tagged(
                  schgen::emit_edge_line(ax, ay, bx, by, uuid));
          });
    m.def("emit_gr_text",
          [](const char* text, double x, double y, double rot,
             const char* layer, const char* uuid, double font_size,
             double thickness, const char* justify) {
              if (text == nullptr || layer == nullptr || uuid == nullptr
                  || justify == nullptr) {
                  throw std::runtime_error(
                      "emit_gr_text: text, layer, uuid, justify required");
              }
              return sexpr_to_tagged(schgen::emit_gr_text(
                  text, x, y, rot, layer, uuid, font_size, thickness,
                  justify));
          });
    m.def("emit_fill_zone",
          [](double net, const char* net_name, const char* zname,
             const char* layer, const std::vector<PtTup>& corners,
             const char* uuid, double clearance, bool solid,
             double min_thickness) {
              if (net_name == nullptr || zname == nullptr || layer == nullptr
                  || uuid == nullptr) {
                  throw std::runtime_error(
                      "emit_fill_zone: net_name, zname, layer, uuid required");
              }
              return sexpr_to_tagged(schgen::emit_fill_zone(
                  net, net_name, zname, layer, as_pts(corners), uuid,
                  clearance, solid, min_thickness));
          });
    m.def("emit_keepout_zone",
          [](const std::vector<PtTup>& corners, const char* uuid,
             const char* name) {
              if (uuid == nullptr || name == nullptr) {
                  throw std::runtime_error(
                      "emit_keepout_zone: uuid and name required");
              }
              return sexpr_to_tagged(
                  schgen::emit_keepout_zone(as_pts(corners), uuid, name));
          });
    m.def("emit_effects",
          [](double size, bool hide, const char* justify) {
              if (justify == nullptr) {
                  throw std::runtime_error("emit_effects: justify required");
              }
              return sexpr_to_tagged(schgen::emit_effects(size, hide, justify));
          });
    m.def("emit_property",
          [](const char* name, const char* value, double x, double y,
             double rot, bool hide) {
              if (name == nullptr || value == nullptr) {
                  throw std::runtime_error(
                      "emit_property: name and value required");
              }
              return sexpr_to_tagged(
                  schgen::emit_property(name, value, x, y, rot, hide));
          });
    m.def("emit_sch_label",
          [](const char* tag, const char* name, const char* shape, double x,
             double y, double rot, const char* justify, const char* uuid) {
              if (tag == nullptr || name == nullptr || shape == nullptr
                  || justify == nullptr || uuid == nullptr) {
                  throw std::runtime_error(
                      "emit_sch_label: tag, name, shape, justify, uuid "
                      "required");
              }
              return sexpr_to_tagged(schgen::emit_sch_label(
                  tag, name, shape, x, y, rot, justify, uuid));
          });
    m.def("quads_overlap",
          [](const std::vector<PtTup>& a, const std::vector<PtTup>& b) {
              return schgen::quads_overlap(as_pts(a), as_pts(b));
          });
    m.def("emit_wire",
          [](double x0, double y0, double x1, double y1, const char* uuid) {
              if (uuid == nullptr) {
                  throw std::runtime_error("emit_wire: uuid required");
              }
              return sexpr_to_tagged(schgen::emit_wire(x0, y0, x1, y1, uuid));
          });
    m.def("emit_junction",
          [](double x, double y, const char* uuid) {
              if (uuid == nullptr) {
                  throw std::runtime_error("emit_junction: uuid required");
              }
              return sexpr_to_tagged(schgen::emit_junction(x, y, uuid));
          });
    m.def("emit_no_connect",
          [](double x, double y, const char* uuid) {
              if (uuid == nullptr) {
                  throw std::runtime_error("emit_no_connect: uuid required");
              }
              return sexpr_to_tagged(schgen::emit_no_connect(x, y, uuid));
          });
    m.def("route_snap_ok", &schgen::route_snap_ok);
    m.def("route_cell_of",
          [](double x, double y, double grid) {
              auto c = schgen::route_cell_of(x, y, grid);
              return std::make_tuple(c.first, c.second);
          });
    m.def("route_point_of",
          [](int i, int j, double grid) {
              auto p = schgen::route_point_of(i, j, grid);
              return std::make_tuple(p.first, p.second);
          });
    m.def("route_cells_between",
          [](double x0, double y0, double x1, double y1, double grid) {
              auto cells = schgen::route_cells_between({x0, y0}, {x1, y1},
                                                       grid);
              std::vector<std::tuple<int, int>> out;
              for (const auto& c : cells) {
                  out.emplace_back(c.first, c.second);
              }
              return out;
          });
    nb::class_<schgen::RouteGrid>(m, "RouteGrid")
        .def(nb::init<>())
        .def("claim",
             [](schgen::RouteGrid& self, const char* owner,
                const std::vector<std::tuple<int, int>>& cells,
                const char* what) {
                 if (owner == nullptr || what == nullptr) {
                     throw std::runtime_error("RouteGrid.claim: owner and what "
                                              "required");
                 }
                 std::vector<schgen::RouteCell> cs;
                 for (const auto& c : cells) {
                     cs.emplace_back(std::get<0>(c), std::get<1>(c));
                 }
                 self.claim(owner, cs, what);
             })
        .def("block_box", &schgen::RouteGrid::block_box)
        .def("free_or",
             [](const schgen::RouteGrid& self, const char* net, int i, int j) {
                 if (net == nullptr) {
                     throw std::runtime_error("RouteGrid.free_or: net required");
                 }
                 return self.free_or(net, {i, j});
             });
    m.def("route_bfs_join",
          [](schgen::RouteGrid& grid, const char* net,
             const std::vector<std::tuple<double, double>>& comp_a,
             const std::vector<std::tuple<double, double>>& comp_b,
             double grid_mm) {
              if (net == nullptr) {
                  throw std::runtime_error("route_bfs_join: net required");
              }
              std::vector<schgen::RoutePoint> a, b;
              for (const auto& p : comp_a) {
                  a.emplace_back(std::get<0>(p), std::get<1>(p));
              }
              for (const auto& p : comp_b) {
                  b.emplace_back(std::get<0>(p), std::get<1>(p));
              }
              auto way = schgen::route_bfs_join(grid, net, a, b, grid_mm);
              std::vector<std::tuple<double, double>> out;
              for (const auto& p : way) {
                  out.emplace_back(p.first, p.second);
              }
              return out;
          });

    nb::class_<schgen::Occupancy>(m, "Occupancy")
        .def(nb::init<double, double, double, double, double, double, double>())
        .def("set_board", &schgen::Occupancy::set_board)
        .def("add",
             [](schgen::Occupancy& self, double x, double y, double w, double h,
                const std::tuple<double, double, double, double>& reach,
                const std::tuple<double, double, double, double>& inset,
                int mask,
                const std::vector<std::tuple<double, double, double, double, int>>&
                    comps) {
                 self.add(x, y, w, h, as_halo(reach), as_halo(inset), mask,
                          as_comps(comps));
             })
        .def("remove",
             [](schgen::Occupancy& self, double x, double y, double w, double h,
                const std::tuple<double, double, double, double>& reach,
                const std::tuple<double, double, double, double>& inset,
                int mask,
                const std::vector<std::tuple<double, double, double, double, int>>&
                    comps) {
                 self.remove(x, y, w, h, as_halo(reach), as_halo(inset), mask,
                             as_comps(comps));
             })
        .def("fits_exhaustive",
             [](const schgen::Occupancy& self, double x, double y, double w,
                double h,
                const std::tuple<double, double, double, double>& reach,
                const std::tuple<double, double, double, double>& inset,
                int mask,
                const std::vector<std::tuple<double, double, double, double, int>>&
                    comps) {
                 return self.fits_exhaustive(x, y, w, h, as_halo(reach),
                                             as_halo(inset), mask,
                                             as_comps(comps));
             })
        .def("fits_hashed",
             [](const schgen::Occupancy& self, double x, double y, double w,
                double h,
                const std::tuple<double, double, double, double>& reach,
                const std::tuple<double, double, double, double>& inset,
                int mask,
                const std::vector<std::tuple<double, double, double, double, int>>&
                    comps) {
                 return self.fits_hashed(x, y, w, h, as_halo(reach),
                                         as_halo(inset), mask, as_comps(comps));
             })
        .def("place_near",
             [](const schgen::Occupancy& self, double ax, double ay, double w,
                double h,
                const std::tuple<double, double, double, double>& reach,
                const std::tuple<double, double, double, double>& inset,
                int mask,
                const std::vector<std::tuple<double, double, double, double, int>>&
                    comps,
                double wx0, double wx1, double wy0, double wy1)
                 -> std::optional<std::tuple<double, double, double, double>> {
                 auto hit = self.place_near(ax, ay, w, h, as_halo(reach),
                                            as_halo(inset), mask,
                                            as_comps(comps), wx0, wx1, wy0,
                                            wy1);
                 if (!hit) {
                     return std::nullopt;
                 }
                 return std::make_tuple(hit->x, hit->y, hit->w, hit->h);
             })
        .def_prop_ro("rect_count", &schgen::Occupancy::rect_count);
}
