#include "schgen/module_symbols.hpp"

#include "schgen/json.hpp"

#include <stdexcept>

namespace schgen {
namespace {
const char* const part_record_file = "part.json";
}

SymbolLibrary project_symbol_library(const ProjectPaths& paths) {
    SymbolLibrary library(paths.repository_root);
    const ModuleDefinition& module = paths.module;
    if (module.mate_symbol.empty()) return library;
    const auto record = paths.parts_dir / module.connector_part / part_record_file;
    const auto part = parse_json_file(record.string());
    const auto* base = object_field(part, "lib_id");
    if (!base || base->kind != JsonKind::String || base->string_value.empty())
        throw std::runtime_error(record.string() + ": lib_id is required to build the module mate symbol");
    return library.with_definitions({renumbered_symbol(library.get(base->string_value), module.mate_symbol, module.mate_pad_names)});
}

}
