#include <cstddef>
#include <cstdint>
#include <optional>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <utility>

#include <nanobind/nanobind.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/tuple.h>
#include <nanobind/stl/vector.h>

#include "schgen/catalog.hpp"
#include "schgen/circuit.hpp"
#include "schgen/cc.hpp"
#include "schgen/embed_fp.hpp"
#include "schgen/emit.hpp"
#include "schgen/legalize.hpp"
#include "schgen/occupancy.hpp"
#include "schgen/pack.hpp"
#include "schgen/pack_anchor.hpp"
#include "schgen/pack_edges.hpp"
#include "schgen/pack_refine.hpp"
#include "schgen/pcb_scan.hpp"
#include "schgen/place_geom.hpp"
#include "schgen/place_search.hpp"
#include "schgen/quantize.hpp"
#include "schgen/reorder.hpp"
#include "schgen/route.hpp"
#include "schgen/seat.hpp"
#include "schgen/sexpr.hpp"
#include "schgen/turn.hpp"

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
using HaloTup = std::tuple<double, double, double, double>;
using EntTup = std::tuple<double, double, double, double, HaloTup, HaloTup, int,
                          int, bool>;
using CompTup = std::tuple<double, double, double, double, int>;
using BlockTup = std::tuple<double, double, double, double, HaloTup, HaloTup,
                            int, std::vector<CompTup>>;

EntTup as_ent(const schgen::Rect& rect) {
    return EntTup{rect.x, rect.y, rect.w, rect.h,
                  HaloTup{rect.reach.w, rect.reach.e, rect.reach.n,
                          rect.reach.s},
                  HaloTup{rect.inset.w, rect.inset.e, rect.inset.n,
                          rect.inset.s},
                  rect.mask, rect.pmask, rect.main};
}

schgen::PairsBlock as_pairs_block(const BlockTup& row) {
    schgen::PairsBlock block;
    block.x = std::get<0>(row);
    block.y = std::get<1>(row);
    block.w = std::get<2>(row);
    block.h = std::get<3>(row);
    block.reach = as_halo(std::get<4>(row));
    block.inset = as_halo(std::get<5>(row));
    block.mask = std::get<6>(row);
    block.comps = as_comps(std::get<7>(row));
    return block;
}

std::vector<schgen::PairsBlock> as_pairs_blocks(
    const std::vector<BlockTup>& rows) {
    std::vector<schgen::PairsBlock> out;
    out.reserve(rows.size());
    for (const auto& row : rows) {
        out.push_back(as_pairs_block(row));
    }
    return out;
}

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
    m.doc() = "schgen native kernels — occupancy, seat, sexpr, catalog";
    m.def("catalog_compile",
          [](const std::string& parts_dir, const std::string& catalog_path) {
              return schgen::compile_part_catalog(parts_dir, catalog_path);
          });
    m.def("catalog_open",
          [](const std::string& catalog_path) {
              return schgen::open_part_catalog(catalog_path);
          });
    m.def("catalog_close", []() { return schgen::close_part_catalog(); });
    m.def("catalog_count", []() { return schgen::part_catalog_count(); });
    m.def("catalog_lookup", [](const std::string& mpn) {
        const schgen::CatalogPart part = schgen::lookup_part_catalog(mpn);
        nb::dict rec;
        rec["mpn"] = part.mpn;
        rec["safe_name"] = part.safe_name;
        rec["lcsc"] = part.lcsc;
        rec["description"] = part.description;
        rec["manufacturer"] = part.manufacturer;
        rec["package"] = part.package;
        rec["jlc_class"] = part.jlc_class;
        rec["prefix"] = part.prefix;
        rec["datasheet"] = part.datasheet;
        rec["product_url"] = part.product_url;
        rec["lib_id"] = part.lib_id;
        rec["footprint"] = part.footprint;
        nb::list models;
        for (const std::string& model : part.models_3d) {
            models.append(model);
        }
        rec["models_3d"] = models;
        nb::list pins;
        for (const schgen::CatalogPin& pin : part.pins) {
            pins.append(nb::make_tuple(pin.number, pin.name, pin.etype));
        }
        rec["pins"] = pins;
        return rec;
    });
    m.def("circuit_compile",
          [](const std::string& circuits_dir, const std::string& catalog_path) {
              return schgen::compile_circuit_catalog(circuits_dir, catalog_path);
          });
    m.def("circuit_open",
          [](const std::string& catalog_path) {
              return schgen::open_circuit_catalog(catalog_path);
          });
    m.def("circuit_close", []() { return schgen::close_circuit_catalog(); });
    m.def("circuit_count", []() { return schgen::circuit_catalog_count(); });
    m.def("circuit_lookup", [](const std::string& name) {
        const schgen::CircuitSheetIr sheet = schgen::lookup_circuit_catalog(name);
        nb::dict rec;
        rec["schema"] = sheet.schema;
        rec["name"] = sheet.name;
        rec["title"] = sheet.title;
        nb::list parts;
        for (const schgen::CircuitPartIr& part : sheet.parts) {
            nb::dict prec;
            prec["ref"] = part.ref;
            prec["lib_id"] = part.lib_id;
            prec["value"] = part.value;
            prec["footprint"] = part.footprint;
            nb::dict fields;
            for (const schgen::CircuitFieldIr& field : part.fields) {
                fields[field.key.c_str()] = field.value;
            }
            prec["fields"] = fields;
            nb::dict pin_names;
            for (const schgen::CircuitPinNameIr& pin_name : part.pin_names) {
                nb::list nums;
                for (const std::string& number : pin_name.numbers) {
                    nums.append(number);
                }
                pin_names[pin_name.name.c_str()] = nums;
            }
            prec["pin_names"] = pin_names;
            nb::list pin_numbers;
            for (const std::string& number : part.pin_numbers) {
                pin_numbers.append(number);
            }
            prec["pin_numbers"] = pin_numbers;
            parts.append(prec);
        }
        rec["parts"] = parts;
        nb::list nets;
        for (const schgen::CircuitNetIr& net : sheet.nets) {
            nb::dict nrec;
            nrec["name"] = net.name;
            nrec["net_class"] = net.net_class;
            nb::list pins;
            for (const schgen::CircuitPinRefIr& pin : net.pins) {
                pins.append(pin.ref + "." + pin.pin);
            }
            nrec["pins"] = pins;
            nets.append(nrec);
        }
        rec["nets"] = nets;
        nb::list nc;
        for (const schgen::CircuitPinRefIr& pin : sheet.nc) {
            nc.append(pin.ref + "." + pin.pin);
        }
        rec["nc"] = nc;
        nb::dict port_types;
        for (const schgen::CircuitPortIr& port : sheet.port_types) {
            nb::dict prec;
            prec["kind"] = port.kind;
            if (port.has_pair_with) {
                prec["pair_with"] = port.pair_with;
            } else {
                prec["pair_with"] = nb::none();
            }
            if (port.has_impedance) {
                prec["impedance"] = port.impedance;
            } else {
                prec["impedance"] = nb::none();
            }
            if (port.has_role) {
                prec["role"] = port.role;
            } else {
                prec["role"] = nb::none();
            }
            if (port.has_bus) {
                prec["bus"] = port.bus;
            } else {
                prec["bus"] = nb::none();
            }
            if (port.has_speed_hz) {
                prec["speed_hz"] = port.speed_hz;
            } else {
                prec["speed_hz"] = nb::none();
            }
            if (port.has_level_v) {
                prec["level_v"] = port.level_v;
            } else {
                prec["level_v"] = nb::none();
            }
            if (port.has_expect) {
                prec["expect"] = port.expect;
            } else {
                prec["expect"] = nb::none();
            }
            port_types[port.net.c_str()] = prec;
        }
        rec["port_types"] = port_types;
        nb::dict hints;
        for (const schgen::CircuitHintIr& hint : sheet.hints) {
            hints[hint.net.c_str()] = hint.style;
        }
        rec["hints"] = hints;
        nb::dict loads;
        for (const schgen::CircuitLoadIr& load : sheet.loads) {
            nb::object existing = loads.attr("get")(load.rail.c_str(), nb::none());
            nb::list rows;
            if (!existing.is_none()) {
                rows = nb::cast<nb::list>(existing);
            }
            nb::list row;
            row.append(load.amps);
            row.append(load.note);
            rows.append(row);
            loads[load.rail.c_str()] = rows;
        }
        rec["loads"] = loads;
        nb::dict tp_waivers;
        nb::dict decap_waivers;
        nb::dict pull_waivers;
        nb::dict reset_waivers;
        nb::dict strap_waivers;
        nb::dict ep_waivers;
        nb::dict thermal_waivers;
        nb::dict part_rule_waivers;
        for (const schgen::CircuitWaiverIr& waiver : sheet.waivers) {
            nb::dict* dest = nullptr;
            if (waiver.kind == "tp_waivers") {
                dest = &tp_waivers;
            } else if (waiver.kind == "decap_waivers") {
                dest = &decap_waivers;
            } else if (waiver.kind == "pull_waivers") {
                dest = &pull_waivers;
            } else if (waiver.kind == "reset_waivers") {
                dest = &reset_waivers;
            } else if (waiver.kind == "strap_waivers") {
                dest = &strap_waivers;
            } else if (waiver.kind == "ep_waivers") {
                dest = &ep_waivers;
            } else if (waiver.kind == "thermal_waivers") {
                dest = &thermal_waivers;
            } else if (waiver.kind == "part_rule_waivers") {
                dest = &part_rule_waivers;
            } else {
                throw std::runtime_error("circuit_lookup: unknown waiver kind "
                                         + waiver.kind);
            }
            (*dest)[waiver.key.c_str()] = waiver.reason;
        }
        rec["tp_waivers"] = tp_waivers;
        rec["decap_waivers"] = decap_waivers;
        rec["pull_waivers"] = pull_waivers;
        rec["reset_waivers"] = reset_waivers;
        rec["strap_waivers"] = strap_waivers;
        rec["ep_waivers"] = ep_waivers;
        rec["thermal_waivers"] = thermal_waivers;
        rec["part_rule_waivers"] = part_rule_waivers;
        return rec;
    });
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
    m.def("evict_window",
          [](double ex, double ey, double ew, double eh,
             const std::tuple<double, double, double, double>& e_reach,
             const std::tuple<double, double, double, double>& e_inset,
             const std::vector<std::tuple<double, double, double, double, int>>&
                 e_comps,
             double w, double h,
             const std::tuple<double, double, double, double>& rch,
             const std::tuple<double, double, double, double>& ins,
             const std::vector<std::tuple<double, double, double, double, int>>&
                 cc,
             double clear) {
              return schgen::evict_window(
                  ex, ey, ew, eh, as_halo(e_reach), as_halo(e_inset),
                  as_comps(e_comps), w, h, as_halo(rch), as_halo(ins),
                  as_comps(cc), clear);
          });
    m.def("boxes_separated", &schgen::boxes_separated);
    m.def("halo4",
          [](const std::tuple<double, double, double, double>& reach,
             const std::tuple<double, double, double, double>& inset) {
              const schgen::Halo hit =
                  schgen::halo4(as_halo(reach), as_halo(inset));
              return std::make_tuple(hit.w, hit.e, hit.n, hit.s);
          });
    m.def("occ_pair_active", &schgen::occ_pair_active);
    m.def("spatial_bounds", &schgen::spatial_bounds);
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
    m.def("pairs_entity",
          [](double x, double y, double w, double h, const HaloTup& reach,
             const HaloTup& inset, int mask, const std::vector<CompTup>& comps) {
              auto rows = schgen::pairs_entity(x, y, w, h, as_halo(reach),
                                               as_halo(inset), mask,
                                               as_comps(comps));
              std::vector<EntTup> out;
              out.reserve(rows.size());
              for (const auto& rect : rows) {
                  out.push_back(as_ent(rect));
              }
              return out;
          });
    m.def("pairs_hold_groups",
          [](const std::vector<BlockTup>& interior,
             const std::vector<BlockTup>& edges, const BoxTup& som_occ,
             int som_mask, const std::vector<CompTup>& som_comps,
             double board_w, double board_h, double mh_corner_ko,
             int punch_mask) {
              auto groups = schgen::pairs_hold_groups(
                  as_pairs_blocks(interior), as_pairs_blocks(edges),
                  std::get<0>(som_occ), std::get<1>(som_occ),
                  std::get<2>(som_occ), std::get<3>(som_occ), som_mask,
                  as_comps(som_comps), board_w, board_h, mh_corner_ko,
                  punch_mask);
              std::vector<std::vector<EntTup>> out;
              out.reserve(groups.size());
              for (const auto& group : groups) {
                  std::vector<EntTup> row;
                  row.reserve(group.size());
                  for (const auto& rect : group) {
                      row.push_back(as_ent(rect));
                  }
                  out.push_back(std::move(row));
              }
              return out;
          });
    m.def("pairs_hold_from_layout",
          [](const std::vector<BlockTup>& interior,
             const std::vector<BlockTup>& edges, const BoxTup& som_occ,
             int som_mask, const std::vector<CompTup>& som_comps,
             double board_w, double board_h, double mh_corner_ko,
             int punch_mask, double clear) {
              return schgen::pairs_hold_from_layout(
                  as_pairs_blocks(interior), as_pairs_blocks(edges),
                  std::get<0>(som_occ), std::get<1>(som_occ),
                  std::get<2>(som_occ), std::get<3>(som_occ), som_mask,
                  as_comps(som_comps), board_w, board_h, mh_corner_ko,
                  punch_mask, clear);
          });
    m.def("py_round", &schgen::py_round);
    m.def("fixed_part_grid", &schgen::fixed_part_grid);
    m.def("evict_corridor_grid", &schgen::evict_corridor_grid);
    m.def("som_pose_half_mm", &schgen::som_pose_half_mm);
    m.def("placeholder_zone_half_mm", &schgen::placeholder_zone_half_mm);
    m.def("interior_dims", &schgen::interior_dims);
    m.def("derive_outline_wh", &schgen::derive_outline_wh);
    m.def("legalize_pose_quantum", &schgen::legalize_pose_quantum);
    m.def("quant_credit", &schgen::quant_credit);
    m.def("snap_erosion_bound", &schgen::snap_erosion_bound);
    m.def("snap_erosion_pad", &schgen::snap_erosion_pad);
    m.def("outline_snap_up", &schgen::outline_snap_up);
    m.def("outline_grow", &schgen::outline_grow);
    m.def("fine_shrink", &schgen::fine_shrink);
    m.def("est_via_cost", &schgen::est_via_cost);
    m.def("gsnap", &schgen::gsnap);
    m.def("gfloor", &schgen::gfloor);
    m.def("gceil", &schgen::gceil);
    m.def("pair_axis",
          [](const std::tuple<double, double, double, double>& a,
             const std::tuple<double, double, double, double>& b) {
              auto hit = schgen::pair_axis(as_box(a), as_box(b));
              return std::make_tuple(hit.axis_x ? "x" : "y", hit.a_first);
          });
    m.def("wall_sep_edges",
          [](bool axis_x, const std::vector<std::string>& names,
             const std::vector<double>& sizes, double span, double clear,
             const std::vector<std::tuple<bool, std::string, std::string,
                                          double>>& seps,
             const std::vector<std::tuple<std::string, BoxTup>>& frects) {
              std::vector<schgen::SepSpec> spec;
              spec.reserve(seps.size());
              for (const auto& s : seps) {
                  spec.push_back(schgen::SepSpec{std::get<0>(s), std::get<1>(s),
                                                 std::get<2>(s), std::get<3>(s)});
              }
              std::vector<std::pair<std::string, schgen::Box4>> fr;
              fr.reserve(frects.size());
              for (const auto& r : frects) {
                  fr.emplace_back(std::get<0>(r), as_box(std::get<1>(r)));
              }
              auto rows = schgen::wall_sep_edges(axis_x, names, sizes, span,
                                                 clear, spec, fr);
              std::vector<std::tuple<std::string, std::string, double,
                                     std::string, int, std::string>> out;
              out.reserve(rows.size());
              for (const auto& e : rows) {
                  out.emplace_back(e.src, e.dst, e.cost, e.kind, e.sep_index,
                                   e.wall_name);
              }
              return out;
          });
    m.def("near_max_edges",
          [](const std::string& subject, const std::string& target,
             double bound, const char* axis, const BoxTup& hs,
             const BoxTup& hg, const BoxTup& sr, const BoxTup& gr,
             bool s_movable, bool g_movable,
             const std::optional<std::tuple<double, double>>& pose_s,
             const std::optional<std::tuple<double, double>>& pose_g) {
              if (axis == nullptr || (axis[0] != 'x' && axis[0] != 'y')) {
                  throw std::runtime_error("near_max_edges: axis required");
              }
              std::optional<std::pair<double, double>> ps;
              std::optional<std::pair<double, double>> pg;
              if (pose_s.has_value()) {
                  ps = {std::get<0>(*pose_s), std::get<1>(*pose_s)};
              }
              if (pose_g.has_value()) {
                  pg = {std::get<0>(*pose_g), std::get<1>(*pose_g)};
              }
              auto rows = schgen::near_max_edges(
                  subject, target, bound, axis[0] == 'x', as_box(hs),
                  as_box(hg), as_box(sr), as_box(gr), s_movable, g_movable,
                  ps, pg);
              std::vector<std::tuple<std::string, std::string, double, bool>>
                  out;
              out.reserve(rows.size());
              for (const auto& e : rows) {
                  out.emplace_back(e.src, e.dst, e.cost, e.perp);
              }
              return out;
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
    m.def("flow_budget",
          [](double board_w, double board_h,
             std::optional<std::tuple<double, double, double, double>> som) {
              std::optional<schgen::Box4> core;
              if (som.has_value()) {
                  core = as_box(*som);
              }
              return schgen::flow_budget(board_w, board_h, core);
          });
    m.def("bbox_gap",
          [](const std::tuple<double, double, double, double>& a,
             const std::tuple<double, double, double, double>& b) {
              return schgen::bbox_gap(as_box(a), as_box(b));
          });
    m.def("rect_gap",
          [](const std::tuple<double, double, double, double>& a,
             const std::tuple<double, double, double, double>& b) {
              return schgen::rect_gap(as_box(a), as_box(b));
          });
    m.def("facing_dot",
          [](double zx, double zy, double ox, double oy, double dx,
             double dy) {
              auto hit = schgen::facing_dot(zx, zy, ox, oy, dx, dy);
              return std::make_tuple(hit.first, hit.second);
          });
    m.def("predicted_centroid",
          [](double pose_x, double pose_y, double origin_x, double origin_y,
             const std::vector<std::tuple<std::string, double, double>>& offsets,
             std::optional<std::vector<std::string>> refs)
              -> std::optional<std::tuple<double, double>> {
              const std::vector<std::string>* allow = nullptr;
              if (refs.has_value()) {
                  allow = &(*refs);
              }
              auto hit = schgen::predicted_centroid(pose_x, pose_y, origin_x,
                                                    origin_y, offsets, allow);
              if (!hit) {
                  return std::nullopt;
              }
              return std::make_tuple(hit->first, hit->second);
          });
    m.def("predicted_bbox",
          [](double pose_x, double pose_y, double origin_x, double origin_y,
             const std::vector<std::tuple<std::string, double, double>>& offsets,
             const std::vector<std::tuple<std::string, double, double, double,
                                          double>>& pad_union)
              -> std::optional<std::tuple<double, double, double, double>> {
              auto hit = schgen::predicted_bbox(pose_x, pose_y, origin_x,
                                                origin_y, offsets, pad_union);
              if (!hit) {
                  return std::nullopt;
              }
              return std::make_tuple(hit->x0, hit->y0, hit->x1, hit->y1);
          });
    m.def("channel_demand_mm", &schgen::channel_demand_mm);
    m.def("channel_gap_mm",
          [](bool near_max_adjacent, int cross_airwire_count, double clear,
             int channel_min_nets, double channel_floor_mm,
             double channel_per_net_mm) {
              return schgen::channel_gap_mm(
                  near_max_adjacent, cross_airwire_count, clear,
                  channel_min_nets, channel_floor_mm, channel_per_net_mm);
          });
    m.def("legalize_build_seps",
          [](const std::vector<std::string>& names,
             const std::vector<BoxTup>& seed_rects,
             const std::vector<std::string>& fixed_names,
             const std::vector<BoxTup>& fixed_rects,
             const std::vector<std::tuple<std::string, std::string, int>>&
                 demand_rows,
             const std::vector<std::pair<std::string, std::string>>&
                 near_max_pairs,
             double clear, int channel_min_nets, double channel_floor_mm,
             double channel_per_net_mm) {
              auto seps = schgen::legalize_build_seps(
                  names, as_boxes(seed_rects), fixed_names,
                  as_boxes(fixed_rects), demand_rows, near_max_pairs, clear,
                  channel_min_nets, channel_floor_mm, channel_per_net_mm);
              std::vector<std::tuple<std::string, std::string, std::string,
                                     double, std::string, bool>>
                  out;
              out.reserve(seps.size());
              for (const auto& sep : seps) {
                  out.emplace_back(sep.axis, sep.lo, sep.hi, sep.gap,
                                   sep.basis, sep.flippable);
              }
              return out;
          });
    m.def("evaluate_terms",
          [](double board_w, double board_h,
             const std::optional<BoxTup>& som_core,
             const std::vector<std::pair<std::string, PtTup>>& poses,
             const std::vector<std::tuple<
                 std::string,
                 std::vector<std::tuple<std::string, double, double>>,
                 std::vector<std::tuple<std::string, double, double, double,
                                        double>>>>& metrics,
             const std::vector<std::tuple<std::string, std::string, std::string,
                                          std::optional<double>,
                                          std::vector<std::string>>>& terms,
             const std::vector<std::pair<std::string, double>>& far_guard,
             const std::vector<std::pair<std::string, BoxTup>>& som_j_rects,
             double origin_x, double origin_y) {
              std::optional<schgen::Box4> core;
              if (som_core.has_value()) {
                  core = as_box(*som_core);
              }
              std::vector<std::pair<std::string, std::pair<double, double>>>
                  pose_rows;
              pose_rows.reserve(poses.size());
              for (const auto& p : poses) {
                  pose_rows.emplace_back(
                      p.first,
                      std::make_pair(std::get<0>(p.second),
                                     std::get<1>(p.second)));
              }
              std::vector<schgen::EvalMetric> mets;
              mets.reserve(metrics.size());
              for (const auto& m : metrics) {
                  schgen::EvalMetric row;
                  row.name = std::get<0>(m);
                  row.offsets = std::get<1>(m);
                  row.pad_union = std::get<2>(m);
                  mets.push_back(std::move(row));
              }
              std::vector<schgen::EvalTermIn> tin;
              tin.reserve(terms.size());
              for (const auto& t : terms) {
                  schgen::EvalTermIn row;
                  row.kind = std::get<0>(t);
                  row.subject = std::get<1>(t);
                  row.target = std::get<2>(t);
                  if (std::get<3>(t).has_value()) {
                      row.bound = *std::get<3>(t);
                      row.bound_set = true;
                  }
                  row.out_refs = std::get<4>(t);
                  tin.push_back(std::move(row));
              }
              std::vector<std::pair<std::string, schgen::Box4>> jacks;
              jacks.reserve(som_j_rects.size());
              for (const auto& j : som_j_rects) {
                  jacks.emplace_back(j.first, as_box(j.second));
              }
              auto hits = schgen::evaluate_terms(
                  board_w, board_h, core, pose_rows, mets, tin, far_guard,
                  jacks, origin_x, origin_y);
              std::vector<std::tuple<double, double, double, bool, std::string>>
                  out;
              out.reserve(hits.size());
              for (const auto& h : hits) {
                  out.emplace_back(h.measured, h.bound, h.margin, h.ok,
                                   h.note);
              }
              return out;
          });
    m.def("legalize_descend_passes",
          [](const std::vector<std::string>& names,
             const std::vector<double>& pos_x,
             const std::vector<double>& pos_y,
             const std::vector<double>& seed_x,
             const std::vector<double>& seed_y,
             const std::vector<std::tuple<std::string, std::string, double>>&
                 edges_x,
             const std::vector<std::tuple<std::string, std::string, double>>&
                 edges_y,
             const std::vector<std::pair<std::string, std::string>>& hops,
             const std::vector<std::pair<std::string, PtTup>>& cent_off,
             const std::vector<std::pair<std::string, PtTup>>& fixed_poses,
             double som_mid_x, double som_mid_y, bool has_som, bool seed_only,
             double hop_weight, double seed_weight, int median_passes) {
              std::vector<schgen::NamedEdge> ex;
              std::vector<schgen::NamedEdge> ey;
              ex.reserve(edges_x.size());
              ey.reserve(edges_y.size());
              for (const auto& e : edges_x) {
                  ex.push_back(schgen::NamedEdge{std::get<0>(e), std::get<1>(e),
                                                 std::get<2>(e)});
              }
              for (const auto& e : edges_y) {
                  ey.push_back(schgen::NamedEdge{std::get<0>(e), std::get<1>(e),
                                                 std::get<2>(e)});
              }
              std::vector<std::pair<std::string, std::pair<double, double>>>
                  cents;
              std::vector<std::pair<std::string, std::pair<double, double>>>
                  fixed;
              cents.reserve(cent_off.size());
              fixed.reserve(fixed_poses.size());
              for (const auto& c : cent_off) {
                  cents.emplace_back(
                      c.first, std::make_pair(std::get<0>(c.second),
                                              std::get<1>(c.second)));
              }
              for (const auto& f : fixed_poses) {
                  fixed.emplace_back(
                      f.first, std::make_pair(std::get<0>(f.second),
                                              std::get<1>(f.second)));
              }
              return schgen::legalize_descend_passes(
                  names, pos_x, pos_y, seed_x, seed_y, ex, ey, hops, cents,
                  fixed, som_mid_x, som_mid_y, has_som, seed_only, hop_weight,
                  seed_weight, median_passes);
          });
    m.def("legalize_repair_axis",
          [](bool axis_x, const std::vector<std::string>& names,
             const std::vector<double>& sizes, double span, double clear,
             const std::vector<std::tuple<bool, std::string, std::string,
                                          double, bool>>& seps,
             const std::vector<std::tuple<std::string, BoxTup>>& frects,
             const std::vector<std::tuple<std::string, std::string, double>>&
                 extra,
             int repair_max) {
              std::vector<schgen::RepairSep> spec;
              spec.reserve(seps.size());
              for (const auto& s : seps) {
                  spec.push_back(schgen::RepairSep{
                      std::get<0>(s), std::get<1>(s), std::get<2>(s),
                      std::get<3>(s), std::get<4>(s)});
              }
              std::vector<std::pair<std::string, schgen::Box4>> fr;
              fr.reserve(frects.size());
              for (const auto& r : frects) {
                  fr.emplace_back(std::get<0>(r), as_box(std::get<1>(r)));
              }
              std::vector<schgen::NamedEdge> extra_e;
              extra_e.reserve(extra.size());
              for (const auto& e : extra) {
                  extra_e.push_back(schgen::NamedEdge{
                      std::get<0>(e), std::get<1>(e), std::get<2>(e)});
              }
              auto hit = schgen::legalize_repair_axis(
                  axis_x, names, sizes, span, clear, spec, fr, extra_e,
                  repair_max);
              std::vector<std::tuple<bool, std::string, std::string, double,
                                     bool>>
                  seps_out;
              seps_out.reserve(hit.seps.size());
              for (const auto& s : hit.seps) {
                  seps_out.emplace_back(s.axis_x, s.lo, s.hi, s.gap,
                                        s.flippable);
              }
              return std::make_tuple(hit.ok, hit.pos, seps_out, hit.flips,
                                     hit.fail);
          });
    m.def("rects_overlap_any",
          [](const std::vector<BoxTup>& probes,
             const std::vector<BoxTup>& obstacles, double eps) {
              return schgen::rects_overlap_any(as_boxes(probes),
                                               as_boxes(obstacles), eps);
          });
    m.def("cross_edge_fanout_hold",
          [](const std::vector<std::tuple<
                 double, double, double, double, BoxTup, BoxTup, std::string>>&
                 blocks,
             double clear) {
              std::vector<schgen::EdgeFanoutBlock> rows;
              rows.reserve(blocks.size());
              for (const auto& block : blocks) {
                  const std::string& edge = std::get<6>(block);
                  if (edge.empty()) {
                      throw std::runtime_error(
                          "_geom.cross_edge_fanout_hold: edge required");
                  }
                  rows.push_back(schgen::EdgeFanoutBlock{
                      std::get<0>(block), std::get<1>(block),
                      std::get<2>(block), std::get<3>(block),
                      as_halo(std::get<4>(block)), as_halo(std::get<5>(block)),
                      edge[0]});
              }
              return schgen::cross_edge_fanout_hold(rows, clear);
          });
    m.def("edge_run_margin_ok",
          [](const char* edge, double x, double y, double w, double h,
             double board_w, double board_h, double edge_margin,
             double overflow_tol) {
              if (edge == nullptr || edge[0] == '\0') {
                  throw std::runtime_error(
                      "_geom.edge_run_margin_ok: edge required");
              }
              return schgen::edge_run_margin_ok(
                  edge[0], x, y, w, h, board_w, board_h, edge_margin,
                  overflow_tol);
          });
    m.def("edge_runs_margin_ok",
          [](const std::vector<
                 std::tuple<std::string, double, double, double, double>>&
                 blocks,
             double board_w, double board_h, double edge_margin,
             double overflow_tol) {
              std::vector<std::tuple<char, double, double, double, double>>
                  rows;
              rows.reserve(blocks.size());
              for (const auto& block : blocks) {
                  const std::string& edge = std::get<0>(block);
                  if (edge.empty()) {
                      throw std::runtime_error(
                          "_geom.edge_runs_margin_ok: edge required");
                  }
                  rows.emplace_back(edge[0], std::get<1>(block),
                                    std::get<2>(block), std::get<3>(block),
                                    std::get<4>(block));
              }
              return schgen::edge_runs_margin_ok(
                  rows, board_w, board_h, edge_margin, overflow_tol);
          });
    m.def("pack_interior_order", &schgen::pack_interior_order);
    m.def("pack_conn_weight", &schgen::pack_conn_weight);
    m.def("nets_by_sheet", &schgen::nets_by_sheet);
    m.def("obstacle_bucket", &schgen::obstacle_bucket);
    m.def("obstacle_hole", &schgen::obstacle_hole);
    m.def("net_clearance_rule", &schgen::net_clearance_rule);
    m.def("next_flag_x", &schgen::next_flag_x);
    m.def("flags_row_origin", &schgen::flags_row_origin);
    m.def("conn_signed_ceil", &schgen::conn_signed_ceil);
    m.def("conn_gnd_x", &schgen::conn_gnd_x);
    m.def("farm_wrap_advance",
          [](double col_x, double max_right, bool has_cur, double farm_left,
             double cy, double row_step, double unit) {
              auto hit = schgen::farm_wrap_advance(
                  col_x, max_right, has_cur, farm_left, cy, row_step, unit);
              return std::make_tuple(hit.wrapped, hit.col_x, hit.cy);
          });
    m.def("conn_flag_y", &schgen::conn_flag_y);
    m.def("conn_flag_x0", &schgen::conn_flag_x0);
    m.def("mst_manhattan",
          [](const std::vector<PtTup>& pts) {
              auto edges = schgen::mst_manhattan(as_pts(pts));
              std::vector<std::tuple<int, int>> out;
              out.reserve(edges.size());
              for (const auto& e : edges) {
                  out.emplace_back(e.first, e.second);
              }
              return out;
          });
    m.def("cross_net_cost",
          [](const std::vector<std::tuple<double, double, int, int>>& pts,
             double via_mm, const std::vector<std::uint8_t>& sheet_is_bot) {
              return schgen::cross_net_cost(pts, via_mm, sheet_is_bot);
          });
    m.def("weighted_median",
          [](const std::vector<std::tuple<double, double>>& pulls) {
              std::vector<std::pair<double, double>> rows;
              rows.reserve(pulls.size());
              for (const auto& p : pulls) {
                  rows.emplace_back(std::get<0>(p), std::get<1>(p));
              }
              return schgen::weighted_median(rows);
          });
    m.def("constraint_edges_ok",
          [](const std::vector<int>& src, const std::vector<int>& dst,
             const std::vector<double>& cost, const std::vector<double>& pos) {
              return schgen::constraint_edges_ok(src, dst, cost, pos);
          });
    m.def("constraint_bounds",
          [](int node, const std::vector<int>& src, const std::vector<int>& dst,
             const std::vector<double>& cost, const std::vector<double>& pos) {
              auto hit = schgen::constraint_bounds(node, src, dst, cost, pos);
              return std::make_tuple(hit.first, hit.second);
          });
    m.def("shelf_pack",
          [](const std::vector<std::tuple<std::string, double, double, double,
                                          double, double, bool>>& items,
             double target_w,
             const std::vector<std::tuple<double, double, double, double,
                                          double, bool>>& blockers,
             double zone_pad) {
              std::vector<schgen::ShelfItem> rows;
              rows.reserve(items.size());
              for (const auto& t : items) {
                  rows.push_back(schgen::ShelfItem{
                      std::get<0>(t),
                      schgen::Box4{std::get<1>(t), std::get<2>(t),
                                   std::get<3>(t), std::get<4>(t)},
                      std::get<5>(t), std::get<6>(t)});
              }
              std::vector<schgen::ShelfOcc> occ;
              occ.reserve(blockers.size());
              for (const auto& t : blockers) {
                  occ.push_back(schgen::ShelfOcc{
                      schgen::Box4{std::get<0>(t), std::get<1>(t),
                                   std::get<2>(t), std::get<3>(t)},
                      std::get<4>(t), std::get<5>(t)});
              }
              auto packed = schgen::shelf_pack(rows, target_w, occ, zone_pad);
              return std::make_tuple(packed.placed, packed.packed_w,
                                     packed.packed_h);
          });
    m.def("via_site_blocker",
          [](double vx, double vy,
             const std::tuple<double, double, double, double, double, double,
                              double, double, double, double, double>& spec,
             const std::vector<std::tuple<double, double, double, double,
                                          std::string, double, std::string>>&
                 obstacles,
             const std::vector<PtTup>& chosen)
              -> std::optional<std::tuple<std::string, std::string, std::string,
                                          double, double>> {
              const schgen::ViaSiteSpec site{
                  std::get<0>(spec), std::get<1>(spec), std::get<2>(spec),
                  std::get<3>(spec), std::get<4>(spec), std::get<5>(spec),
                  std::get<6>(spec), std::get<7>(spec), std::get<8>(spec),
                  std::get<9>(spec), std::get<10>(spec)};
              std::vector<schgen::ViaObstacle> obs;
              obs.reserve(obstacles.size());
              for (const auto& t : obstacles) {
                  obs.push_back(schgen::ViaObstacle{
                      std::get<0>(t), std::get<1>(t), std::get<2>(t),
                      std::get<3>(t), std::get<4>(t), std::get<5>(t),
                      std::get<6>(t)});
              }
              auto hit = schgen::via_site_blocker(vx, vy, site, obs,
                                                  as_pts(chosen));
              if (!hit.blocked) {
                  return std::nullopt;
              }
              return std::make_tuple(hit.kind, hit.label, hit.nname, hit.x,
                                     hit.y);
          });
    m.def("fallback_via_sites",
          [](double x0, double y0, double x1, double y1, double via_size,
             double pitch) {
              auto pts = schgen::fallback_via_sites(x0, y0, x1, y1, via_size,
                                                    pitch);
              std::vector<std::tuple<double, double>> out;
              out.reserve(pts.size());
              for (const auto& p : pts) {
                  out.emplace_back(p.first, p.second);
              }
              return out;
          });
    m.def("zone_fanout_reach",
          [](double zw, double zh,
             const std::vector<std::tuple<double, double, double, double, int,
                                          double>>& members,
             int min_subject_pins) {
              auto hit = schgen::zone_fanout_reach(zw, zh, members,
                                                   min_subject_pins);
              return std::make_tuple(
                  std::make_tuple(hit.first.w, hit.first.e, hit.first.n,
                                  hit.first.s),
                  std::make_tuple(hit.second.w, hit.second.e, hit.second.n,
                                  hit.second.s));
          });
    m.def("overlap_area",
          [](const BoxTup& a, const BoxTup& b) {
              return schgen::overlap_area(as_box(a), as_box(b));
          });
    m.def("text_box",
          [](const std::string& txt, double x, double y, double size,
             double margin) {
              auto b = schgen::text_box(txt, x, y, size, margin);
              return std::make_tuple(b.x0, b.y0, b.x1, b.y1);
          });
    m.def("point_box_dist",
          [](double x, double y, const BoxTup& box) {
              return schgen::point_box_dist(x, y, as_box(box));
          });
    m.def("seg_box_dist",
          [](double x1, double y1, double x2, double y2, const BoxTup& box) {
              return schgen::seg_box_dist(x1, y1, x2, y2, as_box(box));
          });
    m.def("band_cover",
          [](const std::vector<std::tuple<double, std::string>>& points,
             double reach) {
              std::vector<std::pair<double, std::string>> pts;
              pts.reserve(points.size());
              for (const auto& t : points) {
                  pts.emplace_back(std::get<0>(t), std::get<1>(t));
              }
              auto bands = schgen::band_cover(pts, reach);
              std::vector<std::vector<std::tuple<double, std::string>>> out;
              out.reserve(bands.size());
              for (const auto& band : bands) {
                  std::vector<std::tuple<double, std::string>> row;
                  row.reserve(band.size());
                  for (const auto& p : band) {
                      row.emplace_back(p.first, p.second);
                  }
                  out.push_back(std::move(row));
              }
              return out;
          });
    m.def("coverage_ok",
          [](double u, double v, const std::vector<PtTup>& members,
             double bound) {
              auto hit = schgen::coverage_ok(u, v, as_pts(members), bound);
              return std::make_tuple(hit.first, hit.second);
          });
    m.def("place_clear_label",
          [](double cx0, double cy0, double cx1, double cy1,
             const std::string& label, double size,
             const schgen::SilkBoxIndex& occupied,
             const schgen::SilkBoxIndex* placed,
             const std::optional<BoxTup>& bounds) {
              std::optional<schgen::Box4> box;
              if (bounds.has_value()) {
                  box = as_box(*bounds);
              }
              auto hit = schgen::place_clear_label(cx0, cy0, cx1, cy1, label,
                                                   size, occupied, placed,
                                                   box);
              return std::make_tuple(hit.x, hit.y, hit.box.x0, hit.box.y0,
                                     hit.box.x1, hit.box.y1, hit.extra);
          },
          nb::arg("cx0"), nb::arg("cy0"), nb::arg("cx1"), nb::arg("cy1"),
          nb::arg("label"), nb::arg("size"), nb::arg("occupied"),
          nb::arg("placed") = nb::none(), nb::arg("bounds") = nb::none());
    m.def("segments_cross", &schgen::segments_cross);
    m.def("visual_hv_cross", &schgen::visual_hv_cross);
    m.def("collinear_overlap", &schgen::collinear_overlap);
    m.def("reorder_cluster_assign",
          [](const std::vector<std::vector<std::vector<BoxTup>>>& segs,
             const std::vector<int>& assign0, int sweeps) {
              std::vector<std::vector<std::vector<schgen::Seg2>>> rows;
              rows.reserve(segs.size());
              for (const auto& member : segs) {
                  std::vector<std::vector<schgen::Seg2>> slots;
                  slots.reserve(member.size());
                  for (const auto& slot : member) {
                      slots.push_back(as_segs(slot));
                  }
                  rows.push_back(std::move(slots));
              }
              auto hit = schgen::reorder_cluster_assign(rows, assign0, sweeps);
              return std::make_tuple(hit.before, hit.best, hit.assign);
          });
    m.def("som_core_rect",
          [](double som_x, double som_y, double som_w, double som_h,
             double origin_x, double origin_y, double clearance) {
              auto b = schgen::som_core_rect(som_x, som_y, som_w, som_h,
                                             origin_x, origin_y, clearance);
              return std::make_tuple(b.x0, b.y0, b.x1, b.y1);
          });
    m.def("rotate_offsets_90", &schgen::rotate_offsets_90);
    m.def("cluster_interchangeable_rows",
          &schgen::cluster_interchangeable_rows);
    m.def("nearest_manhattan",
          [](double px, double py,
             const std::vector<std::pair<double, double>>& pts) {
              return schgen::nearest_manhattan(px, py, pts);
          });
    m.def("overlap_1d", &schgen::overlap_1d);
    m.def("same_edge_gap",
          [](const BoxTup& a, const BoxTup& b, double band_frac)
              -> std::optional<std::pair<std::string, double>> {
              return schgen::same_edge_gap(as_box(a), as_box(b), band_frac);
          });
    m.def("foreign_t_touch",
          [](double ax0, double ay0, double ax1, double ay1, double bx0,
             double by0, double bx1, double by1, bool same_net)
              -> std::optional<std::pair<double, double>> {
              return schgen::foreign_t_touch(ax0, ay0, ax1, ay1, bx0, by0,
                                             bx1, by1, same_net);
          });
    m.def("refdes_hit_court",
          [](double fx, double fy, double ca, double sa, double lx, double ly,
             const std::optional<BoxTup>& court) {
              std::optional<schgen::Box4> box;
              if (court.has_value()) {
                  box = as_box(*court);
              }
              return schgen::refdes_hit_court(fx, fy, ca, sa, lx, ly, box);
          });
    m.def("uv_to_board",
          [](double cx, double cy, double u, double v, double rot) {
              return schgen::uv_to_board(cx, cy, u, v, rot);
          });
    m.def("via_in_escape_region",
          [](double bx, double by,
             const std::tuple<double, double, double, double>& zone,
             double margin) {
              return schgen::via_in_escape_region(bx, by, as_box(zone), margin);
          });
    m.def("coexistence_box_hit",
          [](double inst_x, double inst_y, double rot,
             const std::tuple<double, double, double, double>& box,
             double region_u, double region_v) {
              return schgen::coexistence_box_hit(inst_x, inst_y, rot,
                                                 as_box(box), region_u,
                                                 region_v);
          });
    m.def("legalize_som_rect",
          [](double som_x, double som_y, double som_w, double som_h,
             double pad) {
              auto b = schgen::legalize_som_rect(som_x, som_y, som_w, som_h,
                                                 pad);
              return std::make_tuple(b.x0, b.y0, b.x1, b.y1);
          });
    m.def("legalize_mh_corners",
          [](double board_w, double board_h, double mh_ko) {
              std::vector<std::tuple<double, double, double, double>> out;
              for (const auto& b : schgen::legalize_mh_corners(
                       board_w, board_h, mh_ko)) {
                  out.emplace_back(b.x0, b.y0, b.x1, b.y1);
              }
              return out;
          });
    m.def("som_jack_rects", &schgen::som_jack_rects);
    m.def("grow_rect",
          [](const BoxTup& box, double margin) {
              auto b = schgen::grow_rect(as_box(box), margin);
              return std::make_tuple(b.x0, b.y0, b.x1, b.y1);
          });
    m.def("offset_rect",
          [](const BoxTup& box, double dx, double dy) {
              auto b = schgen::offset_rect(as_box(box), dx, dy);
              return std::make_tuple(b.x0, b.y0, b.x1, b.y1);
          });
    m.def("rect_covers",
          [](const BoxTup& outer, const BoxTup& inner) {
              return schgen::rect_covers(as_box(outer), as_box(inner));
          });
    m.def("rects_intersect_open",
          [](const BoxTup& a, const BoxTup& b) {
              return schgen::rects_intersect_open(as_box(a), as_box(b));
          });
    m.def("point_in_rect",
          [](double x, double y, const BoxTup& box) {
              return schgen::point_in_rect(x, y, as_box(box));
          });
    m.def("rect_center",
          [](const BoxTup& box) {
              return schgen::rect_center(as_box(box));
          });
    m.def("coexistence_region", &schgen::coexistence_region);
    m.def("construct_reach", &schgen::construct_reach);
    m.def("obstacle_scan_region",
          [](const std::vector<double>& us, double margin) {
              auto b = schgen::obstacle_scan_region(us, margin);
              return std::make_tuple(b.x0, b.y0, b.x1, b.y1);
          });
    m.def("escape_lane_extents", &schgen::escape_lane_extents);
    m.def("aabb_from_corners",
          [](double x0, double y0, double x1, double y1, int digits) {
              auto b = schgen::aabb_from_corners(x0, y0, x1, y1, digits);
              return std::make_tuple(b.x0, b.y0, b.x1, b.y1);
          });
    m.def("min_hypot_to_points",
          [](double u, double v,
             const std::vector<std::pair<double, double>>& pts) {
              return schgen::min_hypot_to_points(u, v, pts);
          });
    m.def("within_reach", &schgen::within_reach);
    m.def("count_within_reach", &schgen::count_within_reach);
    m.def("page_mid_local",
          [](const BoxTup& page, double origin_x, double origin_y) {
              return schgen::page_mid_local(as_box(page), origin_x, origin_y);
          });
    m.def("pair_convergence", &schgen::pair_convergence);
    m.def("signed_mag", &schgen::signed_mag);
    m.def("pad_row_sign", &schgen::pad_row_sign);
    m.def("interior_tier", &schgen::interior_tier);
    m.def("bus_lane_adjacent", &schgen::bus_lane_adjacent);
    m.def("padded_xywh", &schgen::padded_xywh);
    m.def("box_to_xywh",
          [](const BoxTup& box) {
              return schgen::box_to_xywh(as_box(box));
          });
    m.def("rect_corners_ccw",
          [](const BoxTup& box) {
              return schgen::rect_corners_ccw(as_box(box));
          });
    m.def("board_to_uv",
          [](double cx, double cy, double bx, double by, double rot) {
              return schgen::board_to_uv(cx, cy, bx, by, rot);
          });
    m.def("corridor_local_from_uv",
          [](const std::vector<std::pair<double, double>>& pads,
             double r_construct, double v_margin) {
              auto b = schgen::corridor_local_from_uv(pads, r_construct,
                                                      v_margin);
              return std::make_tuple(b.x0, b.y0, b.x1, b.y1);
          });
    m.def("corridor_board_rect",
          [](const BoxTup& local, double cx, double cy, double rot) {
              auto b = schgen::corridor_board_rect(as_box(local), cx, cy, rot);
              return std::make_tuple(b.x0, b.y0, b.x1, b.y1);
          });
    m.def("mirror_offset_x",
          [](double ox, double oy, const BoxTup& cb, double zone_w) {
              return schgen::mirror_offset_x(ox, oy, as_box(cb), zone_w);
          });
    m.def("offset_turned_box",
          [](const BoxTup& bbox, double rot, double ox, double oy) {
              auto b = schgen::offset_turned_box(as_box(bbox), rot, ox, oy);
              return std::make_tuple(b.x0, b.y0, b.x1, b.y1);
          });
    m.def("offset_boxes",
          [](const std::vector<BoxTup>& boxes, double ox, double oy) {
              auto rows = schgen::offset_boxes(as_boxes(boxes), ox, oy);
              std::vector<BoxTup> out;
              out.reserve(rows.size());
              for (const auto& box : rows) {
                  out.emplace_back(box.x0, box.y0, box.x1, box.y1);
              }
              return out;
          });
    m.def("grid_controls",
          [](const std::vector<std::tuple<std::string, double, double, double,
                                          double>>& items,
             double target_w, double button_gap, double zone_pad,
             double place_clear) {
              auto hit = schgen::grid_controls(items, target_w, button_gap,
                                               zone_pad, place_clear);
              std::vector<std::tuple<double, double, double, double>> occ;
              occ.reserve(hit.occ.size());
              for (const auto& b : hit.occ) {
                  occ.emplace_back(b.x0, b.y0, b.x1, b.y1);
              }
              return std::make_tuple(hit.offs, occ, hit.packed_w, hit.packed_h);
          });
    m.def("contact_geometry",
          [](const std::vector<std::tuple<double, double, double, double>>&
                 pads) {
              auto hit = schgen::contact_geometry(pads);
              return std::make_tuple(hit.row_v, hit.half_w, hit.half_h,
                                     hit.span_u, hit.pitch);
          });
    m.def("via_feasible",
          [](double u, double v, double dia, double drill,
             const std::vector<std::tuple<double, double, double, double,
                                          double, std::string>>& front_cu,
             const std::vector<std::tuple<double, double, double, double,
                                          double, std::string>>& back_cu,
             const std::vector<std::tuple<double, double, double, double,
                                          double, std::string>>& samenet,
             const std::vector<std::tuple<double, double, double, std::string>>&
                 holes,
             const std::tuple<double, double, double, double>& clear,
             bool want_audit) {
              schgen::ViaClear vc;
              vc.margin = std::get<0>(clear);
              vc.hole_foreign = std::get<1>(clear);
              vc.hole_samenet = std::get<2>(clear);
              vc.hole_hole = std::get<3>(clear);
              return schgen::via_feasible(u, v, dia, drill, front_cu, back_cu,
                                          samenet, holes, vc, want_audit);
          });
    m.def("seat_band",
          [](const std::vector<std::tuple<std::string, double, double>>&
                 members,
             const std::vector<std::tuple<double, double, double, double,
                                          double, std::string>>& front_cu,
             const std::vector<std::tuple<double, double, double, double,
                                          double, std::string>>& back_cu,
             const std::vector<std::tuple<double, double, double, double,
                                          double, std::string>>& samenet,
             const std::vector<std::tuple<double, double, double, std::string>>&
                 holes,
             double row_v, double half_h,
             const std::vector<std::pair<double, double>>& ladder,
             const std::tuple<double, double, double, double>& clear,
             double via_row, double r_construct, double lattice,
             const char* conn, int depth) {
              schgen::ViaClear vc;
              vc.margin = std::get<0>(clear);
              vc.hole_foreign = std::get<1>(clear);
              vc.hole_samenet = std::get<2>(clear);
              vc.hole_hole = std::get<3>(clear);
              auto hit = schgen::seat_band(
                  members, front_cu, back_cu, samenet, holes, row_v, half_h,
                  ladder, vc, via_row, r_construct, lattice,
                  conn == nullptr ? "" : conn, depth);
              std::vector<std::tuple<double, double, double, double, double,
                                     std::vector<std::string>>>
                  vias;
              vias.reserve(hit.vias.size());
              for (const auto& v : hit.vias) {
                  vias.emplace_back(v.u, v.v, v.dia, v.drill, v.worst,
                                    v.members);
              }
              std::vector<std::tuple<std::string, std::string, double, double,
                                     double, double, double, double, int,
                                     std::vector<std::string>>>
                  ledger;
              ledger.reserve(hit.ledger.size());
              for (const auto& e : hit.ledger) {
                  ledger.emplace_back(e.kind, e.conn, e.u, e.v, e.dia, e.drill,
                                      e.worst, e.at, e.depth, e.members);
              }
              return std::make_tuple(vias, ledger, hit.audit);
          });
    m.def("escape_ladder_plan",
          [](const std::vector<std::tuple<double, double, std::string>>&
                 gnd_pads,
             const std::vector<std::pair<double, double>>& vias, double pitch,
             double pitch_tol, double row_v, double stub_w_pair,
             double stub_w_single, double spine_w) {
              auto rows = schgen::escape_ladder_plan(
                  gnd_pads, vias, pitch, pitch_tol, row_v, stub_w_pair,
                  stub_w_single, spine_w);
              std::vector<std::tuple<double, double, double, double, double,
                                     std::string>>
                  out;
              out.reserve(rows.size());
              for (const auto& seg : rows) {
                  out.emplace_back(seg.ax, seg.ay, seg.bx, seg.by, seg.w,
                                   seg.role);
              }
              return out;
          });
    m.def("escape_ladder_connected",
          [](const std::vector<std::tuple<double, double, double>>& vias,
             const std::vector<std::tuple<double, double, double, double,
                                          double, std::string>>& segs,
             const std::vector<std::pair<double, double>>& pads, double half_w,
             double half_h) {
              auto hit = schgen::escape_ladder_connected(vias, segs, pads,
                                                         half_w, half_h);
              return std::make_tuple(hit.via_seg_components, hit.pad_stubs);
          });
    m.def("escape_redundancy_u",
          [](double base_u, double base_v, double dia, double drill,
             const std::vector<std::tuple<double, double, double, double,
                                          double, std::string>>& front_cu,
             const std::vector<std::tuple<double, double, double, double,
                                          double, std::string>>& back_cu,
             const std::vector<std::tuple<double, double, double, double,
                                          double, std::string>>& samenet,
             const std::vector<std::tuple<double, double, double, std::string>>&
                 holes,
             const std::tuple<double, double, double, double>& clear,
             double redundancy_offset, double lattice, int max_steps)
              -> std::optional<double> {
              schgen::ViaClear via_clear;
              via_clear.margin = std::get<0>(clear);
              via_clear.hole_foreign = std::get<1>(clear);
              via_clear.hole_samenet = std::get<2>(clear);
              via_clear.hole_hole = std::get<3>(clear);
              return schgen::escape_redundancy_u(
                  base_u, base_v, dia, drill, front_cu, back_cu, samenet,
                  holes, via_clear, redundancy_offset, lattice, max_steps);
          });
    m.def("is_passive_ref", &schgen::is_passive_ref);
    m.def("classify_side",
          [](const char* ref, const char* lib,
             const std::tuple<double, double, double, double>& bbox,
             bool in_decoupling, bool two_side, double top_area,
             const std::vector<std::string>& top_always) {
              return schgen::classify_side(
                  ref == nullptr ? "" : ref, lib == nullptr ? "" : lib,
                  as_box(bbox), in_decoupling, two_side, top_area, top_always);
          });
    m.def("decoupling_caps", &schgen::decoupling_caps);
    m.def("zone_target_w", &schgen::zone_target_w);
    m.def("connector_target_w", &schgen::connector_target_w);
    m.def("canonical_plane_rect",
          [](double origin_x, double origin_y, double board_w, double board_h,
             double edge_back) {
              auto b = schgen::canonical_plane_rect(origin_x, origin_y, board_w,
                                                    board_h, edge_back);
              return std::make_tuple(b.x0, b.y0, b.x1, b.y1);
          });
    m.def("isolation_void_rect",
          [](const std::tuple<double, double, double, double>& court,
             double margin) {
              auto b = schgen::isolation_void_rect(as_box(court), margin);
              return std::make_tuple(b.x0, b.y0, b.x1, b.y1);
          });
    m.def("board_box_to_uv",
          [](double cx, double cy, double rot,
             const std::tuple<double, double, double, double>& box) {
              auto b = schgen::board_box_to_uv(cx, cy, rot, as_box(box));
              return std::make_tuple(b.x0, b.y0, b.x1, b.y1);
          });
    m.def("cluster_slot_segs",
          [](const std::vector<std::tuple<std::string, double, double>>&
                 pad_offs,
             const std::vector<std::string>& pad_nets,
             const std::vector<std::pair<double, double>>& slots,
             const std::vector<std::tuple<
                 std::string, std::vector<std::pair<double, double>>>>&
                 static_pts) {
              auto hit = schgen::cluster_slot_segs(pad_offs, pad_nets, slots,
                                                   static_pts);
              std::vector<std::vector<
                  std::tuple<double, double, double, double>>>
                  out;
              out.reserve(hit.size());
              for (const auto& segs : hit) {
                  std::vector<std::tuple<double, double, double, double>> row;
                  row.reserve(segs.size());
                  for (const auto& s : segs) {
                      row.emplace_back(s.x0, s.y0, s.x1, s.y1);
                  }
                  out.push_back(std::move(row));
              }
              return out;
          });
    m.def("group_interchangeable", &schgen::group_interchangeable);
    m.def("reorder_interchangeable", &schgen::reorder_interchangeable);
    m.def("scan_floats", &schgen::scan_floats);
    m.def("font_size",
          [](nb::handle node, double default_size) {
              return schgen::font_size(sexpr_from_py(node), default_size);
          });
    m.def("inst_pad_xy", &schgen::inst_pad_xy);
    m.def("collect_emitted_text_boxes",
          [](nb::handle doc, bool include_silk_gfx, double default_size) {
              auto boxes = schgen::collect_emitted_text_boxes(
                  sexpr_from_py(doc), include_silk_gfx, default_size);
              std::vector<std::tuple<double, double, double, double>> out;
              out.reserve(boxes.size());
              for (const auto& b : boxes) {
                  out.emplace_back(b.x0, b.y0, b.x1, b.y1);
              }
              return out;
          });
    m.def("boxes_union",
          [](const std::vector<BoxTup>& boxes) -> std::optional<BoxTup> {
              auto hit = schgen::boxes_union(as_boxes(boxes));
              if (!hit) {
                  return std::nullopt;
              }
              return std::make_tuple(hit->x0, hit->y0, hit->x1, hit->y1);
          });
    m.def("text_wh",
          [](const std::string& text, double size, double char_w,
             double line_h) {
              auto wh = schgen::text_wh(text, size, char_w, line_h);
              return std::make_tuple(wh.first, wh.second);
          });
    m.def("centered_box",
          [](const std::string& text, double cx, double cy, double size,
             double char_w, double line_h, bool vertical) {
              auto b = schgen::centered_box(text, cx, cy, size, char_w, line_h,
                                            vertical);
              return std::make_tuple(b.x0, b.y0, b.x1, b.y1);
          });
    m.def("llabel_box",
          [](const std::string& text, double x, double y, int rotation,
             double size, double char_w, double line_h, double width_pad,
             double gap) {
              auto b = schgen::llabel_box(text, x, y, rotation, size, char_w,
                                          line_h, width_pad, gap);
              return std::make_tuple(b.x0, b.y0, b.x1, b.y1);
          });
    m.def("silk_gfx_extent",
          [](const std::vector<PtTup>& pts, double fx, double fy, double ca,
             double sa, double hw) -> std::optional<BoxTup> {
              auto hit = schgen::silk_gfx_extent(as_pts(pts), fx, fy, ca, sa,
                                                 hw);
              if (!hit) {
                  return std::nullopt;
              }
              return std::make_tuple(hit->x0, hit->y0, hit->x1, hit->y1);
          });
    m.def("pair_gap",
          [](const std::tuple<double, double, double, double>& ar,
             const std::tuple<double, double, double, double>& ai,
             const std::tuple<double, double, double, double>& br,
             const std::tuple<double, double, double, double>& bi,
             const char* axis, double floor) {
              if (axis == nullptr || axis[0] == '\0') {
                  throw std::runtime_error("pair_gap: axis required");
              }
              return schgen::pair_gap(as_halo(ar), as_halo(ai), as_halo(br),
                                      as_halo(bi), axis[0], floor);
          });
    m.def("glabel_box",
          [](const std::string& text, double x, double y, int rotation,
             double size, double char_w, double line_h, double pad_len,
             double glabel_h, double inset) {
              auto b = schgen::glabel_box(text, x, y, rotation, size, char_w,
                                          line_h, pad_len, glabel_h, inset);
              return std::make_tuple(b.x0, b.y0, b.x1, b.y1);
          });
    m.def("point_on_seg", &schgen::point_on_seg);
    m.def("min_box_gap",
          [](const std::vector<std::tuple<double, double, double, double>>& a,
             const std::vector<std::tuple<double, double, double, double>>& b)
              -> std::optional<double> {
              return schgen::min_box_gap(as_boxes(a), as_boxes(b));
          });
    m.def("flip_to_bottom",
          [](nb::handle node) {
              auto tree = sexpr_from_py(node);
              schgen::flip_to_bottom(tree);
              return sexpr_to_tagged(tree);
          });
    m.def("restamp_uuid",
          [](nb::handle node, const std::string& uuid) {
              auto tree = sexpr_from_py(node);
              schgen::restamp_uuid(tree, uuid);
              return sexpr_to_tagged(tree);
          });
    m.def("set_or_add",
          [](nb::handle node, nb::handle kv) {
              auto tree = sexpr_from_py(node);
              auto child = sexpr_from_py(kv);
              schgen::set_or_add(tree, child);
              return sexpr_to_tagged(tree);
          });
    m.def("set_pad_net",
          [](nb::handle pad, int num, const std::string& name) {
              auto tree = sexpr_from_py(pad);
              schgen::set_pad_net(tree, num, name);
              return sexpr_to_tagged(tree);
          });
    m.def("thermal_via_inherit",
          [](double cx, double cy,
             const std::vector<std::tuple<double, double, double, double, int,
                                          std::string>>& netted)
              -> std::optional<std::tuple<int, std::string>> {
              auto hit = schgen::thermal_via_inherit(cx, cy, netted);
              if (!hit) {
                  return std::nullopt;
              }
              return std::make_tuple(hit->first, hit->second);
          });
    m.def("zone_anchor",
          [](const char* zone, double som_x, double som_y, double som_w,
             double som_h, double board_w, double board_h) {
              if (zone == nullptr || zone[0] == '\0') {
                  throw std::runtime_error("zone_anchor: zone required");
              }
              auto p = schgen::zone_anchor(zone[0], som_x, som_y, som_w,
                                           som_h, board_w, board_h);
              return std::make_tuple(p.first, p.second);
          });
    m.def("j_edge_of", &schgen::j_edge_of);
    m.def("j_edge_map", &schgen::j_edge_map);
    m.def("dominant_j",
          [](const std::vector<std::pair<std::string, int>>& affinity)
              -> std::optional<std::string> {
              return schgen::dominant_j(affinity);
          });
    m.def("affinity_j_from_expect", &schgen::affinity_j_from_expect);
    m.def("affinity_j_from_target",
          [](const std::string& target) -> std::optional<std::string> {
              return schgen::affinity_j_from_target(target);
          });
    m.def("j_affinity", &schgen::j_affinity);
    m.def("pack_anchor",
          [](bool face_override, const char* face, double som_x, double som_y,
             double som_w, double som_h, double som_halo, double block_w,
             double block_h, double zone_ax, double zone_ay, bool exclusive,
             bool inboard, bool zone_is_at_edge, const char* edge, double eb_x,
             double eb_y, double eb_w, double eb_h, double eb_cx, double eb_cy,
             double pull_weight, bool has_soft_pull, double pull_x,
             double pull_y, double zone_w, double som_w_scale, double som_pull,
             double aff_pow, double som_cx, double som_cy,
             const std::vector<std::tuple<double, double, double>>& affinity) {
              schgen::PackAnchorIn in;
              in.face_override = face_override;
              in.face = (face != nullptr && face[0] != '\0') ? face[0] : '\0';
              in.som_x = som_x;
              in.som_y = som_y;
              in.som_w = som_w;
              in.som_h = som_h;
              in.som_halo = som_halo;
              in.block_w = block_w;
              in.block_h = block_h;
              in.zone_ax = zone_ax;
              in.zone_ay = zone_ay;
              in.exclusive = exclusive;
              in.inboard = inboard;
              in.zone_is_at_edge = zone_is_at_edge;
              in.edge = (edge != nullptr && edge[0] != '\0') ? edge[0] : '\0';
              in.eb_x = eb_x;
              in.eb_y = eb_y;
              in.eb_w = eb_w;
              in.eb_h = eb_h;
              in.eb_cx = eb_cx;
              in.eb_cy = eb_cy;
              in.pull_weight = pull_weight;
              in.has_soft_pull = has_soft_pull;
              in.pull_x = pull_x;
              in.pull_y = pull_y;
              in.zone_w = zone_w;
              in.som_w_scale = som_w_scale;
              in.som_pull = som_pull;
              in.aff_pow = aff_pow;
              in.som_cx = som_cx;
              in.som_cy = som_cy;
              in.affinity = affinity;
              auto p = schgen::pack_anchor(in);
              return std::make_tuple(p.first, p.second);
          });
    m.def("dodge_value_off_nc",
          [](const std::string& text, double vp_x, double vp_y, double ax,
             double ay, double unit, double char_w, double line_h, double size,
             const std::vector<BoxTup>& ncs, double nc_pad) {
              auto hit = schgen::dodge_value_off_nc(
                  text, vp_x, vp_y, ax, ay, unit, char_w, line_h, size,
                  as_boxes(ncs), nc_pad);
              return std::make_tuple(hit.first, hit.second);
          });
    m.def("vband_stem_free",
          [](double x, double y0, double y1, const std::vector<BoxTup>& segs,
             double pad) {
              return schgen::vband_stem_free(x, y0, y1, as_boxes(segs), pad);
          });
    m.def("lane_x",
          [](int sgn, double y0, double y1, double start, double unit,
             double half_w, double y_pad, double spot_pad,
             const std::vector<BoxTup>& parts,
             const std::vector<BoxTup>& segs,
             const std::vector<BoxTup>& ncs) -> std::optional<double> {
              return schgen::lane_x(sgn, y0, y1, start, unit, half_w, y_pad,
                                    spot_pad, as_boxes(parts), as_boxes(segs),
                                    as_boxes(ncs));
          });
    m.def("foreign_rows_clear",
          [](const BoxTup& box, const std::vector<double>& foreign_ys,
             double eps) {
              return schgen::foreign_rows_clear(as_box(box), foreign_ys, eps);
          });
    m.def("cell_floor",
          [](double x0, double x1, const std::vector<BoxTup>& boxes,
             const std::vector<BoxTup>& segs) {
              return schgen::cell_floor(x0, x1, as_boxes(boxes),
                                        as_boxes(segs));
          });
    m.def("nearest_rect_gap",
          [](const BoxTup& subject, const std::vector<BoxTup>& others,
             double touch_eps) {
              auto hit = schgen::nearest_rect_gap(as_box(subject),
                                                  as_boxes(others),
                                                  touch_eps);
              return std::make_tuple(hit.gap, hit.index);
          });
    m.def("body_box",
          [](double x0, double y0, double x1, double y1, double ax, double ay,
             int rot) {
              auto b = schgen::body_box(x0, y0, x1, y1, ax, ay, rot);
              return std::make_tuple(b.x0, b.y0, b.x1, b.y1);
          });
    m.def("boxes_paths_extent",
          [](const std::vector<BoxTup>& boxes,
             const std::vector<PtTup>& pts) {
              auto b = schgen::boxes_paths_extent(as_boxes(boxes), as_pts(pts));
              return std::make_tuple(b.x0, b.y0, b.x1, b.y1);
          });
    m.def("band_edge",
          [](double y0, double y1, int side, double default_edge,
             const std::vector<BoxTup>& boxes,
             const std::vector<BoxTup>& segs) {
              return schgen::band_edge(y0, y1, side, default_edge,
                                       as_boxes(boxes), as_boxes(segs));
          });
    m.def("edge_components",
          [](const char* edge, double block_x, double block_y, double board_w,
             double board_h, int punch_mask,
             const std::vector<std::tuple<double, double, double, double, int>>&
                 comps) {
              if (edge == nullptr || edge[0] == '\0') {
                  throw std::runtime_error("edge_components: edge required");
              }
              auto rows = schgen::edge_components(
                  edge[0], block_x, block_y, board_w, board_h, punch_mask,
                  as_comps(comps));
              std::vector<std::tuple<double, double, double, double, int>> out;
              out.reserve(rows.size());
              for (const auto& c : rows) {
                  out.emplace_back(c.dx, c.dy, c.w, c.h, c.mask);
              }
              return out;
          });
    m.def("som_decoupling_grid",
          [](double som_w, double som_h, int n, double inset) {
              return schgen::som_decoupling_grid(som_w, som_h, n, inset);
          });
    m.def("som_decoupling_cells",
          [](double som_x, double som_y, double som_w, double som_h, int n,
             double inset) {
              auto pts = schgen::som_decoupling_cells(som_x, som_y, som_w,
                                                      som_h, n, inset);
              std::vector<std::tuple<double, double>> out;
              out.reserve(pts.size());
              for (const auto& p : pts) {
                  out.emplace_back(p.first, p.second);
              }
              return out;
          });
    m.def("geom_key",
          [](double x, double y) {
              auto k = schgen::geom_key(x, y);
              return std::make_tuple(k.first, k.second);
          });
    m.def("seed_geometry_unions",
          [](const std::vector<std::tuple<int, int, double, double>>& raw_nodes,
             const std::vector<BoxTup>& raw_segs,
             const std::vector<std::tuple<PtTup, PtTup>>& raw_bonds) {
              std::vector<schgen::GeomNode> nodes;
              nodes.reserve(raw_nodes.size());
              for (const auto& t : raw_nodes) {
                  schgen::GeomNode n;
                  n.kx = std::get<0>(t);
                  n.ky = std::get<1>(t);
                  n.x = std::get<2>(t);
                  n.y = std::get<3>(t);
                  nodes.push_back(n);
              }
              std::vector<schgen::GeomSeg> segs;
              segs.reserve(raw_segs.size());
              for (const auto& t : raw_segs) {
                  segs.push_back(schgen::GeomSeg{
                      std::get<0>(t), std::get<1>(t), std::get<2>(t),
                      std::get<3>(t)});
              }
              std::vector<schgen::GeomBond> bonds;
              bonds.reserve(raw_bonds.size());
              for (const auto& t : raw_bonds) {
                  const auto& a = std::get<0>(t);
                  const auto& b = std::get<1>(t);
                  bonds.push_back(schgen::GeomBond{
                      std::get<0>(a), std::get<1>(a), std::get<0>(b),
                      std::get<1>(b)});
              }
              auto roots = schgen::seed_geometry_unions(nodes, segs, bonds);
              std::vector<std::tuple<int, int>> out;
              out.reserve(roots.size());
              for (const auto& r : roots) {
                  out.emplace_back(r.first, r.second);
              }
              return out;
          });
    m.def("embed_footprint_body",
          [](nb::handle node, double x, double y, double rotation,
             const std::string& side, const std::string& uuid) {
              auto tree = sexpr_from_py(node);
              return sexpr_to_tagged(schgen::embed_footprint_body(
                  std::move(tree), x, y, rotation, side, uuid));
          });
    m.def("embed_footprint_decorate",
          [](nb::handle node, const std::string& ref, const std::string& value,
             double rotation, bool hide_reference,
             const std::vector<std::tuple<std::string, int, std::string>>&
                 pad_nets,
             const std::vector<std::tuple<int, int, std::string>>& inherit,
             nb::callable uid) {
              std::unordered_map<std::string, std::pair<int, std::string>>
                  nets;
              for (const auto& row : pad_nets) {
                  nets[std::get<0>(row)] = {std::get<1>(row),
                                            std::get<2>(row)};
              }
              std::unordered_map<int, std::pair<int, std::string>> inherited;
              for (const auto& row : inherit) {
                  inherited[std::get<0>(row)] = {std::get<1>(row),
                                                 std::get<2>(row)};
              }
              auto tree = sexpr_from_py(node);
              auto uid_fn = [&](const std::string& kind) {
                  return nb::cast<std::string>(uid(kind));
              };
              return sexpr_to_tagged(schgen::embed_footprint_decorate(
                  std::move(tree), ref, value, rotation, hide_reference, nets,
                  inherited, uid_fn));
          });
    m.def("pad_geom",
          [](nb::handle node)
              -> std::optional<std::tuple<double, double, double, double>> {
              auto g = schgen::pad_geom(sexpr_from_py(node));
              if (!g) {
                  return std::nullopt;
              }
              return std::make_tuple(g->at_x, g->at_y, g->half_w, g->half_h);
          });
    m.def("beside_offset",
          [](double hx, double hy, const BoxTup& target,
             const std::string& direction, double gap,
             std::optional<double> along) {
              auto p = schgen::beside_offset(hx, hy, as_box(target), direction,
                                             gap, along);
              return std::make_tuple(p.first, p.second);
          });
    m.def("som_components",
          [](double origin_x, double origin_y, double radius,
             const std::vector<PtTup>& cells, const std::vector<BoxTup>& bands,
             int bottom_mask, int punch_mask) {
              auto rows = schgen::som_components(
                  origin_x, origin_y, radius, as_pts(cells), as_boxes(bands),
                  bottom_mask, punch_mask);
              std::vector<std::tuple<double, double, double, double, int>> out;
              out.reserve(rows.size());
              for (const auto& c : rows) {
                  out.emplace_back(c.dx, c.dy, c.w, c.h, c.mask);
              }
              return out;
          });
    m.def("any_boxes_overlap",
          [](const std::vector<BoxTup>& boxes, double halo) {
              return schgen::any_boxes_overlap(as_boxes(boxes), halo);
          });
    m.def("lane_in_dir",
          [](int sgn, double pt_x, double pt_y, double ty, double unit,
             double half_w, double y_pad, double spot_pad,
             double corridor_pad, double x_nudge,
             const std::vector<BoxTup>& parts,
             const std::vector<BoxTup>& spot_segs,
             const std::vector<BoxTup>& ncs,
             const std::vector<BoxTup>& corridor_boxes,
             const std::vector<BoxTup>& corridor_segs)
              -> std::optional<double> {
              return schgen::lane_in_dir(
                  sgn, pt_x, pt_y, ty, unit, half_w, y_pad, spot_pad,
                  corridor_pad, x_nudge, as_boxes(parts), as_boxes(spot_segs),
                  as_boxes(ncs), as_boxes(corridor_boxes),
                  as_segs(corridor_segs));
          });
    m.def("pin_page_position",
          [](double pin_x, double pin_y, double anchor_x, double anchor_y,
             int rotation) {
              auto p = schgen::pin_page_position(pin_x, pin_y, anchor_x,
                                                 anchor_y, rotation);
              return std::make_tuple(p.first, p.second);
          });
    m.def("stem_dir",
          [](int pin_rot, int part_rot) {
              auto p = schgen::stem_dir(pin_rot, part_rot);
              return std::make_tuple(p.first, p.second);
          });
    m.def("pin_text_boxes",
          [](const std::vector<std::tuple<double, double, int, double, bool,
                                          std::string, std::string>>& pins,
             double part_x, double part_y, int part_rot,
             bool pin_numbers_hidden, bool pin_names_hidden, double char_w,
             double line_h, double size) {
              std::vector<schgen::PinTextIn> rows;
              rows.reserve(pins.size());
              for (const auto& p : pins) {
                  rows.push_back(schgen::PinTextIn{
                      std::get<0>(p), std::get<1>(p), std::get<2>(p),
                      std::get<3>(p), std::get<4>(p), std::get<5>(p),
                      std::get<6>(p)});
              }
              auto boxes = schgen::pin_text_boxes(
                  rows, part_x, part_y, part_rot, pin_numbers_hidden,
                  pin_names_hidden, char_w, line_h, size);
              std::vector<std::tuple<double, double, double, double,
                                     std::string>> out;
              out.reserve(boxes.size());
              for (const auto& b : boxes) {
                  out.emplace_back(b.box.x0, b.box.y0, b.box.x1, b.box.y1,
                                   b.kind);
              }
              return out;
          });
    m.def("escape_run_legs",
          [](double px, double py, double tx, double unit, double edge_clear,
             const std::vector<std::tuple<double, double, double, double,
                                          std::string, std::string>>& boxes,
             const std::vector<BoxTup>& parts,
             const std::vector<BoxTup>& spot_segs,
             const std::vector<BoxTup>& ncs,
             const std::vector<BoxTup>& corridor_boxes,
             const std::vector<BoxTup>& corridor_segs,
             const std::vector<BoxTup>& stem_segs, double spot_pad,
             double corridor_pad, double stem_pad) {
              std::vector<schgen::OwnedBox> owned;
              owned.reserve(boxes.size());
              for (const auto& b : boxes) {
                  owned.push_back(schgen::OwnedBox{
                      schgen::Box4{std::get<0>(b), std::get<1>(b),
                                   std::get<2>(b), std::get<3>(b)},
                      std::get<4>(b), std::get<5>(b)});
              }
              auto legs = schgen::escape_run_legs(
                  px, py, tx, unit, edge_clear, owned, as_boxes(parts),
                  as_boxes(spot_segs), as_boxes(ncs), as_boxes(corridor_boxes),
                  as_segs(corridor_segs), as_boxes(stem_segs), spot_pad,
                  corridor_pad, stem_pad);
              std::vector<std::tuple<double, double, double, double>> out;
              out.reserve(legs.size());
              for (const auto& leg : legs) {
                  out.emplace_back(leg.first.first, leg.first.second,
                                   leg.second.first, leg.second.second);
              }
              return out;
          });
    m.def("cout_column_centers",
          [](const BoxTup& inductor_out, double pad, double cout_gap,
             double template_clear, const std::vector<PtTup>& halves) {
              auto rows = schgen::cout_column_centers(
                  as_box(inductor_out), pad, cout_gap, template_clear,
                  as_pts(halves));
              std::vector<PtTup> out;
              out.reserve(rows.size());
              for (const auto& p : rows) {
                  out.emplace_back(p.first, p.second);
              }
              return out;
          });
    m.def("bulk_cap_pose",
          [](double hf_ox, const BoxTup& hf_box, const std::string& direction,
             double gap, double hx, double hy, double inductor_left,
             double template_clear) {
              auto p = schgen::bulk_cap_pose(hf_ox, as_box(hf_box), direction,
                                             gap, hx, hy, inductor_left,
                                             template_clear);
              return std::make_tuple(p.first, p.second);
          });
    m.def("bfs_escape",
          [](double pt_x, double pt_y, double ty, double unit,
             double extent_x0, double extent_y0, double extent_x1,
             double extent_y1, double margin_cells,
             const std::vector<BoxTup>& boxes,
             const std::vector<BoxTup>& segs, double cell_pad)
              -> std::optional<std::vector<PtTup>> {
              auto hit = schgen::bfs_escape(
                  pt_x, pt_y, ty, unit, extent_x0, extent_y0, extent_x1,
                  extent_y1, margin_cells, as_boxes(boxes), as_segs(segs),
                  cell_pad);
              if (!hit) {
                  return std::nullopt;
              }
              std::vector<PtTup> out;
              out.reserve(hit->size());
              for (const auto& p : *hit) {
                  out.emplace_back(p.first, p.second);
              }
              return out;
          });
    m.def("place_refdes",
          [](const BoxTup& court, const std::string& ref, double size,
             const BoxTup& box, const schgen::SilkBoxIndex& occupied,
             const schgen::SilkBoxIndex& placed, const BoxTup& bounds,
             double fx, double fy, double ca, double sa, double min_size,
             double box_pad, double far_off, double pen_eps,
             double off_improve, const std::vector<double>& shrinks) {
              auto hit = schgen::place_refdes(
                  as_box(court), ref, size, as_box(box), occupied, placed,
                  as_box(bounds), fx, fy, ca, sa, min_size, box_pad, far_off,
                  pen_eps, off_improve, shrinks);
              return std::make_tuple(
                  hit.moved, hit.local_x, hit.local_y, hit.size,
                  hit.add_box.x0, hit.add_box.y0, hit.add_box.x1,
                  hit.add_box.y1);
          });
    m.def("edge_target",
          [](const std::string& edge, double som_x, double som_y, double som_w,
             double som_h,
             const std::vector<std::pair<std::string, double>>& j_aff,
             const std::vector<std::tuple<std::string, double, double>>&
                 jacks) {
              if (edge.size() != 1) {
                  throw std::runtime_error("edge_target: edge required");
              }
              schgen::PackEdgesSpec spec;
              spec.som_x = som_x;
              spec.som_y = som_y;
              spec.som_w = som_w;
              spec.som_h = som_h;
              std::vector<schgen::PackEdgeJack> rows;
              rows.reserve(jacks.size());
              for (const auto& j : jacks) {
                  rows.push_back(schgen::PackEdgeJack{
                      std::get<0>(j), std::get<1>(j), std::get<2>(j)});
              }
              return schgen::edge_target(edge[0], spec, j_aff, rows);
          });
    m.def("pick_sided_challenger", &schgen::pick_sided_challenger);
    m.def("reseat_rank",
          [](double ax, double ay,
             const std::vector<std::tuple<double, double, double, double,
                                          std::string>>& placed) {
              return schgen::reseat_rank(ax, ay, placed);
          });
    m.def("hf_cap_pose",
          [](double beside_oy, double inductor_left, double template_clear,
             double hx) {
              auto p = schgen::hf_cap_pose(beside_oy, inductor_left,
                                           template_clear, hx);
              return std::make_tuple(p.first, p.second);
          });
    m.def("pack_edges",
          [](const std::vector<std::tuple<
                 std::string, double, double, std::optional<double>,
                 std::tuple<double, double, double, double>,
                 std::tuple<double, double, double, double>,
                 std::vector<std::pair<std::string, double>>, bool,
                 std::string, std::string>>& blocks,
             const std::vector<std::tuple<std::string, double, double>>& jacks,
             double board_w, double board_h, double edge_margin,
             double edge_inset, double clear, double cable_neighbor_gap,
             double overmold_side_gap, double affinity_floor, double som_x,
             double som_y, double som_w, double som_h) {
              schgen::PackEdgesSpec spec;
              spec.board_w = board_w;
              spec.board_h = board_h;
              spec.edge_margin = edge_margin;
              spec.edge_inset = edge_inset;
              spec.clear = clear;
              spec.cable_neighbor_gap = cable_neighbor_gap;
              spec.overmold_side_gap = overmold_side_gap;
              spec.affinity_floor = affinity_floor;
              spec.som_x = som_x;
              spec.som_y = som_y;
              spec.som_w = som_w;
              spec.som_h = som_h;
              std::vector<schgen::PackEdgeBlock> rows;
              rows.reserve(blocks.size());
              for (const auto& b : blocks) {
                  schgen::PackEdgeBlock row;
                  row.name = std::get<0>(b);
                  row.w = std::get<1>(b);
                  row.h = std::get<2>(b);
                  row.order_hint = std::get<3>(b);
                  row.reach = as_halo(std::get<4>(b));
                  row.inset = as_halo(std::get<5>(b));
                  row.j_aff = std::get<6>(b);
                  row.overmold = std::get<7>(b);
                  row.current_edge = std::get<8>(b);
                  row.assigned_edge = std::get<9>(b);
                  rows.push_back(std::move(row));
              }
              std::vector<schgen::PackEdgeJack> jack_rows;
              jack_rows.reserve(jacks.size());
              for (const auto& j : jacks) {
                  jack_rows.push_back(schgen::PackEdgeJack{
                      std::get<0>(j), std::get<1>(j), std::get<2>(j)});
              }
              auto hit = schgen::pack_edges(rows, jack_rows, spec);
              std::vector<std::tuple<std::string, std::string, double, double>>
                  poses;
              poses.reserve(hit.poses.size());
              for (const auto& p : hit.poses) {
                  poses.emplace_back(p.name, p.edge, p.x, p.y);
              }
              return std::make_tuple(poses, hit.spilled);
          });
    m.def("thermal_via_scan",
          [](nb::handle footprint,
             const std::vector<std::tuple<std::string, int, std::string>>&
                 nets) {
              std::unordered_map<std::string, std::pair<int, std::string>>
                  pad_nets;
              for (const auto& n : nets) {
                  pad_nets.emplace(std::get<0>(n),
                                   std::make_pair(std::get<1>(n),
                                                  std::get<2>(n)));
              }
              return schgen::thermal_via_scan(sexpr_from_py(footprint),
                                              pad_nets);
          });
    m.def("silk_gfx_pts",
          [](nb::handle node) {
              auto hit = schgen::silk_gfx_pts(sexpr_from_py(node));
              return std::make_tuple(hit.first, hit.second);
          });
    m.def("collect_fp_silk_gfx",
          [](nb::handle footprint) {
              auto hit = schgen::collect_fp_silk_gfx(sexpr_from_py(footprint));
              std::vector<std::tuple<double, double, double, double>> top;
              std::vector<std::tuple<double, double, double, double>> bot;
              top.reserve(hit.first.size());
              bot.reserve(hit.second.size());
              for (const auto& b : hit.first) {
                  top.emplace_back(b.x0, b.y0, b.x1, b.y1);
              }
              for (const auto& b : hit.second) {
                  bot.emplace_back(b.x0, b.y0, b.x1, b.y1);
              }
              return std::make_tuple(top, bot);
          });
    m.def("farm_row_right_bound", &schgen::farm_row_right_bound);
    m.def("conn_port_columns", &schgen::conn_port_columns);
    m.def("conn_cluster_groups", &schgen::conn_cluster_groups);
    m.def("pad_boxes_local",
          [](const std::vector<std::tuple<std::string, double, double, double,
                                          double, double>>& rows,
             double rotation) {
              return schgen::pad_boxes_local(rows, rotation);
          });
    m.def("pad_boxes_named",
          [](const std::vector<std::tuple<std::string, double, double, double,
                                          double, double>>& rows,
             double rotation) {
              return schgen::pad_boxes_named(rows, rotation);
          });
    m.def("footprint_bbox",
          [](const char* text, int decimals) {
              if (text == nullptr) {
                  throw std::runtime_error("footprint_bbox: text required");
              }
              auto box = schgen::footprint_bbox(schgen::sexpr_loads(text),
                                                decimals);
              return std::make_tuple(box.x0, box.y0, box.x1, box.y1);
          });
    m.def("extract_som_scan",
          [](const char* text) {
              if (text == nullptr) {
                  throw std::runtime_error("extract_som_scan: text required");
              }
              auto hit = schgen::extract_som_scan(text);
              std::vector<std::tuple<std::string, double, double, double,
                                     double, double, double, double>>
                  js;
              js.reserve(hit.js.size());
              for (const auto& j : hit.js) {
                  js.emplace_back(j.ref, j.pcb_x, j.pcb_y, j.rot, j.x, j.y,
                                  j.w, j.h);
              }
              return std::make_tuple(hit.w, hit.h, js);
          });
    m.def("som_keepout_rects",
          [](double som_x, double som_y, double som_w, double som_h,
             double occ_pad,
             const std::vector<std::tuple<double, double, double, double>>&
                 connectors,
             double seat_band) {
              auto boxes = schgen::som_keepout_rects(
                  som_x, som_y, som_w, som_h, occ_pad, connectors, seat_band);
              std::vector<std::tuple<double, double, double, double>> out;
              out.reserve(boxes.size());
              for (const auto& b : boxes) {
                  out.emplace_back(b.x0, b.y0, b.x1, b.y1);
              }
              return out;
          });
    m.def("zone_components_assemble",
          [](const std::vector<BoxTup>& minor, const std::vector<BoxTup>& punch,
             int minor_mask, int punch_mask) {
              auto rows = schgen::zone_components_assemble(
                  as_boxes(minor), as_boxes(punch), minor_mask, punch_mask);
              std::vector<std::tuple<double, double, double, double, int>> out;
              out.reserve(rows.size());
              for (const auto& c : rows) {
                  out.emplace_back(c.dx, c.dy, c.w, c.h, c.mask);
              }
              return out;
          });
    m.def("part_dims_from_name",
          [](const std::string& name,
             const std::vector<std::tuple<std::string, double, double>>&
                 fixed_dims,
             double default_w, double default_h) {
              auto hit = schgen::part_dims_from_name(name, fixed_dims,
                                                     default_w, default_h);
              return std::make_tuple(hit.first, hit.second);
          });
    m.def("courtyard_dims_from_text",
          [](const char* text)
              -> std::optional<std::pair<double, double>> {
              if (text == nullptr) {
                  throw std::runtime_error(
                      "courtyard_dims_from_text: text required");
              }
              return schgen::courtyard_dims_from_text(text);
          });
    m.def("pad_names_from_text",
          [](const char* text) {
              if (text == nullptr) {
                  throw std::runtime_error("pad_names_from_text: text required");
              }
              return schgen::pad_names_from_text(text);
          });
    m.def("has_thru_pads_from_text",
          [](const char* text) {
              if (text == nullptr) {
                  throw std::runtime_error(
                      "has_thru_pads_from_text: text required");
              }
              return schgen::has_thru_pads_from_text(text);
          });
    m.def("scan_pad_nodes",
          [](const char* text) {
              if (text == nullptr) {
                  throw std::runtime_error("scan_pad_nodes: text required");
              }
              return schgen::scan_pad_nodes(schgen::sexpr_loads(text));
          });
    m.def("scan_mod_pads",
          [](const char* text) {
              if (text == nullptr) {
                  throw std::runtime_error("scan_mod_pads: text required");
              }
              return schgen::scan_mod_pads(schgen::sexpr_loads(text));
          });
    m.def("ref_prefix", &schgen::ref_prefix);
    m.def("is_testpoint_ref", &schgen::is_testpoint_ref);
    m.def("is_cluster_passive",
          [](const std::string& ref, int pins,
             const std::vector<std::string>& not_plain,
             const std::vector<std::string>& prefixes) {
              return schgen::is_cluster_passive(ref, pins, not_plain,
                                                prefixes);
          });
    m.def("intelligent_need",
          [](int pins,
             const std::vector<std::tuple<int, double, std::string>>& tiers,
             double top_need, const std::string& top_basis) {
              return schgen::intelligent_need(pins, tiers, top_need,
                                              top_basis);
          });
    m.def("zone_fanout_members_rows",
          [](const std::vector<std::tuple<double, double, double, double,
                                          double, double, double, int>>& rows,
             int min_subject_pins,
             const std::vector<std::tuple<int, double>>& need_tiers,
             double top_need) {
              return schgen::zone_fanout_members_rows(
                  rows, min_subject_pins, need_tiers, top_need);
          });
    m.def("inst_placed_box",
          [](const std::tuple<double, double, double, double>& local,
             double inst_x, double inst_y, double rotation, int decimals) {
              auto b = schgen::inst_placed_box(as_box(local), inst_x, inst_y,
                                              rotation, decimals);
              return std::make_tuple(b.x0, b.y0, b.x1, b.y1);
          });
    m.def("collect_gr_text_boxes",
          [](nb::handle doc, double default_size) {
              auto boxes = schgen::collect_gr_text_boxes(sexpr_from_py(doc),
                                                         default_size);
              std::vector<std::tuple<double, double, double, double>> out;
              out.reserve(boxes.size());
              for (const auto& b : boxes) {
                  out.emplace_back(b.x0, b.y0, b.x1, b.y1);
              }
              return out;
          });
    m.def("refine_pack_passes",
          [](const schgen::Occupancy& occupancy,
             const std::vector<std::tuple<
                 std::string, double, double, double, double,
                 std::tuple<double, double, double, double>,
                 std::tuple<double, double, double, double>, int,
                 std::vector<std::tuple<double, double, double, double, int>>,
                 bool, std::string, double, double, double, double, double,
                 double, double, bool, bool, bool, std::string, double, double,
                 double, double, double, double, double, std::string, double,
                 double, double, double, double, double,
                 std::vector<std::pair<std::string, double>>>>& rows,
             const std::vector<std::tuple<std::string, double, double>>&
                 center_rows,
             int max_passes, double board_w, double board_h) {
              std::vector<schgen::RefineBlock> blocks;
              blocks.reserve(rows.size());
              for (const auto& r : rows) {
                  schgen::RefineBlock block;
                  block.name = std::get<0>(r);
                  block.x = std::get<1>(r);
                  block.y = std::get<2>(r);
                  block.w = std::get<3>(r);
                  block.h = std::get<4>(r);
                  block.reach = as_halo(std::get<5>(r));
                  block.inset = as_halo(std::get<6>(r));
                  block.mask = std::get<7>(r);
                  block.comps = as_comps(std::get<8>(r));
                  schgen::PackAnchorIn in;
                  in.face_override = std::get<9>(r);
                  const std::string& face = std::get<10>(r);
                  in.face = face.empty() ? '\0' : face[0];
                  in.som_x = std::get<11>(r);
                  in.som_y = std::get<12>(r);
                  in.som_w = std::get<13>(r);
                  in.som_h = std::get<14>(r);
                  in.som_halo = std::get<15>(r);
                  in.zone_ax = std::get<16>(r);
                  in.zone_ay = std::get<17>(r);
                  in.exclusive = std::get<18>(r);
                  in.inboard = std::get<19>(r);
                  in.zone_is_at_edge = std::get<20>(r);
                  const std::string& edge = std::get<21>(r);
                  in.edge = edge.empty() ? '\0' : edge[0];
                  in.eb_x = std::get<22>(r);
                  in.eb_y = std::get<23>(r);
                  in.eb_w = std::get<24>(r);
                  in.eb_h = std::get<25>(r);
                  in.eb_cx = std::get<26>(r);
                  in.eb_cy = std::get<27>(r);
                  in.pull_weight = std::get<28>(r);
                  block.pull_to = std::get<29>(r);
                  in.zone_w = std::get<30>(r);
                  in.som_w_scale = std::get<31>(r);
                  in.som_pull = std::get<32>(r);
                  in.aff_pow = std::get<33>(r);
                  in.som_cx = std::get<34>(r);
                  in.som_cy = std::get<35>(r);
                  block.anchor = in;
                  block.aff_named = std::get<36>(r);
                  blocks.push_back(std::move(block));
              }
              std::unordered_map<std::string, std::pair<double, double>>
                  centers;
              for (const auto& c : center_rows) {
                  centers.emplace(std::get<0>(c),
                                  std::make_pair(std::get<1>(c),
                                                 std::get<2>(c)));
              }
              auto hit = schgen::refine_pack_passes(
                  occupancy, std::move(blocks), centers, max_passes, board_w,
                  board_h);
              return std::make_tuple(hit.poses, hit.passes);
          });
    m.def("seat_shape_sides",
          [](const schgen::Occupancy& occupancy, double ax, double ay,
             const std::vector<std::tuple<
                 int, double, double,
                 std::tuple<double, double, double, double>,
                 std::tuple<double, double, double, double>, int, std::string,
                 std::vector<std::tuple<double, double, double, double, int>>,
                 double, double, double, double>>& rows,
             double board_w, double board_h, double clear) {
              std::vector<schgen::SeatShapeCand> cands;
              cands.reserve(rows.size());
              for (const auto& r : rows) {
                  schgen::SeatShapeCand cand;
                  cand.index = std::get<0>(r);
                  cand.w = std::get<1>(r);
                  cand.h = std::get<2>(r);
                  cand.reach = as_halo(std::get<3>(r));
                  cand.inset = as_halo(std::get<4>(r));
                  cand.mask = std::get<5>(r);
                  cand.side = std::get<6>(r);
                  cand.comps = as_comps(std::get<7>(r));
                  cand.win_x0 = std::get<8>(r);
                  cand.win_x1 = std::get<9>(r);
                  cand.win_y0 = std::get<10>(r);
                  cand.win_y1 = std::get<11>(r);
                  cands.push_back(std::move(cand));
              }
              auto hits = schgen::seat_shape_sides(
                  occupancy, ax, ay, cands, board_w, board_h, clear);
              std::vector<std::tuple<
                  std::string, int, double, double, double, double,
                  std::tuple<double, double, double, double>,
                  std::tuple<double, double, double, double>,
                  std::vector<std::tuple<double, double, double, double, int>>,
                  double>>
                  out;
              out.reserve(hits.size());
              for (const auto& hit : hits) {
                  std::vector<std::tuple<double, double, double, double, int>>
                      comps;
                  comps.reserve(hit.comps.size());
                  for (const auto& comp : hit.comps) {
                      comps.emplace_back(comp.dx, comp.dy, comp.w, comp.h,
                                         comp.mask);
                  }
                  out.emplace_back(
                      hit.side, hit.index, hit.x, hit.y, hit.w, hit.h,
                      std::make_tuple(hit.reach.w, hit.reach.e, hit.reach.n,
                                      hit.reach.s),
                      std::make_tuple(hit.inset.w, hit.inset.e, hit.inset.n,
                                      hit.inset.s),
                      std::move(comps), hit.dist_key);
              }
              return out;
          });
    m.def("collect_refdes_props",
          [](nb::handle doc, double default_size) {
              auto hits = schgen::collect_refdes_props(sexpr_from_py(doc),
                                                       default_size);
              std::vector<std::tuple<
                  int, int, std::string, double, double, double, double,
                  double, double, double, bool, double, double, double,
                  double>>
                  out;
              out.reserve(hits.size());
              for (const auto& h : hits) {
                  out.emplace_back(h.footprint_index, h.property_index, h.ref,
                                   h.fp_x, h.fp_y, h.cos_a, h.sin_a, h.local_x,
                                   h.local_y, h.size, h.bottom, h.text_box.x0,
                                   h.text_box.y0, h.text_box.x1, h.text_box.y1);
              }
              return out;
          });
    m.def("collect_refdes_rows",
          [](nb::handle doc,
             const std::vector<std::pair<std::string, BoxTup>>& courts,
             double default_size) {
              std::unordered_map<std::string, schgen::Box4> court_by_ref;
              court_by_ref.reserve(courts.size());
              for (const auto& kv : courts) {
                  court_by_ref.emplace(kv.first, as_box(kv.second));
              }
              auto rows = schgen::collect_refdes_rows(
                  sexpr_from_py(doc), court_by_ref, default_size);
              std::vector<std::tuple<
                  int, int, std::string, double, double, double, double,
                  std::tuple<double, double, double, double>, double,
                  std::tuple<double, double, double, double>, bool>>
                  out;
              out.reserve(rows.size());
              for (const auto& r : rows) {
                  out.emplace_back(
                      r.footprint_index, r.property_index, r.ref, r.fp_x,
                      r.fp_y, r.cos_a, r.sin_a,
                      std::make_tuple(r.court.x0, r.court.y0, r.court.x1,
                                      r.court.y1),
                      r.size,
                      std::make_tuple(r.text_box.x0, r.text_box.y0,
                                      r.text_box.x1, r.text_box.y1),
                      r.bottom);
              }
              return out;
          });
    m.def("footprint_alias", &schgen::footprint_alias);
    m.def("mirror_assert_ok", &schgen::mirror_assert_ok);
    m.def("needs_flag", &schgen::needs_flag);
    m.def("farm_cluster_origin",
          [](double extent_x0, double extent_y1, double unit, int n_box_bucks) {
              return schgen::farm_cluster_origin(extent_x0, extent_y1, unit,
                                                 n_box_bucks);
          });
    m.def("next_rail_col", &schgen::next_rail_col);
    m.def("set_font_size",
          [](nb::handle node, double size) {
              return sexpr_to_tagged(
                  schgen::set_font_size(sexpr_from_py(node), size));
          });
    m.def("hide_undersom_bottom_refs",
          [](nb::handle doc, double x0, double y0, double x1, double y1) {
              auto hit = schgen::hide_undersom_bottom_refs(
                  sexpr_from_py(doc), x0, y0, x1, y1);
              return std::make_tuple(sexpr_to_tagged(hit.first), hit.second);
          });
    m.def("turn_point",
          [](double x, double y, double deg) {
              auto p = schgen::turn_point(x, y, deg);
              return std::make_tuple(p.first, p.second);
          });
    m.def("world_turned_point",
          [](double inst_x, double inst_y, double lx, double ly, double rot,
             int decimals) {
              return schgen::world_turned_point(inst_x, inst_y, lx, ly, rot,
                                                decimals);
          });
    m.def("turn_box",
          [](const std::tuple<double, double, double, double>& box,
             double deg) {
              auto b = schgen::turn_box(as_box(box), deg);
              return std::make_tuple(b.x0, b.y0, b.x1, b.y1);
          });
    m.def("pad_half_extent",
          [](double size_w, double size_h, double deg) {
              auto p = schgen::pad_half_extent(size_w, size_h, deg);
              return std::make_tuple(p.first, p.second);
          });
    m.def("corners_rot",
          [](const std::tuple<double, double, double, double>& rect,
             double rot, double inst_x, double inst_y, double lo_x,
             double lo_y, double hi_x, double hi_y, int decimals) {
              auto pts = schgen::corners_rot(as_box(rect), rot, inst_x, inst_y,
                                             lo_x, lo_y, hi_x, hi_y, decimals);
              std::vector<std::tuple<double, double>> out;
              out.reserve(pts.size());
              for (const auto& p : pts) {
                  out.emplace_back(p.first, p.second);
              }
              return out;
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
    m.def("emit_iso_void_zone",
          [](const std::vector<PtTup>& corners, const char* uuid,
             const char* name, const char* layer, double min_thickness) {
              if (uuid == nullptr || name == nullptr || layer == nullptr) {
                  throw std::runtime_error(
                      "emit_iso_void_zone: uuid, name, and layer required");
              }
              return sexpr_to_tagged(schgen::emit_iso_void_zone(
                  as_pts(corners), uuid, name, layer, min_thickness));
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
    m.def("emit_layers_node",
          []() { return sexpr_to_tagged(schgen::emit_layers_node()); });
    m.def("emit_stackup_node",
          []() { return sexpr_to_tagged(schgen::emit_stackup_node()); });
    m.def("emit_sheet",
          [](double x, double y, double w, double h, const char* uuid,
             const char* name, const char* file, const char* inst_project,
             const char* path, const char* page,
             const std::vector<std::tuple<std::string, std::string, double,
                                          double, double, std::string,
                                          std::string>>& pins) {
              if (uuid == nullptr || name == nullptr || file == nullptr
                  || inst_project == nullptr || path == nullptr
                  || page == nullptr) {
                  throw std::runtime_error(
                      "emit_sheet: uuid, name, file, project, path, page "
                      "required");
              }
              std::vector<schgen::SheetPin> rows;
              rows.reserve(pins.size());
              for (const auto& p : pins) {
                  schgen::SheetPin pin;
                  pin.name = std::get<0>(p);
                  pin.shape = std::get<1>(p);
                  pin.x = std::get<2>(p);
                  pin.y = std::get<3>(p);
                  pin.rot = std::get<4>(p);
                  pin.justify = std::get<5>(p);
                  pin.uuid = std::get<6>(p);
                  rows.push_back(std::move(pin));
              }
              return sexpr_to_tagged(schgen::emit_sheet(
                  x, y, w, h, uuid, name, file, inst_project, path, page,
                  rows));
          });
    m.def("emit_symbol",
          [](const char* lib_id, double x, double y, double rot,
             const char* uuid, const char* ref, double ref_x, double ref_y,
             double ref_rot, bool hide_ref, const char* value, double val_x,
             double val_y, double val_rot, bool hide_val,
             const char* footprint,
             const std::vector<std::tuple<std::string, std::string>>& fields,
             const std::vector<std::tuple<std::string, std::string>>& pins,
             const char* inst_project, const char* inst_path) {
              if (lib_id == nullptr || uuid == nullptr || ref == nullptr
                  || value == nullptr || footprint == nullptr
                  || inst_project == nullptr || inst_path == nullptr) {
                  throw std::runtime_error(
                      "emit_symbol: lib_id, uuid, ref, value, footprint, "
                      "project, and path required");
              }
              std::vector<std::pair<std::string, std::string>> extra;
              extra.reserve(fields.size());
              for (const auto& f : fields) {
                  extra.emplace_back(std::get<0>(f), std::get<1>(f));
              }
              std::vector<std::pair<std::string, std::string>> pin_rows;
              pin_rows.reserve(pins.size());
              for (const auto& p : pins) {
                  pin_rows.emplace_back(std::get<0>(p), std::get<1>(p));
              }
              return sexpr_to_tagged(schgen::emit_symbol(
                  lib_id, x, y, rot, uuid, ref, ref_x, ref_y, ref_rot,
                  hide_ref, value, val_x, val_y, val_rot, hide_val, footprint,
                  extra, pin_rows, inst_project, inst_path));
          });
    m.def("flip_layer_token",
          [](const char* name) {
              if (name == nullptr) {
                  throw std::runtime_error("flip_layer_token: name required");
              }
              return schgen::flip_layer_token(name);
          });
    m.def("rotate_pad_angle", &schgen::rotate_pad_angle);
    m.def("sch_xform",
          [](double x, double y, double ax, double ay, int rot) {
              auto p = schgen::sch_xform(x, y, ax, ay, rot);
              return std::make_tuple(p.first, p.second);
          });
    m.def("pad_union_hull",
          [](const std::vector<std::tuple<std::string, double, double, double,
                                          double>>& pads)
              -> std::optional<std::tuple<double, double, double, double>> {
              auto hit = schgen::pad_union_hull(pads);
              if (!hit) {
                  return std::nullopt;
              }
              return std::make_tuple(hit->x0, hit->y0, hit->x1, hit->y1);
          });
    m.def("centroid_offset",
          [](const std::vector<std::tuple<std::string, double, double>>& offsets,
             double half_w, double half_h) {
              auto hit = schgen::centroid_offset(offsets, half_w, half_h);
              return std::make_tuple(hit.first, hit.second);
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
    m.def("stagger_overlap_ranks",
          [](const std::vector<std::vector<PtTup>>& quads) {
              std::vector<std::vector<std::pair<double, double>>> rows;
              rows.reserve(quads.size());
              for (const auto& q : quads) {
                  rows.push_back(as_pts(q));
              }
              return schgen::stagger_overlap_ranks(rows);
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
    nb::class_<schgen::SilkBoxIndex>(m, "SilkBoxIndex")
        .def(nb::init<double>(), nb::arg("cell") = 8.0)
        .def("add",
             [](schgen::SilkBoxIndex& self, const BoxTup& box) {
                 self.add(as_box(box));
             })
        .def("pen",
             [](const schgen::SilkBoxIndex& self, const BoxTup& gb) {
                 return self.pen(as_box(gb));
             })
        .def("hits",
             [](const schgen::SilkBoxIndex& self, const BoxTup& gb) {
                 return self.hits(as_box(gb));
             });
    nb::class_<schgen::BreatheGrid>(m, "BreatheGrid")
        .def(nb::init<double, double, double, double, double>())
        .def("stamp",
             [](schgen::BreatheGrid& self, const BoxTup& box, int val) {
                 self.stamp(as_box(box), val);
             },
             nb::arg("box"), nb::arg("val") = 1)
        .def("free",
             [](const schgen::BreatheGrid& self, const BoxTup& box) {
                 return self.free(as_box(box));
             });
}
