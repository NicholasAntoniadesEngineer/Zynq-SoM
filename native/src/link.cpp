#include "schgen/link.hpp"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <numeric>
#include <optional>
#include <stdexcept>
#include <utility>

namespace schgen {
namespace {
using Strings = std::vector<std::string>;

std::string join(const Strings& items, const std::string& separator) {
    std::string out;
    for (const auto& item : items) {
        if (&item != &items.front()) out += separator;
        out += item;
    }
    return out;
}

std::string repr(const std::string& value) {
    const char quote = value.find('\'') != std::string::npos &&
                       value.find('"') == std::string::npos ? '"' : '\'';
    std::string out(1, quote);
    constexpr char hex[] = "0123456789abcdef";
    for (unsigned char c : value) {
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

std::string list_repr(Strings values) {
    std::sort(values.begin(), values.end());
    for (auto& value : values) value = repr(value);
    return "[" + join(values, ", ") + "]";
}

std::string float_repr(double value) {
    if (std::isnan(value)) return "nan";
    if (std::isinf(value)) return std::signbit(value) ? "-inf" : "inf";
    const std::string sign = std::signbit(value) ? "-" : "";
    char buffer[64];
    const auto converted = std::to_chars(buffer, buffer + sizeof(buffer),
        std::abs(value), std::chars_format::scientific);
    if (converted.ec != std::errc{}) throw std::runtime_error("link: cannot format voltage");
    const std::string scientific(buffer, converted.ptr);
    const auto e = scientific.find('e');
    const int exponent = std::stoi(scientific.substr(e + 1));
    if (exponent < -4 || exponent >= 16) return sign + scientific;
    std::string digits = scientific.substr(0, e);
    const auto dot = digits.find('.');
    if (dot != std::string::npos) digits.erase(dot, 1);
    const int point = exponent + 1;
    if (point <= 0) return sign + "0." + std::string(-point, '0') + digits;
    if (point >= static_cast<int>(digits.size()))
        return sign + digits + std::string(point - digits.size(), '0') + ".0";
    digits.insert(static_cast<std::size_t>(point), ".");
    return sign + digits;
}

std::string upper(std::string text) {
    for (char& c : text) if (c >= 'a' && c <= 'z') c -= 'a' - 'A';
    return text;
}
bool starts_with(const std::string& text, const std::string& prefix) {
    return text.compare(0, prefix.size(), prefix) == 0;
}
bool ends_with(const std::string& text, const std::string& suffix) {
    return text.size() >= suffix.size() &&
        text.compare(text.size() - suffix.size(), suffix.size(), suffix) == 0;
}

Strings tokens(const std::string& name) {
    Strings out;
    const auto text = upper(name);
    int previous = 0;
    for (char c : text) {
        const int kind = c >= 'A' && c <= 'Z' ? 1 : (c >= '0' && c <= '9' ? 2 : 0);
        if (kind) {
            if (kind != previous) out.emplace_back();
            out.back() += c;
        }
        previous = kind;
    }
    return out;
}

std::size_t levenshtein(const std::string& a, const std::string& b,
                        std::size_t cap = 3) {
    if (a.size() > b.size() + cap || b.size() > a.size() + cap) return cap + 1;
    std::vector<std::size_t> prev(b.size() + 1), cur(b.size() + 1);
    std::iota(prev.begin(), prev.end(), 0);
    for (std::size_t i = 0; i < a.size(); ++i) {
        cur[0] = i + 1;
        for (std::size_t j = 0; j < b.size(); ++j)
            cur[j + 1] = std::min({prev[j + 1] + 1, cur[j] + 1,
                                  prev[j] + (a[i] != b[j])});
        if (*std::min_element(cur.begin(), cur.end()) > cap) return cap + 1;
        prev.swap(cur);
    }
    return prev.back();
}

std::string polarity(const std::string& name) {
    const auto up = upper(name);
    for (const auto& entry : std::vector<std::pair<std::string, std::string>>{
            {"_DP", "P"}, {"_DM", "N"}, {"_DN", "N"}, {"DP", "P"},
            {"DM", "N"}, {"DN", "N"}, {"_P", "P"}, {"_N", "N"},
            {"D+", "P"}, {"D-", "N"}, {"+", "P"}, {"-", "N"},
            {"P", "P"}, {"N", "N"}})
        if (ends_with(up, entry.first)) return entry.second;
    return {};
}

std::string complement(const std::string& name) {
    const auto up = upper(name);
    for (const auto& entry : std::vector<std::pair<std::string, std::string>>{
            {"_P", "_N"}, {"_DP", "_DM"}, {"DP", "DM"},
            {"D+", "D-"}, {"+", "-"}, {"P", "N"}})
        if (ends_with(up, entry.first))
            return name.substr(0, name.size() - entry.first.size()) + entry.second;
    return {};
}

Strings hinted_order(const std::set<std::string>& members, const Strings& hints) {
    auto remaining = members;
    Strings result;
    for (const auto& hint : hints) if (remaining.erase(hint)) result.push_back(hint);
    result.insert(result.end(), remaining.begin(), remaining.end());
    return result;
}

const CircuitPortIr* port_type(const CircuitSheetIr& sheet, const std::string& net) {
    const auto found = std::find_if(sheet.port_types.begin(), sheet.port_types.end(),
        [&](const auto& pt) { return pt.net == net; });
    return found == sheet.port_types.end() ? nullptr : &*found;
}

void check_pairs(const std::vector<CircuitSheetIr>& sheets, LinkResult& result,
                 const LinkDiagnosticOrder& order) {
    for (std::size_t index = 0; index < sheets.size(); ++index) {
        const auto& sheet = sheets[index];
        std::set<std::set<std::string>> seen;
        for (const auto& pt : sheet.port_types) {
            if (!pt.has_pair_with) continue;
            const std::set<std::string> key{pt.net, pt.pair_with};
            if (!seen.insert(key).second) continue;
            std::set<std::string> pols;
            for (const auto& name : key) pols.insert(polarity(name));
            if (pols == std::set<std::string>{"P", "N"}) continue;
            Strings hints;
            for (const auto& hint : order.pairs)
                if (hint.sheet_index == index && hint.net == pt.net) {
                    hints = hint.members;
                    break;
                }
            Strings detail;
            for (const auto& name : hinted_order(key, hints)) {
                const auto pol = polarity(name);
                detail.push_back(repr(name) + ": " + (pol.empty() ? "None" : repr(pol)));
            }
            result.errors.push_back("diff-pair polarity: " + sheet.name + ": pair " +
                list_repr(Strings(key.begin(), key.end())) + " reads as {" + join(detail, ", ") +
                "} — need exactly one P and one N");
        }
        for (const auto& net : sheet.nets) {
            if (net.net_class != "port" || port_type(sheet, net.name) ||
                polarity(net.name) != "P") continue;
            const auto comp = complement(net.name);
            if (comp.empty() || port_type(sheet, comp)) continue;
            if (std::any_of(sheet.nets.begin(), sheet.nets.end(),
                [&](const auto& n) { return n.name == comp; }))
                result.warnings.push_back(sheet.name + ": ports " + net.name + "/" + comp +
                    " look like a pair but are untyped (no port_type)");
        }
    }
}

void check_buses(const std::vector<CircuitSheetIr>& sheets, LinkResult& result,
                 const LinkDiagnosticOrder& order) {
    using Role = std::optional<std::string>;
    for (const auto& sheet : sheets) {
        Strings buses;
        std::map<std::string, std::vector<Role>> roles;
        std::map<std::string, std::map<Role, Strings>> members;
        for (const auto& pt : sheet.port_types) {
            if (pt.kind != "i2c") continue;
            const auto bus = pt.has_bus && !pt.bus.empty() ? pt.bus : "I2C";
            const Role role = pt.has_role ? Role(pt.role) : std::nullopt;
            if (!members.count(bus)) buses.push_back(bus);
            if (!members[bus].count(role)) roles[bus].push_back(role);
            members[bus][role].push_back(pt.net);
        }
        for (const auto& bus : buses) {
            std::set<std::string> missing{"scl", "sda"};
            for (const auto& role : roles[bus]) {
                if (role) missing.erase(*role);
                const auto& nets = members.at(bus).at(role);
                if (nets.size() > 1)
                    result.errors.push_back("i2c bus " + repr(bus) + " on " + sheet.name +
                        ": duplicate role " + (role ? repr(*role) : "None") + ": " + list_repr(nets));
            }
            for (const auto& role : hinted_order(missing, order.missing_i2c_roles))
                result.warnings.push_back("i2c bus " + repr(bus) + " on " + sheet.name +
                    ": no " + role + " member typed");
        }
    }
}

void check_agreement(const std::vector<CircuitSheetIr>& sheets, LinkResult& result) {
    using Typed = std::pair<std::string, const CircuitPortIr*>;
    Strings nets, buses;
    std::map<std::string, std::vector<Typed>> by_net;
    std::map<std::string, std::map<double, Strings>> sd_levels;
    for (const auto& sheet : sheets) for (const auto& pt : sheet.port_types) {
        if (!by_net.count(pt.net)) nets.push_back(pt.net);
        by_net[pt.net].emplace_back(sheet.name, &pt);
        if (pt.kind == "sd_bus" && pt.has_level_v) {
            const auto bus = pt.has_bus && !pt.bus.empty() ? pt.bus : "SD";
            if (!sd_levels.count(bus)) buses.push_back(bus);
            sd_levels[bus][pt.level_v].push_back(sheet.name + ":" + pt.net);
        }
    }
    for (const auto& bus : buses) {
        const auto& levels = sd_levels.at(bus);
        if (levels.size() < 2) continue;
        Strings detail;
        for (const auto& [level, members] : levels)
            detail.push_back(float_repr(level) + "V: " + join(members, ", "));
        result.errors.push_back("sd_bus level mismatch on bus " + repr(bus) + ": " +
                                join(detail, "; "));
    }
    for (const auto& net : nets) {
        const auto& typed = by_net.at(net);
        if (typed.size() < 2) continue;
        std::set<std::string> kinds;
        std::set<int32_t> impedances;
        std::set<double> levels;
        Strings kind_detail, impedance_detail, level_detail;
        for (const auto& [sheet, pt] : typed) {
            if (pt->kind != "single") kinds.insert(pt->kind);
            if (pt->has_impedance) impedances.insert(pt->impedance);
            if (pt->has_level_v) levels.insert(pt->level_v);
            kind_detail.push_back(sheet + "=" + pt->kind);
            impedance_detail.push_back(sheet + "=" +
                (pt->has_impedance ? std::to_string(pt->impedance) : "None") + "R");
            level_detail.push_back(sheet + "=" +
                (pt->has_level_v ? float_repr(pt->level_v) : "None") + "V");
        }
        if (kinds.size() > 1) result.errors.push_back("type mismatch on linked net " +
            repr(net) + ": " + join(kind_detail, "; "));
        if (impedances.size() > 1) result.errors.push_back("impedance mismatch on linked net " +
            repr(net) + ": " + join(impedance_detail, "; "));
        if (levels.size() > 1) result.errors.push_back("level mismatch on linked net " +
            repr(net) + ": " + join(level_detail, "; "));
    }
}

const JsonNode& field(const JsonNode& node, const std::string& key, JsonKind kind,
                      const std::string& where) {
    const auto* value = object_field(node, key);
    if (node.kind != JsonKind::Object || !value || value->kind != kind)
        throw std::runtime_error("link: " + where + "." + key + " is missing or has the wrong type");
    return *value;
}

LinkStringMap string_map(const JsonNode& node, const std::string& key) {
    LinkStringMap result;
    for (const auto& [name, value] : field(node, key, JsonKind::Object, "mapping").object_value) {
        if (name.empty() || value.kind != JsonKind::String || value.string_value.empty())
            throw std::runtime_error("link: mapping." + key + " must contain non-empty strings");
        if (!result.emplace(name, value.string_value).second)
            throw std::runtime_error("link: duplicate mapping." + key + " key " + repr(name));
    }
    return result;
}

void validate_mapping(const LinkMapping& mapping) {
    Strings loaded;
    for (const auto& strap : mapping.do_not_load_straps)
        if (mapping.function_map.count(strap) || mapping.pudc_straps.count(strap) ||
            mapping.vcco_rail_map.count(strap) || mapping.rebound_som_rails.count(strap))
            loaded.push_back(strap);
    if (!loaded.empty())
        throw std::runtime_error("link: SoM voltage straps mapped: " + list_repr(loaded));
}

// Numeric connector pin sorting, without narrowing Python's arbitrary-width int.
struct PinNumber { bool negative; std::string digits; };
PinNumber pin_number(const std::string& text) {
    const auto first = text.find_first_not_of(" \t\n\r\f\v");
    const auto last = text.find_last_not_of(" \t\n\r\f\v");
    if (first == std::string::npos)
        throw std::runtime_error("invalid literal for int() with base 10: " + repr(text));
    auto i = first;
    bool negative = false;
    if (text[i] == '+' || text[i] == '-') { negative = text[i] == '-'; ++i; }
    std::string digits;
    bool previous_digit = false;
    for (; i <= last; ++i) {
        const char c = text[i];
        if (c >= '0' && c <= '9') { digits += c; previous_digit = true; }
        else if (c == '_' && previous_digit) previous_digit = false;
        else break;
    }
    if (digits.empty() || !previous_digit || i <= last)
        throw std::runtime_error("invalid literal for int() with base 10: " + repr(text));
    const auto nonzero = digits.find_first_not_of('0');
    return nonzero == std::string::npos ? PinNumber{false, "0"} :
                                       PinNumber{negative, digits.substr(nonzero)};
}
bool numeric_less(const PinNumber& a, const PinNumber& b) {
    if (a.negative != b.negative) return a.negative;
    if (a.digits == b.digits) return false;
    const bool less = a.digits.size() == b.digits.size() ? a.digits < b.digits :
                                                       a.digits.size() < b.digits.size();
    return a.negative ? !less : less;
}

JsonNode str(const std::string& value) {
    JsonNode node; node.kind = JsonKind::String; node.string_value = value; return node;
}
JsonNode number(double value) {
    JsonNode node; node.kind = JsonKind::Number; node.number_value = value; return node;
}
JsonNode array(const Strings& values) {
    JsonNode node; node.kind = JsonKind::Array;
    for (const auto& value : values) node.array_value.push_back(str(value));
    return node;
}
JsonNode port_json(const CircuitPortIr& pt) {
    JsonNode node; node.kind = JsonKind::Object;
    node.object_value = {
        {"kind", str(pt.kind)}, {"pair_with", pt.has_pair_with ? str(pt.pair_with) : JsonNode{}},
        {"impedance", pt.has_impedance ? number(pt.impedance) : JsonNode{}},
        {"role", pt.has_role ? str(pt.role) : JsonNode{}},
        {"bus", pt.has_bus ? str(pt.bus) : JsonNode{}},
        {"speed_hz", pt.has_speed_hz ? number(pt.speed_hz) : JsonNode{}},
        {"level_v", pt.has_level_v ? number(pt.level_v) : JsonNode{}},
        {"expect", pt.has_expect ? str(pt.expect) : JsonNode{}}};
    return node;
}
}  // namespace

std::vector<std::string> link_drift_candidates(const std::string& name,
                                              const std::set<std::string>& pool) {
    Strings result;
    const auto ta = tokens(name);
    for (const auto& cand : pool) {
        if (cand == name) continue;
        auto tb = tokens(cand);
        if (upper(cand) == upper(name) || join(tb, "") == join(ta, "")) {
            result.push_back(cand); continue;
        }
        std::size_t common = 0;
        const auto count = std::max(ta.size(), tb.size());
        for (const auto& token : ta) {
            const auto found = std::find(tb.begin(), tb.end(), token);
            if (found != tb.end()) { tb.erase(found); ++common; }
        }
        if ((common >= 3 && common + 1 >= count) ||
            levenshtein(upper(name), upper(cand)) <= 2) result.push_back(cand);
    }
    return result;
}

LinkSomNets link_som_nets_from_json(const JsonNode& contract) {
    struct Location { std::string ref, location; PinNumber pin; };
    std::map<std::string, std::vector<Location>> nets;
    for (const auto& [ref, connector] :
         field(contract, "connectors", JsonKind::Object, "contract").object_value) {
        for (const auto& [pin, net] :
             field(connector, "pins", JsonKind::Object, "connector " + repr(ref)).object_value) {
            if (net.kind != JsonKind::String)
                throw std::runtime_error("link: connector " + ref + "." + pin + " net must be a string");
            nets[net.string_value].push_back({ref, ref + "." + pin, pin_number(pin)});
        }
    }
    LinkSomNets result;
    for (auto& [net, locations] : nets) {
        std::stable_sort(locations.begin(), locations.end(), [](const auto& a, const auto& b) {
            return a.ref == b.ref ? numeric_less(a.pin, b.pin) : a.ref < b.ref;
        });
        for (const auto& loc : locations) result[net].push_back(loc.location);
    }
    return result;
}

LinkMapping link_mapping_from_json(const JsonNode& node) {
    LinkMapping mapping;
    if (field(node, "schema", JsonKind::String, "mapping").string_value != "schgen.som_mapping.v1")
        throw std::runtime_error("link: unsupported som_mapping schema");
    mapping.function_map = string_map(node, "function_map");
    mapping.pudc_straps = string_map(node, "pudc_straps");
    mapping.vcco_rail_map = string_map(node, "vcco_rail_map");
    mapping.rebound_som_rails = string_map(node, "rebound_som_rails");
    mapping.isolated_som_rails = string_map(node, "isolated_som_rails");
    for (const auto& item : field(node, "do_not_load_straps", JsonKind::Array, "mapping").array_value) {
        if (item.kind != JsonKind::String || item.string_value.empty())
            throw std::runtime_error("link: mapping.do_not_load_straps must contain non-empty strings");
        mapping.do_not_load_straps.insert(item.string_value);
    }
    if (object_field(node, "rail_aliases")) mapping.rail_aliases = string_map(node, "rail_aliases");
    validate_mapping(mapping);
    return mapping;
}

LinkResult link_sheets(const std::vector<CircuitSheetIr>& sheets,
                       const LinkSomNets& som_nets, const LinkMapping& mapping,
                       const LinkDiagnosticOrder& order) {
    validate_mapping(mapping);
    LinkResult result;
    result.sheets = sheets;
    result.mapping = mapping;
    LinkStringMap rebound;
    for (const auto& [som, carrier] : mapping.rebound_som_rails)
        if (!rebound.emplace(carrier, som).second)
            throw std::runtime_error("link: multiple SoM rails rebound onto " + repr(carrier));
    const auto canon = [&](const std::string& name) {
        if (const auto it = rebound.find(name); it != rebound.end()) return it->second;
        if (const auto it = mapping.rail_aliases.find(name); it != mapping.rail_aliases.end())
            return it->second;
        return name;
    };
    std::set<std::string> bound_som, pool;
    std::map<std::string, std::vector<std::size_t>> ports;
    for (const auto& [name, pins] : som_nets) { (void)pins; pool.insert(name); }
    for (std::size_t i = 0; i < sheets.size(); ++i)
        for (const auto& net : sheets[i].nets) if (net.net_class == "port") {
            ports[net.name].push_back(i); pool.insert(net.name);
        }
    for (std::size_t i = 0; i < sheets.size(); ++i) {
        const auto& sheet = sheets[i];
        for (const auto& net : sheet.nets) {
            if (net.net_class != "port") continue;
            LinkPortBinding binding;
            binding.sheet = sheet.name;
            binding.net = net.name;
            binding.ptype.net = net.name;
            binding.ptype.kind = "single";
            if (const auto* pt = port_type(sheet, net.name)) binding.ptype = *pt;
            for (const auto peer : ports.at(net.name)) if (peer != i)
                binding.targets.push_back("sheet " + sheets[peer].name + ":" + net.name);
            const auto som_name = canon(net.name);
            if (const auto it = som_nets.find(som_name); it != som_nets.end()) {
                const auto& pins = it->second;
                const Strings shown(pins.begin(), pins.begin() + std::min<std::size_t>(4, pins.size()));
                binding.targets.push_back("SoM " + som_name + " (" + join(shown, ",") +
                    (pins.size() > 4 ? ",+" + std::to_string(pins.size() - 4) : "") + ")");
                bound_som.insert(som_name);
            }
            if (binding.targets.empty()) {
                if (binding.ptype.has_expect && !binding.ptype.expect.empty()) {
                    binding.status = "deferred";
                    result.deferred.push_back(sheet.name + ":" + net.name +
                                              " — awaiting " + binding.ptype.expect);
                } else {
                    binding.status = "error";
                    const auto candidates = link_drift_candidates(net.name, pool);
                    if (!candidates.empty()) result.errors.push_back("name drift: " + sheet.name +
                        ":" + net.name + " resolves nowhere; near-miss candidates: " + join(candidates, ", "));
                    else result.errors.push_back("undefined port: " + sheet.name + ":" + net.name +
                        " resolves nowhere (no same-named port on another sheet, not a SoM net, no expect= deferral)");
                }
            }
            result.bindings.push_back(std::move(binding));
        }
    }
    std::map<std::string, std::set<std::string>> rails;
    for (const auto& sheet : sheets) for (const auto& net : sheet.nets)
        if (net.net_class == "power" || net.net_class == "ground") rails[net.name].insert(sheet.name);
    for (const auto& [rail, users] : rails) {
        const auto som_name = canon(rail);
        const auto locations = som_nets.find(som_name);
        const auto user_text = join(Strings(users.begin(), users.end()), ", ");
        Strings on_conn;
        for (const auto& user : users) if (starts_with(user, "som_j")) on_conn.push_back(user);
        if (const auto it = mapping.isolated_som_rails.find(rail); it != mapping.isolated_som_rails.end()) {
            std::set<std::string> connectors;
            if (locations != som_nets.end()) for (const auto& loc : locations->second)
                connectors.insert(loc.substr(0, loc.find('.')));
            Strings offenders;
            for (const auto& user : on_conn) if (connectors.count(upper(user.substr(4))))
                offenders.push_back(user);
            if (!offenders.empty()) result.errors.push_back("RAIL ISOLATION VIOLATED: " + rail +
                " is declared isolated from the SoM (" + it->second + ") but the SoM " + repr(som_name) +
                " output pins still bind it on connector sheet(s) " + join(offenders, ", ") +
                " — som_conn_gen must author those pins NC");
            bound_som.insert(som_name);
            result.rail_bindings.push_back(rail + " — ISOLATED from SoM " + repr(som_name) +
                " pins (round-5 decision: " + it->second + "; pins author-NC on the J1 sheet); "
                "carrier-local rail (sheets: " + user_text + ")");
        } else if (rebound.count(rail)) {
            if (on_conn.empty()) result.errors.push_back("REBIND BROKEN: " + rail +
                " is declared the P0 stand-in for SoM " + repr(som_name) +
                " pins but appears on NO connector sheet (sheets: " + user_text +
                ") — som_conn_gen REBOUND_SOM_RAILS must map SoM " + repr(som_name) + " -> " + rail);
            else if (locations == som_nets.end()) result.errors.push_back("REBIND BROKEN: " + rail +
                " -> SoM " + repr(som_name) + " but " + repr(som_name) + " is not a SoM contract net");
            else {
                bound_som.insert(som_name);
                result.rail_bindings.push_back(rail + " — P0 REBIND of SoM " + repr(som_name) +
                    " (the SoM 4.2-5V input; never the 20V +VIN PD rail — wave3_function_map.md P0) "
                    "<- sheets: " + user_text + " -> SoM " + std::to_string(locations->second.size()) + " pins");
            }
        } else if (locations != som_nets.end()) {
            bound_som.insert(som_name);
            const auto alias = som_name != rail ? " (alias of SoM " + repr(som_name) + ")" : "";
            result.rail_bindings.push_back(rail + alias + " <- sheets: " + user_text + " -> SoM " +
                std::to_string(locations->second.size()) + " pins");
        } else {
            if (!on_conn.empty() && mapping.rebound_som_rails.count(rail))
                result.errors.push_back("REBIND DRIFT: SoM net " + repr(rail) +
                    " appears RAW on connector sheet(s) " + join(on_conn, ", ") +
                    " — som_conn_gen must rebind it (REBOUND_SOM_RAILS) onto its carrier rail");
            if (!on_conn.empty() && rail == "+VIN")
                result.errors.push_back("SoM OVERVOLTAGE: the 20V PD rail +VIN reaches connector sheet(s) " +
                    join(on_conn, ", ") + " — the SoM is a 4.2-5V module; J1 VIN must rebind to +5V_SOM "
                    "(wave3_function_map.md P0)");
            result.rail_bindings.push_back(rail + " — carrier-local rail (sheets: " + user_text + ")");
        }
    }
    check_pairs(sheets, result, order);
    check_buses(sheets, result, order);
    check_agreement(sheets, result);
    std::set<std::string> bound_ports;
    for (const auto& binding : result.bindings)
        if (binding.status == "bound") bound_ports.insert(binding.net);
    auto functions = mapping.function_map;
    for (const auto& [som, target] : mapping.pudc_straps) functions[som] = target;
    for (const auto& [som, target] : functions)
        if (som_nets.count(som) && bound_ports.count(target)) bound_som.insert(som);
    for (const auto& [som, target] : mapping.vcco_rail_map)
        if (som_nets.count(som) && rails.count(target)) bound_som.insert(som);
    // do_not_load_straps is connector-generation policy, not a link exemption.
    for (const auto& [name, pins] : som_nets) {
        (void)pins;
        if (!bound_som.count(name)) result.unbound_som.push_back(name);
    }
    return result;
}

LinkResult link_sheets(const std::vector<CircuitSheetIr>& sheets,
                       const JsonNode& contract, const JsonNode& mapping,
                       const LinkDiagnosticOrder& order) {
    return link_sheets(sheets, link_som_nets_from_json(contract), link_mapping_from_json(mapping), order);
}

std::string LinkResult::report() const {
    Strings names;
    for (const auto& sheet : sheets) names.push_back(sheet.name);
    Strings lines{"schgen link report", std::string(60, '='),
        "sheets (" + std::to_string(sheets.size()) + "): " + join(names, ", "), "",
        "alias map (rails only, exact, enumerated):"};
    for (const auto& [carrier, som] : mapping.rail_aliases)
        lines.push_back("  carrier " + repr(carrier) + " <-> SoM " + repr(som));
    if (mapping.rail_aliases.empty()) lines.push_back("  (no pure spelling aliases)");
    LinkStringMap rebound;
    for (const auto& [som, carrier] : mapping.rebound_som_rails) rebound[carrier] = som;
    for (const auto& [carrier, som] : rebound)
        lines.push_back("  carrier " + repr(carrier) + " == SoM " + repr(som) +
            "  (P0 REBIND, not a spelling alias — wave3_function_map.md P0)");
    lines.push_back("  (identity rails +3V3 / +1V8 / GND need no entry; signals are never aliased)");
    lines.emplace_back();
    const auto bound = std::count_if(bindings.begin(), bindings.end(),
        [](const auto& binding) { return binding.status == "bound"; });
    lines.push_back("bound ports (" + std::to_string(bound) + "):");
    for (const auto& binding : bindings) if (binding.status == "bound")
        lines.push_back("  " + binding.sheet + ":" + binding.net +
            (binding.ptype.kind != "single" && !binding.ptype.kind.empty() ?
                " [" + binding.ptype.kind + "]" : "") + " -> " + join(binding.targets, "; "));
    lines.emplace_back();
    lines.push_back("rails (" + std::to_string(rail_bindings.size()) + "):");
    for (const auto& rail : rail_bindings) lines.push_back("  " + rail);
    lines.emplace_back();
    lines.push_back("deferred ports — author-declared, awaiting later waves (" +
        std::to_string(deferred.size()) + ") [WARNING]:");
    for (const auto& port : deferred) lines.push_back("  " + port);
    lines.emplace_back();
    lines.push_back("unbound SoM nets — no consumer yet, later waves (" +
        std::to_string(unbound_som.size()) + ") [WARNING]:");
    for (std::size_t i = 0; i < unbound_som.size(); i += 6)
        lines.push_back("  " + join(Strings(unbound_som.begin() + i,
            unbound_som.begin() + std::min(i + 6, unbound_som.size())), ", "));
    lines.emplace_back();
    if (!warnings.empty()) {
        lines.push_back("other warnings (" + std::to_string(warnings.size()) + "):");
        for (const auto& warning : warnings) lines.push_back("  WARNING: " + warning);
        lines.emplace_back();
    }
    if (!errors.empty()) {
        lines.push_back("ERRORS (" + std::to_string(errors.size()) + "):");
        for (const auto& error : errors) lines.push_back("  ERROR: " + error);
    } else lines.push_back("errors: none");
    lines.emplace_back();
    const auto count = deferred.size() + (!unbound_som.empty() ? 1 : 0) + warnings.size();
    lines.push_back(std::string("LINK: ") + (ok() ? "PASS" : "FAIL") + " (" +
        std::to_string(errors.size()) + " errors, " + std::to_string(count) + " warnings)");
    return join(lines, "\n");
}

JsonNode link_result_json(const LinkResult& result) {
    JsonNode out; out.kind = JsonKind::Object;
    Strings names;
    for (const auto& sheet : result.sheets) names.push_back(sheet.name);
    JsonNode bindings; bindings.kind = JsonKind::Array;
    for (const auto& binding : result.bindings) {
        JsonNode node; node.kind = JsonKind::Object;
        node.object_value = {{"sheet", str(binding.sheet)}, {"net", str(binding.net)},
            {"ptype", port_json(binding.ptype)}, {"targets", array(binding.targets)},
            {"status", str(binding.status)}};
        bindings.array_value.push_back(std::move(node));
    }
    JsonNode ok; ok.kind = JsonKind::Bool; ok.bool_value = result.ok();
    out.object_value = {{"sheets", array(names)}, {"bindings", std::move(bindings)},
        {"rail_bindings", array(result.rail_bindings)}, {"errors", array(result.errors)},
        {"warnings", array(result.warnings)}, {"unbound_som", array(result.unbound_som)},
        {"deferred", array(result.deferred)}, {"ok", ok}, {"report", str(result.report())}};
    return out;
}

}  // namespace schgen
