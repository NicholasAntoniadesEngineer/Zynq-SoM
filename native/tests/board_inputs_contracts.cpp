#include "schgen/board_inputs.hpp"
#include "schgen/authoring.hpp"
#include <iostream>

namespace {
std::size_t checks = 0;
void require(bool ok, const std::string& message) {
    ++checks;
    if (!ok) throw std::runtime_error(message);
}
const schgen::JsonNode& field(const schgen::JsonNode& n, const std::string& key) {
    const auto* p = schgen::object_field(n, key);
    if (!p) throw std::runtime_error("missing fixture field " + key);
    return *p;
}
}
int main(int argc, char** argv) {
    using namespace schgen;
    try {
        if (argc != 2) throw std::runtime_error("usage: board_inputs_contracts REPOSITORY");
        const auto root = std::filesystem::absolute(argv[1]);
        for (const auto* project : {"carrier", "devkit_mini"}) {
            const auto paths = resolve_project_paths(root, std::filesystem::path(project));
            const auto circuits = load_project_circuits(paths);
            KicadNetlist nets{{"caller-net", {{"R1", "1"}}}};
            LinkResult link;
            const auto input = load_board_inputs(paths, circuits, link, nets);
            require(input.netlist.size() == 1 && input.netlist[0].first == "caller-net",
                    "caller extracted netlist must not be replaced");
            const auto reference = parse_json_file((root / "native/tests/data/floorplan" / (std::string(project) + ".json")).string());
            const auto& expected = field(reference, "input");
            const auto& corridors = field(field(expected, "compose"), "corridors").array_value;
            require(input.floorplan.compose.corridors.size() == corridors.size(), "prior corridor count");
            for (std::size_t i = 0; i < corridors.size(); ++i) {
                const auto& values = corridors[i].array_value;
                const auto& actual = input.floorplan.compose.corridors[i];
                require(actual.first == values[0].string_value &&
                    actual.second.x0 == values[1].number_value && actual.second.y0 == values[2].number_value &&
                    actual.second.x1 == values[3].number_value && actual.second.y1 == values[4].number_value,
                    "sorted live corridor in floorplan coordinates");
            }
            require(object_field(input.prior_escape_sidecar, "escape_meta") != nullptr,
                    "same source snapshot preserves coexistence records");
            require(input.floorplan.sheets.size() == field(expected, "sheets").array_value.size(), "live sheet count");
            for (std::size_t i = 0; i < input.floorplan.sheets.size(); ++i)
                require(authoring_json_equal(authored_circuit_json(input.floorplan.sheets[i]), field(expected, "sheets").array_value[i]), "live circuit IR");
            require(input.floorplan.som.w == field(field(expected,"som"),"w").number_value &&
                    input.floorplan.som.h == field(field(expected,"som"),"h").number_value, "live SoM outline");
            for (const auto& [id, key] : field(expected,"footprint_of").object_value) {
                const auto live = input.floorplan.footprint_of.find(id);
                require(live != input.floorplan.footprint_of.end(), "resolve " + id);
                require(input.footprints.at(live->second)->bytes ==
                    field(field(field(expected,"footprints"),key.string_value),"text").string_value,
                    "independent exact footprint " + id);
            }
            for (const auto& [id, value] : field(expected,"courtyard_dims").object_value) {
                const auto dims = input.floorplan.courtyard_dims.find(id);
                require(dims != input.floorplan.courtyard_dims.end(), "courtyard dossier " + id);
                require(dims->second.first == value.array_value.at(0).number_value &&
                        dims->second.second == value.array_value.at(1).number_value, "courtyard dimensions " + id);
            }
            require(input.return_path_footprints.size() == input.som_interface.connectors.size(), "every real connector has return geometry");
            require(input.floorplan.regulators.size() == field(expected,"regulators").array_value.size(), "live power analysis");
            BoardInputOptions changed;
            changed.two_side = false; changed.place_clear = 0.75; changed.module_offset = {{3.0, 4.0}};
            const auto variant = load_board_inputs(paths, circuits, link, nets, changed);
            require(!variant.two_side && variant.floorplan.place_clear == 0.75 &&
                    variant.floorplan.module_offset == changed.module_offset, "explicit caller policy retained");
            require(input.two_side && input.floorplan.place_clear == 0.5, "prior snapshot stays unchanged");
        }
        std::cout << "Board inputs: " << checks << " live-source contracts passed\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
