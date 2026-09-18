#pragma once

#include "schgen/circuit.hpp"
#include "schgen/json.hpp"

#include <cstddef>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace schgen {

using LinkSomNets = std::map<std::string, std::vector<std::string>>;
using LinkStringMap = std::map<std::string, std::string>;

// Project-local policy. Map directions match som_mapping.json: SoM -> carrier
// for function_map, pudc_straps, vcco_rail_map and rebound_som_rails;
// isolated_som_rails maps carrier rail -> reason. No carrier policy is implicit.
struct LinkMapping {
    LinkStringMap function_map;
    LinkStringMap pudc_straps;
    LinkStringMap vcco_rail_map;
    LinkStringMap rebound_som_rails;
    LinkStringMap isolated_som_rails;
    std::set<std::string> do_not_load_straps;
    LinkStringMap rail_aliases;  // Optional spelling aliases: carrier -> SoM.
};

// Python used hash-ordered sets in two diagnostics. Defaults are deterministic;
// a transitional adapter can supply those iteration orders for byte parity.
// Hints affect presentation only: omitted/duplicate/foreign members never
// remove a check, pair member, or missing-role warning.
struct LinkPairOrder {
    std::size_t sheet_index = 0;
    std::string net;
    std::vector<std::string> members;
};
struct LinkDiagnosticOrder {
    std::vector<LinkPairOrder> pairs;
    std::vector<std::string> missing_i2c_roles;
};

struct LinkPortBinding {
    std::string sheet;
    std::string net;
    CircuitPortIr ptype;
    std::vector<std::string> targets;
    std::string status = "bound";
};

struct LinkResult {
    std::vector<CircuitSheetIr> sheets;
    std::vector<LinkPortBinding> bindings;
    std::vector<std::string> rail_bindings;
    std::vector<std::string> errors;
    std::vector<std::string> warnings;
    std::vector<std::string> unbound_som;
    std::vector<std::string> deferred;
    LinkMapping mapping;

    bool ok() const { return errors.empty(); }
    std::string report() const;
};

// Pure adapters: callers own file loading. The contract has connectors.*.pins;
// mapping requires all six policy fields (empty maps/array are explicit policy).
LinkSomNets link_som_nets_from_json(const JsonNode& contract);
LinkMapping link_mapping_from_json(const JsonNode& mapping);
JsonNode link_result_json(const LinkResult& result);

// As with Python link(), circuit semantic/pin validation belongs to the loader
// and command boundary. Preserve supplied sheet/net/port-type order here.
LinkResult link_sheets(const std::vector<CircuitSheetIr>& sheets,
                       const LinkSomNets& som_nets, const LinkMapping& mapping,
                       const LinkDiagnosticOrder& order = {});
LinkResult link_sheets(const std::vector<CircuitSheetIr>& sheets,
                       const JsonNode& contract, const JsonNode& mapping,
                       const LinkDiagnosticOrder& order = {});

std::vector<std::string> link_drift_candidates(
    const std::string& name, const std::set<std::string>& pool);

}  // namespace schgen
