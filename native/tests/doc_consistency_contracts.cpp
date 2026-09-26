#include "schgen/doc_consistency.hpp"
#include "schgen/project_authoring.hpp"

#include <algorithm>
#include <fstream>
#include <iostream>
#include <iterator>
#include <set>
#include <sstream>
#include <unistd.h>

namespace {
namespace fs = std::filesystem;
using namespace schgen;
std::size_t assertions = 0;
void require(bool ok, const std::string& message) {
    ++assertions;
    if (!ok) throw std::runtime_error(message);
}
const JsonNode& field(const JsonNode& node, const std::string& key) {
    const auto* value = object_field(node, key);
    require(value != nullptr, "missing independent reference " + key);
    return *value;
}
std::string str(const JsonNode& node, const std::string& key) { return field(node, key).string_value; }
std::vector<std::string> strings(const JsonNode& node) {
    std::vector<std::string> out;
    for (const auto& value : node.array_value) out.push_back(value.string_value);
    return out;
}
std::string read(const fs::path& path) {
    std::ifstream input(path, std::ios::binary); require(bool(input), "read " + path.string());
    return {std::istreambuf_iterator<char>(input), {}};
}
void write(const fs::path& path, const std::string& text) {
    fs::create_directories(path.parent_path());
    std::ofstream output(path, std::ios::binary); output << text; output.close();
    require(bool(output), "write private output " + path.string());
}
std::set<std::string> failed(const DocConsistencyResult& result) {
    std::set<std::string> out;
    for (const auto& issue : result.issues) out.insert(issue.family);
    return out;
}
std::string summary(const DocConsistencyResult& result) {
    std::string out;
    for (const auto& issue : result.issues) out += issue.family + ": " + issue.detail + '\n';
    return out;
}
void replace_all(std::string& text, const std::string& old, const std::string& value) {
    std::size_t pos = 0, count = 0;
    while ((pos = text.find(old, pos)) != std::string::npos) {
        text.replace(pos, old.size(), value); pos += value.size(); ++count;
    }
    require(count != 0, "mutation did not change target " + old);
}
template<class Predicate> void remove_lines(std::string& text, Predicate predicate) {
    std::istringstream input(text); std::string line, out;
    while (std::getline(input, line)) if (!predicate(line)) out += line + '\n';
    require(out != text, "line-removal mutation did not change target"); text = out;
}
void apply(DocConsistencyInput& in, const JsonNode& test) {
    const auto op = str(test, "op");
    if (op == "baseline") return;
    if (op == "missing_design") in.design_spec.reset();
    else if (op == "missing_compliance") in.compliance.reset();
    else if (op == "design_no_tables") remove_lines(*in.design_spec, [](const auto& line) { return !line.empty() && line.front() == '|'; });
    else if (op == "unknown_rail") *in.design_spec += "\n| +FICTITIOUS | injected |\n";
    else if (op == "remove_core") replace_all(*in.design_spec, "+2V5_VADJ", "removed_core");
    else if (op == "unknown_sheet") *in.compliance += "\n## MUTANT sheet `nonexistent_sheet`\n";
    else if (op == "remove_citations") remove_lines(*in.compliance, [](const auto& line) {
        return line.compare(0, 3, "## ") == 0 && line.find("sheet") != std::string::npos;
    });
    else if (op == "remove_interface") replace_all(*in.compliance, "USB 2.0", "removed_interface");
    else if (op == "remove_diagram") replace_all(*in.design_spec, "power_sequence.svg", "removed_diagram");
    else if (op == "lost_output") {
        const auto rail = str(test, "rail");
        for (auto* seq : {&in.sequence, &in.repeated_sequence}) {
            seq->stage0.erase(std::remove(seq->stage0.begin(), seq->stage0.end(), rail), seq->stage0.end());
            for (auto* rows : {&seq->chain, &seq->modules}) rows->erase(std::remove_if(rows->begin(), rows->end(),
                [&](const auto& row) { return row.vout == rail; }), rows->end());
        }
    } else if (op == "load_switch_stage0") {
        require(!in.sequence.modules.empty(), "real carrier must have load switches");
        in.sequence.stage0.push_back(in.sequence.modules.front().vout);
        in.repeated_sequence.stage0.push_back(in.sequence.modules.front().vout);
    } else if (op == "load_switch_chain") {
        in.sequence.chain.push_back(in.sequence.modules.front());
        in.repeated_sequence.chain.push_back(in.sequence.modules.front());
    } else if (op == "missing_source") {
        const auto rail = str(test, "rail");
        for (auto* seq : {&in.sequence, &in.repeated_sequence})
            seq->stage0.erase(std::remove(seq->stage0.begin(), seq->stage0.end(), rail), seq->stage0.end());
    } else if (op == "stage0_nondeterminism") std::reverse(in.repeated_sequence.stage0.begin(), in.repeated_sequence.stage0.end());
    else if (op == "chain_nondeterminism") std::reverse(in.repeated_sequence.chain.begin(), in.repeated_sequence.chain.end());
    else if (op == "modules_nondeterminism") std::reverse(in.repeated_sequence.modules.begin(), in.repeated_sequence.modules.end());
    else if (op == "svg_nondeterminism") in.repeated_svg += '\n';
    else if (op == "invalid_svg") in.svg = in.repeated_svg = "<svg";
    else if (op == "few_rects") in.svg = in.repeated_svg = "<svg xmlns=\"http://www.w3.org/2000/svg\"/>";
    else if (op == "unicode_lines") {
        replace_all(*in.design_spec, "\n", "\xe2\x80\xa8"); replace_all(*in.compliance, "\n", "\r\n");
    } else if (op == "ignored_citations") *in.compliance += "\n### Other sheet `nonexistent_sheet`\n##not-a-header sheet `also_missing`\n";
    else if (op == "rail_second_column") *in.design_spec += "\n| note | +FICTITIOUS |\n";
    else if (op == "new_known_rail") {
        in.power.rails.emplace_back("+NEW_RAIL", 0); *in.design_spec += "\n| +NEW_RAIL | added real rail |\n";
    } else throw std::runtime_error("unknown independently captured mutation " + op);
}
void captured_mutants(const DocConsistencyInput& original, const JsonNode& fixture) {
    std::set<std::string> killed;
    for (const auto& test : field(fixture, "cases").array_value) {
        auto changed = original; apply(changed, test);
        std::set<std::string> expected;
        for (const auto& [family, error] : field(test, "failures").object_value) { (void)error; expected.insert(family); }
        const auto result = check_doc_consistency(changed);
        require(failed(result) == expected, str(test, "op") + ": differs from original Python failure families:\n" + summary(result));
        require(result.checked_families == doc_consistency_families(), "mutant dropped a contract family");
        require(result.ok() == expected.empty(), "aggregate verdict lost hard failures");
        killed.insert(expected.begin(), expected.end());
    }
    require(killed == std::set<std::string>(doc_consistency_families().begin(), doc_consistency_families().end()),
            "independent negative cases must kill all nine families");
}
void parser_hardening(const DocConsistencyInput& original) {
    const auto rejected = [&](const std::string& text, const std::string& message) {
        auto in = original; in.svg = in.repeated_svg = text;
        const auto result = check_doc_consistency(in);
        require(failed(result) == std::set<std::string>{doc_consistency_families().at(7)}, message);
    };
    std::string rectangles, comments;
    for (std::size_t i = 0; i <= original.power.regs.size(); ++i) { rectangles += "<rect/>"; comments += "<!-- <rect/> -->"; }
    rejected("<not-svg>" + rectangles + "</not-svg>", "well-formed non-SVG document must not pass");
    rejected("<svg xmlns=\"http://www.w3.org/2000/svg\">" + comments + "</svg>", "comment-spoofed rail boxes must not pass");
    rejected("<svg xmlns=\"http://www.w3.org/2000/svg\"><g xmlns=\"urn:foreign\">" + rectangles + "</g></svg>",
             "foreign elements must not stand in for SVG rail boxes");
    rejected("<!DOCTYPE svg [<!ENTITY data SYSTEM \"file:///nonexistent-doc-consistency-secret\">]>"
             "<svg xmlns=\"http://www.w3.org/2000/svg\"><text>&data;</text>" + rectangles + "</svg>",
             "DTD/external-entity documents must not pass");
    auto in = original;
    in.svg = in.repeated_svg = "<s:svg xmlns:s=\"http://www.w3.org/2000/svg\"><s:g>";
    for (std::size_t i = 0; i <= in.power.regs.size(); ++i) in.svg += "<s:rect/>";
    in.svg += "</s:g></s:svg>"; in.repeated_svg = in.svg;
    require(check_doc_consistency(in).ok(), "valid prefixed/nested SVG rectangles rejected");
    auto policy = default_power_policy(); policy.sources.push_back({"+EXTRA_SOURCE", {1, 1, "mutant"}});
    in = original;
    require(failed(check_doc_consistency(in, policy)) == std::set<std::string>{doc_consistency_families().at(5)},
            "source membership was hard-coded instead of using the supplied live policy");
    in.sequence.stage0.push_back("+EXTRA_SOURCE"); in.repeated_sequence.stage0.push_back("+EXTRA_SOURCE");
    *in.design_spec += "\n| +EXTRA_SOURCE | actual new policy source |\n";
    require(check_doc_consistency(in, policy).ok(), "new policy source is missing from known rails");
    in = original; in.power.bridges.push_back({"mutant", "R999", "+NEW_FROM", "+NEW_TO"});
    *in.design_spec += "\n| +NEW_FROM +NEW_TO | actual bridge endpoints |\n";
    require(check_doc_consistency(in).ok(), "live bridge endpoints missing from known rails");
}
void filesystem_boundary(const fs::path& repo, const fs::path& scratch, const DocConsistencyInput& baseline) {
    auto paths = resolve_project_paths(repo, "carrier");
    const auto original_paths = paths;
    paths.project_root = scratch / "json-only/carrier"; paths.subsystems_dir = paths.project_root / "subsystems";
    for (const auto& source : inventory_project_circuits(original_paths))
        write(paths.subsystems_dir / source.name / "circuit.json", read(source.path));
    write(paths.project_root / "docs/DESIGN_SPEC.md", *baseline.design_spec);
    write(paths.project_root / "docs/COMPLIANCE.md", *baseline.compliance);
    const auto loaded = load_doc_consistency_input(paths);
    require(check_doc_consistency(loaded).ok(), "JSON-only, Python-free document loader failed");
    require(loaded.svg == baseline.svg, "isolated project changed power-sequence bytes");
    const auto design = paths.project_root / "docs/DESIGN_SPEC.md";
    fs::remove(design); fs::create_directory(design);
    require(!load_doc_consistency_input(paths).design_spec, "directory mistaken for document file");
    require(failed(check_doc_consistency(load_doc_consistency_input(paths))).count(doc_consistency_families().front()) == 1,
            "non-file design spec did not fail packet presence");
}
} // namespace
int main(int argc, char** argv) {
    try {
        require(argc == 3, "usage: doc_consistency_contracts REPOSITORY PRIVATE_SCRATCH");
        const auto repo = fs::absolute(argv[1]), root = fs::absolute(argv[2]);
        fs::create_directories(root); auto pattern = (root / "run-XXXXXX").string();
        const char* created = ::mkdtemp(pattern.data()); require(created != nullptr, "private output directory");
        const fs::path scratch = created;
        const auto reference = parse_json_file((repo / "native/tests/data/doc_consistency/python_reference.json").string());
        require(doc_consistency_families() == strings(field(reference, "families")), "nine original test families changed");
        const auto paths = resolve_project_paths(repo, "carrier");
        const auto input = load_doc_consistency_input(paths);
        const auto result = check_doc_consistency(input);
        require(result.ok(), "real authored carrier document checks failed:\n" + summary(result));
        require(result.checked_families.size() == 9, "all nine families required");
        require(result.known_rails == strings(field(reference, "known_rails")), "known rails differ from independent Python");
        require(result.table_rails == strings(field(reference, "table_rails")), "table selection differs from independent Python");
        require(result.cited_sheets == strings(field(reference, "cited_sheets")), "sheet citation selection differs from independent Python");
        const auto legacy = repo / "native/tests/data/firmware_docs/carrier";
        require(input.svg == read(legacy / "power_sequence.svg"), "existing independent legacy SVG bytes changed");
        write(scratch / "first.svg", input.svg); write(scratch / "second.svg", input.repeated_svg);
        require(read(scratch / "first.svg") == read(scratch / "second.svg"), "published private SVG files differ");
        require(result.svg_rectangles >= input.power.regs.size(), "real SVG dropped regulator boxes");
        const auto frozen = parse_json_file((legacy / "inputs.json").string());
        const auto& expected_sequence = field(frozen, "sequence");
        require(input.sequence.stage0 == strings(field(expected_sequence, "stage0")), "existing independent stage-0 oracle changed");
        for (const auto& [name, actual] : std::vector<std::pair<std::string, std::vector<PowerSequenceRow>>>{{"chain", input.sequence.chain}, {"modules", input.sequence.modules}}) {
            const auto& expected = field(expected_sequence, name).array_value;
            require(actual.size() == expected.size(), "independent sequence partition size changed");
            for (std::size_t i = 0; i < actual.size(); ++i) require(actual[i].vout == str(expected[i], "vout"), "independent sequence rail order changed");
        }
        captured_mutants(input, reference); parser_hardening(input);
        // Also test freshly executed C++ authoring factories, not just retained
        // circuit JSON, without modifying either catalog or authored packages.
        require(open_part_catalog(paths.part_catalog_file.string()), "open existing part catalog read-only");
        ProjectAuthoringInput authoring; authoring.project_root = paths.project_root; authoring.context = make_authoring_context(repo);
        std::vector<ProjectCircuit> authored;
        for (const auto& factory : native_project_factories("carrier", authoring)) authored.push_back({factory.name, {}, factory.circuit()});
        require(authored.size() == input.sheets.size(), "fresh native authoring omitted carrier sheets");
        const auto fresh = build_doc_consistency_input(std::move(authored), input.design_spec, input.compliance);
        require(check_doc_consistency(fresh).ok(), "fresh native-authored carrier failed document contracts");
        require(fresh.svg == input.svg, "fresh authoring changed independently verified power sequence");
        require(close_part_catalog(), "close read-only part catalog");
        filesystem_boundary(repo, scratch, input);
        std::cout << "PASS: " << assertions << " doc-consistency assertions; all 9 families; "
                  << field(reference, "cases").array_value.size() << " independent Python mutation cases; "
                  << result.known_rails.size() << " real rails, " << result.cited_sheets.size() << " cited sheets, "
                  << input.power.regs.size() << " regulators, " << result.svg_rectangles << " parsed SVG rectangles\n";
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
