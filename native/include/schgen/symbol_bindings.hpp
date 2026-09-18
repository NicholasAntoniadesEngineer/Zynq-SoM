#pragma once

// Transitional Python transport only. Loading, lookup, parsing, inheritance,
// synthesis, geometry and source caches all live in symbols.cpp.
#include "schgen/symbols.hpp"
#include <cstdint>
#include <nanobind/nanobind.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/set.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>

namespace schgen {

inline SymbolPin symbol_pin_from_python(nanobind::handle value) {
    namespace nb = nanobind;
    SymbolPin pin;
    pin.number = nb::cast<std::string>(value.attr("number"));
    pin.name = nb::cast<std::string>(value.attr("name"));
    pin.etype = nb::cast<std::string>(value.attr("etype"));
    pin.x = nb::cast<double>(value.attr("x"));
    pin.y = nb::cast<double>(value.attr("y"));
    pin.rotation = nb::cast<int>(value.attr("rotation"));
    pin.length = nb::cast<double>(value.attr("length"));
    pin.hidden = nb::cast<bool>(value.attr("hidden"));
    return pin;
}

template <typename ToTagged>
nanobind::object symbol_def_to_python(const SymbolDef& symbol,
        nanobind::handle pin_type, nanobind::handle symbol_type,
        nanobind::handle from_tagged, const ToTagged& to_tagged) {
    namespace nb = nanobind;
    nb::list pins;
    for (const auto& pin : symbol.pins) {
        pins.append(pin_type(pin.number, pin.name, pin.etype, pin.x, pin.y,
                             pin.rotation, pin.length, pin.hidden));
    }
    return symbol_type(symbol.lib_id, from_tagged(to_tagged(symbol.raw)), pins,
        nb::make_tuple(symbol.body[0], symbol.body[1], symbol.body[2], symbol.body[3]),
        symbol.pin_names_hidden, symbol.pin_numbers_hidden);
}

namespace symbol_binding_detail {
// Retain transport objects here (not in the Python adapter) to preserve the
// old Library.get() identity and mutable dataclass/raw-tree API. The domain
// cache remains SymbolLibrary's immutable native definition/file snapshots.
// Methods keep the GIL: one Library and its Python object cache are serialized.
class Library {
public:
    Library(const std::vector<std::string>& paths, nanobind::object pin_type,
            nanobind::object symbol_type, nanobind::object from_tagged)
        : native_(native_paths(paths)), pin_type_(std::move(pin_type)),
          symbol_type_(std::move(symbol_type)), from_tagged_(std::move(from_tagged)) {}

    template <typename ToTagged>
    nanobind::object get(const std::string& id, const ToTagged& to_tagged) {
        namespace nb = nanobind;
        const nb::str key(id.c_str());
        if (definitions_.contains(key)) return nb::borrow<nb::object>(definitions_[key]);
        auto result = symbol_def_to_python(native_.get(id), pin_type_, symbol_type_,
                                           from_tagged_, to_tagged);
        definitions_[key] = result;
        return result;
    }

    template <typename ToTagged>
    std::set<std::string> pin_numbers(const std::string& id, const ToTagged& to_tagged) {
        // The transitional public SymbolDef is mutable. Match the old API when
        // a caller intentionally edits its pin list after get(), without adding
        // a competing Python implementation of discovery or metadata parsing.
        std::set<std::string> numbers;
        for (nanobind::handle pin : get(id, to_tagged).attr("pins"))
            numbers.insert(nanobind::cast<std::string>(pin.attr("number")));
        return numbers;
    }
    void clear() { definitions_.clear(); native_.clear(); }

    void deepcopy_metadata(nanobind::handle deepcopy, const nanobind::dict& memo) {
        definitions_ = nanobind::cast<nanobind::dict>(deepcopy(definitions_, memo));
    }

private:
    static std::vector<std::filesystem::path> native_paths(const std::vector<std::string>& paths) {
        return {paths.begin(), paths.end()};
    }
    SymbolLibrary native_;
    nanobind::object pin_type_, symbol_type_, from_tagged_;
    nanobind::dict definitions_;
};
}  // namespace symbol_binding_detail

// module.cpp owns its anonymous conversion helpers; pass them without exporting
// them or duplicating the s-expression representation here:
//   #include "schgen/symbol_bindings.hpp"
//   schgen::bind_symbols(m, sexpr_from_py, sexpr_to_tagged);
template <typename FromPython, typename ToTagged>
void bind_symbols(nanobind::module_& m, FromPython from_python, ToTagged to_tagged) {
    namespace nb = nanobind;
    using Library = symbol_binding_detail::Library;
    nb::exception<SymbolError>(m, "SymbolError", PyExc_ValueError);
    nb::class_<Library>(m, "SymbolLibrary")
        .def(nb::init<const std::vector<std::string>&, nb::object, nb::object, nb::object>(),
             nb::arg("paths"), nb::arg("pin_type"), nb::arg("symbol_type"), nb::arg("from_tagged"))
        .def("get", [to_tagged](Library& self, const std::string& id) {
            return self.get(id, to_tagged);
        }, nb::arg("lib_id"))
        .def("pin_numbers", [to_tagged](Library& self, const std::string& id) {
            return self.pin_numbers(id, to_tagged);
        }, nb::arg("lib_id"))
        .def("__copy__", [](const Library& self) {
            return nb::cast(new Library(self), nb::rv_policy::take_ownership);
        })
        .def("__deepcopy__", [](Library& self, const nb::dict& memo) {
            const auto original = nb::cast(&self, nb::rv_policy::reference);
            const nb::int_ key(reinterpret_cast<std::uintptr_t>(original.ptr()));
            if (memo.contains(key)) return nb::borrow<nb::object>(memo[key]);
            // Copy native definitions and retain immutable loaded-file snapshots;
            // never reload disk or reconstruct an empty Library. Register before
            // descending into mutable metadata so graph aliases/cycles survive.
            auto result = nb::cast(new Library(self), nb::rv_policy::take_ownership);
            memo[key] = result;
            nb::cast<Library&>(result).deepcopy_metadata(
                nb::module_::import_("copy").attr("deepcopy"), memo);
            return result;
        }, nb::arg("memo"))
        .def("clear", &Library::clear);
    m.def("symbols_clear_file_cache", &clear_symbol_file_cache);
    m.def("symbols_on_grid", &symbol_on_grid, nb::arg("value"));
    m.def("symbols_parse", [from_python, to_tagged](const std::string& id, nb::handle raw,
            nb::handle pin_type, nb::handle symbol_type, nb::handle from_tagged) {
        return symbol_def_to_python(parse_symbol(id, from_python(raw)), pin_type,
                                    symbol_type, from_tagged, to_tagged);
    }, nb::arg("lib_id"), nb::arg("raw"), nb::arg("pin_type"), nb::arg("symbol_type"),
       nb::arg("from_tagged"));
    // A distinct name avoids shadowing module.cpp's older scalar kernel. This
    // overload uses the complete Pin transport and Python's expression grouping.
    m.def("symbols_pin_page_position", [](nb::handle pin, double x, double y, int rotation) {
        return pin_page_position(symbol_pin_from_python(pin), x, y, rotation);
    }, nb::arg("pin"), nb::arg("anchor_x"), nb::arg("anchor_y"), nb::arg("rotation"));
}

}  // namespace schgen
