#pragma once

#include <string>

namespace schgen {

enum class BoardFileKind { Schematic, Project, Pcb, DesignRules, Placements, PlacementsScratch, PinConstraints };

std::string board_file_name(const std::string& stem, BoardFileKind kind);

}
