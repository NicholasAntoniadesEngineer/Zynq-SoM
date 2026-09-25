#pragma once
#include "schgen/pcb_placement.hpp"
#include <algorithm>
#include <fstream>

namespace placement_fixture {
using namespace schgen;
using J = JsonNode;
inline const J &field(const J &n, const std::string &key) {
    auto p = object_field(n, key);
    if (!p)
        throw std::runtime_error("missing fixture field " + key);
    return *p;
}
inline std::string string(const J &n, const std::string &key) { return field(n, key).string_value; }
inline double number(const J &n, const std::string &key) { return field(n, key).number_value; }
inline std::vector<std::string> strings(const J &n) {
    std::vector<std::string> v;
    for (const auto &s : n.array_value)
        v.push_back(s.string_value);
    return v;
}
inline FloorplanPoint point(const J &n) {
    return {n.array_value.at(0).number_value, n.array_value.at(1).number_value};
}
inline Box4 box(const J &n) {
    return {n.array_value.at(0).number_value, n.array_value.at(1).number_value,
            n.array_value.at(2).number_value, n.array_value.at(3).number_value};
}
inline std::string read(const std::filesystem::path &path) {
    std::ifstream f(path, std::ios::binary);
    if (!f)
        throw std::runtime_error("cannot read " + path.string());
    return {std::istreambuf_iterator<char>(f), {}};
}
inline SomOutline som(const J &n) {
    SomOutline s;
    s.w = number(n, "w");
    s.h = number(n, "h");
    for (const auto &j : field(n, "js").array_value)
        s.js.push_back({string(j, "ref"), number(j, "pcb_x"), number(j, "pcb_y"), number(j, "rot"),
                        number(j, "x"), number(j, "y"), number(j, "w"), number(j, "h")});
    return s;
}
struct Fixture {
    PcbPlacementInput input;
    FloorplanStage stage;
    J geometry, snapshots, model, source;
    PcbFootprintPool expected_pool;
};
inline Fixture load(const std::filesystem::path &root, const std::string &project) {
    Fixture f;
    auto base = root / "native/tests/data";
    auto fp = parse_json_file((base / "floorplan" / (project + ".json")).string());
    const auto &in = field(fp, "input");
    f.source = in;
    auto emit = parse_json_file((base / "pcb_emit" / (project + ".json")).string());
    f.model = field(emit, "model");
    auto trace = parse_json_file((base / "pcb_placement" / (project + "_placement.json")).string());
    f.snapshots = field(trace, "snapshots");
    f.geometry =
        field(parse_json_file((base / "pcb_placement" / (project + "_geometry.json")).string()),
              "geometry");
    auto authored =
        field(parse_json_file((base / "pcb_placement" / (project + "_authored.json")).string()),
              "authored");
    for (const auto &[path, bytes] : field(emit, "footprints").object_value)
        f.expected_pool[path] = pcb_check_footprint(path, bytes.string_value);
    auto &input = f.input;
    auto &floor = input.floorplan;
    for (const auto &s : field(in, "sheets").array_value)
        floor.sheets.push_back(decode_intermediate_circuit_ir(s));
    for (const auto &b : field(in, "bindings").array_value) {
        LinkPortBinding binding;
        binding.sheet = string(b, "sheet");
        binding.net = string(b, "net");
        binding.status = string(b, "status");
        binding.targets = strings(field(b, "targets"));
        binding.ptype.expect = string(field(b, "ptype"), "expect");
        floor.link.bindings.push_back(std::move(binding));
    }
    for (const auto &r : field(in, "regulators").array_value) {
        FloorplanRegulator reg;
        reg.sheet = string(r, "sheet");
        reg.ref = string(r, "ref");
        reg.value = string(r, "value");
        reg.kind = string(r, "kind");
        reg.vin = string(r, "vin");
        reg.vout = string(r, "vout");
        reg.i_out = number(r, "i_out");
        reg.eff = number(r, "eff");
        floor.regulators.push_back(std::move(reg));
    }
    floor.si_pairs = parse_signal_specs(field(in, "si_spec"));
    for (const auto &row : field(field(in, "compose"), "corridors").array_value) {
        const auto &a = row.array_value;
        floor.compose.corridors.push_back(
            {a[0].string_value,
             {a[1].number_value, a[2].number_value, a[3].number_value, a[4].number_value}});
    }
    for (const auto &[key, doc] : field(in, "footprints").object_value) {
        std::string source = string(doc, "source"), bytes = string(doc, "text");
        for (const auto &[path, other] : field(emit, "footprints").object_value)
            if (bytes == other.string_value) {
                source = path;
                break;
            }
        input.footprints[key] = pcb_check_footprint(source, bytes);
        floor.footprints[key] = {source, input.footprints.at(key)->document};
    }
    for (const auto &[id, key] : field(in, "footprint_of").object_value)
        floor.footprint_of[id] = key.string_value;
    for (const auto &[key, fp] : f.expected_pool)
        if (std::filesystem::path(key).filename() == "Fiducial_1mm_Mask2mm.kicad_mod") {
            input.footprints[key] = fp;
            floor.footprint_of["Fiducial:Fiducial_1mm_Mask2mm"] = key;
            floor.footprints[key] = {fp->source, fp->document};
        }
    for (const auto &[sheet, contract] : field(authored, "contracts").object_value)
        input.contracts[sheet] = contract;
    const auto &config = field(authored, "project"), placement = field(config, "placement");
    floor.project.raw = config;
    floor.project.name = string(config, "name");
    floor.project.wired_sheets = strings(field(placement, "wired_sheets"));
    floor.project.pilot_prox_sheets = strings(field(placement, "pilot_prox_sheets"));
    auto off = point(field(placement, "module_offset"));
    floor.project.module_offset = {off.first, off.second};
    floor.module_offset = point(field(in, "module_offset"));
    for (const auto &[k, v] : field(placement, "module_face_anchors").object_value)
        floor.project.module_face_anchors.push_back({k, v.string_value});
    floor.project.reg_band_prefixes = strings(field(placement, "reg_band_prefixes"));
    floor.project.escape = field(config, "escape");
    if (const auto *labels = object_field(config, "silk_labels")) {
        if (auto h = object_field(*labels, "headers"))
            for (const auto &[k, v] : h->object_value)
                floor.project.header_desc.push_back({k, v.string_value});
        if (auto s = object_field(*labels, "switches"))
            for (const auto &[k, v] : s->object_value)
                floor.project.switch_desc.push_back({k, v.string_value});
    }
    for (const auto &[k, v] : field(in, "sheet_index").object_value)
        floor.sheet_index.push_back({k, static_cast<int>(v.number_value)});
    floor.som = som(field(in, "som"));
    floor.som_source = string(field(in, "som"), "source");
    if (field(in, "spec").kind != JsonKind::Null)
        floor.spec = floorplan_spec_from_json(field(in, "spec"), "floorplan.json");
    for (const auto &[k, v] : field(in, "courtyard_dims").object_value)
        floor.courtyard_dims[k] = point(v);
    for (const auto &row : field(trace, "netlist").array_value) {
        std::vector<KicadNetlistPin> pins;
        for (const auto &p : row.array_value.at(1).array_value)
            pins.push_back({p.array_value[0].string_value, p.array_value[1].string_value});
        input.netlist.push_back({row.array_value[0].string_value, pins});
    }
    input.interface_bytes = read(root / project / "som_interface.json");
    input.som_interface = load_som_interface(root / project / "som_interface.json");
    auto mapping =
        link_mapping_from_json(parse_json_file((root / project / "som_mapping.json").string()));
    auto functions = mapping.function_map;
    for (const auto &entry : mapping.pudc_straps)
        functions[entry.first] = entry.second;
    input.function_map.assign(functions.begin(), functions.end());
    auto path = root / "parts/DF40C-100DS-0.4V_51/DF40C-100DS-0.4V_51.kicad_mod";
    auto receptacle = pcb_check_footprint(path.string(), read(path));
    for (const auto &[r, c] : input.som_interface.connectors) {
        (void)c;
        input.return_path_footprints[r] = receptacle;
    }
    const auto &expected = field(fp, "expected"), plan = field(expected, "plan");
    auto &p = f.stage.plan;
    p.som = som(field(plan, "som"));
    p.som_source = string(field(plan, "som"), "source");
    p.som_x = number(plan, "som_x");
    p.som_y = number(plan, "som_y");
    p.board_w = number(expected, "board_w");
    p.board_h = number(expected, "board_h");
    auto dec = point(field(plan, "dec_bank"));
    p.dec_count = static_cast<int>(dec.first);
    p.dec_radius = dec.second;
    for (auto key : {"edge_blocks", "interior_blocks"})
        for (const auto &b : field(plan, key).array_value) {
            FloorplanBlock block;
            block.name = string(b, "name");
            block.kind = string(b, "kind");
            block.x = number(b, "x");
            block.y = number(b, "y");
            block.w = number(b, "w");
            block.h = number(b, "h");
            block.shape_idx = static_cast<int>(number(b, "shape_idx"));
            block.side = string(b, "side");
            (std::string(key) == "edge_blocks" ? p.edge_blocks : p.interior_blocks)
                .push_back(block);
        }
    return f;
}
} // namespace placement_fixture
