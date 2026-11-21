#include "../src/schematic_place_internal.hpp"

#include "schgen/schematic_route.hpp"
#include "schgen/validation.hpp"

#include <filesystem>
#include <iostream>
#include <stdexcept>

namespace {
using namespace schgen;
using namespace schgen::schematic_place;
namespace fs = std::filesystem;
using Pins = std::vector<CircuitPinRefIr>;

void require(bool value, const std::string& message) {
    if (!value) throw std::runtime_error(message);
}
CircuitPartIr part(const std::string& ref, const std::string& lib_id, const std::string& value) {
    return {ref, lib_id, value, "", {}, {}, {}};
}
CircuitSheetIr sheet(const std::string& name, std::vector<CircuitPartIr> parts, std::vector<CircuitNetIr> nets) {
    CircuitSheetIr out;
    out.schema = "schgen.circuit/1"; out.name = name; out.title = name;
    out.parts = std::move(parts); out.nets = std::move(nets);
    return out;
}
const SchematicPlacedPart& placed(const SchematicPlacement& pl, const std::string& ref) {
    for (const auto& p : pl.parts) if (p.ref == ref) return p;
    throw std::runtime_error("part " + ref + " was not placed");
}
SchematicPlacedPage drawn(const CircuitSheetIr& circuit, SymbolLibrary& lib) {
    auto page = place_and_route_schematic(circuit, lib);
    const auto visual = check_visual_geometry(page.geometry);
    require(visual.ok, circuit.name + ": " + visual.summary());
    for (const auto& p : circuit.parts) placed(page.placement, p.ref);
    return page;
}
const std::string capacitor = "Device:C";

void ground_template(SymbolLibrary& lib) {
    const auto circuit = sheet("ground_template", {part("C1", capacitor, "100n")},
        {{"+3V3", "power", Pins{{"C1", "1"}}}, {"GND_AUX", "ground", Pins{{"C1", "2"}}}});
    const auto page = drawn(circuit, lib);
    const auto found = std::find_if(page.placement.powers.begin(), page.placement.powers.end(),
        [](const auto& p) { return p.lib_id == "schgen:GND_AUX"; });
    require(found != page.placement.powers.end(), "second ground did not get its own ground symbol");
    const auto& symbol = lib.get("schgen:GND_AUX");
    require(symbol.pins.size() == 1 && symbol.pins.front().name == "GND_AUX", "ground template was not renamed");
    bool rejected = false;
    try { lib.get("schgen:NOT_A_RAIL"); } catch (const SymbolError&) { rejected = true; }
    require(rejected, "a name that is neither rail nor ground resolved to a template");
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: schematic_place_patterns_contracts REPOSITORY_ROOT");
        const fs::path root(argv[1]);
        SymbolLibrary lib(std::vector<fs::path>{root / "schgen/lib", root / "native/tests/data/schematic_place_chain/symbols"});
        ground_template(lib);
        std::cout << "schematic place pattern contracts passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
