#include "schgen/study.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <unistd.h>

namespace {

std::size_t checks = 0;

void require(bool condition, const std::string& detail) {
    ++checks;
    if (!condition) throw std::runtime_error(detail);
}

template <class Call> void rejects(Call call, const std::string& needle) {
    bool thrown = false;
    try {
        call();
    } catch (const std::runtime_error& error) {
        thrown = std::string(error.what()).find(needle) != std::string::npos;
        if (!thrown) throw std::runtime_error("expected '" + needle + "', got: " + error.what());
    }
    require(thrown, "accepted: expected '" + needle + "'");
}

std::string replaced(std::string text, const std::string& before, const std::string& after) {
    const auto at = text.find(before);
    require(at != std::string::npos, "missing mutation " + before);
    return text.replace(at, before.size(), after);
}

const schgen::study::Cell& cell(const std::vector<schgen::study::Cell>& cells, const std::string& key) {
    for (const auto& item : cells)
        if (item.key == key) return item;
    throw std::runtime_error("no cell " + key);
}

void write(const std::filesystem::path& file, const std::string& text) {
    std::filesystem::create_directories(file.parent_path());
    std::ofstream(file, std::ios::binary) << text;
}

const std::string base = "{\"schema\":\"schgen.run/1\",\"boards\":[\"carrier\",\"devkit_mini\"],\"output\":\"out\",\"squeeze\":true,"
                         "\"arrange\":false,\"renders\":false,\"labels\":false,\"timing\":false,\"plane_net\":\"GND\","
                         "\"audit_projections\":2,\"stackup\":{\"carrier\":\"JLC06161H-3313\",\"devkit_mini\":\"JLC06161H-3313\"},"
                         "\"overmold_parts\":{\"carrier\":[],\"devkit_mini\":[]}}";
const std::string studied = "\"overmold_parts\":{\"carrier\":[],\"devkit_mini\":[]},\"study\":{\"stackups\":[\"JLC04161H-3313\",\"JLC08161H-3313\"]}}";
const std::string squeeze = "OWNER HOLDS: 3 small parts held\n"
                            "LAYOUT SQUEEZE: 161 x 150.5 mm to 133.25 x 125 mm, area 24230.5 to 16656.2 mm2 (-31.2%)\n"
                            "  routed airwire 10 to 9 mm\n"
                            "FACES: top 120 to 101, rear 30 to 49\n";
const std::string verdict = "{\"board_ok\":false,\"complete\":true,\"gates\":{"
                            "\"inputs\":{\"status\":\"PASS\",\"mandatory\":true,\"report\":\"\"},"
                            "\"manual\":{\"status\":\"SKIP\",\"mandatory\":true,\"report\":\"\"},"
                            "\"pcb_drc\":{\"status\":\"FAIL\",\"mandatory\":true,\"report\":\"3 errors\"},"
                            "\"render3d\":{\"status\":\"UNAVAILABLE\",\"mandatory\":false,\"report\":\"\"}}}";

void arguments() {
    using namespace schgen;
    const RunArguments plain = parse_run_arguments({}, {});
    require(plain.file == run_config_file && plain.boards.empty() && plain.options.empty(), "bare arguments are not the plain run");
    const RunArguments full = parse_run_arguments({"devkit_mini", "--config", "other.json", "--stackups", "A,B", "carrier"},
                                                  {study::stackups_option});
    require(full.file == "other.json" && full.boards == std::vector<std::string>{"devkit_mini", "carrier"}, "boards or file lost");
    require(full.options.at(study::stackups_option) == "A,B", "stack-up list lost");
    rejects([] { parse_run_arguments({"--config"}, {}); }, "--config needs a file");
    rejects([] { parse_run_arguments({"--stackups", "A"}, {}); }, "unknown option --stackups");
    rejects([] { parse_run_arguments({"--stackups"}, {study::stackups_option}); }, "--stackups needs a value");
    rejects([] { parse_run_arguments({"--stackups", "A", "--stackups", "B"}, {study::stackups_option}); }, "given twice");
    rejects([] { parse_run_arguments({"--layers", "A"}, {study::stackups_option}); }, "unknown option --layers");
}

void configuration() {
    using namespace schgen;
    const RunConfig bare = parse_run_config(parse_json_text(base));
    require(bare.study_stackups.empty(), "a study was invented for a file that names none");
    const RunConfig listed = parse_run_config(parse_json_text(replaced(base, "\"overmold_parts\":{\"carrier\":[],\"devkit_mini\":[]}}", studied)));
    require(listed.study_stackups == std::vector<std::string>{"JLC04161H-3313", "JLC08161H-3313"}, "study stack-ups lost");
    rejects([] { parse_run_config(parse_json_text(replaced(base, "\"overmold_parts\":{\"carrier\":[],\"devkit_mini\":[]}}", "\"overmold_parts\":{\"carrier\":[],\"devkit_mini\":[]},\"study\":{}}"))); },
            "'stackups' is missing");
    rejects([] { parse_run_config(parse_json_text(replaced(base, "\"overmold_parts\":{\"carrier\":[],\"devkit_mini\":[]}}", "\"overmold_parts\":{\"carrier\":[],\"devkit_mini\":[]},\"study\":{\"stackups\":[]}}"))); },
            "'study.stackups' names no stack-up");
    rejects([] { parse_run_config(parse_json_text(replaced(base, "\"overmold_parts\":{\"carrier\":[],\"devkit_mini\":[]}}", "\"overmold_parts\":{\"carrier\":[],\"devkit_mini\":[]},\"study\":[]}"))); },
            "'study' must be an object");
    rejects([] {
        parse_run_config(parse_json_text(replaced(base, "\"overmold_parts\":{\"carrier\":[],\"devkit_mini\":[]}}",
                                                  "\"overmold_parts\":{\"carrier\":[],\"devkit_mini\":[]},\"study\":{\"stackups\":[\"A\"],\"layers\":[]}}")));
    }, "layers");
    rejects([] { parse_run_config(parse_json_text(replaced(base, "\"overmold_parts\":{\"carrier\":[],\"devkit_mini\":[]}}", "\"overmold_parts\":{\"carrier\":[],\"devkit_mini\":[]},\"study\":{\"stackups\":[\"\"]}}"))); },
            "not a name");
    rejects([&] { study::stackups_of(bare, parse_run_arguments({}, {study::stackups_option})); }, "no stack-ups to compare");
    require(study::stackups_of(listed, parse_run_arguments({}, {study::stackups_option})) == listed.study_stackups,
            "configured stack-ups not used");
    const auto given = [&](const std::string& list) {
        return study::stackups_of(listed, parse_run_arguments({study::stackups_option, list}, {study::stackups_option}));
    };
    require(given("X,Y,Z") == std::vector<std::string>{"X", "Y", "Z"}, "the command line does not replace the configured list");
    rejects([&] { given(""); }, "no stack-ups to compare");
    rejects([&] { given("X,,Y"); }, "a stack-up name is empty");
    rejects([&] { given("X,"); }, "a stack-up name is empty");
    rejects([&] { given("X,Y,X"); }, "stack-up 'X' is listed twice");
    require(chosen_boards(listed, {}) == listed.boards, "no named board must mean every listed board");
    require(chosen_boards(listed, {"devkit_mini"}) == std::vector<std::string>{"devkit_mini"}, "named board lost");
    rejects([&] { chosen_boards(listed, {"absent"}); }, "board 'absent' is not listed under 'boards'");
    const RunConfig row = study::row_config(listed, "devkit_mini", "JLC08161H-3313");
    require(row.stackup_of("devkit_mini") == "JLC08161H-3313" && row.stackup_of("carrier") == "JLC06161H-3313",
            "a row must change the stack-up of its own board only");
    require(row.output == std::filesystem::path("out") / "study" / "JLC08161H-3313", "row output folder");
    require(row.board_arguments("devkit_mini", run_config_file) != listed.board_arguments("devkit_mini", run_config_file) && row.squeeze == listed.squeeze &&
            row.plane_net == listed.plane_net, "a row must keep every other setting");
    rejects([&] { study::row_config(listed, "absent", "JLC08161H-3313"); }, "names no stack-up for board 'absent'");
    RunConfig partial = listed;
    partial.overmold_parts.erase("devkit_mini");
    rejects([&] { partial.board_arguments("devkit_mini", run_config_file); }, "'overmold_parts' names no entry for board 'devkit_mini'");
    require(study::table_file(listed, "devkit_mini", ".json") == std::filesystem::path("out") / "study" / "layers_devkit_mini.json",
            "comparison file");
}

void catalogue_cells() {
    using namespace schgen;
    const StackupCatalogue catalogue = load_stackups(stackup_catalogue_file());
    const auto six = study::stackup_cells(catalogue.named("JLC06161H-3313"));
    require(cell(six, "copper_layers").text == "6" && cell(six, "signal_layers").text == "3", "six-layer counts");
    require(cell(six, "layer_order").text == "SGSPGS", "six-layer order");
    require(cell(six, "top_reference").text == "ground" && cell(six, "rear_reference").text == "ground", "six-layer references");
    require(cell(six, "pair_90_ohm_mm").text == "0.1455 / 0.2032" && cell(six, "pair_100_ohm_mm").text == "0.1148 / 0.2032",
            "six-layer pair widths");
    require(cell(six, "pair_90_ohm_mm").value.kind == JsonKind::Object, "pair width must be data");
    const auto four = study::stackup_cells(catalogue.named("JLC04161H-3313"));
    require(cell(four, "copper_layers").text == "4" && cell(four, "rear_reference").text == "power", "four-layer rear reference");
    for (const Stackup& entry : catalogue.entries) {
        const auto cells = study::stackup_cells(entry);
        for (const NamedConstant& impedance : study::constants::study_registry) {
            const int ohms = static_cast<int>(impedance.value);
            const auto& pair = cell(cells, "pair_" + std::to_string(ohms) + "_ohm_mm");
            require((pair.text == "not in catalogue") == !entry.pair(ohms), entry.fabricator_name + " pair width invented or lost");
            require((pair.value.kind == JsonKind::Null) == !entry.pair(ohms), entry.fabricator_name + " pair data invented or lost");
        }
    }
}

void reports() {
    using namespace schgen;
    const auto absent = study::layout_cells(std::nullopt);
    for (const auto& item : absent) require(item.text == "not reported" && item.value.kind == JsonKind::Null, "layout invented");
    const auto layout = study::layout_cells(squeeze);
    require(cell(layout, "size_before_mm").text == "161 x 150.5" && cell(layout, "size_mm").text == "133.25 x 125", "board size");
    require(cell(layout, "area_mm2").text == "16656.2", "board area");
    require(cell(layout, "parts_top").text == "101" && cell(layout, "parts_rear").text == "49", "face counts");
    require(absent.size() == layout.size(), "layout columns depend on the report");
    rejects([] { study::layout_cells(replaced(squeeze, "LAYOUT SQUEEZE", "LAYOUT")); }, "holds 0 lines starting 'LAYOUT SQUEEZE: '");
    rejects([] { study::layout_cells(squeeze + "FACES: top 1 to 1, rear 1 to 1\n"); }, "holds 2 lines starting 'FACES: '");
    rejects([] { study::layout_cells(replaced(squeeze, "133.25 x 125", "133.25 by 125")); }, "not in the expected form");
    rejects([] { study::layout_cells(replaced(squeeze, "rear 30", "rear many")); }, "not in the expected form");
    std::vector<std::string> notes;
    const auto failed = study::gate_cells(parse_json_text(verdict), 1, notes);
    require(cell(failed, "gates").text == "1 of 4" && cell(failed, "result").text == "FAIL", "gate counts");
    require(notes == std::vector<std::string>{"pcb_drc FAIL", "render3d UNAVAILABLE (advisory)"}, "gates not passed");
    notes.clear();
    const auto passed = study::gate_cells(parse_json_text(replaced(verdict, "\"board_ok\":false", "\"board_ok\":true")), 0, notes);
    require(cell(passed, "result").text == "PASS", "passing board");
    notes.clear();
    const auto lost = study::gate_cells(std::nullopt, 1, notes);
    require(cell(lost, "result").text == "ERROR" && cell(lost, "gates").text == "not reported", "a build without a verdict");
    require(notes.size() == 1 && notes.front().find("status 1") != std::string::npos, "a build without a verdict keeps its status");
    rejects([&] { study::gate_cells(parse_json_text("{\"board_ok\":true}"), 0, notes); }, "field 'gates' is missing");
}

void comparison() {
    using namespace schgen;
    const StackupCatalogue catalogue = load_stackups(stackup_catalogue_file());
    const std::filesystem::path root = std::filesystem::temp_directory_path() / ("schgen_study_contracts_" + std::to_string(getpid()));
    std::filesystem::remove_all(root);
    write(root / "good" / study::reports_folder / study::squeeze_report, squeeze);
    write(root / "good" / study::reports_folder / study::verdict_report, verdict);
    Stackup unsized = catalogue.named("JLC10161H-2116");
    unsized.pairs.clear();
    std::vector<study::Row> rows{study::measured_row(catalogue.named("JLC06161H-3313"), root / "good", 1),
                                 study::measured_row(unsized, root / "lost", -1)};
    std::filesystem::remove_all(root);
    const std::string table = study::table("devkit_mini", rows);
    for (const char* needle : {"LAYER STUDY: devkit_mini", "JLC06161H-3313", "JLC10161H-2116", "not in catalogue", "not reported",
                               "133.25 x 125", "ERROR", "FAIL", "pcb_drc FAIL", "status -1"})
        require(table.find(needle) != std::string::npos, std::string("table lacks ") + needle);
    const JsonNode document = parse_json_text(study::document("devkit_mini", rows));
    require(require_string(document, "schema", false, "study") == study::table_schema, "comparison schema");
    const JsonNode* listed = object_field(document, "rows");
    require(listed && listed->array_value.size() == rows.size(), "comparison rows");
    const JsonNode& good = listed->array_value.front();
    const JsonNode& lost = listed->array_value.back();
    require(object_field(good, "size_mm")->array_value.front().number_value == 133.25, "size is not data");
    require(object_field(good, "parts_rear")->number_value == 49, "rear count is not data");
    require(object_field(good, "result")->string_value == "FAIL" && object_field(lost, "result")->string_value == "ERROR", "results");
    require(object_field(lost, "size_mm")->kind == JsonKind::Null && object_field(lost, "pair_90_ohm_mm")->kind == JsonKind::Null,
            "a value that is not known must be null");
    require(object_field(good, "not_passed")->array_value.size() == 2, "gates not passed are not data");
    rows.back().cells.pop_back();
    bool uneven = false;
    try {
        study::table("devkit_mini", rows);
    } catch (const std::logic_error&) {
        uneven = true;
    }
    require(uneven, "rows with different columns were tabulated");
    rejects([] { study::table("devkit_mini", {}); }, "no stack-up was studied");
}

}

int main() {
    try {
        arguments();
        configuration();
        catalogue_cells();
        reports();
        comparison();
        std::cout << checks << " study contracts passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "study contracts FAILED: " << error.what() << "\n";
        return 1;
    }
}
