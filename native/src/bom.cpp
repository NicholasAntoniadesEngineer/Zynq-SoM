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
}
std::string bom_csv_cell(const std::string& value) {
    if (value.find_first_of(",\"\r\n") == std::string::npos) return value;
    std::string out = "\"";
    for (char c : value) {
        if (c == '"') out += '"';
        out += c;
    }
    return out + '"';
}
std::vector<BomRow> group_bom_entries(const std::vector<BomEntry>& entries, bool one_line_per_code) {
    using Key = std::tuple<std::string, std::string, std::string>;
    std::map<Key, std::vector<std::string>> grouped;
    std::map<Key, std::string> comment;
    for (const auto& entry : entries) {
        const bool merged = one_line_per_code && !entry.lcsc.empty();
        const Key key{merged ? std::string() : entry.value, entry.footprint, entry.lcsc};
        grouped[key].push_back(entry.designator);
        const auto seen = comment.find(key);
        if (seen == comment.end() || entry.value < seen->second) comment[key] = entry.value;
    }
    std::vector<BomRow> rows;
    for (const auto& [key, refs] : grouped) rows.push_back({comment.at(key), std::get<1>(key), std::get<2>(key), refs});
    std::stable_sort(rows.begin(), rows.end(), [](const BomRow& a, const BomRow& b) { return std::tie(a.value, a.footprint, a.lcsc) < std::tie(b.value, b.footprint, b.lcsc); });
    return rows;
}
BomOutput generate_bom(const std::vector<CircuitSheetIr>& sheets, bool qualified_refs) {
    BomOutput out;
    std::vector<BomEntry> entries;
    for (const auto& sheet : sheets) {
        std::vector<const CircuitPartIr*> parts;
        for (const auto& part : sheet.parts) parts.push_back(&part);
        std::sort(parts.begin(), parts.end(), [](auto a, auto b) { return a->ref < b->ref; });
        for (auto part : parts) {
            if (field(*part, "BOM") == "exclude") continue;
            const auto lcsc = field(*part, "LCSC");
            if (lcsc.empty()) out.missing_lcsc.push_back(
                sheet.name + ":" + part->ref + " (" + part->value + ")");
            entries.push_back({qualified_refs ? sheet.name + ":" + part->ref : part->ref, part->value, part->footprint, lcsc});
        }
    }
    out.csv = "Comment,Designator,Footprint,LCSC\r\n";
    out.rows = group_bom_entries(entries);
    for (const auto& row : out.rows) {
        const auto designators = join(row.refs);
        if (row.footprint.empty()) out.missing_footprints.push_back(row.value + ": " + designators);
        out.csv += bom_csv_cell(row.value) + ',' + bom_csv_cell(designators) + ','
                 + bom_csv_cell(row.footprint) + ',' + bom_csv_cell(row.lcsc) + "\r\n";
    }
    return out;
}
}
