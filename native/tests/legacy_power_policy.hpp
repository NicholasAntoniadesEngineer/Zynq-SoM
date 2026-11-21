#pragma once

#include "schgen/board_power.hpp"

#include <filesystem>
#include <stdexcept>
#include <string>

namespace schgen {

inline PowerPolicy legacy_power_policy(const std::filesystem::path& root) {
    const auto file = root / "native/tests/data/power/legacy_policy.json";
    const auto document = parse_json_file(file.string());
    reject_unknown_keys(document, {"schema", "basis", "power", "regulated_rails", "module_sheets"}, file.string());
    const auto* power = object_field(document, "power");
    const auto* regulated = object_field(document, "regulated_rails");
    const auto* sheets = object_field(document, "module_sheets");
    if (!power || !regulated || !sheets) throw std::runtime_error(file.string() + ": power, regulated_rails or module_sheets is missing");
    ModuleDefinition module;
    for (const auto& rail : object_field(*regulated, "rails")->array_value) module.regulated_rails.push_back(rail.string_value);
    module.regulated_rails_basis = object_field(*regulated, "basis")->string_value;
    auto policy = explicit_power_policy(parse_board_power(*power, file.string()), module);
    for (const auto& sheet : sheets->array_value) policy.module_sheets.push_back(sheet.string_value);
    return policy;
}

}
