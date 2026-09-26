#pragma once

#include "schgen/board_inputs.hpp"
#include "schgen/compose_repair.hpp"
#include "schgen/netlist_gate.hpp"
#include <optional>

namespace schgen {
struct GeometryCommandOptions {
    std::string command, kicad_cli = "kicad-cli";
    std::filesystem::path repository, output;
    std::optional<std::filesystem::path> project;
    bool help = false, export_spec = false, no_render = false;
    ComposeCommandOptions compose;
};
// Unrecognized commands return nullopt; malformed recognized commands throw.
// Only --repo/--project may precede the command, matching the main dispatcher.
std::optional<GeometryCommandOptions> parse_geometry_command(int argc, char** argv);
std::string geometry_command_help(const std::string& command);

// Caller retains an open part catalog. Every invocation authors native IR,
// validates the actual link, emits/checks fresh schematics and independently
// extracts their connectivity in a private, automatically removed directory.
// No canonical circuit JSON, cached schematic/netlist or placed board is read.
// No source snapshots, sheet index, project reports or baselines are written.
PcbPlacementInput load_geometry_board_inputs(const ProjectPaths&,
    const NetlistExtractOptions& = {});

// All output paths are preflighted before authoring/extraction. Empty output
// means the selected project. Floorplan writes docs/FLOORPLAN.{svg,md}, or
// floorplan.json with --export. Compose writes reports/compose_ledger.*;
// APPLY ALSO edits the selected project's floorplan.json and runs the complete
// native-policy board pipeline into output. --output does NOT redirect that
// input spec. Failed repairs restore spec bytes, not emitted board artifacts.
// Symlinks, special files, hard-linked destinations and unrelated source trees
// are refused. Atomic individual publication is not a directory transaction.
int execute_geometry_command(const GeometryCommandOptions&);
std::optional<int> run_geometry_command(int argc, char** argv);
} // namespace schgen
