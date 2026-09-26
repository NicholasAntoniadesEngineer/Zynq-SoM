#pragma once
#include "schgen/gallery.hpp"
#include "schgen/diagram.hpp"
#include "schgen/link_bindings.hpp"

namespace schgen {
inline void bind_gallery_diagram(nanobind::module_& m) {
    namespace nb=nanobind;
    m.def("block_diagram_write",[](const nb::dict& raw,const LinkSomNets& nets,const std::string& output){
        const auto result=link_result_from_python(raw);
        nb::gil_scoped_release release;
        return write_block_diagram(result,nets,output).string();
    });
    m.def("gallery_targets",[](const std::string& root,const std::string& project){
        return gallery_readme_targets(load_gallery_input(resolve_project_paths(root,project)));
    });
    m.def("gallery_section",[](const std::string& root,const std::string& project,const std::string& directory,bool compact){
        nb::gil_scoped_release release;
        const auto input=load_gallery_input(resolve_project_paths(root,project));
        return compact?render_gallery_compact(input,directory):render_gallery_full(input,directory);
    });
    m.def("gallery_run",[](const std::string& root,const std::string& project){
        nb::gil_scoped_release release;
        const auto input=load_gallery_input(resolve_project_paths(root,project));
        const auto changed=write_gallery(input);std::vector<std::string> paths;
        for(const auto& path:changed)paths.push_back(path.string());
        return std::make_pair(paths,gallery_summary(input,changed));
    });
}
}
