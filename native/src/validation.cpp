#include "schgen/validation.hpp"

#include "schgen/pack.hpp"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <locale>
#include <map>
#include <set>
#include <sstream>
#include <utility>

namespace schgen {
namespace {

using PinKey = std::pair<std::string, std::string>;

std::string repr(const std::string& value) {
    const char quote = value.find('\'') != std::string::npos && value.find('"') == std::string::npos ? '"' : '\'';
    std::string out(1, quote);
    constexpr char hex[] = "0123456789abcdef";
    for (const unsigned char ch : value) {
        if (ch == static_cast<unsigned char>(quote) || ch == '\\') { out += '\\'; out += static_cast<char>(ch); }
        else if (ch == '\n') out += "\\n";
        else if (ch == '\r') out += "\\r";
        else if (ch == '\t') out += "\\t";
        else if (ch < 32 || ch == 127) { out += "\\x"; out += hex[ch >> 4]; out += hex[ch & 15]; }
        else out += static_cast<char>(ch);
    }
    out += quote;
    return out;
}

std::string pin_text(const CircuitPinRefIr& pin) { return pin.ref + "." + pin.pin; }

struct ResolvedPart {
    std::string ref, lib_id;
    std::map<std::string, std::string> etypes;
};

struct ResolvedCircuit {
    std::vector<ResolvedPart> parts;
    std::map<std::string, std::size_t> by_ref;
};

ResolvedCircuit resolve(const CircuitSheetIr& circuit, SymbolLibrary& library) {
    ResolvedCircuit out;
    for (const auto& part : circuit.parts) {
        const std::string where = "circuit " + repr(circuit.name) + " " + part.ref + " (" + part.lib_id + ")";
        if (part.ref.empty() || !out.by_ref.emplace(part.ref, out.parts.size()).second) {
            throw ValidationError(where + ": empty or duplicate part reference");
        }
        ResolvedPart resolved{part.ref, part.lib_id, {}};
        try {
            // Include hidden pins and all units/styles. If several symbol pins
            // share a number, Python's etype_of dict uses the last traversal
            // record's type; retain that behavior exactly.
            for (const auto& pin : library.get(part.lib_id).pins) {
                if (pin.number.empty()) throw ValidationError("symbol has an empty pin number");
                resolved.etypes[pin.number] = pin.etype;
            }
        } catch (const std::exception& error) {
            throw ValidationError(where + ": " + error.what());
        }
        out.parts.push_back(std::move(resolved));
    }
    return out;
}

ElectricalValidationResult completeness(const CircuitSheetIr& circuit, const ResolvedCircuit& resolved) {
    ElectricalValidationResult out;
    out.circuit = circuit.name;
    auto& errors = out.completeness_errors;
    std::map<PinKey, std::string> assigned;
    std::set<PinKey> nc;
    const auto check_pin = [&](const CircuitPinRefIr& pin) {
        const auto found = resolved.by_ref.find(pin.ref);
        if (found == resolved.by_ref.end()) {
            errors.push_back(pin_text(pin) + ": unknown part " + repr(pin.ref));
            return;
        }
        if (!resolved.parts[found->second].etypes.count(pin.pin)) {
            errors.push_back(pin_text(pin) + ": pin does not exist on " + pin.ref);
        }
    };
    std::set<std::string> net_names;
    for (const auto& net : circuit.nets) {
        if (net.name.empty() || !net_names.insert(net.name).second) {
            errors.push_back("empty or duplicate net " + repr(net.name));
        }
        if (net.net_class != "signal" && net.net_class != "power"
            && net.net_class != "ground" && net.net_class != "port") {
            errors.push_back("net " + repr(net.name) + ": unknown net_class " + repr(net.net_class));
        }
        if (net.net_class == "signal" && net.pins.size() < 2) {
            errors.push_back("net " + repr(net.name) + ": single-pin internal signal net");
        }
        for (const auto& pin : net.pins) {
            check_pin(pin);
            const auto entry = assigned.emplace(PinKey{pin.ref, pin.pin}, net.name);
            if (!entry.second && entry.first->second != net.name) {
                errors.push_back(pin_text(pin) + " already on net " + repr(entry.first->second)
                    + ", cannot also join " + repr(net.name));
            }
        }
    }
    for (const auto& pin : circuit.nc) {
        check_pin(pin);
        const PinKey key{pin.ref, pin.pin};
        nc.insert(key);
        if (assigned.count(key)) errors.push_back(pin_text(pin) + " carries a net, cannot be NC");
    }
    for (const auto& part : resolved.parts) {
        PartPinCoverage coverage;
        coverage.ref = part.ref;
        coverage.lib_id = part.lib_id;
        for (const auto& item : part.etypes) {
            const auto& pin = item.first;
            const PinKey key{part.ref, pin};
            coverage.symbol_pins.push_back(pin);
            if (assigned.count(key)) coverage.assigned_pins.push_back(pin);
            else if (nc.count(key)) coverage.nc_pins.push_back(pin);
            else {
                coverage.unassigned_pins.push_back(pin);
                errors.push_back(part.ref + "." + pin + ": UNASSIGNED (net it or declare nc())");
            }
        }
        out.coverage.push_back(std::move(coverage));
    }
    return out;
}

std::vector<std::string> inputs_driven(const CircuitSheetIr& circuit, const ResolvedCircuit& resolved) {
    static const std::set<std::string> drivers = {
        "output", "bidirectional", "tri_state", "passive", "power_out", "open_collector", "open_emitter"};
    std::vector<std::string> errors;
    for (const auto& net : circuit.nets) {
        if (net.net_class == "power" || net.net_class == "ground" || net.net_class == "port") continue;
        bool input = false, driven = false;
        for (const auto& pin : net.pins) {
            const auto part = resolved.by_ref.find(pin.ref);
            if (part == resolved.by_ref.end()) continue;  // Python etype_of.get(..., "?").
            const auto& etypes = resolved.parts[part->second].etypes;
            const auto type = etypes.find(pin.pin);
            if (type == etypes.end()) continue;
            input = input || type->second == "input";
            driven = driven || drivers.count(type->second) != 0;
        }
        if (input && !driven) {
            errors.push_back("net " + repr(net.name) + ": input pin(s) with no same-sheet driver "
                             "and not a PORT — undriven input");
        }
    }
    return errors;
}

bool is_text(const std::string& kind) {
    return kind == "pin_name" || kind == "pin_number" || kind == "reference"
           || kind == "value" || kind == "label";
}

void finite(double value, const std::string& where) {
    if (!std::isfinite(value)) throw ValidationError(where + ": coordinate must be finite");
}

void valid_box(const VisualBox& box, const std::string& where) {
    finite(box.x0, where); finite(box.y0, where); finite(box.x1, where); finite(box.y1, where);
    if (box.x0 > box.x1 || box.y0 > box.y1) throw ValidationError(where + ": inverted box bounds");
    if (box.kind.empty() || box.owner.empty()) {
        throw ValidationError(where + ": box kind and owner must not be empty");
    }
}

void valid_geometry(const SheetGeometry& geo, double clearance) {
    if (!std::isfinite(clearance) || clearance < 0) {
        throw ValidationError("visual clearance must be finite and nonnegative");
    }
    for (std::size_t i = 0; i < geo.boxes.size(); ++i) valid_box(geo.boxes[i], "visual boxes[" + std::to_string(i) + "]");
    for (std::size_t i = 0; i < geo.wires.size(); ++i) {
        const auto& wire = geo.wires[i];
        const std::string where = "visual wires[" + std::to_string(i) + "] (" + wire.net + ")";
        finite(wire.x0, where); finite(wire.y0, where); finite(wire.x1, where); finite(wire.y1, where);
        if (!wire.horizontal() && !wire.vertical()) throw ValidationError(where + ": segment is not orthogonal");
        if (wire.horizontal() && wire.vertical()) throw ValidationError(where + ": zero-length segment");
        if (wire.net.empty()) throw ValidationError(where + ": net must not be empty");
    }
    for (std::size_t i = 0; i < geo.junctions.size(); ++i) {
        const std::string where = "visual junctions[" + std::to_string(i) + "]";
        finite(geo.junctions[i].x, where); finite(geo.junctions[i].y, where);
    }
}

std::string point(double x, double y) {
    std::ostringstream out;
    out.imbue(std::locale::classic());
    out << std::fixed << std::setprecision(2) << '(' << x << ',' << y << ')';
    return out.str();
}

VisualBox segment_box(const VisualSegment& s) {
    constexpr double half = 0.127;
    return {std::min(s.x0, s.x1) - half, std::min(s.y0, s.y1) - half,
            std::max(s.x0, s.x1) + half, std::max(s.y0, s.y1) + half, "wire", "net:" + s.net};
}

}  // namespace

std::string ElectricalValidationResult::completeness_summary() const {
    if (completeness_errors.empty()) return "circuit " + repr(circuit) + " complete";
    std::string out = "circuit " + repr(circuit) + " incomplete:";
    for (const auto& error : completeness_errors) out += "\n  " + error;
    return out;
}

std::string ElectricalValidationResult::summary() const {
    std::string out = completeness_summary();
    for (const auto& error : input_driver_errors) out += "\n  " + error;
    return out;
}

ElectricalValidationResult check_circuit_electrical(const CircuitSheetIr& circuit, SymbolLibrary& library) {
    const auto resolved = resolve(circuit, library);
    auto out = completeness(circuit, resolved);
    out.input_driver_errors = inputs_driven(circuit, resolved);
    return out;
}

std::vector<std::string> check_circuit_completeness(const CircuitSheetIr& circuit, SymbolLibrary& library) {
    return completeness(circuit, resolve(circuit, library)).completeness_errors;
}

void validate_circuit(const CircuitSheetIr& circuit, SymbolLibrary& library) {
    const auto result = completeness(circuit, resolve(circuit, library));
    if (!result.completeness_errors.empty()) throw ValidationError(result.completeness_summary());
}

std::vector<std::string> check_inputs_driven(const CircuitSheetIr& circuit, SymbolLibrary& library) {
    return inputs_driven(circuit, resolve(circuit, library));
}

bool VisualBox::intersects(const VisualBox& other, double pad) const {
    valid_box(*this, "visual box"); valid_box(other, "visual other box");
    if (!std::isfinite(pad)) throw ValidationError("visual box pad must be finite");
    return boxes_overlap(bounds(), other.bounds(), pad);
}

bool VisualSegment::horizontal() const { return std::abs(y0 - y1) < 1e-6; }
bool VisualSegment::vertical() const { return std::abs(x0 - x1) < 1e-6; }

std::string VisualResult::summary() const {
    if (ok) return "VISUAL GATE: PASS (0 overlaps, 0 crossings)";
    std::string out = "VISUAL GATE: FAIL";
    for (const auto& finding : findings) out += "\n  " + finding;
    return out;
}

VisualResult check_visual_geometry(const SheetGeometry& geo, double clearance_mm) {
    valid_geometry(geo, clearance_mm);
    VisualResult out;
    const auto finding = [&](std::string message) {
        out.ok = false;
        out.findings.push_back(std::move(message));
    };
    for (std::size_t i = 0; i < geo.boxes.size(); ++i) {
        for (std::size_t j = i + 1; j < geo.boxes.size(); ++j) {
            const auto& a = geo.boxes[i];
            const auto& b = geo.boxes[j];
            if (a.owner == b.owner && !(is_text(a.kind) && is_text(b.kind))) continue;
            if (a.intersects(b, clearance_mm)) finding(a.kind + "(" + a.owner + ") overlaps " + b.kind + "(" + b.owner + ")");
        }
    }
    for (const auto& wire : geo.wires) {
        const auto wb = segment_box(wire);
        for (const auto& box : geo.boxes) {
            if (box.kind == "body" && box.owner.find("net:") != std::string::npos) continue;
            const double pad = box.kind == "label" && box.owner == "label:" + wire.net ? -0.14 : 0.0;
            if (is_text(box.kind) && wb.intersects(box, pad)) finding("wire(" + wire.net + ") over " + box.kind + "(" + box.owner + ")");
        }
    }
    for (std::size_t i = 0; i < geo.wires.size(); ++i) {
        for (std::size_t j = i + 1; j < geo.wires.size(); ++j) {
            const auto& a = geo.wires[i];
            const auto& b = geo.wires[j];
            if (visual_hv_cross(a.x0, a.y0, a.x1, a.y1, b.x0, b.y0, b.x1, b.y1)) {
                finding("wires CROSS: " + a.net + " x " + b.net + " @" + point(a.x0, a.y0) + "-" + point(b.x0, b.y0));
            }
            if (collinear_overlap(a.x0, a.y0, a.x1, a.y1, b.x0, b.y0, b.x1, b.y1)) {
                finding(std::string(a.net == b.net ? "same-net wire-over-wire" : "collinear overlap") + ": " + a.net + " ~ " + b.net);
            }
            const auto touch = foreign_t_touch(a.x0, a.y0, a.x1, a.y1, b.x0, b.y0, b.x1, b.y1, a.net == b.net);
            if (touch) finding("different-net T-touch: " + a.net + " endpoint on " + b.net + " @" + point(touch->first, touch->second));
        }
    }
    for (const auto& junction : geo.junctions) {
        std::set<std::string> nets;
        for (const auto& wire : geo.wires) {
            if (point_on_seg(junction.x, junction.y, wire.x0, wire.y0, wire.x1, wire.y1, false)) nets.insert(wire.net);
        }
        if (nets.size() > 1) {
            std::string names = "[";
            for (const auto& net : nets) { if (names.size() > 1) names += ", "; names += repr(net); }
            names += ']';
            finding("cross-net junction @" + point(junction.x, junction.y) + ": " + names);
        }
    }
    return out;
}

}  // namespace schgen
