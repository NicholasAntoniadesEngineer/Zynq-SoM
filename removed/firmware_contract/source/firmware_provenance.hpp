#pragma once

#include "schgen/project.hpp"

namespace schgen {
// Repository source provenance for firmware/manual/SC/test-plan generation.
// Canonical JSON and the compiled authoring registry, never Python-file
// existence, establish the input inventory. Registered dependencies cannot
// disappear silently: missing/invalid JSON or missing builder source throws.
// Unregistered IR-only projects are explicitly identified as such.
// Reads files only; does not author circuits, execute source, write artifacts,
// import Python, or invoke a process. Returned paths describe actual canonical
// files (absolute if outside the repository), in deterministic dependency order.
std::vector<std::string> native_firmware_sources(const ProjectPaths& paths);

// The named hardware dependencies of the firmware/SC renderers and manual
// service descriptions. This preserves and extends the legacy curated source
// inventory; it is not an exhaustive manifest of every test-point/SPICE sheet.
// Exposed for test/CLI inventory; not inferred from Python filenames.
const std::vector<std::string>& firmware_provenance_dependencies();

// Native regeneration notices are deliberately project-explicit. PROJECT_DIR
// is a documented placeholder, never an implicit fallback to the carrier.
std::string firmware_native_regeneration_command(const std::string& command);
} // namespace schgen
