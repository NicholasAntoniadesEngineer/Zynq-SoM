#include "schgen/board_power.hpp"
#include "schgen/rated_bom.hpp"
#include "schgen/sheet_roles.hpp"

#include <algorithm>
#include <filesystem>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>

namespace {
using namespace schgen;
const int expected_arguments = 2;
const char* const empty_cell = rated_bom_empty_cell;
const char* const unrated_verdict = "unrated";
std::size_t checks = 0;
void require(bool test, const std::string& why) {
    ++checks;
    if (!test) throw std::runtime_error(why);
}

bool rejected(const RatedBom& report, const BomOutput& bom, const PartRatingsTable& ratings, const PartCheckResult& parts) {
    return !verify_rated_bom(report, bom, ratings, parts).empty();
}

RatedBomLine& line_where(RatedBom& report, bool (*wanted)(const RatedBomLine&)) {
    const auto found = std::find_if(report.lines.begin(), report.lines.end(), wanted);
    if (found == report.lines.end()) throw std::runtime_error("the report has no line of the wanted kind");
    return *found;
}

void board(const std::filesystem::path& root, const std::string& project) {
    const auto paths = resolve_project_paths(root, project);
    const auto circuits = load_project_circuits(paths);
    std::vector<CircuitSheetIr> sheets;
    for (const auto& item : circuits) sheets.push_back(item.circuit);
    const PowerPolicy policy = load_board_power_policy(paths, circuits, load_sheet_roles(paths, circuits));
    const PowerCheckResult power = analyze_power(circuits, policy);
    const PartRatingsTable& ratings = default_part_ratings();
    const PartCheckResult parts = analyze_part_rules(circuits, power, policy, ratings);
    const BomOutput bom = generate_bom(sheets, true);
    const RatedBom report = build_rated_bom(bom, ratings, parts);
    const auto errors = verify_rated_bom(report, bom, ratings, parts);
    require(errors.empty(), project + " rated bill of materials is complete: " + (errors.empty() ? std::string() : errors.front()));

    require(!bom.rows.empty() && report.lines.size() == bom.rows.size(), project + " one line per bill-of-materials line");
    std::set<std::string> keys;
    for (const auto& line : report.lines) require(keys.insert(line.bom.value + "|" + line.bom.footprint + "|" + line.bom.lcsc).second, project + " line appears once: " + line.bom.value);
    require(parts.checked > 0 && report.checks() == parts.checked && parts.evaluated.size() == parts.checked, project + " every engine check is on a line");
    require(report.fails() == parts.findings.size(), project + " failure count equals the engine's");
    require(std::any_of(report.lines.begin(), report.lines.end(), [](const RatedBomLine& l) { return l.verdict == unrated_verdict; }), project + " lines without a rating row are listed unrated");
    require(std::any_of(report.lines.begin(), report.lines.end(), [](const RatedBomLine& l) { return l.voltage.has_value(); }), project + " lines carry a worst voltage stress");
    for (const auto& line : report.lines)
        if (line.verdict == unrated_verdict && line.checks == 0) require(!line.rating && !line.voltage && !line.power, project + " an unrated line has no rating cells: " + line.bom.value);
    require(report.text() == build_rated_bom(bom, ratings, parts).text(), project + " report is reproducible");
    const std::string text = report.text();
    require(text.find("\t" + std::string(unrated_verdict) + "\t" + empty_cell) != std::string::npos, project + " unrated lines print the empty cell in the rating columns");

    auto dropped = report;
    dropped.lines.erase(dropped.lines.begin());
    require(rejected(dropped, bom, ratings, parts), project + " mutation: dropped line");

    auto doubled = report;
    doubled.lines.push_back(doubled.lines.front());
    require(rejected(doubled, bom, ratings, parts), project + " mutation: duplicated line");

    auto reratio = report;
    auto& with_ratio = line_where(reratio, [](const RatedBomLine& l) { return l.voltage.has_value(); });
    with_ratio.voltage->ratio *= 2;
    require(rejected(reratio, bom, ratings, parts), project + " mutation: changed ratio");

    auto restressed = report;
    line_where(restressed, [](const RatedBomLine& l) { return l.voltage.has_value(); }).voltage->stress += 1;
    require(rejected(restressed, bom, ratings, parts), project + " mutation: changed stress");

    auto recounted = report;
    line_where(recounted, [](const RatedBomLine& l) { return l.checks > 0; }).checks += 1;
    require(rejected(recounted, bom, ratings, parts), project + " mutation: changed check count");

    auto unfailed = report;
    line_where(unfailed, [](const RatedBomLine& l) { return l.checks > 0; }).fails += 1;
    require(rejected(unfailed, bom, ratings, parts), project + " mutation: changed failure count");

    auto unrated = report;
    line_where(unrated, [](const RatedBomLine& l) { return l.rating.has_value(); }).rating.reset();
    require(rejected(unrated, bom, ratings, parts), project + " mutation: dropped rating row");

    auto revalued = report;
    auto& with_rating = line_where(revalued, [](const RatedBomLine& l) { return l.rating && l.rating->v_max; });
    *with_rating.rating->v_max += 1;
    require(rejected(revalued, bom, ratings, parts), project + " mutation: changed rating");

    auto fewer = parts;
    fewer.evaluated.pop_back();
    require(rejected(report, bom, ratings, fewer), project + " mutation: the engine's check list shorter than its count");

    auto stray = parts;
    stray.evaluated.front().ref += "_X";
    require(rejected(report, bom, ratings, stray), project + " mutation: engine check on a part that is on no line");
}
}

int main(int argc, char** argv) {
    try {
        if (argc != expected_arguments) throw std::runtime_error("usage: rated_bom_contracts REPOSITORY");
        const std::filesystem::path root = std::filesystem::absolute(argv[1]);
        board(root, "carrier");
        board(root, "devkit_mini");
        std::cout << "rated bill of materials: " << checks << " assertions passed\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
