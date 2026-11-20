#include "schgen/testpoint_map.hpp"

#include "schgen/board_schematic.hpp"
#include "schgen/part_facts.hpp"
#include "schgen/placement_report.hpp"

#include <algorithm>
#include <map>
#include <set>

namespace schgen {
namespace {

std::string key_of(const std::string& sheet, const std::string& ref) { return sheet + ":" + ref; }

std::string net_of(const PcbCheckInstance& part) {
    if (part.pad_nets.size() != 1)
        throw ProjectError("test-point map: " + part.ref + " (" + part.sheet + ") has " + std::to_string(part.pad_nets.size()) +
                           " netted pads, a test point needs exactly one");
    const std::string& net = part.pad_nets.begin()->second.second;
    if (net.empty()) throw ProjectError("test-point map: " + part.ref + " (" + part.sheet + ") carries no net");
    return net;
}

std::string face_of(const PcbCheckInstance& part) {
    if (part.side != "top" && part.side != "bottom")
        throw ProjectError("test-point map: " + part.ref + " (" + part.sheet + ") is on face '" + part.side + "', not top or bottom");
    return part.side;
}

}

TestpointMap build_testpoint_map(const PcbModel& model, const TestpointCoverage& coverage) {
    TestpointMap map;
    for (const PcbCheckInstance& part : model.insts) {
        if (part_class_of(part) != PartClass::test_point) continue;
        map.rows.push_back({part.ref, net_of(part), part.sheet, face_of(part), part.x - model.origin_x, part.y - model.origin_y});
    }
    std::sort(map.rows.begin(), map.rows.end(), [](const TestpointRow& a, const TestpointRow& b) {
        return std::tie(a.sheet, a.ref) < std::tie(b.sheet, b.ref);
    });
    for (const auto& [net, waiver] : coverage.waived) map.waivers.push_back({net, waiver.first, waiver.second});
    std::sort(map.waivers.begin(), map.waivers.end(), [](const TestpointWaiverRow& a, const TestpointWaiverRow& b) {
        return std::tie(a.net, a.sheet) < std::tie(b.net, b.sheet);
    });
    return map;
}

std::string TestpointMap::text() const {
    std::string out = "test_points\torder=sheet,ref\n" + placement_report_row({"ref", "net", "sheet", "face", "x", "y"}) + "\n";
    for (const TestpointRow& row : rows)
        out += placement_report_row({row.ref, row.net, row.sheet, row.face, placement_report_number(row.x), placement_report_number(row.y)}) + "\n";
    out += "waived\torder=net,sheet\n" + placement_report_row({"net", "sheet", "reason"}) + "\n";
    for (const TestpointWaiverRow& row : waivers) out += placement_report_row({row.net, row.sheet, row.reason}) + "\n";
    return out;
}

std::vector<std::string> verify_testpoint_map(const TestpointMap& map, const std::vector<CircuitSheetIr>& sheets,
                                              const SheetIndex& index, const PcbModel& model,
                                              const TestpointCoverage& coverage) {
    std::vector<std::string> errors;
    std::map<std::string, std::int64_t> bands;
    for (const auto& [sheet, band] : index) bands.emplace(sheet, band);
    std::map<std::string, std::string> covered_net;
    for (const auto& [net, keys] : coverage.have)
        for (const std::string& key : keys) covered_net[key] = net;
    std::map<std::string, std::size_t> seen;
    for (const TestpointRow& row : map.rows) ++seen[key_of(row.sheet, row.ref)];
    std::set<std::string> expected;
    const PartFacts& facts = default_part_facts();
    for (const CircuitSheetIr& sheet : sheets)
        for (const CircuitPartIr& part : sheet.parts) {
            if (symbol_class(facts, part.lib_id, part.ref + " (" + sheet.name + ")") != PartClass::test_point) continue;
            const auto band = bands.find(sheet.name);
            if (band == bands.end()) {
                errors.push_back("test point " + part.ref + " on sheet " + sheet.name + " has no sheet band");
                continue;
            }
            const std::string board_ref = board_renamed_ref(part.ref, band->second, sheet.name);
            const std::string key = key_of(sheet.name, board_ref);
            expected.insert(key);
            const auto count = seen.find(key);
            if (count == seen.end()) errors.push_back("test point " + key + " is missing from the map");
            else if (count->second != 1) errors.push_back("test point " + key + " appears " + std::to_string(count->second) + " times in the map");
            const auto net = covered_net.find(key_of(sheet.name, part.ref));
            if (net == covered_net.end()) {
                errors.push_back("test point " + key + " is absent from the coverage result");
                continue;
            }
            const auto row = std::find_if(map.rows.begin(), map.rows.end(), [&](const TestpointRow& r) { return key_of(r.sheet, r.ref) == key; });
            if (row != map.rows.end() && row->net != net->second)
                errors.push_back("test point " + key + " is on net " + row->net + " in the map but " + net->second + " in the coverage result");
        }
    for (const auto& [key, count] : seen)
        if (!expected.count(key)) errors.push_back("map row " + key + " is not a test point of the circuits");
    std::size_t probes = 0;
    for (const PcbCheckInstance& part : model.insts) probes += part_class_of(part) == PartClass::test_point;
    if (map.rows.size() != probes)
        errors.push_back("map has " + std::to_string(map.rows.size()) + " rows but the placed board has " + std::to_string(probes) + " test points");
    if (map.waivers.size() != coverage.waived.size())
        errors.push_back("map lists " + std::to_string(map.waivers.size()) + " waivers but the coverage result has " + std::to_string(coverage.waived.size()));
    for (const auto& [net, waiver] : coverage.waived) {
        const auto row = std::find_if(map.waivers.begin(), map.waivers.end(), [&waived_net = net](const TestpointWaiverRow& r) { return r.net == waived_net; });
        if (row == map.waivers.end()) errors.push_back("waived net " + net + " is missing from the map");
        else if (row->sheet != waiver.first || row->reason != waiver.second) errors.push_back("waived net " + net + " differs from the coverage result");
    }
    return errors;
}

}
