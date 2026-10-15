#include "schgen/board_inputs.hpp"
#include "schgen/authoring.hpp"
#include "historical_input_contracts.hpp"
#include "direct_enable_reference.hpp"
#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <unistd.h> // Darwin declares ::mkdtemp here, as used by other native tests.

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
struct SidecarOverlay {
    std::filesystem::path path;
    SidecarOverlay() {
        auto pattern = (std::filesystem::temp_directory_path() / "board-input-sidecar.XXXXXX").string();
        if (!::mkdtemp(pattern.data())) throw std::runtime_error("cannot create sidecar overlay");
        path = pattern;
    }
    SidecarOverlay(const SidecarOverlay&) = delete;
    SidecarOverlay& operator=(const SidecarOverlay&) = delete;
    ~SidecarOverlay() {
        std::error_code error;
        std::filesystem::remove_all(path, error);
    }
};
void sidecar_independence(const schgen::ProjectPaths& paths,
        const std::vector<schgen::ProjectCircuit>& circuits, const schgen::LinkResult& link,
        const schgen::KicadNetlist& nets) {
    using namespace schgen;
    namespace fs = std::filesystem;
    SidecarOverlay overlay;
    // Keep explicit source paths (including libraries and contracts) unchanged.
    // Only project-root-relative reads need links; never link generated output.
    auto isolated = paths;
    isolated.project_root = overlay.path;
    for (const auto* name : {"floorplan.json", "som_mapping.json", "research/si_spec.json"}) {
        const auto source = paths.project_root / name;
        if (!fs::exists(source)) continue;
        const auto destination = overlay.path / name;
        fs::create_directories(destination.parent_path());
        fs::create_symlink(source, destination);
    }
    const auto sidecar = overlay.path / "escape_block.json";
    require(!fs::exists(sidecar), "overlay starts without generated sidecar");
    const auto baseline = load_board_inputs(isolated, circuits, link, nets);
    require(baseline.floorplan.compose.corridors.empty(), "missing sidecar leaves raw corridors empty");
    auto check = [&](const std::string& state) {
        const auto actual = load_board_inputs(isolated, circuits, link, nets);
        const auto context = paths.project_root.filename().string() + "/" + state;
        const auto& a = actual.floorplan;
        const auto& b = baseline.floorplan;
        require(a.compose.corridors.empty(), context + ": generated corridors ignored");
        require(authoring_json_equal(a.project.raw, b.project.raw) && a.sheet_index == b.sheet_index,
                context + ": project policy and sheet order unchanged");
        require(a.sheets.size() == b.sheets.size(), context + ": sheet count unchanged");
        for (std::size_t i = 0; i < a.sheets.size(); ++i)
            require(authoring_json_equal(authored_circuit_json(a.sheets[i]), authored_circuit_json(b.sheets[i])),
                    context + ": authored circuit unchanged");
        require(actual.netlist.size() == nets.size(), context + ": caller netlist count unchanged");
        for (std::size_t i = 0; i < nets.size(); ++i) {
            require(actual.netlist[i].first == nets[i].first && actual.netlist[i].second.size() == nets[i].second.size(),
                    context + ": caller net unchanged");
            for (std::size_t j = 0; j < nets[i].second.size(); ++j)
                require(actual.netlist[i].second[j].ref == nets[i].second[j].ref &&
                        actual.netlist[i].second[j].pin == nets[i].second[j].pin,
                        context + ": caller connectivity unchanged");
        }
        require(actual.interface_bytes == baseline.interface_bytes &&
                som_interface_json(actual.som_interface) == som_interface_json(baseline.som_interface) &&
                actual.function_map == baseline.function_map, context + ": interface and mapping unchanged");
        require(a.footprint_of == b.footprint_of && a.courtyard_dims == b.courtyard_dims &&
                actual.footprints.size() == baseline.footprints.size(), context + ": footprint resolution unchanged");
        for (const auto& [key, footprint] : baseline.footprints)
            require(actual.footprints.at(key)->bytes == footprint->bytes, context + ": footprint bytes unchanged");
        require(actual.return_path_footprints.size() == baseline.return_path_footprints.size(),
                context + ": return geometry count unchanged");
        for (const auto& [ref, footprint] : baseline.return_path_footprints)
            require(actual.return_path_footprints.at(ref)->bytes == footprint->bytes,
                    context + ": return geometry unchanged");
        require(actual.two_side == baseline.two_side && a.module_offset == b.module_offset &&
                a.place_clear == b.place_clear && a.compact_search == b.compact_search && a.origin == b.origin,
                context + ": placement options unchanged");
    };
    check("missing");
    for (const auto& [state, contents] : std::vector<std::pair<std::string, std::string>>{
            {"stale", R"({"t1_constraints":{"corridors":{"Z:stale":{"rect":[9000,9001,9999,9998]},"A:stale":{"rect":[-9000,-9001,-8000,-8001]}}},"escape_meta":{"coexistence":[{"ref":"STALE","sheet":"power","verdict":"FAIL"}]}})"},
            {"invalid-json", "{not valid JSON"},
            {"invalid-corridors", R"({"t1_constraints":{"corridors":[]}})"},
            {"invalid-rectangle", R"({"t1_constraints":{"corridors":{"bad":{"rect":[1,"bad",3]}}}})"}}) {
        std::ofstream output(sidecar, std::ios::binary | std::ios::trunc);
        output << contents;
        output.close();
        require(!output.fail(), "write isolated " + state + " sidecar");
        check(state);
    }
    require(fs::remove(sidecar), "remove only isolated generated sidecar");
    check("missing-after-malformed");
    require(baseline.floorplan.compose.corridors.empty(), "earlier input snapshot remains unchanged");
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
            require(input.floorplan.compose.corridors.empty(), "generated prior corridors leaked into board inputs");
            require(input.floorplan.sheets.size() == field(expected, "sheets").array_value.size(), "live sheet count");
            for (std::size_t i = 0; i < input.floorplan.sheets.size(); ++i) {
                const auto& live = input.floorplan.sheets[i];
                auto frozen = field(expected,"sheets").array_value[i];
                if(live.name=="power_som") {
                    // d2a1ec20: explicitly project the immutable historical
                    // enable network to the reviewed direct-VIN topology.
                    frozen=authored_circuit_json(direct_enable_reference::project(parse_circuit_ir(frozen)));
                    for(int mutation=0;mutation<3;++mutation){
                        auto changed=live;
                        if(mutation==0)changed.parts.front().value+="_drift";
                        if(mutation==1)changed.title+="_drift";
                        if(mutation==2)for(auto& n:changed.nets)for(auto& p:n.pins)if(p.ref=="U4"&&p.pin=="7")p.pin="8";
                        require(!authoring_json_equal(authored_circuit_json(changed),frozen),"direct-enable projection hid unrelated/enable mutation");
                    }
                }
                historical_input_contracts::check(live, project, [&](const auto& projected) {
                    return authoring_json_equal(authored_circuit_json(projected), frozen);
                });
            }
            require(input.floorplan.som.w == field(field(expected,"som"),"w").number_value &&
                    input.floorplan.som.h == field(field(expected,"som"),"h").number_value, "live SoM outline");
            std::size_t corrected_footprints = 0;
            std::size_t retired_footprints = 0;
            for (const auto& [id, key] : field(expected,"footprint_of").object_value) {
                const auto live = input.floorplan.footprint_of.find(id);
                // d2a1ec20 removed the sole SOD-123 user, power_som D5.
                // Only this reviewed retirement may be absent from the oracle.
                if (id == "Diode_SMD:D_SOD-123") {
                    for (const auto& sheet : input.floorplan.sheets)
                        for (const auto& part : sheet.parts)
                            require(part.footprint != id, "retired diode footprint still requested");
                    require(live == input.floorplan.footprint_of.end(), "retired diode footprint still loaded");
                    ++retired_footprints;
                    continue;
                }
                require(live != input.floorplan.footprint_of.end(), "resolve " + id);
                const auto& frozen = field(field(field(expected,"footprints"),key.string_value),"text").string_value;
                const auto& bytes = input.footprints.at(live->second)->bytes;
                require(bytes == current_footprint_reference(id, frozen),
                    "independent exact footprint " + id);
                if (id == rtc_id) { ++corrected_footprints; footprint_mutations(bytes, frozen); }
            }
            require(retired_footprints == 1, "exact reviewed footprint retirement scope");
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
            sidecar_independence(paths, circuits, link, nets);
        }
        std::cout << "Board inputs: " << checks << " live-source contracts passed\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
