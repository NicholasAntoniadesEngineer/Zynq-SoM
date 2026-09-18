#include "schgen/selftest.hpp"

#include "schematic_place_internal.hpp"
#include "schgen/validation.hpp"

#include <algorithm>
#include <set>

namespace schgen {
namespace {
using schematic_place::Engine;

std::string first_line(const std::string& text) { return text.substr(0, text.find('\n')); }
std::string last_line(const std::string& text) {
    const auto end = text.find_last_not_of('\n');
    if (end == std::string::npos) return {};
    const auto start = text.rfind('\n', end);
    return text.substr(start == std::string::npos ? 0 : start + 1,
        start == std::string::npos ? end + 1 : end - start);
}
// Python's [:90] counts code points, not UTF-8 bytes.
std::string short_diagnostic(const std::string& text) {
    std::size_t chars = 0, end = 0;
    for (; end < text.size(); ++end) {
        if ((static_cast<unsigned char>(text[end]) & 0xc0) != 0x80) {
            if (chars == 90) break;
            ++chars;
        }
    }
    return text.substr(0, end);
}

void apply_strict_shunt_mutation(Engine& engine) {
    // Exactly the old strict_run monkeypatch, including its intentionally
    // incorrect threshold of two OTHER multi-pin parts for every signal net.
    const std::set<std::string> multi(engine.multi.begin(), engine.multi.end());
    schematic_place::Refs strict;
    for (const auto& ref : engine.multi) {
        bool has_signal = false, all_shared = true;
        for (const auto& net : engine.c.nets) {
            if (net.net_class != "signal" && net.net_class != "port") continue;
            if (std::none_of(net.pins.begin(), net.pins.end(),
                    [&](const auto& pin) { return pin.ref == ref; })) continue;
            has_signal = true;
            std::set<std::string> others;
            for (const auto& pin : net.pins)
                if (pin.ref != ref && multi.count(pin.ref)) others.insert(pin.ref);
            if (others.size() < 2) all_shared = false;
        }
        if (has_signal && all_shared) strict.push_back(ref);
    }
    engine.shunts = std::move(strict);
}

SchematicPlacement build_strict_shunt_mutant(const CircuitSheetIr& circuit,
        SymbolLibrary& library, const SchematicSpacing& spacing) {
    auto split = schematic_place::split_auxiliary(circuit);
    Engine engine(split.first, library, spacing);
    apply_strict_shunt_mutation(engine);
    engine.pl = engine.run();
    schematic_place::add_probe_row(engine, circuit, split.second);
    schematic_place::center_on_sheet(engine.pl);
    return std::move(engine.pl);
}
}  // namespace

CircuitSheetIr selftest_rail_decoupling_fixture() {
    CircuitSheetIr c;
    c.schema = "schgen.circuit/1"; c.name = "selftest_railcap";
    c.title = "selftest rail-decoupling-cap fixture";
    c.parts = {
        {"R1", "Device:R", "49.9R", "Resistor_SMD:R_0603_1608Metric", {{"LCSC", "C114625"}}, {}, {}},
        {"C1", "Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", {{"LCSC", "C14663"}}, {}, {}}
    };
    c.nets = {
        {"SIG_A", "port", {{"R1", "1"}}},
        {"+3V3", "power", {{"R1", "2"}, {"C1", "1"}}},
        {"GND", "ground", {{"C1", "2"}}}
    };
    return c;
}

CircuitSheetIr selftest_esd_clamp_fixture() {
    CircuitSheetIr c;
    c.schema = "schgen.circuit/1"; c.name = "selftest_clamp";
    c.title = "selftest connector+ESD-clamp fixture";
    c.parts = {
        {"U1", "TPD4E02B04DQAR:TPD4E02B04DQAR", "TPD4E02B04DQAR", "TPD4E02B04DQAR:TPD4E02B04DQAR",
            {{"LCSC", "C106794"}},
            {{"IO1", {"1"}}, {"GND", {"8", "3"}}, {"IO2", {"2"}}, {"IO3", {"4"}},
             {"IO4", {"5"}}, {"NC", {"6", "7", "9", "10"}}},
            {"1", "10", "2", "3", "4", "5", "6", "7", "8", "9"}},
        {"J1", "Connector_Generic:Conn_01x04", "J",
            "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical", {}, {}, {}}
    };
    c.nets = {
        {"SIG_1", "port", {{"J1", "1"}, {"U1", "1"}}},
        {"SIG_2", "port", {{"J1", "2"}, {"U1", "2"}}},
        {"SIG_3", "port", {{"J1", "3"}, {"U1", "4"}}},
        {"SIG_4", "port", {{"J1", "4"}, {"U1", "5"}}},
        {"GND", "ground", {{"U1", "8"}, {"U1", "3"}}}
    };
    c.nc = {{"U1", "10"}, {"U1", "6"}, {"U1", "7"}, {"U1", "9"}};
    return c;
}

PlacerMutationProof selftest_rail_decoup_dropped(const CircuitSheetIr& fixture, SymbolLibrary& library) {
    // Invalid electrical input is a fixture/programming error, not a killed
    // placement mutation. Keep ValidationError and resolver/resource failures.
    validate_circuit(fixture, library);
    PlacerMutationProof result;
    try { build_schematic_placement(fixture, library); result.baseline_ok = true; }
    catch (const SchematicPlaceError& e) { result.baseline_failure = e.what(); }
    std::string by = "(no error)";
    try {
        auto split = schematic_place::split_auxiliary(fixture);
        Engine mutant(split.first, library);
        // Drop the rail-decoupling work queue, not the component or its nets.
        // For the canonical fixture this is equivalent to skipping
        // _rail_decoupling_columns: C1 remains electrically required and must
        // be rejected by the UNMODIFIED Engine::run missing-part gate.
        mutant.cluster.clear();
        ++result.mutation_attempts;
        mutant.pl = mutant.run();
        schematic_place::add_probe_row(mutant, fixture, split.second);
        schematic_place::center_on_sheet(mutant.pl);
    } catch (const SchematicPlaceError& e) {
        result.mutation_failure = e.what();
        result.mutation_killed = result.mutation_failure.find("unplaced") != std::string::npos;
        by = first_line(result.mutation_failure);
    }
    result.diagnostic = "rail_decoup_dropped: stub _rail_decoupling_columns -> the +3V3->GND cap is never drained\n"
        "            by placer missing-gate: " + short_diagnostic(by);
    return result;
}

PlacerMutationProof selftest_clamp_thresh_strict(const CircuitSheetIr& fixture, SymbolLibrary& library) {
    validate_circuit(fixture, library);
    PlacerMutationProof result;
    try { place_and_route_schematic(fixture, library); result.baseline_ok = true; }
    catch (const SchematicPlaceError& e) { result.baseline_failure = e.what(); }
    std::string by = "(no error)";
    const schematic_place::PageOperations operations{
        [&](const auto& c, auto& lib, const auto& spacing) {
            ++result.mutation_attempts;
            return build_strict_shunt_mutant(c, lib, spacing);
        },
        [](const auto& c, const auto& placement, auto& lib) { return route_schematic(c, placement, lib); },
        [](const auto& geometry) { return check_visual_geometry(geometry); }
    };
    try { schematic_place::place_and_route_with(fixture, library, {}, 8, operations); }
    catch (const SchematicPlaceError& e) {
        result.mutation_failure = e.what(); result.mutation_killed = true;
        by = last_line(result.mutation_failure);
    }
    result.diagnostic = "clamp_thresh_strict: revert the clamp shunt rule to >=2 -> the ESD array crosses lanes\n"
        "            by placer route/visual: " + short_diagnostic(by);
    return result;
}

PlacerMutationProof selftest_rail_decoup_dropped(SymbolLibrary& library) {
    return selftest_rail_decoup_dropped(selftest_rail_decoupling_fixture(), library);
}
PlacerMutationProof selftest_clamp_thresh_strict(SymbolLibrary& library) {
    return selftest_clamp_thresh_strict(selftest_esd_clamp_fixture(), library);
}
}  // namespace schgen
