#pragma once

#include "schgen/json_bindings.hpp"
#include "schgen/schematic_place.hpp"
#include "schgen/symbol_bindings.hpp"
#include "schgen/selftest.hpp"
#include <nanobind/stl/tuple.h>

namespace schgen {
namespace schematic_place_binding_detail {
inline nanobind::object text_position(const std::optional<SchematicTextPosition>& p) {
    return p ? nanobind::object(nanobind::make_tuple(p->x, p->y, p->rotation)) : nanobind::none();
}
inline nanobind::dict placement(const SchematicPlacement& p) {
    namespace nb = nanobind;
    nb::dict out;
    nb::list parts, powers, hlabels, llabels, nc, boxes;
    for (const auto& a : p.parts)
        parts.append(nb::make_tuple(a.ref, a.lib_id, a.value, a.x, a.y, a.rotation,
                                    a.footprint, text_position(a.ref_pos), text_position(a.val_pos)));
    for (const auto& a : p.powers)
        powers.append(nb::make_tuple(a.lib_id, a.value, a.ref, a.x, a.y, a.rotation,
                                     a.net, text_position(a.val_pos), a.show_value));
    for (const auto& a : p.hlabels) hlabels.append(nb::make_tuple(a.name, a.x, a.y, a.rotation, a.shape));
    for (const auto& a : p.llabels) llabels.append(nb::make_tuple(a.name, a.x, a.y, a.rotation));
    for (const auto& a : p.no_connects) nc.append(nb::make_tuple(a.x, a.y));
    for (const auto& a : p.boxes) boxes.append(nb::make_tuple(a.x0, a.y0, a.x1, a.y1, a.kind, a.owner));
    nb::dict plans;
    for (const auto& [net, paths] : p.plans) plans[nb::cast(net)] = nb::cast(paths);
    out["parts"] = parts; out["powers"] = powers;
    out["hlabels"] = hlabels; out["llabels"] = llabels;
    out["no_connects"] = nc; out["boxes"] = boxes;
    out["plans"] = plans; out["label_bridged"] = nb::cast(p.label_bridged);
    out["paper"] = nb::cast(p.paper);
    return out;
}
inline nanobind::tuple page(const SchematicPlacedPage& page) {
    namespace nb = nanobind;
    nb::list segments, junctions, refs;
    for (const auto& s : page.routed.segs) segments.append(nb::make_tuple(s.x0, s.y0, s.x1, s.y1, s.net));
    for (const auto& p : page.routed.junctions) junctions.append(nb::make_tuple(p.x, p.y));
    for (const auto& p : page.circuit.parts) refs.append(nb::cast(p.ref));
    return nb::make_tuple(page.circuit.name, refs, placement(page.placement), segments, junctions);
}
}

template <class FromPython>
void bind_schematic_place(nanobind::module_& m, FromPython from_python) {
    namespace nb = nanobind;
    nb::exception<SchematicPlaceError>(m, "SchematicPlaceError", PyExc_ValueError);
    m.def("schematic_partition", [from_python](const nb::dict& raw,
            const symbol_binding_detail::Library& source_library) {
        const auto circuit = decode_intermediate_circuit_ir(json_from_python(raw));
        auto library = source_library.snapshot(from_python);
        std::vector<CircuitSheetIr> pages;
        {
            nb::gil_scoped_release release;
            pages = partition_schematic_pages(circuit, library);
        }
        nb::list out;
        for (const auto& page : pages) {
            nb::list refs;
            for (const auto& part : page.parts) refs.append(nb::cast(part.ref));
            out.append(nb::make_tuple(page.name, refs));
        }
        return out;
    });
    m.def("schematic_mutation_proof", [from_python](const nb::dict& raw,
            const symbol_binding_detail::Library& source_library, bool clamp) {
        const auto circuit = decode_intermediate_circuit_ir(json_from_python(raw));
        auto library = source_library.snapshot(from_python);
        PlacerMutationProof proof;
        {
            nb::gil_scoped_release release;
            proof = clamp ? selftest_clamp_thresh_strict(circuit, library)
                          : selftest_rail_decoup_dropped(circuit, library);
        }
        return nb::make_tuple(proof.baseline_ok, proof.mutation_killed, proof.diagnostic);
    });
    m.def("schematic_place", [from_python](const nb::dict& raw,
            const symbol_binding_detail::Library& source_library,
            const std::vector<double>& spacing, int attempts, int mode) {
        if (spacing.size() != 9) throw nb::value_error("placement requires nine spacing values");
        if (mode < 0 || mode > 2) throw nb::value_error("invalid placement mode");
        const auto circuit = decode_intermediate_circuit_ir(json_from_python(raw));
        auto library = source_library.snapshot(from_python);
        const SchematicSpacing sp{spacing[0], spacing[1], spacing[2], spacing[3], spacing[4],
                                  spacing[5], spacing[6], spacing[7], spacing[8]};
        std::vector<SchematicPlacedPage> pages;
        {
            nb::gil_scoped_release release;
            if (mode == 0) pages.push_back({circuit, build_schematic_placement(circuit, library, sp), {}, {}});
            else if (mode == 1) pages.push_back(place_and_route_schematic(circuit, library, sp, attempts));
            else pages = paginate_and_route_schematic(circuit, library, sp, attempts);
        }
        nb::list out;
        for (const auto& p : pages) out.append(schematic_place_binding_detail::page(p));
        return out;
    }, nb::arg("circuit"), nb::arg("library"), nb::arg("spacing"),
       nb::arg("max_attempts") = 8, nb::arg("mode") = 2);
}
}
