#include "placement_report_fixture.hpp"
#include "schgen/order_files.hpp"
#include "schgen/run_config.hpp"

#include <iostream>
#include <set>

namespace {
using namespace schgen;
std::size_t checks = 0;
void require(bool test, const std::string& why) {
    ++checks;
    if (!test) throw std::runtime_error(why);
}
bool failing(const OrderFilesVerdict& verdict, const std::string& fragment) {
    for (const std::string& line : verdict.failures) if (line.find(fragment) != std::string::npos) return true;
    return false;
}
std::string replaced(std::string text, const std::string& from, const std::string& to) {
    const std::size_t at = text.find(from);
    if (at == std::string::npos) throw std::runtime_error("mutation target missing: " + from);
    return text.replace(at, from.size(), to);
}
std::string first_row(const std::string& text, std::size_t line) {
    std::size_t begin = 0;
    for (std::size_t index = 0; index < line; ++index) begin = text.find('\n', begin) + 1;
    return text.substr(begin, text.find('\n', begin) - begin);
}

void board(const std::filesystem::path& root, const std::string& project) {
    apply_run_config(root / run_config_file, project);
    const FabricatorProfile& profile = board_fabrication().profile;
    const AssemblyFacts facts = load_assembly_facts_in(root / "parts");
    auto scene = placement_report_fixture::scene(root, project);
    scene.model.origin_x = -1;
    scene.model.origin_y = 0;
    scene.model.board_h = 1e3;
    const OrderFiles files = build_order_files(scene.sheets, scene.index, scene.model, profile, facts);
    const OrderFilesVerdict verdict = check_order_files(files.bom, files.cpl, files.unplaced, profile);
    require(verdict.ok(), project + " order files pass: " + (verdict.failures.empty() ? std::string() : verdict.failures.front()));
    require(!files.unplaced.empty(), project + " test points and mounting holes are declared not placed");
    for (const PcbCheckInstance& part : scene.model.insts)
        require((files.unplaced.count(part.ref) > 0) == assembly_class_unplaced(facts, part_class_of(part)), project + " not-placed items follow the part class: " + part.ref);
    require(first_row(files.bom, 0) == "Comment,Designator,Footprint,JLCPCB Part #\r" && first_row(files.cpl, 0) == "Designator,Mid X,Mid Y,Layer,Rotation\r", project + " column names");
    require(std::any_of(verdict.advisories.begin(), verdict.advisories.end(), [](const std::string& line) { return line.find("rotation offsets: not verified") != std::string::npos; }), project + " rotation offsets are reported as not verified");
    require(files.cpl.find("mm,") != std::string::npos && files.cpl.find(",T,") != std::string::npos && files.cpl.find(",B,") != std::string::npos, project + " units and layer tokens");

    const std::string some = first_row(files.cpl, 1);
    const std::string designator = some.substr(0, some.find(','));
    require(failing(check_order_files(files.bom, replaced(files.cpl, some + "\n", ""), files.unplaced, profile), "BOM designator " + designator + " is not in the CPL"), project + " mutation: BOM designator missing from the CPL");
    require(failing(check_order_files(replaced(files.bom, designator, "ZZ99999"), files.cpl, files.unplaced, profile), "CPL designator " + designator + " is not in the BOM"), project + " mutation: CPL designator missing from the BOM");
    require(failing(check_order_files(files.bom, files.cpl + some + "\n", files.unplaced, profile), "CPL designator " + designator + " appears more than once"), project + " mutation: duplicate CPL designator");
    const std::string line = first_row(files.bom, 1);
    require(failing(check_order_files(files.bom + line + "\n", files.cpl, files.unplaced, profile), "appears more than once"), project + " mutation: duplicate BOM designator");
    require(failing(check_order_files(replaced(files.bom, "Designator", "Designators"), files.cpl, files.unplaced, profile), "BOM columns are not exactly"), project + " mutation: BOM column name");
    require(failing(check_order_files(files.bom, replaced(files.cpl, "Mid X", "PosX"), files.unplaced, profile), "CPL columns are not exactly"), project + " mutation: CPL column name");
    require(failing(check_order_files(files.bom, replaced(files.cpl, "Rotation", "Rot"), files.unplaced, profile), "CPL columns are not exactly"), project + " mutation: CPL rotation column name");
    const std::size_t comma = some.find(',');
    const std::string negative = some.substr(0, comma + 1) + "-" + some.substr(comma + 1);
    require(failing(check_order_files(files.bom, replaced(files.cpl, some, negative), files.unplaced, profile), "is not positive"), project + " mutation: negative coordinate");
    require(failing(check_order_files(files.bom, replaced(files.cpl, ",T,", ",Top,"), files.unplaced, profile), "layer 'Top'"), project + " mutation: layer token");
    require(failing(check_order_files(files.bom, replaced(files.cpl, some, replaced(some, "mm", "")), files.unplaced, profile), "are not numbers in mm"), project + " mutation: unit suffix removed");
    require(failing(check_order_files(replaced(files.bom, designator, "r" + designator.substr(1)), files.cpl, files.unplaced, profile), "is not upper case"), project + " mutation: lower-case designator");
    std::string crowded = files.cpl;
    const std::vector<std::string> cells = [&] {
        std::vector<std::string> out;
        std::string current;
        for (char c : some) { if (c == ',') { out.push_back(current); current.clear(); } else current += c; }
        out.push_back(current);
        return out;
    }();
    crowded += "ZZ1," + cells[1] + "," + cells[2] + "," + cells[3] + ",0\r\n";
    require(failing(check_order_files(files.bom + "x,ZZ1,x,\r\n", crowded, files.unplaced, profile), "closer than"), project + " mutation: two designators on one point");
    std::string many = "Comment,Designator,Footprint,JLCPCB Part #\r\nx,\"";
    const std::size_t limit = static_cast<std::size_t>(profile.number(fabricator_key::designators_per_line));
    for (std::size_t item = 0; item <= limit; ++item) many += (item ? ",N" : "N") + std::to_string(item);
    require(failing(check_order_files(many + "\",x,\r\n", files.cpl, files.unplaced, profile), "carries " + std::to_string(limit + 1) + " designators"), project + " mutation: line over the designator limit");
}
}

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("repo root required");
        board(argv[1], "carrier");
        board(argv[1], "devkit_mini");
        std::cout << "order files: " << checks << " assertions passed\n";
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
