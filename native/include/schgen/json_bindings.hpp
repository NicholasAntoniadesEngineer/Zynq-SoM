#pragma once

// Temporary interpreter boundary. Domain logic and validation use JsonNode and
// remain in the independently buildable C++ core.
#include "schgen/json.hpp"
#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>
#include <cmath>

namespace schgen {
inline JsonNode json_from_python(nanobind::handle value, unsigned depth = 0) {
    namespace nb = nanobind;
    if (depth > 128) throw nb::value_error("JSON input nesting exceeds 128 levels");
    JsonNode out;
    if (value.is_none()) return out;
    if (nb::isinstance<nb::bool_>(value)) {
        out.kind = JsonKind::Bool; out.bool_value = nb::cast<bool>(value);
    } else if (nb::isinstance<nb::str>(value)) {
        out.kind = JsonKind::String; out.string_value = nb::cast<std::string>(value);
    } else if (nb::isinstance<nb::int_>(value) || nb::isinstance<nb::float_>(value)) {
        out.kind = JsonKind::Number; out.number_value = nb::cast<double>(value);
        if (!std::isfinite(out.number_value)) throw nb::value_error("non-finite JSON number");
        if (nb::isinstance<nb::int_>(value)) {
            nb::object roundtrip = nb::steal<nb::object>(PyLong_FromDouble(out.number_value));
            if (!roundtrip.is_valid()) throw nb::python_error();
            const int equal = PyObject_RichCompareBool(value.ptr(), roundtrip.ptr(), Py_EQ);
            if (equal < 0) throw nb::python_error();
            if (!equal) throw nb::value_error("JSON integer loses precision in native numeric representation");
        }
    } else if (nb::isinstance<nb::dict>(value)) {
        out.kind = JsonKind::Object;
        for (auto [key, item] : nb::borrow<nb::dict>(value)) {
            if (!nb::isinstance<nb::str>(key)) throw nb::type_error("JSON object keys must be strings");
            out.object_value.emplace_back(nb::cast<std::string>(key), json_from_python(item, depth + 1));
        }
    } else if (nb::isinstance<nb::list>(value) || nb::isinstance<nb::tuple>(value)) {
        out.kind = JsonKind::Array;
        for (auto item : nb::borrow<nb::iterable>(value)) out.array_value.push_back(json_from_python(item, depth + 1));
    } else throw nb::type_error("unsupported JSON value type");
    return out;
}
inline nanobind::object json_to_python(const JsonNode& value) {
    namespace nb = nanobind;
    switch (value.kind) {
    case JsonKind::Null: return nb::none();
    case JsonKind::Bool: return nb::bool_(value.bool_value);
    case JsonKind::Number:
        if (std::isfinite(value.number_value) && std::trunc(value.number_value) == value.number_value)
            return nb::steal<nb::object>(PyLong_FromDouble(value.number_value));
        return nb::float_(value.number_value);
    case JsonKind::String: return nb::cast(value.string_value);
    case JsonKind::Array: {
        nb::list out;
        for (const auto& item : value.array_value) out.append(json_to_python(item));
        return out;
    }
    case JsonKind::Object: {
        nb::dict out;
        for (const auto& [key, item] : value.object_value) out[nb::cast(key)] = json_to_python(item);
        return out;
    }
    }
    throw nb::value_error("invalid native JSON kind");
}
}
