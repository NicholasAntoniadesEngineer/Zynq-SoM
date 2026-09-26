#pragma once

// Transitional data transport only. Rendering, measurement, validation, report
// formatting and publication remain in the Python-independent C++ core.
#include "schgen/model3d.hpp"
#include "schgen/native_render.hpp"
#include <cstdint>
#include <nanobind/nanobind.h>
#include <nanobind/stl/array.h>
#include <nanobind/stl/map.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>

namespace schgen {
namespace native_render_bindings_detail {
namespace nb=nanobind;
inline NativeRenderOptions options(const std::string& executable,std::int64_t timeout_ms) {
    NativeRenderOptions out; out.kicad_cli=executable; out.timeout=std::chrono::milliseconds(timeout_ms); return out;
}
inline Render3dOptions options3d(const std::string& quality,int width,int height,
                               const std::optional<std::string>& models,
                               const std::string& executable,std::int64_t timeout_ms) {
    Render3dOptions out; out.quality=quality; out.width=width; out.height=height;
    out.kicad_cli=executable; out.timeout=std::chrono::milliseconds(timeout_ms);
    if (models) out.model_directory=*models;
    return out;
}
inline nb::dict page_data(const PageRaster& r) {
    nb::dict out; out["png_path"]=nb::cast(r.png_path.string()); out["width_px"]=r.width_px;
    out["height_px"]=r.height_px; out["page_w_mm"]=r.page_w_mm;
    out["page_h_mm"]=r.page_h_mm; out["dpi"]=r.dpi; return out;
}
inline nb::dict model_data(const Model3dResult& r) {
    nb::dict out; out["ok"]=r.ok; out["total"]=r.total; out["covered"]=r.covered;
    out["unmatched"]=nb::cast(r.unmatched); out["broken"]=nb::cast(r.broken);
    out["misfit"]=nb::cast(r.misfit); out["misplaced"]=nb::cast(r.misplaced);
    out["missing"]=nb::cast(r.missing); out["invalid"]=nb::cast(r.invalid);
    out["line"]=nb::cast(r.line()); out["report"]=nb::cast(r.report()); return out;
}
inline Model3dResult model_from_data(const nb::dict& raw) {
    Model3dResult out; out.ok=nb::cast<bool>(raw["ok"]);
    out.total=nb::cast<std::size_t>(raw["total"]); out.covered=nb::cast<std::size_t>(raw["covered"]);
    out.unmatched=nb::cast<decltype(out.unmatched)>(raw["unmatched"]);
    out.broken=nb::cast<decltype(out.broken)>(raw["broken"]);
    out.misfit=nb::cast<decltype(out.misfit)>(raw["misfit"]);
    out.misplaced=nb::cast<decltype(out.misplaced)>(raw["misplaced"]);
    out.missing=nb::cast<decltype(out.missing)>(raw["missing"]);
    if (raw.contains("invalid")) out.invalid=nb::cast<decltype(out.invalid)>(raw["invalid"]);
    return out;
}
inline nb::dict geometry_data(const Model3dGeometry& r) {
    nb::dict out; out["model_xy"]=nb::cast(r.model_xy); out["fab_xy"]=nb::cast(r.fab_xy);
    out["model_box"]=nb::cast(r.model_box); out["pad_box"]=nb::cast(r.pad_box);
    out["misfit"]=nb::cast(r.misfit); out["misplaced"]=nb::cast(r.misplaced); return out;
}
inline nb::dict render_data(const Render3dResult& r) {
    nb::dict out; std::vector<std::string> written;
    for (const auto& path:r.written) written.push_back(path.string());
    out["written"]=nb::cast(written); out["ok"]=r.ok(); out["summary"]=nb::cast(r.summary());
    nb::list views,failures;
    for (const auto& v:r.views) {
        nb::dict row; row["view"]=nb::cast(v.view); row["path"]=nb::cast(v.path.string());
        row["width"]=v.width; row["height"]=v.height; views.append(row);
    }
    for (const auto& f:r.failures) {
        nb::dict row; row["view"]=nb::cast(f.view); row["diagnostic"]=nb::cast(f.diagnostic); failures.append(row);
    }
    out["views"]=views; out["failures"]=failures; return out;
}
}

inline void bind_native_render(nanobind::module_& m) {
    namespace nb=nanobind;
    namespace detail=native_render_bindings_detail;
    m.def("render_sheet_to_png",[](const std::string& schematic,const std::string& png,int dpi,const std::string& executable,std::int64_t timeout_ms) {
        PageRaster r;
        { nb::gil_scoped_release release; r=render_sheet_to_png(schematic,png,dpi,detail::options(executable,timeout_ms)); }
        return detail::page_data(r);
    },nb::arg("schematic_path"),nb::arg("png_path"),nb::arg("dpi")=300,
      nb::arg("kicad_cli")="kicad-cli",nb::arg("timeout_ms")=300000);
    m.def("render_pdf_to_png",[](const std::string& pdf,const std::string& png,int dpi) {
        PageRaster r; { nb::gil_scoped_release release; r=render_pdf_to_png(pdf,png,dpi); }
        return detail::page_data(r);
    },nb::arg("pdf_path"),nb::arg("png_path"),nb::arg("dpi")=300);
    m.def("render_mm_to_px",[](int width,int height,double page_w,double page_h,double x,double y) {
        return PageRaster{{},width,height,page_w,page_h,0}.mm_to_px(x,y);
    },nb::arg("width_px"),nb::arg("height_px"),nb::arg("page_w_mm"),nb::arg("page_h_mm"),nb::arg("x_mm"),nb::arg("y_mm"));
    m.def("render3d_find_model_dir",[]() -> std::optional<std::string> {
        const auto path=find_render_model_directory(); return path?std::optional<std::string>(path->string()):std::nullopt;
    },nb::call_guard<nb::gil_scoped_release>());
    m.def("render3d_run",[](const std::string& pcb,const std::string& output,const std::string& quality,int width,int height,
                            const std::optional<std::string>& models,const std::string& executable,std::int64_t timeout_ms) {
        Render3dResult r;
        { nb::gil_scoped_release release; r=render_board_3d(pcb,output,detail::options3d(quality,width,height,models,executable,timeout_ms)); }
        return detail::render_data(r);
    },nb::arg("pcb"),nb::arg("out_dir"),nb::arg("quality")="high",nb::arg("width")=1600,nb::arg("height")=1200,
      nb::arg("model_dir").none()=nb::none(),nb::arg("kicad_cli")="kicad-cli",nb::arg("timeout_ms")=300000);
    m.def("render3d_export_step",[](const std::string& pcb,const std::string& output,const std::optional<std::string>& models,
                                    const std::string& executable,std::int64_t timeout_ms) {
        nb::gil_scoped_release release;
        export_board_step(pcb,output,detail::options3d("high",1600,1200,models,executable,timeout_ms));
    },nb::arg("pcb"),nb::arg("output"),nb::arg("model_dir").none()=nb::none(),
      nb::arg("kicad_cli")="kicad-cli",nb::arg("timeout_ms")=300000);
    m.def("model3d_default_directory",[] { return default_model3d_directory().string(); });
    m.def("model3d_resolve_path",[](const std::string& raw,const std::string& models,const std::string& project) -> std::optional<std::string> {
        const auto path=resolve_model3d_path(raw,models,project); return path?std::optional<std::string>(path->string()):std::nullopt;
    },nb::arg("raw"),nb::arg("model_dir"),nb::arg("project_root"));
    m.def("model3d_measure",[](const std::string& footprint,const std::string& clause,const std::string& model,const std::string& extension) {
        Model3dGeometry r; { nb::gil_scoped_release release; r=measure_model3d(footprint,clause,model,extension); }
        return detail::geometry_data(r);
    },nb::arg("footprint_text"),nb::arg("clause_body"),nb::arg("model_text"),nb::arg("extension"));
    m.def("model3d_check",[](const std::string& parts,const std::string& project,const std::optional<std::string>& models) {
        Model3dResult r;
        { nb::gil_scoped_release release; r=check_model3d(parts,project,models?std::filesystem::path(*models):default_model3d_directory()); }
        return detail::model_data(r);
    },nb::arg("parts_directory"),nb::arg("project_root"),nb::arg("model_dir").none()=nb::none());
    m.def("model3d_run",[](const std::string& parts,const std::string& project,const std::string& reports,const std::optional<std::string>& models) {
        Model3dResult r;
        { nb::gil_scoped_release release; r=run_model3d(parts,project,reports,models?std::filesystem::path(*models):default_model3d_directory()); }
        return detail::model_data(r);
    },nb::arg("parts_directory"),nb::arg("project_root"),nb::arg("report_directory"),nb::arg("model_dir").none()=nb::none());
    m.def("model3d_result_text",[](const nb::dict& raw) {
        const auto result=detail::model_from_data(raw); nb::dict out;
        out["line"]=nb::cast(result.line()); out["report"]=nb::cast(result.report()); return out;
    },nb::arg("result"));
    m.def("model3d_obj_to_wrl",&model3d_obj_to_wrl,nb::arg("obj"),nb::call_guard<nb::gil_scoped_release>());
}
}
