#include "schgen/board_files.hpp"

#include <stdexcept>

namespace schgen {
namespace {

const char* suffix_of(BoardFileKind kind) {
    switch (kind) {
        case BoardFileKind::Schematic: return ".kicad_sch";
        case BoardFileKind::Project: return ".kicad_pro";
        case BoardFileKind::Pcb: return ".kicad_pcb";
        case BoardFileKind::DesignRules: return "_pcb.kicad_dru";
        case BoardFileKind::Placements: return "_cpl.csv";
        case BoardFileKind::PlacementsScratch: return "_cpl.pipeline.csv";
        case BoardFileKind::PinConstraints: return "_pins.xdc";
    }
    throw std::logic_error("unknown board file kind");
}

}

std::string board_file_name(const std::string& stem, BoardFileKind kind) {
    if (stem.empty()) throw std::runtime_error("a board file name needs the stem from the board's files.stem");
    return stem + suffix_of(kind);
}

}
