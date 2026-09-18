#include "schgen/bom.hpp"

#include <algorithm>
#include <map>
#include <sstream>
#include <tuple>

namespace schgen {
namespace {
std::string field(const CircuitPartIr& part, const std::string& name) {
    for (const auto& entry : part.fields) if (entry.key == name) return entry.value;
    return {};
}
std::string join(const std::vector<std::string>& values) {
    std::string out;
    for (const auto& value : values) {
        if (!out.empty()) out += ',';
        out += value;
    }
    return out;
}
std::string csv_cell(const std::string& value) {
    if (value.find_first_of(",\"\r\n") == std::string::npos) return value;
    std::string out = "\"";
    for (char c : value) {
        if (c == '"') out += '"';
        out += c;
    }
    return out + '"';
}
}
BomOutput generate_bom(const std::vector<CircuitSheetIr>& sheets, bool qualified_refs) {
    BomOutput out;
    using Key = std::tuple<std::string, std::string, std::string>;
    std::map<Key, std::vector<std::string>> grouped;
    for (const auto& sheet : sheets) {
        std::vector<const CircuitPartIr*> parts;
        for (const auto& part : sheet.parts) parts.push_back(&part);
        std::sort(parts.begin(), parts.end(), [](auto a, auto b) { return a->ref < b->ref; });
        for (auto part : parts) {
            if (field(*part, "BOM") == "exclude") continue;
            const auto lcsc = field(*part, "LCSC");
            if (lcsc.empty()) out.missing_lcsc.push_back(
                sheet.name + ":" + part->ref + " (" + part->value + ")");
            grouped[{part->value, part->footprint, lcsc}].push_back(
                qualified_refs ? sheet.name + ":" + part->ref : part->ref);
        }
    }
    out.csv = "Comment,Designator,Footprint,LCSC\r\n";
    for (const auto& [key, refs] : grouped) {
        const auto& [value, footprint, lcsc] = key;
        out.rows.push_back({value, footprint, lcsc, refs});
        const auto designators = join(refs);
        if (footprint.empty()) out.missing_footprints.push_back(value + ": " + designators);
        out.csv += csv_cell(value) + ',' + csv_cell(designators) + ','
                 + csv_cell(footprint) + ',' + csv_cell(lcsc) + "\r\n";
    }
    return out;
}
}
