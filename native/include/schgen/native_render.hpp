#pragma once
#include <chrono>
#include <filesystem>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace schgen {
class RenderError : public std::runtime_error { public: using std::runtime_error::runtime_error; };
struct PageRaster {
    std::filesystem::path png_path;
    int width_px=0,height_px=0;
    double page_w_mm=0,page_h_mm=0,dpi=0;
    std::pair<double,double> mm_to_px(double x_mm,double y_mm) const;
};
struct NativeRenderOptions {
    std::string kicad_cli="kicad-cli";
    std::chrono::milliseconds timeout{300000};
};
// First-page Poppler C++ rendering; no Python runtime. Physical geometry is
// preserved; Poppler raster/PNG bytes are NOT claimed identical to MuPDF.
PageRaster render_pdf_to_png(const std::filesystem::path& pdf,
                            const std::filesystem::path& png,int dpi=300);
PageRaster render_sheet_to_png(const std::filesystem::path& schematic,
                              const std::filesystem::path& png,int dpi=300,
                              const NativeRenderOptions& options={});
struct Render3dOptions : NativeRenderOptions {
    std::string quality="high";
    int width=1600,height=1200;
    std::optional<std::filesystem::path> model_directory;
};
struct Render3dFailure { std::string view,diagnostic; };
struct Render3dView { std::string view; std::filesystem::path path; int width=0,height=0; };
struct Render3dResult {
    std::vector<std::filesystem::path> written;
    std::vector<Render3dView> views;
    std::vector<Render3dFailure> failures;
    bool ok() const { return written.size()==8 && failures.empty(); }
    std::string summary() const;
};
std::optional<std::filesystem::path> find_render_model_directory();
// Runs KiCad's actual C++ ray tracer, eight legacy views in legacy order.
// Private input/output staging prevents .kicad_pro mutations and stale success.
// Each published PNG is fully decoded. KiCad may shrink its render canvas;
// observed dimensions are returned in views and bounded by the requested size.
Render3dResult render_board_3d(const std::filesystem::path& pcb,
                             const std::filesystem::path& out_directory,
                             const Render3dOptions& options={});
// Native KiCad/OpenCascade board STEP generation retaining actual components.
// Missing WRL->STEP substitutes or exporter failure are reported, not waived.
void export_board_step(const std::filesystem::path& pcb,
                       const std::filesystem::path& output,
                       const Render3dOptions& options={});
}
