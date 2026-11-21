#include "schgen/json.hpp"
#include "schgen/model3d.hpp"
#include "schgen/part_facts.hpp"
#include "schgen/pcb_checks.hpp"

#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

namespace {

using namespace schgen;

namespace fixture {
constexpr double tolerance = 1e-9, mesh_top_units = 0.5, vertex_top = 8.54, apex = 8.647, lift = -3, stated = 0.25;
const char* const mesh =
    "#VRML V2.0 utf8\nShape{geometry IndexedFaceSet{coord Coordinate{point [0 0 0, 1 0 0.5, 0 1 0.25]} "
    "coordIndex [0,1,2,-1]}}";
const char* const solid =
    "DATA;\n#1 = ( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) );\n"
    "#2 = CARTESIAN_POINT('',(0.,0.,-3.));\n#3 = VERTEX_POINT('',#2);\n"
    "#4 = CARTESIAN_POINT('',(1.,0.,8.54));\n#5 = VERTEX_POINT('',#4);\n"
    "#6 = CARTESIAN_POINT('',(1.,0.,8.647));\nENDSEC;\n";
const char* const facts_text =
    "{\"schema\": \"schgen.part_facts/3\", \"classes\": {\"Device:R\": \"resistor\"}, \"connectors\": {}, "
    "\"thermal\": {}, \"thermal_copper\": {}, \"ep_vias\": {}, \"isolation\": {}, \"regulators\": {}, \"zeners\": {}, \"reference_pins\": {}, \"control_grid\": {}, \"model_overrides\": {}, \"footprint_aliases\": {}, \"lands\": {}, \"electrical_spacing\": {\"source\": \"fixture\", \"column\": \"B2\", \"basis\": \"fixture\", \"rows\": [{\"max_volts\": 30, \"spacing_mm\": 0.1}]}, \"stated_heights\": {\"Pad:Bare\": {\"mm\": 0.25, \"basis\": \"fixture\", \"reviewed\": \"2026-11-19\"}}}";
}

void require(bool condition, const std::string& what) {
    if (!condition) throw std::runtime_error("part facts contract failed: " + what);
}

template <typename Action>
void refuses(Action action, const std::string& names, const std::string& what) {
    try {
        action();
    } catch (const std::runtime_error& error) {
        require(std::string(error.what()).find(names) != std::string::npos, what + " names " + names);
        return;
    }
    throw std::runtime_error("part facts contract failed: " + what);
}

bool near(double first, double second) { return std::abs(first - second) < fixture::tolerance; }

void write(const std::filesystem::path& path, const std::string& text) {
    std::ofstream(path, std::ios::binary) << text;
}

void models_are_measured(const std::filesystem::path& scratch) {
    require(near(model_top(fixture::mesh, ".wrl", "mesh"), fixture::mesh_top_units * part_fact_constants::vrml_unit.value),
            "a VRML mesh is measured to its highest point in millimetres");
    require(near(model_top(fixture::solid, ".STEP", "solid"), fixture::vertex_top),
            "a STEP solid is measured to its highest vertex, not to a construction point");
    require(fixture::apex > fixture::vertex_top, "the fixture holds a construction point above the solid");
    refuses([] { model_top(std::string("Transform{}") + fixture::mesh, ".wrl", "moved"); }, "moved",
            "a VRML scene transform is refused");
    refuses([] { model_top(std::string(fixture::solid) + "#9 = MAPPED_ITEM('',#1,#2);", ".step", "assembled"); },
            "assembled", "a STEP assembly transform is refused");
    refuses([] { model_top("DATA;\n#2 = CARTESIAN_POINT('',(0.,0.,1.));\n#3 = VERTEX_POINT('',#2);\n", ".step", "unitless"); },
            "unitless", "a STEP model with no length unit is refused");
    refuses([] { model_top(fixture::mesh, ".obj", "other"); }, "other", "an unknown model format is refused");
    write(scratch / "body.wrl", fixture::mesh);
    write(scratch / "pins.step", fixture::solid);
    write(scratch / "facts.json", fixture::facts_text);
    const PartFacts facts = load_part_facts(scratch / "facts.json");
    std::filesystem::create_directories(scratch / "catalog" / "Part");
    write(scratch / "catalog" / "Part" / "Part.wrl", fixture::mesh);
    const ModelRoots roots{scratch, scratch, scratch / "catalog"};
    const auto footprint = [](const std::string& body) { return sexpr_loads("(footprint \"fixture\" " + body + ")"); };
    const PartHeight plain = footprint_height(
        facts, "Lib:Plain", footprint("(model \"${KIPRJMOD}/body.wrl\" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 90)))"),
        roots, "U1");
    require(near(plain.mm, fixture::mesh_top_units * part_fact_constants::vrml_unit.value) &&
            plain.source.find("body.wrl") != std::string::npos,
            "a footprint takes its height from the model it names and records that model");
    const PartHeight lifted = footprint_height(
        facts, "Lib:Pins", footprint("(model \"${KIPRJMOD}/body.wrl\") (model \"${KICAD10_3DMODEL_DIR}/pins.step\" (offset (xyz 0 0 -3)))"),
        roots, "J1");
    require(near(lifted.mm, fixture::vertex_top + fixture::lift) && lifted.source.find("pins.step") != std::string::npos,
            "the tallest of several models wins and its offset is applied");
    require(near(footprint_height(facts, "Part:Part", footprint("(model \"${KIPRJMOD}/../parts/Part/Part.wrl\")"), roots, "U4").mm,
                 fixture::mesh_top_units * part_fact_constants::vrml_unit.value),
            "a catalogue model is read from the parts folder in use, wherever the project folder is");
    require(near(footprint_height(facts, "Pad:Bare", footprint(""), roots, "TP1").mm, fixture::stated),
            "a footprint with no model takes its stated height");
    refuses([&] { footprint_height(facts, "Lib:None", footprint(""), roots, "TP2"); }, "TP2",
            "a footprint with neither a model nor a stated height is refused");
    refuses([&] { footprint_height(facts, "Pad:Bare", footprint("(model \"${KIPRJMOD}/body.wrl\")"), roots, "TP3"); },
            "TP3", "a height with two sources is refused");
    refuses([&] { footprint_height(facts, "Lib:Gone", footprint("(model \"${KIPRJMOD}/gone.wrl\")"), roots, "U2"); },
            "U2", "a model that does not resolve is refused");
    refuses([&] { footprint_height(facts, "Lib:Tilt", footprint("(model \"${KIPRJMOD}/body.wrl\" (rotate (xyz 90 0 0)))"), roots, "U3"); },
            "U3", "a tilted model is refused");
    require(symbol_class(facts, "Device:R", "R1") == PartClass::resistor, "a symbol takes the class the facts give it");
    refuses([&] { symbol_class(facts, "Device:X", "X1 (sheet)"); }, "X1 (sheet)", "a symbol with no class is refused");
    write(scratch / "bad.json", "{\"schema\": \"schgen.part_facts/3\", \"classes\": {\"Device:R\": \"widget\"}, \"connectors\": {}, \"thermal\": {}, \"thermal_copper\": {}, \"ep_vias\": {}, \"isolation\": {}, \"regulators\": {}, \"zeners\": {}, \"reference_pins\": {}, \"control_grid\": {}, \"model_overrides\": {}, \"footprint_aliases\": {}, \"lands\": {}, \"electrical_spacing\": {\"source\": \"fixture\", \"column\": \"B2\", \"basis\": \"fixture\", \"rows\": [{\"max_volts\": 30, \"spacing_mm\": 0.1}]}, \"stated_heights\": {}}");
    refuses([&] { load_part_facts(scratch / "bad.json"); }, "widget", "an unknown class name is refused");
    refuses([&] { load_part_facts(scratch / "absent.json"); }, "absent.json", "a missing facts file is refused");
    PcbCheckInstance bare;
    bare.ref = "R9";
    refuses([&] { part_class_of(bare); }, "R9", "an instance with no class is refused");
    refuses([&] { part_height_of(bare); }, "R9", "an instance with no height is refused");
}

void repository_facts_cover_the_catalog(const std::filesystem::path& repository) {
    const PartFacts facts = load_part_facts(repository / "parts" / "part_facts.json");
    std::size_t folders = 0;
    for (const auto& entry : std::filesystem::directory_iterator(repository / "parts")) {
        if (!entry.is_directory()) continue;
        ++folders;
        const JsonNode part = parse_json_file((entry.path() / "part.json").string());
        const std::string symbol = require_string(part, "lib_id", false, "part facts contract");
        symbol_class(facts, symbol, entry.path().filename().string());
    }
    require(folders > 0, "the repository holds part folders");
    for (const auto& [symbol, part_class] : facts.classes)
        require(part_class_named(part_class_name(part_class)) == part_class, symbol + " has a class that round trips by name");
    for (const auto& [footprint, height] : facts.stated_heights)
        require(height.source.find("part_facts.json") != std::string::npos, footprint + " records where its height is stated");
}

}

int main(int argc, char** argv) {
    try {
        if (argc != 3) throw std::runtime_error("usage: part_facts_contracts REPOSITORY SCRATCH");
        const std::filesystem::path scratch = argv[2];
        std::filesystem::remove_all(scratch);
        std::filesystem::create_directories(scratch);
        models_are_measured(scratch);
        repository_facts_cover_the_catalog(std::filesystem::absolute(argv[1]));
        std::cout << "part facts contracts ok\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 1;
    }
}
