#pragma once
#include "schgen/ratsnest_documents.hpp"
#include <nanobind/stl/array.h>

namespace schgen {
inline void bind_ratsnest_documents(nanobind::module_& m) {
    namespace nb=nanobind;
    m.def("ratsnest_palette",&ratsnest_palette);
    m.def("ratsnest_airwires",[](const PcbModel& model,const std::optional<std::string>& side,const RatsnestNets& nets,const RatsnestEdges& edges){
        std::vector<std::tuple<double,double,double,double,bool>> out;
        for(const auto& wire:ratsnest_airwires(model,nets,edges,side))out.emplace_back(wire.x0,wire.y0,wire.x1,wire.y1,wire.cross);
        return out;
    },nb::arg("model"),nb::arg("side").none(),nb::arg("nets"),nb::arg("edges"));
    m.def("ratsnest_svg",&render_ratsnest_svg,nb::call_guard<nb::gil_scoped_release>());
    m.def("ratsnest_board_png",[](const PcbModel& model,const RatsnestPalette& palette,const std::string& side,const RatsnestNets& nets,const RatsnestEdges& edges){
        RatsnestImage image;{nb::gil_scoped_release release;image=render_ratsnest_board_image(model,palette,side,nets,edges);}
        return nb::bytes(image.png.data(),image.png.size());
    });
    m.def("ratsnest_sheet_png",[](const PcbModel& model,const std::string& sheet,const std::set<std::string>& refs,const RatsnestNets& nets,const RatsnestEdges& edges,const std::set<std::string>& som_refs){
        RatsnestImage image;{nb::gil_scoped_release release;image=render_ratsnest_sheet_image(model,sheet,refs,nets,edges,som_refs);}
        return nb::bytes(image.png.data(),image.png.size());
    });
    m.def("ratsnest_sheet_pngs",[](const PcbModel& model,const RatsnestNets& nets,const RatsnestEdges& edges){
        std::vector<RatsnestImage> images;{nb::gil_scoped_release release;images=render_ratsnest_subsystem_images(model,nets,edges);}
        nb::list out;for(const auto& image:images)out.append(nb::make_tuple(image.filename,nb::bytes(image.png.data(),image.png.size())));return out;
    });
    m.def("ratsnest_run",[](const PcbModel& model,const std::string& root,
            const std::optional<RatsnestNets>& nets,const std::optional<RatsnestEdges>& edges){
        RatsnestPublication result;
        {nb::gil_scoped_release release;result=run_ratsnest_documents(model,root,nets?&*nets:nullptr,edges?&*edges:nullptr);}
        nb::dict out;out["png_top"]=nb::cast(result.png_top.string());out["png_bottom"]=nb::cast(result.png_bottom.string());out["svg"]=nb::cast(result.svg.string());
        out["cross_mm"]=result.cross_mm;out["total_mm"]=result.total_mm;out["n_cross"]=result.n_cross;
        out["board_w"]=result.board_w;out["board_h"]=result.board_h;out["n_top"]=result.n_top;out["n_bottom"]=result.n_bottom;return out;
    },nb::arg("model"),nb::arg("root"),nb::arg("nets").none(),nb::arg("edges").none());
}
}
