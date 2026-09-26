#pragma once
#include "schgen/board_schematic.hpp"

namespace schgen {
struct SubsystemBuildOptions {
    NetlistExtractOptions extraction;
    bool no_render=false;
};
struct SubsystemBuildResult {
    bool electrical_ok=false,cc_ok=false,netlist_ok=false,erc_ok=false,visual_ok=false;
    bool rendered=false;
    std::filesystem::path schematic;
    std::string report;
    bool ok() const {return electrical_ok&&cc_ok&&netlist_ok&&erc_ok&&visual_ok;}
};
// Value-owned authored IR is the only geometry input. No arbitrary placement
// callback, interpreter, cached schematic or supplied gate verdict is accepted.
// Rendering failure remains advisory, matching the original single-sheet CLI.
SubsystemBuildResult build_subsystem_sheet(const CircuitSheetIr&,SymbolLibrary&,
    const std::filesystem::path& output,const SubsystemBuildOptions& = {});
}
