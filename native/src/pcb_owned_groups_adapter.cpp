#include "schgen/pcb_owned_groups_adapter.hpp"
#include "schgen/placement_requirements.hpp"
#include "pcb_placement_internal.hpp"
#include "schgen/pcb_placement_gates.hpp"

namespace schgen {
class TrustedOwnedGroups {
public:
    PlacementRequirements requirements;
    PlacementRequirementDeclaration declaration;
    CircuitSheetIr circuit;
    std::map<std::string, CatalogPart> catalog;
    std::map<std::string, std::string> refs, nets;
    std::map<std::pair<std::string, std::string>, std::pair<int, std::string>> pin_nets;
    std::map<std::string, int> net_numbers;
    std::vector<OwnedCapPlacement> rows;
};
const std::vector<OwnedCapPlacement>& owned_group_placements(const TrustedOwnedGroups& trusted) {
    return trusted.rows;
}
namespace {
void demand(bool value, const std::string& message) {
    if (!value) throw std::runtime_error("owned-group adapter: " + message);
}
OwnedCapRole role_of(const std::string& role) {
    if (role == "shared_output_bulk") return OwnedCapRole::OutputBulk;
    if (role == "input_bypass" || role == "output_bypass" || role == "supply_bypass" ||
        role == "authored_reference_rail_bypass_not_translation_filter") return OwnedCapRole::Bypass;
    throw std::runtime_error("owned-group adapter: unknown role " + role);
}
void attach_nets(PcbCheckInstance& p, const TrustedOwnedGroups& trusted) {
    for (const auto& pin : pad_names_from_text(p.mod->bytes)) {
        auto found = trusted.pin_nets.find({p.ref, pin});
        p.pad_nets.emplace(pin, found == trusted.pin_nets.end()
            ? std::pair<int, std::string>{0, ""} : found->second);
    }
}
PlacementRequirementReport identity(const TrustedOwnedGroups& t, const PcbCheckInput& model) {
    return check_placement_requirements(t.requirements, t.declaration, t.circuit,
        t.catalog, model, t.refs, t.nets);
}
}
TrustedOwnedGroupInputs resolve_owned_group_inputs(const ProjectPaths& paths,
    const std::vector<ProjectCircuit>& circuits, const PcbPlacementInput& in) {
    TrustedOwnedGroupInputs result;
    if (!in.floorplan.compact_search || !paths.is_default_project) return result;
    std::map<std::string, int> bands;
    std::set<int> used_bands;
    for (const auto& [sheet, band] : in.floorplan.sheet_index)
        demand(bands.emplace(sheet, band).second && used_bands.insert(band).second,
               "duplicate sheet/band mapping");
    std::map<std::pair<std::string, std::string>, std::string> extracted;
    std::map<std::string, int> numbers{{"", 0}};
    int next = 1;
    for (const auto& [net, pins] : in.netlist) {
        if (net.empty() || net.rfind("unconnected-", 0) == 0) continue;
        demand(numbers.emplace(net, next++).second, "duplicate extracted net");
        for (const auto& pin : pins)
            demand(extracted.emplace(std::make_pair(pin.ref, pin.pin), net).second,
                   "multiply-netted extracted pin " + pin.ref + "." + pin.pin);
    }
    for (const auto* sheet : {"board_aux", "bringup_rails"}) {
        auto t = std::make_shared<TrustedOwnedGroups>();
        t->declaration = carrier_surface_requirement_declaration(sheet);
        // Missing/malformed required manifests fail. No catch-and-empty path.
        t->requirements = parse_placement_requirements(parse_json_file(
            (paths.subsystems_dir / sheet / "placement_requirements.json").string()));
        const ProjectCircuit* source = nullptr;
        for (const auto& c : circuits) if (c.name == sheet) {
            demand(!source, "duplicate live sheet"); source = &c;
        }
        demand(source && bands.count(sheet), "missing live sheet/band " + std::string(sheet));
        t->circuit = source->circuit;
        for (const auto& p : t->circuit.parts)
            demand(t->refs.emplace(p.ref, board_renamed_ref(p.ref, bands.at(sheet), sheet)).second,
                   "duplicate live reference");
        for (const auto& net : t->circuit.nets) {
            for (const auto& pin : net.pins) {
                const auto ref = t->refs.at(pin.ref);
                const auto& mapped = extracted.at({ref, pin.pin});
                auto [found, inserted] = t->nets.emplace(net.name, mapped);
                demand(inserted || found->second == mapped, "split extracted net " + net.name);
            }
        }
        t->net_numbers = numbers;
        // Include ALL extracted connected pins for these references. The
        // independent checker rejects extra connections, not just missing ones.
        std::set<std::string> board_refs;
        for (const auto& [local, ref] : t->refs) { (void)local; board_refs.insert(ref); }
        for (const auto& [pin, net] : extracted) if (board_refs.count(pin.first))
            t->pin_nets.emplace(pin, std::make_pair(numbers.at(net), net));
        std::vector<std::string> owner_mpns;
        for (const auto& [ref, mpn] : t->declaration.owner_mpn) {
            (void)ref; owner_mpns.push_back(mpn);
        }
        const auto owners = read_part_catalog(paths.part_catalog_file.string(), owner_mpns);
        for (std::size_t i = 0; i < owners.size(); ++i)
            t->catalog.emplace(owner_mpns[i], owners[i]);
        // Validate before accepting typed rows. This identity-only probe uses
        // real source footprints; its neutral top poses grant no movement.
        PcbCheckModel probe; probe.net_numbers = numbers;
        for (const auto& p : t->circuit.parts) {
            PcbCheckInstance inst;
            inst.ref = t->refs.at(p.ref); inst.sheet = sheet;
            inst.value = p.value; inst.footprint = p.footprint;
            inst.mod = in.footprints.at(in.floorplan.footprint_of.at(p.footprint));
            attach_nets(inst, *t);
            // A netlist pin absent from the physical footprint is also fatal.
            for (const auto& [pin, net] : t->pin_nets) if (pin.first == inst.ref) {
                (void)net; demand(inst.pad_nets.count(pin.second), "extracted pin absent from footprint");
            }
            probe.insts.push_back(std::move(inst));
        }
        auto report = identity(*t, PcbCheckInput(std::move(probe)));
        demand(report.hard_requirements_met(), report.summary());
        for (const auto& r : t->requirements.ownership)
            t->rows.push_back({t->refs.at(r.owner), r.pin, t->refs.at(r.cap), r.cap_pin,
                r.return_pin, t->nets.at(r.rail), t->nets.at(r.return_net), role_of(r.role)});
        result.emplace(sheet, std::move(t));
    }
    return result;
}

namespace pcb_placement {
namespace {
PcbCheckModel local_model(const Context& ctx, const Geometry& g, const std::string& sheet,
    const Shape& shape, const TrustedOwnedGroups& trusted) {
    demand(shape.side == "top" || shape.side == "bottom", "invalid shape side");
    PcbCheckModel model; model.origin_x = model.origin_y = 0;
    model.board_w = shape.w; model.board_h = shape.h;
    model.net_numbers = trusted.net_numbers;
    std::set<std::string> seen;
    for (const auto* offsets : {&shape.top_off, &shape.bot_off})
        for (const auto& [ref, xy] : *offsets) {
            demand(seen.insert(ref).second, "duplicate shape reference");
            const auto& p = ctx.by_ref.at(ref);
            demand(p.sheet == sheet, "foreign shape member");
            PcbCheckInstance inst; inst.ref = ref; inst.sheet = sheet;
            inst.value = p.value; inst.footprint = p.footprint;
            inst.side = offsets == &shape.top_off ? shape.side :
                (shape.side == "top" ? "bottom" : "top");
            auto mirror = shape.mirror.find(ref);
            inst.mod = ctx.pool.at(mirror == shape.mirror.end() ? g.resolvable.at(ref) : mirror->second);
            inst.mirror = mirror != shape.mirror.end();
            inst.x = xy.first; inst.y = xy.second;
            inst.rotation = normalize((g.conn_rot.count(ref) ? g.conn_rot.at(ref) : 0) +
                (shape.extra_rot.count(ref) ? shape.extra_rot.at(ref) : 0));
            attach_nets(inst, trusted);
            model.insts.push_back(std::move(inst));
        }
    demand(seen == std::set<std::string>(g.refs_by_sheet.at(sheet).begin(),
        g.refs_by_sheet.at(sheet).end()), "incomplete shape population");
    return model;
}
OwnedShapeQuality quality(const Context& ctx, const TrustedOwnedGroups& t,
    const PcbCheckModel& model, ExecutionFailureReceipt* failure) {
    OwnedShapeQuality q; q.state = OwnedShapeQualityState::Rejected;
    const PcbCheckInput checked(model);
    const auto report = identity(t, checked);
    q.diagnostics = report.violations;
    if (!report.hard_requirements_met()) return q;
    for (const auto& m : report.measurements) {
        const auto cap = t.refs.at(m.member);
        const auto row = std::find_if(t.rows.begin(), t.rows.end(), [&](const auto& r) { return r.cap == cap; });
        demand(row != t.rows.end(), "measurement lacks declared ownership");
        q.measurements.push_back({m.owner, m.owner_pin, m.member, m.member_pin,
            m.owner_side, m.member_side, m.planar_pad_box_gap_mm});
        q.subjects.emplace(cap, OwnedShapeSubject{row->owner, row->owner_pin, row->cap_pin,
            row->return_pin, row->rail, row->return_net, m.owner_side, m.member_side,
            row->role == OwnedCapRole::Bypass ? OwnedShapeRole::Bypass : OwnedShapeRole::OutputBulk});
        (row->role == OwnedCapRole::Bypass ? q.bypass_pad_gaps : q.bulk_pad_gaps)
            .emplace(cap, m.planar_pad_box_gap_mm);
    }
    auto mech = check_placement_mech(checked);
    merge_execution_counts(ctx.quantization, mech.quantization_engagements, failure);
    if (!mech.ok) q.diagnostics.push_back(mech.summary());
    const auto contract = ctx.in.contracts.find(t.circuit.name);
    if (contract != ctx.in.contracts.end()) {
        const auto result = check_pcb_placement_contract(checked, t.circuit.name, &contract->second, t.refs);
        if (!result.ok) q.diagnostics.push_back(result.summary());
    }
    q.fanout_starved = check_fanout(checked, std::nullopt).n_starved;
    if (q.diagnostics.empty()) q.state = OwnedShapeQualityState::Measured;
    return q;
}
bool same_shape(const Shape& a, const Shape& b) {
    return a.w == b.w && a.h == b.h && a.top_off == b.top_off && a.bot_off == b.bot_off &&
        a.extra_rot == b.extra_rot && a.side == b.side && a.mirror == b.mirror;
}
}
void append_owned_group_zone_shapes(Context& ctx, PcbZoneResult& out, const std::string& sheet,
    const Shape& incumbent, bool allow_movement, ExecutionFailureReceipt* failure) {
    if (!ctx.in.floorplan.compact_search) return;
    auto& g = out.geometry;
    const auto found = g.shapes.find(sheet);
    const auto originals = found == g.shapes.end() ? std::vector<Shape>{incumbent} : found->second;
    const auto evidence = ctx.in.owned_groups.find(sheet);
    if (evidence == ctx.in.owned_groups.end()) {
        for (std::size_t i = 0; i < originals.size(); ++i)
            out.owned_shape_quality[{sheet, static_cast<int>(i)}] = {};
        return;
    }
    demand(bool(evidence->second), "null trusted input");
    const auto& trusted = *evidence->second;
    // Even an inert authored contract may constrain an individual member.
    // Do not grant local search permission under unhandled external policy.
    const auto contract = ctx.in.contracts.find(sheet);
    if (contract != ctx.in.contracts.end()) allow_movement = false;
    auto variants = originals;
    for (std::size_t i = 0; i < originals.size(); ++i) {
        const auto model = local_model(ctx, g, sheet, originals[i], trusted);
        const auto before = quality(ctx, trusted, model, failure);
        out.owned_shape_quality[{sheet, static_cast<int>(i)}] = before;
        if (!allow_movement || before.state != OwnedShapeQualityState::Measured) continue;
        OwnedGroupOptions options; options.compact = true; options.clearance = ctx.clearance;
        for (const auto& ref : trusted.requirements.top_switches) {
            options.top_refs.insert(trusted.refs.at(ref)); options.fixed_refs.insert(trusted.refs.at(ref));
        }
        for (const auto& p : model.insts) {
            const auto& part = ctx.by_ref.at(p.ref);
            if (face_top(part) || g.conn_rot.count(p.ref) || g.conn_edge.count(p.ref))
                options.fixed_refs.insert(p.ref);
        }
        for (const auto& r : trusted.rows)
            if (r.role == OwnedCapRole::Bypass && !options.fixed_refs.count(r.cap))
                options.movable_caps.insert(r.cap);
        const auto candidates = construct_owned_group_candidates(model, trusted.rows, options);
        // Import exactly once BEFORE rejection, duplicate checks or any gate
        // which may throw. Failed search attempts are real executed scalars.
        merge_execution_counts(ctx.quantization, candidates.quantization, failure);
        auto& search_notes = out.owned_shape_quality.at({sheet, static_cast<int>(i)}).diagnostics;
        for (const auto& note : candidates.diagnostics) search_notes.push_back("search: " + note);
        search_notes.push_back("Bounded search only: no emitted alternatives is not an infeasibility proof; trial-budget exhaustion is not separately reported by the constructor.");
        for (const auto& candidate : candidates.alternatives) {
            const auto measured = quality(ctx, trusted, candidate.model, failure);
            if (measured.state != OwnedShapeQualityState::Measured ||
                *measured.fanout_starved > *before.fanout_starved) continue;
            auto next = originals[i]; next.w = candidate.model.board_w; next.h = candidate.model.board_h;
            next.tag += "/" + candidate.tag;
            for (const auto& p : candidate.model.insts) {
                auto& offsets = next.top_off.count(p.ref) ? next.top_off : next.bot_off;
                offsets.at(p.ref) = {p.x, p.y};
            }
            if (std::any_of(variants.begin(), variants.end(), [&](const auto& prior) { return same_shape(prior, next); })) continue;
            out.owned_shape_quality[{sheet, static_cast<int>(variants.size())}] = measured;
            variants.push_back(std::move(next));
        }
    }
    if (variants.size() > originals.size()) g.shapes[sheet] = std::move(variants);
}
}
}
