#include "schgen/board_inputs.hpp"
#include "schgen/authoring.hpp"
#include "historical_input_contracts.hpp"
#include <algorithm>
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
const std::string rtc_id = "RV-3028-C7-32.768kHz-1ppm-TA-QC:RV-3028-C7-32.768kHz-1ppm-TA-QC";
std::string zero_court_line(const std::string& point) {
    return "\t(fp_line\n\t\t(start " + point + ")\n\t\t(end " + point +
        ")\n\t\t(stroke\n\t\t\t(width 0.05)\n\t\t\t(type solid)\n\t\t)\n\t\t(layer \"F.CrtYd\")\n\t)\n";
}
std::string current_footprint_reference(const std::string& id, std::string frozen) {
    if (id != rtc_id) return frozen;
    // 529c196a removed these exact three lines, not arbitrary degenerate
    // geometry. Delete literal bytes from the immutable oracle so pads, models,
    // valid edges, ordering and formatting remain under the exact comparison.
    for (const auto* point : {"1.6 -0.75", "-1.6 -0.75", "-1.6 0.75"}) {
        const auto line = zero_court_line(point);
        const auto pos = frozen.find(line);
        require(pos != std::string::npos && frozen.find(line, pos + line.size()) == std::string::npos,
            "unique reviewed historical RV-3028 zero edge " + std::string(point));
        frozen.erase(pos, line.size());
    }
    return frozen;
}
void footprint_mutations(const std::string& live, const std::string& frozen) {
    const auto expected = current_footprint_reference(rtc_id, frozen);
    require(live == expected && live != frozen, "reviewed RV-3028 correction must be present");
    for (const auto* point : {"1.6 -0.75", "-1.6 -0.75", "-1.6 0.75"}) {
        auto changed = live;
        changed.insert(changed.find("\t(fp_line"), zero_court_line(point));
        require(changed != expected, "restored zero courtyard edge rejected");
    }
    for (const auto& [before, after] : std::vector<std::pair<std::string, std::string>>{
            {"(size 0.504012 0.799998)", "(size 0.604012 0.799998)"},
            {"RV-3028-C7-32.768kHz-1ppm-TA-QC.wrl", "wrong-model.wrl"},
            {"(end 1.6 -0.75)", "(end 1.6001 -0.75)"},
            {"(layer \"F.CrtYd\")", "(layer \"B.CrtYd\")"}}) {
        const auto pos = live.find(before);
        require(pos != std::string::npos, "RV mutation target " + before);
        auto changed = live; changed.replace(pos, before.size(), after);
        require(changed != current_footprint_reference(rtc_id, frozen), "unrelated RV byte mutation rejected");
    }
    require(current_footprint_reference("unlisted:part", frozen) == frozen,
        "unlisted footprint never receives RV correction");
    auto rejects = [&](const std::string& changed) {
        bool rejected = false;
        try { (void)current_footprint_reference(rtc_id, changed); }
        catch (const std::runtime_error&) { rejected = true; }
        require(rejected, "unexpected historical RV edge preimage accepted");
    };
    rejects(live); // already corrected historical input is not a new baseline
    rejects(frozen + zero_court_line("1.6 -0.75"));
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
            for (std::size_t i = 0; i < input.floorplan.sheets.size(); ++i) {
                const auto& live = input.floorplan.sheets[i];
                const auto& frozen = field(expected,"sheets").array_value[i];
                historical_input_contracts::check(live, project, [&](const auto& projected) {
                    return authoring_json_equal(authored_circuit_json(projected), frozen);
                });
            }
            require(input.floorplan.som.w == field(field(expected,"som"),"w").number_value &&
                    input.floorplan.som.h == field(field(expected,"som"),"h").number_value, "live SoM outline");
            std::size_t corrected_footprints = 0;
            for (const auto& [id, key] : field(expected,"footprint_of").object_value) {
                const auto live = input.floorplan.footprint_of.find(id);
                require(live != input.floorplan.footprint_of.end(), "resolve " + id);
                const auto& frozen = field(field(field(expected,"footprints"),key.string_value),"text").string_value;
                const auto& bytes = input.footprints.at(live->second)->bytes;
                require(bytes == current_footprint_reference(id, frozen),
                    "independent exact footprint " + id);
                if (id == rtc_id) { ++corrected_footprints; footprint_mutations(bytes, frozen); }
            }
            require(corrected_footprints == (std::string(project) == "carrier" ? 1u : 0u),
                "exact reviewed footprint correction scope");
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
