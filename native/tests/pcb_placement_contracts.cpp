#include "pcb_placement_fixture.hpp"
#include "schgen/pcb_emit.hpp"
#include <iostream>

namespace {
using namespace placement_fixture;
int checks = 0;
void require(bool p, const std::string &message) {
    ++checks;
    if (!p)
        throw std::runtime_error(message);
}
void exact(double a, double b, const std::string &context) {
    require(a == b, context + " actual " + std::to_string(a) + " expected " + std::to_string(b));
}
void same(const J &a, const J &b, const std::string &path) {
    require(a.kind == b.kind, path + " type");
    if (a.kind == JsonKind::Object) {
        require(a.object_value.size() == b.object_value.size(), path + " key count");
        for (const auto &[k, v] : b.object_value)
            same(field(a, k), v, path + "/" + k);
    } else if (a.kind == JsonKind::Array) {
        require(a.array_value.size() == b.array_value.size(), path + " array size");
        for (std::size_t k = 0; k < b.array_value.size(); ++k)
            same(a.array_value[k], b.array_value[k], path + "/" + std::to_string(k));
    } else if (a.kind == JsonKind::Number)
        exact(a.number_value, b.number_value, path);
    else if (a.kind == JsonKind::String)
        require(a.string_value == b.string_value,
                path + " string: " + a.string_value + " != " + b.string_value);
    else if (a.kind == JsonKind::Bool)
        require(a.bool_value == b.bool_value, path + " bool");
}
void offsets(const FloorplanOffsets &actual, const J &expected, const std::string &context) {
    require(actual.size() == expected.object_value.size(), context + " member count");
    for (const auto &[r, p] : expected.object_value) {
        require(actual.count(r), context + " missing " + r);
        auto a = actual.at(r), b = point(p);
        exact(a.first, b.first, context + "/" + r + " x");
        exact(a.second, b.second, context + "/" + r + " y");
    }
}
void rotations(const FloorplanRotations &actual, const J &expected, const std::string &context) {
    require(actual.size() == expected.object_value.size(), context + " member count");
    for (const auto &[r, p] : expected.object_value)
        exact(actual.at(r), p.number_value, context + "/" + r);
}
void geometry(const PcbZoneResult &zones, const J &expected, const std::string &context) {
    const auto &g = zones.geometry;
    offsets(g.zone_box, field(expected, "zone_box"), context + "/size");
    for (const auto &[sheet, e] : field(expected, "top_off").object_value) {
        offsets(g.top_off.at(sheet), e, context + "/" + sheet + "/top");
        offsets(g.bot_off.at(sheet), field(field(expected, "bot_off"), sheet),
                context + "/" + sheet + "/bottom");
    }
    rotations(g.conn_rot, field(expected, "conn_rot"), context + "/connector rotations");
    rotations(g.zone_extra_rot, field(expected, "zone_extra_rot"), context + "/extra rotations");
    require(g.side_of.size() == field(expected, "side_of").object_value.size(),
            context + " sides count");
    for (const auto &[r, s] : field(expected, "side_of").object_value)
        require(g.side_of.at(r) == s.string_value, context + " side " + r);
    require(g.shapes.size() == field(expected, "shapes").object_value.size(),
            context + " shape sheets count");
    for (const auto &[sheet, ss] : field(expected, "shapes").object_value) {
        const auto &shapes = g.shapes.at(sheet);
        require(shapes.size() == ss.array_value.size(), context + " " + sheet + " shape count");
        for (std::size_t k = 0; k < shapes.size(); ++k) {
            const auto &s = shapes[k];
            const auto &e = ss.array_value[k];
            auto where = context + "/" + sheet + "/shape " + std::to_string(k);
            exact(s.w, number(e, "w"), where + " w");
            exact(s.h, number(e, "h"), where + " h");
            offsets(s.top_off, field(e, "top_off"), where + " top");
            offsets(s.bot_off, field(e, "bot_off"), where + " bottom");
            rotations(s.extra_rot, field(e, "extra_rot"), where + " rot");
            require(s.side == string(e, "side") && s.tag == string(e, "tag"), where + " tag/side");
            require(s.mirror.size() == field(e, "mirror").object_value.size(),
                    where + " mirror count");
        }
    }
}
void run(const std::filesystem::path &root, const std::string &name, const std::string &mode) {
    auto f = load(root, name);
    const bool single = mode == "--single";
    if (single) {
        const auto variant = parse_json_file(
            (root / "native/tests/data/pcb_placement" / (name + "_single.json")).string());
        f.input.two_side = false;
        if (const auto *error = object_field(variant, "error")) {
            require(error->string_value.find("bringup_rails chose shape 8") != std::string::npos,
                    "frozen carrier top-preferred shape rejection");
            bool rejected = false;
            try {
                build_pcb_model(f.input);
            } catch (const PcbZoneInfeasible &e) {
                rejected = true;
                require(std::string(e.what()).find("bringup_rails chose unregistered shape 8") !=
                            std::string::npos,
                        "same top-preferred shape binding policy rejection");
            }
            require(rejected, "top-preferred model must not ship an unregistered shape");
            return;
        }
        f.model = field(variant, "model");
        f.snapshots = field(variant, "snapshots");
        for (const auto &[path, bytes] : field(variant, "footprints").object_value)
            f.expected_pool[path] = pcb_check_footprint(path, bytes.string_value);
    }
    auto zones = build_pcb_zone_geometry(f.input);
    if (!single) {
        geometry(zones, f.geometry, name + " zones");
        std::cout << name << ": complete independently frozen zone/shape geometry passed\n";
        require(zones.fallback_events == strings(field(f.source, "zone_events")),
                name + " ordered zone fallback events");
        for (const auto &[key, value] : field(f.source, "zone_quant").object_value)
            exact(static_cast<double>(zones.quantization_engagements[key]), value.number_value,
                  name + " zone quantization " + key);
    }
    if (mode == "--zones-only")
        return;
    auto result = (mode == "--production" || single) ? build_pcb_model(f.input)
                                                     : place_pcb_model(f.input, zones, f.stage);
    if (mode == "--production") {
        const auto fixtures = root / "native/tests/data/floorplan";
        const auto &docs = result.floorplan.documents;
        require(docs.svg == read(fixtures / (name + ".svg")),
                name + " live-solved floorplan SVG exact bytes");
        require(docs.markdown == read(fixtures / (name + ".md")),
                name + " live-solved floorplan Markdown exact bytes");
        auto fp = parse_json_file((fixtures / (name + ".json")).string());
        std::string ledger;
        for (const auto &entry : field(field(fp, "expected"), "ledger").array_value)
            ledger += string(entry, "text") + "\n";
        require(render_floorplan_ledger(result.floorplan.plan) == ledger,
                name + " live-solved floorplan ledger exact bytes");
    }
    for (const auto &[stage, snap] : f.snapshots.object_value) {
        const auto &actual = result.stages.at(stage);
        require(actual.size() == snap.object_value.size(), name + "/" + stage + " pose count");
        for (const auto &[r, pose] : snap.object_value) {
            require(actual.count(r), stage + " missing ref " + r);
            const auto &a = actual.at(r);
            const auto &p = pose.array_value;
            exact(std::get<0>(a), p[0].number_value, name + "/" + stage + "/" + r + " x");
            exact(std::get<1>(a), p[1].number_value, name + "/" + stage + "/" + r + " y");
            exact(std::get<2>(a), p[2].number_value, name + "/" + stage + "/" + r + " rotation");
            if (p.size() == 4)
                require(std::get<3>(a) == p[3].string_value, stage + "/" + r + " side");
        }
        std::cout << name << "/" << stage << ": all original Python poses passed\n";
    }
    auto expected = pcb_model_from_json(f.model, f.expected_pool);
    const auto &actual = result.model;
    require(actual.insts.size() == expected.insts.size(), name + " model instances");
    for (std::size_t k = 0; k < actual.insts.size(); ++k) {
        const auto &a = actual.insts[k];
        const auto &b = expected.insts[k];
        require(a.ref == b.ref && a.value == b.value && a.footprint == b.footprint &&
                    a.sheet == b.sheet && a.side == b.side && a.mirror == b.mirror &&
                    a.pad_nets == b.pad_nets,
                name + " complete instance metadata " + a.ref);
        require(a.mod->bytes == b.mod->bytes, name + " exact footprint bytes " + a.ref);
    }
    require(actual.placed == expected.placed && actual.n_top == expected.n_top &&
                actual.n_bottom == expected.n_bottom &&
                actual.net_numbers == expected.net_numbers &&
                actual.netclass_of == expected.netclass_of &&
                actual.stage_moves == expected.stage_moves,
            name + " complete model counts/nets/movement ledger");
    auto actual_json = pcb_model_json(actual), expected_json = pcb_model_json(expected);
    // Footprint identity is proven above by exact document bytes. Source pool
    // keys are provider-owned; compare all remaining model data without path
    // portability affecting the physical/model contract.
    for (auto *json : {&actual_json, &expected_json})
        for (auto &[key, value] : json->object_value)
            if (key == "insts")
                for (auto &inst : value.array_value)
                    inst.object_value.erase(
                        std::remove_if(inst.object_value.begin(), inst.object_value.end(),
                                       [](const auto &kv) { return kv.first == "mod_path"; }),
                        inst.object_value.end());
    same(actual_json, expected_json, name + "/complete model");
    if (!single) {
        auto fixture_policy = pcb_emit_policy(f.input.floorplan.project);
        // This immutable fixture predates the genuine part-model repair.
        // Current-policy model-only equivalence is checked independently by
        // pcb_emit_contracts; retain full historical geometry/byte checks here.
        fixture_policy.model_overrides.clear();
        auto emitted = render_pcb(actual, fixture_policy);
        require(emitted.pcb == read(root / "native/tests/data/pcb_emit" / (name + ".kicad_pcb")),
                name + " recomputed placement to rendered PCB exact bytes");
        require(render_pcb_design_rules(actual) ==
                    read(root / "native/tests/data/pcb_emit" / (name + ".kicad_dru")),
                name + " recomputed placement design rules exact bytes");
    }
    std::cout << name << ": complete model, copper, return-path metadata and escape plan passed\n";
}
} // namespace
int main(int argc, char **argv) {
    try {
        std::string mode = argc == 3 ? argv[2] : "--production";
        if (argc < 2 || argc > 3 ||
            (mode != "--zones-only" && mode != "--production" && mode != "--placed-only" &&
             mode != "--single"))
            throw std::runtime_error(
                "repo root [--zones-only|--production|--placed-only|--single]");
        for (const auto &name : {"carrier", "devkit_mini"}) {
            run(argv[1], name, mode);
            if (mode == "--production")
                run(argv[1], name, "--single");
        }
        std::cout << "PCB placement: " << checks << " assertions passed\n";
    } catch (const std::exception &e) {
        std::cerr << e.what() << "\n";
        return 1;
    }
}
