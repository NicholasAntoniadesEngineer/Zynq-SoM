#include "manufacturing_assembly_internal.hpp"
#include "schgen/manufacturing_checks.hpp"
#include "schgen/atomic_file.hpp"
#include "schgen/design_rules.hpp"

namespace schgen {
using namespace manufacturing_detail;
namespace {
void publish(const std::filesystem::path& path,const std::string& text) {
    if(path.empty())throw ProjectError("manufacturing output path is empty");
    write_atomic_file(path.string(),{text.begin(),text.end()});
}
void distinct(const std::filesystem::path& a,const std::filesystem::path& b) {
    if(std::filesystem::weakly_canonical(a)==std::filesystem::weakly_canonical(b))throw ProjectError("manufacturing output destinations must be distinct");
}
}
ManufacturingManifestInput prepare_manufacturing_manifest(std::vector<ProjectCircuit> sheets,Stm32PinMap stm32,std::optional<ManufacturingXdc> xdc,std::optional<std::string> device,ManufacturingPreflight preflight,const PowerPolicy& policy) {
    ManufacturingManifestInput in;in.sheets=std::move(sheets);in.stm32=std::move(stm32);in.xdc=std::move(xdc);in.device=std::move(device);in.preflight=preflight;
    std::vector<CircuitSheetIr> circuits;for(const auto& sc:in.sheets)circuits.push_back(sc.circuit);
    const auto c=check_testpoint_coverage(circuits);in.coverage={c.covered(),c.required.size(),c.waived.size()};
    // Explicitly use a supplied power policy for both analysis and rendering.
    in.power=analyze_power(in.sheets,policy);return in;
}
std::filesystem::path run_manufacturing_manifest(ManufacturingManifestInput in,const std::filesystem::path& root,const std::filesystem::path& output,const PowerPolicy& policy) {
    in.artifacts=manufacturing_artifacts(root,output);publish(output,render_manufacturing_manifest(in,policy));return output;
}
ManufacturingSiRun run_si_constraints(const std::vector<ProjectCircuit>& sheets,const std::filesystem::path& spec,const std::filesystem::path& dru,const std::filesystem::path& md) {
    distinct(dru,md);distinct(spec,dru);distinct(spec,md);
    ManufacturingSiRun out;out.dru=dru;out.md=md;out.model=load_si_constraints(sheets,spec);out.verdict=check_si_constraints(out.model);
    const auto rules=render_si_design_rules(out.model,std::filesystem::exists(dru)?read(dru):"(version 1)\n");const auto table=render_si_markdown(out.model);
    publish(dru,rules);publish(md,table);return out;
}
ManufacturingFabResult run_manufacturing_fab(const std::filesystem::path& reports,const std::filesystem::path& pcb,const std::filesystem::path& dru,const std::filesystem::path& project,const ManufacturingFabProfile& profile) {
    if(!std::filesystem::is_regular_file(pcb))throw ProjectError("fabrication gate requires an emitted board: "+pcb.string());
    const auto output=reports/"fab_profile.txt";distinct(output,pcb);distinct(output,dru);distinct(output,project);
    const auto doc=sexpr_loads(read(pcb));const auto node=std::get_if<SexprList>(&doc.v);
    if(!node||node->empty()||!std::holds_alternative<Sexpr::Sym>(node->front().v)||std::get<Sexpr::Sym>(node->front().v).name!="kicad_pcb")throw ProjectError("fabrication gate requires a kicad_pcb document");
    auto result=check_manufacturing_fab(measure_manufacturing_board(doc,std::filesystem::exists(dru)?read(dru):"",std::filesystem::exists(project)?read(project):""),profile);publish(output,result.report()+"\n");return result;
}
JsonNode run_assembly_documents(const PcbModel& model,const PowerCheckResult& power,const std::string& name,const std::filesystem::path& md,const std::filesystem::path& png_dir,const PcbEmitPolicy& policy) {
    if(md.empty()||png_dir.empty())throw ProjectError("assembly output destinations are required");distinct(md,png_dir);
    const auto plan=assembly_plan(model,power,policy);const auto markdown=render_assembly_markdown(model,plan,name);const auto images=render_assembly_images(model,plan);
    std::set<std::string> expected;for(const auto& i:images){const auto p=std::filesystem::path(i.filename);if(p.filename()!=p||p.extension()!=".png"||!expected.insert(i.filename).second)throw ProjectError("invalid assembly image filename: "+i.filename);distinct(md,png_dir/p);}
    std::filesystem::create_directories(png_dir);std::vector<JsonNode> paths;
    for(const auto& i:images){auto path=png_dir/i.filename;publish(path,i.png);paths.push_back(j(path.string()));}
    publish(md,markdown);
    // Only the dedicated caller-selected image directory is pruned; failures
    // propagate before a successful result can reach the board verdict.
    for(const auto& entry:std::filesystem::directory_iterator(png_dir))if(entry.path().extension()==".png"&&!expected.count(entry.path().filename().string())&&!entry.is_directory())std::filesystem::remove(entry.path());
    JsonNode yes;yes.kind=JsonKind::Bool;yes.bool_value=true;
    return obj({{"ok",yes},{"md",j(md.string())},{"png_dir",j(png_dir.string())},{"pngs",arr(std::move(paths))},{"n_steps",j(plan.steps.size())},{"n_phases",j(plan.phases.size())},{"n_parts",j(assembly_detail::parts(model).size())},{"n_pngs",j(images.size())}});
}
std::pair<std::filesystem::path,bool> run_manufacturing_pipeline(const ManufacturingPipelineInput& input,const std::filesystem::path& output) {
    auto text=render_manufacturing_pipeline(input);if(std::filesystem::exists(output)&&read(output)==text)return {output,false};publish(output,text);return {output,true};
}
std::pair<std::filesystem::path,bool> run_manufacturing_pipeline(ManufacturingPipelineInput input,const std::filesystem::path& root,const std::filesystem::path& output) {
    input.baselines=manufacturing_pipeline_baselines(root);return run_manufacturing_pipeline(input,output);
}
} // namespace schgen
