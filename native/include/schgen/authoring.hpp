#pragma once

#include "schgen/catalog.hpp"
#include "schgen/circuit_helpers.hpp"
#include <functional>
#include <map>
#include <optional>
#include <set>

namespace schgen {
using AuthoringStrings = std::vector<std::pair<std::string, std::string>>;
struct AuthoringContext {
    // Caller owns catalog/library lifetime. No interpreter, subprocess, or JSON
    // circuit fallback. An absent symbol resolver means unresolved inline symbols.
    std::function<CatalogPart(const std::string&)> part = lookup_part_catalog;
    std::function<std::optional<std::set<std::string>>(const std::string&)> pins;
};
AuthoringContext make_authoring_context(const std::filesystem::path& repository);
struct AuthoringPort {
    std::string kind = "single";
    std::optional<std::string> pair_with, role, bus, expect;
    std::optional<int32_t> impedance, speed_hz;
    std::optional<double> level_v;
};
struct AuthoringPartSelection {
    std::optional<std::string> ref, value, lcsc, lib_id, footprint;
};

class CircuitAuthor {
public:
    explicit CircuitAuthor(std::string name, std::string title = {}, AuthoringContext context = {});
    explicit CircuitAuthor(CircuitSheetIr circuit, AuthoringContext context = {});
    const CircuitSheetIr& view() const { return circuit_; }
    CircuitSheetIr finish() const;
    std::string auto_ref(const std::string& prefix);
    static std::string classify(const std::string& name);
    std::string part(const std::string& ref, const std::string& lib_id,
                     const std::string& value, const std::string& footprint = {},
                     const AuthoringStrings& fields = {});
    std::string use_part(const std::string& mpn, const AuthoringPartSelection& selection = {});
    void field(const std::string& ref, const std::string& key, const std::string& value);
    void net(const std::string& name, const std::vector<std::string>& pins = {},
             const std::optional<std::string>& net_class = std::nullopt);
    void port(const std::string& name, const std::vector<std::string>& pins = {},
              const AuthoringPort& type = {}, bool explicit_type = false);
    void port_type(const std::string& net, const AuthoringPort& type = {});
    CircuitPortIr port_type_of(const std::string& net) const;
    void nc(const std::vector<std::string>& pins);
    void bind(const AuthoringStrings& mapping);
    void hint(const std::string& net, const std::string& style);
    void draws(const std::string& rail, double amps, const std::string& note = {});
    void waive(const std::string& kind, const std::string& key, const std::string& reason);
    std::string testpoint(const std::string& net, const std::optional<std::string>& ref = std::nullopt);
    std::string mounting_hole(const std::string& net = "CHASSIS_GND",
                             const std::optional<std::string>& ref = std::nullopt);
    std::vector<std::string> decouple(const std::string& pin, const std::vector<std::string>& values,
        const std::optional<std::string>& rail = std::nullopt, const std::string& gnd = "GND",
        const std::string& lib_id = "Device:C", const std::string& footprint = {});
    std::string pullup(const std::string& pin, const std::string& value, const std::string& rail,
        const std::string& lib_id = "Device:R", const std::string& footprint = {});
    std::string series(const std::string& in, const std::string& out, const std::string& value,
        const std::string& prefix = "R", const std::string& lib_id = "Device:R",
        const std::string& footprint = {});
    std::vector<CircuitPinRefIr> expand_pin(const std::string& pin) const;
    std::optional<std::string> net_of(const CircuitPinRefIr& pin) const;
    // Page snapshots can retain a differential mate on another page. This is
    // an intermediate IR, so a subsequent full-circuit finish() is not implied.
    CircuitSheetIr subset(const std::set<std::string>& refs, int page) const;
    void validate(const std::vector<std::pair<std::string, std::vector<std::string>>>& pins) const;
private:
    CircuitSheetIr circuit_;
    AuthoringContext context_;
    std::map<std::string, std::size_t> counters_;
    const CircuitNetIr* find_net(const std::string&) const;
    CircuitPartIr& find_part(const std::string&);
    CircuitPinRefIr single_pin(const std::string&) const;
};

class SubsystemMeta {
public:
    explicit SubsystemMeta(const JsonNode& value = {});
    std::string bus(const std::string& role, const std::string& fallback) const;
    std::string note(const std::string& key, const std::string& fallback) const;
    std::optional<std::string> expect(const std::string& port,
        std::optional<std::string> fallback = std::nullopt) const;
    // expect_kw ignores empty/null values; direct expects.get preserves them.
    std::optional<std::string> expect_kw(const std::string& port) const;
    CircuitSheetIr finish(CircuitAuthor& circuit) const;
    const AuthoringStrings& bindings() const { return bind_; }
private:
    AuthoringStrings bind_, buses_, notes_;
    std::vector<std::pair<std::string, std::optional<std::string>>> expects_;
};

// Canonical Circuit.to_ir transport, including explicit null metadata, lexical
// pin-number/NC sorting, insertion order and every waiver. No file I/O.
JsonNode authored_circuit_json(const CircuitSheetIr& circuit);
bool authoring_json_equal(const JsonNode& a, const JsonNode& b);
} // namespace schgen
