#pragma once

#include "schgen/named_constant.hpp"
#include "schgen/sexpr.hpp"

#include <array>
#include <cstdint>
#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <string_view>

namespace schgen {

namespace part_fact_constants {
inline constexpr NamedConstant vrml_unit{"vrml_unit", 2.54, "mm", "physical",
    "KiCad reads one VRML model unit as a tenth of an inch, and the part importer writes its models in that unit"};
inline constexpr std::array part_fact_registry{vrml_unit};
}

enum class PartClass : std::uint8_t {
    resistor,
    capacitor,
    inductor,
    ferrite,
    transformer,
    diode,
    led,
    transistor,
    integrated_circuit,
    connector,
    header,
    module_connector,
    control_switch,
    test_point,
    crystal,
    battery_holder,
    mounting_hole,
    fiducial
};

struct PartHeight {
    double mm = 0;
    std::string source;
};

struct PartFact {
    PartClass part_class;
    PartHeight height;
};

struct PartFacts {
    std::filesystem::path file;
    std::map<std::string, PartClass> classes;
    std::map<std::string, PartHeight> stated_heights;
};

struct ModelRoots {
    std::filesystem::path model_directory, project_root, parts_directory;
};

std::string_view part_class_name(PartClass part_class);
PartClass part_class_named(std::string_view name);
bool presents_on_top(PartClass part_class);

PartFacts load_part_facts(const std::filesystem::path& file);
PartClass symbol_class(const PartFacts& facts, const std::string& symbol, const std::string& part);
double model_top(const std::string& text, const std::string& extension, const std::string& model);
PartHeight footprint_height(const PartFacts& facts, const std::string& footprint, const Sexpr& document,
                            const ModelRoots& roots, const std::string& part);
PartHeight model_height(const std::string& raw_path, const ModelRoots& roots, const std::string& part);

}
