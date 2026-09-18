#include "schgen/bom.hpp"
#include "schgen/project.hpp"

#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>

namespace {
void require(bool test, const char* message) {
    if (!test) throw std::runtime_error(message);
}
schgen::CircuitPartIr part(std::string ref, std::string value, std::string footprint,
                           std::vector<schgen::CircuitFieldIr> fields = {}) {
    schgen::CircuitPartIr result;
    result.ref = std::move(ref); result.value = std::move(value);
    result.footprint = std::move(footprint); result.fields = std::move(fields);
    return result;
}
}
int main(int argc, char** argv) {
    try {
        schgen::CircuitSheetIr a, b;
        a.name = "a"; b.name = "b";
        a.parts = {part("R2", "10k", "R_0603", {{"LCSC", "C1"}}),
                   part("R10", "10k", "R_0603", {{"LCSC", "C1"}}),
                   part("H1", "mount", "", {{"BOM", "exclude"}}),
                   part("U1", "chip,\"quoted\"", "pkg"),
                   part("J1", "connector", "")};
        b.parts = {part("R1", "10k", "R_0603", {{"LCSC", "C1"}})};
        const auto result = schgen::generate_bom({a, b});
        require(result.rows.size() == 3, "BOM exclusion/grouping");
        require(result.csv == "Comment,Designator,Footprint,LCSC\r\n"
            "10k,\"a:R10,a:R2,b:R1\",R_0603,C1\r\n"
            "\"chip,\"\"quoted\"\"\",a:U1,pkg,\r\n"
            "connector,a:J1,,\r\n", "CSV quoting/order/newlines differ");
        require(result.missing_lcsc == std::vector<std::string>{
                    "a:J1 (connector)", "a:U1 (chip,\"quoted\")"}, "missing LCSC evidence");
        require(result.missing_footprints == std::vector<std::string>{"connector: a:J1"},
                "unplaceable part evidence");
        require(schgen::generate_bom({a, b}, false).rows[0].refs ==
                    std::vector<std::string>{"R10", "R2", "R1"}, "standalone ref policy");
        require(schgen::generate_bom({}).csv == "Comment,Designator,Footprint,LCSC\r\n",
                "empty BOM header");
        a.parts = {part("R1", "line\nbreak", "tab\t", {{"BOM", "EXCLUDE"}})};
        require(schgen::generate_bom({a}).csv.find("\"line\nbreak\",a:R1,tab\t,\r\n") !=
                    std::string::npos, "newline CSV cell or exact BOM exclude policy");
        if (argc == 2) {
            const auto paths = schgen::resolve_project_paths(argv[1], "carrier");
            std::vector<schgen::CircuitSheetIr> sheets;
            for (const auto& circuit : schgen::load_project_circuits(paths)) sheets.push_back(circuit.circuit);
            std::ifstream file(paths.project_root / "manufacturing/bom_jlc.csv", std::ios::binary);
            require(file.good(), "cannot read real carrier BOM baseline");
            const std::string golden((std::istreambuf_iterator<char>(file)), {});
            const auto real = schgen::generate_bom(sheets);
            require(real.csv == golden, "real carrier BOM differs from baseline");
            require(real.missing_footprints.empty(), "carrier contains unplaceable BOM rows");
            require(sheets.size() == 37, "carrier BOM omitted circuits");
        }
        std::cout << "BOM native contracts passed\n";
        return 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
