#pragma once
#include "schgen/pcb_emit.hpp"
#include "schgen/pcb_checks_bindings.hpp"

namespace schgen {
inline void bind_pcb_emission(nanobind::module_& m) {
    namespace nb = nanobind;
    nb::class_<PcbModel>(m, "PcbEmissionModel");
    m.def("pcb_emission_prepare", [](const nb::dict& raw,
            const std::map<std::string, std::string>& files) {
        PcbFootprintPool pool;
        for (const auto& [path, bytes] : files) pool.emplace(path, pcb_check_footprint(path, bytes));
        return pcb_model_from_json(json_from_python(raw), pool);
    });
    m.def("pcb_emission_write", [](const PcbModel& model, const std::string& path,
            const std::string& kind, const nb::dict& policy) {
        auto p = default_pcb_emit_policy();
        using model_binding::get;
        p.header_descriptions = get<ProjectStrings>(policy, "header_descriptions");
        p.switch_descriptions = get<ProjectStrings>(policy, "switch_descriptions");
        p.connector_descriptions = get<ProjectStrings>(policy, "connector_descriptions");
        p.connector_mating_faces = get<ProjectStrings>(policy, "connector_mating_faces");
        p.footprint_aliases = get<ProjectStrings>(policy, "footprint_aliases");
        p.isolation_prefixes = get<std::vector<std::string>>(policy, "isolation_prefixes");
        p.ground_layer = get<std::string>(policy, "ground_layer");
        p.power_class = get<std::string>(policy, "power_class");
#define PCB_NUMBER(name) p.name = get<double>(policy, #name)
        PCB_NUMBER(gnd_plane_edge_back); PCB_NUMBER(gnd_plane_clearance);
        PCB_NUMBER(pour_clearance); PCB_NUMBER(zone_min_thickness); PCB_NUMBER(isolation_margin);
        PCB_NUMBER(thermal_via_size); PCB_NUMBER(thermal_via_drill); PCB_NUMBER(thermal_via_clear);
        PCB_NUMBER(hole_samenet_pad); PCB_NUMBER(thermal_via_h2h); PCB_NUMBER(thermal_via_edge);
        PCB_NUMBER(thermal_via_spacing); PCB_NUMBER(thermal_lattice_pitch);
        PCB_NUMBER(default_track); PCB_NUMBER(default_clearance); PCB_NUMBER(power_track);
        PCB_NUMBER(power_clearance); PCB_NUMBER(minimum_hole_to_hole); PCB_NUMBER(stack_thickness);
#undef PCB_NUMBER
        p.thermal_copper.clear();
        p.thermal_credit_needs.clear();
        for (auto raw : get<nb::list>(policy, "thermal_credit_needs")) {
            const auto v = nb::cast<nb::dict>(raw);
            p.thermal_credit_needs.push_back({get<std::string>(v, "value_prefix"),
                get<int>(v, "min_vias"), get<double>(v, "radius_mm"),
                get<std::vector<std::string>>(v, "pour_layers")});
        }
        for (auto [key, value] : get<nb::dict>(policy, "thermal_copper")) {
            const auto v = nb::cast<nb::dict>(value);
            PcbThermalCopperSpec spec;
            spec.via_sites = get<std::vector<std::pair<double,double>>>(v, "via_sites");
            spec.max_vias = get<std::size_t>(v, "max_vias");
            const auto pour = pcb_check_binding::box(v["pour"]);
            if (!pour) throw std::invalid_argument("thermal pour geometry is required");
            spec.pour = *pour;
            spec.pour_layers = get<std::vector<std::string>>(v, "pour_layers");
            spec.cite = get<std::string>(v, "cite");
            p.thermal_copper.emplace_back(nb::cast<std::string>(key), std::move(spec));
        }
        std::vector<std::string> diagnostics, fallbacks;
        {
            nb::gil_scoped_release release;
            if (kind == "pcb") {
                const auto result = write_pcb(model, path, p);
                diagnostics = result.diagnostics; fallbacks = result.fallback_events;
            } else if (kind == "project") write_pcb_project(model, path, p);
            else if (kind == "rules") write_pcb_design_rules(model, path, p);
            else throw std::invalid_argument("unknown PCB emission kind: " + kind);
        }
        return nb::make_tuple(diagnostics, fallbacks);
    });
}
}
