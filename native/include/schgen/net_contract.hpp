#pragma once

#include "schgen/project.hpp"
#include "schgen/som_interface.hpp"

namespace schgen {
class NetContractError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

struct NetContractInput {
    // Caller-owned authored IR is authoritative; rendering never reloads it.
    std::vector<CircuitSheetIr> circuits;
    SomInterface som;
};
struct NetContractEntry { std::string name, identifier; };
struct NetContractDocument {
    // Original names, deduplicated/sorted independently in the two domains.
    std::vector<NetContractEntry> som, rails;
    std::string header;
};

// Read live canonical authored IR + selected som_interface.json, using the
// existing native loaders. No Python, constructor execution, or generated-net
// inventory. Explicit caller IR may instead be passed directly to the renderer.
NetContractInput load_net_contract_input(const ProjectPaths& paths);

// Preserve legacy ASCII '+' -> 'P', '-' / punctuation -> '_' identifiers when
// safe in C++. Empty names use net_empty. Reserved/keyword/non-ASCII identifiers
// use net_x + lowercase hex of ALL original bytes. Names themselves never change.
// Distinct names mapping to one identifier are rejected per domain by generate.
std::string net_contract_identifier(const std::string& name);

// C++17 header: namespace NAME { namespace SOM/RAILS { inline constexpr
// std::string_view ...; } inline constexpr std::array som_names/rail_names; }
// Namespace may have validated ::-separated components; never std/reserved.
// Literal bytes (including embedded NUL and UTF-8) use explicit lengths and
// safe escaping. Input/namespace/collision failures throw before publication.
NetContractDocument generate_net_contract_header(const NetContractInput& input,
    const std::string& name_space = "schgen_nets");

// Explicit publication only, no default project output and no inventory edits.
// Output must name a .h/.hh/.hpp/.hxx file; symlink/non-file targets are refused.
// Render completely before an atomic replacement, reusing the native writer.
NetContractDocument write_net_contract_header(const NetContractInput& input,
    const std::filesystem::path& output, const std::string& name_space = "schgen_nets");
} // namespace schgen
