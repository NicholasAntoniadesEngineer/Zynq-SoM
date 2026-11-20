#include "schgen/board_definition.hpp"

#include <iostream>
#include <stdexcept>

namespace {

using namespace schgen;

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
    if (at == std::string::npos) throw std::runtime_error("fixture lacks " + before);
    return text.replace(at, before.size(), after);
}

const char* const small = R"json({
  "schema": "schgen.board/1",
  "name": "bench",
  "module": {
    "connector_part": "DF40C-100DP-0.4V_51",
    "draw": {"connector": "J1", "rail": "+5V_SOM", "amps": 2.15, "note": "module supply"},
    "sdio_level_v": 1.8,
    "sd_bus": ["SDIO_CLK", "SDIO_CMD"],
    "pairs": [{"positive": "USB_P", "negative": "USB_N", "kind": "usb_hs_pair"},
              {"positive": "ETH_P", "negative": "ETH_N", "kind": "diff_pair", "impedance": 100}],
    "loads": [{"connector": "J2", "rail": "+3V3", "amps": 0.02, "note": "bank supply"}]
  },
  "sheets": [
    {"name": "som_j1", "module_connector": "J1", "title": "Module connector one"},
    {"name": "power", "settings": {"bind": {"+VIN": "+VIN_SYS"}}, "additions": {"draws": []}},
    {"name": "mechanical"}
  ]
})json";

BoardDefinition parsed(const std::string& text) { return parse_board(parse_json_text(text), "fixture"); }

void reads_a_board() {
    const BoardDefinition board = parsed(small);
    require(board.name == "bench" && board.sheets.size() == 3, "the sheets are listed in file order");
    require(board.sheet("som_j1").from_module() && board.sheet("som_j1").module_connector == "J1", "a module connector sheet names its connector");
    require(!board.sheet("power").from_module() && board.sheet("power").additions.has_value(), "a library sheet carries its settings and additions");
    require(board.sheet("mechanical").settings.kind == JsonKind::Object && board.sheet("mechanical").settings.object_value.empty(),
            "a sheet with no settings has an empty settings object");
    require(board.module.pairs.size() == 2 && !board.module.pairs.front().impedance && board.module.pairs.back().impedance,
            "pair impedance is optional and kept when given");
    require(board.module.draw.rail == "+5V_SOM" && board.module.loads.front().connector == "J2", "module draw and loads are read");
    rejects([&] { board.sheet("absent"); }, "has no sheet absent");
}

void refuses_bad_boards() {
    rejects([] { parsed(replaced(small, "schgen.board/1", "schgen.board/0")); }, "schema is not");
    rejects([] { parsed(replaced(small, "\"name\": \"mechanical\"", "\"name\": \"power\"")); }, "listed twice");
    rejects([] { parsed(replaced(small, "\"amps\": 2.15", "\"amps\": 0")); }, "not above zero");
    rejects([] { parsed(replaced(small, "{\"name\": \"mechanical\"}", "{\"name\": \"mechanical\", \"title\": \"x\"}")); },
            "not a module connector sheet");
    rejects([] { parsed(replaced(small, "\"sheets\": [", "\"extra\": 1, \"sheets\": [")); }, "extra");
    rejects([] { parsed(replaced(small, "\"impedance\": 100", "\"impedance\": 100.5")); }, "not a whole number");
}

void reads_the_real_boards(const std::filesystem::path& repository) {
    for (const char* name : {"carrier", "devkit_mini"}) {
        const BoardDefinition board = load_board(repository / name);
        require(board.name == name && !board.sheets.empty(), std::string(name) + " loads from its own folder");
        std::size_t connectors = 0;
        for (const BoardSheet& sheet : board.sheets) connectors += sheet.from_module() ? 1 : 0;
        require(connectors > 0, std::string(name) + " has module connector sheets");
    }
    rejects([&] { load_board(repository / "subsystems"); }, "is missing");
}

}

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: board_definition_contracts REPOSITORY");
        reads_a_board();
        refuses_bad_boards();
        reads_the_real_boards(argv[1]);
        std::cout << "board definition contracts: " << checks << " checks passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "board definition contracts FAILED: " << error.what() << "\n";
        return 1;
    }
}
