#include "schgen/turn.hpp"
#include "schgen/stackup.hpp"
#include "pcb_emit_internal.hpp"
#include "schgen/label_seats.hpp"
#include "schgen/schematic.hpp"

namespace schgen {
using namespace pcb_emission;
const PcbEmitPolicy &default_pcb_emit_policy() {
    static const PcbEmitPolicy policy = [] {
        PcbEmitPolicy p;
        p.footprint_aliases = {
            {"Capacitor_SMD:C_1206_3225Metric", "Capacitor_SMD:C_1206_3216Metric"}};
        p.connector_descriptions = {{"pd_input", "PWR"},
                                    {"usbc_otg", "USB OTG"},
                                    {"usb_jtag_connector", "JTAG"},
                                    {"usb_uart_connector", "UART"},
                                    {"microsd", "microSD"},
                                    {"hdmi_tx", "HDMI TX"},
                                    {"hdmi_rx", "HDMI RX"},
                                    {"rj45_connector", "ETH"},
                                    {"board_qwiic", "QWIIC"},
                                    {"camera", "CAM"},
                                    {"lcd", "LCD"},
                                    {"pmod", "PMOD"},
                                    {"pmod_expansion", "PMOD"}};
        p.thermal_copper = {{"LM61460",
                             {{{1.55, -2.5},
                               {1.55, 2.5},
                               {2.45, -2.5},
                               {2.45, 2.5},
                               {1.55, -4.35},
                               {1.55, 4.35},
                               {2.45, -4.35},
                               {2.45, 4.35},
                               {1, -4.35},
                               {1, 4.35},
                               {-1.6, -2.7},
                               {-1.6, 2.7},
                               {.3, -2.6},
                               {.3, 2.6},
                               {2.85, -1.45},
                               {2.85, 0},
                               {2.85, 1.45}},
                              8,
                              {-3, -4.75, 4.4, 4.75},
                              {"F.Cu", "B.Cu"},
                              "TI SNVSBD5D 11.1.1 thermal-via field at PGND1/PGND2"}},
                            {"TLV75725",
                             {{{-1.15, 0},
                               {1.15, 0},
                               {-1.75, 0},
                               {1.75, 0},
                               {1.85, -1},
                               {1.85, 1},
                               {2.35, -.55},
                               {2.35, .55},
                               {-1.85, -1},
                               {-1.85, 1}},
                              3,
                              {-2.9, -1.6, 2.9, 1.6},
                              {"F.Cu"},
                              "TI TLV757P DYD JESD51-5 pad-adjacent thermal vias"}}};
        for (const auto &[_, need] : default_thermal_policy().pour_needs)
            p.thermal_credit_needs.push_back(need);
        p.isolation_prefixes = {"HX5008", "KH-5224"};
        return p;
    }();
    return policy;
}
Box4 ground_plane_box(double origin_x, double origin_y, double width, double height, double edge_back) {
    return {origin_x + edge_back, origin_y + edge_back, origin_x + width - edge_back, origin_y + height - edge_back};
}
Box4 thermal_pour_local(const Box4& pour, bool mirror) {
    return mirror ? Box4{pour.x0, 0.0 - pour.y1, pour.x1, 0.0 - pour.y0} : pour;
}
std::vector<std::pair<double, double>> thermal_pour_corners(const Box4& local, double rotation, double x, double y,
                                                            const Box4& plane) {
    return corners_rot(local, rotation, x, y, plane.x0, plane.y0, plane.x1, plane.y1, 3);
}
Box4 thermal_pour_extent(const Box4& pour, bool mirror, double rotation, double x, double y, const Box4& plane) {
    const auto corners = thermal_pour_corners(thermal_pour_local(pour, mirror), rotation, x, y, plane);
    Box4 extent{corners.front().first, corners.front().second, corners.front().first, corners.front().second};
    for (const auto& [cx, cy] : corners) {
        extent.x0 = std::min(extent.x0, cx);
        extent.y0 = std::min(extent.y0, cy);
        extent.x1 = std::max(extent.x1, cx);
        extent.y1 = std::max(extent.y1, cy);
    }
    return extent;
}
PcbEmitPolicy pcb_emit_policy(const ProjectConfig &c) {
    auto p = default_pcb_emit_policy();
    p.interface_reference_labels_only = true;
    p.labels = c.labels;
    p.connectors = c.connectors;
    p.header_descriptions = c.header_desc;
    p.switch_descriptions = c.switch_desc;
    p.model_overrides = project_pcb_model_overrides();
    return p;
}
const std::vector<PcbModelOverride>& project_pcb_model_overrides() {
    // Genuine part-linked CAD, quarter-turn aligned to the unchanged stock pads.
    // Provenance and orientation proof: tests/data/render_models/FUSB302B_REPAIR.md.
    static const std::vector<PcbModelOverride> overrides{{"FUSB302BMPX",
        "Package_DFN_QFN:WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm",
        "${KIPRJMOD}/../parts/FUSB302BMPX/FUSB302BMPX.wrl", 90}};
    return overrides;
}
PcbEmissionResult render_pcb(const PcbModel &m, const PcbEmitPolicy &p, QuantizationCounts* counts,
                            const labels::LabelSeating* seats) {
    if (seats && !p.labels)
        throw PcbEmissionError("label seats were supplied while labels are off");
    if (!std::isfinite(m.board_w) || !std::isfinite(m.board_h) || m.board_w <= 0 || m.board_h <= 0)
        throw PcbEmissionError("PCB outline dimensions must be finite and positive");
    // Typed callers bypass the JSON boundary. Reject nonfinite geometry before
    // it can reach the silk spatial index's floating-to-integer cell conversion.
    auto finite = [](std::initializer_list<double> values) {
        return std::all_of(values.begin(), values.end(), [](double v) { return std::isfinite(v); });
    };
    if (!finite({m.origin_x, m.origin_y}))
        throw PcbEmissionError("PCB origin must be finite");
    for (const auto &i : m.insts) {
        if (!finite({i.x, i.y, i.rotation}))
            throw PcbEmissionError(i.ref + ": nonfinite placement");
        if (i.side != "top" && i.side != "bottom")
            throw PcbEmissionError(i.ref + ": invalid footprint side " + i.side);
    }
    for (const auto &b : {m.som_keepout, m.som_core})
        if (b && !finite({b->x0, b->y0, b->x1, b->y1}))
            throw PcbEmissionError("PCB SoM box must be finite");
    for (const auto &c : m.copper) {
        if (c.kind != "via" && c.kind != "segment")
            throw PcbEmissionError("unknown escape copper kind '" + c.kind + "'");
        if (!finite({c.x, c.y, c.x1, c.y1, c.x2, c.y2, c.size, c.drill, c.width}))
            throw PcbEmissionError("PCB copper geometry must be finite");
    }
    for (const auto &[index, locked] : m.copper_locks) {
        (void)locked;
        if (index >= m.copper.size() || m.copper[index].kind != "via")
            throw PcbEmissionError("PCB copper lock must refer to a via index");
    }
    if (!std::isfinite(p.thermal_lattice_pitch) || p.thermal_lattice_pitch <= 0)
        throw PcbEmissionError("PCB thermal lattice pitch must be finite and positive");
    PcbEmissionResult result;
    if (!counts) counts = &result.quantization_engagements;
    std::map<std::string, std::size_t> seqs;
    const auto board = schematic_stable_uuid({"Zynq_Carrier", "pcb"});
    Uid uid = [&](const std::string &key) {
        return schematic_stable_uuid({board, "pcb-id", key, std::to_string(seqs[key]++)});
    };
    auto &doc = result.document;
    doc = node(
        "kicad_pcb",
        {node("version", {num(20260206)}), node("generator", {str("schgen")}),
         node("generator_version", {str("1.0")}),
         node("general",
              {node("thickness", {num(p.stack_thickness)}), node("legacy_teardrops", {sym("no")})}),
         node("paper", {str("A3")}),
         node("title_block",
              {node("title", {str("Zynq Carrier — PCB foundation (schgen)")}),
               node("company", {str("Zynq SoM Carrier")}),
               node("comment",
                    {num(1),
                     str("FOUNDATION: derived outline + SoM-body keep-out + " + std::to_string(board_stackup().copper.size()) + "L stackup + net "
                         "classes + 2-side placement (SoM-mirror mezzanine, per-subsystem ratsnest "
                         "bundles). NOT routed — schgen-generated (do not hand-edit).")})}),
         emit_layers_node()});
    auto &root = std::get<SexprList>(doc.v);
    root.push_back(node("setup", {emit_stackup_node(), node("pad_to_mask_clearance", {num(0)}),
                                  node("allow_soldermask_bridges_in_footprints", {sym("yes")}),
                                  node("aux_axis_origin", {num(m.origin_x), num(m.origin_y)})}));
    std::vector<std::pair<std::string, int>> nets(m.net_numbers.begin(), m.net_numbers.end());
    std::stable_sort(nets.begin(), nets.end(),
                     [](const auto &a, const auto &b) { return a.second < b.second; });
    for (const auto &[name, n] : nets)
        root.push_back(node("net", {num(n), str(name)}));
    Points edges{{m.origin_x, m.origin_y},
                 {m.origin_x + m.board_w, m.origin_y},
                 {m.origin_x + m.board_w, m.origin_y + m.board_h},
                 {m.origin_x, m.origin_y + m.board_h},
                 {m.origin_x, m.origin_y}};
    for (std::size_t n = 0; n < 4; ++n)
        root.push_back(emit_edge_line(edges[n].first, edges[n].second, edges[n + 1].first,
                                      edges[n + 1].second, uid("edge:" + std::to_string(n))));
    if (m.som_keepout) {
        auto pts = closed_rect_pts(*m.som_keepout, 3, counts);
        pts.pop_back();
        root.push_back(emit_keepout_zone(pts, uid("som-keepout"), "SoM_body_keepout"));
    }
    auto g = m.net_numbers.find("GND");
    if (g != m.net_numbers.end() && g->second) {
        auto box = round_box(ground_plane_box(m.origin_x, m.origin_y, m.board_w, m.board_h, p.gnd_plane_edge_back),
                             3, counts);
        for (const std::string& layer : board_stackup().ground_layers()) {
            const std::string inner = layer.substr(0, layer.find('.'));
            root.push_back(emit_fill_zone(g->second, "GND", "GND_plane_" + inner, layer, rect_corners_ccw(box),
                                          uid(layer == p.ground_layer ? "gnd-plane" : "gnd-plane:" + layer),
                                          p.gnd_plane_clearance, false, p.zone_min_thickness));
        }
    }
    for (const auto &i : m.insts)
        if (std::any_of(p.isolation_prefixes.begin(), p.isolation_prefixes.end(),
                        [&](const auto &prefix) { return starts(i.value, prefix); }))
            for (const CopperLayer& layer : board_stackup().copper) {
                if (layer.role == CopperRole::signal) continue;
                root.push_back(emit_iso_void_zone(
                    rect_corners_ccw(isolation_void_rect(courtyard(i), p.isolation_margin, counts)),
                    uid(layer.name == p.ground_layer ? "iso-void:" + i.ref : "iso-void:" + i.ref + ":" + layer.name),
                    "ethernet_isolation_void_" + i.ref + (layer.name == p.ground_layer ? "" : "_" + layer.name.substr(0, layer.name.find('.'))),
                    layer.name, p.zone_min_thickness));
            }
    auto thermal = thermal_nodes(m, p, uid, result, counts);
    root.insert(root.end(), thermal.zones.begin(), thermal.zones.end());
    if (m.som_core) {
        auto b = *m.som_core;
        auto pts = closed_rect_pts(b, 3, counts);
        for (std::size_t n = 0; n < 4; ++n)
            root.push_back(emit_gr_line(pts[n].first, pts[n].second, pts[n + 1].first,
                                        pts[n + 1].second, .15, "F.SilkS",
                                        uid("som-silk:" + std::to_string(n))));
        auto [ax, ay] = round_xy(b.x0, b.y0 + 3, 3, counts);
        auto [bx, by] = round_xy(b.x0 + 3, b.y0, 3, counts);
        root.push_back(emit_gr_line(ax, ay, bx, by, .15, "F.SilkS", uid("som-silk:ch")));
        auto [x, y] = round_xy(b.x0 + labels::constants::title_indent.value, b.y0 - labels::constants::title_rise.value, 3, counts);
        root.push_back(emit_gr_text(labels::module_title, x, y, 0, "F.SilkS", uid("som-silk:label"),
                                    labels::constants::title_height.value, .25,
                                    "left bottom"));
    }
    for (const auto &i : m.insts)
        root.push_back(embed(i, p, uid));
    if (seats) {
        seat_references(m, doc, *seats);
    } else if (m.som_keepout) {
        auto b = *m.som_keepout;
        auto hidden = hide_undersom_bottom_refs(std::move(doc), b.x0, b.y0, b.x1, b.y1);
        doc = std::move(hidden.first);
        result.hidden_bottom_references = hidden.second;
    }
    // Reacquire the list after the value-returning hide transform.
    auto labels = p.labels ? descriptors(m, p, uid, doc, counts, seats) : std::vector<Sexpr>{};
    auto &final = std::get<SexprList>(doc.v);
    final.insert(final.end(), labels.begin(), labels.end());
    if (!seats)
        result.moved_references = declutter(m, doc, counts);
    final.insert(final.end(), thermal.vias.begin(), thermal.vias.end());
    for (std::size_t index = 0; index < m.copper.size(); ++index) {
        const auto &c = m.copper[index];
        if (c.kind == "via") {
            auto lock = m.copper_locks.find(index);
            final.push_back(emit_via(c.x, c.y, c.size, c.drill, c.net, uid("stitch-via"),
                                     lock == m.copper_locks.end() || lock->second));
        } else if (c.kind == "segment")
            final.push_back(
                emit_segment(c.x1, c.y1, c.x2, c.y2, c.width, c.layer, c.net, uid("stitch-seg")));
        else
            throw PcbEmissionError("unknown escape copper kind '" + c.kind + "'");
    }
    result.pcb = sexpr_dumps(doc) + "\n";
    return result;
}
PcbEmissionResult write_pcb(const PcbModel &m, const std::filesystem::path &path,
                            const PcbEmitPolicy &p, QuantizationCounts* counts) {
    auto r = render_pcb(m, p, counts);
    publish(path, r.pcb);
    return r;
}
} // namespace schgen
