#include "pcb_placement_internal.hpp"

namespace schgen::pcb_placement {
Context::Context(const PcbPlacementInput &input)
    : in(input), pool(input.footprints), clearance(input.floorplan.place_clear) {
    if (!std::isfinite(clearance) || clearance <= 0)
        throw PcbZoneInfeasible("placement clearance must be positive and finite");
    wired.insert(in.floorplan.project.wired_sheets.begin(),
                 in.floorplan.project.wired_sheets.end());
    pilot.insert(in.floorplan.project.pilot_prox_sheets.begin(),
                 in.floorplan.project.pilot_prox_sheets.end());
    l4_exempt = wired;
    std::map<std::string, int> bands(in.floorplan.sheet_index.begin(),
                                     in.floorplan.sheet_index.end());
    for (std::size_t i = 0; i < in.floorplan.sheets.size(); ++i) {
        const auto &sheet = in.floorplan.sheets[i];
        auto band = bands.count(sheet.name) ? bands.at(sheet.name) : static_cast<int>(i + 1);
        for (const auto &p : sheet.parts) {
            auto ref = board_renamed_ref(p.ref, band, sheet.name);
            BoardPart b{ref, p.ref, sheet.name, p.footprint, p.value, p.lib_id};
            parts.push_back(b);
            by_ref.emplace(ref, b);
            board_refs[sheet.name][p.ref] = ref;
        }
        for (const auto &net : sheet.nets) {
            if (net.net_class == "port") {
                auto pt = circuit_port_type(sheet, net.name);
                if (pt.kind == "single")
                    continue;
                auto klass = port_net_class(pt);
                if (!classes.count(klass)) {
                    auto g = pt.has_impedance ? differential_geometry(pt.impedance) : nullptr;
                    classes[klass] = g ? std::optional<DifferentialGeometry>(*g) : std::nullopt;
                }
                netclass_of[net.name] = klass;
            } else if (net.net_class == "power") {
                classes.emplace("POWER", std::nullopt);
                netclass_of[net.name] = "POWER";
            }
        }
        if (sheet.name.size() == 6 && sheet.name.rfind("som_j", 0) == 0) {
            auto ref = "J" + sheet.name.substr(5);
            auto p = std::find_if(sheet.parts.begin(), sheet.parts.end(),
                                  [&](const auto &x) { return x.ref == ref; });
            if (p != sheet.parts.end()) {
                auto fp = resolve(p->footprint);
                auto j = std::find_if(in.floorplan.som.js.begin(), in.floorplan.som.js.end(),
                                      [&](const auto &x) { return x.ref == ref; });
                if (fp && j != in.floorplan.som.js.end()) {
                    PcbStagePartner partner;
                    partner.footprint = fp;
                    partner.rotation = j->w < j->h ? 90 : 0;
                    for (const auto &net : sheet.nets)
                        for (const auto &pin : net.pins)
                            if (pin.ref == ref)
                                partner.nets[net.name].push_back(pin.pin);
                    partners[sheet.name] = std::move(partner);
                }
            }
        }
    }
    for (const auto &[sheet, c] : in.contracts)
        if (wired.count(sheet))
            for (const auto &near : optional(optional(c, "external"), "near_max").array_value) {
                auto target = text(near, "other");
                target = target.substr(0, target.find('.'));
                l4_exempt.insert(target);
            }
    l4_exempt.erase("@som");
}
std::string Context::key(const std::string &footprint) const {
    auto p = in.floorplan.footprint_of.find(footprint);
    return p == in.floorplan.footprint_of.end() ? "" : p->second;
}
PcbCheckFootprintPtr Context::resolve(const std::string &footprint) const {
    auto k = key(footprint);
    auto p = pool.find(k);
    return p == pool.end() ? nullptr : p->second;
}
PcbStageInput Context::stage_input(const std::string &sheet, const Geometry &g) const {
    PcbStageInput s;
    s.sheet = sheet;
    auto c = in.contracts.find(sheet);
    if (c != in.contracts.end())
        s.contract = c->second;
    auto b = board_refs.find(sheet);
    if (b != board_refs.end())
        s.board_refs = b->second;
    auto r = g.refs_by_sheet.find(sheet);
    if (r != g.refs_by_sheet.end())
        s.refs = r->second;
    s.side_of = g.side_of;
    s.bbox_of = g.bbox_of;
    s.pilot = pilot.count(sheet);
    s.partners = partners;
    s.place_clear = clearance;
    for (const auto &[ref, k] : g.resolvable)
        s.footprints[ref] = pool.at(k);
    for (const auto &sc : in.floorplan.sheets)
        if (sc.name == sheet)
            for (const auto &net : sc.nets)
                for (const auto &pin : net.pins)
                    if (!pin.ref.empty() && pin.ref[0] != '#') {
                        auto b = s.board_refs.find(pin.ref);
                        if (b != s.board_refs.end())
                            s.pad_nets[{b->second, pin.pin}] = net.name;
                        if (net.net_class == "port" || net.net_class == "power" ||
                            net.net_class == "ground")
                            s.inter_nets[pin.ref][net.name].push_back(pin.pin);
                    }
    if (in.floorplan.spec) {
        const auto &spec = *in.floorplan.spec;
        auto edges = spec.edge_of();
        auto e = edges.find(sheet);
        if (e != edges.end())
            s.outer_dir = e->second;
        if (!text(optional(s.contract, "external"), "downstream").empty()) {
            std::string side = s.outer_dir;
            auto i = spec.interior.find(sheet);
            if (i != spec.interior.end() && i->second.side)
                side = *i->second.side;
            if (side == "N")
                s.facing = "S";
            else if (side == "S")
                s.facing = "N";
            else if (side == "E")
                s.facing = "W";
            else if (side == "W")
                s.facing = "E";
        }
        if (s.facing.empty() &&
            optional(optional(s.contract, "external"), "media_faces_near_max").bool_value) {
            const auto &near = optional(optional(s.contract, "external"), "near_max").array_value;
            if (!near.empty()) {
                auto target = text(near.front(), "other");
                target = target.substr(0, target.find('.'));
                auto e = edges.find(target);
                if (e != edges.end())
                    s.facing = e->second;
            }
        }
    }
    return s;
}
bool face_top(const BoardPart &p) {
    auto prefix = ref_prefix(p.ref);
    return prefix == "TP" || prefix == "LED" || prefix == "SW" ||
           p.footprint.find("TestPoint") != std::string::npos ||
           p.lib_id.find("TestPoint") != std::string::npos || p.footprint.rfind("LED_", 0) == 0 ||
           p.lib_id.rfind("Switch:", 0) == 0;
}
bool edge_family(const std::string &value) {
    static const std::set<std::string> values{"TYPE-C-31-M-12", "HDMI-019S", "AFC07-S40FCA-00",
                                              "SFW15R-1STE1LF", "TF-01A",    "DS1024-2x6R2",
                                              "XT60PW-M"};
    return values.count(value) != 0;
}
Shape turned(const Shape &s, QuantizationCounts* counts) {
    Shape out = s;
    out.w = placement_turn_dimension_precision4dp(s.h, counts);
    out.h = placement_turn_dimension_precision4dp(s.w, counts);
    out.extra_rot.clear();
    for (auto *offsets : {&out.top_off, &out.bot_off})
        for (auto &[r, p] : *offsets) {
            p = {placement_turn_offset_precision4dp(p.second, counts), placement_turn_offset_precision4dp(s.w - p.first, counts)};
            auto rot = s.extra_rot.find(r);
            out.extra_rot[r] = normalize((rot == s.extra_rot.end() ? 0 : rot->second) + 90);
        }
    return out;
}
} // namespace schgen::pcb_placement
