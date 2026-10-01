#include "schgen/floorplan.hpp"
#include "schgen/atomic_file.hpp"

namespace schgen {
FloorplanDocuments render_floorplan_documents(const FloorplanPlan& plan,
                                               const FloorplanInput& input, ExecutionFailureReceipt* failure) {
    FloorplanDocuments out;
    try {
    out.notes=build_floorplan_notes(plan,input);
    out.svg=render_floorplan_svg(plan,out.notes,&out.accounting.quantization_engagements);
    out.markdown=render_floorplan_md(plan,out.notes,input);
    return out;
    } catch (...) { capture_execution_failure(failure,out.accounting);throw; }
}
FloorplanStage generate_floorplan(const FloorplanInput& input, ExecutionFailureReceipt* failure) {
    FloorplanStage stage;
    ExecutionFailureReceipt child;
    bool planned=false;
    try {
    stage.plan=build_floorplan(input,&child);
    planned=true;
    stage.documents=render_floorplan_documents(stage.plan,input,&child);
    return stage;
    } catch (...) {
        ExecutionAccounting prefix;
        if(planned)prefix={stage.plan.accounting.quantization_engagements,stage.plan.accounting.fallback_events};
        else if(!child.captured)prefix={input.accounting.quantization_engagements,input.accounting.fallback_events};
        capture_execution_failure(failure,std::move(prefix),&child);
        throw;
    }
}
std::vector<std::filesystem::path> write_floorplan_documents(
        const FloorplanDocuments& documents,const std::filesystem::path& directory) {
    const auto svg=directory/"FLOORPLAN.svg",md=directory/"FLOORPLAN.md";
    write_atomic_file(svg.string(),{documents.svg.begin(),documents.svg.end()});
    write_atomic_file(md.string(),{documents.markdown.begin(),documents.markdown.end()});
    return {svg,md};
}
}  // namespace schgen
