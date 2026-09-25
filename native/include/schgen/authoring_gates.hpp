#pragma once
#include "schgen/subsystem_authoring.hpp"

namespace schgen {
// Factories are explicit frontend declarations, not inferred from source text
// or from the existence of a cached JSON file. Missing factories fail closed.
// A caller may supply a live native extension/plugin factory; the gate neither
// imports nor executes Python. A throwing factory is reported as a build error.
struct SubsystemPackageFactory {
    std::string name;
    std::vector<std::string> interface;
    std::function<CircuitSheetIr(const SubsystemMeta&)> circuit_meta;
    std::function<CircuitSheetIr()> circuit;
};
struct CarrierPackageFactory {
    std::string name;
    std::function<CircuitSheetIr()> circuit;
    std::optional<JsonNode> meta;
};
std::vector<SubsystemPackageFactory> native_subsystem_factories(const AuthoringContext& context = {});
CarrierPackageFactory native_subsystem_adapter(const std::string& name, const JsonNode& meta,
                                               const AuthoringContext& context = {});

struct SubsystemPackageReport {
    std::string name;
    std::filesystem::path path;
    std::vector<std::string> missing;
    bool has_circuit = false, accepts_meta = false;
    std::vector<std::string> declared_interface, interface_drift, errors;
    bool ok() const;
};
struct SubsystemStructureResult {
    std::vector<SubsystemPackageReport> packages;
    bool ok() const;
    std::size_t n_ok() const;
    std::string summary() const;
    int exit_code(bool strict = false) const { return strict && !ok() ? 1 : 0; }
};
struct CarrierPackageReport {
    std::string name;
    std::filesystem::path path;
    bool adapter = false;
    std::vector<std::string> missing;
    bool has_circuit = false, has_meta = false;
    std::vector<std::string> errors;
    bool ok() const;
    std::string kind() const { return adapter ? "adapter" : "local"; }
};
struct CarrierStructureResult {
    std::vector<CarrierPackageReport> packages;
    bool ok() const;
    std::size_t n_ok() const;
    std::size_t n_adapters() const;
    std::size_t n_locals() const;
    std::string summary() const;
    int exit_code() const { return ok() ? 0 : 1; }
};

// Preserve the repository's retained-authoring package-shape contract (.py,
// README/test/.cir companions). No source is evaluated. Native callable and
// metadata declarations come from the supplied registry. In particular, never
// register a companion circuit.json loader as its own adapter factory: the gate
// compares that companion against an independently authored circuit.
std::vector<std::string> subsystem_required_files(const std::string& name);
std::vector<std::string> carrier_required_files(const std::string& name, bool adapter);
SubsystemPackageReport check_subsystem_package(const std::string& name,
    const std::filesystem::path& library, const SubsystemPackageFactory* factory);
SubsystemStructureResult check_subsystem_structure(const std::filesystem::path& library,
    const std::vector<SubsystemPackageFactory>& factories);
CarrierPackageReport check_carrier_package(const std::string& name,
    const std::filesystem::path& base, const std::filesystem::path& library,
    const CarrierPackageFactory* factory);
CarrierStructureResult check_carrier_structure(const std::filesystem::path& base,
    const std::filesystem::path& library, const std::vector<CarrierPackageFactory>& factories);
// Exact Python summaries have no final newline; publication adds one, atomically.
void write_authoring_gate_report(const std::filesystem::path& path, const std::string& summary);
JsonNode subsystem_structure_json(const SubsystemStructureResult& result);
JsonNode carrier_structure_json(const CarrierStructureResult& result);
} // namespace schgen
