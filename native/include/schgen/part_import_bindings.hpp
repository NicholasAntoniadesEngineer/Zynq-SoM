#pragma once

// Transitional, data-only compatibility boundary. No conversion, transport or
// publication policy lives in the Python adapter or in interpreter callbacks.
#include "schgen/part_import.hpp"
#include "schgen/json_bindings.hpp"
#include <cstdint>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>

namespace schgen::part_import_binding {
namespace nb=nanobind;
inline CatalogPin pin(nb::handle value) {
    const auto row=nb::cast<nb::dict>(value);
    return {nb::cast<std::string>(row["number"]),nb::cast<std::string>(row["name"]),nb::cast<std::string>(row["etype"])};
}
inline std::vector<CatalogPin> pins(const nb::iterable& rows) {
    std::vector<CatalogPin> out;for(auto row:rows)out.push_back(pin(row));return out;
}
inline nb::dict pin_data(const CatalogPin& p) {
    nb::dict out;out["number"]=p.number;out["name"]=p.name;out["etype"]=p.etype;return out;
}
inline nb::list pin_data(const std::vector<CatalogPin>& pins) {
    nb::list out;for(const auto& p:pins)out.append(pin_data(p));return out;
}
inline PartImportInfo info(const nb::dict& d) {
    PartImportInfo out;auto& p=out.part;
    auto value=[&](const char* k,const std::string& fallback=""){return d.contains(k)?nb::cast<std::string>(d[k]):fallback;};
    p.mpn=value("mpn");p.lcsc=value("lcsc");p.prefix=value("prefix","U");p.package=value("package");
    p.description=value("description");p.manufacturer=value("manufacturer");p.jlc_class=value("jlc_class");
    p.product_url=value("product_url");p.datasheet=value("datasheet");
    if(d.contains("tags"))out.tags=nb::cast<std::vector<std::string>>(d["tags"]);
    return out;
}
inline nb::dict info_data(const PartImportInfo& info) {
    nb::dict out;const auto& p=info.part;
    out["mpn"]=p.mpn;out["lcsc"]=p.lcsc;out["prefix"]=p.prefix;out["package"]=p.package;
    out["description"]=p.description;out["manufacturer"]=p.manufacturer;out["jlc_class"]=p.jlc_class;
    out["product_url"]=p.product_url;out["datasheet"]=p.datasheet;out["tags"]=nb::cast(info.tags);return out;
}
inline nb::object tagged(const Sexpr& node) {
    if(const auto* v=std::get_if<Sexpr::Sym>(&node.v))return nb::make_tuple("sym",v->name);
    if(const auto* v=std::get_if<std::string>(&node.v))return nb::make_tuple("str",*v);
    if(const auto* v=std::get_if<double>(&node.v))return nb::make_tuple("num",*v);
    if(const auto* v=std::get_if<bool>(&node.v))return nb::make_tuple("bool",*v);
    nb::list out;for(const auto& child:std::get<SexprList>(node.v))out.append(tagged(child));
    return nb::make_tuple("list",out);
}
inline nb::list tagged_nodes(const std::vector<Sexpr>& nodes) {
    nb::list out;for(const auto& n:nodes)out.append(tagged(n));return out;
}
inline nb::object model_data(const std::optional<PartModelTransform>& m) {
    if(!m)return nb::none();nb::dict out;
    out["uuid"]=m->uuid;out["title"]=m->title;out["tx"]=m->tx;out["ty"]=m->ty;out["tz"]=m->tz;
    out["rx"]=m->rx;out["ry"]=m->ry;out["rz"]=m->rz;return out;
}
} // namespace schgen::part_import_binding

namespace schgen {
inline void bind_part_import(nanobind::module_& m) {
    namespace nb=nanobind;
    namespace d=part_import_binding;
    m.def("part_import_info",[](const nb::dict& result){return d::info_data(part_import_info(json_from_python(result)));});
    m.def("part_import_pins",[](const nb::dict& result){return d::pin_data(part_import_pins(json_from_python(result)));});
    m.def("part_normalize_pin_types",[](const nb::iterable& pins,const std::string& prefix){return d::pin_data(part_normalize_pin_types(d::pins(pins),prefix));});
    m.def("part_safe_name",&part_safe_name);
    m.def("part_next_pin_number",[](const nb::iterable& pins){return part_next_pin_number(d::pins(pins));});
    m.def("part_synthesize_ep",[](const std::string& lcsc,const nb::iterable& pins)->nb::object {
        const auto p=part_synthesize_ep(lcsc,d::pins(pins));return p?nb::object(d::pin_data(*p)):nb::none();
    });
    m.def("part_ep_pad_nodes",[](const std::string& number,const std::string& lcsc){return d::tagged_nodes(part_ep_pad_nodes(number,lcsc));});
    m.def("part_silk_plus_nodes",[](const std::string& lcsc){return d::tagged_nodes(part_silk_plus_nodes(lcsc));});
    m.def("part_group_pins",[](const nb::iterable& pins){
        const auto g=part_group_pins(d::pins(pins));nb::dict out;
        out["left"]=d::pin_data(g.left);out["right"]=d::pin_data(g.right);out["top"]=d::pin_data(g.top);out["bottom"]=d::pin_data(g.bottom);return out;
    });
    m.def("part_generate_symbol",[](const std::string& name,const nb::iterable& pins,const nb::dict& raw_info){
        auto info=d::info(raw_info);if(!raw_info.contains("mpn"))info.part.mpn=name;
        const auto values=d::pins(pins);Sexpr result;
        {nb::gil_scoped_release release;result=part_generate_symbol(name,values,info);}
        return d::tagged(result);
    });
    m.def("part_convert_footprint",[](const nb::dict& raw_result,const std::string& name,const nb::dict& raw_info,
                                       const std::vector<std::string>& models,const nb::object& raw_ep){
        const auto result=json_from_python(raw_result);const auto info=d::info(raw_info);
        const auto ep=raw_ep.is_none()?std::optional<CatalogPin>{}:std::optional<CatalogPin>{d::pin(raw_ep)};
        PartFootprint fp;{nb::gil_scoped_release release;fp=part_convert_footprint(result,name,info,models,ep);}
        nb::dict out;out["tree"]=d::tagged(fp.tree);out["model"]=d::model_data(fp.model);out["diagnostics"]=nb::cast(fp.diagnostics);return out;
    },nb::arg("result"),nb::arg("name"),nb::arg("info"),nb::arg("models"),nb::arg("ep").none()=nb::none());
    m.def("part_metadata_json",[](const std::string& name,const nb::dict& raw_info,const nb::iterable& pins,const std::vector<std::string>& models){
        auto p=d::info(raw_info).part;p.safe_name=name;p.lib_id=p.footprint=name+":"+name;p.pins=d::pins(pins);p.models_3d=models;
        return part_metadata_json(p);
    });
    m.def("part_http_get",[](const std::string& url,std::int64_t timeout_ms){
        std::string bytes;
        {nb::gil_scoped_release release;const PartHttpRequest request{url,std::chrono::milliseconds(timeout_ms)};
         bytes=part_http_body(request,part_curl_transport()(request));}
        return nb::bytes(bytes.data(),bytes.size());
    },nb::arg("url"),nb::arg("timeout_ms")=30000);
    m.def("part_fetch_cad",[](const std::string& lcsc){
        JsonNode payload;{nb::gil_scoped_release release;payload=parse_json_text(fetch_part_cad(lcsc,part_curl_transport()));}
        return json_to_python(payload);
    });
    m.def("part_fetch_3d_models",[](const std::string& uuid,const std::string& outdir,const std::string& base,bool overwrite){
        PartModelDownload download;std::vector<std::string> files;
        {nb::gil_scoped_release release;download=fetch_part_models(uuid,base,part_curl_transport());files=publish_part_models(download,outdir,base,overwrite);}
        nb::dict out;out["files"]=nb::cast(files);out["diagnostics"]=nb::cast(download.diagnostics);return out;
    },nb::arg("uuid"),nb::arg("outdir"),nb::arg("base"),nb::arg("overwrite")=false);
    m.def("part_add",[](const std::string& lcsc,const std::optional<std::string>& name,const std::string& root,
                        const std::optional<std::string>& from_json,bool overwrite){
        PartImportRequest request;request.lcsc=lcsc;request.name=name.value_or("");request.parts_root=root;
        if(from_json)request.from_json=*from_json;
        PartImportPlan plan;std::filesystem::path outdir;
        {nb::gil_scoped_release release;
         plan=prepare_part_import_request(request,from_json?PartTransport{}:part_curl_transport());outdir=publish_part_import(plan,root,overwrite);}
        nb::dict out;out["outdir"]=outdir.string();out["mpn"]=plan.part.mpn;out["lcsc"]=plan.part.lcsc;
        out["name"]=plan.part.safe_name;out["pins"]=plan.part.pins.size();out["pads"]=plan.pad_count;
        out["models"]=nb::cast(plan.part.models_3d);out["diagnostics"]=nb::cast(plan.diagnostics);return out;
    },nb::arg("lcsc"),nb::arg("name").none(),nb::arg("parts_root"),nb::arg("from_json").none(),nb::arg("overwrite")=false);
}
} // namespace schgen
