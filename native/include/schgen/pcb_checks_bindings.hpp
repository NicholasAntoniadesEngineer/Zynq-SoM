#pragma once
#include "schgen/pcb_checks.hpp"
#include "schgen/ratsnest_gate.hpp"
#include "schgen/model_checks_bindings.hpp"
#include <nanobind/stl/map.h>
#include <nanobind/stl/tuple.h>
#include <nanobind/stl/set.h>

namespace schgen {
namespace pcb_check_binding {
namespace nb=nanobind;
template<class T> void field(T& value,nb::dict& d,const char* key,bool read) {
    if(read)value=nb::cast<T>(d[key]);else d[key]=nb::cast(value);
}
inline std::optional<Box4> box(nb::handle raw) {
    if(raw.is_none())return std::nullopt;
    const auto v=nb::cast<std::tuple<double,double,double,double>>(raw);
    return Box4{std::get<0>(v),std::get<1>(v),std::get<2>(v),std::get<3>(v)};
}
inline nb::object box(const std::optional<Box4>& b) {
    if(!b)return nb::none();return nb::make_tuple(b->x0,b->y0,b->x1,b->y1);
}
inline void transfer(ConnectorModelResult& r, nb::dict& d, bool read) {
    field(r.ok,d,"ok",read);
    field(r.n_connectors,d,"n_connectors",read);
    field(r.bad_z,d,"bad_z",read);
    field(r.missing_model,d,"missing_model",read);
    field(r.geom_conflicts,d,"geom_conflicts",read);
    field(r.geom_checked,d,"geom_checked",read);
    using Row=std::tuple<std::string,std::string,std::string,std::optional<double>,bool>;
    if(read){for(const auto& v:nb::cast<std::vector<Row>>(d["models"]))r.models.push_back({std::get<0>(v),std::get<1>(v),std::get<2>(v),std::get<3>(v),std::get<4>(v)});}
    else{nb::list rows;for(const auto& v:r.models)rows.append(nb::make_tuple(v.ref,v.mpn,v.value,v.z,v.ok));d["models"]=rows;}
}
inline void transfer(ConnectorSpacingResult& r, nb::dict& d, bool read) {
    field(r.ok,d,"ok",read);
    field(r.board_w,d,"board_w",read);
    field(r.board_h,d,"board_h",read);
    field(r.violations,d,"violations",read);
    using Row=std::tuple<std::string,std::string,std::string,std::string,double,double,bool>;
    if(read){for(const auto& v:nb::cast<std::vector<Row>>(d["pairs"]))r.pairs.push_back({std::get<0>(v),std::get<1>(v),std::get<2>(v),std::get<3>(v),std::get<4>(v),std::get<5>(v),std::get<6>(v)});}
    else{nb::list rows;for(const auto& v:r.pairs)rows.append(nb::make_tuple(v.ref_a,v.ref_b,v.family,v.axis,v.gap,v.need,v.ok));d["pairs"]=rows;}
}
inline void transfer(PlacementMechResult& r, nb::dict& d, bool read) {
    field(r.ok,d,"ok",read);
    field(r.board_w,d,"board_w",read);
    field(r.board_h,d,"board_h",read);
    field(r.n_connectors,d,"n_connectors",read);
    field(r.n_face_top,d,"n_face_top",read);
    field(r.bad_connectors,d,"bad_connectors",read);
    field(r.under_som,d,"under_som",read);
    field(r.controls_under_som,d,"controls_under_som",read);
    field(r.top_under_som,d,"top_under_som",read);
    field(r.face_top_on_bottom,d,"face_top_on_bottom",read);
    using Row=std::tuple<std::string,std::string,std::string,double,std::pair<int,int>,double,bool>;
    if(read){r.som_core=box(d["som_core"]);for(const auto& v:nb::cast<std::vector<Row>>(d["connectors"]))r.connectors.push_back({std::get<0>(v),std::get<1>(v),std::get<2>(v),std::get<3>(v),std::get<5>(v),std::get<4>(v),std::get<6>(v)});}
    else{d["som_core"]=box(r.som_core);nb::list rows;for(const auto& v:r.connectors)rows.append(nb::make_tuple(v.ref,v.mpn,v.edge,v.rotation,v.face_dir,v.flush,v.ok));d["connectors"]=rows;}
}
inline void transfer(PcbFanoutRecord& r, nb::dict& d, bool read) {
    field(r.ref,d,"ref",read);
    field(r.sheet,d,"sheet",read);
    field(r.side,d,"side",read);
    field(r.pins,d,"pins",read);
    field(r.clearance,d,"clearance",read);
    field(r.need,d,"need",read);
    field(r.nearest_ref,d,"nearest_ref",read);
    field(r.nearest_sheet,d,"nearest_sheet",read);
    field(r.basis,d,"basis",read);

}
inline void transfer(PcbFanoutResult& r, nb::dict& d, bool read) {
    field(r.ok,d,"ok",read);
    field(r.n_subjects,d,"n_subjects",read);
    field(r.n_starved,d,"n_starved",read);
    field(r.baseline,d,"baseline",read);
    field(r.regressions,d,"regressions",read);
    if(read){for(auto raw:nb::cast<nb::list>(d["records"])){PcbFanoutRecord rec;auto row=nb::cast<nb::dict>(raw);transfer(rec,row,true);r.records.push_back(rec);}}
    else{nb::list rows;for(auto& rec:r.records){nb::dict row;transfer(rec,row,false);rows.append(row);}d["records"]=rows;}
}
inline void transfer(RefdesOverlapResult& r, nb::dict& d, bool read) {
    field(r.ok,d,"ok",read);
    field(r.n_top,d,"n_top",read);
    field(r.n_bottom,d,"n_bottom",read);
    field(r.bottom_pairs,d,"bottom_pairs",read);
    field(r.top_pairs,d,"top_pairs",read);

}
inline void transfer(ReturnPathContact& r, nb::dict& d, bool read) {
    field(r.ref,d,"ref",read);
    field(r.pad,d,"pad",read);
    field(r.row,d,"row",read);
    field(r.index,d,"index",read);
    field(r.x,d,"x",read);
    field(r.y,d,"y",read);
    field(r.net,d,"net",read);
    field(r.klass,d,"klass",read);

}
inline void transfer(ReturnPathViolation& r, nb::dict& d, bool read) {
    field(r.ref,d,"ref",read);
    field(r.base,d,"base",read);
    field(r.net,d,"net",read);
    field(r.pad,d,"pad",read);
    field(r.distance,d,"distance",read);

}
inline void transfer(ReturnPathResult& r, nb::dict& d, bool read) {
    field(r.ok,d,"ok",read);
    field(r.k,d,"k",read);
    field(r.n_pairs,d,"n_pairs",read);
    field(r.n_pair_contacts,d,"n_pair_contacts",read);
    field(r.dist_hist,d,"dist_hist",read);
    field(r.per_conn,d,"per_conn",read);
    field(r.pairs_per_conn,d,"pairs_per_conn",read);
    field(r.worst_distance,d,"worst_distance",read);
    field(r.connectors,d,"connectors",read);
    if(read){for(auto raw:nb::cast<nb::list>(d["violations"])){ReturnPathViolation rec;auto row=nb::cast<nb::dict>(raw);transfer(rec,row,true);r.violations.push_back(rec);}}
    else{nb::list rows;for(auto& rec:r.violations){nb::dict row;transfer(rec,row,false);rows.append(row);}d["violations"]=rows;}
}
inline void transfer(EscapeLaneResult& r, nb::dict& d, bool read) {
    field(r.ok,d,"ok",read);
    field(r.n_lanes,d,"n_lanes",read);
    field(r.n_pairs,d,"n_pairs",read);
    field(r.n_genuine,d,"n_genuine",read);
    field(r.violations,d,"violations",read);

}
inline void transfer(ReturnStitchResult& r, nb::dict& d, bool read) {
    field(r.ok,d,"ok",read);
    field(r.hash_ok,d,"hash_ok",read);
    field(r.radius,d,"radius",read);
    field(r.worst_mm,d,"worst_mm",read);
    field(r.n_contacts,d,"n_contacts",read);
    field(r.n_covered,d,"n_covered",read);
    field(r.n_vias,d,"n_vias",read);
    field(r.violations,d,"violations",read);
    field(r.per_conn,d,"per_conn",read);
    field(r.v1_verdict,d,"v1_verdict",read);
    field(r.file_parity,d,"file_parity",read);
    using Row=std::tuple<int,std::string,std::string,std::string,std::string,std::optional<double>>;
    if(read){for(const auto& v:nb::cast<std::vector<Row>>(d["coverage"]))r.coverage.push_back({std::get<0>(v),std::get<1>(v),std::get<2>(v),std::get<3>(v),std::get<4>(v),std::get<5>(v)});}
    else{nb::list rows;for(const auto& v:r.coverage)rows.append(nb::make_tuple(v.rank,v.klass,v.ref,v.pad,v.function,v.distance));d["coverage"]=rows;}
}
inline void transfer(PcbRailAmpacity& r, nb::dict& d, bool read) {
    field(r.name,d,"name",read);
    field(r.contacts,d,"contacts",read);
    field(r.current_a,d,"current_a",read);
    field(r.volts,d,"volts",read);
    field(r.conns,d,"conns",read);

}
inline void transfer(RailAmpacityResult& r, nb::dict& d, bool read) {
    field(r.errors,d,"errors",read);
    field(r.findings,d,"findings",read);
    field(r.per_contact_a,d,"per_contact_a",read);
    field(r.derating,d,"derating",read);
    if(read){for(auto raw:nb::cast<nb::list>(d["rails"])){PcbRailAmpacity rec;auto row=nb::cast<nb::dict>(raw);transfer(rec,row,true);r.rails.push_back(rec);}}
    else{nb::list rows;for(auto& rec:r.rails){nb::dict row;transfer(rec,row,false);rows.append(row);}d["rails"]=rows;}
}
inline void transfer(RatsnestGateResult& r, nb::dict& d, bool read) {
    field(r.ok,d,"ok",read);
    field(r.off_board,d,"off_board",read);
    field(r.dispersed,d,"dispersed",read);
    field(r.clusters,d,"clusters",read);
    field(r.cross_mm,d,"cross_mm",read);
    field(r.total_mm,d,"total_mm",read);
    field(r.n_cross,d,"n_cross",read);
    field(r.n_subsystems,d,"n_subsystems",read);
    field(r.cross_budget_mm,d,"cross_budget_mm",read);
    field(r.board_w,d,"board_w",read);
    field(r.board_h,d,"board_h",read);
}
template<class T> nb::dict result(T value) {nb::dict out;transfer(value,out,false);return out;}
template<class T> T result(nb::dict value) {T out;transfer(out,value,true);return out;}
inline PcbCheckModel model(const nb::dict& d,const std::map<std::string,std::string>& files) {
    using model_binding::get;PcbCheckModel r;
    r.board_w=get<double>(d,"board_w");r.board_h=get<double>(d,"board_h");
    r.origin_x=get<double>(d,"origin_x");r.origin_y=get<double>(d,"origin_y");
    r.net_numbers=get<std::map<std::string,int>>(d,"net_numbers");
    r.netclass_of=get<std::map<std::string,std::string>>(d,"netclass_of");
    r.som_core=box(d["som_core"]);
    std::map<std::string,PcbCheckFootprintPtr> pool;
    for(const auto& [path,bytes]:files)pool.emplace(path,pcb_check_footprint(path,bytes));
    for(auto raw:get<nb::list>(d,"insts")) {
        const auto v=nb::cast<nb::dict>(raw);PcbCheckInstance i;
        i.ref=get<std::string>(v,"ref");i.value=get<std::string>(v,"value");i.footprint=get<std::string>(v,"footprint");
        i.sheet=get<std::string>(v,"sheet");i.side=get<std::string>(v,"side");
        i.x=get<double>(v,"x");i.y=get<double>(v,"y");i.rotation=get<double>(v,"rotation");
        i.pad_nets=get<std::map<std::string,std::pair<int,std::string>>>(v,"pad_nets");i.mirror=get<bool>(v,"mirror");
        const auto path=get<std::optional<std::string>>(v,"mod_path");if(path){const auto f=pool.find(*path);if(f!=pool.end())i.mod=f->second;}
        r.insts.push_back(std::move(i));
    }
    for(auto raw:get<nb::list>(d,"copper")) {
        const auto v=nb::cast<nb::dict>(raw);PcbCheckCopper c;
        auto string=[&](const char* key,std::string& val){if(v.contains(key))val=nb::cast<std::string>(v[key]);};
        auto number=[&](const char* key,double& val){if(v.contains(key))val=nb::cast<double>(v[key]);};
        string("kind",c.kind);string("group",c.group);string("conn",c.conn);string("role",c.role);string("net_name",c.net_name);string("layer",c.layer);
        if(v.contains("net"))c.net=get<int>(v,"net");
        number("x",c.x);number("y",c.y);number("x1",c.x1);number("y1",c.y1);number("x2",c.x2);number("y2",c.y2);
        number("size",c.size);number("drill",c.drill);number("width",c.width);r.copper.push_back(std::move(c));
    }
    if(!d["escape_plan"].is_none())r.escape_plan=pcb_escape_plan_from_json(json_from_python(d["escape_plan"]));
    r.escape_interface_sha256=get<std::optional<std::string>>(d,"escape_interface_sha256");
    return r;
}
}
inline void bind_pcb_checks(nanobind::module_& m) {
    namespace nb=nanobind;using namespace pcb_check_binding;
    nb::class_<PcbCheckInput>(m,"PcbCheckInput");
    m.def("pcb_ratsnest", [](const PcbCheckInput& input,
            const std::optional<RatsnestNets>& nets,
            const std::optional<RatsnestEdges>& edges, double cross_k) {
        RatsnestGateResult value;
        { nb::gil_scoped_release release;
          value = check_ratsnest(input, nets ? &*nets : nullptr, edges ? &*edges : nullptr, cross_k); }
        return result(value);
    }, nb::arg("input"), nb::arg("nets").none(), nb::arg("edges").none(), nb::arg("cross_k"));
    m.def("pcb_ratsnest_summary", [](nb::dict raw) { return result<RatsnestGateResult>(raw).summary(); });
    m.def("pcb_check_prepare",[](const nb::dict& raw,const std::map<std::string,std::string>& files){
        return PcbCheckInput(model(raw,files));
    });
    m.def("pcb_connector_models",[](const PcbCheckInput& in,const std::map<std::string,std::string>& faces){return result(check_connector_models(in.model(),faces));});
    m.def("pcb_connector_spacing",[](const PcbCheckInput& in){return result(check_connector_spacing(in));});
    m.def("pcb_placement_mech",[](const PcbCheckInput& in){return result(check_placement_mech(in));});
    m.def("pcb_fanout",[](const PcbCheckInput& in,std::optional<int> baseline){return result(check_fanout(in,baseline));},
        nb::arg("input"),nb::arg("baseline").none());
    m.def("pcb_fanout_ratchet",&pcb_fanout_ratchet,nb::arg("count"),nb::arg("previous").none());
    m.def("pcb_is_df40_part",&pcb_is_df40_part);
    m.def("pcb_counts_as_crowder",&pcb_counts_as_crowder);
    m.def("pcb_fanout_need",&pcb_fanout_need);
    m.def("pcb_refdes_overlap",[](const std::string& bytes,bool bottom){return result(check_refdes_overlap(sexpr_loads(bytes),bottom));});
    m.def("pcb_return_path_map",[](const nb::dict& rows,int k){
        std::map<std::string,std::vector<ReturnPathContact>> cs;
        for(auto [key,value]:rows)for(auto row:nb::cast<nb::list>(value))
            cs[nb::cast<std::string>(key)].push_back(result<ReturnPathContact>(nb::cast<nb::dict>(row)));
        return result(check_return_path(cs,k));
    });
    m.def("pcb_return_path_contacts",[](const std::string& ref,const std::map<std::string,std::string>& pins,const std::string& source,const std::string& bytes){
        XdcStrings pairs;for(const auto& p:pins)pairs.push_back(p);nb::list out;
        for(const auto& c:build_return_path_contacts(ref,pairs,*pcb_check_footprint(source,bytes)))out.append(result(c));return out;
    });
    m.def("pcb_return_contacts_positions",[](const std::string& ref,const std::map<std::string,std::string>& pins,const std::map<std::string,std::pair<double,double>>& positions){
        XdcStrings pairs;for(const auto& p:pins)pairs.push_back(p);nb::list out;
        for(const auto& c:build_return_path_contacts(ref,pairs,positions))out.append(result(c));return out;
    });
    m.def("pcb_return_pad_positions",[](const std::string& source,const std::string& bytes){
        std::map<std::string,std::pair<double,double>> out;
        const auto footprint=pcb_check_footprint(source,bytes);
        for(const auto& p:footprint->pads)
            if(!std::get<0>(p).empty())out[std::get<0>(p)]={std::get<2>(p),std::get<3>(p)};
        return out;
    });
    m.def("pcb_return_violation_line",[](const nb::dict& raw){return result<ReturnPathViolation>(raw).as_line();});
    m.def("pcb_classify_net",&pcb_classify_net);m.def("pcb_pair_partner",&pcb_pair_partner);
    m.def("pcb_pair_base",&pcb_pair_base);m.def("pcb_hs_pairs",&pcb_hs_pairs);
    m.def("pcb_escape_lanes",[](const PcbCheckInput& in,const nb::dict& pop,const std::string& bytes){
        return result(check_escape_lanes(in.model(),pcb_escape_population_from_json(json_from_python(pop)),bytes));
    });
    m.def("pcb_return_stitch",[](const PcbCheckInput& in,const nb::dict& path,const std::map<std::string,std::tuple<int,std::string,std::string>>& raw,
            const std::string& interface_bytes,const std::string& pcb_source,const std::optional<std::string>& pcb_bytes,bool check_file){
        std::map<std::string,ReturnStitchClass> triage;
        for(const auto& [net,t]:raw)triage.emplace(net,ReturnStitchClass{std::get<0>(t),std::get<1>(t),std::get<2>(t)});
        PcbEmittedBoard emitted;emitted.source=pcb_source;emitted.exists=pcb_bytes.has_value();
        if(pcb_bytes)emitted.document=sexpr_loads(*pcb_bytes);
        return result(check_return_stitch(in,result<ReturnPathResult>(path),triage,interface_bytes,check_file?&emitted:nullptr));
    },nb::arg("input"),nb::arg("return_path"),nb::arg("triage"),nb::arg("interface_bytes"),
      nb::arg("pcb_source"),nb::arg("pcb_bytes").none(),nb::arg("check_file"));
    m.def("pcb_rail_ampacity",[](const nb::list& raw,const std::map<std::string,std::map<std::string,std::string>>& pins,
            const std::map<std::string,std::string>& resolved,const std::set<std::string>& isolated){
        std::vector<ProjectCircuit> sheets;
        for(auto item:raw){const auto pair=nb::cast<nb::tuple>(item);ProjectCircuit sc;sc.name=nb::cast<std::string>(pair[0]);
            for(auto [rail,values]:nb::cast<nb::dict>(pair[1]))
                for(const auto& [amps,note]:nb::cast<std::vector<std::pair<double,std::string>>>(values))
                    sc.circuit.loads.push_back({nb::cast<std::string>(rail),amps,note});
            sheets.push_back(std::move(sc));}
        SomInterface iface;for(const auto& [ref,rows]:pins){SomConnector c;for(const auto& p:rows)c.pins.push_back(p);iface.connectors.emplace_back(ref,std::move(c));}
        LinkMapping mapping;mapping.function_map=resolved;
        for(const auto& rail:isolated)mapping.isolated_som_rails.emplace(rail,"");
        return result(analyze_rail_ampacity(sheets,iface,mapping));
    });
    m.def("pcb_check_summary",[](const std::string& kind,const nb::dict& raw){
        if(kind=="connector-model")return result<ConnectorModelResult>(raw).summary();
        if(kind=="connector-spacing")return result<ConnectorSpacingResult>(raw).summary();
        if(kind=="placement-mech")return result<PlacementMechResult>(raw).summary();
        if(kind=="fanout")return result<PcbFanoutResult>(raw).summary();
        if(kind=="return-path")return result<ReturnPathResult>(raw).summary();
        if(kind=="escape-lanes")return result<EscapeLaneResult>(raw).summary();
        if(kind=="return-stitch")return result<ReturnStitchResult>(raw).summary();
        if(kind=="rail-ampacity")return result<RailAmpacityResult>(raw).report();
        throw nb::value_error("unknown PCB check summary");
    });
}
}
