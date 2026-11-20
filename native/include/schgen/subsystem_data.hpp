#pragma once

#include "schgen/subsystem_authoring.hpp"

#include <filesystem>

namespace schgen {

inline constexpr const char* subsystem_data_schema = "schgen.subsystem/1";
inline constexpr const char* subsystem_data_file = "subsystem.json";
inline constexpr const char* subsystem_library_folder = "subsystems";

SubsystemDefinition subsystem_data_definition(const JsonNode& document, const std::string& source);
std::vector<SubsystemDefinition> subsystem_data_definitions(const std::filesystem::path& library);
CircuitSheetIr extend_subsystem_data(CircuitSheetIr sheet, const JsonNode& additions, const AuthoringContext& context);
CircuitSheetIr author_subsystem_data(const JsonNode& document, const SubsystemMeta& meta,
                                     const AuthoringContext& context);

}
