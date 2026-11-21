#include "schgen/assembly_parts.hpp"

#include "schgen/bom_values.hpp"

#include <algorithm>
#include <map>

namespace schgen {
namespace {

const char* const resistor_symbol = "Device:R";
const char* const capacitor_symbol = "Device:C";
const char* const inductor_symbol = "Device:L";

std::string joined(const std::vector<std::string>& items) {
    std::string out;
    for (const std::string& item : items) out += (out.empty() ? "" : ",") + item;
    return out;
}

std::optional<std::string> hint_of(const std::string& symbol) {
    if (symbol == resistor_symbol) return "R";
    if (symbol == capacitor_symbol) return "C";
    if (symbol == inductor_symbol) return "L";
    return std::nullopt;
}

}

AssemblyPartsVerdict check_assembly_parts(const std::vector<CircuitSheetIr>& sheets, const OrderFiles& files,
                                          const AssemblyFacts& facts, const PartFacts& part_facts, int build_count) {
    AssemblyPartsVerdict verdict;
    const auto fail = [&](const std::string& text) { verdict.failures.push_back(text); };
    std::map<std::string, std::vector<std::string>> lines_of_code;
    std::set<std::string> listed;
    std::set<std::string> codes;
    for (const BomRow& line : files.lines) {
        const std::string name = line.value + " (" + joined(line.refs) + ")";
        listed.insert(line.refs.begin(), line.refs.end());
        if (line.lcsc.empty()) { fail("BOM line " + name + " has no JLCPCB part code"); continue; }
        codes.insert(line.lcsc);
        lines_of_code[line.lcsc].push_back(name);
        const auto row = facts.parts.find(line.lcsc);
        if (row == facts.parts.end()) { fail(line.lcsc + " " + name + " has no row in " + facts.file + "; run schgen assembly-refresh"); continue; }
        if (!row->second.in_library) fail(line.lcsc + " " + name + " is not in the JLCPCB assembly library");
        else if (!row->second.buyable) fail(line.lcsc + " " + name + " is in the library but not buyable (" + row->second.read_utc + ")");
    }
    for (const auto& [code, names] : lines_of_code)
        if (names.size() > 1) fail(code + " is on " + std::to_string(names.size()) + " BOM lines: " + joined(names));
    std::map<std::pair<std::string, double>, std::set<std::string>> spellings;
    for (const CircuitSheetIr& sheet : sheets)
        for (const CircuitPartIr& part : sheet.parts) {
            const auto hint = hint_of(part.lib_id);
            if (!hint) continue;
            if (const auto value = normalize_bom_value(part.value, hint)) spellings[{value->component_class, value->magnitude}].insert(part.value);
        }
    for (const auto& [key, names] : spellings)
        if (names.size() > 1) fail("one value spelled " + std::to_string(names.size()) + " ways: " + joined(std::vector<std::string>(names.begin(), names.end())));
    std::vector<std::string> unlisted;
    for (const std::string& ref : files.placed) if (!listed.count(ref)) unlisted.push_back(ref);
    if (!unlisted.empty()) fail("the board needs " + std::to_string(unlisted.size()) + " placed parts the BOM lacks: " + joined(unlisted));
    for (const CircuitSheetIr& sheet : sheets) {
        std::map<PartClass, std::vector<std::string>> wanting;
        for (const CircuitPartIr& part : sheet.parts) {
            const PartClass part_class = symbol_class(part_facts, part.lib_id, part.ref + " (" + sheet.name + ")");
            if (facts.needs.count(part_class)) wanting[part_class].push_back(sheet.name + ":" + part.ref);
        }
        for (const auto& [part_class, refs] : wanting) {
            const AssemblyNeed& need = facts.needs.at(part_class);
            const bool met = std::any_of(need.satisfied_by.begin(), need.satisfied_by.end(), [&](const std::string& code) { return codes.count(code) > 0; });
            if (!met) fail("the finished board needs a " + need.item + ", which is not a placed BOM part (needed by " + joined(refs) + ")");
        }
    }
    std::string oldest;
    std::vector<std::string> short_stock;
    for (const BomRow& line : files.lines) {
        const auto row = facts.parts.find(line.lcsc);
        if (row == facts.parts.end()) continue;
        if (oldest.empty() || row->second.read_utc < oldest) oldest = row->second.read_utc;
        const std::int64_t wanted = static_cast<std::int64_t>(line.refs.size()) * build_count;
        if (row->second.in_library && row->second.jlc_stock < wanted)
            short_stock.push_back(line.lcsc + " " + line.value + ": need " + std::to_string(wanted) + " (" + std::to_string(line.refs.size()) + " per board x " + std::to_string(build_count) +
                                  " boards), JLCPCB stock " + std::to_string(row->second.jlc_stock) + (row->second.route.empty() ? "" : ", route " + row->second.route));
    }
    verdict.facts.push_back(std::to_string(files.lines.size()) + " BOM lines, " + std::to_string(codes.size()) + " codes, facts rows read " + (oldest.empty() ? std::string("never") : "from " + oldest));
    if (!short_stock.empty()) {
        verdict.advisories.push_back("ADVISORY: out of stock today: " + std::to_string(short_stock.size()) + " lines");
        for (const std::string& line : short_stock) verdict.advisories.push_back("ADVISORY:   " + line);
    }
    return verdict;
}

std::string AssemblyPartsVerdict::summary() const {
    std::string out = facts.empty() ? std::string() : facts.front();
    out += failures.empty() ? std::string("; no failures") : "; " + std::to_string(failures.size()) + " failing";
    if (!advisories.empty()) out += "; " + advisories.front();
    return out;
}

std::string AssemblyPartsVerdict::report() const {
    std::string out = "ASSEMBLY PARTS\n";
    for (const std::string& line : facts) out += "  " + line + "\n";
    for (const std::string& line : failures) out += "  FAIL: " + line + "\n";
    for (const std::string& line : advisories) out += "  " + line + "\n";
    return out + "ASSEMBLY PARTS: " + (ok() ? "PASS" : "FAIL") + "\n";
}

}
