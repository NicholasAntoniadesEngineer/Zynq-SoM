#include "schgen/connector_pinout.hpp"
#include "schgen/part_facts.hpp"
#include "schgen/project.hpp"

#include <algorithm>
#include <filesystem>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>

namespace {
using namespace schgen;
const int expected_arguments = 2;
const char* const empty_cell = connector_pinout_empty_cell;
std::size_t checks = 0;
void require(bool test, const std::string& why) {
    ++checks;
    if (!test) throw std::runtime_error(why);
}

bool rejected(const ConnectorPinout& pinout, const std::vector<CircuitSheetIr>& sheets, const SheetIndex& index, const PartFacts& facts) {
    return !verify_connector_pinout(pinout, sheets, index, facts).empty();
}

ConnectorPinRow& row_where(ConnectorPinout& pinout, bool (*wanted)(const ConnectorPinRow&)) {
    const auto found = std::find_if(pinout.rows.begin(), pinout.rows.end(), wanted);
    if (found == pinout.rows.end()) throw std::runtime_error("the pinout has no row of the wanted kind");
    return *found;
}

void board(const std::filesystem::path& root, const std::string& project, const PartFacts& facts) {
    const auto paths = resolve_project_paths(root, project);
    std::vector<CircuitSheetIr> sheets;
    for (const auto& item : load_project_circuits(paths)) sheets.push_back(item.circuit);
    const SheetIndex index = load_sheet_index(paths);
    const ConnectorPinout pinout = build_connector_pinout(sheets, index, facts);
    const auto errors = verify_connector_pinout(pinout, sheets, index, facts);
    require(errors.empty(), project + " pinout is complete: " + (errors.empty() ? std::string() : errors.front()));

    std::size_t pins = 0;
    for (const auto& sheet : sheets)
        for (const auto& part : sheet.parts) {
            const PartClass kind = symbol_class(facts, part.lib_id, part.ref);
            if (kind == PartClass::connector || kind == PartClass::header) pins += part.pin_numbers.size();
        }
    require(pins > 0 && pinout.rows.size() == pins, project + " one row per pin of every connector and header part");
    std::set<std::string> keys;
    for (const auto& row : pinout.rows) require(keys.insert(row.sheet + ":" + row.ref + "." + row.pin).second, project + " pin appears once: " + row.ref + "." + row.pin);
    require(std::any_of(pinout.rows.begin(), pinout.rows.end(), [](const ConnectorPinRow& r) { return r.net == empty_cell; }), project + " unconnected pins are listed with no net");
    require(std::any_of(pinout.rows.begin(), pinout.rows.end(), [](const ConnectorPinRow& r) { return r.port_kind != empty_cell && r.route_class != empty_cell; }),
            project + " pins reach typed ports with a route class");
    require(std::any_of(pinout.rows.begin(), pinout.rows.end(), [](const ConnectorPinRow& r) { return !r.protectors.empty(); }), project + " pins reach protecting parts");
    for (const auto& row : pinout.rows) {
        require(row.net != empty_cell || (row.port_kind == empty_cell && row.route_class == empty_cell && row.impedance == empty_cell && row.protectors.empty()),
                project + " an unconnected pin carries no port, class or protector: " + row.ref + "." + row.pin);
        require(!row.pin_name.empty() && !row.board_ref.empty(), project + " every row names its pin and board reference: " + row.ref + "." + row.pin);
    }
    require(pinout.text() == build_connector_pinout(sheets, index, facts).text(), project + " report is reproducible");

    auto dropped = pinout;
    dropped.rows.erase(dropped.rows.begin());
    require(rejected(dropped, sheets, index, facts), project + " mutation: dropped row");

    auto doubled = pinout;
    doubled.rows.push_back(doubled.rows.front());
    require(rejected(doubled, sheets, index, facts), project + " mutation: duplicated row");

    auto renamed = pinout;
    row_where(renamed, [](const ConnectorPinRow& r) { return r.net != empty_cell; }).net += "_X";
    require(rejected(renamed, sheets, index, facts), project + " mutation: changed net");

    auto opened = pinout;
    row_where(opened, [](const ConnectorPinRow& r) { return r.net == empty_cell; }).net = "X";
    require(rejected(opened, sheets, index, facts), project + " mutation: net on an unconnected pin");

    auto reclassed = pinout;
    row_where(reclassed, [](const ConnectorPinRow& r) { return r.route_class != empty_cell; }).route_class += "_X";
    require(rejected(reclassed, sheets, index, facts), project + " mutation: changed route class");

    auto unguarded = pinout;
    row_where(unguarded, [](const ConnectorPinRow& r) { return !r.protectors.empty(); }).protectors.clear();
    require(rejected(unguarded, sheets, index, facts), project + " mutation: dropped protecting part");

    auto stranger = pinout;
    row_where(stranger, [](const ConnectorPinRow& r) { return !r.protectors.empty(); }).protectors.front().board_ref += "_X";
    require(rejected(stranger, sheets, index, facts), project + " mutation: protecting part that does not exist");

    auto foreign = pinout;
    foreign.rows.front().pin += "_X";
    require(rejected(foreign, sheets, index, facts), project + " mutation: pin that is not on the connector");

    auto marked = pinout;
    row_where(marked, [](const ConnectorPinRow& r) { return r.declared == empty_cell; }).declared = connector_pinout_declared_open;
    require(rejected(marked, sheets, index, facts), project + " mutation: pin marked unconnected without a declaration");
}
}

int main(int argc, char** argv) {
    try {
        if (argc != expected_arguments) throw std::runtime_error("usage: connector_pinout_contracts REPOSITORY");
        const std::filesystem::path root = std::filesystem::absolute(argv[1]);
        const PartFacts& facts = default_part_facts();
        board(root, "carrier", facts);
        board(root, "devkit_mini", facts);
        std::cout << "connector pinout: " << checks << " assertions passed\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
