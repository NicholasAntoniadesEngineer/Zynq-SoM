#include "schgen/netlist_gate.hpp"

#include "schgen/occupancy.hpp"
#include "schgen/sexpr.hpp"
#include "schgen/symbols.hpp"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <fstream>
#include <iterator>
#include <map>
#include <set>
#include <utility>

namespace schgen {
namespace {
using Pin = std::pair<std::string, std::string>;
using Point = std::pair<double, double>;
using Declared = std::map<Pin, std::string>;

bool starts(const std::string& text, const std::string& prefix) { return text.rfind(prefix, 0) == 0; }
std::string pin_text(const Pin& pin) { return pin.first + "." + pin.second; }

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
    return out + quote;
}

template <typename Range>
std::string repr_list(const Range& items) {
    std::string out = "[";
    for (const auto& item : items) { if (out.size() > 1) out += ", "; out += repr(item); }
    return out + ']';
}

Declared declared_of(const CircuitSheetIr& circuit) {
    Declared out;
    for (const auto& net : circuit.nets)
        for (const auto& pin : net.pins) out[{pin.ref, pin.pin}] = net.name;
    return out;
}

// This is a dict, not a multimap. Retain first position and last value for
// duplicate net names even when the caller supplies records without XML.
ExtractedNetlist dictionary(const ExtractedNetlist& entries) {
    ExtractedNetlist out;
    std::map<std::string, std::size_t> indices;
    for (const auto& entry : entries) {
        const auto [it, inserted] = indices.emplace(entry.first, out.size());
        if (inserted) out.push_back(entry);
        else out[it->second].second = entry.second;
    }
    return out;
}

bool public_net(const CircuitNetIr& net) {
    return net.net_class == "power" || net.net_class == "ground" || net.net_class == "port";
}
std::string class_name(const CircuitNetIr& net) {
    return net.net_class == "power" ? "POWER" : net.net_class == "ground" ? "GROUND" : "PORT";
}

const SexprList& items(const Sexpr& node) {
    const auto* list = std::get_if<SexprList>(&node.v);
    if (!list) throw NetlistGateError("NC geometry: expected s-expression list");
    return *list;
}
std::string atom(const Sexpr& node) {
    if (const auto* value = std::get_if<std::string>(&node.v)) return *value;
    if (const auto* value = std::get_if<Sexpr::Sym>(&node.v)) return value->name;
    if (const auto* value = std::get_if<double>(&node.v)) {
        if (*value == std::trunc(*value)) return sexpr_fmt_num(*value);
        char buffer[128];
        const auto result = std::to_chars(buffer, buffer + sizeof(buffer), *value);
        if (result.ec == std::errc{}) return {buffer, result.ptr};
    }
    if (const auto* value = std::get_if<bool>(&node.v)) return *value ? "True" : "False";
    throw NetlistGateError("NC geometry: expected atom");
}
bool tagged(const Sexpr& node, const std::string& name) {
    const auto* list = std::get_if<SexprList>(&node.v);
    return list && !list->empty() && !std::holds_alternative<SexprList>((*list)[0].v) && atom((*list)[0]) == name;
}
const Sexpr* find(const Sexpr& node, const std::string& name) {
    for (const auto& sub : items(node)) if (tagged(sub, name)) return &sub;
    return nullptr;
}
const Sexpr& at(const Sexpr& node, std::size_t index) {
    const auto& list = items(node);
    if (index >= list.size()) throw NetlistGateError("NC geometry: missing coordinate or value");
    return list[index];
}
double number(const Sexpr& node) {
    double value;
    if (const auto* direct = std::get_if<double>(&node.v)) value = *direct == 0.0 ? 0.0 : *direct;
    else {
        const auto text = atom(node);
        std::size_t used = 0;
        value = std::stod(text, &used);
        if (used != text.size()) throw NetlistGateError("NC geometry: expected numeric coordinate");
    }
    if (!std::isfinite(value)) throw NetlistGateError("NC geometry: nonfinite coordinate or rotation");
    return value;
}
int rotation(const Sexpr& position) {
    if (items(position).size() < 4) return 0;
    // Python int(float(...)) % 360, without an out-of-range integer cast.
    const auto angle = static_cast<int>(std::fmod(std::trunc(number(at(position, 3))), 360.0));
    return angle < 0 ? angle + 360 : angle;
}
Point rounded(double x, double y) { return {py_round(x, 2), py_round(y, 2)}; }

std::string float_text(double value) {
    char buffer[512];
    const auto mag = std::fabs(value);
    const auto format = (mag == 0.0 || (mag >= 1e-4 && mag < 1e16))
        ? std::chars_format::fixed : std::chars_format::scientific;
    const auto converted = std::to_chars(buffer, buffer + sizeof(buffer), value, format);
    if (converted.ec != std::errc{}) throw NetlistGateError("NC geometry: cannot format coordinate");
    std::string out(buffer, converted.ptr);
    if (out.find_first_of(".e") == std::string::npos) out += ".0";
    return out;
}
std::string point_text(const Point& point) { return "(" + float_text(point.first) + ", " + float_text(point.second) + ")"; }

void walk_pins(const Sexpr& block, std::vector<SymbolPin>& pins) {
    for (const auto& sub : items(block)) if (tagged(sub, "symbol")) walk_pins(sub, pins);
    for (const auto& sub : items(block)) {
        if (!tagged(sub, "pin")) continue;
        SymbolPin pin;
        if (const auto* pos = find(sub, "at")) {
            pin.x = number(at(*pos, 1)); pin.y = number(at(*pos, 2)); pin.rotation = rotation(*pos);
        }
        if (const auto* num = find(sub, "number"); num && items(*num).size() > 1) pin.number = atom(at(*num, 1));
        pins.push_back(std::move(pin));
    }
}
}  // namespace

std::string NetlistGateResult::summary() const {
    if (ok) return "NETLIST GATE: PASS (extracted == declared)";
    std::string out = "NETLIST GATE: FAIL";
    for (const auto& [tag, messages] : std::vector<std::pair<std::string, const std::vector<std::string>*>>{
            {"SHORT", &shorts}, {"OPEN", &opens}, {"NC-CHEAT", &nc_cheats},
            {"PART", &part_mismatches}, {"NAME", &name_mismatches}})
        for (const auto& message : *messages) out += "\n  " + tag + ": " + message;
    return out;
}

ExtractedNetlist parse_netlist_xml(std::string_view xml, const std::string& source) {
    try { return parse_kicad_netlist_xml(xml, source); }
    catch (const std::exception& error) { throw NetlistGateError(error.what()); }
}
ExtractedNetlist extract_netlist(const std::filesystem::path& schematic, const NetlistExtractOptions& options) {
    try { return parse_netlist_xml(export_kicad_netlist_xml(schematic, options), schematic.string()); }
    catch (const std::exception& error) { throw NetlistGateError(error.what()); }
}
std::string normalize_netlist_name(std::string_view name) {
    const auto start = name.find_first_not_of('/');
    return start == std::string_view::npos ? std::string{} : std::string(name.substr(start));
}

std::vector<std::string> dead_two_terminal(const CircuitSheetIr& circuit) {
    std::map<std::string, std::set<std::string>> pins, nets;
    for (const auto& net : circuit.nets) for (const auto& pin : net.pins) {
        pins[pin.ref].insert(pin.pin); nets[pin.ref].insert(net.name);
    }
    std::vector<std::string> out;
    for (const auto& part : circuit.parts) {
        if (!(starts(part.lib_id, "Device:C") || starts(part.lib_id, "Device:R") || starts(part.lib_id, "Device:L"))) continue;
        if (pins[part.ref].size() >= 2 && nets[part.ref].size() == 1)
            out.push_back(part.ref + " (" + part.lib_id + "): both terminals on one net " + repr(*nets[part.ref].begin())
                          + " — electrically dead (capshort)");
    }
    return out;
}

std::vector<std::string> emitted_nc_cheats(const CircuitSheetIr& circuit, std::string_view text) {
    try {
        const auto doc = sexpr_loads(text);
        std::vector<Point> nc;
        for (const auto& sub : items(doc)) if (tagged(sub, "no_connect")) {
            const auto* pos = find(sub, "at");
            if (!pos) throw NetlistGateError("NC geometry: no_connect has no at");
            nc.push_back(rounded(number(at(*pos, 1)), number(at(*pos, 2))));
        }
        if (nc.empty()) return {};
        std::map<std::string, std::vector<SymbolPin>> lib_pins;
        if (const auto* library = find(doc, "lib_symbols"))
            for (const auto& block : items(*library)) if (tagged(block, "symbol")) {
                std::vector<SymbolPin> pins;
                walk_pins(block, pins);
                lib_pins[atom(at(block, 1))] = std::move(pins);
            }
        std::map<Point, std::vector<Pin>> pin_at;
        for (const auto& inst : items(doc)) {
            if (!tagged(inst, "symbol")) continue;
            const auto* lid = find(inst, "lib_id");
            const auto* pos = find(inst, "at");
            if (!lid || !pos) continue;
            const auto ax = number(at(*pos, 1)), ay = number(at(*pos, 2));
            const auto rot = rotation(*pos);
            std::string ref;
            for (const auto& prop : items(inst))
                if (tagged(prop, "property") && items(prop).size() > 2 && atom(at(prop, 1)) == "Reference") {
                    ref = atom(at(prop, 2)); break;
                }
            for (const auto& pin : lib_pins[atom(at(*lid, 1))]) {
                const auto [px, py] = pin_page_position(pin, ax, ay, rot);
                pin_at[rounded(px, py)].emplace_back(ref, pin.number);
            }
        }
        const auto declared = declared_of(circuit);
        std::vector<std::string> out;
        for (const auto& pos : nc) {
            const auto& pins = pin_at[pos];
            const auto netted = std::find_if(pins.begin(), pins.end(), [&](const auto& pin) { return declared.count(pin) != 0; });
            if (netted != pins.end()) out.push_back("no_connect at " + point_text(pos) + " sits on " + pin_text(*netted)
                + " which carries declared net " + repr(declared.at(*netted)) + " — NC is never a layout fallback (forbidden)");
            else if (pins.empty()) out.push_back("no_connect at " + point_text(pos) + " lands on no pin — stray marker");
        }
        return out;
    } catch (const NetlistGateError&) { throw; }
    catch (const std::exception& error) { throw NetlistGateError("NC geometry: " + std::string(error.what())); }
}

NetlistGateResult check_netlist(const CircuitSheetIr& circuit, const ExtractedNetlist& input, std::string_view text) {
    const auto extracted = dictionary(input);
    const auto declared = declared_of(circuit);
    Declared extracted_of;
    std::set<std::string> extracted_refs;
    for (const auto& [name, pins] : extracted) for (const auto& pin : pins) {
        if (starts(pin.ref, "#")) continue;
        extracted_of[{pin.ref, pin.pin}] = name;
        extracted_refs.insert(pin.ref);
    }
    NetlistGateResult out;
    for (const auto& [name, pins] : extracted) {
        std::set<std::string> merged;
        std::string members;
        for (const auto& pin : pins) {
            const Pin key{pin.ref, pin.pin};
            const auto it = declared.find(key);
            if (it == declared.end()) continue;
            merged.insert(it->second);
            if (!members.empty()) members += ", ";
            members += pin_text(key) + "=" + it->second;
        }
        if (merged.size() >= 2) out.shorts.push_back("extracted " + repr(name) + " merges " + repr_list(merged) + " [" + members + "]");
    }
    const auto dead = dead_two_terminal(circuit);
    out.shorts.insert(out.shorts.end(), dead.begin(), dead.end());
    for (const auto& net : circuit.nets) {
        std::set<std::string> ext_names, real;
        std::vector<std::string> stranded;
        for (const auto& pin : net.pins) {
            const auto it = extracted_of.find({pin.ref, pin.pin});
            if (it == extracted_of.end()) { stranded.push_back(pin_text({pin.ref, pin.pin})); continue; }
            ext_names.insert(it->second);
            if (starts(it->second, "unconnected-")) stranded.push_back(pin_text({pin.ref, pin.pin}));
            else if (!it->second.empty()) real.insert(it->second);
        }
        if (net.pins.size() >= 2 && (real.size() > 1 || !stranded.empty()))
            out.opens.push_back("declared " + repr(net.name) + ": extracted as " + repr_list(ext_names)
                + (stranded.empty() ? "" : ", stranded: " + repr_list(stranded)));
        if (public_net(net)) for (const auto& pin : net.pins) {
            const auto it = extracted_of.find({pin.ref, pin.pin});
            const auto name = it == extracted_of.end() ? "" : it->second;
            if (name.empty() || starts(name, "unconnected-"))
                out.opens.push_back(class_name(net) + " " + repr(net.name) + ": " + pin_text({pin.ref, pin.pin})
                                    + " emitted bare (" + repr(name) + ")");
        }
    }
    if (text.find("(no_connect") != std::string_view::npos) out.nc_cheats = emitted_nc_cheats(circuit, text);
    for (const auto& net : circuit.nets) if (public_net(net)) for (const auto& pin : net.pins) {
        const auto it = extracted_of.find({pin.ref, pin.pin});
        if (it != extracted_of.end() && !starts(it->second, "unconnected-") && normalize_netlist_name(it->second) != net.name)
            out.name_mismatches.push_back(pin_text({pin.ref, pin.pin}) + ": declared " + repr(net.name) + " but extracted " + repr(it->second)
                + (it->second.find("Net-(") != std::string::npos ? " [LOST-NAME rail: power symbol/label did not attach]" : ""));
    }
    std::set<std::string> nc_refs, netted_refs;
    for (const auto& pin : circuit.nc) nc_refs.insert(pin.ref);
    for (const auto& [pin, net] : declared) {
        (void)net;
        netted_refs.insert(pin.first);
    }
    for (const auto& part : circuit.parts) {
        // Only an NC-only part can legitimately have no extracted net entry.
        // A single NC pin must not exempt other, declared signal/rail pins.
        // Index once rather than rescanning every NC declaration for each part.
        const bool nc_only = nc_refs.count(part.ref) && !netted_refs.count(part.ref);
        if (!extracted_refs.count(part.ref) && !nc_only)
            out.part_mismatches.push_back(part.ref + ": missing from extracted netlist");
    }
    out.ok = out.shorts.empty() && out.opens.empty() && out.nc_cheats.empty() && out.part_mismatches.empty() && out.name_mismatches.empty();
    return out;
}

NetlistGateResult check_netlist(const CircuitSheetIr& circuit, const std::filesystem::path& schematic,
                               const NetlistExtractOptions& options) {
    const auto extracted = extract_netlist(schematic, options);
    std::ifstream in(schematic, std::ios::binary);
    if (!in) throw NetlistGateError("cannot read schematic: " + schematic.string());
    const std::string text{std::istreambuf_iterator<char>(in), {}};
    if (in.bad()) throw NetlistGateError("cannot read schematic: " + schematic.string());
    return check_netlist(circuit, extracted, text);
}
}  // namespace schgen
