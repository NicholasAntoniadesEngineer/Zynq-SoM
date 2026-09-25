#include "schgen/floorplan.hpp"
#include "schgen/atomic_file.hpp"

namespace schgen {
FloorplanDocuments render_floorplan_documents(const FloorplanPlan& plan,
                                               const FloorplanInput& input) {
    FloorplanDocuments out;
    out.notes=build_floorplan_notes(plan,input);
    out.svg=render_floorplan_svg(plan,out.notes);
    out.markdown=render_floorplan_md(plan,out.notes,input);
    return out;
}
FloorplanStage generate_floorplan(const FloorplanInput& input) {
    FloorplanStage stage;
    stage.plan=build_floorplan(input);
    stage.documents=render_floorplan_documents(stage.plan,input);
    return stage;
}
std::vector<std::filesystem::path> write_floorplan_documents(
        const FloorplanDocuments& documents,const std::filesystem::path& directory) {
    const auto svg=directory/"FLOORPLAN.svg",md=directory/"FLOORPLAN.md";
    write_atomic_file(svg.string(),{documents.svg.begin(),documents.svg.end()});
    write_atomic_file(md.string(),{documents.markdown.begin(),documents.markdown.end()});
    return {svg,md};
}
}  // namespace schgen
