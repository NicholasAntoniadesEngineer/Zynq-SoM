#include "placement_report_fixture.hpp"
#include "schgen/assembly_parts.hpp"
#include "schgen/assembly_refresh.hpp"
#include "schgen/run_config.hpp"

#include <fstream>
#include <iostream>
#include <sstream>

namespace {
using namespace schgen;
std::size_t checks = 0;
void require(bool test, const std::string& why) {
    ++checks;
    if (!test) throw std::runtime_error(why);
}
std::string read(const std::filesystem::path& file) {
    std::ifstream in(file, std::ios::binary);
    if (!in) throw std::runtime_error("cannot read " + file.string());
    std::stringstream text;
    text << in.rdbuf();
    return text.str();
}
std::string replaced(std::string text, const std::string& from, const std::string& to) {
    const std::size_t at = text.find(from);
    if (at == std::string::npos) throw std::runtime_error("mutation target missing: " + from);
    return text.replace(at, from.size(), to);
}
template <class F> void rejects(F action, const std::string& fragment, const std::string& why) {
    ++checks;
    try { action(); } catch (const std::exception& error) {
        if (std::string(error.what()).find(fragment) != std::string::npos) return;
        throw std::runtime_error(why + ": wrong message: " + error.what());
    }
    throw std::runtime_error(why + ": accepted");
}
bool failing(const AssemblyPartsVerdict& verdict, const std::string& fragment) {
    for (const std::string& line : verdict.failures) if (line.find(fragment) != std::string::npos) return true;
    return false;
}

void recorded(const std::filesystem::path& root) {
    const std::filesystem::path folder = root / "native/tests/data/assembly";
    const AssemblyTransport transport = [&](const AssemblyRequest& request) {
        const std::string& url = request.url;
        const std::string code = url.substr(url.find_last_of("/=") + 1);
        if (url.rfind(assembly_endpoint::search, 0) == 0) {
            const std::size_t at = request.body->find("\"keyword\":\"") + std::string("\"keyword\":\"").size();
            return read(folder / (request.body->substr(at, request.body->find('"', at) - at) + ".search.json"));
        }
        if (url.rfind(assembly_endpoint::part_page, 0) == 0) return read(folder / (code + ".page.html"));
        if (url.rfind(assembly_endpoint::lcsc_detail, 0) == 0) return read(folder / (code + ".lcsc.json"));
        throw std::runtime_error("unexpected request " + url);
    };
    const std::string when = "2026-11-21T00:00:00Z";
    const AssemblyPart resistor = read_assembly_part("C22775", transport, when);
    require(resistor.in_library && resistor.part_class == "basic" && resistor.assembly_type == "SMT Assembly" && resistor.pcba_type == "economic_and_standard" && resistor.buyable, "recorded basic resistor");
    require(resistor.assembly_mode == "smtWeld" && resistor.jlc_stock > 0 && resistor.lcsc_stock.value_or(0) > 0 && resistor.read_utc == when && resistor.source_urls.size() == 3, "recorded resistor stock, mode and sources");
    const AssemblyPart plug = read_assembly_part("C98732", transport, when);
    require(plug.part_class == "extended" && plug.assembly_type == "Wave Soldering" && plug.assembly_mode == "manualWeld", "recorded wave-soldered part");
    const AssemblyPart split = read_assembly_part("C22775", [&](const AssemblyRequest& r) -> std::string {
        if (r.url.rfind(assembly_endpoint::part_page, 0) != 0) return transport(r);
        return replaced(replaced(read(folder / "C22775.page.html"), "smtWeld", "smtWe\"])</script><script>self.__next_f.push([1,\"ld"), "moistureSensitivityLevelEn\\\":null", "moistureSensitivityLevelEn\\\":\\\"M\"])</script><script>self.__next_f.push([1,\"SL 1\\\""); }, when);
    require(split.assembly_mode == "smtWeld" && split.msl == "MSL 1", "a value split across the page's streaming chunks is read whole");
    const AssemblyPart absent = read_assembly_part("C42440491", transport, when);
    require(!absent.in_library && !absent.buyable && absent.lcsc_stock.value_or(0) > 0, "a code the library lacks is a row that says so");
    rejects([&] { read_assembly_part("C22775", [&](const AssemblyRequest& r) -> std::string {
        if (r.url.rfind(assembly_endpoint::part_page, 0) == 0) return "<html></html>";
        return transport(r); }, when); }, "does not show its assembly type", "a page without the facts was accepted");
    rejects([&] { read_assembly_part("C22775", [&](const AssemblyRequest&) -> std::string { throw std::runtime_error("offline"); }, when); }, "offline", "a network failure was swallowed");

    AssemblyFacts old;
    old.parts["C98732"] = plug;
    old.parts["C98732"].jlc_stock = 1;
    old.parts["C98732"].route = "pre_order";
    old.parts["C00000"] = resistor;
    const auto result = refresh_assembly_facts(old, {"C98732", "C22775", "C00000", "C22775"}, [&](const AssemblyRequest& r) -> std::string {
        if (r.url.find("C00000") != std::string::npos || (r.body && r.body->find("C00000") != std::string::npos)) throw std::runtime_error("offline");
        return transport(r); }, [&] { return when; });
    require(result.facts.parts.at("C98732").jlc_stock == plug.jlc_stock && result.facts.parts.at("C98732").route == "pre_order", "refresh updates a row and keeps its hand-declared route");
    require(result.facts.parts.count("C22775") == 1 && result.facts.parts.at("C00000").jlc_stock == resistor.jlc_stock, "refresh adds a row and keeps the old row of a code it could not read");
    require(result.failures.size() == 1 && result.failures.front().find("C00000") != std::string::npos && result.failures.front().find("old row is kept") != std::string::npos, "the failed code is reported");
    require(result.changes.size() == 2, "changes are listed once per code");
    const std::string text = assembly_facts_text(result.facts);
    const AssemblyFacts again = parse_assembly_facts(parse_json_text(text), "round trip");
    require(assembly_facts_text(again) == text, "the facts text is stable");
    require(text.find("\"C00000\"") < text.find("\"C22775\"") && text.find("\"C22775\"") < text.find("\"C98732\""), "rows are sorted");
}

void loader(const std::filesystem::path& root) {
    const std::string text = read(root / "parts/assembly_facts.json");
    const AssemblyFacts facts = load_assembly_facts_in(root / "parts");
    require(facts.unplaced_classes.count(PartClass::test_point) && facts.unplaced_classes.count(PartClass::mounting_hole) && facts.unplaced_classes.count(PartClass::fiducial), "not-placed classes");
    require(assembly_facts_text(facts) == text, "the committed facts file is in the writer's canonical form");
    for (const auto& [code, part] : facts.parts) require(!part.read_utc.empty() && !part.source_urls.empty(), code + " row is dated and sourced");
    const auto parse = [](const std::string& body) { return parse_assembly_facts(parse_json_text(body), "assembly_facts.json"); };
    rejects([&] { parse(replaced(text, "\"parts\"", "\"surprise\": 1, \"parts\"")); }, "surprise", "unknown key");
    rejects([&] { parse(replaced(text, "schgen.assembly_facts/1", "schgen.assembly_facts/2")); }, "unknown schema", "schema");
    rejects([&] { parse(replaced(text, ", \"owner_fits\": ", ", \"surprise_fits\": ")); }, "surprise_fits", "a need without its owner decision field");
    rejects([&] { parse(replaced(text, "\"test_point\"", "\"widget\"")); }, "widget", "unknown class");
    rejects([&] { parse(replaced(text, "\"parts\": {", "\"parts\": {\"X1\": {}, ")); }, "not an LCSC code", "bad code");
    rejects([&] { parse(replaced(text, "\"read_utc\"", "\"read\"")); }, "read", "missing time stamp");
    rejects([&] { parse(replaced(text, "\"read_utc\": \"2", "\"read_utc\": \"x")); }, "not a UTC time stamp", "bad time stamp");
    rejects([&] { parse(replaced(text, "\"in_library\": true", "\"in_library\": 1")); }, "in_library", "wrong type");
}

void board(const std::filesystem::path& root, const std::string& project) {
    apply_run_config(root / run_config_file, project);
    const FabricatorProfile& profile = board_fabrication().profile;
    const int builds = board_fabrication().config.build_count;
    const AssemblyFacts facts = load_assembly_facts_in(root / "parts");
    auto scene = placement_report_fixture::scene(root, project);
    scene.model.origin_x = -1;
    scene.model.origin_y = 0;
    scene.model.board_h = 1e3;
    const OrderFiles files = build_order_files(scene.sheets, scene.index, scene.model, profile, facts);
    const PartFacts& part_facts = default_part_facts();
    const auto base = check_assembly_parts(scene.sheets, files, facts, part_facts, builds);
    for (const std::string& line : base.failures) std::cout << project << " assembly_parts FAIL: " << line << '\n';
    for (const std::string& line : base.advisories) std::cout << project << ' ' << line << '\n';
    require(!files.lines.empty() && !base.facts.empty(), project + " the gate read the BOM");

    const BomRow* coded = nullptr;
    for (const BomRow& line : files.lines) if (!line.lcsc.empty() && facts.parts.count(line.lcsc) && facts.parts.at(line.lcsc).in_library) { coded = &line; break; }
    require(coded != nullptr, project + " has a coded line");
    auto no_code = files;
    for (BomRow& line : no_code.lines) if (line.lcsc == coded->lcsc) line.lcsc.clear();
    require(failing(check_assembly_parts(scene.sheets, no_code, facts, part_facts, builds), "has no JLCPCB part code"), project + " mutation: a BOM line with no code");
    auto lost = facts;
    lost.parts.erase(coded->lcsc);
    require(failing(check_assembly_parts(scene.sheets, files, lost, part_facts, builds), "has no row in"), project + " mutation: a code missing from the facts file");
    auto outside = facts;
    outside.parts.at(coded->lcsc).in_library = false;
    require(failing(check_assembly_parts(scene.sheets, files, outside, part_facts, builds), "not in the JLCPCB assembly library"), project + " mutation: a part not in the library");
    auto unbuyable = facts;
    unbuyable.parts.at(coded->lcsc).buyable = false;
    require(failing(check_assembly_parts(scene.sheets, files, unbuyable, part_facts, builds), "not buyable"), project + " mutation: a part not buyable");
    auto twice = files;
    twice.lines.push_back(*coded);
    require(failing(check_assembly_parts(scene.sheets, twice, facts, part_facts, builds), "BOM lines"), project + " mutation: one code on two lines");
    auto spelled = scene.sheets;
    bool changed = false;
    for (CircuitSheetIr& sheet : spelled)
        for (CircuitPartIr& part : sheet.parts)
            if (!changed && part.lib_id == "Device:R" && part.value == "10k") { part.value = "10K0"; changed = true; }
    if (changed) require(failing(check_assembly_parts(spelled, files, facts, part_facts, builds), "one value spelled"), project + " mutation: one value spelled two ways");
    auto short_of_stock = facts;
    short_of_stock.parts.at(coded->lcsc).jlc_stock = 0;
    const auto stock = check_assembly_parts(scene.sheets, files, short_of_stock, part_facts, builds);
    require(stock.ok() == base.ok() && !stock.advisories.empty() && stock.advisories.front().find("out of stock today") != std::string::npos, project + " stock is an advisory, not a failure");
    auto placed = files;
    placed.placed.insert("ZZ99999");
    require(failing(check_assembly_parts(scene.sheets, placed, facts, part_facts, builds), "BOM lacks"), project + " mutation: a placed part the BOM lacks");
    auto with_need = facts;
    with_need.needs[PartClass::resistor] = {"shunt for the test", {}, {}};
    require(failing(check_assembly_parts(scene.sheets, files, with_need, part_facts, builds), "not a placed BOM part"), project + " mutation: a loose item the board needs");
    with_need.needs[PartClass::resistor].owner_fits = "decision recorded for the test";
    const auto decided = check_assembly_parts(scene.sheets, files, with_need, part_facts, builds);
    require(!failing(decided, "not a placed BOM part") && decided.report().find("NOT FITTED BY THE ASSEMBLER, by decision: shunt for the test") != std::string::npos &&
            decided.report().find("decision recorded for the test") != std::string::npos, project + ": an item the owner fits by recorded decision is stated, not failed");
}
}

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("repo root required");
        recorded(argv[1]);
        loader(argv[1]);
        board(argv[1], "carrier");
        board(argv[1], "devkit_mini");
        std::cout << "assembly: " << checks << " assertions passed\n";
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
