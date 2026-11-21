#include "schgen/run_config.hpp"
#include "placement_report_fixture.hpp"
#include "schgen/decoupling_report.hpp"
#include "schgen/stackup.hpp"
#include <iostream>

namespace {
using namespace schgen;
std::size_t checks = 0;
void require(bool test, const std::string &why) {
    ++checks;
    if (!test)
        throw std::runtime_error(why);
}
bool rejected(const DecouplingReport &report, const rules::RuleContext &context, const layout::AuthoredIntent &intent,
              const rules::RuleResult &bypass) {
    return !verify_decoupling_report(report, context, intent, bypass).empty();
}
void board(const std::filesystem::path &root, const std::string &project) {
    const auto scene = placement_report_fixture::scene(root, project);
    const auto &model = scene.model;
    const auto &intent = scene.intent;
    const PcbCheckInput input(model);
    const rules::RuleContext context(input, model, board_stackup(), intent);
    const auto integrity = check_placement_integrity(input, model, intent);
    const auto &bypass = integrity.of(rules::bypass_rule_id);
    const auto report = build_decoupling_report(context);
    const auto errors = verify_decoupling_report(report, context, intent, bypass);
    require(errors.empty(), project + " report is complete: " + (errors.empty() ? std::string() : errors.front()));

    std::size_t purposes = 0, bypasses = 0;
    for (const auto &service : intent.services) {
        const bool decoupling = service.role == "bypass" || service.role == "reservoir";
        purposes += decoupling;
        bypasses += service.role == "bypass";
    }
    require(purposes > 0 && report.rows.size() == purposes, project + " one row per bypass or reservoir purpose row: " + std::to_string(report.rows.size()) + " rows, " + std::to_string(purposes) + " purposes");
    require(bypass.checked == bypasses, project + " bypass rows equal the rule's checked count");
    require(report.failures("bypass") == bypass.findings.size(), project + " fail count equals the rule's");
    std::size_t reservoirs = 0;
    for (const auto &row : report.rows) {
        reservoirs += row.role == "reservoir";
        require(row.role == "bypass" || row.role == "reservoir", project + " role of " + row.cap);
        const rules::Service *served = nullptr;
        for (const auto *service : context.serving({"bypass", "reservoir"}))
            if (context.parts()[service->part].ref == row.cap && service->role == row.role &&
                context.parts()[service->owner].ref == row.owner)
                served = service;
        require(served != nullptr, project + " row has a serving capacitor: " + row.cap);
        require(row.gap == *context.pad_gap(served->owner, served->pads, served->part),
                project + " distance equals the rule's measurement: " + row.cap);
    }
    for (const auto &row : report.rows)
        require(row.judged == (row.role == "bypass"), project + " only rule-judged rows carry a verdict: " + row.cap);
    require(report.failures() == bypass.findings.size(), project + " total fail count equals the rule's findings");
    require(report.text().find("unjudged") != std::string::npos || reservoirs == 0, project + " unjudged rows are labelled");
    require(reservoirs + bypasses == report.rows.size(), project + " roles partition the rows");
    require(report.text() == build_decoupling_report(context).text(), project + " report is reproducible");

    auto dropped = report;
    dropped.rows.erase(dropped.rows.begin());
    require(rejected(dropped, context, intent, bypass), project + " mutation: dropped row");

    auto doubled = report;
    doubled.rows.push_back(doubled.rows.front());
    require(rejected(doubled, context, intent, bypass), project + " mutation: duplicated row");

    const auto bypass_row = std::find_if(report.rows.begin(), report.rows.end(), [](const DecouplingRow &r) { return r.role == "bypass"; });
    require(bypass_row != report.rows.end(), project + " has a bypass row");
    auto farther = report;
    farther.rows[static_cast<std::size_t>(bypass_row - report.rows.begin())].gap += 1;
    require(rejected(farther, context, intent, bypass), project + " mutation: changed bypass distance");

    auto flipped = report;
    flipped.rows[static_cast<std::size_t>(bypass_row - report.rows.begin())].pass = !bypass_row->pass;
    require(rejected(flipped, context, intent, bypass), project + " mutation: flipped verdict");

    const auto reservoir_row = std::find_if(report.rows.begin(), report.rows.end(), [](const DecouplingRow &r) { return r.role == "reservoir"; });
    if (reservoir_row != report.rows.end()) {
        auto moved = report;
        moved.rows[static_cast<std::size_t>(reservoir_row - report.rows.begin())].gap += 1;
        require(rejected(moved, context, intent, bypass), project + " mutation: changed reservoir distance");
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
        std::cout << "decoupling report: " << checks << " assertions passed\n";
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
