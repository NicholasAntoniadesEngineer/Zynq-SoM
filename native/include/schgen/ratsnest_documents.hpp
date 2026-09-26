#pragma once
#include "schgen/pcb_model.hpp"
#include "schgen/ratsnest.hpp"
#include <array>
#include <filesystem>
#include <set>

namespace schgen {
using RatsnestColor = std::array<unsigned char, 3>;
using RatsnestPalette = std::map<std::string, RatsnestColor>;
struct RatsnestAirwire {
    double x0, y0, x1, y1;
    bool cross;
};
struct RatsnestImage {
    // Relative to renders/: top/bottom at its root, sheets under ratsnest/.
    std::string filename, png;
    int width = 0, height = 0;
};
struct RatsnestDocuments {
    std::string svg;
    std::vector<RatsnestImage> images;
    double cross_mm = 0, total_mm = 0, board_w = 0, board_h = 0;
    int n_cross = 0, n_top = 0, n_bottom = 0;
};
RatsnestPalette ratsnest_palette(const std::vector<std::string>& sheets);
std::vector<RatsnestAirwire> ratsnest_airwires(const PcbModel&, const RatsnestNets&,
    const RatsnestEdges&, const std::optional<std::string>& side = std::nullopt);
std::string render_ratsnest_svg(const PcbModel&, const RatsnestPalette&,
    const RatsnestNets&, const RatsnestEdges&);
RatsnestImage render_ratsnest_board_image(const PcbModel&, const RatsnestPalette&,
    const std::string& side, const RatsnestNets&, const RatsnestEdges&);
RatsnestImage render_ratsnest_sheet_image(const PcbModel&, const std::string& sheet,
    const std::set<std::string>& refs, const RatsnestNets&, const RatsnestEdges&,
    const std::set<std::string>& som_refs = {});
std::vector<RatsnestImage> render_ratsnest_subsystem_images(const PcbModel&,
    const RatsnestNets&, const RatsnestEdges&);
std::vector<RatsnestImage> render_ratsnest_images(const PcbModel&, const RatsnestPalette&,
    const RatsnestNets&, const RatsnestEdges&);
// Missing nets/MST are computed from current immutable footprint/pose data.
// Explicitly supplied nets/MST are validated and used, never silently replaced.
RatsnestDocuments render_ratsnest_documents(const PcbModel&,
    const RatsnestNets* = nullptr, const RatsnestEdges* = nullptr);
struct RatsnestPublication {
    std::filesystem::path png_top, png_bottom, svg;
    std::vector<std::filesystem::path> sheets;
    double cross_mm = 0, total_mm = 0, board_w = 0, board_h = 0;
    int n_cross = 0, n_top = 0, n_bottom = 0;
};
// Render before writing; atomic per-file publication; stale *.png cleanup is
// confined to project_root/renders/ratsnest, after successful publication.
RatsnestPublication run_ratsnest_documents(const PcbModel&, const std::filesystem::path& project_root,
    const RatsnestNets* = nullptr, const RatsnestEdges* = nullptr);
std::string ratsnest_document_summary(const RatsnestPublication&, const std::filesystem::path& repository_root);
} // namespace schgen
