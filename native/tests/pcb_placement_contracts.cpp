#include "pcb_placement_fixture.hpp"
#include "schgen/pcb_emit.hpp"
#include "pcb_placement_requirements.hpp"
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
        // The old devkit result remains an immutable NEGATIVE physical witness.
        // Do not require current production to reproduce that failure, nor the
        // carrier's former wrong-shape rejection from mismatched planning zones.
        if (const auto *model = object_field(variant, "model")) {
            auto pool=f.expected_pool;
            for(const auto& [path,bytes]:field(variant,"footprints").object_value)
                pool[path]=pcb_check_footprint(path,bytes.string_value);
            const auto original=pcb_model_from_json(*model,pool);
            require(!check_fanout(PcbCheckInput(original),0).ok,
                    "immutable top-preferred overlap witness must still fail the physical gate");
        }
    }
    auto zones = build_pcb_zone_geometry(f.input);
    if (!single && mode == "--zones-only") {
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
    // Historical coordinates are valid renderer operands, not an optimisation
    // target. Preserve the immutable emitter oracle separately below.
    placement_requirements_test::structure(f.input,zones,result,require);
    const auto expected=pcb_model_from_json(f.model,f.expected_pool);
    placement_requirements_test::physical(f.input,result.model,require);
    require(result.model.netclass_of==expected.netclass_of,name+" source net-class assignment");
    same(field(pcb_model_json(result.model),"classes"),field(f.model,"classes"),name+" source impedance classes");
    const auto check_structure=[&](auto mutate,const std::string& why) {
        auto changed=result;mutate(changed);
        bool rejected=false;
        try {placement_requirements_test::structure(f.input,zones,changed,require);}
        catch(const std::exception&) {rejected=true;}
        require(rejected,"mutation escaped: "+why);
    };
    check_structure([](auto& r){r.model.insts.pop_back();},"missing instance");
    check_structure([](auto& r){r.model.insts.push_back(r.model.insts.front());},"duplicate instance");
    check_structure([](auto& r){r.model.insts.front().x=-100.;},"off-board pose");
    check_structure([](auto& r){++r.model.n_top;},"incorrect side population");
    require(!result.floorplan.plan.interior_blocks.empty(),"registered-shape mutation witness");
    check_structure([](auto& r){r.floorplan.plan.interior_blocks.front().shape_idx=1000000;},
                    "unregistered shape index");
    check_structure([](auto& r){r.model.insts.front().value="WRONG";},"part value");
    check_structure([](auto& r){r.model.insts.front().mirror=!r.model.insts.front().mirror;},"mirror identity");
    check_structure([](auto& r){r.stages.at("breathe").erase(r.stages.at("breathe").begin());},"missing stage reference");
    check_structure([](auto& r){++r.model.stage_moves.at("breathe");},"incorrect movement ledger");
    check_structure([](auto& r){std::get<0>(r.stages.at("instantiate").begin()->second)+=1;},"movement in frozen stage");
    if(!single) {
        auto wrong=result.model;
        const auto connector=std::find_if(wrong.insts.begin(),wrong.insts.end(),[](const auto& p) {
            return p.value=="TYPE-C-31-M-12";
        });
        require(connector!=wrong.insts.end(),"mechanical orientation negative witness");
        connector->rotation+=180;
        require(!check_placement_mech(PcbCheckInput(wrong)).ok,"reversed connector must fail physical acceptance");
        wrong=result.model;wrong.copper.clear();
        bool rejected=false;
        try {placement_requirements_test::physical(f.input,wrong,require);}
        catch(const std::runtime_error&) {rejected=true;}
        require(rejected,"missing return copper must fail physical acceptance");
    }
    if(!single) {
        auto fixture_policy=pcb_emit_policy(f.input.floorplan.project);
        fixture_policy.model_overrides.clear();
        require(render_pcb(expected,fixture_policy).pcb==
                    read(root/"native/tests/data/pcb_emit"/(name+".kicad_pcb")),
                name+" immutable model still renders exact historical PCB bytes");
        require(render_pcb_design_rules(expected)==
                    read(root/"native/tests/data/pcb_emit"/(name+".kicad_dru")),
                name+" immutable design-rule formatter bytes");
    }
    // Repetition tests same-input reproducibility, not equality to a different
    // algorithm/version/seed. Emitted current PCB and full model must agree.
    const auto repeated=(mode=="--production"||single)?build_pcb_model(f.input):
        place_pcb_model(f.input,zones,f.stage);
    same(pcb_model_json(result.model),pcb_model_json(repeated.model),name+" same-input full model");
    require(result.stages==repeated.stages,name+" same-input stage sequence");
    same(floorplan_plan_json(result.floorplan.plan),floorplan_plan_json(repeated.floorplan.plan),
         name+" same-input floorplan and complete execution ledger");
    require(result.placement_accounting.quantization_engagements==repeated.placement_accounting.quantization_engagements&&
            result.placement_accounting.fallback_events==repeated.placement_accounting.fallback_events&&
            result.zone_accounting.quantization_engagements==repeated.zone_accounting.quantization_engagements&&
            result.zone_accounting.fallback_events==repeated.zone_accounting.fallback_events,
            name+" same-input actual placement/zone work");
    require(result.floorplan.documents.svg==repeated.floorplan.documents.svg&&
            result.floorplan.documents.markdown==repeated.floorplan.documents.markdown,
            name+" same-input generated floorplan documents");
    const auto policy=pcb_emit_policy(f.input.floorplan.project);
    require(render_pcb(result.model,policy).pcb==render_pcb(repeated.model,policy).pcb,
            name+" same-input emitted PCB");
    std::cout<<name<<(single?" top-preferred":" two-sided")
        <<": source identity, stage transport, repeatability and scoped physical acceptance PASS\n";
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
