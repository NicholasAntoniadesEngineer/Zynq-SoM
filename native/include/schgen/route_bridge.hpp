#pragma once

#include "schgen/json.hpp"
#include "schgen/route_run.hpp"
#include "schgen/sexpr.hpp"

#include <optional>
#include <string>
#include <vector>

namespace schgen::route {

struct ReadNotes {
    std::size_t footprints = 0, pads = 0, tracks = 0, vias = 0, planes = 0, keepouts = 0;
    std::vector<std::string> approximated;
};

Board board_from_pcb(const Sexpr& pcb, const JsonNode& project, ReadNotes* notes = nullptr);
RunSetup read_setup(const JsonNode& root);
std::string with_copper(const std::string& board_text, const Board& board, const std::vector<Item>& copper);
std::optional<int> run_route_command(int argc, char** argv);

}
