#include "schgen/firmware_provenance.hpp"
#include "schgen/firmware_docs.hpp"

#include <algorithm>
#include <fstream>
#include <iostream>
#include <iterator>
#include <sstream>
#include <unistd.h>

namespace {
namespace fs = std::filesystem;
using namespace schgen;
std::size_t assertions = 0;
void require(bool condition, const std::string& message) {
    ++assertions;
    if (!condition) throw std::runtime_error(message);
}
template<class F> void rejects(F action, const std::string& fragment) {
    bool failed = false;
    try { action(); } catch (const std::exception& error) {
        failed = true;
        require(std::string(error.what()).find(fragment) != std::string::npos,
                "unexpected failure: " + std::string(error.what()));
    }
    require(failed, "expected rejection: " + fragment);
}
struct Scratch {
    fs::path path;
    Scratch() {
        auto pattern = (fs::temp_directory_path() / "firmware-provenance-XXXXXX").string();
        const auto created = ::mkdtemp(pattern.data());
        require(created != nullptr, "allocate isolated fixture tree"); path = created;
    }
    ~Scratch() { std::error_code ignored; fs::remove_all(path, ignored); }
};
std::string read(const fs::path& path) {
    std::ifstream file(path, std::ios::binary);
    require(bool(file), "read " + path.string());
    return {std::istreambuf_iterator<char>(file), {}};
}
void write(const fs::path& path, const std::string& bytes) {
    fs::create_directories(path.parent_path());
    std::ofstream file(path, std::ios::binary); file << bytes; file.close();
    require(bool(file), "write isolated fixture " + path.string());
}
std::string text(const std::vector<std::string>& lines) {
    std::string out;
    for (const auto& line : lines) out += line + "\n";
    return out;
}
std::vector<std::string> lines(const std::string& text) {
    std::istringstream input(text); std::string line; std::vector<std::string> out;
    while (std::getline(input, line)) out.push_back(line);
    return out;
}
void project(const fs::path& repo, const std::string& name) {
    const auto paths = resolve_project_paths(repo, name);
    const auto expected = read(repo / "native/tests/data/firmware_provenance" / (name + "_sources.txt"));
    const auto actual = native_firmware_sources(paths);
    require(text(actual) == expected, name + ": independently reviewed source inventory differs");
    require(std::none_of(actual.begin(), actual.end(), [](const auto& entry) {
        return entry.find(".py") != std::string::npos || entry.find("PYTHONPATH") != std::string::npos;
    }), "Python dependency retained in native provenance");
    require(native_firmware_sources(paths) == actual, "deterministic provenance");

    Scratch scratch;
    auto isolated = paths;
    isolated.repository_root = scratch.path;
    isolated.project_root = scratch.path / name;
    isolated.subsystems_dir = isolated.project_root / "subsystems";
    isolated.som_interface_file = isolated.project_root / "som_interface.json";
    isolated.som_schematic = scratch.path / "som/Zynq_SoM.kicad_sch";
    // Copy ONLY explicit provenance assets: no Python, catalog generation,
    // imports, or constructors. Real canonical JSON is independently parsed.
    for (const auto& entry : lines(expected)) {
        const auto relative = entry.substr(0, entry.find(" ("));
        fs::create_directories((scratch.path / relative).parent_path());
        fs::copy_file(repo / relative, scratch.path / relative);
    }
    require(text(native_firmware_sources(isolated)) == expected, "Python-free repository lost provenance");
    std::vector<fs::path> constructors;
    for (const auto& dependency : firmware_provenance_dependencies()) {
        if (!fs::exists(isolated.subsystems_dir / dependency)) continue;
        for (const auto& file : {isolated.subsystems_dir / (dependency + ".py"),
                               isolated.subsystems_dir / dependency / (dependency + ".py")}) {
            write(file, "raise RuntimeError('this source must never be imported')\n");
            constructors.push_back(file);
        }
    }
    require(text(native_firmware_sources(isolated)) == expected, "constructor existence changed native provenance");
    for (const auto& file : constructors) fs::remove(file);
    require(text(native_firmware_sources(isolated)) == expected, "deleting all temporary Python changed provenance");
    const auto json = isolated.subsystems_dir / "power/circuit.json";
    const auto bytes = read(json);
    fs::rename(json.parent_path(), scratch.path / "saved-power");
    rejects([&] { native_firmware_sources(isolated); }, "missing source file");
    fs::rename(scratch.path / "saved-power", json.parent_path());
    fs::remove(json);
    rejects([&] { native_firmware_sources(isolated); }, "missing source file");
    write(json, "{bad json");
    rejects([&] { native_firmware_sources(isolated); }, "expected string");
    auto renamed = bytes;
    const std::string original_name = "\"name\": \"power\"";
    const auto name_offset = renamed.find(original_name);
    require(name_offset != std::string::npos, "canonical fixture power name");
    renamed.replace(name_offset, original_name.size(), "\"name\": \"wrong_sheet\"");
    write(json, renamed);
    rejects([&] { native_firmware_sources(isolated); }, "canonical circuit name mismatch for power");
    write(json, bytes);
    const auto builder = scratch.path / "native/src/subsystem_authoring_power.cpp";
    const auto source = read(builder);
    fs::remove(builder);
    rejects([&] { native_firmware_sources(isolated); }, "missing source file");
    fs::create_directory(builder);
    rejects([&] { native_firmware_sources(isolated); }, "missing source file");
    fs::remove(builder); write(builder, source);
    const auto registry = scratch.path / "native/src/project_authoring_registry.cpp";
    const auto registry_bytes = read(registry);
    fs::remove(registry);
    rejects([&] { native_firmware_sources(isolated); }, "missing source file");
    write(registry, registry_bytes);
    const auto contract_bytes = read(isolated.som_interface_file);
    fs::remove(isolated.som_interface_file);
    rejects([&] { native_firmware_sources(isolated); }, "missing source file");
    write(isolated.som_interface_file, contract_bytes);
    const auto schematic_bytes = read(isolated.som_schematic);
    fs::remove(isolated.som_schematic);
    rejects([&] { native_firmware_sources(isolated); }, "missing source file");
    write(isolated.som_schematic, schematic_bytes);
    require(text(native_firmware_sources(isolated)) == expected, "restored sources did not restore provenance");
    Scratch outside;
    const auto outside_som = outside.path / "live.kicad_sch";
    write(outside_som, schematic_bytes);
    fs::remove(isolated.som_schematic);
    fs::create_symlink(outside_som, isolated.som_schematic);
    require(native_firmware_sources(isolated).at(1) ==
        fs::canonical(outside_som).generic_string() + " (U9 pin map, live kicad-cli extraction)",
        "external live SoM source did not preserve actual canonical provenance");
    fs::remove(outside_som);
    rejects([&] { native_firmware_sources(isolated); }, "missing source file");
    fs::remove(isolated.som_schematic); write(isolated.som_schematic, schematic_bytes);
    const auto unsafe_contract = isolated.project_root / "unsafe\ncontract.json";
    write(unsafe_contract, contract_bytes);
    const auto contract_path = isolated.som_interface_file;
    isolated.som_interface_file = unsafe_contract;
    rejects([&] { native_firmware_sources(isolated); }, "unsafe in a generated C comment");
    isolated.som_interface_file = contract_path;
    // A canonical-IR-only custom project is supported, but its absent native
    // authoring registration is explicit rather than guessed from filenames.
    const auto previous = isolated.project_root;
    fs::rename(previous, scratch.path / "unregistered");
    isolated.project_root = scratch.path / "unregistered";
    isolated.subsystems_dir = isolated.project_root / "subsystems";
    isolated.som_interface_file = isolated.project_root / "som_interface.json";
    const auto ir_only = native_firmware_sources(isolated);
    require(std::any_of(ir_only.begin(), ir_only.end(), [](const auto& entry) {
        return entry == "native authoring factory not registered for unregistered:power (canonical IR only; no native builder provenance claimed)";
    }), "unregistered canonical input silently lost native provenance");
    require(std::none_of(ir_only.begin(), ir_only.end(), [](const auto& entry) {
        return entry.find("native/src/") != std::string::npos;
    }), "unregistered project falsely claimed a native builder");
    if (name == "devkit_mini") {
        const auto optional = isolated.subsystems_dir / "board_qwiic";
        fs::create_symlink(scratch.path / "missing-optional-source", optional);
        rejects([&] { native_firmware_sources(isolated); }, "missing source file");
        fs::remove(optional);
        require(native_firmware_sources(isolated) == ir_only, "absent optional dependency was not restored");
    }
}
} // namespace
int main(int argc, char** argv) {
    try {
        require(argc == 2, "usage: firmware_provenance_contracts REPOSITORY");
        project(fs::absolute(argv[1]), "carrier"); project(fs::absolute(argv[1]), "devkit_mini");
        for (const auto* command : {"firmware", "manual", "scfw", "testplan", "power-sequence"})
            require(firmware_native_regeneration_command(command) == "native/bin/schgen " + std::string(command) + " --project PROJECT_DIR",
                    "native regeneration instruction");
        rejects([] { firmware_native_regeneration_command("firmware;python"); }, "unknown native regeneration command");
        std::cout << "PASS: " << assertions << " canonical firmware provenance and Python-removal contracts\n";
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
