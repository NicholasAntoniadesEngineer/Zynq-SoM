#include "schgen/firmware_docs.hpp"
#include "schgen/json.hpp"
#include "schgen/power_checks.hpp"
#include "schgen/project.hpp"
#include <libxml/parser.h>
#include <libxml/tree.h>
#include <algorithm>
#include <climits>
#include <memory>
#include <set>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using namespace schgen;
namespace fs = std::filesystem;
const int expected_arguments = 2;
const double overload_load = 99;
const char* const fixture_folder = "native/tests/data/firmware_docs";
std::size_t assertions = 0;
void require(bool ok, const std::string& why) { ++assertions; if (!ok) throw std::runtime_error(why); }
const JsonNode& field(const JsonNode& n, const std::string& k) { auto p = object_field(n, k); if (!p) throw std::runtime_error("missing fixture field " + k); return *p; }
std::string str(const JsonNode& n, const std::string& k) { return field(n, k).string_value; }
double num(const JsonNode& n, const std::string& k) { return field(n, k).number_value; }
std::vector<std::string> strings(const JsonNode& n) { std::vector<std::string> out; for (const auto& v : n.array_value) out.push_back(v.string_value); return out; }
std::string read(const fs::path& p) { std::ifstream f(p, std::ios::binary); if (!f) throw std::runtime_error("cannot read " + p.string()); return {std::istreambuf_iterator<char>(f), {}}; }
template<class F> void throws(F fn, const std::string& fragment) {
    bool caught = false;
    try { fn(); } catch (const std::exception& e) { caught = true; require(std::string(e.what()).find(fragment) != std::string::npos, "unexpected exception: " + std::string(e.what())); }
    require(caught, "expected rejection: " + fragment);
}
PowerCheckResult power(const JsonNode& n) {
    PowerCheckResult out; out.errors = strings(field(n, "errors"));
    for (const auto& r : field(n, "regs").array_value) out.regs.push_back({static_cast<int>(num(r, "n")), str(r, "sheet"), str(r, "ref"), str(r, "value"), str(r, "kind"), str(r, "vin"), str(r, "vout"), num(r, "limit_a"), num(r, "eff"), str(r, "note"), num(r, "i_out"), num(r, "i_in")});
    for (const auto& b : field(n, "bridges").array_value) { const auto& a = b.array_value; out.bridges.push_back({a.at(0).string_value, a.at(1).string_value, a.at(2).string_value, a.at(3).string_value}); }
    return out;
}
void exact(const std::string& actual, const fs::path& expected) {
    const auto wanted = read(expected);
    if (actual != wanted) {
        const auto pos = std::mismatch(actual.begin(), actual.end(), wanted.begin(), wanted.end()).first - actual.begin();
        throw std::runtime_error("byte parity failed: " + expected.string() + " at byte " + std::to_string(pos));
    }
    ++assertions;
}
std::vector<std::string> outputs(const std::vector<PowerSequenceRow>& rows) {
    std::vector<std::string> out;
    for (const auto& row : rows) out.push_back(row.vout);
    return out;
}
bool svg_element(const xmlNode* node, const char* name) {
    return node && node->type == XML_ELEMENT_NODE && xmlStrEqual(node->name, BAD_CAST name) &&
        node->ns && xmlStrEqual(node->ns->href, BAD_CAST "http://www.w3.org/2000/svg");
}
std::size_t svg_rectangles(const std::string& text) {
    if (text.size() > INT_MAX) throw std::runtime_error("SVG exceeds parser input limit");
    std::unique_ptr<xmlParserCtxt, decltype(&xmlFreeParserCtxt)> context(xmlNewParserCtxt(), xmlFreeParserCtxt);
    if (!context) throw std::bad_alloc();
    std::unique_ptr<xmlDoc, decltype(&xmlFreeDoc)> doc(xmlCtxtReadMemory(context.get(), text.data(),
        static_cast<int>(text.size()), nullptr, nullptr,
        XML_PARSE_NONET | XML_PARSE_NOERROR | XML_PARSE_NOWARNING), xmlFreeDoc);
    if (!doc) throw std::runtime_error("invalid SVG XML");
    if (doc->intSubset || doc->extSubset) throw std::runtime_error("DTD is not allowed in SVG");
    const auto* root = xmlDocGetRootElement(doc.get());
    if (!svg_element(root, "svg")) throw std::runtime_error("SVG root/namespace missing");
    std::vector<const xmlNode*> pending{root}; std::size_t count = 0;
    while (!pending.empty()) {
        const auto* node = pending.back(); pending.pop_back();
        if (svg_element(node, "rect")) ++count;
        for (auto* child = node->children; child; child = child->next) pending.push_back(child);
    }
    return count;
}
void partition_and_determinism(const std::vector<ProjectCircuit>& sheets) {
    const auto policy = default_power_policy();
    const auto power = analyze_power(sheets, policy);
    const auto sequence = build_power_sequence(sheets, power, policy);
    const auto svg = render_power_sequence_svg(sequence, power.ok(), policy);
    const auto repeated_power = analyze_power(sheets, policy);
    const auto repeated_sequence = build_power_sequence(sheets, repeated_power, policy);
    const auto repeated_svg = render_power_sequence_svg(repeated_sequence, repeated_power.ok(), policy);
    const std::set<std::string> stage0(sequence.stage0.begin(), sequence.stage0.end());
    const auto chain_outputs = outputs(sequence.chain), module_outputs = outputs(sequence.modules);
    const std::set<std::string> chain(chain_outputs.begin(), chain_outputs.end());
    std::set<std::string> placed = stage0;
    placed.insert(chain.begin(), chain.end()); placed.insert(module_outputs.begin(), module_outputs.end());
    for (const auto& reg : power.regs) {
        require(placed.count(reg.vout) != 0, "power-sequence drops regulator output " + reg.vout);
        if (reg.kind == "load_switch") {
            require(stage0.count(reg.vout) == 0, reg.vout + " load switch is in stage-0");
            require(chain.count(reg.vout) == 0, reg.vout + " load switch is in the rail chain");
        }
    }
    for (const auto& [name, source] : policy.sources) {
        (void)source;
        require(stage0.count(name) != 0, "source " + name + " not in stage-0");
    }
    require(sequence.stage0 == repeated_sequence.stage0 && chain_outputs == outputs(repeated_sequence.chain) &&
            module_outputs == outputs(repeated_sequence.modules), "power-sequence build is not deterministic");
    require(svg == repeated_svg, "power-sequence SVG bytes are not deterministic");
    require(svg_rectangles(svg) >= power.regs.size(), "power-sequence SVG has fewer rail boxes than regulators");
}
void mutants(const std::vector<ProjectCircuit>& sheets, const PowerCheckResult& pr) {
    auto cyclic = pr; PowerReg cycle; cycle.vin = "+VBUS_IN"; cycle.vout = "+VBUS_IN"; cyclic.regs.push_back(cycle);
    throws([&] { build_power_sequence(sheets, cyclic); }, "reachable regulator cycle");
    auto seq = build_power_sequence(sheets, pr); require(!seq.chain.empty(), "chain fixture empty");
    seq.chain.front().load = overload_load; seq.chain.front().enable = "EN_<&>";
    seq.chain.front().vin = seq.stage0.at(0);
    const auto svg = render_power_sequence_svg(seq, false);
    require(svg.find("#dc2626") != std::string::npos && svg.find("(FAIL)") != std::string::npos && svg.find("EN_&amp;lt;&amp;amp;&amp;gt;") != std::string::npos, "SVG overload/status/escaping policy");
}
}

int main(int argc, char** argv) {
    try {
        if (argc != expected_arguments) throw std::runtime_error("usage: power_sequence_contracts REPOSITORY");
        const auto root = fs::absolute(argv[1]);
        for (const std::string name : {"carrier", "devkit_mini"}) {
            const auto dir = root / fixture_folder / name;
            const auto snapshot = parse_json_file((dir / "inputs.json").string());
            const auto sheets = load_project_circuits(resolve_project_paths(root, name));
            const auto pr = power(field(snapshot, "power"));
            const auto seq = build_power_sequence(sheets, pr);
            require(seq.stage0 == strings(field(field(snapshot, "sequence"), "stage0")), "stage0 ordering");
            exact(render_power_sequence_svg(seq, pr.ok()), dir / "power_sequence.svg");
            exact(render_power_sequence_svg(seq, false), dir / "power_sequence_fail.svg");
            const auto native_power = analyze_power(sheets);
            exact(render_power_sequence_svg(build_power_sequence(sheets, native_power), native_power.ok()), dir / "power_sequence.svg");
            partition_and_determinism(sheets);
            if (name == "carrier") mutants(sheets, pr);
            std::cout << name << ": power sequence matches the frozen drawings\n";
        }
        std::cout << assertions << " assertions passed\n";
        return 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
