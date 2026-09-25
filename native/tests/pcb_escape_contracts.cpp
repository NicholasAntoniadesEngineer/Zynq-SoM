#include "schgen/occupancy.hpp"
#include "schgen/pcb_escape.hpp"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <sstream>

namespace {
using namespace schgen;
namespace fs = std::filesystem;
std::size_t checks = 0;
void require(bool pass, const std::string &why) {
    ++checks;
    if (!pass)
        throw std::runtime_error(why);
}
std::string read(const fs::path &p) {
    std::ifstream f(p, std::ios::binary);
    if (!f)
        throw std::runtime_error("cannot read fixture " + p.string());
    return {std::istreambuf_iterator<char>(f), {}};
}
const JsonNode &field(const JsonNode &n, const std::string &key) {
    auto p = object_field(n, key);
    if (!p)
        throw std::runtime_error("fixture field missing " + key);
    return *p;
}
std::string string(const JsonNode &n, const std::string &k) { return field(n, k).string_value; }
double number(const JsonNode &n, const std::string &k) { return field(n, k).number_value; }
Box4 box(const JsonNode &n) {
    const auto &a = n.array_value;
    return {a.at(0).number_value, a.at(1).number_value, a.at(2).number_value, a.at(3).number_value};
}
void exact(const std::string &a, const std::string &b, const std::string &why) {
    ++checks;
    if (a != b) {
        std::size_t i = 0;
        while (i < a.size() && i < b.size() && a[i] == b[i])
            ++i;
        throw std::runtime_error(why + " byte " + std::to_string(i) +
                                 "\nactual: " + a.substr(i, 200) + "\nexpect: " + b.substr(i, 200));
    }
}
void json_equal(const JsonNode &a, const JsonNode &b, const std::string &path) {
    require(a.kind == b.kind, path + " type");
    if (a.kind == JsonKind::Object) {
        require(a.object_value.size() == b.object_value.size(), path + " size");
        for (const auto &[key, v] : b.object_value)
            json_equal(field(a, key), v, path + "/" + key);
    } else if (a.kind == JsonKind::Array) {
        require(a.array_value.size() == b.array_value.size(), path + " size");
        for (std::size_t i = 0; i < b.array_value.size(); ++i)
            json_equal(a.array_value[i], b.array_value[i], path + "/" + std::to_string(i));
    } else if (a.kind == JsonKind::String)
        exact(a.string_value, b.string_value, path);
    else if (a.kind == JsonKind::Number)
        require(a.number_value == b.number_value,
                path + " numeric: " + std::to_string(a.number_value) +
                    " != " + std::to_string(b.number_value));
    else if (a.kind == JsonKind::Bool)
        require(a.bool_value == b.bool_value, path + " boolean");
}
template <class F> void rejects(F fn, const std::string &expected) {
    bool threw = false;
    try {
        fn();
    } catch (const PcbEscapeError &e) {
        threw = true;
        require(std::string(e.what()).find(expected) != std::string::npos,
                "wrong rejection: " + std::string(e.what()) + " wanted " + expected);
    }
    require(threw, "missing rejection: " + expected);
}
struct Fixture {
    JsonNode raw;
    PcbModel model;
    ReturnPathResult v1;
    std::string interface_bytes;
    ProjectStrings functions;
    std::map<std::string, PcbEscapeSignalClass> triage;
    std::size_t j1 = 0, j2 = 0, j3 = 0;
    PcbEscapeInput input() const { return {model, v1, triage, interface_bytes}; }
};
PcbCheckFootprintPtr pad_footprint(double w, double h, const std::string &type = "smd") {
    return pcb_check_footprint("mutation.kicad_mod", "(footprint \"mutation\" (pad \"1\" " + type +
                                                         " rect (at 0 0) (size " +
                                                         sexpr_fmt_num(w) + " " + sexpr_fmt_num(h) +
                                                         ") (drill 0.3)))");
}
void obstacle(Fixture &f, const PcbCheckInstance &conn, double u, double v, double w, double h,
              const std::string &side = "bottom", const std::string &type = "smd",
              const std::string &net = "FOREIGN", const std::string &sheet = "mutant") {
    PcbCheckInstance i;
    i.ref = "MUT" + std::to_string(f.model.insts.size());
    i.sheet = sheet;
    i.side = side;
    i.mod = pad_footprint(w, h, type);
    i.rotation = conn.rotation;
    std::tie(i.x, i.y) = uv_to_board(conn.x, conn.y, u, v, conn.rotation);
    i.pad_nets["1"] = {net.empty() ? 0 : 8000, net};
    f.model.insts.push_back(std::move(i));
}
Fixture load(const fs::path &root, const std::string &name) {
    Fixture f;
    f.raw = parse_json_file((root / "native/tests/data/pcb_emit" / (name + ".json")).string());
    const auto &m = field(f.raw, "model");
    f.model.board_w = number(m, "board_w");
    f.model.board_h = number(m, "board_h");
    f.model.som_keepout = box(field(m, "som_keepout"));
    f.model.som_core = box(field(m, "som_core"));
    std::map<std::string, PcbCheckFootprintPtr> pool;
    for (const auto &[path, bytes] : field(f.raw, "footprints").object_value)
        pool[path] = pcb_check_footprint(path, bytes.string_value);
    for (const auto &r : field(m, "insts").array_value) {
        PcbCheckInstance i;
        i.ref = string(r, "ref");
        i.value = string(r, "value");
        i.sheet = string(r, "sheet");
        i.footprint = string(r, "footprint");
        i.side = string(r, "side");
        i.x = number(r, "x");
        i.y = number(r, "y");
        i.rotation = number(r, "rotation");
        i.mirror = field(r, "mirror").bool_value;
        i.mod = pool.at(string(r, "mod_path"));
        for (const auto &[pad, p] : field(r, "pad_nets").object_value)
            i.pad_nets[pad] = {static_cast<int>(p.array_value.at(0).number_value),
                               p.array_value.at(1).string_value};
        if (i.sheet == "som_j1")
            f.j1 = f.model.insts.size();
        if (i.sheet == "som_j2")
            f.j2 = f.model.insts.size();
        if (i.sheet == "som_j3")
            f.j3 = f.model.insts.size();
        f.model.insts.push_back(std::move(i));
    }
    for (const auto &[net, n] : field(m, "net_numbers").object_value)
        f.model.net_numbers[net] = static_cast<int>(n.number_value);
    for (const auto &[net, n] : field(m, "netclass_of").object_value)
        f.model.netclass_of[net] = n.string_value;
    for (const auto &[cls, g] : field(m, "classes").object_value) {
        if (g.kind == JsonKind::Null)
            f.model.classes[cls] = std::nullopt;
        else
            f.model.classes[cls] = DifferentialGeometry{static_cast<int>(number(g, "impedance")),
                                                        number(g, "width_mm"), number(g, "gap_mm"),
                                                        string(g, "source")};
    }
    f.interface_bytes = read(root / name / "som_interface.json");
    auto iface = load_som_interface(root / name / "som_interface.json");
    auto mapping =
        link_mapping_from_json(parse_json_file((root / name / "som_mapping.json").string()));
    auto functions = mapping.function_map;
    for (const auto &p : mapping.pudc_straps)
        functions[p.first] = p.second;
    f.functions.assign(functions.begin(), functions.end());
    const auto path = root / "parts/DF40C-100DS-0.4V_51/DF40C-100DS-0.4V_51.kicad_mod";
    const auto fp = pcb_check_footprint(path.string(), read(path));
    std::map<std::string, PcbCheckFootprintPtr> mods;
    for (const auto &[ref, conn] : iface.connectors) {
        (void)conn;
        mods[ref] = fp;
    }
    f.v1 = check_return_path(iface, mods);
    for (auto idx : {f.j1, f.j2, f.j3})
        for (const auto &[pad, n] : f.model.insts[idx].pad_nets) {
            (void)pad;
            if (!n.second.empty() && pcb_classify_net(n.second) == "SIGNAL")
                f.triage[n.second] = classify_pcb_escape_signal(n.second, f.functions);
        }
    for (const auto &v : f.v1.violations)
        f.triage[v.net] = classify_pcb_escape_signal(v.net, f.functions);
    return f;
}
void baseline(const fs::path &root, const std::string &name) {
    auto f = load(root, name);
    const auto &expected = field(f.raw, "model");
    auto input = f.input();
    require(!f.v1.ok && f.v1.n_pairs == 69 && f.v1.n_pair_contacts == 138 && f.v1.n_fail() == 29,
            "v1 failure must stay 69/138/29");
    auto copper = build_pcb_escape_copper(input);
    auto plan = build_pcb_escape_plan(input);
    json_equal(copper.copper_json(), field(expected, "copper"), name + "/copper");
    json_equal(copper.meta.json(), field(expected, "escape_meta"), name + "/meta");
    json_equal(plan.json(), field(expected, "escape_plan"), name + "/plan");
    exact(render_pcb_escape_block(plan, copper.meta),
          read(root / "native/tests/data/pcb_escape" / (name + "_escape_block.json")),
          name + " exact escape block");
    auto snapshot = render_pcb_escape_block(plan, copper.meta);
    auto good = f.model;
    good.escape_plan = plan.for_checks();
    good.copper = copper.copper;
    good.escape_interface_sha256 = copper.meta.som_interface_sha256;
    auto config = parse_json_file((root / name / "project.json").string());
    require(check_escape_lanes(good, pcb_escape_population_from_json(field(config, "escape")),
                               f.interface_bytes)
                .ok,
            "generated lane plan gates");
    std::map<std::string, ReturnStitchClass> cl;
    for (const auto &[net, t] : f.triage)
        cl[net] = {t.rank(), t.klass, t.function};
    require(check_return_stitch(PcbCheckInput(good), f.v1, cl, f.interface_bytes).ok,
            "generated copper return-stitch gate");
    // Exact frozen inputs retained; caller mutation cannot affect a prepared invocation.
    f.model.net_numbers.erase("GND");
    json_equal(build_pcb_escape_copper(input).copper_json(), copper.copper_json(),
               name + "/immutable snapshot");
    rejects([&] { build_pcb_escape_copper(f.input()); }, "refusing to emit net-0 copper");
    exact(render_pcb_escape_block(plan, copper.meta), snapshot,
          "render never reruns mutated caller");
    std::cout << name << ": complete frozen copper/meta/plan and exact escape_block bytes passed\n";
}
void real_mutations(const fs::path &root, const std::string &name) {
    const auto base = load(root, name);
    auto cases =
        parse_json_file((root / "native/tests/data/pcb_escape/policy_mutations.json").string());
    for (const auto &test : cases.array_value) {
        auto f = base;
        const auto id = string(test, "mutation");
        auto conn = f.model.insts[f.j1];
        if (id == "gnd_absent")
            f.model.net_numbers.erase("GND");
        else if (id == "gnd_zero")
            f.model.net_numbers["GND"] = 0;
        else if (id == "missing_j3")
            f.model.insts[f.j3].sheet = "unrelated";
        else if (id == "missing_keepout")
            f.model.som_keepout.reset();
        else if (id == "plane_uncovered")
            f.model.board_w = 1;
        else if (id == "isolation_intrusion") {
            obstacle(f, conn, 0, 0, 1, 1);
            f.model.insts.back().value = "HX5008-mutant";
        } else if (id == "foreign_barrel" || id == "no_net_barrel" || id == "npth_barrel") {
            obstacle(f, conn, 15, 0, .5, .5, "top",
                     id == "npth_barrel" ? "np_thru_hole" : "thru_hole",
                     id == "no_net_barrel" ? "" : "FOREIGN");
            f.model.insts.back().ref = "MUT";
        } else if (id == "blocked_bottom" || id == "blocked_front")
            obstacle(f, conn, 0, 0, 40, 10, id == "blocked_bottom" ? "bottom" : "top");
        else if (id == "no_ground_attach")
            for (auto &[pad, n] : f.model.insts[f.j1].pad_nets) {
                (void)pad;
                if (n.second == "GND")
                    n = {0, ""};
            }
        else if (id == "missing_violation_pad")
            f.v1.violations.front().pad = "no-pad";
        else if (id == "missing_violation_connector")
            f.v1.violations.front().ref = "J9";
        else if (id == "missing_triage")
            f.triage.erase(f.v1.violations.front().net);
        else if (id == "unknown_class")
            f.triage.at(f.v1.violations.front().net).klass = "UNKNOWN";
        // Keep this isolated from actual board copper: +100 lands on carrier
        // motor_sense and correctly fails the earlier ladder-clearance gate.
        else if (id == "off_region_connector")
            f.model.insts[f.j1].x += 1000;
        else if (id == "missing_dp_geometry")
            for (auto &[cls, g] : f.model.classes) {
                if (cls.rfind("DP", 0) == 0)
                    g.reset();
            }
        else if (id == "unknown_signal")
            f.model.insts[f.j1].pad_nets["1"] = {8000, "UNRESEARCHED_SIGNAL"};
        else if (id == "unresolved_connector")
            f.model.insts[f.j1].mod.reset();
        else
            throw std::runtime_error("unimplemented mutation fixture " + id);
        rejects(
            [&] {
                if (string(test, "stage") == "copper")
                    build_pcb_escape_copper(f.input());
                else
                    build_pcb_escape_plan(f.input());
            },
            string(test, "error"));
    }
    // A real connector's entire bottom channel is narrowed analytically. With
    // rule .15 + margin .10, annulus radii .225/.200/.175 need .475/.450/.425.
    // The independent .460/.438 inner boundaries therefore force rungs 2/3.
    for (const auto &[half_gap, diameter, drill] :
         std::vector<std::tuple<double, double, double>>{{.46, .4, .25}, {.438, .35, .2}}) {
        auto f = base;
        auto conn = f.model.insts[f.j1];
        for (int s : {-1, 1})
            obstacle(f, conn, 0, s * (half_gap + 5), 40, 10);
        auto hit = build_pcb_escape_copper(f.input());
        for (const auto &c : hit.copper)
            if (c.conn == "J1" && c.kind == "via")
                require(c.size == diameter && c.drill == drill,
                        "narrowed real channel selects exact permitted via rung");
    }
    {
        auto f = base;
        auto conn = f.model.insts[f.j1];
        for (int s : {-1, 1})
            obstacle(f, conn, 0, s * (.40 + 5), 40, 10);
        rejects([&] { build_pcb_escape_copper(f.input()); }, "never a threshold relax");
    }
    {
        auto f = base;
        auto conn = f.model.insts[f.j1];
        obstacle(f, conn, 15, 0, .5, .5, "top", "thru_hole", "GND");
        require(!build_pcb_escape_copper(f.input()).copper.empty(),
                "ground barrel is not foreign plane perforation");
    }
    {
        auto f = base;
        auto conn = f.model.insts[f.j1];
        obstacle(f, conn, 15, 0, .5, .5, "top", "np_thru_hole", "");
        f.model.insts.back().x = 1;
        require(!build_pcb_escape_copper(f.input()).copper.empty(),
                "foreign barrel outside region allowed");
    }
    {
        auto f = base;
        auto conn = f.model.insts[f.j1];
        obstacle(f, conn, 0, 0, 1, 1);
        f.model.insts.back().mod.reset();
        f.model.insts.back().side = "top";
        require(!build_pcb_escape_plan(f.input()).lanes.empty(),
                "plan ignores unrelated unresolved geometry");
    }
    {
        auto f = base;
        f.v1.violations.clear();
        f.v1.ok = true;
        auto c = build_pcb_escape_copper(f.input());
        require(c.copper.empty() && c.meta.vias.empty() && c.meta.worst_cover_mm == 0,
                "no remediation without actual v1 violations");
    }
    {
        auto f = base;
        const auto input = f.input();
        auto p = build_pcb_escape_plan(input);
        f.interface_bytes += ' ';
        auto changed = build_pcb_escape_plan(f.input());
        require(p.content_key != changed.content_key, "interface bytes invalidate key");
        f = base;
        f.model.insts[f.j1].rotation = 90;
        changed = build_pcb_escape_plan(f.input());
        require(p.content_key != changed.content_key, "rotation invalidates key");
        const auto &a = p.lanes.at("J1").front();
        const auto &b = changed.lanes.at("J1").front();
        const auto &inst = base.model.insts[base.j1];
        auto uv = board_to_uv(inst.x, inst.y, a.port_x, a.port_y, inst.rotation);
        auto xy = uv_to_board(inst.x, inst.y, uv.first, uv.second, 90);
        require(b.port_x == py_round(xy.first, 4) && b.port_y == py_round(xy.second, 4),
                "rotated real connector recomputes ports");
    }
    {
        auto f = base;
        const auto old = build_pcb_escape_plan(f.input());
        f.model.insts[f.j1].mod = pcb_check_footprint(f.model.insts[f.j1].mod->source,
                                                      f.model.insts[f.j1].mod->bytes + "\n");
        auto fresh = build_pcb_escape_plan(f.input());
        require(old.content_key != fresh.content_key,
                "exact unchanged geometry but footprint bytes invalidate key");
    }
    {
        auto f = base;
        auto conn = f.model.insts[f.j1];
        for (const auto &sheet : {"som_decoupling", "hdmi_rx_term", "power_som", "foreign_sheet"})
            obstacle(f, conn, 0, 0, .1, .1, "bottom", "smd", "FOREIGN", sheet);
        f.v1.violations.clear();
        auto hit = build_pcb_escape_copper(f.input());
        for (const auto &sheet : {"som_decoupling", "hdmi_rx_term", "power_som", "foreign_sheet"})
            require(std::any_of(hit.meta.coexistence.begin(), hit.meta.coexistence.end(),
                                [&](const auto &r) {
                                    return r.sheet == sheet && r.verdict == "STAY" &&
                                           !r.basis.empty();
                                }),
                    "coexistence basis " + std::string(sheet));
    }
    std::cout << name << ": real-board escape policy mutations passed\n";
}
} // namespace
int main(int argc, char **argv) {
    try {
        if (argc != 2)
            throw std::runtime_error("repo root required");
        for (const auto &name : {"carrier", "devkit_mini"}) {
            baseline(argv[1], name);
            real_mutations(argv[1], name);
        }
        std::cout << "PCB escape: " << checks << " independent assertions passed\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << e.what() << "\n";
        return 1;
    }
}
