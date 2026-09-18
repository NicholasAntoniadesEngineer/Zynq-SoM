// Standalone discovery/catalog contracts: compile with project_catalog.cpp,
// circuit.cpp, catalog.cpp, json.cpp and atomic_file.cpp; no Python or board build.
#include "schgen/project_catalog.hpp"

#include "schgen/atomic_file.hpp"
#include "schgen/catalog.hpp"
#include "schgen/circuit.hpp"
#include "schgen/json.hpp"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>
#include <unistd.h>

namespace {
namespace fs = std::filesystem;

void require(bool value, const std::string& message) {
    if (!value) throw std::runtime_error(message);
}

struct TempDir {
    fs::path path;
    TempDir() {
        auto pattern = (fs::temp_directory_path() / "schgen-project-XXXXXX").string();
        require(::mkdtemp(pattern.data()) != nullptr, "mkdtemp failed");
        path = fs::canonical(pattern);
    }
    ~TempDir() {
        std::error_code error;
        fs::remove_all(path, error);
    }
};

struct CatalogGuard {
    ~CatalogGuard() {
        schgen::close_circuit_catalog();
        schgen::close_part_catalog();
    }
};

void write(const fs::path& path, const std::string& text) {
    schgen::write_atomic_file(path.string(), {text.begin(), text.end()});
}

std::string read(const fs::path& path) {
    std::ifstream stream(path, std::ios::binary);
    require(bool(stream), "cannot read: " + path.string());
    return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}

std::string fixture(const std::string& name, const std::string& title = "Fixture") {
    return R"({"schema":"schgen.circuit/1","name":")" + name
        + R"(","title":")" + title + R"(","parts":[],"nets":[],"nc":[],
"port_types":{},"hints":{},"loads":{},"tp_waivers":{},"decap_waivers":{},
"pull_waivers":{},"reset_waivers":{},"strap_waivers":{},"ep_waivers":{},
"thermal_waivers":{},"part_rule_waivers":{}})";
}

template <typename F>
void rejects(F action, const std::string& message) {
    try {
        action();
    } catch (const std::exception& error) {
        require(std::string(error.what()).find(message) != std::string::npos,
                "wrong rejection: " + std::string(error.what()));
        return;
    }
    throw std::runtime_error("missing rejection: " + message);
}

void discovery_contracts(const fs::path& root) {
    const auto paths = schgen::project_catalog_paths(root, "carrier");
    rejects([&] { schgen::discover_project_subsystems(paths.subsystems_dir); },
            "subsystems directory missing");
    fs::create_directories(paths.subsystems_dir);
    require(schgen::discover_project_subsystems(paths.subsystems_dir).empty(),
            "empty project invented sheets");
    rejects([&] { schgen::compile_project_circuit_catalog(paths); }, "no circuit.json");
    write(paths.subsystems_dir / "zeta/circuit.json", fixture("zeta"));
    write(paths.subsystems_dir / "alpha/circuit.json", fixture("alpha"));
    write(paths.subsystems_dir / "legacy.py", "raise RuntimeError('never execute')");
    rejects([&] { schgen::discover_project_subsystems(paths.subsystems_dir); },
            "incomplete subsystem migration");
    fs::remove(paths.subsystems_dir / "legacy.py");
    write(paths.subsystems_dir / "legacy/legacy.py", "raise RuntimeError('never execute')");
    rejects([&] { schgen::compile_project_circuit_catalog(paths); },
            "incomplete subsystem migration");
    fs::remove(paths.subsystems_dir / "legacy/legacy.py");
    write(paths.subsystems_dir / "test_only.py", "raise RuntimeError('never execute')");
    write(root / "external/circuit.json", fixture("linked"));
    fs::create_directory_symlink(root / "external", paths.subsystems_dir / "linked");
    const auto entries = schgen::discover_project_subsystems(paths.subsystems_dir);
    require(entries.size() == 2 && entries[0].name == "alpha" && entries[1].name == "zeta",
            "JSON-only discovery lost name/order or included Python");
    require(entries[0].circuit_json == paths.subsystems_dir / "alpha/circuit.json"
            && entries[0].legacy_handle == paths.subsystems_dir / "alpha/alpha.py"
            && !fs::exists(entries[0].legacy_handle), "handle requires Python");
    require(schgen::compile_project_circuit_catalog(paths), "compile failed");
    const auto good = read(paths.circuit_catalog);
    for (const std::string directory : {".hidden", "_private", "nested/child"}) {
        const auto extra = paths.subsystems_dir / directory / "circuit.json";
        write(extra, fixture("ignored"));
        require(schgen::discover_project_subsystems(paths.subsystems_dir).size() == 2,
                "noncanonical sheet discovered");
        rejects([&] { schgen::compile_project_circuit_catalog(paths); }, "noncanonical");
        require(read(paths.circuit_catalog) == good, "rejection damaged catalog");
        fs::remove(extra);
    }
    const auto bad = paths.subsystems_dir / "bad/circuit.json";
    for (const auto& payload : {fixture("other"), std::string("{}"), std::string("[]"),
                                std::string("{broken")}) {
        write(bad, payload);
        rejects([&] { schgen::compile_project_circuit_catalog(paths); }, "");
        require(read(paths.circuit_catalog) == good, "bad JSON damaged catalog");
    }
    fs::remove(bad);
    require(schgen::compile_project_circuit_catalog(paths), "rebuild failed");
    require(read(paths.circuit_catalog) == good, "rebuild changed catalog bytes");
}

void isolation_contracts(const fs::path& root) {
    const auto first = schgen::project_catalog_paths(root, "first/devkit_mini");
    const auto second = schgen::project_catalog_paths(root, "second/devkit_mini");
    const auto absolute = schgen::project_catalog_paths(root, first.project_root);
    require(first.circuit_catalog == absolute.circuit_catalog
            && first.part_catalog == absolute.part_catalog, "absolute project drift");
    require(first.circuit_catalog != second.circuit_catalog, "same basename aliases circuits");
    require(first.part_catalog == second.part_catalog
            && first.part_catalog == root / "native/catalog.bin", "part catalog duplicated");
    require(first.parts_dir == second.parts_dir && first.parts_dir == root / "parts",
            "shared part library changed");
    write(first.subsystems_dir / "power/circuit.json", fixture("power", "FIRST"));
    write(second.subsystems_dir / "power/circuit.json", fixture("power", "SECOND"));
    schgen::compile_project_circuit_catalog(first);
    schgen::compile_project_circuit_catalog(second);
    for (const auto* paths : {&first, &second, &first}) {
        schgen::open_circuit_catalog(paths->circuit_catalog.string());
        require(schgen::circuit_catalog_count() == 1, "project count leaked");
        require(schgen::lookup_circuit_catalog("power").title ==
                (paths == &first ? "FIRST" : "SECOND"), "project lookup leaked");
    }
    rejects([&] { schgen::project_catalog_paths(root, ""); }, "required");
    rejects([&] { schgen::project_catalog_paths({}, "carrier"); }, "required");
}

void real_project_contracts(const fs::path& repo, const fs::path& output,
                            const std::string& project, std::size_t count) {
    auto paths = schgen::project_catalog_paths(repo, project);
    // The repository is input-only. Even when invoked by CTest, no shared build
    // output or project artifact is touched.
    paths.circuit_catalog = output / project / "circuits.bin";
    paths.part_catalog = output / project / "catalog.bin";
    const auto entries = schgen::discover_project_subsystems(paths.subsystems_dir);
    require(entries.size() == count, project + ": wrong discovery count");
    require(schgen::compile_project_circuit_catalog(paths), "project compile failed");
    schgen::open_circuit_catalog(paths.circuit_catalog.string());
    require(schgen::circuit_catalog_count() == count, project + ": wrong catalog count");
    for (const auto& entry : entries) {
        const auto ir = schgen::parse_json_file(entry.circuit_json.string());
        const auto sheet = schgen::lookup_circuit_catalog(entry.name);
        require(sheet.name == entry.name && sheet.schema == "schgen.circuit/1"
                && sheet.title == schgen::require_string(ir, "title", true, entry.name),
                entry.name + ": identity drift");
        const auto* parts = schgen::object_field(ir, "parts");
        const auto* nets = schgen::object_field(ir, "nets");
        require(parts && nets && sheet.parts.size() == parts->array_value.size()
                && sheet.nets.size() == nets->array_value.size(), entry.name + ": IR shape drift");
        for (std::size_t i = 0; i < sheet.parts.size(); ++i) {
            require(sheet.parts[i].ref == schgen::require_string(
                parts->array_value[i], "ref", false, entry.name), entry.name + ": part order drift");
        }
        for (std::size_t i = 0; i < sheet.nets.size(); ++i) {
            require(sheet.nets[i].name == schgen::require_string(
                nets->array_value[i], "name", false, entry.name), entry.name + ": net order drift");
        }
    }
    const auto bytes = read(paths.circuit_catalog);
    schgen::compile_project_circuit_catalog(paths);
    require(read(paths.circuit_catalog) == bytes, project + ": nondeterministic circuit catalog");
    require(schgen::compile_part_catalog(paths.parts_dir.string(), paths.part_catalog.string()),
            "part compile failed");
    schgen::open_part_catalog(paths.part_catalog.string());
    require(schgen::part_catalog_count() > 0, "empty part catalog");
    std::cout << project << ": " << entries.size() << " JSON sheets loaded, "
              << schgen::part_catalog_count() << " parts cataloged\n";
}
}  // namespace

int main(int argc, char** argv) {
    try {
        require(argc == 2, "expected repository path");
        TempDir tmp;
        CatalogGuard catalogs;
        discovery_contracts(tmp.path / "discovery");
        isolation_contracts(tmp.path / "isolation");
        real_project_contracts(argv[1], tmp.path / "real", "carrier", 37);
        real_project_contracts(argv[1], tmp.path / "real", "devkit_mini", 12);
        std::cout << "project catalog contracts passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
