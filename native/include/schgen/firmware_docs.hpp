#pragma once

#include "schgen/bringup_facts.hpp"
#include "schgen/power_checks.hpp"

namespace schgen {

class FirmwareDocsError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

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
    const PowerCheckResult&, const PowerPolicy&);
std::string render_power_sequence_svg(const PowerSequence&, bool ok,
    const PowerPolicy&);

} // namespace schgen
