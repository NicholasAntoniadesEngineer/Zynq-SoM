#include "schgen/atomic_file.hpp"
#include "schgen/diagram.hpp"
#include "schgen/gallery.hpp"
#include "schgen/pcb_checks.hpp"
#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <unistd.h>

namespace fs = std::filesystem;
using namespace schgen;
namespace {
int checks = 0, failures = 0;
fs::path output;
void require(bool ok, const std::string &why) {
    ++checks;
    if (!ok) {
        ++failures;
        std::cerr << "FAIL: " << why << "\n";
    }
}
std::string read(const fs::path &p) {
    std::ifstream f(p, std::ios::binary);
    if (!f)
        throw std::runtime_error("cannot read " + p.string());
    return {std::istreambuf_iterator<char>(f), {}};
}
void write(const fs::path &p, const std::string &s) {
    fs::create_directories(p.parent_path());
    write_atomic_file(p.string(), {s.begin(), s.end()});
}
const JsonNode &field(const JsonNode &n, const std::string &key) {
    auto p = object_field(n, key);
    if (!p)
        throw std::runtime_error("missing fixture " + key);
    return *p;
}
std::string str(const JsonNode &n, const std::string &key) { return field(n, key).string_value; }
std::vector<std::string> strings(const JsonNode &a) {
    std::vector<std::string> out;
    for (const auto &n : a.array_value)
        out.push_back(n.string_value);
    return out;
}
LinkResult graph(const JsonNode &d) {
    LinkResult link;
    for (const auto &n : field(d, "sheets").array_value) {
        CircuitSheetIr s;
        s.name = n.string_value;
        link.sheets.push_back(s);
    }
    for (const auto &b : field(d, "bindings").array_value) {
        LinkPortBinding v;
        v.sheet = str(b, "sheet");
        v.net = str(b, "net");
        v.status = str(b, "status");
        v.ptype.kind = str(field(b, "ptype"), "kind");
        v.targets = strings(field(b, "targets"));
        link.bindings.push_back(v);
    }
    link.rail_bindings = strings(field(d, "rail_bindings"));
    link.unbound_som = strings(field(d, "unbound_som"));
    return link;
}
LinkSomNets nets(const JsonNode &n) {
    LinkSomNets out;
    for (const auto &[k, v] : n.object_value)
        out[k] = strings(v);
    return out;
}
GalleryInput gallery(const JsonNode &n) {
    GalleryInput in;
    in.repository_root = str(n, "repo");
    in.project_root = str(n, "project");
    in.is_default_project = field(n, "default").bool_value;
    for (const auto &s : field(n, "sheets").array_value)
        in.sheets.push_back({str(s, "name"), str(s, "title")});
    const auto renders = strings(field(n, "render_files")), wired = strings(field(n, "wired"));
    in.render_files = {renders.begin(), renders.end()};
    in.wired_sheets = {wired.begin(), wired.end()};
    in.ratsnest_files = strings(field(n, "ratsnest_files"));
    return in;
}
void equal_bytes(const std::string &got, const std::string &expected, const std::string &name) {
    require(got == expected, name);
    if (got != expected) {
        write(output / (name + ".got"), got);
        write(output / (name + ".expected"), expected);
        const auto end = std::mismatch(got.begin(), got.end(), expected.begin(), expected.end());
        std::cerr << "first differing byte " << std::distance(got.begin(), end.first) << " (sizes "
                  << got.size() << " / " << expected.size() << ")\n";
    }
}
template <typename F> void rejects(F f, const std::string &why) {
    bool caught = false;
    try {
        f();
    } catch (const std::exception &) {
        caught = true;
    }
    require(caught, why);
}
void fixture_cases(const JsonNode &all) {
    require(str(all, "schema") == "schgen.gallery_diagram.python/1", "fixture schema");
    require(field(all, "diagrams").array_value.size() == 9, "nine independent diagrams");
    require(field(all, "galleries").array_value.size() == 7, "seven independent galleries");
    require(field(all, "splices").array_value.size() == 12, "twelve independent splices");
    for (const auto &c : field(all, "diagrams").array_value) {
        const auto name = str(c, "name"), expected = str(c, "expected");
        auto link = graph(field(c, "link"));
        const auto som = nets(field(c, "som_nets"));
        equal_bytes(render_block_diagram(link, som), expected, "diagram-" + name);
        const auto path = output / "diagrams" / (name + ".svg");
        require(write_block_diagram(link, som, path) == path, "diagram writer path");
        equal_bytes(read(path), expected, "diagram-writer-" + name);
        const auto old = render_block_diagram(link, som);
        link.unbound_som.push_back("fresh-mutation");
        require(render_block_diagram(link, som) != old, "diagram consumes fresh link state");
    }
    for (const auto &c : field(all, "galleries").array_value) {
        const auto name = str(c, "name");
        auto in = gallery(c);
        equal_bytes(render_gallery_full(in, in.project_root), str(c, "expected_full"),
                    "gallery-full-" + name);
        equal_bytes(render_gallery_compact(in, in.repository_root), str(c, "expected_compact"),
                    "gallery-compact-" + name);
        equal_bytes(render_gallery_full(in, in.repository_root / "docs/nested"),
                    str(c, "expected_nested"), "gallery-nested-" + name);
        equal_bytes(gallery_readme_targets(in), str(c, "expected_targets"),
                    "gallery-targets-" + name);
        const auto old = render_gallery_full(in, in.project_root);
        in.sheets.push_back({"fresh-native-sheet", "live"});
        require(render_gallery_full(in, in.project_root) != old, "gallery consumes fresh sheets");
    }
    for (const auto &c : field(all, "splices").array_value) {
        const auto &original = field(c, "original");
        const auto got = splice_gallery(
            original.kind == JsonKind::Null ? "" : original.string_value, str(c, "section"));
        require(got.changed == field(c, "changed").bool_value, "splice changed " + str(c, "name"));
        equal_bytes(got.bytes, str(c, "expected"), "splice-" + str(c, "name"));
    }
}
void boundary_contracts() {
    LinkResult invalid;
    CircuitSheetIr s;
    s.name = "a";
    invalid.sheets = {s};
    LinkPortBinding b;
    b.sheet = "a";
    b.net = "N";
    b.ptype.kind = "single";
    b.targets = {"sheet missing:N"};
    invalid.bindings = {b};
    const auto target = output / "preserve.svg";
    write(target, "keep");
    rejects([&] { write_block_diagram(invalid, {}, target); }, "missing peer rejected");
    equal_bytes(read(target), "keep", "diagram-failure-preserves-destination");
    b.targets = {"sheet "};
    invalid.bindings = {b};
    rejects([&] { render_block_diagram(invalid, {}); }, "malformed peer rejected");
    b.targets = {"SoM J1.1"};
    b.ptype.kind = "unsupported";
    invalid.bindings = {b};
    rejects([&] { render_block_diagram(invalid, {}); }, "unknown rendered kind rejected");
    rejects([&] { splice_gallery(std::string(1, static_cast<char>(0xff)), ""); },
            "invalid UTF8 README rejected");
    ProjectPaths sparse;
    sparse.repository_root = output;
    sparse.project_root = output / "sparse";
    write(sparse.project_root / "project.json", "deliberately invalid JSON");
    auto input = load_gallery_input(sparse, {});
    require(input.render_files.empty() && !fs::exists(sparse.project_root / "renders"),
            "gallery discovery is read-only with missing renders");
    write(sparse.project_root / "renders/ratsnest/duplicate ٢.png", "");
    fs::create_symlink("missing-target", sparse.project_root / "renders/ratsnest/som.png");
    input = load_gallery_input(sparse, {});
    const auto pending = render_gallery_full(input, sparse.project_root);
    require(pending.find("ratsnest renders pending") != std::string::npos,
            "Unicode sync duplicates and dangling SoM hero stay pending");
    write(sparse.project_root / "renders/ratsnest/active.png", "");
    rejects([&] { load_gallery_input(sparse, {}); },
            "wired config parsed when sheet thumbnails exist");
    write(sparse.project_root / "project.json", R"({"placement":{"wired_sheets":["active"]}})");
    input = load_gallery_input(sparse, {});
    require(render_gallery_full(input, sparse.project_root).find("**active** `wired`") !=
                std::string::npos,
            "native discovery applies live wired-sheet config");
    input.project_root = output / "absent-parent";
    rejects([&] { write_gallery(input); }, "gallery preserves missing-parent failure");
    require(!fs::exists(input.project_root), "gallery does not create absent README parent");
}
void live_projects(const JsonNode &all, const fs::path &repo) {
    for (const std::string name : {"carrier", "devkit_mini"}) {
        const auto paths = resolve_project_paths(repo, name);
        const auto loaded = load_project_circuits(paths);
        std::vector<CircuitSheetIr> sheets;
        for (const auto &c : loaded)
            sheets.push_back(c.circuit);
        const auto som =
            link_som_nets_from_json(parse_json_file(paths.som_interface_file.string()));
        const auto policy = link_mapping_from_json(
            parse_json_file((paths.project_root / "som_mapping.json").string()));
        const auto linked = link_sheets(sheets, som, policy);
        const auto &rows = field(all, "diagrams").array_value;
        const auto item = std::find_if(rows.begin(), rows.end(),
                                       [&](const auto &c) { return str(c, "name") == name; });
        equal_bytes(render_block_diagram(linked, som), str(*item, "expected"),
                    "live-native-diagram-" + name);

        // Canonical JSON-only clone: no authoring .py files, no circuit catalog,
        // no Python process. All generated documents remain under test output.
        const auto clone = output / "json-only" / name;
        write(clone / "project.json", read(paths.project_file));
        write(clone / "som_interface.json", read(paths.som_interface_file));
        write(clone / "som_mapping.json", read(paths.project_root / "som_mapping.json"));
        for (const auto &c : loaded)
            write(clone / "subsystems" / c.name / "circuit.json", read(c.path));
        bool no_python = true;
        for (const auto &p : fs::recursive_directory_iterator(clone))
            if (p.path().extension() == ".py")
                no_python = false;
        require(no_python, "JSON-only native input tree has no Python sources");
        const auto &gs = field(all, "galleries").array_value;
        const auto g = std::find_if(gs.begin(), gs.end(),
                                    [&](const auto &c) { return str(c, "name") == name; });
        auto expected_input = gallery(*g);
        for (const auto &n : expected_input.render_files)
            if (n != "ratsnest")
                write(clone / "renders" / n, "");
        for (const auto &n : expected_input.ratsnest_files)
            write(clone / "renders/ratsnest" / n, "");
        auto cp = resolve_project_paths(output / "json-only", name);
        const auto actual = load_gallery_input(cp);
        require(actual.sheets.size() == expected_input.sheets.size(),
                "JSON-only native gallery sheet count");
        equal_bytes(render_gallery_full(actual, cp.project_root), str(*g, "expected_full"),
                    "live-native-gallery-" + name);
        const auto changed = generate_gallery(cp);
        require(changed.size() == (cp.is_default_project ? 2u : 1u),
                "gallery native writer targets");
        equal_bytes(read(cp.project_root / "README.md"), str(*g, "expected_full") + "\n",
                    "live-native-readme-" + name);
        if (cp.is_default_project) {
            equal_bytes(read(cp.repository_root / "README.md"), str(*g, "expected_compact") + "\n",
                        "live-native-root-readme-" + name);
            require(changed.front() == cp.repository_root / "README.md" &&
                        changed.back() == cp.project_root / "README.md",
                    "gallery changed-path order");
        }
        equal_bytes(gallery_summary(actual, changed),
                    "GALLERY: " + std::to_string(actual.sheets.size()) + " sheets -> " +
                        str(*g, "expected_targets") + " (" +
                        (cp.is_default_project ? "README.md, " : "") + name + "/README.md)",
                    "live-gallery-command-summary-" + name);
        require(generate_gallery(cp).empty(), "gallery idempotent publication");
        require(gallery_summary(actual, {}).find("(unchanged)") != std::string::npos,
                "gallery unchanged summary");
        auto edited = load_project_circuits(cp);
        edited.front().circuit.title = "Fresh native title | changed";
        const auto fresh = load_gallery_input(cp, edited);
        require(
            render_gallery_full(fresh, cp.project_root).find("Fresh native title \\| changed") !=
                std::string::npos,
            "gallery consumes fresh typed circuit metadata");
        const auto json_link = link_sheets(
            [&] {
                std::vector<CircuitSheetIr> out;
                for (const auto &c : load_project_circuits(cp))
                    out.push_back(c.circuit);
                return out;
            }(),
            som, policy);
        equal_bytes(render_block_diagram(json_link, som), str(*item, "expected"),
                    "json-only-native-diagram-" + name);
        std::cout << name
                  << ": live JSON-only native loader/linker SVG + Markdown byte parity PASS\n";
    }
}
} // namespace
int main(int argc, char **argv) {
    try {
        if (argc != 4)
            throw std::runtime_error(
                "usage: gallery_diagram_contracts FIXTURE_DIR OUTPUT_PARENT REPOSITORY_ROOT");
        const fs::path fixtures = argv[1];
        fs::create_directories(argv[2]);
        auto pattern = (fs::path(argv[2]) / "gallery-diagram.XXXXXX").string();
        if (!::mkdtemp(pattern.data()))
            throw std::runtime_error("cannot create isolated contract directory");
        output = pattern;
        const auto bytes = read(fixtures / "python.json");
        std::ifstream manifest(fixtures / "SHA256SUMS");
        std::string hash, filename;
        require(static_cast<bool>(manifest >> hash >> filename) && filename == "python.json",
                "oracle checksum manifest");
        require(pcb_sha256(bytes) == hash, "immutable independent Python oracle bytes");
        const auto all = parse_json_file((fixtures / "python.json").string());
        fixture_cases(all);
        boundary_contracts();
        live_projects(all, argv[3]);
        std::cout << "gallery/diagram: " << checks << " checks, " << failures << " failures\n";
        std::cout << "contract outputs: " << output.string() << "\n";
        return failures ? 1 : 0;
    } catch (const std::exception &e) {
        std::cerr << e.what() << "\n";
        return 1;
    }
}
