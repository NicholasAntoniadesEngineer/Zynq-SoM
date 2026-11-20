#include "schgen/run_config.hpp"
#include "placement_report_fixture.hpp"
#include "schgen/testpoint_map.hpp"
#include <iostream>
#include <set>

namespace {
using namespace schgen;
std::size_t checks = 0;
void require(bool test, const std::string &why) {
    ++checks;
    if (!test)
        throw std::runtime_error(why);
}
bool rejected(const TestpointMap &map, const std::vector<CircuitSheetIr> &sheets, const SheetIndex &index,
              const PcbModel &model, const TestpointCoverage &coverage) {
    return !verify_testpoint_map(map, sheets, index, model, coverage).empty();
}
void board(const std::filesystem::path &root, const std::string &project) {
    const auto scene = placement_report_fixture::scene(root, project);
    const auto &model = scene.model;
    const auto &sheets = scene.sheets;
    const auto &index = scene.index;
    const auto coverage = check_testpoint_coverage(sheets);
    const auto map = build_testpoint_map(model, coverage);
    const auto errors = verify_testpoint_map(map, sheets, index, model, coverage);
    require(errors.empty(), project + " map is complete: " + (errors.empty() ? std::string() : errors.front()));
    std::size_t probes = 0;
    for (const auto &part : model.insts)
        probes += part_class_of(part) == PartClass::test_point;
    require(probes > 0 && map.rows.size() == probes, project + " one row per test-point part");
    std::set<std::string> keys;
    for (const auto &row : map.rows)
        require(keys.insert(row.sheet + ":" + row.ref).second, project + " row appears once: " + row.ref);
    std::size_t held = 0;
    for (const auto &[net, refs] : coverage.have)
        held += refs.size();
    require(held == map.rows.size(), project + " rows equal the coverage result's test points");
    for (const auto &row : map.rows) {
        const auto covered = std::find_if(coverage.have.begin(), coverage.have.end(),
                                          [&](const auto &entry) { return entry.first == row.net; });
        require(covered != coverage.have.end(), project + " net of " + row.ref + " is in the coverage result");
    }
    require(map.waivers.size() == coverage.waived.size(), project + " every waived net is listed");
    for (const auto &waiver : map.waivers)
        require(!waiver.reason.empty() && !waiver.sheet.empty(), project + " waiver carries sheet and reason");
    require(map.text() == build_testpoint_map(model, coverage).text(), project + " report is reproducible");

    auto dropped = map;
    dropped.rows.erase(dropped.rows.begin());
    require(rejected(dropped, sheets, index, model, coverage), project + " mutation: dropped row");

    auto doubled = map;
    doubled.rows.push_back(doubled.rows.front());
    require(rejected(doubled, sheets, index, model, coverage), project + " mutation: duplicated row");

    auto renamed = map;
    renamed.rows.front().net += "_X";
    require(rejected(renamed, sheets, index, model, coverage), project + " mutation: changed net");

    auto moved = map;
    moved.rows.front().x += 1;
    require(rejected(moved, sheets, index, model, coverage), project + " mutation: changed position");

    if (!map.waivers.empty()) {
        auto lost = map;
        lost.waivers.erase(lost.waivers.begin());
        require(rejected(lost, sheets, index, model, coverage), project + " mutation: dropped waiver");
        auto reworded = map;
        reworded.waivers.front().reason += " changed";
        require(rejected(reworded, sheets, index, model, coverage), project + " mutation: changed waiver reason");
    }
}
} // namespace
int main(int argc, char **argv) {
    try {
        if (argc != 2)
            throw std::runtime_error("repo root required");
        schgen::apply_run_config(std::filesystem::path(argv[1]) / schgen::run_config_file, "carrier");
        board(argv[1], "carrier");
        board(argv[1], "devkit_mini");
        std::cout << "test-point map: " << checks << " assertions passed\n";
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
