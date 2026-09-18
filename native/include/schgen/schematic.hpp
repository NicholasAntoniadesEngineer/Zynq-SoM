#pragma once

#include "schgen/circuit.hpp"
#include "schgen/json.hpp"
#include "schgen/sexpr.hpp"
#include "schgen/symbols.hpp"

#include <cstdint>
#include <functional>
#include <map>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace schgen {

struct SchematicTextPosition {
    double x = 0.0, y = 0.0;
    int rotation = 0;
};
struct SchematicPlacedPart {
    std::string ref, lib_id, value;
    double x = 0.0, y = 0.0;
    int rotation = 0;
    std::string footprint;
    std::optional<SchematicTextPosition> ref_pos, val_pos;
};
struct SchematicPlacedPower {
    std::string lib_id, value, ref;
    double x = 0.0, y = 0.0;
    int rotation = 0;
    std::string net;
    std::optional<SchematicTextPosition> val_pos;
    bool show_value = false;
    const std::string& net_name() const { return net.empty() ? value : net; }
};
struct SchematicWire { double x0 = 0.0, y0 = 0.0, x1 = 0.0, y1 = 0.0; };
struct SchematicJunction { double x = 0.0, y = 0.0; };
struct SchematicHierLabel {
    std::string name;
    double x = 0.0, y = 0.0;
    int rotation = 0;
    std::string shape = "bidirectional";
};
struct SchematicLocalLabel {
    std::string name;
    double x = 0.0, y = 0.0;
    int rotation = 0;
};
struct SchematicNoConnect { double x = 0.0, y = 0.0; };
struct SchematicSheetPin {
    std::string name;
    double x = 0.0, y = 0.0;
    int rotation = 180;
    std::string shape = "bidirectional";
};
struct SchematicSheetSymbol {
    std::string name, file;
    double x = 0.0, y = 0.0, w = 0.0, h = 0.0;
    std::string uuid;
    std::vector<SchematicSheetPin> pins;
    std::string page = "2";
};
struct SchematicDesign {
    CircuitSheetIr circuit;
    std::vector<SchematicPlacedPart> parts;
    std::vector<SchematicPlacedPower> powers;
    std::vector<SchematicWire> wires;
    std::vector<SchematicJunction> junctions;
    std::vector<SchematicHierLabel> hlabels;
    std::vector<SchematicLocalLabel> llabels;
    std::vector<SchematicNoConnect> no_connects;
    std::vector<SchematicSheetSymbol> sheets;
    std::string paper = "A4";
    bool standalone = true;
};

struct SchematicOptions {
    // Empty means Python's None/empty-string fallback. An explicitly supplied
    // "/" instance path is preserved, although KiCad callers should use /UUID.
    std::string instance_path, project, sheet_uuid;
};
struct SchematicOutput {
    Sexpr document;
    std::string text;  // Complete sexpr_dumps(document) plus exactly one newline.
    std::string root_uuid, project, instance_path;
};

// UUIDv5(uuid5(NAMESPACE_DNS, "schgen.kicad-id"), slash-joined UTF-8 parts).
// Parts have already been stringified by the caller, as Python str(part).
std::string schematic_stable_uuid(const std::vector<std::string>& parts);

class SchematicIdFactory {
public:
    explicit SchematicIdFactory(std::string scope) : scope_(std::move(scope)) {}
    std::string operator()(const std::string& kind);
private:
    std::string scope_;
    std::map<std::string, std::uint64_t> counts_;
};

// Pure conversion of placement dataclass fields. A supplied typed circuit is
// retained in memory; this adapter never reloads it from a file. Missing optional
// fields have the Python dataclass defaults. Positions are [x, y, rotation]/null.
SchematicDesign schematic_design_from_json(const JsonNode& placement, CircuitSheetIr circuit);

// Symbol definitions are treated as immutable. Use e.g.
// [&library](const std::string& id) -> const SymbolDef& { return library.get(id); }.
// raw must be the resolved symbol block; pins retain Library.get traversal order.
using SchematicSymbolResolver = std::function<const SymbolDef&(const std::string&)>;
SchematicOutput emit_schematic(const SchematicDesign& design,
                               const SchematicSymbolResolver& symbols,
                               const SchematicOptions& options = {});
SchematicOutput emit_schematic(const SchematicDesign& design,
                               const std::vector<SymbolDef>& symbols,
                               const SchematicOptions& options = {});

}  // namespace schgen
