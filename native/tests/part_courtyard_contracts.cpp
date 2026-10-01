#include "schgen/part_import.hpp"
#include "schgen/pcb_emit.hpp"
#include "schgen/mirror.hpp"
#include <algorithm>
#include <fstream>
#include <iostream>

namespace {
using namespace schgen;
namespace fs = std::filesystem;
void require(bool ok, const std::string& message) {
    if (!ok) throw std::runtime_error(message);
}
std::string read(const fs::path& path) {
    std::ifstream f(path, std::ios::binary);
    require(bool(f), "cannot read " + path.string());
    return {std::istreambuf_iterator<char>(f), {}};
}
void write(const fs::path& path, const std::string& bytes) {
    std::ofstream f(path, std::ios::binary); f << bytes;
    require(bool(f), "cannot write " + path.string());
}
const JsonNode& field(const JsonNode& n, const std::string& key) {
    const auto* p = object_field(n, key); require(p != nullptr, "missing " + key); return *p;
}
JsonNode& field(JsonNode& n, const std::string& key) {
    for (auto& kv : n.object_value) if (kv.first == key) return kv.second;
    throw std::runtime_error("missing " + key);
}
bool tag(const Sexpr& n, const std::string& key) {
    const auto* l = std::get_if<SexprList>(&n.v);
    if (!l || l->empty()) return false;
    const auto* s = std::get_if<Sexpr::Sym>(&l->front().v);
    return s && s->name == key;
}
const Sexpr& child(const Sexpr& n, const std::string& key) {
    for (const auto& c : std::get<SexprList>(n.v)) if (tag(c, key)) return c;
    throw std::runtime_error("missing node " + key);
}
std::string text(const Sexpr& n, std::size_t i) {
    return std::get<std::string>(std::get<SexprList>(n.v).at(i).v);
}
bool court(const Sexpr& n) {
    if (!tag(n, "fp_line")) return false;
    const auto layer = text(child(n, "layer"), 1);
    return layer == "F.CrtYd" || layer == "B.CrtYd";
}
bool zero(const Sexpr& n) {
    if (!court(n)) return false;
    const auto& a = std::get<SexprList>(child(n, "start").v);
    const auto& b = std::get<SexprList>(child(n, "end").v);
    return std::get<double>(a.at(1).v) == std::get<double>(b.at(1).v) &&
           std::get<double>(a.at(2).v) == std::get<double>(b.at(2).v);
}
std::size_t remove_zero(Sexpr& n) {
    auto& l = std::get<SexprList>(n.v); const auto before = l.size();
    l.erase(std::remove_if(l.begin(), l.end(), zero), l.end()); return before - l.size();
}
std::size_t courts(const Sexpr& n) {
    const auto& l = std::get<SexprList>(n.v);
    return std::count_if(l.begin(), l.end(), court);
}
const std::string& file(const PartImportPlan& p, const std::string& name) {
    for (const auto& f : p.files) if (f.name == name) return f.bytes;
    throw std::runtime_error("missing generated " + name);
}

void synthetic(JsonNode result, const PartImportInfo& info) {
    auto& shapes = field(field(field(result, "packageDetail"), "dataStr"), "shape").array_value;
    // Origin is (400,300). Distinct raw points collapse only AFTER 0.254
    // conversion/4-place rounding; retain the next genuinely nonzero edge.
    JsonNode s; s.kind = JsonKind::String;
    s.string_value = "SOLIDREGION~99~~M400 300 L400.00001 300 L400.0004 300 L401 301 L400 300 Z~solid";
    shapes = {s};
    auto out = part_convert_footprint(result, "probe", info).tree;
    require(courts(out) == 3, "converted duplicate removed, tiny nonzero edge preserved");
    require(remove_zero(out) == 0, "no surviving zero courtyard edge");
    const auto& first = *std::find_if(std::get<SexprList>(out.v).begin(), std::get<SexprList>(out.v).end(), court);
    require(std::get<double>(std::get<SexprList>(child(first, "end").v).at(1).v) == 0.0001,
            "no epsilon-based deletion of tiny edge");
    s.string_value = "SOLIDREGION~99~~M400 300 L400 300 L400.00001 300 Z~solid";
    shapes = {s};
    require(courts(part_convert_footprint(result, "probe", info).tree) == 0, "fully collapsed path emits no edges");
    s.string_value = "SOLIDREGION~3~~M400 300 L400 300 L401 301 Z~solid";
    shapes = {s}; out = part_convert_footprint(result, "probe", info).tree;
    const auto& pts = std::get<SexprList>(child(child(out, "fp_poly"), "pts").v);
    require(pts.size() == 5 && sexpr_dumps(pts[1]) == sexpr_dumps(pts[2]),
            "non-courtyard duplicate vertices remain unchanged");
}
}

// REPO CORRECTED_MOD OUTPUT [FAILING_BOARD]. No fixture is modified. The
// independent historical oracle permits only removal of exactly-zero court
// edges; every surviving node, order, metadata, pad and other file is exact.
int main(int argc, char** argv) {
    try {
        require(argc == 4 || argc == 5, "REPO CORRECTED_MOD OUTPUT [FAILING_BOARD]");
        const fs::path root(argv[1]), output(argv[3]); fs::create_directories(output);
        const std::string name = "RV-3028-C7-32.768kHz-1ppm-TA-QC";
        const auto corrected = sexpr_loads(read(argv[2]));
        require(courts(corrected) == 4, "source contains precisely four rectangle edges");
        auto checked = corrected; require(remove_zero(checked) == 0, "source has no degenerate court edges");
        std::size_t cases = 0, variants = 0, changed = 0, removed = 0; bool found = false;
        for (const auto& entry : fs::directory_iterator(root / "native/tests/data/part_gen")) {
            if (entry.path().extension() != ".json") continue;
            ++cases; const auto ref = parse_json_file(entry.path().string());
            const auto n = field(ref, "name").string_value;
            for (const auto& variant : field(ref, "variants").array_value) {
                ++variants; std::vector<std::string> models;
                for (const auto& m : field(variant, "models").array_value) models.push_back(m.string_value);
                const auto plan = prepare_part_import(field(ref, "input").string_value, field(ref, "lcsc").string_value, n, models);
                const auto old = sexpr_loads(field(variant, "footprint").string_value);
                auto want = old; const auto count = remove_zero(want);
                require(count == (n == name ? 3u : n == "HDMI-019S" ? 4u : 0u),
                        n + ": historical correction must be exact and named");
                require(file(plan, n + ".kicad_mod") == sexpr_dumps(want) + "\n", n + ": unintended footprint change");
                require(file(plan, n + ".kicad_sym") == field(ref, "symbol").string_value, n + ": symbol changed");
                require(file(plan, "part.json") == field(variant, "part_json").string_value, n + ": metadata changed");
                require(file(plan, n + ".easyeda.json") == field(ref, "input").string_value, n + ": raw input changed");
                if (count) { ++changed; removed += count; std::cout << "historical correction " << n << " models=" << models.size() << " zero_edges=" << count << '\n'; }
                if (n == name) {
                    require(count == 3 && courts(want) == 4, "RV historical seven-to-four boundary");
                    // Source model paths are independent of the import model variant.
                    auto a = want, b = corrected;
                    for (auto* p : {&a, &b}) {
                        auto& l = std::get<SexprList>(p->v);
                        l.erase(std::remove_if(l.begin(), l.end(), [](const auto& node){ return tag(node, "model"); }), l.end());
                    }
                    require(sexpr_dumps(a) == sexpr_dumps(b), "RV source non-model geometry differs from frozen oracle");
                    found = true;
                }
            }
        }
        require(found && cases == 62, "full historical corpus including RV required");
        require(variants == 186 && changed == 6 && removed == 21, "exact six-variant correction scope");
        const auto raw = parse_json_file((root / "parts" / name / (name + ".easyeda.json")).string());
        const auto& result = field(raw, "result");
        auto imported = part_convert_footprint(result, name, part_import_info(result)).tree;
        auto source_geometry = corrected;
        for (auto* p : {&imported, &source_geometry}) {
            auto& l = std::get<SexprList>(p->v);
            l.erase(std::remove_if(l.begin(), l.end(), [](const auto& n){ return tag(n, "model"); }), l.end());
        }
        require(sexpr_dumps(imported) == sexpr_dumps(source_geometry), "actual source provider reimports to corrected geometry");
        synthetic(result, part_import_info(result));
        for (bool bottom : {false, true}) for (int angle : {0, 90, 180, 270}) {
            PcbModel m; m.board_w = 40; m.board_h = 40; m.placed = 1;
            PcbFootprintInst i; i.ref = "U1"; i.value = name; i.footprint = name; i.sheet = "probe";
            i.x = 45; i.y = 45; i.rotation = angle; i.side = bottom ? "bottom" : "top"; i.mirror = bottom;
            const auto doc = bottom ? mirrored_footprint(corrected) : corrected;
            i.mod = pcb_check_footprint(bottom ? ".mirrored_fp/RV.kicad_mod" : "RV.kicad_mod", sexpr_dumps(doc), doc);
            m.insts.push_back(i); m.n_top = bottom ? 0 : 1; m.n_bottom = bottom ? 1 : 0;
            write(output / (i.side + "-" + std::to_string(angle) + ".kicad_pcb"), render_pcb(m).pcb);
        }
        if (argc == 5) {
            auto board = sexpr_loads(read(argv[4])); std::size_t hits = 0;
            for (auto& fp : std::get<SexprList>(board.v)) if (tag(fp, "footprint")) {
                bool target = false;
                for (const auto& n : std::get<SexprList>(fp.v))
                    if (tag(n, "property") && text(n, 1) == "Reference" && text(n, 2) == "U3002") target = true;
                if (target) { ++hits; require(remove_zero(fp) == 3 && courts(fp) == 4, "full-board exact U3002 correction"); }
            }
            require(hits == 1, "exactly one U3002");
            write(output / "carrier-corrected.kicad_pcb", sexpr_dumps(board) + "\n");
        }
        std::cout << "PASS cases=" << cases << " variants=" << variants << " changed_variants=" << changed
                  << " removed_zero_edges=" << removed << " matrix=8\n";
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
