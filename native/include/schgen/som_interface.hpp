#pragma once

#include "schgen/xdc.hpp"

#include <filesystem>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace schgen {

// Ordered dictionaries: replacing a duplicate key retains its first position,
// exactly as in the Python extractor. Pin numbers and net names stay verbatim.
struct SomConnector {
    // Missing XML elements are ""; present elements without text are nullopt.
    std::optional<std::string> value = std::string{};
    std::optional<std::string> footprint = std::string{};
    XdcStrings pins;
};

struct SomInterface {
    std::string source;
    std::vector<std::pair<std::string, SomConnector>> connectors;
};

struct SomZynq {
    std::string zynq_ref, source;
    std::optional<std::string> value = std::string{};
    XdcStrings pin_names, ball_net, jpin_net;
};

struct SomExtractOptions {
    // Executable name searched on PATH, or an explicit path. Never a shell command.
    std::string kicad_cli = "kicad-cli";
};

// Shared KiCad extraction boundary, also used by the schematic netlist gate.
// Duplicate net names replace their pins without moving the first occurrence.
// Missing attributes remain empty; node and net source order is preserved.
struct KicadNetlistPin { std::string ref, pin; };
using KicadNetlist = std::vector<std::pair<std::string, std::vector<KicadNetlistPin>>>;

// Uses the same shell-free argv, private RAII scratch directory, stderr capture
// and hardened libxml2 parser as the SoM extractors. Throws SomInterfaceError.
std::string export_kicad_netlist_xml(const std::filesystem::path& schematic,
                                    const SomExtractOptions& options = {});
KicadNetlist parse_kicad_netlist_xml(std::string_view xml,
                                    const std::string& source = "<memory>");

class SomInterfaceError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

// Live extraction always exports the supplied schematic with kicad-cli; no
// cached contract is substituted. These APIs currently use POSIX process I/O.
SomInterface extract_som_interface(
    const std::filesystem::path& som_sch, const std::vector<std::string>& refs,
    const SomExtractOptions& options = {});
SomZynq extract_som_zynq(
    const std::filesystem::path& som_sch, const std::string& zynq_ref = "U2",
    const std::vector<std::string>& jrefs = {"J1", "J2", "J3"},
    const SomExtractOptions& options = {});

// Pure extraction from KiCad XML, also useful for deterministic/offline tests.
// Semantic errors match Python; XML syntax errors include libxml2 diagnostics.
// DTDs are rejected; no external entities or network resources are loaded.
SomInterface parse_som_interface_xml(
    std::string_view xml, const std::string& source,
    const std::vector<std::string>& refs);
SomZynq parse_som_zynq_xml(
    std::string_view xml, const std::string& source,
    const std::string& zynq_ref = "U2",
    const std::vector<std::string>& jrefs = {"J1", "J2", "J3"});

// Contract JSON uses Python json.dumps(indent=1, sort_keys=True) bytes, including
// ASCII Unicode escapes and the final newline. Loading preserves file order.
SomInterface load_som_interface(const std::filesystem::path& path);
std::string som_interface_json(const SomInterface& data);
std::string som_zynq_json(const SomZynq& data);

// Equivalent to som_interface.cmd: strip comma-separated refs, extract, create
// output parents and atomically publish JSON. Return the exact console report.
std::string write_som_interface(
    const std::filesystem::path& som_sch, const std::string& comma_refs,
    const std::filesystem::path& output, const SomExtractOptions& options = {});

// Copies only live fields. Contract pins, requested refs, ports, mappings and
// bank/VCCO rail decisions remain the caller's responsibility. som_source is
// initially the supplied source string; callers may relativize it for display.
void apply_som_to_xdc(XdcInput& input, const SomZynq& live);

}  // namespace schgen
