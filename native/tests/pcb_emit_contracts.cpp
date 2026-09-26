#include "schgen/atomic_file.hpp"
#include "schgen/pcb_emit.hpp"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <stdexcept>

namespace fs = std::filesystem;
using namespace schgen;
namespace {
int checks = 0;
void require(bool ok, const std::string &message) {
    ++checks;
    if (!ok)
        throw std::runtime_error(message);
}
std::string read(const fs::path &path) {
    std::ifstream f(path, std::ios::binary);
    if (!f)
        throw std::runtime_error("cannot read " + path.string());
    return {std::istreambuf_iterator<char>(f), {}};
}
void fixture_integrity(const fs::path &fixtures) {
    std::ifstream manifest(fixtures / "SHA256SUMS");
    require(static_cast<bool>(manifest), "fixture hash manifest exists");
    std::string hash, filename;
    int count = 0;
    while (manifest >> hash >> filename) {
        require(pcb_sha256(read(fixtures / filename)) == hash,
                filename + ": immutable fixture hash");
        ++count;
    }
    require(count == 11, "all frozen fixture files are pinned");
}
const JsonNode &field(const JsonNode &n, const std::string &k) {
    auto p = object_field(n, k);
    if (!p)
        throw std::runtime_error("missing fixture " + k);
    return *p;
}
bool same_json(const JsonNode &a, const JsonNode &b) {
    if (a.kind != b.kind)
        return false;
    switch (a.kind) {
    case JsonKind::Null:
        return true;
    case JsonKind::Bool:
        return a.bool_value == b.bool_value;
    case JsonKind::Number:
        return a.number_value == b.number_value;
    case JsonKind::String:
        return a.string_value == b.string_value;
    case JsonKind::Array:
        if (a.array_value.size() != b.array_value.size())
            return false;
        for (std::size_t i = 0; i < a.array_value.size(); ++i)
            if (!same_json(a.array_value[i], b.array_value[i]))
                return false;
        return true;
    case JsonKind::Object:
        if (a.object_value.size() != b.object_value.size())
            return false;
        for (const auto &[k, v] : a.object_value) {
            auto other = object_field(b, k);
            if (!other || !same_json(v, *other))
                return false;
        }
        return true;
    }
    return false;
}
template <class F> void rejects(F &&f, const std::string &message) {
    try {
        f();
    } catch (const std::exception &e) {
        require(std::string(e.what()).find(message) != std::string::npos,
                "wrong rejection: " + std::string(e.what()));
        return;
    }
    throw std::runtime_error("expected rejection: " + message);
}
void equal(const std::string &got, const std::string &want, const std::string &context,
           const fs::path &artifacts) {
    if (got != want) {
        fs::create_directories(artifacts);
        write_atomic_file((artifacts / "actual.txt").string(), {got.begin(), got.end()});
        write_atomic_file((artifacts / "expected.txt").string(), {want.begin(), want.end()});
        std::size_t n = 0;
        while (n < std::min(got.size(), want.size()) && got[n] == want[n])
            ++n;
        throw std::runtime_error(context + ": byte difference at " + std::to_string(n) +
                                 "; saved actual/expected in " + artifacts.string());
    }
    ++checks;
}
PcbFootprintPool footprints(const JsonNode &n) {
    PcbFootprintPool pool;
    for (const auto &[k, v] : n.object_value)
        pool[k] = pcb_check_footprint(k, v.string_value);
    return pool;
}
PcbEmitPolicy policy(const JsonNode &n) {
    auto p = default_pcb_emit_policy();
    for (const auto &[k, v] : field(n, "header_descriptions").object_value)
        p.header_descriptions.emplace_back(k, v.string_value);
    for (const auto &[k, v] : field(n, "switch_descriptions").object_value)
        p.switch_descriptions.emplace_back(k, v.string_value);
    return p;
}
void project(const fs::path &fixtures, const fs::path &output, const std::string &name) {
    auto raw = parse_json_file((fixtures / (name + ".json")).string());
    auto pool = footprints(field(raw, "footprints"));
    auto m = pcb_model_from_json(field(raw, "model"), pool);
    auto p = policy(raw);
    auto result = render_pcb(m, p);
    equal(result.pcb, read(fixtures / (name + ".kicad_pcb")), name + " exact board", output);
    auto repaired_policy = p;
    repaired_policy.model_overrides = project_pcb_model_overrides();
    const auto repaired = render_pcb(m, repaired_policy);
    if (name == "carrier") {
        auto expected = result.document;
        int replaced = 0;
        const auto replace_model = [&](const auto& self, Sexpr& node) -> void {
            auto* list = std::get_if<SexprList>(&node.v);
            if (!list) return;
            if (list->size() > 1 && std::holds_alternative<Sexpr::Sym>((*list)[0].v) &&
                std::get<Sexpr::Sym>((*list)[0].v).name == "model" &&
                std::holds_alternative<std::string>((*list)[1].v) &&
                std::get<std::string>((*list)[1].v) == "${KICAD10_3DMODEL_DIR}/Package_DFN_QFN.3dshapes/WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm.step") {
                node = sexpr_loads(R"((model "${KIPRJMOD}/../parts/FUSB302BMPX/FUSB302BMPX.wrl" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 90))))");
                ++replaced;
                return;
            }
            for (auto& child : *list) self(self, child);
        };
        replace_model(replace_model, expected);
        require(replaced == 1, "independent model-only correction has exactly one target");
        equal(sexpr_dumps(repaired.document), sexpr_dumps(expected), name + " repair preserves all copper and other models", output);
        repaired_policy.model_overrides.front().value = "different-part";
        equal(render_pcb(m, repaired_policy).pcb, result.pcb, name + " model repair is part-specific", output);
        repaired_policy.model_overrides = project_pcb_model_overrides();
        repaired_policy.model_overrides.front().footprint = "different-footprint";
        equal(render_pcb(m, repaired_policy).pcb, result.pcb, name + " model repair is footprint-specific", output);
    } else {
        equal(repaired.pcb, result.pcb, name + " no irrelevant model repair", output);
    }
    auto restored = pcb_model_from_json(pcb_model_json(m), pool);
    equal(render_pcb(restored, p).pcb, result.pcb, name + " transport preserves emission", output);
    const auto transported = pcb_model_json(m);
    for (const auto &key :
         {"escape_plan", "escape_meta", "stage_moves", "copper", "insts", "classes", "deferred"})
        require(same_json(field(transported, key), field(field(raw, "model"), key)),
                name + " transport preserves " + key);
    require(result.diagnostics.size() == field(raw, "diagnostics").array_value.size(),
            name + " diagnostics count");
    for (std::size_t i = 0; i < result.diagnostics.size(); ++i)
        equal(result.diagnostics[i], field(raw, "diagnostics").array_value[i].string_value,
              name + " diagnostic", output);
    std::size_t fallbacks = 0;
    for (const auto &key : result.fallback_events) {
        require(key == "thermal_via_lattice", "registered fallback only");
        ++fallbacks;
    }
    require(fallbacks == static_cast<std::size_t>(
                             field(field(raw, "fallbacks"), "thermal_via_lattice").number_value),
            name + " fallback engagement count");
    auto original = field(raw, "original_project").string_value;
    auto path = output / (name + ".kicad_pro");
    write_atomic_file(path.string(), {original.begin(), original.end()});
    auto prior = read_pcb_project(path);
    equal(render_pcb_project(m, "Zynq_Carrier.kicad_pro", &prior, p),
          read(fixtures / (name + ".kicad_pro")), name + " exact project", output);
    equal(render_pcb_design_rules(m, p), read(fixtures / (name + ".kicad_dru")),
          name + " exact rules", output);
    write_pcb_project(m, path, p);
    equal(read(path), read(fixtures / (name + ".kicad_pro")), name + " project atomic write",
          output);
    write_pcb_design_rules(m, output / (name + ".dru"), p);
    equal(read(output / (name + ".dru")), read(fixtures / (name + ".kicad_dru")),
          name + " rules atomic write", output);
    write_pcb(m, output / (name + ".pcb"), p);
    equal(read(output / (name + ".pcb")), result.pcb, name + " atomic write", output);
    require(!m.insts.empty(), name + " real source inventory");
    auto before = sexpr_dumps(m.insts.front().mod->document);
    auto changed = m;
    changed.insts.front().x += .125;
    require(render_pcb(changed, p).pcb != result.pcb, name + " fresh pose mutation changes board");
    equal(sexpr_dumps(m.insts.front().mod->document), before, name + " immutable footprint source",
          output);
    std::cout << name << ": exact generated PCB/project/rules PASS\n";
}
void mutations(const fs::path &fixtures, const fs::path &output, const std::string &filename) {
    auto raw = parse_json_file((fixtures / filename).string());
    auto pool = footprints(field(raw, "footprints"));
    for (const auto &row : field(raw, "cases").array_value) {
        auto name = field(row, "name").string_value;
        auto m = pcb_model_from_json(field(row, "model"), pool);
        auto p = policy(row);
        auto result = render_pcb(m, p);
        equal(result.pcb, field(row, "pcb").string_value, name + " board", output);
        auto restored = pcb_model_from_json(pcb_model_json(m), pool);
        equal(render_pcb(restored, p).pcb, result.pcb, name + " model round trip", output);
        auto stats = field(row, "stats");
        require(result.hidden_bottom_references == field(stats, "hidden").number_value,
                name + " hidden references");
        require(result.moved_references == field(stats, "moved").number_value,
                name + " moved references");
        require(result.diagnostics.size() == field(row, "diagnostics").array_value.size(),
                name + " diagnostic count");
        for (std::size_t i = 0; i < result.diagnostics.size(); ++i)
            equal(result.diagnostics[i], field(row, "diagnostics").array_value[i].string_value,
                  name + " diagnostic", output);
        require(result.fallback_events.size() ==
                    field(field(row, "fallbacks"), "thermal_via_lattice").number_value,
                name + " lattice events");
        std::optional<PcbProjectDocument> prior;
        if (field(row, "original_project").kind != JsonKind::Null) {
            auto text = field(row, "original_project").string_value;
            auto path = output / (name + ".json");
            write_atomic_file(path.string(), {text.begin(), text.end()});
            prior = read_pcb_project(path);
        }
        equal(render_pcb_project(m, name + ".kicad_pro", prior ? &*prior : nullptr, p),
              field(row, "project").string_value, name + " project", output);
        equal(render_pcb_design_rules(m, p), field(row, "rules").string_value, name + " rules",
              output);
    }
    std::cout << field(raw, "cases").array_value.size() << " frozen emission mutation cases PASS\n";
}
void boundaries(const fs::path &fixtures, const fs::path &output) {
    auto raw = parse_json_file((fixtures / "devkit_mini.json").string());
    auto pool = footprints(field(raw, "footprints"));
    auto model = pcb_model_from_json(field(raw, "model"), pool);
    rejects([&] { pcb_model_from_json(field(raw, "model"), {}); }, "unresolved footprint snapshot");
    auto bad = model;
    bad.board_w = 0;
    rejects([&] { render_pcb(bad); }, "outline dimensions");
    const auto sentinel = output / "preserve-on-failure.pcb";
    write_atomic_file(sentinel.string(), {'k', 'e', 'e', 'p'});
    rejects([&] { write_pcb(bad, sentinel); }, "outline dimensions");
    equal(read(sentinel), "keep", "render failure preserves existing file", output);
    bad = model;
    bad.origin_x = std::numeric_limits<double>::infinity();
    rejects([&] { render_pcb(bad); }, "origin must be finite");
    bad = model;
    bad.insts.front().x = std::numeric_limits<double>::quiet_NaN();
    rejects([&] { render_pcb(bad); }, "nonfinite placement");
    bad = model;
    bad.insts.front().side = "sideways";
    rejects([&] { render_pcb(bad); }, "invalid footprint side");
    bad = model;
    bad.insts.front().mirror = true;
    bad.insts.front().side = "top";
    rejects([&] { render_pcb(bad); }, "mirror=True demands");
    bad = model;
    bad.insts.front().mod.reset();
    rejects([&] { render_pcb(bad); }, "unresolved");
    bad = model;
    PcbCheckCopper copper;
    copper.kind = "arc";
    bad.copper.push_back(copper);
    rejects([&] { render_pcb(bad); }, "unknown escape copper kind");
    bad = model;
    bad.copper_locks[bad.copper.size()] = false;
    rejects([&] { render_pcb(bad); }, "lock must refer to a via");
    bad = model;
    bad.copper.front().x = std::numeric_limits<double>::infinity();
    rejects([&] { render_pcb(bad); }, "copper geometry must be finite");
    auto p = default_pcb_emit_policy();
    p.thermal_lattice_pitch = 0;
    rejects([&] { render_pcb(model, p); }, "lattice pitch");
    auto transport = pcb_model_json(model);
    for (auto &[k, v] : transport.object_value)
        if (k == "escape_meta")
            v.object_value.erase(std::remove_if(v.object_value.begin(), v.object_value.end(),
                                                [](const auto &field) {
                                                    return field.first == "som_interface_sha256";
                                                }),
                                 v.object_value.end());
    auto missing_hash = pcb_model_from_json(transport, pool);
    require(missing_hash.escape_interface_sha256 && missing_hash.escape_interface_sha256->empty(),
            "missing hash remains distinguishable from absent metadata");
    require(same_json(field(pcb_model_json(missing_hash), "escape_meta"),
                      field(transport, "escape_meta")),
            "diagnostic metadata missing its hash round trips without invented fields");
    for (auto &[k, v] : transport.object_value)
        if (k == "placed")
            v.number_value = .5;
    rejects([&] { pcb_model_from_json(transport, pool); }, "invalid integer");
    ProjectConfig config;
    config.header_desc = {{"J_CUSTOM", "Custom header"}};
    config.switch_desc = {{"SW_CUSTOM", "Custom switch"}};
    auto configured = pcb_emit_policy(config);
    require(configured.header_descriptions == config.header_desc &&
                configured.switch_descriptions == config.switch_desc,
            "project-specific description policy");
    std::cout << "PCB emission boundary/error contracts PASS\n";
}
} // namespace
int main(int argc, char **argv) {
    try {
        if (argc != 3)
            throw std::runtime_error("usage: pcb_emit_contracts FIXTURES TEMP_OUTPUT");
        fs::path fixtures = argv[1], output = argv[2];
        fs::create_directories(output);
        fixture_integrity(fixtures);
        project(fixtures, output, "devkit_mini");
        project(fixtures, output, "carrier");
        mutations(fixtures, output, "mutations.json");
        mutations(fixtures, output, "edge_cases.json");
        mutations(fixtures, output, "unicode_strip.json");
        boundaries(fixtures, output);
        std::cout << "PCB emission: " << checks << " checks passed\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
