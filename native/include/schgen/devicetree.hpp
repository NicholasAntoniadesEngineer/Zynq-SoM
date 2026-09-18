#pragma once

#include "schgen/som_interface.hpp"

#include <filesystem>
#include <stdexcept>
#include <string>
#include <vector>

namespace schgen {

struct DeviceTreeInput {
    SomInterface contract;
    SomZynq live;
    XdcStrings function_map;
    std::vector<std::string> refs = {"J1", "J2", "J3"};
    std::string contract_path, contract_source, som_source, mapping_source;
};

struct DeviceTreeMio {
    // Canonical decimal, not a machine integer: Python accepted arbitrary-size
    // indices. Real Zynq MIO indices are small; never silently narrow a bad one.
    std::string index, raw, function, jpin;
};

struct DeviceTreeSdio {
    std::string net, role, jpin;
};

struct DeviceTreeOutput {
    std::string text;
    std::vector<DeviceTreeMio> mio_rows;
    std::vector<DeviceTreeSdio> sdio_rows;
};

class DeviceTreeError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

// Reads project/som_mapping.json (schema schgen.som_mapping.v1) and the selected
// interface contract. pudc_straps overrides function_map exactly as dict.update.
// Uses link_mapping_from_json to validate all policy maps and protect boot straps.
// Reuses the caller's live extraction; never invokes KiCad or Python.
DeviceTreeInput load_devicetree_input(
    const std::filesystem::path& repository,
    const std::filesystem::path& project,
    const SomZynq& live,
    const std::filesystem::path& contract = {},
    const std::vector<std::string>& refs = {"J1", "J2", "J3"});

// Pure render + all Python SDIO completeness, PS/PL, MIO population and duplicate
// index gates. Includes the commented UART/SDIO templates verbatim. Intentional
// baseline deltas are only the generated-by/regenerate/renames source comments.
// Caller publishes text only on success and reports mio_rows.size().
DeviceTreeOutput generate_devicetree(const DeviceTreeInput& input);

}  // namespace schgen
