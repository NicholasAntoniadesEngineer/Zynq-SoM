#include "schgen/rated_bom.hpp"

#include "schgen/placement_report.hpp"
#include "schgen/project.hpp"

#include <algorithm>
#include <map>
#include <set>

namespace schgen {
namespace {

const char* const empty_cell = rated_bom_empty_cell;
const char* const ref_joiner = ":";
const char* const verdict_fail = "fail";
const char* const verdict_waived = "waived";
const char* const verdict_advisory = "advisory";
const char* const verdict_pass = "pass";
const char* const verdict_unrated = "unrated";
const char* const verdict_unevaluated = "unevaluated";
const char* const bound_at_least = ">=";
const char* const bound_at_most = "<=";
const char* const blank_characters = " \t\r\n";
const char* const forbidden_cell_characters = "\t\r\n";

[[noreturn]] void refuse(const std::string& why) { throw ProjectError("bom ratings: " + why); }

std::string trimmed(const std::string& text) {
    const std::size_t first = text.find_first_not_of(blank_characters);
    if (first == std::string::npos) return {};
    return text.substr(first, text.find_last_not_of(blank_characters) - first + 1);
}

std::string key_of(const std::string& sheet, const std::string& ref) { return sheet + ref_joiner + ref; }

std::map<std::string, const PartRatings*> rating_index(const PartRatingsTable& table) {
    std::map<std::string, const PartRatings*> out;
    for (const auto& [lcsc, rating] : table) out.emplace(lcsc, &rating);
    return out;
}

const char* bound_text(PartCheckBound bound) {
    if (bound == PartCheckBound::at_least) return bound_at_least;
    if (bound == PartCheckBound::at_most) return bound_at_most;
    refuse("a ratio carries no bound");
}

bool worse(const PartCheckRecord& a, const PartCheckRecord& b) {
    if (a.bound != b.bound) refuse("checks of one quantity on one line disagree on the bound: " + a.rule + " and " + b.rule);
    return a.bound == PartCheckBound::at_least ? *a.ratio < *b.ratio : *a.ratio > *b.ratio;
}

void keep_worst(std::optional<RatedBomWorst>& slot, std::optional<PartCheckRecord>& holder, const PartCheckRecord& record) {
    if (!record.ratio) return;
    if (holder && !worse(record, *holder)) return;
    holder = record;
    slot = RatedBomWorst{key_of(record.sheet, record.ref), *record.stress, *record.ratio, *record.limit, record.bound};
}

std::string verdict_of(const RatedBomLine& line) {
    if (line.fails) return verdict_fail;
    if (!line.rating) return verdict_unrated;
    if (line.waived) return verdict_waived;
    if (line.advisory) return verdict_advisory;
    if (line.checks) return verdict_pass;
    return verdict_unevaluated;
}

std::string optional_number(const std::optional<double>& value) { return value ? placement_report_number(*value) : std::string(empty_cell); }

std::string optional_text(const std::optional<std::string>& value) { return value && !value->empty() ? *value : std::string(empty_cell); }

std::string worst_stress(const std::optional<RatedBomWorst>& worst) { return worst ? placement_report_number(worst->stress) : std::string(empty_cell); }

std::string worst_ratio(const std::optional<RatedBomWorst>& worst) { return worst ? placement_report_number(worst->ratio) : std::string(empty_cell); }

std::string worst_limit(const std::optional<RatedBomWorst>& worst) {
    return worst ? bound_text(worst->bound) + placement_report_number(worst->limit) : std::string(empty_cell);
}

std::string worst_at(const std::optional<RatedBomWorst>& worst) { return worst ? worst->at : std::string(empty_cell); }

std::map<std::string, std::size_t> line_of_ref(const BomOutput& bom) {
    std::map<std::string, std::size_t> out;
    for (std::size_t index = 0; index < bom.rows.size(); ++index)
        for (const std::string& ref : bom.rows[index].refs)
            if (!out.emplace(ref, index).second) refuse("reference " + ref + " is on two bill-of-materials lines");
    return out;
}

}

std::size_t RatedBom::checks() const {
    std::size_t total = 0;
    for (const RatedBomLine& line : lines) total += line.checks;
    return total;
}

std::size_t RatedBom::fails() const {
    std::size_t total = 0;
    for (const RatedBomLine& line : lines) total += line.fails;
    return total;
}

std::size_t RatedBom::waived() const {
    std::size_t total = 0;
    for (const RatedBomLine& line : lines) total += line.waived;
    return total;
}

std::size_t RatedBom::advisory() const {
    std::size_t total = 0;
    for (const RatedBomLine& line : lines) total += line.advisory;
    return total;
}

std::size_t RatedBom::unrated() const {
    return static_cast<std::size_t>(std::count_if(lines.begin(), lines.end(), [](const RatedBomLine& line) { return !line.rating; }));
}

RatedBom build_rated_bom(const BomOutput& bom, const PartRatingsTable& ratings, const PartCheckResult& parts) {
    const auto table = rating_index(ratings);
    const auto owner = line_of_ref(bom);
    RatedBom report;
    for (std::size_t index = 0; index < bom.rows.size(); ++index) {
        RatedBomLine line;
        line.number = index + 1;
        line.bom = bom.rows[index];
        const auto found = table.find(trimmed(line.bom.lcsc));
        if (found != table.end()) line.rating = *found->second;
        report.lines.push_back(std::move(line));
    }
    std::vector<std::optional<PartCheckRecord>> voltage_holder(report.lines.size()), power_holder(report.lines.size());
    for (const PartCheckRecord& record : parts.evaluated) {
        const std::string key = key_of(record.sheet, record.ref);
        const auto at = owner.find(key);
        if (at == owner.end()) refuse("check " + record.rule + " on " + key + " concerns no line of the bill of materials");
        RatedBomLine& line = report.lines[at->second];
        ++line.checks;
        line.fails += record.verdict == PartCheckVerdict::fail;
        line.waived += record.verdict == PartCheckVerdict::waived;
        line.advisory += record.verdict == PartCheckVerdict::advisory;
        if (record.quantity == part_check_voltage_quantity) keep_worst(line.voltage, voltage_holder[at->second], record);
        else if (record.quantity == part_check_power_quantity) keep_worst(line.power, power_holder[at->second], record);
    }
    for (RatedBomLine& line : report.lines) line.verdict = verdict_of(line);
    return report;
}

std::string RatedBom::text() const {
    std::string out = "bom_ratings\torder=value,footprint,lcsc\n" +
                      placement_report_row({"line", "value", "footprint", "lcsc", "qty", "kind", "v_max_V", "i_max_A", "p_max_W", "t_max_C", "vin_max_V", "tol", "dielectric",
                                            "checks", "v_stress_V", "v_ratio", "v_limit", "v_at", "p_stress_W", "p_ratio", "p_limit", "p_at", "fail", "waived", "advisory",
                                            "verdict", "rating_source"}) + "\n";
    for (const RatedBomLine& line : lines) {
        const std::optional<PartRatings>& r = line.rating;
        out += placement_report_row({std::to_string(line.number), line.bom.value, line.bom.footprint.empty() ? std::string(empty_cell) : line.bom.footprint,
                                     line.bom.lcsc.empty() ? std::string(empty_cell) : line.bom.lcsc, std::to_string(line.bom.refs.size()),
                                     r ? r->kind : std::string(empty_cell), r ? optional_number(r->v_max) : empty_cell, r ? optional_number(r->i_max) : empty_cell,
                                     r ? optional_number(r->p_max) : empty_cell, r ? optional_number(r->temp_max) : empty_cell, r ? optional_number(r->vin_max) : empty_cell,
                                     r ? optional_text(r->tol) : empty_cell, r ? optional_text(r->dielectric) : empty_cell, std::to_string(line.checks),
                                     worst_stress(line.voltage), worst_ratio(line.voltage), worst_limit(line.voltage), worst_at(line.voltage),
                                     worst_stress(line.power), worst_ratio(line.power), worst_limit(line.power), worst_at(line.power),
                                     std::to_string(line.fails), std::to_string(line.waived), std::to_string(line.advisory), line.verdict,
                                     r ? r->source : std::string(empty_cell)}) + "\n";
    }
    out += "totals\torder=none\n" + placement_report_row({"lines", "checks", "fail", "waived", "advisory", "unrated"}) + "\n" +
           placement_report_row({std::to_string(lines.size()), std::to_string(checks()), std::to_string(fails()), std::to_string(waived()), std::to_string(advisory()),
                                 std::to_string(unrated())}) + "\n";
    return out;
}

std::vector<std::string> verify_rated_bom(const RatedBom& report, const BomOutput& bom, const PartRatingsTable& ratings, const PartCheckResult& parts) {
    std::vector<std::string> errors;
    const auto table = rating_index(ratings);
    std::map<std::string, std::size_t> seen;
    for (const RatedBomLine& line : report.lines) ++seen[line.bom.value + "\n" + line.bom.footprint + "\n" + line.bom.lcsc];
    for (const BomRow& row : bom.rows) {
        const std::string key = row.value + "\n" + row.footprint + "\n" + row.lcsc;
        const auto count = seen.find(key);
        const std::string name = row.value + " / " + row.footprint + " / " + row.lcsc;
        if (count == seen.end()) errors.push_back("bill-of-materials line " + name + " is missing from the report");
        else if (count->second != 1) errors.push_back("bill-of-materials line " + name + " appears " + std::to_string(count->second) + " times in the report");
    }
    if (report.lines.size() != bom.rows.size())
        errors.push_back("report has " + std::to_string(report.lines.size()) + " lines but the bill of materials has " + std::to_string(bom.rows.size()));
    if (parts.evaluated.size() != parts.checked)
        errors.push_back("the engine recorded " + std::to_string(parts.evaluated.size()) + " checks but counted " + std::to_string(parts.checked));
    if (report.checks() != parts.checked)
        errors.push_back("report holds " + std::to_string(report.checks()) + " checks but the engine evaluated " + std::to_string(parts.checked));
    if (report.fails() != parts.findings.size())
        errors.push_back("report holds " + std::to_string(report.fails()) + " failures but the engine found " + std::to_string(parts.findings.size()));
    const auto engine_waived = static_cast<std::size_t>(std::count_if(parts.evaluated.begin(), parts.evaluated.end(), [](const PartCheckRecord& r) { return r.verdict == PartCheckVerdict::waived; }));
    if (report.waived() != engine_waived)
        errors.push_back("report holds " + std::to_string(report.waived()) + " waived checks but the engine waived " + std::to_string(engine_waived));
    const auto owner = line_of_ref(bom);
    std::vector<std::size_t> checks(report.lines.size(), 0), fails(report.lines.size(), 0);
    for (const PartCheckRecord& record : parts.evaluated) {
        const auto at = owner.find(key_of(record.sheet, record.ref));
        if (at == owner.end()) {
            errors.push_back("check " + record.rule + " on " + key_of(record.sheet, record.ref) + " concerns no line of the bill of materials");
            continue;
        }
        ++checks[at->second];
        fails[at->second] += record.verdict == PartCheckVerdict::fail;
    }
    for (std::size_t index = 0; index < report.lines.size() && index < bom.rows.size(); ++index) {
        const RatedBomLine& line = report.lines[index];
        const std::string name = "line " + std::to_string(index + 1);
        if (line.bom.value != bom.rows[index].value || line.bom.footprint != bom.rows[index].footprint || line.bom.lcsc != bom.rows[index].lcsc || line.bom.refs != bom.rows[index].refs)
            errors.push_back(name + " is not the bill-of-materials line at that position");
        if (line.number != index + 1) errors.push_back(name + " is numbered " + std::to_string(line.number));
        const auto found = table.find(trimmed(bom.rows[index].lcsc));
        if ((found == table.end()) == line.rating.has_value()) errors.push_back(name + (line.rating ? " carries a rating row the table does not hold" : " lacks the rating row the table holds"));
        if (found != table.end() && line.rating) {
            const PartRatings& want = *found->second;
            const PartRatings& have = *line.rating;
            if (have.kind != want.kind || have.v_max != want.v_max || have.i_max != want.i_max || have.p_max != want.p_max || have.temp_max != want.temp_max ||
                have.vin_max != want.vin_max || have.tol != want.tol || have.dielectric != want.dielectric || have.source != want.source)
                errors.push_back(name + " rating differs from the table row of LCSC " + bom.rows[index].lcsc);
        }
        if (line.checks != checks[index]) errors.push_back(name + " holds " + std::to_string(line.checks) + " checks but the engine evaluated " + std::to_string(checks[index]) + " on it");
        if (line.fails != fails[index]) errors.push_back(name + " holds " + std::to_string(line.fails) + " failures but the engine found " + std::to_string(fails[index]) + " on it");
        if (line.verdict != verdict_of(line)) errors.push_back(name + " verdict " + line.verdict + " does not follow from its counts");
        const auto check_worst = [&](const std::optional<RatedBomWorst>& worst, const std::string& quantity) {
            if (!worst) return;
            const auto match = std::find_if(parts.evaluated.begin(), parts.evaluated.end(), [&](const PartCheckRecord& r) {
                return r.quantity == quantity && key_of(r.sheet, r.ref) == worst->at && r.ratio && *r.ratio == worst->ratio && r.stress && *r.stress == worst->stress &&
                       r.limit && *r.limit == worst->limit && r.bound == worst->bound;
            });
            if (match == parts.evaluated.end()) {
                errors.push_back(name + " " + quantity + " cells are not the engine's check at " + worst->at);
                return;
            }
            if (owner.at(key_of(match->sheet, match->ref)) != index) errors.push_back(name + " " + quantity + " worst check sits on another line");
            const double quotient = match->bound == PartCheckBound::at_least ? *match->rating / *match->stress : *match->stress / *match->rating;
            if (quotient != worst->ratio) errors.push_back(name + " " + quantity + " ratio is not rating against stress at " + worst->at);
        };
        check_worst(line.voltage, part_check_voltage_quantity);
        check_worst(line.power, part_check_power_quantity);
        for (const std::string& cell : {line.bom.value, line.bom.footprint, line.bom.lcsc})
            if (cell.find_first_of(forbidden_cell_characters) != std::string::npos) errors.push_back(name + " carries a cell the tab-separated report cannot hold");
    }
    return errors;
}

}
