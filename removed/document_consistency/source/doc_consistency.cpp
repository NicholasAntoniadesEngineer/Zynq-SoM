#include "schgen/doc_consistency.hpp"

#include <libxml/parser.h>
#include <libxml/tree.h>

#include <algorithm>
#include <climits>
#include <fstream>
#include <iterator>
#include <memory>
#include <regex>
#include <set>

namespace schgen {
namespace {
std::optional<std::string> read_document(const std::filesystem::path& path) {
    if (!std::filesystem::is_regular_file(path)) return std::nullopt;
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("doc consistency: cannot read " + path.string());
    std::string bytes{std::istreambuf_iterator<char>(input), {}};
    if (input.bad()) throw std::runtime_error("doc consistency: read failed " + path.string());
    return bytes;
}
std::vector<std::string> lines(const std::string& text) {
    // Python str.splitlines(), including Unicode NEL/line/paragraph separators.
    std::vector<std::string> out; std::size_t start = 0;
    for (std::size_t i = 0; i < text.size();) {
        const auto c = static_cast<unsigned char>(text[i]); std::size_t width = 0;
        if (c == '\r') width = i + 1 < text.size() && text[i + 1] == '\n' ? 2 : 1;
        else if (c == '\n' || c == '\v' || c == '\f' || (c >= 0x1c && c <= 0x1e)) width = 1;
        else if (text.compare(i, 2, "\xc2\x85") == 0) width = 2;
        else if (text.compare(i, 3, "\xe2\x80\xa8") == 0 || text.compare(i, 3, "\xe2\x80\xa9") == 0) width = 3;
        if (width) { out.push_back(text.substr(start, i - start)); i += width; start = i; }
        else ++i;
    }
    if (start < text.size()) out.push_back(text.substr(start));
    return out;
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
} // namespace

const std::vector<std::string>& doc_consistency_families() {
    static const std::vector<std::string> names{
        "test_packet_files_present", "test_design_spec_rail_table_rails_are_real",
        "test_design_spec_core_rails_documented", "test_compliance_cited_sheets_exist",
        "test_compliance_covers_every_required_interface", "test_power_sequence_partitions_every_regulator",
        "test_power_sequence_build_is_deterministic", "test_power_sequence_svg_byte_deterministic",
        "test_design_spec_references_the_three_diagrams"};
    return names;
}

DocConsistencyInput build_doc_consistency_input(std::vector<ProjectCircuit> sheets,
    std::optional<std::string> design_spec, std::optional<std::string> compliance, const PowerPolicy& policy) {
    DocConsistencyInput out;
    out.sheets = std::move(sheets); out.design_spec = std::move(design_spec); out.compliance = std::move(compliance);
    out.power = analyze_power(out.sheets, policy);
    out.sequence = build_power_sequence(out.sheets, out.power, policy);
    out.svg = render_power_sequence_svg(out.sequence, out.power.ok(), policy);
    const auto repeated_power = analyze_power(out.sheets, policy);
    out.repeated_sequence = build_power_sequence(out.sheets, repeated_power, policy);
    out.repeated_svg = render_power_sequence_svg(out.repeated_sequence, repeated_power.ok(), policy);
    return out;
}
DocConsistencyInput load_doc_consistency_input(const ProjectPaths& paths, const PowerPolicy& policy) {
    return build_doc_consistency_input(load_project_circuits(paths),
        read_document(paths.project_root / "docs/DESIGN_SPEC.md"),
        read_document(paths.project_root / "docs/COMPLIANCE.md"), policy);
}

DocConsistencyResult check_doc_consistency(const DocConsistencyInput& input, const PowerPolicy& policy) {
    DocConsistencyResult out; out.checked_families = doc_consistency_families();
    const auto fail = [&](std::size_t family, const std::string& detail) {
        out.issues.push_back({out.checked_families.at(family), detail});
    };
    if (!input.design_spec) fail(0, "DESIGN_SPEC.md missing or not a file");
    if (!input.compliance) fail(0, "COMPLIANCE.md missing or not a file");
    const auto design = input.design_spec.value_or(""), compliance = input.compliance.value_or("");
    std::set<std::string> known, tables, cited, names;
    for (const auto& [name, source] : policy.sources) { (void)source; known.insert(name); }
    for (const auto& [name, load] : input.power.rails) { (void)load; known.insert(name); }
    for (const auto& reg : input.power.regs) { known.insert(reg.vin); known.insert(reg.vout); }
    for (const auto& bridge : input.power.bridges) { known.insert(bridge.from); known.insert(bridge.to); }
    for (const auto& sheet : input.sheets) names.insert(sheet.name);
    static const std::regex rail(R"(\+[A-Z0-9_]+)"), citation(R"(`([a-z0-9_]+)`)");
    for (const auto& line : lines(design)) if (!line.empty() && line.front() == '|') {
        const auto end = line.find('|', 1);
        const auto first = line.substr(1, end == std::string::npos ? end : end - 1);
        for (std::sregex_iterator it(first.begin(), first.end(), rail), stop; it != stop; ++it)
            tables.insert(it->str());
    }
    if (tables.empty()) fail(1, "no rail tokens found in DESIGN_SPEC tables");
    for (const auto& name : tables) if (!known.count(name)) fail(1, "DESIGN_SPEC names unknown rail " + name);
    for (const auto* name : {"+VIN", "+5V", "+3V3", "+1V8", "+5V_SOM", "+3V3_SC", "+2V5_VADJ"})
        if (design.find(name) == std::string::npos) fail(2, "DESIGN_SPEC does not mention core rail " + std::string(name));
    for (const auto& line : lines(compliance))
        if (line.compare(0, 3, "## ") == 0 && line.find("sheet") != std::string::npos)
            for (std::sregex_iterator it(line.begin(), line.end(), citation), stop; it != stop; ++it)
                cited.insert((*it)[1].str());
    if (cited.empty()) fail(3, "no sheet citations found in COMPLIANCE headers");
    for (const auto& name : cited) if (!names.count(name)) fail(3, "COMPLIANCE cites unknown sheet " + name);
    for (const auto* name : {"HDMI", "Ethernet", "USB 2.0", "MIPI CSI-2", "USB-PD", "bank-35 IO"})
        if (compliance.find(name) == std::string::npos) fail(4, "COMPLIANCE missing interface " + std::string(name));
    const std::set<std::string> stage0(input.sequence.stage0.begin(), input.sequence.stage0.end());
    const auto chain_outputs = outputs(input.sequence.chain), module_outputs = outputs(input.sequence.modules);
    const std::set<std::string> chain(chain_outputs.begin(), chain_outputs.end());
    std::set<std::string> placed = stage0;
    placed.insert(chain.begin(), chain.end()); placed.insert(module_outputs.begin(), module_outputs.end());
    for (const auto& reg : input.power.regs) {
        if (!placed.count(reg.vout)) fail(5, "power-sequence drops regulator output " + reg.vout);
        if (reg.kind == "load_switch") {
            if (stage0.count(reg.vout)) fail(5, reg.vout + " load switch is in stage-0");
            if (chain.count(reg.vout)) fail(5, reg.vout + " load switch is in the rail chain");
        }
    }
    for (const auto& [name, source] : policy.sources) {
        (void)source;
        if (!stage0.count(name)) fail(5, "source " + name + " not in stage-0");
    }
    if (input.sequence.stage0 != input.repeated_sequence.stage0 ||
        chain_outputs != outputs(input.repeated_sequence.chain) ||
        module_outputs != outputs(input.repeated_sequence.modules)) fail(6, "power-sequence build is not deterministic");
    if (input.svg != input.repeated_svg) fail(7, "power-sequence SVG bytes are not deterministic");
    try {
        out.svg_rectangles = svg_rectangles(input.svg);
        if (out.svg_rectangles < input.power.regs.size()) fail(7, "power-sequence SVG has fewer rail boxes than regulators");
    } catch (const std::runtime_error& error) { fail(7, error.what()); }
    for (const auto* artifact : {"block_diagram.svg", "power_tree.svg", "power_sequence.svg"})
        if (design.find(artifact) == std::string::npos) fail(8, "DESIGN_SPEC does not reference " + std::string(artifact));
    out.known_rails.assign(known.begin(), known.end()); out.table_rails.assign(tables.begin(), tables.end());
    out.cited_sheets.assign(cited.begin(), cited.end());
    return out;
}
} // namespace schgen
