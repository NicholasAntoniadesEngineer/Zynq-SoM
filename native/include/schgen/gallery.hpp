#pragma once
#include "schgen/project.hpp"
#include <set>

namespace schgen {
struct GallerySheet {
    std::string name, title;
};
// Snapshot of live inputs, not rendered/frozen output. Names in the two file
// collections are basenames relative to renders/ and renders/ratsnest/.
struct GalleryInput {
    std::filesystem::path repository_root, project_root;
    bool is_default_project = false;
    std::vector<GallerySheet> sheets;
    std::set<std::string> render_files;
    std::vector<std::string> ratsnest_files;
    std::set<std::string> wired_sheets;
};
GalleryInput load_gallery_input(const ProjectPaths &, const std::vector<ProjectCircuit> &);
GalleryInput load_gallery_input(const ProjectPaths &); // canonical JSON loader only
std::string render_gallery_full(const GalleryInput &, const std::filesystem::path &readme_dir);
std::string render_gallery_compact(const GalleryInput &, const std::filesystem::path &readme_dir);
std::string gallery_readme_targets(const GalleryInput &);
struct GallerySplice {
    std::string bytes;
    bool changed = false;
};
// Accept raw UTF-8 file bytes. Match read_text universal-newline comparison,
// preserving original bytes when the normalized text is already unchanged.
GallerySplice splice_gallery(const std::string &original, const std::string &section);
std::vector<std::filesystem::path> write_gallery(const GalleryInput &);
std::vector<std::filesystem::path> generate_gallery(const ProjectPaths &);
std::string gallery_summary(const GalleryInput &,
                            const std::vector<std::filesystem::path> &changed);
} // namespace schgen
