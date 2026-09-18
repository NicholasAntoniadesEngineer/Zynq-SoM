#include "schgen/xdc.hpp"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <limits>
#include <map>
#include <regex>
#include <set>
#include <sstream>

namespace schgen {
namespace {
using Strings = std::vector<std::string>;
using Map = std::map<std::string, std::string>;

std::string join(const Strings& items, const std::string& sep) {
    std::string out;
    for (std::size_t i = 0; i < items.size(); ++i) {
        if (i) out += sep;
        out += items[i];
    }
    return out;
}

// Match Python repr for the ASCII names used in KiCad diagnostics, including
// quotes and control characters, rather than interpolating unsafe raw names.
std::string repr(const std::string& s) {
    const char quote = s.find('\'') != std::string::npos &&
                       s.find('"') == std::string::npos ? '"' : '\'';
    std::string out(1, quote);
    const char* hex = "0123456789abcdef";
    for (unsigned char c : s) {
        if (c == quote || c == '\\') { out += '\\'; out += c; }
        else if (c == '\n') out += "\\n";
        else if (c == '\r') out += "\\r";
        else if (c == '\t') out += "\\t";
        else if (c < 32 || c == 127) {
            out += "\\x"; out += hex[c >> 4]; out += hex[c & 15];
        } else out += c;
    }
    return out + quote;
}

std::string list_repr(Strings items) {
    std::sort(items.begin(), items.end());
    for (auto& item : items) item = repr(item);
    return "[" + join(items, ", ") + "]";
}

bool pair_kind(const std::string& kind) {
    return kind == "diff_pair" || kind == "usb_hs_pair" || kind == "tmds_pair";
}
std::string clock(const XdcPin& pin) {
    return xdc_pin_traits(pin.pin_name).first;
}
bool p_side(const XdcPin& pin) {
    return xdc_pin_traits(pin.pin_name).second;
}
bool power_or_ground(const std::string& net) {
    static const std::regex pattern(
        "^(GND|GNDA|GNDD|GNDPWR|AGND|DGND|PGND|VSS|CHASSIS_GND|\\+|VDD|VCC)|^VBUS$");
    return std::regex_search(net, pattern);
}
Map as_map(const XdcStrings& pairs) { return Map(pairs.begin(), pairs.end()); }

struct PinNumber {
    bool negative;
    std::string digits;
};

PinNumber pin_number(const std::string& pin) {
    // Decimal KiCad pin IDs need numeric (not lexical) ordering. Do not narrow
    // them to machine integers: Python int() did not overflow at 64 bits.
    const auto first = pin.find_first_not_of(" \t\n\r\f\v");
    const auto last = pin.find_last_not_of(" \t\n\r\f\v");
    std::size_t i = first;
    bool negative = false;
    if (i != std::string::npos && (pin[i] == '+' || pin[i] == '-')) {
        negative = pin[i] == '-';
        ++i;
    }
    std::string digits;
    bool previous_digit = false;
    for (; i != std::string::npos && i <= last; ++i) {
        const char c = pin[i];
        if (c >= '0' && c <= '9') { digits += c; previous_digit = true; }
        else if (c == '_' && previous_digit) previous_digit = false;
        else break;
    }
    if (digits.empty() || !previous_digit || i <= last)
        throw XdcError("invalid literal for int() with base 10: " + repr(pin));
    const auto nonzero = digits.find_first_not_of('0');
    if (nonzero == std::string::npos) return {false, "0"};
    return {negative, digits.substr(nonzero)};
}

XdcStrings sorted_pins(const XdcStrings& pins) {
    struct Numbered { std::pair<std::string, std::string> pin; PinNumber number; };
    std::vector<Numbered> ordered;
    ordered.reserve(pins.size());
    for (const auto& pin : pins) ordered.push_back({pin, pin_number(pin.first)});
    std::stable_sort(ordered.begin(), ordered.end(), [](const auto& a, const auto& b) {
        if (a.number.negative != b.number.negative) return a.number.negative;
        const auto& x = a.number.digits;
        const auto& y = b.number.digits;
        if (x == y) return false;
        const bool less = x.size() == y.size() ? x < y : x.size() < y.size();
        return a.number.negative ? !less : less;
    });
    XdcStrings result;
    result.reserve(pins.size());
    for (auto& item : ordered) result.push_back(std::move(item.pin));
    return result;
}

std::string float_repr(double value) {
    if (std::isinf(value)) return "inf";
    // Shortest round-tripping digits, with Python's fixed/scientific cutoff
    // and its .0 for integral floats. Neither printf %g nor setprecision(16)
    // preserves diagnostics for all binary64 voltage values.
    char buffer[64];
    const auto converted = std::to_chars(buffer, buffer + sizeof(buffer), value,
                                         std::chars_format::scientific);
    if (converted.ec != std::errc{}) throw XdcError("cannot format rail voltage");
    std::string scientific(buffer, converted.ptr);
    const auto e = scientific.find('e');
    const int exponent = std::stoi(scientific.substr(e + 1));
    if (exponent < -4 || exponent >= 16) return scientific;
    std::string digits = scientific.substr(0, e);
    const auto dot = digits.find('.');
    if (dot != std::string::npos) digits.erase(dot, 1);
    const int point = exponent + 1;
    if (point <= 0) return "0." + std::string(-point, '0') + digits;
    if (point >= static_cast<int>(digits.size()))
        return digits + std::string(point - digits.size(), '0') + ".0";
    digits.insert(static_cast<std::size_t>(point), ".");
    return digits;
}

std::string render(const XdcOutput& result, const XdcInput& in, const Map& rails) {
    std::set<std::string> banks;
    std::size_t clocks = 0;
    for (const auto& e : result.entries) {
        banks.insert(e.bank);
        clocks += !clock(e).empty();
    }
    Strings rail_desc;
    for (const auto& b : banks) rail_desc.push_back("bank " + b + " = " + rails.at(b));
    Strings lines = {
        std::string(78, '#'),
        "# Zynq_Carrier_pins.xdc — GENERATED by `schgen xdc`. DO NOT EDIT.",
        "# Device: " + in.device + " (" + in.zynq_ref + " on the SoM)",
        "# Sources (all programmatic, zero hand-typed pins):",
        "#   ball map : " + in.som_source + " netlist (kicad-cli, at generation time)",
        "#   contract : " + in.contract_source + " (cross-checked pin-for-pin, stale = build FAIL)",
        "#   types    : carrier subsystems' typed-port registry",
        "# VCCO rail map (project fpga.bank_rails): " + join(rail_desc, ", "),
        "# " + std::to_string(result.entries.size()) + " pins, banks " +
            join(Strings(banks.begin(), banks.end()), "/") + ", " +
            std::to_string(clocks) + " clock-capable (MRCC/SRCC)",
        "# Ports named IO_* are the bound SoM contract nets not yet claimed",
        "# by a function sheet; the wave-3 function map renames them here",
        "# automatically on the next `schgen board`.",
        std::string(78, '#')};
    std::set<std::string> emitted;
    std::map<std::string, const XdcPin*> by_net;
    for (const auto& e : result.entries) by_net[e.net] = &e;
    for (const auto& bank : banks) {
        std::vector<const XdcPin*> pins;
        for (const auto& e : result.entries) if (e.bank == bank) pins.push_back(&e);
        std::sort(pins.begin(), pins.end(), [](auto a, auto b) { return a->net < b->net; });
        lines.push_back("");
        lines.push_back("# ---- bank " + bank + " — VCCO = " + rails.at(bank) +
                        " (" + std::to_string(pins.size()) + " pins) " + std::string(20, '-'));
        for (const auto* e : pins) {
            if (emitted.count(e->net)) continue;
            std::vector<const XdcPin*> group{e};
            if (pair_kind(e->type.kind)) {
                group.push_back(by_net.at(*e->type.pair_with));
                std::stable_sort(group.begin(), group.end(), [](auto a, auto b) {
                    return p_side(*a) > p_side(*b);
                });
                lines.push_back("# " + e->type.kind + " (" +
                    (e->type.impedance ? std::to_string(*e->type.impedance) : "None") +
                    "R): " + group[0]->net + " / " + group[1]->net);
            }
            for (const auto* g : group) {
                const auto used = g->consumers.empty() ? "unclaimed (wave-3 function map)" :
                                  join(g->consumers, ", ");
                lines.push_back("set_property -dict {PACKAGE_PIN " + g->ball +
                    std::string(g->ball.size() < 4 ? 4 - g->ball.size() : 0, ' ') +
                    " IOSTANDARD " + g->iostd + "} [get_ports {" + g->net +
                    "}]  ;# " + g->jpin + " " + g->pin_name + " <- " + used);
                const auto cc = clock(*g);
                if (!cc.empty() && p_side(*g))
                    lines.push_back("#   ^ " + cc + "-capable: # create_clock -name " +
                        g->net + " -period <ns> [get_ports {" + g->net + "}]");
                emitted.insert(g->net);
            }
        }
    }
    return join(lines, "\n") + "\n";
}
}  // namespace

double xdc_rail_volts(const std::string& rail) {
    static const std::regex pattern("^\\+([0-9]+)V([0-9]*)");
    std::smatch m;
    if (!std::regex_search(rail, m, pattern))
        throw XdcError("cannot parse voltage from rail name " + repr(rail));
    const std::string number = m[1].str() + "." +
                               (m[2].str().empty() ? "0" : m[2].str());
    double value = 0;
    const auto parsed = std::from_chars(number.data(), number.data() + number.size(), value);
    if (parsed.ec == std::errc::result_out_of_range) {
        // Python float() returns infinity / zero on decimal overflow / underflow.
        return m[1].str().find_first_not_of('0') != std::string::npos ?
            std::numeric_limits<double>::infinity() : 0.0;
    }
    if (parsed.ec != std::errc{}) throw XdcError("cannot parse voltage from rail name " + repr(rail));
    return value;
}

std::pair<std::string, bool> xdc_pin_traits(const std::string& name) {
    static const std::regex positive("IO_L[0-9]+P");
    std::string cc;
    for (const auto* kind : {"MRCC", "SRCC"})
        if (name.find(kind) != std::string::npos) { cc = kind; break; }
    return {cc, std::regex_search(name, positive)};
}

XdcOutput generate_xdc(const XdcInput& in) {
    const auto rails = as_map(in.bank_rails), vcco = as_map(in.vcco_rails);
    std::set<std::string> banks;
    for (const auto& [b, _] : rails) banks.insert(b);
    for (const auto& [b, _] : vcco) banks.insert(b);
    Strings bank_order;
    for (const auto& b : in.drift_order) if (banks.erase(b)) bank_order.push_back(b);
    bank_order.insert(bank_order.end(), banks.begin(), banks.end());
    Strings drift;
    for (const auto& b : bank_order) {
        const auto a = rails.find(b), z = vcco.find(b);
        if (a != rails.end() && z != vcco.end() && a->second == z->second) continue;
        drift.push_back(repr(b) + ": {'bank_rails': " +
            (a == rails.end() ? "None" : repr(a->second)) + ", 'VCCO_RAIL_MAP': " +
            (z == vcco.end() ? "None" : repr(z->second)) + "}");
    }
    if (!drift.empty()) throw XdcError(
        "VCCO bank-rail drift: project.json fpga.bank_rails and the "
        "project som_conn_gen.VCCO_RAIL_MAP disagree — the XDC would emit "
        "the wrong IOSTANDARD on a re-railed bank: {" + join(drift, ", ") + "}");

    XdcOutput result;
    const auto names = as_map(in.pin_names), functions = as_map(in.function_map);
    std::map<std::string, Strings> net_balls, consumers;
    std::map<std::string, XdcPort> types;
    for (const auto& p : in.ports) {
        consumers[p.net].push_back(p.sheet);
        if (p.kind != "single") types.emplace(p.net, p);
    }
    for (const auto& [ball, net] : in.ball_net) {
        const auto name = names.find(ball);
        if (name != names.end() && name->second.rfind("IO_", 0) == 0)
            net_balls[net].push_back(ball);
    }
    std::map<std::string, XdcStrings> contract;
    for (const auto& [ref, pins] : in.connectors) contract[ref] = pins;
    for (const auto& ref : in.refs) {
        if (!contract.count(ref)) throw XdcError(ref + " missing from " + in.contract_path);
        Map live_pins;
        for (const auto& [jp, net] : in.jpin_net) if (jp.rfind(ref + ".", 0) == 0) {
            const auto end = jp.find('.', ref.size() + 1);
            live_pins[jp.substr(ref.size() + 1, end - ref.size() - 1)] = net;
        }
        std::set<std::string> expected, actual;
        for (const auto& [pin, _] : contract.at(ref)) expected.insert(pin);
        for (const auto& [pin, _] : live_pins) actual.insert(pin);
        if (expected != actual) throw XdcError(ref + ": contract pin set != live SoM netlist — "
            "som_interface.json is STALE; re-run `schgen som-interface`");
        auto& pins = contract.at(ref);
        pins = sorted_pins(pins);
        for (const auto& [pin, net] : pins)
            if (live_pins.at(pin) != net) throw XdcError(ref + "." + pin + ": contract says " +
                repr(net) + " but the SoM netlist says " + repr(live_pins.at(pin)) +
                " — som_interface.json is STALE; re-run `schgen som-interface`");
        result.checks.push_back(ref + ": all " + std::to_string(expected.size()) +
                               " contract pins match the live SoM netlist verbatim");
    }

    Map seen_balls, seen_nets;
    static const std::regex safe_port("[A-Za-z0-9_]+"), bank_suffix("_([0-9]+)$");
    for (const auto& ref : in.refs) for (const auto& [pin, som_net] : contract.at(ref)) {
        if (som_net.rfind("unconnected-", 0) == 0) continue;
        auto net = som_net == "VIN" ? "+VIN" : som_net;
        if (functions.count(net)) net = functions.at(net);
        if (power_or_ground(net)) continue;
        const auto found = net_balls.find(som_net);
        if (found == net_balls.end()) continue;
        const auto& balls = found->second;
        if (balls.size() > 1) throw XdcError(repr(som_net) + ": reaches " +
            std::to_string(balls.size()) + " PL balls (" + list_repr(balls) +
            ") — ambiguous LOC, refusing to guess");
        const auto& ball = balls.front();
        const auto& name = names.at(ball);
        const auto jp = ref + "." + pin;
        if (!consumers.count(net)) throw XdcError("orphan: " + jp + " net " + repr(som_net) +
            " reaches PL ball " + ball + " but is not a PORT on any carrier sheet");
        if (!std::regex_match(net, safe_port)) throw XdcError(repr(net) +
            ": not a safe Vivado port name (get_ports needs [A-Za-z0-9_]+)");
        std::smatch match;
        if (!std::regex_search(name, match, bank_suffix)) throw XdcError("ball " + ball +
            " pin name " + repr(name) + " carries no bank suffix");
        if (seen_balls.count(ball)) throw XdcError("ball " + ball + " claimed twice: " +
            repr(seen_balls.at(ball)) + " and " + repr(net));
        if (seen_nets.count(net)) throw XdcError("net " + repr(net) + " mapped twice: " +
            seen_nets.at(net) + " and " + jp);
        seen_balls[ball] = net;
        seen_nets[net] = jp;
        XdcPin entry;
        entry.net = net; entry.jpin = jp; entry.ball = ball; entry.pin_name = name;
        entry.bank = match[1].str();
        for (const auto& sheet : consumers.at(net))
            if (sheet.rfind("som_j", 0) != 0) entry.consumers.push_back(sheet);
        if (types.count(net)) entry.type = types.at(net);
        result.entries.push_back(std::move(entry));
    }
    const auto refs = join(in.refs, "/");
    if (result.entries.empty()) throw XdcError("no carrier port reaches a PL ball through " +
                                              refs + " — wrong refs?");
    std::set<std::string> nets;
    for (const auto& e : result.entries) nets.insert(e.net);
    for (auto& e : result.entries) {
        if (!rails.count(e.bank)) throw XdcError("bank " + e.bank + " (" + e.net + " @ " + e.ball +
            "): no VCCO rail decision in project.json fpga.bank_rails — decide the rail there, never default");
        const auto& rail = rails.at(e.bank);
        const auto volts = xdc_rail_volts(rail);
        if (pair_kind(e.type.kind)) {
            if (!e.type.pair_with || !nets.count(*e.type.pair_with)) throw XdcError(e.net +
                ": typed " + e.type.kind + " but its complement " +
                (e.type.pair_with ? repr(*e.type.pair_with) : "None") +
                " is not bound through " + refs + " — half a pair cannot be constrained");
            if (e.type.kind == "tmds_pair") {
                if (volts != 3.3) throw XdcError(e.net + ": TMDS_33 needs a 3.3 V bank, bank " +
                                               e.bank + " runs " + rail);
                e.iostd = "TMDS_33";
            } else {
                if (volts != 2.5) throw XdcError(e.net + ": LVDS_25 needs a 2.5 V bank, bank " +
                    e.bank + " runs " + rail + " (bank " + e.bank + ")");
                e.iostd = "LVDS_25";
            }
        } else if (volts == 3.3) e.iostd = "LVCMOS33";
        else if (volts == 2.5) e.iostd = "LVCMOS25";
        else if (volts == 1.8) e.iostd = "LVCMOS18";
        else {
            throw XdcError("bank " + e.bank + ": no LVCMOS standard for " +
                           float_repr(volts) + " V rail " + rail);
        }
    }
    std::set<std::string> expected;
    for (const auto& [jp, net] : in.jpin_net)
        if (std::find(in.refs.begin(), in.refs.end(), jp.substr(0, jp.find('.'))) != in.refs.end() &&
            net_balls.count(net)) expected.insert(net);
    if (result.entries.size() != expected.size()) throw XdcError("emitted " +
        std::to_string(result.entries.size()) + " pins but the live netlist shows " +
        std::to_string(expected.size()) + " " + refs + " nets on PL balls — a net was dropped");
    result.checks.push_back("emitted pin count " + std::to_string(result.entries.size()) +
        " == live " + refs + "-to-PL net population " + std::to_string(expected.size()));
    result.checks.push_back(std::to_string(seen_balls.size()) + " unique balls, " +
                           std::to_string(seen_nets.size()) + " unique ports (no double-claims)");
    result.text = render(result, in, rails);
    std::size_t n_lines = 0;
    std::istringstream text(result.text);
    for (std::string line; std::getline(text, line);) if (line.rfind("set_property", 0) == 0) ++n_lines;
    if (n_lines != result.entries.size()) throw XdcError("wrote " + std::to_string(n_lines) +
        " set_property lines for " + std::to_string(result.entries.size()) + " pins — renderer bug");
    result.checks.push_back(std::to_string(n_lines) + " set_property lines for " +
                            std::to_string(result.entries.size()) + " pins");
    return result;
}
}  // namespace schgen
