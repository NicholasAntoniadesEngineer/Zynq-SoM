#pragma once
#include "schgen/assembly_documents.hpp"
#include "schgen/pcb_emit_bindings.hpp"

namespace schgen {
namespace assembly_binding {
namespace nb = nanobind;
inline AssemblyPlan plan(const nb::list& steps, const nb::list& phases) {
    using model_binding::get;
    AssemblyPlan out;
    for (auto raw : steps) {
        const auto d = nb::cast<nb::dict>(raw);
        out.steps.push_back({get<int>(d,"n"),get<std::string>(d,"slug"),get<std::string>(d,"title"),
            get<std::vector<std::size_t>>(d,"insts"),get<std::vector<std::string>>(d,"notes")});
    }
    for (auto raw : phases) {
        const auto d = nb::cast<nb::dict>(raw);
        out.phases.push_back({get<int>(d,"n"),get<std::string>(d,"slug"),get<std::string>(d,"title"),
            get<std::vector<std::string>>(d,"sheets"),get<std::vector<std::size_t>>(d,"insts"),
            get<std::vector<std::string>>(d,"checkpoints"),get<std::string>(d,"lead")});
    }
    return out;
}
inline nb::dict row(const AssemblyStep& step) {
    nb::dict d;d["n"]=step.n;d["slug"]=nb::cast(step.slug);d["title"]=nb::cast(step.title);
    d["insts"]=nb::cast(step.insts);d["notes"]=nb::cast(step.notes);return d;
}
inline nb::dict row(const AssemblyPhase& phase) {
    nb::dict d;d["n"]=phase.n;d["slug"]=nb::cast(phase.slug);d["title"]=nb::cast(phase.title);
    d["sheets"]=nb::cast(phase.sheets);d["insts"]=nb::cast(phase.insts);
    d["checkpoints"]=nb::cast(phase.checkpoints);d["lead"]=nb::cast(phase.lead);return d;
}
}
inline void bind_assembly(nanobind::module_& m) {
    namespace nb = nanobind;
    m.def("assembly_joint", [](const std::string& source,const std::string& bytes) {
        return assembly_joint(*pcb_check_footprint(source,bytes));
    });
    m.def("assembly_steps", [](const PcbModel& model,const nb::dict& policy) {
        nb::list out;for(const auto& v:assembly_process_steps(model,pcb_emission_policy(policy)))out.append(assembly_binding::row(v));return out;
    });
    m.def("assembly_phases", [](const PcbModel& model,const nb::dict& power,const nb::dict& policy) {
        nb::list out;for(const auto& v:assembly_bringup_phases(model,power_result_from_json(json_from_python(power)),pcb_emission_policy(policy)))out.append(assembly_binding::row(v));return out;
    });
    m.def("assembly_markdown", [](const PcbModel& model,const nb::list& steps,const nb::list& phases,const std::string& name) {
        const auto plan=assembly_binding::plan(steps,phases);
        nb::gil_scoped_release release;return render_assembly_markdown(model,plan,name);
    });
    m.def("assembly_images", [](const PcbModel& model,const nb::list& steps,const nb::list& phases) {
        const auto plan=assembly_binding::plan(steps,phases);std::vector<AssemblyImage> images;
        {nb::gil_scoped_release release;images=render_assembly_images(model,plan);}
        nb::list out;for(const auto& v:images)out.append(nb::make_tuple(v.filename,nb::bytes(v.png.data(),v.png.size())));return out;
    });
    m.def("assembly_stage_image", [](const PcbModel& model,const std::vector<std::size_t>& done,
            const std::vector<std::size_t>& current,const std::string& caption,nb::object mate) {
        const auto box=pcb_check_binding::box(mate);std::string bytes;
        {nb::gil_scoped_release release;bytes=render_assembly_stage_image(model,done,current,caption,box);}
        return nb::bytes(bytes.data(),bytes.size());
    },nb::arg("model"),nb::arg("done"),nb::arg("current"),nb::arg("caption"),nb::arg("mate").none());
    m.def("assembly_run", [](const PcbModel& model,const nb::dict& power,const std::string& name,
            const std::string& md,const std::string& png_dir,const nb::dict& policy) {
        const auto p=power_result_from_json(json_from_python(power));const auto pol=pcb_emission_policy(policy);JsonNode result;
        {nb::gil_scoped_release release;result=run_assembly_documents(model,p,name,md,png_dir,pol);}
        return json_to_python(result);
    });
    m.def("assembly_verdict", [](nb::object raw,const std::string& root) {
        return assembly_verdict(json_from_python(raw),root);
    },nb::arg("result").none(),nb::arg("root"));
}
}
