#include "schgen/board_inputs.hpp"
#include "schgen/catalog.hpp"
#include "schgen/board_schematic.hpp"
#include "schgen/netlist_gate.hpp"
#include "../src/pcb_placement_internal.hpp"
#include <fstream>
#include <cstdlib>
#include <unistd.h>
#include <iostream>

namespace {
using namespace schgen;
std::size_t checks = 0;
void require(bool ok, const std::string& message) {
    ++checks; if (!ok) throw std::runtime_error(message);
}
template<class F> void rejects(F f, const std::string& message) {
    bool threw = false;
    try { f(); } catch (const std::exception&) { threw = true; }
    require(threw, message);
}
bool same(const FloorplanZoneShape& a, const FloorplanZoneShape& b) {
    return a.w == b.w && a.h == b.h && a.top_off == b.top_off && a.bot_off == b.bot_off &&
        a.extra_rot == b.extra_rot && a.tag == b.tag && a.side == b.side && a.mirror == b.mirror;
}
std::vector<FloorplanZoneShape> shapes(const PcbZoneResult& z, const std::string& sheet) {
    auto found = z.geometry.shapes.find(sheet);
    if (found != z.geometry.shapes.end()) return found->second;
    FloorplanZoneShape s; s.w = z.geometry.zone_box.at(sheet).first;
    s.h = z.geometry.zone_box.at(sheet).second; s.top_off = z.geometry.top_off.at(sheet);
    s.bot_off = z.geometry.bot_off.at(sheet); s.tag = "base";
    for (const auto* offsets : {&s.top_off, &s.bot_off}) for (const auto& [ref, xy] : *offsets) {
        (void)xy; auto r = z.geometry.zone_extra_rot.find(ref);
        if (r != z.geometry.zone_extra_rot.end()) s.extra_rot.emplace(*r);
    }
    return {s};
}
// Independent assembly through the production binder, not adapter internals.
PcbCheckModel model_for(const PcbPlacementInput& in, const PcbZoneResult& zones,
    const std::string& sheet, int index) {
    const auto g = bind_pcb_zone_shapes(zones, {{sheet, index}});
    std::map<std::pair<std::string, std::string>, std::pair<int, std::string>> pins;
    PcbCheckModel m; m.origin_x = m.origin_y = 0;
    m.board_w = g.zone_box.at(sheet).first; m.board_h = g.zone_box.at(sheet).second;
    int next = 1;
    for (const auto& [net, ps] : in.netlist) if (!net.empty() && net.rfind("unconnected-", 0) != 0) {
        m.net_numbers[net] = next++;
        for (const auto& p : ps) pins[{p.ref, p.pin}] = {m.net_numbers.at(net), net};
    }
    pcb_placement::Context ctx(in);
    for (const auto& ref : g.refs_by_sheet.at(sheet)) {
        PcbCheckInstance p; const auto& part = ctx.by_ref.at(ref);
        p.ref = ref; p.sheet = sheet; p.value = part.value; p.footprint = part.footprint;
        p.mod = zones.footprints.at(g.resolvable.at(ref));
        p.mirror = g.mirror_refs.count(ref); p.side = g.side_of.at(ref);
        const auto& offsets = g.top_off.at(sheet).count(ref) ? g.top_off.at(sheet) : g.bot_off.at(sheet);
        p.x = offsets.at(ref).first; p.y = offsets.at(ref).second;
        p.rotation = g.zone_extra_rot.count(ref) ? g.zone_extra_rot.at(ref) : 0;
        for (const auto& pin : pad_names_from_text(p.mod->bytes))
            p.pad_nets[pin] = pins.count({ref, pin}) ? pins.at({ref, pin}) : std::pair<int, std::string>{0, ""};
        m.insts.push_back(p);
    }
    return m;
}
void check_quality(const PcbPlacementInput& in, const PcbZoneResult& zones,
    const std::string& sheet, int index) {
    const auto& q = zones.owned_shape_quality.at({sheet, index});
    require(q.state == OwnedShapeQualityState::Measured, "missing meaningful quality for existing/new shape");
    const auto& rows = owned_group_placements(*in.owned_groups.at(sheet));
    require(q.bypass_pad_gaps.size() + q.bulk_pad_gaps.size() == rows.size(), "all roles measured");
    auto m = model_for(in, zones, sheet, index); PcbCheckInput checked(m);
    std::map<std::string, std::size_t> indices;
    for (std::size_t i = 0; i < m.insts.size(); ++i) indices[m.insts[i].ref] = i;
    for (const auto& r : rows) {
        const auto a = checked.geometry_at(indices.at(r.owner)).pad_boxes.at(r.owner_pin);
        const auto b = checked.geometry_at(indices.at(r.cap)).pad_boxes.at(r.cap_pin);
        const double gap = std::hypot(std::max({0., a.x0-b.x1, b.x0-a.x1}),
                                     std::max({0., a.y0-b.y1, b.y0-a.y1}));
        const auto& metrics = r.role == OwnedCapRole::Bypass ? q.bypass_pad_gaps : q.bulk_pad_gaps;
        require(metrics.at(r.cap) == gap, "quality disagrees with bound physical named pads");
    }
    require(q.fanout_starved == check_fanout(checked, std::nullopt).n_starved, "fanout quality");
}
}
int main(int argc, char** argv) {
    using namespace schgen;
    try {
        if (argc != 4)
            throw std::runtime_error("usage: adapter-contracts REPOSITORY CATALOG PRIVATE-SCRATCH");
        close_part_catalog();
        const auto paths = resolve_project_paths(argv[1], "carrier");
        const auto circuits = load_project_circuits(paths);
        std::vector<CircuitSheetIr> sheets;
        for (const auto& c : circuits) sheets.push_back(c.circuit);
        const auto link = link_sheets(sheets, parse_json_file(paths.som_interface_file.string()),
            parse_json_file((paths.project_root / "som_mapping.json").string()));
        require(link.ok(), "live link");
        const auto nets = extract_netlist(paths.project_root / "Zynq_Carrier.kicad_sch");
        BoardInputOptions options; options.compact_search = true;
        auto in = load_board_inputs(paths, circuits, link, nets, options);
        require(in.owned_groups.size() == 2, "production loader did not resolve both mandatory sheets");
        rejects([&] { (void)part_catalog_count(); }, "production loader leaked global catalog");
        auto missing_catalog = paths;
        missing_catalog.part_catalog_file = std::filesystem::path(argv[3]) / "absent-catalog.bin";
        rejects([&] { load_board_inputs(missing_catalog, circuits, link, nets, options); },
                "production loader accepted missing independent catalog");
        std::size_t rows = 0, bulk = 0;
        for (const auto& [sheet, trusted] : in.owned_groups) {
            (void)sheet; for (const auto& r : owned_group_placements(*trusted)) {
                ++rows; bulk += r.role == OwnedCapRole::OutputBulk;
            }
        }
        require(rows == 6 && bulk == 1, "six explicit owners and one fixed bulk");
        auto disabled = in; disabled.floorplan.compact_search = false;
        require(resolve_owned_group_inputs(paths, {}, disabled).empty(), "default resolver must be a no-op");
        auto unrelated = paths; unrelated.is_default_project = false;
        require(resolve_owned_group_inputs(unrelated, {}, in).empty(), "no carrier policy injected into other project");

        auto bad = in; bad.floorplan.sheet_index.push_back(bad.floorplan.sheet_index.front());
        rejects([&] { resolve_owned_group_inputs(paths, circuits, bad); }, "duplicate hierarchy band accepted");
        auto bad_circuits = circuits;
        bad_circuits.erase(std::remove_if(bad_circuits.begin(), bad_circuits.end(), [](const auto& c) { return c.name == "board_aux"; }), bad_circuits.end());
        rejects([&] { resolve_owned_group_inputs(paths, bad_circuits, in); }, "missing required live sheet accepted");
        bad_circuits = circuits;
        for (auto& c : bad_circuits) if (c.name == "board_aux")
            for (auto& p : c.circuit.parts) if (p.ref == "U1") p.value = "wrong-catalog-part";
        rejects([&] { resolve_owned_group_inputs(paths, bad_circuits, in); }, "catalog identity drift accepted");
        bad_circuits = circuits;
        for (auto& c : bad_circuits) if (c.name == "board_aux")
            for (auto& p : c.circuit.parts) if (p.ref == "C1") p.value = "10u";
        rejects([&] { resolve_owned_group_inputs(paths, bad_circuits, in); }, "cap value drift accepted");
        const auto cap = owned_group_placements(*in.owned_groups.at("board_aux")).front().cap;
        bad = in;
        for (auto& [net, ps] : bad.netlist) { (void)net;
            ps.erase(std::remove_if(ps.begin(), ps.end(), [&](const auto& p) { return p.ref == cap && p.pin == "1"; }), ps.end());
        }
        rejects([&] { resolve_owned_group_inputs(paths, circuits, bad); }, "missing extracted pin accepted");
        bad.netlist.push_back({"wrong-rail", {{cap, "1"}}});
        rejects([&] { resolve_owned_group_inputs(paths, circuits, bad); }, "split extracted rail accepted");
        bad = in; bad.netlist.push_back({"extra-pin-net", {{cap, "99"}}});
        rejects([&] { resolve_owned_group_inputs(paths, circuits, bad); }, "extra physical pin accepted");

        std::filesystem::create_directories(argv[3]);
        auto pattern = (std::filesystem::path(argv[3]) / "owned-adapter.XXXXXX").string();
        const auto created = ::mkdtemp(pattern.data());
        require(created != nullptr, "private manifest scratch creation");
        const std::filesystem::path scratch = created;
        std::filesystem::create_directories(scratch / "board_aux");
        std::filesystem::create_directories(scratch / "bringup_rails");
        auto private_paths = paths; private_paths.subsystems_dir = scratch;
        rejects([&] { resolve_owned_group_inputs(private_paths, circuits, in); }, "missing mandatory manifest accepted");
        for (const auto* sheet : {"board_aux", "bringup_rails"})
            std::filesystem::copy_file(paths.subsystems_dir / sheet / "placement_requirements.json",
                scratch / sheet / "placement_requirements.json", std::filesystem::copy_options::overwrite_existing);
        const auto manifest = scratch / "board_aux/placement_requirements.json";
        std::ifstream read(manifest); const std::string original((std::istreambuf_iterator<char>(read)), {}); read.close();
        auto changed = original; changed.replace(changed.find("input_bypass"), std::string("input_bypass").size(), "unknown_role");
        { std::ofstream file(manifest); file << changed; }
        rejects([&] { resolve_owned_group_inputs(private_paths, circuits, in); }, "unknown manifest role accepted");
        changed = original;
        const auto first = changed.find('{', changed.find("\"ownership\""));
        const auto last = changed.find('}', first);
        changed.erase(first, changed.find(',', last) - first + 1);
        { std::ofstream file(manifest); file << changed; }
        rejects([&] { resolve_owned_group_inputs(private_paths, circuits, in); }, "omitted reviewed ownership accepted");
        changed = original;
        changed.replace(changed.find("\"SW1\""), 5, "\"SW99\"");
        { std::ofstream file(manifest); file << changed; }
        rejects([&] { resolve_owned_group_inputs(private_paths, circuits, in); }, "wrong top access declaration accepted");
        { std::ofstream file(manifest); file << original; }
        require(resolve_owned_group_inputs(private_paths, circuits, in).size() == 2, "private manifest recovery");

        // Run only the two owned zones. No board solve, placement stages,
        // render, emission or publication. Retain their live layer policies.
        in.floorplan.sheets.erase(std::remove_if(in.floorplan.sheets.begin(), in.floorplan.sheets.end(),
            [&](const auto& c) { return !in.owned_groups.count(c.name); }), in.floorplan.sheets.end());
        auto& spec = *in.floorplan.spec; spec.edges.clear(); spec.ordered_edges.clear();
        for (auto i = spec.interior.begin(); i != spec.interior.end();)
            if (!in.owned_groups.count(i->first)) i = spec.interior.erase(i); else ++i;
        auto baseline_in = in; baseline_in.owned_groups.clear();
        const auto baseline = build_pcb_zone_geometry(baseline_in);
        const auto zones = build_pcb_zone_geometry(in);
        std::size_t appended = 0, expected_calls = 0, measured_shapes = 0;
        for (const auto& [sheet, trusted] : in.owned_groups) {
            const auto old = shapes(baseline, sheet), now = shapes(zones, sheet);
            require(now.size() > old.size(), sheet + " production hook appended no owned alternatives");
            for (std::size_t i = 0; i < old.size(); ++i) require(same(old[i], now[i]), "original alternative/index modified");
            require(baseline.geometry.top_off.at(sheet) == zones.geometry.top_off.at(sheet) &&
                baseline.geometry.bot_off.at(sheet) == zones.geometry.bot_off.at(sheet) &&
                baseline.geometry.zone_box.at(sheet) == zones.geometry.zone_box.at(sheet), "incumbent overwritten");
            std::size_t bypass = 0;
            for (const auto& r : owned_group_placements(*trusted)) bypass += r.role == OwnedCapRole::Bypass;
            // Every constructor makes two cap orders, each with one alignment
            // plus twelve trials per other part, two scalar calls per trial.
            expected_calls += old.size() * 2 * bypass * (1 + 12 * (zones.geometry.refs_by_sheet.at(sheet).size()-1)) * 2;
            for (std::size_t i = 0; i < now.size(); ++i) {
                check_quality(in, zones, sheet, static_cast<int>(i)); ++measured_shapes;
                if (i < old.size()) continue;
                const auto pos = now[i].tag.find("/owned-pins-");
                require(pos != std::string::npos, "appended shape provenance");
                const auto parent_tag = now[i].tag.substr(0, pos);
                auto parent = std::find_if(old.begin(), old.end(), [&](const auto& s) { return s.tag == parent_tag; });
                require(parent != old.end(), "candidate recursively generated from appended output");
                require(now[i].side == parent->side && now[i].mirror == parent->mirror && now[i].extra_rot == parent->extra_rot,
                    "side/mirror/rotation changed");
                std::set<std::string> movable;
                for (const auto& r : owned_group_placements(*trusted)) if (r.role == OwnedCapRole::Bypass) movable.insert(r.cap);
                for (const auto* offsets : {&parent->top_off, &parent->bot_off}) for (const auto& [ref, xy] : *offsets)
                    if (!movable.count(ref)) require((now[i].top_off.count(ref) ? now[i].top_off : now[i].bot_off).at(ref) == xy,
                        "fixed owner/bulk/switch/member moved");
                const auto& before = zones.owned_shape_quality.at({sheet, static_cast<int>(parent-old.begin())});
                const auto& after = zones.owned_shape_quality.at({sheet, static_cast<int>(i)});
                bool improvement = false;
                for (const auto& [ref, gap] : after.bypass_pad_gaps) {
                    require(gap <= before.bypass_pad_gaps.at(ref), "owned gap regressed");
                    improvement |= gap < before.bypass_pad_gaps.at(ref);
                }
                require(improvement && *after.fanout_starved <= *before.fanout_starved, "candidate quality not improved");
            }
            appended += now.size()-old.size();
            std::cout << sheet << ": " << old.size() << " originals retained, " << now.size()-old.size() << " owned alternatives appended\n";
        }
        auto expected = baseline.quantization_engagements;
        checked_quantization_add(expected, "placement_member_pose_precision4dp", expected_calls);
        require(zones.quantization_engagements == expected, "exact production count delta including discarded candidates");
        auto prefix = in; prefix.owned_groups.erase("bringup_rails");
        const auto successful_prefix = build_pcb_zone_geometry(prefix);
        auto later_failure = prefix; later_failure.owned_groups["bringup_rails"] = nullptr;
        ExecutionFailureReceipt receipt;
        rejects([&] { build_pcb_zone_geometry(later_failure, &receipt); }, "null trusted evidence accepted");
        require(receipt.captured && !receipt.unavailable &&
            receipt.accounting.quantization_engagements == successful_prefix.quantization_engagements,
            "later zone failure lost/doubled prior adapter attempts");

        // Force an immutable owner overlap in one original. The helper must
        // discard its trials, and the hook must still retain every scalar call.
        auto rejected = baseline;
        auto original_shape = shapes(baseline, "board_aux").front();
        const auto& declarations = owned_group_placements(*in.owned_groups.at("board_aux"));
        const auto owner1 = declarations.front().owner;
        const auto owner2 = declarations.back().owner;
        auto& owner1_map = original_shape.top_off.count(owner1) ? original_shape.top_off : original_shape.bot_off;
        auto& owner2_map = original_shape.top_off.count(owner2) ? original_shape.top_off : original_shape.bot_off;
        require(&owner1_map == &owner2_map, "overlap fixture owners need same face");
        owner2_map.at(owner2) = owner1_map.at(owner1);
        rejected.geometry.shapes["board_aux"] = {original_shape};
        pcb_placement::Context context(in); context.pool = baseline.footprints;
        pcb_placement::append_owned_group_zone_shapes(context, rejected, "board_aux", original_shape, true);
        require(rejected.geometry.shapes.at("board_aux").size() == 1 &&
            same(rejected.geometry.shapes.at("board_aux").front(), original_shape), "rejected search changed incumbent");
        const auto rejected_calls = 2 * 4 * (1 + 12 * (rejected.geometry.refs_by_sheet.at("board_aux").size()-1)) * 2;
        require(context.quantization.size() == 1 &&
            context.quantization.at("placement_member_pose_precision4dp") == rejected_calls,
            "fully rejected helper attempts lost their exact counts");
        auto excluded = baseline;
        pcb_placement::Context excluded_context(in); excluded_context.pool = baseline.footprints;
        pcb_placement::append_owned_group_zone_shapes(excluded_context, excluded, "board_aux",
            shapes(baseline, "board_aux").front(), false);
        require(excluded_context.quantization.empty() &&
            shapes(excluded, "board_aux").size() == shapes(baseline, "board_aux").size(),
            "excluded zone acquired movement or counts");
        for (std::size_t i = 0; i < shapes(excluded, "board_aux").size(); ++i)
            check_quality(in, excluded, "board_aux", static_cast<int>(i));

        auto repeat = build_pcb_zone_geometry(in);
        require(repeat.quantization_engagements == zones.quantization_engagements, "nondeterministic counts");
        for (const auto& [sheet, trusted] : in.owned_groups) { (void)trusted;
            const auto a = shapes(zones, sheet), b = shapes(repeat, sheet);
            require(a.size() == b.size(), "nondeterministic alternatives");
            for (std::size_t i = 0; i < a.size(); ++i) require(same(a[i], b[i]), "nondeterministic shape");
        }
        auto legacy = in; legacy.floorplan.compact_search = false;
        auto legacy_empty = legacy; legacy_empty.owned_groups.clear();
        auto a = build_pcb_zone_geometry(legacy), b = build_pcb_zone_geometry(legacy_empty);
        require(a.owned_shape_quality.empty() && a.quantization_engagements == b.quantization_engagements, "default activation/count regression");
        for (const auto& [sheet, trusted] : in.owned_groups) { (void)trusted;
            auto as = shapes(a, sheet), bs = shapes(b, sheet); require(as.size() == bs.size(), "default shape count");
            for (std::size_t i = 0; i < as.size(); ++i) require(same(as[i], bs[i]), "default geometry changed");
        }
        close_part_catalog();
        std::cout << "PASS " << checks << " adapter checks; " << appended << " appended, " << measured_shapes
                  << " shapes measured; exact attempted scalar delta=" << expected_calls << "; no board solve/render\n";
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
