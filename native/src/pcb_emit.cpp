#include "pcb_emit_internal.hpp"
#include "schgen/schematic.hpp"

namespace schgen {
using namespace pcb_emission;
const PcbEmitPolicy &default_pcb_emit_policy() {
    static const PcbEmitPolicy policy = [] {
        PcbEmitPolicy p;
        p.footprint_aliases = {
            {"Capacitor_SMD:C_1206_3225Metric", "Capacitor_SMD:C_1206_3216Metric"}};
        p.connector_mating_faces = {
            {"TYPE-C-31-M-12", "+Y"}, {"HDMI-019S", "+Y"},    {"AFC07-S40FCA-00", "+Y"},
            {"KH-5224-8P8C-D", "+Y"}, {"TF-01A", "+Y"},       {"SFW15R-1STE1LF", "+Y"},
            {"ZX-SH1.0-4PWT", "+Y"},  {"DS1024-2x6R2", "+Y"}, {"XT60PW-M", "+X"}};
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
PcbEmitPolicy pcb_emit_policy(const ProjectConfig &c) {
    auto p = default_pcb_emit_policy();
    p.header_descriptions = c.header_desc;
    p.switch_descriptions = c.switch_desc;
    return p;
}
PcbEmissionResult render_pcb(const PcbModel &m, const PcbEmitPolicy &p) {
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
                     str("FOUNDATION: derived outline + SoM-body keep-out + 4L stackup + net "
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
        auto pts = closed_rect_pts(*m.som_keepout, 3);
        pts.pop_back();
        root.push_back(emit_keepout_zone(pts, uid("som-keepout"), "SoM_body_keepout"));
    }
    auto g = m.net_numbers.find("GND");
    if (g != m.net_numbers.end() && g->second) {
        double b = p.gnd_plane_edge_back;
        auto box = round_box({m.origin_x + b, m.origin_y + b, m.origin_x + m.board_w - b,
                              m.origin_y + m.board_h - b},
                             3);
        root.push_back(emit_fill_zone(g->second, "GND", "GND_plane_In1", p.ground_layer,
                                      rect_corners_ccw(box), uid("gnd-plane"),
                                      p.gnd_plane_clearance, false, p.zone_min_thickness));
    }
    for (const auto &i : m.insts)
        if (std::any_of(p.isolation_prefixes.begin(), p.isolation_prefixes.end(),
                        [&](const auto &prefix) { return starts(i.value, prefix); }))
            root.push_back(emit_iso_void_zone(
                rect_corners_ccw(isolation_void_rect(courtyard(i), p.isolation_margin)),
                uid("iso-void:" + i.ref), "ethernet_isolation_void_" + i.ref, p.ground_layer,
                p.zone_min_thickness));
    auto thermal = thermal_nodes(m, p, uid, result);
    root.insert(root.end(), thermal.zones.begin(), thermal.zones.end());
    if (m.som_core) {
        auto b = *m.som_core;
        auto pts = closed_rect_pts(b, 3);
        for (std::size_t n = 0; n < 4; ++n)
            root.push_back(emit_gr_line(pts[n].first, pts[n].second, pts[n + 1].first,
                                        pts[n + 1].second, .15, "F.SilkS",
                                        uid("som-silk:" + std::to_string(n))));
        auto [ax, ay] = round_xy(b.x0, b.y0 + 3, 3);
        auto [bx, by] = round_xy(b.x0 + 3, b.y0, 3);
        root.push_back(emit_gr_line(ax, ay, bx, by, .15, "F.SilkS", uid("som-silk:ch")));
        auto [x, y] = round_xy(b.x0 + 1, b.y0 - 1.2, 3);
        root.push_back(emit_gr_text("Zynq SoM", x, y, 0, "F.SilkS", uid("som-silk:label"), 1.4, .25,
                                    "left bottom"));
    }
    for (const auto &i : m.insts)
        root.push_back(embed(i, p, uid));
    if (m.som_keepout) {
        auto b = *m.som_keepout;
        auto hidden = hide_undersom_bottom_refs(std::move(doc), b.x0, b.y0, b.x1, b.y1);
        doc = std::move(hidden.first);
        result.hidden_bottom_references = hidden.second;
    }
    // Reacquire the list after the value-returning hide transform.
    auto labels = descriptors(m, p, uid, doc);
    auto &final = std::get<SexprList>(doc.v);
    final.insert(final.end(), labels.begin(), labels.end());
    result.moved_references = declutter(m, doc);
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
                            const PcbEmitPolicy &p) {
    auto r = render_pcb(m, p);
    publish(path, r.pcb);
    return r;
}
} // namespace schgen
