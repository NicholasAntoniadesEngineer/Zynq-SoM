#pragma once
#include "schgen/project.hpp"

namespace schgen {
struct PairSignalSpec {
    std::string interface, signal, net_p, net_n;
    int z_diff_ohm = 0;
    double match_tol_mil = 0.0, intra_pair_skew_mil = 0.0;
    bool ac_coupled = false;
    std::string spec_cite, notes;
    double match_tol_mm() const;
    double intra_pair_skew_mm() const;
};
std::vector<PairSignalSpec> parse_signal_specs(const JsonNode&);
std::vector<PairSignalSpec> load_signal_specs(const std::filesystem::path&);
struct DifferentialGeometry {
    int impedance = 0;
    double width_mm = 0.0, gap_mm = 0.0;
    std::string source;
};
const DifferentialGeometry* differential_geometry(int impedance);
std::string port_net_class(const CircuitPortIr&);
bool needs_signal_specs(const std::vector<ProjectCircuit>&);
struct LayoutConstraints {
    std::string dru, csv;
    std::size_t port_count = 0;
};
// Pure ordered-data generation. A typed differential pair must have its own
// researched target; there is no per-kind/default-skew fallback.
LayoutConstraints generate_layout_constraints(const std::vector<ProjectCircuit>&,
    const std::vector<PairSignalSpec>&, const std::string& specification_source);
LayoutConstraints write_layout_constraints(const std::vector<ProjectCircuit>&,
    const std::filesystem::path& specification, const std::filesystem::path& output_directory);
}  // namespace schgen
