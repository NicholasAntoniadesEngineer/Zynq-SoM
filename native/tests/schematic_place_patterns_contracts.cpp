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
bool same(double a, double b) { return std::abs(a - b) < 1e-6; }
const std::string gate = "74xGxx:74LVC1G08", resistor = "Device:R", capacitor = "Device:C";

std::vector<CircuitNetIr> gate_nets(std::vector<CircuitNetIr> extra) {
    std::vector<CircuitNetIr> nets{
        {"IN_A", "port", Pins{{"U1", "1"}}}, {"IN_B", "port", Pins{{"U1", "2"}}}};
    nets.insert(nets.end(), extra.begin(), extra.end());
    return nets;
}

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

void side_pin_chain(SymbolLibrary& lib) {
    const auto circuit = sheet("side_pin_chain",
        {part("U1", gate, "AND"), part("D1", "Device:LED", "red"), part("R1", resistor, "1k")},
        gate_nets({{"+3V3", "power", Pins{{"U1", "5"}, {"R1", "1"}}}, {"GND", "ground", Pins{{"U1", "3"}}},
                   {"LED_K", "signal", Pins{{"U1", "4"}, {"D1", "1"}}}, {"LED_A", "signal", Pins{{"D1", "2"}, {"R1", "2"}}}}));
    const auto page = drawn(circuit, lib);
    require(same(placed(page.placement, "D1").x, placed(page.placement, "R1").x), "side-pin chain is not one column");
}

void divider_ladder(SymbolLibrary& lib) {
    const std::string fuse = "TPS26631PWPR:TPS26631PWPR";
    const auto circuit = sheet("divider_ladder",
        {part("U1", fuse, "eFuse"), part("R1", resistor, "100k"), part("R2", resistor, "10k"), part("R3", resistor, "5.1k")},
        {{"+VIN", "power", Pins{{"U1", "1"}, {"U1", "2"}, {"U1", "3"}, {"U1", "6"}, {"R1", "1"}}},
         {"GND", "ground", Pins{{"U1", "9"}, {"U1", "21"}, {"R3", "2"}}},
         {"UV_SET", "signal", Pins{{"U1", "7"}, {"R1", "2"}, {"R2", "1"}}},
         {"OV_SET", "signal", Pins{{"U1", "8"}, {"R2", "2"}, {"R3", "1"}}}});
    const auto page = drawn(circuit, lib);
    const auto& r1 = placed(page.placement, "R1"); const auto& r2 = placed(page.placement, "R2");
    const auto& r3 = placed(page.placement, "R3");
    require(same(r1.x, r2.x) && same(r2.x, r3.x), "divider ladder is not one column");
    require(r1.y < r2.y && r2.y < r3.y, "divider ladder is not ordered rail to ground");
}

void trunk_port_tail(SymbolLibrary& lib) {
    const auto circuit = sheet("trunk_port_tail",
        {part("U1", gate, "AND"), part("R1", resistor, "10k"), part("C1", capacitor, "100n"), part("R2", resistor, "10k")},
        gate_nets({{"+3V3", "power", Pins{{"U1", "5"}, {"R1", "1"}}}, {"GND", "ground", Pins{{"U1", "3"}, {"C1", "2"}}},
                   {"NODE", "signal", Pins{{"U1", "4"}, {"R1", "2"}, {"C1", "1"}, {"R2", "1"}}},
                   {"SENSE", "port", Pins{{"R2", "2"}}}}));
    const auto page = drawn(circuit, lib);
    require(std::any_of(page.placement.hlabels.begin(), page.placement.hlabels.end(),
        [](const auto& h) { return h.name == "SENSE"; }), "port behind the series part has no label");
}

void power_path(SymbolLibrary& lib) {
    const std::string plug = "XT60PW-M:XT60PW-M";
    auto circuit = sheet("power_path",
        {part("J1", plug, "IN"), part("J2", plug, "OUT"), part("F1", resistor, "fuse"), part("C1", capacitor, "100n"),
         part("U1", gate, "AND")},
        gate_nets({{"+VA", "power", Pins{{"J1", "2"}, {"F1", "1"}}},
                   {"+VB", "power", Pins{{"F1", "2"}, {"J2", "2"}, {"C1", "1"}, {"U1", "5"}}},
                   {"GND", "ground", Pins{{"J1", "1"}, {"J1", "3"}, {"J1", "4"}, {"J2", "1"}, {"J2", "3"}, {"J2", "4"},
                                           {"C1", "2"}, {"U1", "3"}}},
                   {"OUT_Y", "port", Pins{{"U1", "4"}}}}));
    circuit.hints = {{"+VA", "path"}, {"+VB", "path"}};
    const auto page = drawn(circuit, lib);
    const auto& j1 = placed(page.placement, "J1"); const auto& f1 = placed(page.placement, "F1");
    const auto& c1 = placed(page.placement, "C1"); const auto& j2 = placed(page.placement, "J2");
    require(j1.x < f1.x && f1.x < c1.x && c1.x < j2.x, "power path does not read inlet, series element, shunt, outlet");
    require(placed(page.placement, "U1").y > f1.y, "the rest of the sheet is not below the power path");
    auto broken = circuit; broken.hints = {{"IN_A", "path"}};
    bool rejected = false;
    try { place_and_route_schematic(broken, lib, {}, 1); } catch (const SchematicPlaceError& e) {
        rejected = std::string(e.what()).find("is not a power rail") != std::string::npos;
    }
    require(rejected, "a path hint on a signal net was accepted");
}

void compact_retry(SymbolLibrary& lib) {
    const auto circuit = sheet("compact_retry", {part("C1", capacitor, "100n")},
        {{"+3V3", "power", Pins{{"C1", "1"}}}, {"GND", "ground", Pins{{"C1", "2"}}}});
    std::vector<SchematicSpacing> seen;
    PageOperations ops;
    ops.build = [&](const CircuitSheetIr&, SymbolLibrary&, const SchematicSpacing& spacing) {
        seen.push_back(spacing);
        SchematicPlacement pl;
        const double width = spacing.compact ? 100.0 : 500.0;
        pl.boxes.push_back({0.0, 0.0, width, 50.0, "body", "C1"});
        return pl;
    };
    ops.route = [](const CircuitSheetIr&, const SchematicPlacement&, SymbolLibrary&) { return SchematicRoutedSheet{}; };
    ops.check_visual = [](const SheetGeometry&) { return VisualResult{}; };
    place_and_route_with(circuit, lib, {}, 3, ops);
    require(seen.size() == 2 && !seen[0].compact && seen[1].compact, "an oversized sheet was not retried compact");
    require(same(seen[0].port_run, seen[1].port_run), "the compact retry also expanded the spacing");
}

void pack_relocates(SymbolLibrary& lib) {
    const auto circuit = sheet("pack_relocates", {part("C1", capacitor, "100n"), part("C2", capacitor, "100n")},
        {{"+3V3", "power", Pins{{"C1", "1"}, {"C2", "1"}}}, {"GND", "ground", Pins{{"C1", "2"}, {"C2", "2"}}}});
    Engine engine(circuit, lib);
    engine.pl.boxes.push_back({0.0, 0.0, 10.16, 101.6, "body", "A"});
    engine.pl.boxes.push_back({91.44, 0.0, 101.6, 101.6, "body", "B"});
    const auto mark = engine._mark();
    engine.passive("C1", 50.8, 203.2, 0);
    engine.pl.plan("+3V3", {{50.8, 199.39}, {50.8, 196.85}});
    engine._pack_since(mark);
    const auto& c1 = placed(engine.pl, "C1");
    require(c1.y < 101.6 && c1.x > 10.16 && c1.x < 91.44, "a detached cell was not packed into the free space");
    const auto& path = engine.pl.plans.front().second.front();
    require(same(path.front().first, c1.x) && same(c1.y - path.front().second, 3.81), "the cell's wires did not move with it");
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: schematic_place_patterns_contracts REPOSITORY_ROOT");
        const fs::path root(argv[1]);
        SymbolLibrary lib(std::vector<fs::path>{root / "schgen/lib", root / "native/tests/data/schematic_place_chain/symbols"});
        ground_template(lib); side_pin_chain(lib); divider_ladder(lib); trunk_port_tail(lib);
        power_path(lib); compact_retry(lib); pack_relocates(lib);
        std::cout << "schematic place pattern contracts passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
