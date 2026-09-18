#pragma once

// Transitional interpreter boundary. In module.cpp, after its existing
// sexpr_from_py converter is in scope:
//   schgen::bind_schematic(m, sexpr_from_py);
// The converter is injected; no second S-expression parser or SymbolLibrary
// wrapper is needed. The supplied Python Library.get retains its search paths.
#include "schgen/json_bindings.hpp"
#include "schgen/schematic.hpp"

#include <nanobind/nanobind.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>

#include <map>
#include <optional>
#include <string>
#include <utility>

namespace schgen {

// Circuit.to_ir() transport. Emission historically reads only name/title and
// part properties: it also supports empty circuits and intermediate placement
// states. Electrical validation remains at the existing caller/gate boundary.
inline CircuitSheetIr schematic_circuit_from_python(const nanobind::dict& raw) {
    namespace nb = nanobind;
    CircuitSheetIr circuit;
    circuit.name = nb::cast<std::string>(raw["name"]);
    circuit.title = nb::cast<std::string>(raw["title"]);
    for (const auto row : nb::cast<nb::list>(raw["parts"])) {
        const auto part = nb::cast<nb::dict>(row);
        CircuitPartIr item;
        item.ref = nb::cast<std::string>(part["ref"]);
        item.footprint = nb::cast<std::string>(part["footprint"]);
        for (auto [key, value] : nb::cast<nb::dict>(part["fields"]))
            item.fields.push_back({nb::cast<std::string>(key), nb::cast<std::string>(value)});
        circuit.parts.push_back(std::move(item));
    }
    return circuit;
}

template<class FromPython>
void bind_schematic(nanobind::module_& m, FromPython from_python) {
    namespace nb = nanobind;
    m.def("schematic_stable_uuid", &schematic_stable_uuid, nb::arg("parts"),
          nb::call_guard<nb::gil_scoped_release>());
    nb::class_<SchematicIdFactory>(m, "SchematicIdFactory")
        .def(nb::init<std::string>(), nb::arg("scope"))
        .def("__call__", &SchematicIdFactory::operator(), nb::arg("kind"));

    m.def("emit_schematic", [from_python](const nb::dict& raw_circuit,
            const nb::dict& raw_placement, const nb::object& get_symbol,
            const std::optional<std::string>& instance_path,
            const std::optional<std::string>& project,
            const std::optional<std::string>& sheet_uuid) {
        if (!PyCallable_Check(get_symbol.ptr()))
            throw nb::type_error("emit_schematic: get_symbol must be callable");
        const auto design = schematic_design_from_json(json_from_python(raw_placement),
                                                       schematic_circuit_from_python(raw_circuit));
        const SchematicOptions options{instance_path.value_or(""), project.value_or(""),
                                       sheet_uuid.value_or("")};
        // Cache complete native copies for this call only. First lookup order is
        // controlled by the core's sorted library IDs; instance/pin order stays
        // exactly as provided. Only native copies are accessed without the GIL.
        std::map<std::string, SymbolDef> definitions;
        const auto resolve = [&](const std::string& id) -> const SymbolDef& {
            const auto found = definitions.find(id);
            if (found != definitions.end()) return found->second;
            nb::gil_scoped_acquire acquire;
            const nb::object source = get_symbol(nb::cast(id));
            SymbolDef definition;
            definition.lib_id = id;
            definition.raw = from_python(source.attr("raw"));
            for (const auto pin : nb::cast<nb::iterable>(source.attr("pins"))) {
                SymbolPin metadata;
                metadata.number = nb::cast<std::string>(pin.attr("number"));
                definition.pins.push_back(std::move(metadata));
            }
            return definitions.emplace(id, std::move(definition)).first->second;
        };
        SchematicOutput output;
        {
            nb::gil_scoped_release release;
            output = emit_schematic(design, resolve, options);
        }
        return output.text;
    }, nb::arg("circuit"), nb::arg("placement"), nb::arg("get_symbol"),
       nb::arg("instance_path") = nb::none(), nb::arg("project") = nb::none(),
       nb::arg("sheet_uuid") = nb::none());
}

}  // namespace schgen
