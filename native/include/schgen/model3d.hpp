#pragma once

#include <array>
#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace schgen {
using Model3dBox = std::array<double, 4>;
struct Model3dGeometry {
    std::optional<std::pair<double, double>> model_xy, fab_xy;
    std::optional<Model3dBox> model_box, pad_box;
    std::optional<std::string> misfit, misplaced;
};
// Legacy XY point-envelope measurement, NOT a STEP solid/VRML scene evaluator.
// Preserves the gate's 2.54-mm WRL units, quarter-turn bounds and fit thresholds.
Model3dGeometry measure_model3d(const std::string& footprint,
                              const std::string& clause,
                              const std::string& model_text,
                              const std::string& extension);
struct Model3dResult {
    bool ok = true;
    std::size_t total = 0, covered = 0;
    std::map<std::string, std::string> unmatched, broken, misfit, misplaced, invalid;
    std::vector<std::string> missing;
    std::string line() const;
    std::string report() const;
};
std::filesystem::path default_model3d_directory();
std::optional<std::filesystem::path> resolve_model3d_path(
    const std::string& raw, const std::filesystem::path& model_directory,
    const std::filesystem::path& project_root);
// Explicit roots; missing/empty footprint inventories throw, never vacuously pass.
// Invalid/unmeasurable model assets hard-fail in addition to legacy hard failures.
Model3dResult check_model3d(const std::filesystem::path& parts_directory,
                          const std::filesystem::path& project_root,
                          const std::filesystem::path& model_directory = default_model3d_directory());
Model3dResult run_model3d(const std::filesystem::path& parts_directory,
                        const std::filesystem::path& project_root,
                        const std::filesystem::path& report_directory,
                        const std::filesystem::path& model_directory = default_model3d_directory());
// EasyEDA's repository-owned OBJ conversion, retaining Python's existing units,
// origin, decimal rounding, material strings and per-material indexing.
std::optional<std::string> model3d_obj_to_wrl(const std::string& obj);
}
