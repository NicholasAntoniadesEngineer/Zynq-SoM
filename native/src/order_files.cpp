#include "schgen/order_files.hpp"

#include "schgen/board_schematic.hpp"
#include "schgen/bom.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <iomanip>
#include <map>
#include <sstream>

namespace schgen {
namespace {

const char* const line_end = "\r\n";
const char cell_separator = ',';
const char* const rotation_advisory = "ADVISORY: rotation offsets: not verified; the CPL rotation is KiCad's footprint rotation, and the per-footprint offset table that JLCPCB's placement preview must confirm does not exist yet";
const int coordinate_decimals = 4;
const double full_turn_degrees = 360.0;
const double rotation_tolerance = 1e-9;
const std::size_t layer_top = 0;
const std::size_t layer_bottom = 1;

std::string number_text(double value, int decimals) {
    std::ostringstream text;
    text.imbue(std::locale::classic());
    text << std::fixed << std::setprecision(decimals) << value;
    std::string out = text.str();
    if (out.find('.') != std::string::npos) {
        out.erase(out.find_last_not_of('0') + 1);
        if (out.back() == '.') out.pop_back();
    }
    return out;
}

std::string row_text(const std::vector<std::string>& cells) {
    std::string out;
    for (std::size_t index = 0; index < cells.size(); ++index) out += (index ? std::string(1, cell_separator) : std::string()) + bom_csv_cell(cells[index]);
    return out + line_end;
}

std::pair<std::string, std::size_t> reference_key(const std::string& ref) {
    const std::size_t digits = ref.find_first_of("0123456789");
    if (digits == std::string::npos) return {ref, 0};
    return {ref.substr(0, digits), static_cast<std::size_t>(std::stoull(ref.substr(digits)))};
}

bool natural_less(const std::string& a, const std::string& b) {
    const auto left = reference_key(a), right = reference_key(b);
    if (left != right) return left < right;
    return a < b;
}

std::string field_of(const CircuitPartIr& part, const std::string& name) {
    for (const auto& entry : part.fields) if (entry.key == name) return entry.value;
    return {};
}

std::vector<std::vector<std::string>> parse_csv(const std::string& text) {
    std::vector<std::vector<std::string>> rows;
    std::vector<std::string> row;
    std::string cell;
    bool quoted = false, any = false;
    for (std::size_t index = 0; index < text.size(); ++index) {
        const char c = text[index];
        if (quoted) {
            if (c == '"' && index + 1 < text.size() && text[index + 1] == '"') { cell += '"'; ++index; }
            else if (c == '"') quoted = false;
            else cell += c;
        } else if (c == '"') { quoted = true; any = true; }
        else if (c == cell_separator) { row.push_back(cell); cell.clear(); any = true; }
        else if (c == '\r') {}
        else if (c == '\n') {
            if (any || !cell.empty()) { row.push_back(cell); rows.push_back(row); }
            row.clear(); cell.clear(); any = false;
        } else { cell += c; any = true; }
    }
    if (any || !cell.empty()) { row.push_back(cell); rows.push_back(row); }
    return rows;
}

std::vector<std::string> split_designators(const std::string& cell) {
    std::vector<std::string> out;
    std::string current;
    for (char c : cell) {
        if (c == cell_separator) { out.push_back(current); current.clear(); }
        else current += c;
    }
    out.push_back(current);
    return out;
}

bool measure(const std::string& cell, const std::string& suffix, double& value) {
    if (cell.size() <= suffix.size() || cell.compare(cell.size() - suffix.size(), suffix.size(), suffix) != 0) return false;
    const std::string digits = cell.substr(0, cell.size() - suffix.size());
    std::size_t used = 0;
    try { value = std::stod(digits, &used); } catch (const std::exception&) { return false; }
    return used == digits.size();
}

std::string join_list(const std::vector<std::string>& items) {
    std::string out;
    for (const std::string& item : items) out += (out.empty() ? "" : ", ") + item;
    return out;
}

}

OrderFiles build_order_files(const std::vector<CircuitSheetIr>& sheets, const SheetIndex& index, const PcbModel& model,
                             const FabricatorProfile& profile, const AssemblyFacts& facts) {
    const std::vector<std::string> bom_columns = profile.texts(fabricator_key::bom_columns);
    const std::vector<std::string> cpl_columns = profile.texts(fabricator_key::cpl_columns);
    const std::vector<std::string> layers = profile.texts(fabricator_key::layer_tokens);
    const std::string suffix = profile.text(fabricator_key::coordinate_suffix);
    const std::size_t per_line = static_cast<std::size_t>(profile.number(fabricator_key::designators_per_line));
    OrderFiles out;
    std::vector<BomEntry> entries;
    const std::map<std::string, std::int64_t> bands(index.begin(), index.end());
    for (const CircuitSheetIr& sheet : sheets) {
        const auto band = bands.find(sheet.name);
        if (band == bands.end()) throw ProjectError("order files: sheet '" + sheet.name + "' has no sheet band");
        for (const CircuitPartIr& part : sheet.parts) {
            if (field_of(part, "BOM") == "exclude") continue;
            entries.push_back({board_renamed_ref(part.ref, band->second, sheet.name), part.value, part.footprint, field_of(part, "LCSC")});
        }
    }
    std::sort(entries.begin(), entries.end(), [](const BomEntry& a, const BomEntry& b) { return natural_less(a.designator, b.designator); });
    out.bom = row_text(bom_columns);
    out.lines = group_bom_entries(entries, true);
    for (const BomRow& row : out.lines)
        for (std::size_t begin = 0; begin < row.refs.size(); begin += per_line) {
            std::string designators;
            const std::size_t end = std::min(row.refs.size(), begin + per_line);
            for (std::size_t item = begin; item < end; ++item) designators += (designators.empty() ? "" : std::string(1, cell_separator)) + row.refs[item];
            out.bom += row_text({row.value, designators, row.footprint, row.lcsc});
        }
    std::vector<const PcbCheckInstance*> placed;
    for (const PcbCheckInstance& part : model.insts) {
        if (assembly_class_unplaced(facts, part_class_of(part))) out.unplaced.insert(part.ref);
        else { placed.push_back(&part); out.placed.insert(part.ref); }
    }
    std::sort(placed.begin(), placed.end(), [](const PcbCheckInstance* a, const PcbCheckInstance* b) { return natural_less(a->ref, b->ref); });
    out.cpl = row_text(cpl_columns);
    for (const PcbCheckInstance* part : placed) {
        if (part->side != "top" && part->side != "bottom") throw ProjectError("order files: " + part->ref + " is on face '" + part->side + "', not top or bottom");
        const double x = part->x - model.origin_x, y = model.origin_y + model.board_h - part->y;
        double turn = std::fmod(part->rotation, full_turn_degrees);
        if (turn < 0) turn += full_turn_degrees;
        out.cpl += row_text({part->ref, number_text(x, coordinate_decimals) + suffix, number_text(y, coordinate_decimals) + suffix,
                             layers.at(part->side == "top" ? layer_top : layer_bottom), number_text(turn, coordinate_decimals)});
    }
    return out;
}

OrderFilesVerdict check_order_files(const std::string& bom, const std::string& cpl, const std::set<std::string>& unplaced,
                                    const FabricatorProfile& profile) {
    OrderFilesVerdict verdict;
    const auto fail = [&](const std::string& text) { verdict.failures.push_back(text); };
    const std::vector<std::string> bom_columns = profile.texts(fabricator_key::bom_columns);
    const std::vector<std::string> cpl_columns = profile.texts(fabricator_key::cpl_columns);
    const std::vector<std::string> layers = profile.texts(fabricator_key::layer_tokens);
    const std::string suffix = profile.text(fabricator_key::coordinate_suffix);
    const std::size_t per_line = static_cast<std::size_t>(profile.number(fabricator_key::designators_per_line));
    const double spacing = profile.number(fabricator_key::cpl_point_spacing);
    const auto bom_rows = parse_csv(bom), cpl_rows = parse_csv(cpl);
    std::map<std::string, std::size_t> in_bom, in_cpl;
    if (bom_rows.empty() || bom_rows.front() != bom_columns) fail("BOM columns are not exactly: " + join_list(bom_columns));
    if (cpl_rows.empty() || cpl_rows.front() != cpl_columns) fail("CPL columns are not exactly: " + join_list(cpl_columns));
    const auto upper = [](const std::string& name) {
        return std::none_of(name.begin(), name.end(), [](char c) { return std::islower(static_cast<unsigned char>(c)); });
    };
    std::size_t lines = 0;
    for (std::size_t index = bom_rows.empty() ? 0 : 1; index < bom_rows.size(); ++index) {
        const auto& row = bom_rows[index];
        ++lines;
        if (row.size() != bom_columns.size()) { fail("BOM line " + std::to_string(index) + " has " + std::to_string(row.size()) + " cells"); continue; }
        const std::vector<std::string> names = split_designators(row[1]);
        if (names.size() > per_line) fail("BOM line " + std::to_string(index) + " carries " + std::to_string(names.size()) + " designators, at most " + std::to_string(per_line) + " are accepted");
        for (const std::string& name : names) {
            if (name.empty()) fail("BOM line " + std::to_string(index) + " has an empty designator");
            else if (!upper(name)) fail("BOM designator " + name + " is not upper case");
            else if (++in_bom[name] == 2) fail("BOM designator " + name + " appears more than once");
        }
    }
    struct Point { double x, y; std::string ref; };
    std::map<std::string, std::vector<Point>> by_layer;
    std::size_t placements = 0;
    for (std::size_t index = cpl_rows.empty() ? 0 : 1; index < cpl_rows.size(); ++index) {
        const auto& row = cpl_rows[index];
        ++placements;
        if (row.size() != cpl_columns.size()) { fail("CPL row " + std::to_string(index) + " has " + std::to_string(row.size()) + " cells"); continue; }
        const std::string& name = row[0];
        if (name.empty()) fail("CPL row " + std::to_string(index) + " has an empty designator");
        else if (!upper(name)) fail("CPL designator " + name + " is not upper case");
        else if (++in_cpl[name] == 2) fail("CPL designator " + name + " appears more than once");
        double x = 0, y = 0, turn = 0;
        if (!measure(row[1], suffix, x) || !measure(row[2], suffix, y)) { fail("CPL " + name + ": coordinates '" + row[1] + "', '" + row[2] + "' are not numbers in mm"); continue; }
        if (!(x > 0) || !(y > 0)) fail("CPL " + name + ": coordinate " + row[1] + ", " + row[2] + " is not positive");
        if (std::find(layers.begin(), layers.end(), row[3]) == layers.end()) fail("CPL " + name + ": layer '" + row[3] + "' is not one of " + join_list(layers));
        std::size_t used = 0;
        try { turn = std::stod(row[4], &used); } catch (const std::exception&) { used = 0; }
        if (used != row[4].size() || row[4].empty() || turn < 0 || turn >= full_turn_degrees - rotation_tolerance) fail("CPL " + name + ": rotation '" + row[4] + "' is not degrees from 0 up to 360");
        by_layer[row[3]].push_back({x, y, name});
    }
    for (const auto& [name, count] : in_bom) { (void)count; if (!in_cpl.count(name) && !unplaced.count(name)) fail("BOM designator " + name + " is not in the CPL"); }
    for (const auto& [name, count] : in_cpl) { (void)count; if (!in_bom.count(name) && !unplaced.count(name)) fail("CPL designator " + name + " is not in the BOM"); }
    for (auto& [layer, points] : by_layer) {
        std::sort(points.begin(), points.end(), [](const Point& a, const Point& b) { return a.x < b.x; });
        for (std::size_t first = 0; first < points.size(); ++first)
            for (std::size_t second = first + 1; second < points.size() && points[second].x - points[first].x < spacing; ++second)
                if (std::hypot(points[second].x - points[first].x, points[second].y - points[first].y) < spacing)
                    fail("CPL " + points[first].ref + " and " + points[second].ref + " on layer " + layer + " are closer than " + number_text(spacing, coordinate_decimals) + " mm");
    }
    verdict.facts.push_back("BOM " + std::to_string(lines) + " lines, " + std::to_string(in_bom.size()) + " designators; CPL " + std::to_string(placements) + " rows, " + std::to_string(in_cpl.size()) + " designators; " + std::to_string(unplaced.size()) + " declared not placed");
    verdict.advisories.push_back(rotation_advisory);
    return verdict;
}

std::string OrderFilesVerdict::summary() const {
    std::string out = facts.empty() ? std::string() : facts.front();
    out += failures.empty() ? std::string("; no failures") : "; " + std::to_string(failures.size()) + " failing";
    for (const std::string& line : advisories) out += "; " + line;
    return out;
}

std::string OrderFilesVerdict::report() const {
    std::string out = "ORDER FILES\n";
    for (const std::string& line : facts) out += "  " + line + "\n";
    for (const std::string& line : failures) out += "  FAIL: " + line + "\n";
    for (const std::string& line : advisories) out += "  " + line + "\n";
    return out + "ORDER FILES: " + (ok() ? "PASS" : "FAIL") + "\n";
}

}
