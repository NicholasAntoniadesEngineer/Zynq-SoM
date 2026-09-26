// Register as native_regression_rc_smoke. This is an unconditional LIVE test:
// absence of KiCad, emission, extraction or ERC is a failure, never a skip.
// The independently captured original m1_rc input/golden is reused, not run.
#include "schgen/netlist_gate.hpp"
#include "schgen/schematic.hpp"
#include "schgen/validation.hpp"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <unistd.h>

namespace {
namespace fs = std::filesystem;
using namespace schgen;
std::size_t checks = 0;
void require(bool ok, const std::string& text) {
    ++checks; if (!ok) throw std::runtime_error(text);
}
const JsonNode& field(const JsonNode& n, const char* name) {
    const auto* value = object_field(n, name);
    if (!value) throw std::runtime_error(std::string("missing independent input: ") + name);
    return *value;
}
std::string read(const fs::path& path) {
    std::ifstream file(path, std::ios::binary);
    require(static_cast<bool>(file), "cannot read " + path.string());
    return {std::istreambuf_iterator<char>(file), {}};
}
void write(const fs::path& path, const std::string& text) {
    std::ofstream file(path, std::ios::binary); file << text; file.close();
    require(static_cast<bool>(file), "cannot write " + path.string());
}
}  // namespace

int main(int argc, char** argv) {
    fs::path scratch;
    try {
        require(argc == 2 || (argc == 4 && std::string(argv[2]) == "--kicad-cli"),
                "usage: regression_rc_smoke_contracts ROOT [--kicad-cli PATH]");
        const auto root = fs::canonical(argv[1]);
        const NetlistExtractOptions extraction{argc == 4 ? argv[3] : "kicad-cli"};
        auto pattern = (fs::temp_directory_path() / "schgen-regression-rc-XXXXXX").string();
        require(::mkdtemp(pattern.data()) != nullptr, "mkdtemp failed"); scratch = pattern;
        std::cout << "RC SMOKE ARTIFACTS: " << scratch << '\n';
        const auto input = parse_json_file((root / "native/tests/data/schematic/cases.json").string());
        const JsonNode* row = nullptr;
        for (const auto& candidate : field(input, "cases").array_value)
            if (field(candidate, "name").string_value == "m1-rc") row = &candidate;
        require(row != nullptr, "independent original m1_rc input missing");
        const auto& placed = field(*row, "design");
        const auto circuit = parse_circuit_ir(field(placed, "circuit"));
        const auto design = schematic_design_from_json(placed, circuit);
        SymbolLibrary symbols(root);
        validate_circuit(circuit, symbols);
        const auto resolver = [&](const std::string& id) -> const SymbolDef& { return symbols.get(id); };
        const std::map<std::string, std::pair<double, double>> expected_pins{
            {"R1.1", {101.6, 77.47}}, {"R1.2", {101.6, 85.09}},
            {"R2.1", {101.6, 97.79}}, {"R2.2", {101.6, 105.41}},
            {"C1.1", {111.76, 91.44}}, {"C1.2", {111.76, 99.06}}};
        std::size_t pins = 0;
        for (const auto& part : design.parts)
            for (const auto& pin : symbols.get(part.lib_id).pins) {
                require(pin_page_position(pin, part.x, part.y, part.rotation) ==
                    expected_pins.at(part.ref + "." + pin.number), "original RC pin geometry changed");
                ++pins;
            }
        require(pins == 6, "original RC six pins must be exercised");
        const auto clean = emit_schematic(design, resolver).text;
        require(clean == read(root / "native/tests/data/schematic/m1-rc.kicad_sch"),
                "native RC emission differs from independent Python golden");
        for (const std::string variant : {"clean", "open", "short", "undriven"}) {
            auto changed = design;
            if (variant == "open") changed.wires.erase(changed.wires.begin() + 1);
            if (variant == "short") changed.wires.push_back({101.6, 77.47, 101.6, 105.41});
            if (variant == "undriven") changed.powers.erase(std::remove_if(changed.powers.begin(), changed.powers.end(),
                [](const auto& power) { return power.lib_id == "power:PWR_FLAG"; }), changed.powers.end());
            const auto path = scratch / (variant + ".kicad_sch");
            write(path, emit_schematic(changed, resolver).text);
            const auto gate = check_netlist(circuit, path, extraction);
            const auto erc = run_kicad_erc(path, extraction);
            write(scratch / (variant + ".netlist.txt"), gate.summary());
            write(scratch / (variant + ".erc.txt"), erc.report);
            write(scratch / (variant + ".erc.stderr"), erc.stderr_text);
            require(!erc.report.empty(), "actual ERC report required");
            if (variant == "clean") {
                require(gate.ok && erc.exit_code == 0, "RC baseline must pass actual netlist AND ERC: " + gate.summary() + erc.report);
            } else if (variant == "undriven") {
                require(gate.ok && erc.exit_code != 0, "independent ERC-only negative control survived");
            } else {
                require(!gate.ok, variant + " physical wire mutation survived live connectivity gate");
                require(variant == "open" ? !gate.opens.empty() : !gate.shorts.empty(), "wrong live mutation rejection");
            }
        }
        bool rejected = false;
        try { (void)check_netlist(circuit, scratch / "clean.kicad_sch", {(scratch / "missing-kicad").string()}); }
        catch (const std::exception&) { rejected = true; }
        require(rejected, "missing KiCad cannot pass by fallback");
        std::cout << "M1 RC: PASS — native emission, actual netlist + ERC, open/short/undriven negative controls; "
                  << checks << " checks\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "RC SMOKE FAIL: " << error.what() << " (retained " << scratch << ")\n";
        return 1;
    }
}
