#include "pcb_placement_internal.hpp"

namespace schgen::pcb_placement {
Placer::Placer(const PcbPlacementInput &in, const PcbZoneResult &zones, const FloorplanStage &stage)
    : ctx(in), geometry(zones.geometry), plan(stage.plan), width(plan.board_w),
      height(plan.board_h) {
    ctx.pool = zones.footprints;
    out.floorplan = stage;
    out.fallback_events = zones.fallback_events;
    out.zone_accounting = {zones.quantization_engagements, zones.fallback_events};
    if (!std::isfinite(width) || !std::isfinite(height) || width <= 0 || height <= 0)
        throw PcbZoneInfeasible("invalid board dimensions");
    for (const auto &p : ctx.parts)
        if (!geometry.resolvable.count(p.ref) &&
            (std::find(geometry.mh_refs.begin(), geometry.mh_refs.end(), p.ref) !=
                 geometry.mh_refs.end() ||
             p.sheet.rfind("som_j", 0) == 0 || p.sheet == "som_decoupling")) {
            auto fp = ctx.resolve(p.footprint);
            if (!fp) {
                geometry.deferred.push_back(p.ref + " (" + p.sheet + "): footprint '" +
                                            p.footprint +
                                            "' not found in parts/ or the KiCad std libs");
                continue;
            }
            geometry.resolvable[p.ref] = ctx.key(p.footprint);
            geometry.bbox_of[p.ref] = footprint_bbox(fp->document, 3);
            geometry.side_of[p.ref] = "top";
        }
    auto augmented = zones;
    augmented.geometry = geometry;
    std::map<std::string, int> selected;
    for (const auto *blocks : {&plan.edge_blocks, &plan.interior_blocks})
        for (const auto &b : *blocks)
            selected[b.name] = b.shape_idx;
    geometry = bind_pcb_zone_shapes(augmented, selected);
    observe_checkpoint("shape_bind");
    std::set<std::string> names;
    for (const auto &[name, pins] : ctx.in.netlist) {
        (void)pins;
        if (!name.empty() && name.rfind("unconnected-", 0) != 0)
            names.insert(name);
    }
    net_numbers[""] = 0;
    int index = 1;
    for (const auto &name : names)
        net_numbers[name] = index++;
    for (const auto &[name, pins] : ctx.in.netlist)
        if (name.rfind("unconnected-", 0) != 0)
            for (const auto &pin : pins)
                if (!pin.ref.empty() && pin.ref[0] != '#')
                    pin_net[{pin.ref, pin.pin}] = {
                        net_numbers.count(name) ? net_numbers.at(name) : 0, name};
    keepout = {plan.som_x - 1, plan.som_y - 1, plan.som_x + plan.som.w + 1,
               plan.som_y + plan.som.h + 1};
    for (const auto &[sheet, c] : in.contracts) {
        (void)c;
        auto members = pcb_contract_members(ctx.stage_input(sheet, geometry));
        contract_members.insert(members.begin(), members.end());
    }
}
double Placer::rot(const std::string &r) const {
    auto p = rotations.find(r);
    return p == rotations.end() ? 0 : p->second;
}
std::string Placer::side(const std::string &r) const {
    auto p = geometry.side_of.find(r);
    return p == geometry.side_of.end() ? "top" : p->second;
}
PcbCheckFootprintPtr Placer::mod(const std::string &r) const {
    return ctx.pool.at(geometry.resolvable.at(r));
}
Box4 Placer::box(const std::string &r, FloorplanPoint p) const {
    return offset_turned_box(geometry.bbox_of.at(r), rot(r), p.first, p.second);
}
int Placer::pins(const std::string &r) const {
    return static_cast<int>(pad_names_from_text(mod(r)->bytes).size());
}
void Placer::checkpoint(const std::string &name, bool page) {
    std::map<std::string, PcbPlacementPose> snap;
    if (page) {
        for (const auto &i : out.model.insts)
            snap[i.ref] = {i.x, i.y, i.rotation, i.side};
    } else
        for (const auto &[r, p] : pos)
            snap[r] = {p.first, p.second, rot(r), ""};
    out.stages[name] = snap;
    const std::string domain = page ? "page" : "board";
    if (!previous_domain.empty() && domain == previous_domain) {
        int moved = 0;
        for (const auto &[r, p] : snap) {
            auto i = previous.find(r);
            if (i != previous.end() && i->second != p)
                ++moved;
        }
        out.model.stage_moves[name] = moved;
        if (moved && (name == "instantiate" || name == "escape_copper"))
            throw PcbZoneInfeasible("STAGE MOVEMENT: frozen placement changed at " + name);
    }
    previous = std::move(snap);
    previous_domain = domain;
    observe_checkpoint(name);
}
void Placer::seed() {
    out.stages["zone_pack"] = {};
    out.stages["plan_lattice"] = {};
    out.stages["shape_bind"] = {};
    std::map<std::string, FloorplanPoint> som_rel;
    std::map<std::string, double> som_rot;
    for (const auto &j : plan.som.js) {
        som_rel[j.ref] = {j.x, j.y};
        som_rot[j.ref] = j.w < j.h ? 90 : 0;
    }
    for (const auto &p : ctx.parts)
        if (geometry.resolvable.count(p.ref) && p.sheet.size() >= 6 &&
            p.sheet.rfind("som_j", 0) == 0 && p.ref.rfind("J", 0) == 0) {
            std::string j = "J" + p.sheet.substr(5, 1);
            if (som_rel.count(j)) {
                som_refs[p.ref] = j;
                rotations[p.ref] = som_rot.at(j);
            }
        }
    for (const auto &[r, v] : geometry.conn_rot)
        if (geometry.resolvable.count(r))
            rotations[r] = v;
    for (const auto &[r, v] : geometry.zone_extra_rot)
        if (geometry.resolvable.count(r))
            rotations[r] = normalize(rot(r) + v);
    for (const auto *blocks : {&plan.edge_blocks, &plan.interior_blocks})
        for (const auto &b : *blocks)
            if (geometry.zone_box.count(b.name))
                origins[b.name] = {b.x, b.y};
    const std::vector<FloorplanPoint> corners{
        {5, 5}, {width - 5, 5}, {width - 5, height - 5}, {5, height - 5}};
    for (std::size_t i = 0; i < geometry.mh_refs.size(); ++i) {
        auto r = geometry.mh_refs[i];
        pos[r] = corners[i % 4];
        fixed.insert(r);
    }
    for (const auto &[r, j] : som_refs) {
        pos[r] = {plan.som_x + som_rel.at(j).first, plan.som_y + som_rel.at(j).second};
        fixed.insert(r);
    }
    for (const auto &[sheet, xy] : origins)
        for (const auto *all : {&geometry.top_off, &geometry.bot_off}) {
            auto found = all->find(sheet);
            if (found != all->end())
                for (const auto &[r, p] : found->second) {
                    pos[r] = {xy.first + p.first, xy.second + p.second};
                    grid_placed.insert(r);
                }
        }
    std::vector<std::string> dec;
    for (const auto &[r, p] : ctx.by_ref)
        if (p.sheet == "som_decoupling" && geometry.resolvable.count(r))
            dec.push_back(r);
    auto cells =
        som_decoupling_cells(plan.som_x, plan.som_y, plan.som.w, plan.som.h, plan.dec_count, 6);
    if (dec.size() != cells.size())
        throw PcbZoneInfeasible("decoupling bank count disagrees with resolved parts");
    for (std::size_t i = 0; i < dec.size(); ++i) {
        pos[dec[i]] = cells[i];
        geometry.side_of[dec[i]] = "bottom";
        grid_placed.insert(dec[i]);
    }
    checkpoint("step3_emission");
}
void Placer::instantiate() {
    auto &m = out.model;
    m.board_w = width;
    m.board_h = height;
    m.two_side = ctx.in.two_side;
    m.net_numbers = net_numbers;
    m.netclass_of = ctx.netclass_of;
    m.classes = ctx.classes;
    m.deferred = geometry.deferred;
    for (const auto &[r, key] : geometry.resolvable) {
        (void)key;
        const auto &p = ctx.by_ref.at(r);
        auto xy = pos.find(r);
        if (xy == pos.end())
            throw PcbZoneInfeasible("resolved part has no board pose: " + r);
        std::string face = fixed.count(r) ? "top" : side(r);
        if (face == "bottom" && face_top(p))
            throw PcbZoneInfeasible("EMISSION: user-facing part " + r +
                                    " is about to emit on B.Cu");
        PcbFootprintInst inst;
        inst.ref = r;
        inst.value = p.value;
        inst.footprint = p.footprint;
        inst.sheet = p.sheet;
        inst.side = face;
        inst.mod = mod(r);
        inst.rotation = rot(r);
        inst.mirror = geometry.mirror_refs.count(r);
        for (const auto &pad : pad_names_from_text(inst.mod->bytes)) {
            auto n = pin_net.find({r, pad});
            inst.pad_nets[pad] =
                n == pin_net.end() ? std::pair<int, std::string>{0, ""} : n->second;
        }
        inst.x = grid_placed.count(r) ? py_round(25 + xy->second.first, 4)
                                      : ctx.fixed_grid(25 + xy->second.first);
        inst.y = grid_placed.count(r) ? py_round(25 + xy->second.second, 4)
                                      : ctx.fixed_grid(25 + xy->second.second);
        m.insts.push_back(inst);
        ++m.placed;
        if (face == "bottom")
            ++m.n_bottom;
        else
            ++m.n_top;
    }
    auto fid = ctx.resolve("Fiducial:Fiducial_1mm_Mask2mm");
    if (fid) {
        std::vector<FloorplanPoint> positions{{34, 34},
                                              {25 + width - 9, 34},
                                              {34, 25 + height - 9},
                                              {25 + keepout.x0 + 3, 25 + keepout.y0 + 3},
                                              {25 + keepout.x1 - 3, 25 + keepout.y1 - 3}};
        int index = 1;
        for (auto xy : positions) {
            PcbFootprintInst i;
            i.ref = "FID" + std::to_string(index++);
            i.value = "Fiducial";
            i.footprint = "Fiducial:Fiducial_1mm_Mask2mm";
            i.x = py_round(xy.first, 4);
            i.y = py_round(xy.second, 4);
            i.mod = fid;
            i.sheet = "mechanical";
            m.insts.push_back(i);
            ++m.placed;
            ++m.n_top;
        }
    }
    m.som_keepout = offset_rect(keepout, 25, 25);
    m.som_core = som_core_rect(plan.som_x, plan.som_y, plan.som.w, plan.som.h, 25, 25, .03);
    checkpoint("instantiate");
    checkpoint("emission_frame", true);
}
void Placer::escape() {
    auto v1 = check_return_path(ctx.in.som_interface, ctx.in.return_path_footprints);
    std::map<std::string, PcbEscapeSignalClass> triage;
    for (const auto &i : out.model.insts)
        if (som_refs.count(i.ref))
            for (const auto &[pad, n] : i.pad_nets) {
                (void)pad;
                if (!n.second.empty() && pcb_classify_net(n.second) == "SIGNAL")
                    triage[n.second] = classify_pcb_escape_signal(n.second, ctx.in.function_map);
            }
    for (const auto &v : v1.violations)
        triage[v.net] = classify_pcb_escape_signal(v.net, ctx.in.function_map);
    PcbEscapeInput input(out.model, v1, triage, ctx.in.interface_bytes);
    auto copper = build_pcb_escape_copper(input);
    auto lanes = build_pcb_escape_plan(input);
    out.model.copper = std::move(copper.copper);
    out.model.escape_meta = copper.meta.json();
    out.model.escape_interface_sha256 = copper.meta.som_interface_sha256;
    out.model.escape_plan = lanes.for_checks();
    out.model.escape_plan_record = lanes.json();
    checkpoint("escape_copper", true);
}
} // namespace schgen::pcb_placement

namespace schgen {
PcbPlacementResult place_pcb_model(const PcbPlacementInput &in, const PcbZoneResult &zones,
                                   const FloorplanStage &stage) {
    return place_pcb_model_accounted(in, zones, stage, PcbZoneAccountingOwnership::Unspecified);
}
PcbPlacementResult place_pcb_model_accounted(const PcbPlacementInput &in, const PcbZoneResult &zones,
    const FloorplanStage &stage, PcbZoneAccountingOwnership ownership) {
    pcb_placement::Placer p(in, zones, stage);
    p.out.zone_accounting_ownership = ownership;
    p.seed();
    if (in.two_side)
        p.l4_pull();
    p.checkpoint("l4_pull");
    p.edge_seat();
    p.checkpoint("edge_seat");
    if (in.two_side) {
        p.breathe("A");
        p.breathe("B");
    }
    p.checkpoint("breathe");
    p.refit();
    p.checkpoint("refit_facing");
    p.reorder();
    p.checkpoint("reorder");
    if (in.two_side)
        p.evict();
    p.checkpoint("corridor_eviction");
    p.instantiate();
    p.escape();
    p.out.placement_accounting.quantization_engagements = std::move(p.ctx.quantization);
    return std::move(p.out);
}
ExecutionAccounting pcb_placement_accounting(const PcbPlacementResult &result) {
    const auto ownership = result.zone_accounting_ownership;
    if (ownership != PcbZoneAccountingOwnership::IncludedInFloorplan &&
        ownership != PcbZoneAccountingOwnership::SeparateFromFloorplan)
        throw std::logic_error("PCB accounting: supplied floorplan/zone ownership is unspecified");
    const auto &plan = result.floorplan.plan.accounting;
    ExecutionAccounting total;
    auto append = [&](const auto &delta) {
        checked_quantization_merge(total.quantization_engagements, delta.quantization_engagements);
        total.fallback_events.insert(total.fallback_events.end(), delta.fallback_events.begin(), delta.fallback_events.end());
    };
    // A distinct placement-zone solve ran before the planning-zone/floorplan solve.
    if (ownership == PcbZoneAccountingOwnership::SeparateFromFloorplan) append(result.zone_accounting);
    append(plan);
    append(result.placement_accounting);
    return total;
}
} // namespace schgen
