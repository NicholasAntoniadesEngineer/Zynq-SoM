#pragma once

#include "schgen/json.hpp"

#include <cstdint>
#include <cstddef>
#include <filesystem>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace schgen {

struct CircuitPinRefIr {
    std::string ref;
    std::string pin;
};

struct CircuitFieldIr {
    std::string key;
    std::string value;
};

struct CircuitPinNameIr {
    std::string name;
    std::vector<std::string> numbers;
};

struct CircuitPartIr {
    std::string ref;
    std::string lib_id;
    std::string value;
    std::string footprint;
    std::vector<CircuitFieldIr> fields;
    std::vector<CircuitPinNameIr> pin_names;
    std::vector<std::string> pin_numbers;
};

struct CircuitNetIr {
    std::string name;
    std::string net_class;
    std::vector<CircuitPinRefIr> pins;
};

struct CircuitPortIr {
    std::string net;
    std::string kind;
    std::string pair_with;
    bool has_pair_with = false;
    int32_t impedance = 0;
    bool has_impedance = false;
    std::string role;
    bool has_role = false;
    std::string bus;
    bool has_bus = false;
    int32_t speed_hz = 0;
    bool has_speed_hz = false;
    double level_v = 0.0;
    bool has_level_v = false;
    std::string expect;
    bool has_expect = false;
};

struct CircuitHintIr {
    std::string net;
    std::string style;
};

struct CircuitLoadIr {
    std::string rail;
    double amps = 0.0;
    std::string note;
};

struct CircuitWaiverIr {
    std::string kind;
    std::string key;
    std::string reason;
};

struct CircuitServiceIr {
    std::string part;
    std::string role;
    CircuitPinRefIr owner;
    std::string net;
    std::string target;
};

struct CircuitFreeIr {
    std::string part;
    std::string reason;
};

struct CircuitLayoutIr {
    std::vector<CircuitServiceIr> serves;
    std::vector<CircuitFreeIr> free;
};

struct CircuitSheetIr {
    std::string schema;
    std::string name;
    std::string title;
    std::vector<CircuitPartIr> parts;
    std::vector<CircuitNetIr> nets;
    std::vector<CircuitPinRefIr> nc;
    std::vector<CircuitPortIr> port_types;
    std::vector<CircuitHintIr> hints;
    std::vector<CircuitLoadIr> loads;
    std::vector<CircuitWaiverIr> waivers;
    CircuitLayoutIr layout;
};

inline constexpr std::size_t kTitleFieldGlyphs = 40, kTitleContinuationGlyphs = 55, kTitleRowLimit = 2;
inline constexpr unsigned char kUtf8LeadMask = 0xc0, kUtf8ContinuationTag = 0x80;
inline constexpr std::string_view kTitleBreak = " \xe2\x80\x94 ";
std::vector<std::string> title_block_rows(const std::string& title);
void require_title_fits(const std::string& sheet, const std::string& title);

const std::vector<std::string>& circuit_service_roles();
void validate_circuit_layout(const CircuitSheetIr& sheet);
JsonNode circuit_layout_json(const CircuitSheetIr& sheet);
CircuitLayoutIr parse_circuit_layout(const JsonNode& document, const CircuitSheetIr& sheet);
CircuitLayoutIr load_circuit_layout(const std::filesystem::path& path, const CircuitSheetIr& sheet);

struct LayoutIntentResult {
    bool ok = true;
    std::size_t support_parts = 0, served = 0, released = 0;
    std::vector<std::string> undeclared;
    std::string summary() const;
};
LayoutIntentResult check_layout_intent(const std::vector<CircuitSheetIr>& sheets);

// Authoritative canonical JSON loader, also used by catalog compilation.
// Preserves source ordering and validates expanded IR electrical invariants.
// Read-only: no catalog state, interpreter, or symbol-library dependency.
// Throws std::runtime_error with the source path on malformed input.
CircuitSheetIr load_circuit_json(const std::filesystem::path& path);

// Same parser and semantic validation for caller-owned in-memory records.
// Does not reload a file or consult a catalog; edits in root are authoritative.
CircuitSheetIr parse_circuit_ir(const JsonNode& root);

// Shape-checked transport of an intermediate in-memory sheet. Preserves page
// metadata whose differential mate may live on another page; does NOT assert
// electrical completeness. File/catalog/CLI ingestion must use parse_circuit_ir.
CircuitSheetIr decode_intermediate_circuit_ir(const JsonNode& root);

bool compile_circuit_catalog(const std::string& circuits_dir,
                             const std::string& catalog_path);
bool open_circuit_catalog(const std::string& catalog_path);
bool close_circuit_catalog();
CircuitSheetIr lookup_circuit_catalog(const std::string& name);
std::size_t circuit_catalog_count();

}  // namespace schgen
