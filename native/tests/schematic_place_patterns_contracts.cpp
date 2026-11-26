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

void pack_near_served_part(SymbolLibrary& lib) {
    auto circuit = sheet("pack_near_served_part",
        {part("U1", gate, "AND"), part("U2", gate, "AND"), part("R1", resistor, "10k"), part("R2", resistor, "10k")},
        {{"+3V3", "power", Pins{{"U1", "5"}, {"U2", "5"}, {"R1", "1"}, {"R2", "1"}}}, {"GND", "ground", Pins{{"U1", "3"}, {"U2", "3"}}},
         {"NODE", "signal", Pins{{"U2", "4"}, {"R1", "2"}, {"R2", "2"}}}});
    CircuitServiceIr service; service.part = "R2"; service.role = "pull"; service.owner = {"U1", "4"};
    circuit.layout.serves.push_back(service);
    const Point stated{5.08, 5.08}, sharing{96.52, 5.08};
    const double upper_half = 45.72;
    const auto distance = [](const SchematicPlacedPart& p, Point to) { return std::abs(p.x - to.first) + std::abs(p.y - to.second); };
    for (const std::string ref : {"R1", "R2"}) {
        Engine engine(circuit, lib);
        engine.pl.boxes.push_back({0.0, 0.0, 10.16, 10.16, "body", "U1"});
        engine.pl.boxes.push_back({91.44, 0.0, 101.6, 10.16, "body", "U2"});
        engine.pl.boxes.push_back({0.0, 91.44, 101.6, 101.6, "body", "FLOOR"});
        const auto mark = engine._mark();
        engine.passive(ref, 50.8, 203.2, 0);
        engine._pack_since(mark);
        const auto& moved = placed(engine.pl, ref);
        require(moved.y < upper_half, ref + " was packed into the first free space, not beside the part it serves");
        if (ref == "R1") require(distance(moved, sharing) < distance(moved, stated), "a detached cell was not packed beside the part it shares a net with");
        else require(distance(moved, stated) < distance(moved, sharing), "a detached cell was not packed beside the part its purpose names");
    }
}

void enclosing_taps(SymbolLibrary& lib) {
    const auto circuit = sheet("enclosing_taps",
        {part("U1", gate, "AND"), part("R1", resistor, "10k"), part("C1", capacitor, "100n"), part("R2", resistor, "10k")},
        gate_nets({{"+3V3", "power", Pins{{"U1", "5"}, {"R1", "1"}}}, {"GND", "ground", Pins{{"U1", "3"}, {"C1", "2"}}},
                   {"NODE", "signal", Pins{{"U1", "4"}, {"R1", "2"}, {"C1", "1"}, {"R2", "1"}}},
                   {"SENSE", "port", Pins{{"R2", "2"}}}}));
    for (const long foreign : {TRUNK_ENCLOSED_LIMIT, TRUNK_ENCLOSED_LIMIT + 1}) {
        Engine engine(circuit, lib);
        Trunk trunk; trunk.net = "NODE"; trunk.y = 101.6;
        for (long i = 0; i < foreign; ++i)
            engine.pl.boxes.push_back({10.16 + 10.16 * i, 20.32, 15.24 + 10.16 * i, 30.48, "body", "X" + std::to_string(i)});
        engine.pl.boxes.push_back({10.16, 40.64, 15.24, 50.8, "body", "R1"});
        engine.pl.boxes.push_back({20.32, 40.64, 25.4, 50.8, "body", "#PWR01"});
        engine.pl.plan("NODE", {{0.0, 0.0}, {76.2, 0.0}, {76.2, 101.6}});
        std::vector<double> nodes{76.2};
        const bool stubbed = engine._stub_enclosing_taps(trunk, {{0, 76.2, {0.0, 0.0}, "right"}}, nodes);
        const auto& path = engine.pl.plans.front().second.front();
        if (foreign <= TRUNK_ENCLOSED_LIMIT) {
            require(!stubbed && nodes.size() == 1 && path.size() == 3 && engine.pl.llabels.empty(),
                    "a bus tap within the enclosure limit was broken into a stub");
        } else {
            require(stubbed && nodes.empty() && path.size() == 2 && same(path.back().first, engine.sp.port_run)
                    && same(path.back().second, 0.0), "a bus tap that encloses unrelated symbols was not cut to a stub");
            require(engine.pl.llabels.size() == 1 && engine.pl.llabels.front().name == "NODE"
                    && engine.pl.label_bridged.count("NODE") == 1, "the stub of an enclosing bus tap carries no label");
        }
    }
}

void bus_drawn_one_way(SymbolLibrary& lib) {
    auto circuit = sheet("bus_drawn_one_way",
        {part("U1", "SN74HCT245PWR:SN74HCT245PWR", "driver"), part("U2", "SN74LVC125ADR:SN74LVC125ADR", "receiver")},
        {{"+5V", "power", Pins{{"U1", "20"}, {"U1", "1"}, {"U2", "14"}}},
         {"GND", "ground", Pins{{"U1", "10"}, {"U1", "19"}, {"U2", "7"}, {"U2", "1"}, {"U2", "4"}}},
         {"IN_A", "port", Pins{{"U1", "2"}}}, {"IN_B", "port", Pins{{"U1", "3"}}},
         {"OUT_A", "port", Pins{{"U2", "3"}}}, {"OUT_B", "port", Pins{{"U2", "6"}}},
         {"BUS_A", "signal", Pins{{"U1", "18"}, {"U2", "2"}}}, {"BUS_B", "signal", Pins{{"U1", "17"}, {"U2", "5"}}}});
    for (const char* number : {"4", "5", "6", "7", "8", "9", "11", "12", "13", "14", "15", "16"}) circuit.nc.push_back({"U1", number});
    for (const char* number : {"8", "9", "10", "11", "12", "13"}) circuit.nc.push_back({"U2", number});
    const auto labelled = [&](bool refine) {
        SchematicSpacing spacing; spacing.refine = refine;
        const auto page = place_and_route_schematic(circuit, lib, spacing);
        require(check_visual_geometry(page.geometry).ok, "the two-part bus sheet does not pass the visual check");
        return page.placement.label_bridged.count("BUS_A") + page.placement.label_bridged.count("BUS_B");
    };
    require(labelled(false) == 1, "the ordinary round no longer draws the crossed pair as one wire and one label pair");
    require(labelled(true) == 2, "the refine round left one member of a bus wired while its sibling is labelled");
}

CircuitSheetIr backup_selector(const std::string& name, bool three_way) {
    const std::string memory = "24AA025E48T-I_OT:24AA025E48T-I_OT", clock = "RV-3028-C7-32.768kHz-1ppm-TA-QC:RV-3028-C7-32.768kHz-1ppm-TA-QC";
    const std::string holder = "KH-CR1220-2:KH-CR1220-2", watchdog = "TPS3823-33DBVR:TPS3823-33DBVR";
    const std::string header = three_way ? "Connector_Generic:Conn_01x03" : "Connector_Generic:Conn_01x02";
    std::vector<CircuitNetIr> nets{
        {"+3V3_AUX", "power", Pins{{"U1", "6"}, {"U1", "5"}, {"C1", "1"}, {"U2", "7"}, {"R1", "1"}, {"C2", "1"}, {"U3", "5"}, {"C3", "1"}}},
        {"GND", "ground", Pins{{"U1", "2"}, {"U1", "4"}, {"C1", "2"}, {"U2", "5"}, {"U2", "8"}, {"C2", "2"}, {"BT1", "2"}, {"U3", "2"}, {"C3", "2"}, {"R3", "2"}}},
        {"BUS_SCL", "port", Pins{{"U1", "1"}, {"U2", "3"}}}, {"BUS_SDA", "port", Pins{{"U1", "3"}, {"U2", "4"}}},
        {"CLOCK_INT", "signal", Pins{{"U2", "2"}, {"R1", "2"}}}, {"KICK_IN", "signal", Pins{{"U3", "4"}, {"R2", "2"}}},
        {"KICK", "port", Pins{{"R2", "1"}}}, {"RESET_OUT", "port", Pins{{"U3", "1"}}}};
    if (three_way) {
        nets.push_back({"BACKUP_LOW", "signal", Pins{{"J1", "1"}, {"R3", "1"}}});
        nets.push_back({"BACKUP_CELL", "signal", Pins{{"BT1", "1"}, {"J1", "3"}}});
        nets.push_back({"BACKUP", "signal", Pins{{"U2", "6"}, {"J1", "2"}}});
    } else {
        nets.push_back({"BACKUP", "signal", Pins{{"U2", "6"}, {"BT1", "1"}, {"J1", "1"}}});
        nets.push_back({"BACKUP_LOW", "signal", Pins{{"J1", "2"}, {"R3", "1"}}});
    }
    auto circuit = sheet(name,
        {part("U1", memory, "memory"), part("C1", capacitor, "100n"), part("U2", clock, "clock"), part("R1", resistor, "10k"),
         part("C2", capacitor, "100n"), part("BT1", holder, "cell"), part("J1", header, "select"), part("R3", resistor, "10k"),
         part("U3", watchdog, "watchdog"), part("C3", capacitor, "100n"), part("R2", resistor, "1k")}, std::move(nets));
    circuit.nc = {{"U2", "1"}, {"U3", "3"}};
    return circuit;
}

void drawn_at_first_pitch(const CircuitSheetIr& circuit, SymbolLibrary& lib, const std::vector<std::pair<std::string, std::string>>& neighbours) {
    const auto page = place_and_route_schematic(circuit, lib, {}, 1);
    const auto visual = check_visual_geometry(page.geometry);
    require(visual.ok, circuit.name + ": " + visual.summary());
    const double reach = GRAFT_REACH.value * GRAFT_STEP + PASSIVE_SPAN;
    for (const auto& [hung, owner] : neighbours) {
        const auto& a = placed(page.placement, hung); const auto& b = placed(page.placement, owner);
        require(std::abs(a.x - b.x) + std::abs(a.y - b.y) <= reach, circuit.name + ": " + hung + " is not drawn beside " + owner);
    }
    for (const auto& p : circuit.parts) placed(page.placement, p.ref);
}

void backup_selector_three_way(SymbolLibrary& lib) {
    drawn_at_first_pitch(backup_selector("backup_selector_three_way", true), lib, {{"BT1", "J1"}, {"R3", "J1"}});
}

void backup_selector_in_series(SymbolLibrary& lib) {
    drawn_at_first_pitch(backup_selector("backup_selector_in_series", false), lib, {{"J1", "BT1"}, {"R3", "J1"}});
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: schematic_place_patterns_contracts REPOSITORY_ROOT");
        const fs::path root(argv[1]);
        SymbolLibrary lib(std::vector<fs::path>{root / "schgen/lib", root / "native/tests/data/schematic_place_chain/symbols"});
        ground_template(lib); side_pin_chain(lib); divider_ladder(lib); trunk_port_tail(lib);
        power_path(lib); compact_retry(lib); pack_relocates(lib); enclosing_taps(lib); bus_drawn_one_way(lib); pack_near_served_part(lib);
        SymbolLibrary headers(std::vector<fs::path>{root / "native/tests/data/schematic_place_patterns/symbols", root / "schgen/lib",
                                                    root / "native/tests/data/schematic_place_chain/symbols"});
        backup_selector_three_way(headers); backup_selector_in_series(headers);
        std::cout << "schematic place pattern contracts passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
