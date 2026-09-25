#pragma once

#include "schgen/bringup_facts.hpp"
#include "schgen/power_checks.hpp"
#include "schgen/spice.hpp"
#include <tuple>

namespace schgen {

class FirmwareDocsError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

// All generation below is pure: caller-owned sheets, live U9 extraction, and
// provenance are authoritative. No cwd, environment, cache, Python, or writes.
struct FirmwareDocsInput {
    std::vector<ProjectCircuit> sheets;
    Stm32PinMap stm32;
    std::vector<std::string> firmware_sources;
};
// Explicit filesystem boundary; live extraction is never replaced by a cache.
FirmwareDocsInput load_firmware_docs_input(const ProjectPaths&,
    const SomExtractOptions& = {});
std::vector<std::string> firmware_sources(const ProjectPaths&);
std::vector<std::string> firmware_absent_inputs(const FirmwareDocsInput&);
std::vector<std::string> manual_missing_requirements(const FirmwareDocsInput&);
std::vector<std::string> scfw_missing_requirements(const FirmwareDocsInput&);

std::string render_firmware_contract(const FirmwareDocsInput&);
std::string render_bringup_manual(const FirmwareDocsInput&);
// Probe values are already-formatted coverage locations (net -> comma joined
// locations). Analysis owners provide checks/probes; this layer only joins them.
std::string render_test_plan(const FirmwareDocsInput&, const SpiceResult&,
    const ProjectStrings& probes);
// Ordered scan rows: address, reference, description, optional AUX-domain flag.
// Missing/invalid optional device sections retain the renderer's skip behavior.
using TestplanI2cDevice = std::tuple<int, std::string, std::string, bool>;
std::vector<TestplanI2cDevice> testplan_i2c_devices(const std::vector<ProjectCircuit>&);
struct FirmwareDocArtifact { std::string path, text; };
std::vector<FirmwareDocArtifact> render_scfw(const FirmwareDocsInput&);

struct PowerSequenceRow {
    std::string vout, vin;
    std::optional<double> volts;
    double load = 0, limit = 0;
    std::string kind, ref, sheet;
    std::optional<std::string> enable;
};
struct PowerSequence {
    std::vector<std::string> stage0;
    std::vector<PowerSequenceRow> chain, modules;
};
PowerSequence build_power_sequence(const std::vector<ProjectCircuit>&,
    const PowerCheckResult&, const PowerPolicy& = default_power_policy());
std::string render_power_sequence_svg(const PowerSequence&, bool ok = true,
    const PowerPolicy& = default_power_policy());

} // namespace schgen
