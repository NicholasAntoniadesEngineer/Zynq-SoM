#include "schgen/board_inputs.hpp"
#include "schgen/footprint_courtyard.hpp"
#include "schgen/part_import.hpp"
#include "schgen/pcb_scan.hpp"
#include "schgen/process.hpp"
#include "schgen/run_config.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <unistd.h>

namespace {
using namespace schgen;
namespace fs = std::filesystem;

std::size_t checks = 0;
void require(bool ok, const std::string& message) {
    ++checks;
    if (!ok) throw std::runtime_error(message);
}
template <class Action> std::string refusal(Action action) {
    try {
        action();
    } catch (const courtyard::CourtyardError& error) {
        return error.what();
    }
    return {};
}
bool mentions(const std::string& text, const std::string& word) { return text.find(word) != std::string::npos; }
std::string read(const fs::path& file) {
    std::ifstream in(file, std::ios::binary);
    require(bool(in), "cannot read " + file.string());
    return {std::istreambuf_iterator<char>(in), {}};
}
void write(const fs::path& file, const std::string& bytes) {
    std::ofstream out(file, std::ios::binary);
    out << bytes;
    require(bool(out), "cannot write " + file.string());
}
bool same(const Box4& a, const Box4& b) {
    const double fine = courtyard::constants::extent_quantum.value;
    return std::abs(a.x0 - b.x0) < fine && std::abs(a.y0 - b.y0) < fine && std::abs(a.x1 - b.x1) < fine && std::abs(a.y1 - b.y1) < fine;
}
struct Scratch {
    fs::path path;
    Scratch() {
        auto pattern = (fs::canonical(fs::temp_directory_path()) / "schgen-courtyard-XXXXXX").string();
        const auto made = ::mkdtemp(pattern.data());
        require(made != nullptr, "private fixture directory");
        path = made;
    }
    ~Scratch() {
        std::error_code ignored;
        fs::remove_all(path, ignored);
    }
};

const char* const lead_frame =
    "(footprint \"probe\" (layer \"F.Cu\")"
    " (fp_line (start -2 -1) (end 2 -1) (stroke (width 0.05) (type solid)) (layer \"F.CrtYd\"))"
    " (fp_line (start 2 -1) (end 2 1) (stroke (width 0.05) (type solid)) (layer \"F.CrtYd\"))"
    " (fp_line (start 2 1) (end -2 1) (stroke (width 0.05) (type solid)) (layer \"F.CrtYd\"))"
    " (fp_line (start -2 1) (end -2 -1) (stroke (width 0.05) (type solid)) (layer \"F.CrtYd\"))"
    " (fp_line (start -2 -1) (end 2 -1) (stroke (width 0.2) (type solid)) (layer \"F.SilkS\"))"
    " (pad \"1\" smd rect (at 0 -2.5) (size 0.6 1.203) (layers \"F.Cu\"))"
    " (pad \"2\" smd rect (at 0 2.5) (size 0.6 1.2) (layers \"F.Cu\")))";

void judged() {
    const auto bare = sexpr_loads(lead_frame);
    const auto why = courtyard::defect(bare);
    require(why && mentions(*why, "does not enclose its pads"), "pads beyond the courtyard are a defect");
    require(mentions(refusal([&] { courtyard::require_sound(bare, "library/probe.kicad_mod"); }), "library/probe.kicad_mod"),
            "the refusal names the footprint");
    const auto open = sexpr_loads("(footprint \"probe\" (pad \"1\" smd rect (at 0 0) (size 1 1) (layers \"F.Cu\")))");
    require(courtyard::defect(open) && mentions(*courtyard::defect(open), "no courtyard"), "pads without a courtyard are a defect");
    require(!courtyard::defect(sexpr_loads("(footprint \"mark\" (fp_line (start 0 0) (end 1 1) (layer \"F.SilkS\")))")),
            "a footprint without pads has nothing to enclose");
    const auto shaped = sexpr_loads(
        "(footprint \"probe\""
        " (fp_rect (start -1 -1) (end 1 1) (layer \"F.CrtYd\"))"
        " (pad \"1\" smd custom (at 0 0) (size 0.2 0.2) (layers \"F.Cu\") (primitives (gr_poly (pts (xy 0 0) (xy 3 0) (xy 3 0.5)) (width 0)))))");
    require(courtyard::defect(shaped).has_value(), "drawn pad copper beyond the courtyard is a defect");
}

void derived() {
    const auto bare = sexpr_loads(lead_frame);
    const auto body = courtyard::court_edges(bare);
    require(body.size() == 4, "the provider outline is read as the body");
    const auto general = courtyard::enclosed(bare, body, {courtyard::Kind::general, std::nullopt}, "probe");
    require(!courtyard::defect(general), "the derived courtyard is sound");
    const auto extents = courtyard::measure(general);
    require(same(*extents.court, {-2.25, -3.36, 2.25, 3.35}), "general clearance beyond body and pads, rounded outward to the grid");
    require(same(*footprint_extent(general, FootprintExtent::fab, 6), {-2, -1, 2, 1}), "the provider outline becomes the fabrication body");
    require(same(*footprint_extent(general, FootprintExtent::body, 6), {-2, -3.1015, 2, 3.1}), "the body extent joins outline and pads");
    require(sexpr_dumps(courtyard::enclosed(general, body, {courtyard::Kind::general, std::nullopt}, "probe")) == sexpr_dumps(general),
            "deriving twice changes nothing");
    const auto strip = [](Sexpr footprint) {
        auto& nodes = std::get<SexprList>(footprint.v);
        nodes.erase(std::remove_if(nodes.begin(), nodes.end(), [](const Sexpr& node) {
            const auto dump = sexpr_dumps(node);
            return dump.find("CrtYd") != std::string::npos || dump.find("F.Fab") != std::string::npos;
        }), nodes.end());
        return sexpr_dumps(footprint);
    };
    require(strip(general) == strip(bare), "pads and silk are untouched");
    const auto stamped = [](Sexpr footprint) {
        auto& nodes = std::get<SexprList>(footprint.v);
        nodes.insert(nodes.begin() + 2, sexpr_loads(std::string("(generator \"") + courtyard::part_generator + "\")"));
        return footprint;
    };
    const auto added = courtyard::derived_clearance(stamped(general));
    require(added && std::abs(*added - courtyard::constants::general_clearance.value) < courtyard::constants::court_grid.value,
            "a courtyard this tool derived reports the clearance it added");
    require(!courtyard::derived_clearance(general), "a footprint from another generator is taken as drawn");
    require(!courtyard::derived_clearance(stamped(bare)), "a provider outline kept as the courtyard has no derived clearance");
    const auto connector = courtyard::measure(courtyard::enclosed(bare, body, {courtyard::Kind::connector, std::nullopt}, "probe"));
    require(same(*connector.court, {-2.5, -3.61, 2.5, 3.6}), "connector clearance");
    for (const auto kind : {courtyard::Kind::canned_capacitor, courtyard::Kind::crystal})
        require(courtyard::clearance_of(kind, {-2, -1, 2, 1}) == courtyard::constants::connector_clearance.value, "half millimetre classes");
    require(courtyard::clearance_of(courtyard::Kind::grid_array, {-2, -1, 2, 1}) == courtyard::constants::array_clearance.value, "grid array clearance");
    require(courtyard::clearance_of(courtyard::Kind::general, {-0.5, -0.25, 0.5, 0.25}) == courtyard::constants::small_clearance.value,
            "a body under the small size takes the small clearance");
    require(courtyard::clearance_of(courtyard::Kind::general, {-0.8, -0.4, 0.8, 0.4}) == courtyard::constants::general_clearance.value,
            "a body with one long side keeps the general clearance");
    const auto padded = sexpr_loads("(footprint \"probe\" (pad \"1\" smd rect (at 0 0) (size 1 1) (layers \"F.Cu\")))");
    require(mentions(refusal([&] { courtyard::enclosed(padded, {}, {courtyard::Kind::general, std::nullopt}, "probe"); }), "no body outline"),
            "a part without any body outline is refused");
    const auto declared = courtyard::measure(courtyard::enclosed(padded, {}, {courtyard::Kind::general, std::make_pair(3.0, 2.0)}, "probe"));
    require(same(*declared.court, {-1.75, -1.25, 1.75, 1.25}), "a declared body stands in for a missing provider outline");
    require(mentions(refusal([&] { courtyard::enclosed(bare, body, {courtyard::Kind::general, std::make_pair(3.0, 2.0)}, "probe"); }), "declares body_mm"),
            "a declared body beside a provider outline is refused");
    const auto rear = sexpr_loads("(footprint \"probe\" (fp_line (start 0 0) (end 1 0) (layer \"B.CrtYd\")) (pad \"1\" smd rect (at 0 0) (size 1 1) (layers \"B.Cu\")))");
    require(mentions(refusal([&] { courtyard::enclosed(rear, body, {courtyard::Kind::general, std::nullopt}, "probe"); }), "rear courtyard"),
            "a rear courtyard is refused");
}

void tabled() {
    const auto table = courtyard::parse_rules(parse_json_text(
        "{\"schema\":\"schgen.courtyard_classes/1\",\"source\":\"test\",\"parts\":{\"a\":{\"kind\":\"connector\"},"
        "\"b\":{\"kind\":\"general\",\"body_mm\":[3,2],\"body_source\":\"test\"}}}"), "table");
    require(table.at("a").kind == courtyard::Kind::connector && table.at("b").body->first == 3, "classes are read");
    require(mentions(refusal([&] { (void)table.at("c"); }), "c: no courtyard class"), "an unlisted part is refused by name");
    for (const char* broken : {"{\"schema\":\"other\",\"source\":\"s\",\"parts\":{\"a\":{\"kind\":\"general\"}}}",
                               "{\"schema\":\"schgen.courtyard_classes/1\",\"source\":\"s\",\"parts\":{\"a\":{\"kind\":\"round\"}}}",
                               "{\"schema\":\"schgen.courtyard_classes/1\",\"source\":\"s\",\"parts\":{\"a\":{\"kind\":\"general\",\"body_mm\":[3]}}}",
                               "{\"schema\":\"schgen.courtyard_classes/1\",\"source\":\"s\",\"parts\":{\"a\":{\"kind\":\"general\",\"body_source\":\"x\"}}}"})
        require(!refusal([&] { (void)courtyard::parse_rules(parse_json_text(broken), "table"); }).empty(), "a malformed class table is refused");
}

std::vector<fs::path> part_folders(const fs::path& parts) {
    std::vector<fs::path> folders;
    for (const auto& entry : fs::directory_iterator(parts))
        if (entry.is_directory() && fs::is_regular_file(entry.path() / (entry.path().filename().string() + ".kicad_mod")))
            folders.push_back(entry.path());
    std::sort(folders.begin(), folders.end());
    return folders;
}

void stocked(const fs::path& parts, const std::string& executable) {
    const auto table = courtyard::load_rules(parts / courtyard::rule_file);
    const auto folders = part_folders(parts);
    require(folders.size() == table.parts.size() && !folders.empty(), "every part footprint has a courtyard class and no class is spare");
    PartImportPolicy policy;
    policy.courts = table;
    for (const auto& folder : folders) {
        const std::string part = folder.filename().string();
        const auto footprint = sexpr_loads(read(folder / (part + ".kicad_mod")));
        require(!courtyard::defect(footprint), part + ": stored courtyard is sound");
        const auto extents = courtyard::measure(footprint);
        const auto shell = footprint_extent(footprint, FootprintExtent::fab, 6);
        require(shell.has_value(), part + ": the body outline is on the fabrication layer");
        const double clearance = courtyard::clearance_of(table.at(part).kind, *shell);
        const double grid = courtyard::constants::court_grid.value, fine = courtyard::constants::extent_quantum.value;
        const std::array<double, 4> margin{extents.body->x0 - extents.court->x0, extents.body->y0 - extents.court->y0,
                                           extents.court->x1 - extents.body->x1, extents.court->y1 - extents.body->y1};
        for (const double side : margin)
            require(side > clearance - fine && side < clearance + grid, part + ": courtyard is body and pads plus the class clearance, on the grid");
        const auto raw = read(folder / (part + ".easyeda.json"));
        const auto plan = prepare_part_import(raw, {}, part, {}, {}, policy);
        const auto fresh = std::find_if(plan.files.begin(), plan.files.end(), [&](const PartImportFile& file) { return file.name == part + ".kicad_mod"; });
        require(fresh != plan.files.end(), part + ": import yields a footprint");
        const auto imported = courtyard::measure(sexpr_loads(fresh->bytes));
        require(imported.court && same(*imported.court, *extents.court), part + ": a fresh import derives the stored courtyard");
    }
    const auto current = run_process({executable, "part-courtyard", "--parts-root", parts.string()});
    require(current.exit_code == 0 && mentions(current.stdout_text, " 0 stale"), "stored courtyards are current: " + current.stderr_text);
    Scratch scratch;
    const std::string part = folders.front().filename().string();
    fs::create_directories(scratch.path / part);
    for (const char* suffix : {".kicad_mod", ".easyeda.json"}) fs::copy_file(folders.front() / (part + suffix), scratch.path / part / (part + suffix));
    write(scratch.path / courtyard::rule_file,
          "{\"schema\":\"schgen.courtyard_classes/1\",\"source\":\"test\",\"parts\":{\"" + part + "\":{\"kind\":\"" +
              courtyard::kind_name(table.at(part).kind) + "\"}}}");
    const fs::path copy = scratch.path / part / (part + ".kicad_mod");
    const std::string stored = read(copy);
    auto shrunk = sexpr_loads(stored);
    auto& nodes = std::get<SexprList>(shrunk.v);
    nodes.erase(std::remove_if(nodes.begin(), nodes.end(), [](const Sexpr& node) { return sexpr_dumps(node).find("F.CrtYd") != std::string::npos; }),
                nodes.end());
    write(copy, sexpr_dumps(shrunk) + "\n");
    const std::vector<std::string> command{executable, "part-courtyard", "--parts-root", scratch.path.string()};
    require(run_process(command).exit_code != 0 && read(copy) != stored, "a stale courtyard fails the command and is left alone without --write");
    auto repair = command;
    repair.push_back("--write");
    require(run_process(repair).exit_code == 0 && read(copy) == stored, "--write restores exactly the stored footprint");
    const auto judged_file = run_process({executable, "part-courtyard", "--footprint", copy.string()});
    require(judged_file.exit_code == 0 && mentions(judged_file.stdout_text, "sound"), "a sound footprint is judged sound");
    write(copy, sexpr_dumps(shrunk) + "\n");
    const auto refused = run_process({executable, "part-courtyard", "--footprint", copy.string()});
    require(refused.exit_code != 0 && mentions(refused.stdout_text, "REFUSED"), "a footprint with pads and no courtyard is judged refused");
}

void loaded(const fs::path& root) {
    apply_run_config(root / run_config_file, "devkit_mini");
    const auto paths = resolve_project_paths(root, fs::path("devkit_mini"));
    const auto circuits = load_project_circuits(paths);
    const KicadNetlist nets{{"caller-net", {{"R1", "1"}}}};
    const LinkResult link;
    const auto roles = load_sheet_roles(paths, circuits);
    const auto input = load_board_inputs(paths, circuits, roles, link, nets);
    const std::string parts = paths.parts_dir.lexically_normal().string();
    std::string chosen;
    for (const auto& [id, source] : input.floorplan.footprint_of) {
        (void)id;
        if (source.compare(0, parts.size(), parts) == 0) chosen = fs::path(source).parent_path().filename().string();
    }
    require(!chosen.empty(), "the board uses at least one part footprint");
    Scratch scratch;
    for (const auto& entry : fs::directory_iterator(paths.parts_dir))
        if (entry.path().filename() != chosen) fs::create_symlink(entry.path(), scratch.path / entry.path().filename());
    fs::create_directories(scratch.path / chosen);
    for (const auto& entry : fs::directory_iterator(paths.parts_dir / chosen))
        if (entry.path().extension() != ".kicad_mod") fs::create_symlink(entry.path(), scratch.path / chosen / entry.path().filename());
    auto bare = sexpr_loads(read(paths.parts_dir / chosen / (chosen + ".kicad_mod")));
    auto& nodes = std::get<SexprList>(bare.v);
    nodes.erase(std::remove_if(nodes.begin(), nodes.end(), [](const Sexpr& node) { return sexpr_dumps(node).find("F.CrtYd") != std::string::npos; }),
                nodes.end());
    write(scratch.path / chosen / (chosen + ".kicad_mod"), sexpr_dumps(bare) + "\n");
    BoardInputOptions options;
    options.footprints.parts_dir = scratch.path;
    const auto why = refusal([&] { (void)load_board_inputs(paths, circuits, roles, link, nets, options); });
    require(mentions(why, chosen) && mentions(why, "no courtyard"), "a board build refuses a footprint with pads and no courtyard, by name: " + why);
}
}

int main(int argc, char** argv) {
    try {
        if (argc != 3) throw std::runtime_error("usage: footprint_courtyard_contracts REPOSITORY SCHGEN");
        const fs::path root = fs::absolute(argv[1]);
        judged();
        derived();
        tabled();
        stocked(root / "parts", argv[2]);
        loaded(root);
        std::cout << "PASS " << checks << " courtyard checks\n";
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
