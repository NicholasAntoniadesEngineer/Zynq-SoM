// Standalone native contracts. Optional --snapshot compares every result field
// and report byte against a Python-generated JSON snapshot; --corpus accepts
// multiple pure-link input/output snapshots. Neither mode executes Python.
#include "schgen/link.hpp"

#include <algorithm>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using namespace schgen;
using Strings = std::vector<std::string>;

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}
void equal(const Strings& actual, const Strings& expected, const char* where) {
    if (actual == expected) return;
    std::string detail = where;
    for (const auto& line : actual) detail += "\n  actual: " + line;
    for (const auto& line : expected) detail += "\nexpected: " + line;
    throw std::runtime_error(detail);
}
template<class F> void rejects(F action, const std::string& fragment) {
    try { action(); }
    catch (const std::exception& e) {
        require(std::string(e.what()).find(fragment) != std::string::npos,
                "wrong rejection: " + std::string(e.what()));
        return;
    }
    throw std::runtime_error("expected rejection: " + fragment);
}

CircuitSheetIr sheet(const std::string& name, const Strings& ports = {}) {
    CircuitSheetIr out; out.name = name; out.schema = "schgen.circuit/1";
    for (const auto& port : ports) out.nets.push_back({port, "port", {}});
    return out;
}
CircuitPortIr type(const std::string& net, const std::string& kind = "single") {
    CircuitPortIr out; out.net = net; out.kind = kind; return out;
}
CircuitPortIr pair(const std::string& net, const std::string& other) {
    auto out = type(net, "diff_pair");
    out.has_pair_with = true; out.pair_with = other;
    out.has_impedance = true; out.impedance = 100;
    return out;
}
CircuitPortIr i2c(const std::string& net, const std::string& role, const std::string& bus) {
    auto out = type(net, "i2c");
    out.has_role = true; out.role = role;
    out.has_bus = true; out.bus = bus;
    return out;
}
CircuitPortIr voltage(const std::string& net, double level) {
    auto out = type(net, "sd_bus"); out.has_level_v = true; out.level_v = level; return out;
}
LinkResult run(const std::vector<CircuitSheetIr>& sheets, const LinkSomNets& nets = {},
               const LinkMapping& mapping = {}, const LinkDiagnosticOrder& order = {}) {
    return link_sheets(sheets, nets, mapping, order);
}

JsonNode str(const std::string& value) {
    JsonNode out; out.kind = JsonKind::String; out.string_value = value; return out;
}
JsonNode obj(std::vector<std::pair<std::string, JsonNode>> fields = {}) {
    JsonNode out; out.kind = JsonKind::Object; out.object_value = std::move(fields); return out;
}
JsonNode arr(std::vector<JsonNode> values = {}) {
    JsonNode out; out.kind = JsonKind::Array; out.array_value = std::move(values); return out;
}
JsonNode empty_mapping() {
    return obj({{"schema", str("schgen.som_mapping.v1")}, {"function_map", obj()},
        {"pudc_straps", obj()}, {"vcco_rail_map", obj()}, {"rebound_som_rails", obj()},
        {"isolated_som_rails", obj()}, {"do_not_load_straps", arr()}});
}
const JsonNode& field(const JsonNode& object, const std::string& key) {
    const auto* value = object_field(object, key);
    require(value != nullptr, "snapshot missing key " + key);
    return *value;
}
Strings strings(const JsonNode& array) {
    require(array.kind == JsonKind::Array, "snapshot must be an array");
    Strings out;
    for (const auto& value : array.array_value) {
        require(value.kind == JsonKind::String, "snapshot must contain strings");
        out.push_back(value.string_value);
    }
    return out;
}

void binding_contracts() {
    const auto empty = run({});
    require(empty.ok() && empty.bindings.empty(), "empty pure input failed");
    require(empty.report().find("LINK: PASS (0 errors, 0 warnings)") != std::string::npos,
            "empty report changed");
    auto a = sheet("same", {"SHARED", "DEFERRED", "LOST_FOREVER", "I2C-SDA", "EMPTY"});
    auto defer = type("DEFERRED"); defer.has_expect = true; defer.expect = "wave 9";
    auto blank = type("EMPTY"); blank.has_expect = true;
    a.port_types = {defer, blank};
    auto b = sheet("same", {"SHARED"});
    auto c = sheet("third", {"SHARED"});
    b.nets.push_back({"LOST_FOREVER", "signal", {}});
    const auto out = run({a, b, c}, {{"SHARED", {"J1.1", "J1.2", "J1.3", "J1.4", "J2.5"}},
                                    {"I2C_SDA", {"J2.1"}}, {"UNUSED", {}}});
    require(out.bindings.size() == 7 && out.sheets.size() == 3, "binding/sheet population changed");
    equal(out.bindings[0].targets, {"sheet same:SHARED", "sheet third:SHARED",
        "SoM SHARED (J1.1,J1.2,J1.3,J1.4,+1)"}, "target order/identity/pin abbreviation");
    equal(out.deferred, {"same:DEFERRED — awaiting wave 9"}, "expect deferral");
    equal(out.errors, {
        "undefined port: same:LOST_FOREVER resolves nowhere (no same-named port on another sheet, not a SoM net, no expect= deferral)",
        "name drift: same:I2C-SDA resolves nowhere; near-miss candidates: I2C_SDA",
        "undefined port: same:EMPTY resolves nowhere (no same-named port on another sheet, not a SoM net, no expect= deferral)"},
        "port error order and diagnostics");
    equal(out.unbound_som, {"I2C_SDA", "UNUSED"}, "sorted unbound population");
    require(out.bindings[0].ptype.kind == "single" && !out.bindings[0].ptype.has_expect &&
            out.bindings[1].status == "deferred" && out.bindings[2].status == "error",
            "binding type defaults/status changed");
    require(out.report().find("LINK: FAIL (3 errors, 2 warnings)") != std::string::npos,
            "report warning count must count unbound as one warning");
    a = sheet("only", {"EXACT"});
    auto pt = type("EXACT"); pt.has_expect = true; pt.expect = "later"; a.port_types = {pt};
    require(run({a}, {{"EXACT", {}}}).bindings[0].status == "bound", "expect overrode an actual binding");
    equal(run({a}, {{"EXACT", {}}}).bindings[0].targets, {"SoM EXACT ()"}, "empty explicit pin list");

    equal(link_drift_candidates("IO_L1_P_35", {"IO_L1_P_35", "io_l1_p_35", "IO-L1-P-35",
        "P_35_IO_L1", "IO_L1_N_35", "unrelated"}),
        {"IO-L1-P-35", "IO_L1_N_35", "P_35_IO_L1", "io_l1_p_35"}, "drift rules/sort");
    equal(link_drift_candidates("AAAA", {"AA", "A", "BBBB", "AAABBB"}), {"AA"},
          "edit-distance cap must not silently grow");
    equal(link_drift_candidates("!", {"?"}), {"?"}, "empty token spelling comparison");
    equal(link_drift_candidates("A_A_A_B", {"A_B_C_D"}), {}, "token matches consume repeated tokens");
}

void rail_contracts() {
    LinkMapping mapping;
    mapping.rebound_som_rails = {{"VIN", "+5V_SOM"}};
    mapping.isolated_som_rails = {{"+3V3", "local source only"}};
    mapping.rail_aliases = {{"GROUND", "GND"}};
    auto power = sheet("power");
    power.nets = {{"+5V_SOM", "power", {}}, {"+3V3", "power", {}},
                  {"GROUND", "ground", {}}, {"+LOCAL", "power", {}}};
    auto conn = sheet("som_j1");
    conn.nets = {{"+5V_SOM", "power", {}}};
    const LinkSomNets som{{"VIN", {"J1.1", "J1.2"}}, {"+3V3", {"J1.24"}}, {"GND", {"J1.3"}}};
    const auto good = run({power, conn}, som, mapping);
    require(good.ok() && good.unbound_som.empty(), "safe rails failed");
    equal(good.rail_bindings, {
        "+3V3 — ISOLATED from SoM '+3V3' pins (round-5 decision: local source only; pins author-NC on the J1 sheet); carrier-local rail (sheets: power)",
        "+5V_SOM — P0 REBIND of SoM 'VIN' (the SoM 4.2-5V input; never the 20V +VIN PD rail — wave3_function_map.md P0) <- sheets: power, som_j1 -> SoM 2 pins",
        "+LOCAL — carrier-local rail (sheets: power)",
        "GROUND (alias of SoM 'GND') <- sheets: power -> SoM 1 pins"}, "rail ordering/text");
    equal(run({power}, som, mapping).errors, {
        "REBIND BROKEN: +5V_SOM is declared the P0 stand-in for SoM 'VIN' pins but appears on NO connector sheet (sheets: power) — som_conn_gen REBOUND_SOM_RAILS must map SoM 'VIN' -> +5V_SOM"},
        "missing connector gate");
    equal(run({conn}, {}, mapping).errors, {
        "REBIND BROKEN: +5V_SOM -> SoM 'VIN' but 'VIN' is not a SoM contract net"},
        "missing contract gate");
    conn.nets.push_back({"+3V3", "power", {}});
    conn.nets.push_back({"+VIN", "power", {}});
    const auto bad = run({conn, power}, som, mapping);
    equal(bad.errors, {
        "RAIL ISOLATION VIOLATED: +3V3 is declared isolated from the SoM (local source only) but the SoM '+3V3' output pins still bind it on connector sheet(s) som_j1 — som_conn_gen must author those pins NC",
        "SoM OVERVOLTAGE: the 20V PD rail +VIN reaches connector sheet(s) som_j1 — the SoM is a 4.2-5V module; J1 VIN must rebind to +5V_SOM (wave3_function_map.md P0)"},
        "isolation/overvoltage gates and order");
    auto other = sheet("som_j2"); other.nets = {{"+3V3", "power", {}}};
    require(run({other}, som, mapping).ok(), "isolation check ignored actual contract connector");
    other.name = "som_J1";
    require(run({other}, som, mapping).ok(), "connector prefix case changed");
    conn.nets = {{"VIN", "power", {}}};
    equal(run({conn}, {}, mapping).errors, {
        "REBIND DRIFT: SoM net 'VIN' appears RAW on connector sheet(s) som_j1 — som_conn_gen must rebind it (REBOUND_SOM_RAILS) onto its carrier rail"}, "raw rebind gate");
    require(run({conn}, som, mapping).ok(), "raw contract branch changed from Python policy");
    mapping.rebound_som_rails["SECOND"] = "+5V_SOM";
    rejects([&] { run({}, {}, mapping); }, "multiple SoM rails rebound");
}

void pair_contracts() {
    auto a = sheet("pairs", {"Z_P", "A_P", "USB_DP", "USB_DM", "MISSING_POLARITY", "SELF_P"});
    a.port_types = {pair("Z_P", "A_P"), pair("A_P", "Z_P"),
                    pair("MISSING_POLARITY", "USB_DM"), pair("SELF_P", "SELF_P")};
    LinkSomNets som;
    for (const auto& net : a.nets) som[net.name] = {};
    LinkDiagnosticOrder order;
    order.pairs = {{0, "Z_P", {"Z_P", "Z_P", "foreign"}}};
    const auto out = run({a}, som, {}, order);
    equal(out.errors, {
        "diff-pair polarity: pairs: pair ['A_P', 'Z_P'] reads as {'Z_P': 'P', 'A_P': 'P'} — need exactly one P and one N",
        "diff-pair polarity: pairs: pair ['MISSING_POLARITY', 'USB_DM'] reads as {'MISSING_POLARITY': None, 'USB_DM': 'N'} — need exactly one P and one N",
        "diff-pair polarity: pairs: pair ['SELF_P'] reads as {'SELF_P': 'P'} — need exactly one P and one N"},
        "pair validation, de-duplication, and non-exempting order hints");
    equal(out.warnings, {"pairs: ports USB_DP/USB_DM look like a pair but are untyped (no port_type)"},
          "untyped pair diagnostic");
    for (const auto& names : std::vector<std::pair<std::string, std::string>>{
            {"A_P", "A_N"}, {"A_DP", "A_DM"}, {"ADP", "ADN"}, {"AD+", "AD-"},
            {"A+", "A-"}, {"AP", "AN"}, {"p", "n"}}) {
        a = sheet("valid", {names.first, names.second});
        a.port_types = {pair(names.first, names.second), pair(names.second, names.first)};
        require(run({a}, {{names.first, {}}, {names.second, {}}}).ok(), "polarity suffix rejected");
    }
    a = sheet("inference", {"x_p", "x_N"});
    a.nets[1].net_class = "signal";
    equal(run({a}, {{"x_p", {}}}).warnings,
          {"inference: ports x_p/x_N look like a pair but are untyped (no port_type)"},
          "complement keeps prefix case and matches non-port complement like Python");
    a.port_types.push_back(type("x_p"));
    require(run({a}, {{"x_p", {}}}).warnings.empty(), "explicit single type did not suppress inference");
}

void bus_and_agreement_contracts() {
    auto a = sheet("a", {"ZDA", "ADA", "ZCL", "ACL", "ONLY", "BAD"});
    a.port_types = {i2c("ZDA", "sda", "Z"), i2c("ADA", "sda", "Z"),
        i2c("ZCL", "scl", "Z"), i2c("ACL", "scl", "Z"), i2c("ONLY", "scl", ""), type("BAD", "i2c")};
    a.port_types.back().has_bus = true; a.port_types.back().bus = "A";
    LinkSomNets som; for (const auto& net : a.nets) som[net.name] = {};
    LinkDiagnosticOrder order; order.missing_i2c_roles = {"sda", "sda", "bogus"};
    const auto buses = run({a}, som, {}, order);
    equal(buses.errors, {"i2c bus 'Z' on a: duplicate role 'sda': ['ADA', 'ZDA']",
                        "i2c bus 'Z' on a: duplicate role 'scl': ['ACL', 'ZCL']"},
                        "I2C bus/role insertion order");
    equal(buses.warnings, {"i2c bus 'I2C' on a: no sda member typed",
        "i2c bus 'A' on a: no sda member typed", "i2c bus 'A' on a: no scl member typed"},
        "I2C fallback bus and non-exempting missing-role hints");

    a = sheet("a", {"Z", "A"});
    a.port_types = {voltage("Z", 3.3), type("A")};
    a.port_types[0].has_impedance = true; a.port_types[0].impedance = 90;
    auto b = sheet("b", {"Z", "OTHER"});
    auto pt = type("Z", "tmds_pair");
    pt.has_impedance = true; pt.impedance = 100; pt.has_level_v = true; pt.level_v = 1.8;
    b.port_types = {pt, voltage("OTHER", 1.8)};
    auto c = sheet("c", {"Z"}); c.port_types = {type("Z")};
    const auto agreement = run({a, b, c}, {{"A", {}}, {"OTHER", {}}});
    equal(agreement.errors, {
        "sd_bus level mismatch on bus 'SD': 1.8V: b:OTHER; 3.3V: a:Z",
        "type mismatch on linked net 'Z': a=sd_bus; b=tmds_pair; c=single",
        "impedance mismatch on linked net 'Z': a=90R; b=100R; c=NoneR",
        "level mismatch on linked net 'Z': a=3.3V; b=1.8V; c=NoneV"},
        "SD aggregate check must precede linked type/impedance/level checks");
    for (const auto& sample : std::vector<std::pair<double, std::string>>{
            {0.0, "0.0"}, {-0.0, "-0.0"}, {-1.25, "-1.25"}, {1e-5, "1e-05"},
            {1e-4, "0.0001"}, {1e16, "1e+16"}, {1.2345678901234567, "1.2345678901234567"}}) {
        a = sheet("a", {"X"}); b = sheet("b", {"X"});
        auto left = type("X"); left.has_level_v = true; left.level_v = sample.first;
        auto right = type("X"); right.has_level_v = true; right.level_v = 99.0;
        a.port_types = {left}; b.port_types = {right};
        equal(run({a, b}).errors, {"level mismatch on linked net 'X': a=" + sample.second +
            "V; b=99.0V"}, "Python float diagnostic formatting");
    }
}

void mapping_and_json_contracts() {
    LinkMapping mapping;
    mapping.function_map = {{"RAW", "FUNC"}, {"RAW_OVERRIDE", "FUNC"}, {"PENDING", "LATER"}};
    mapping.pudc_straps = {{"RAW_OVERRIDE", "NOT_PRESENT"}};
    mapping.vcco_rail_map = {{"+VCCO_34", "+3V3"}};
    mapping.do_not_load_straps = {"BOOT"};
    auto a = sheet("a", {"FUNC", "LATER"});
    auto future = type("LATER"); future.has_expect = true; future.expect = "later";
    a.port_types = {future}; a.nets.push_back({"+3V3", "power", {}});
    auto b = sheet("b", {"FUNC"});
    const auto result = run({a, b}, {{"RAW", {}}, {"RAW_OVERRIDE", {}}, {"PENDING", {}},
        {"+VCCO_34", {}}, {"BOOT", {}}}, mapping);
    equal(result.unbound_som, {"BOOT", "PENDING", "RAW_OVERRIDE"},
        "function/PUDC/VCCO accounting must not bind deferred ports or exempt straps");
    for (int which = 0; which != 4; ++which) {
        auto invalid = mapping;
        auto* target = which == 0 ? &invalid.function_map : which == 1 ? &invalid.pudc_straps :
                       which == 2 ? &invalid.vcco_rail_map : &invalid.rebound_som_rails;
        (*target)["BOOT"] = "FUNC";
        rejects([&] { run({}, {}, invalid); }, "SoM voltage straps mapped: ['BOOT']");
    }
    auto policy = empty_mapping();
    require(link_mapping_from_json(policy).function_map.empty(), "explicit empty policy rejected");
    const auto contract = obj({{"connectors", obj({
        {"J2", obj({{"pins", obj({{"1", str("N")}})}})},
        {"J1", obj({{"pins", obj({{"10", str("N")}, {"2", str("N")}, {"02", str("N")},
            {"-10", str("N")}, {"-2", str("N")}, {"10000000000000000000000", str("N")},
            {"+1_0", str("N")}, {"1", str("X")}})}})}})}});
    const auto nets = link_som_nets_from_json(contract);
    equal(nets.at("N"), {"J1.-10", "J1.-2", "J1.2", "J1.02", "J1.10", "J1.+1_0",
        "J1.10000000000000000000000", "J2.1"}, "stable arbitrary-width numeric pin sorting");
    require(link_sheets({sheet("a", {"N"})}, contract, policy).ok(), "JSON overload failed");
    for (const auto* pin : {"1tail", "", "-", "1__0", "1_"})
        rejects([&] { link_som_nets_from_json(obj({{"connectors", obj({
            {"J1", obj({{"pins", obj({{pin, str("X")}})}})}})}})); }, "invalid literal for int()");
    rejects([&] { link_som_nets_from_json(obj()); }, "contract.connectors");
    for (std::size_t i = 0; i < policy.object_value.size(); ++i) {
        auto missing = policy; missing.object_value.erase(missing.object_value.begin() + i);
        rejects([&] { link_mapping_from_json(missing); }, "missing or has the wrong type");
    }
    auto wrong = policy; wrong.object_value[1].second = arr();
    rejects([&] { link_mapping_from_json(wrong); }, "mapping.function_map");
    wrong = policy; wrong.object_value[0].second = str("v2");
    rejects([&] { link_mapping_from_json(wrong); }, "unsupported som_mapping schema");
    wrong = policy; wrong.object_value[1].second = obj({{"X", str("")}});
    rejects([&] { link_mapping_from_json(wrong); }, "must contain non-empty strings");
    wrong = policy; wrong.object_value[1].second = obj({{"X", str("A")}, {"X", str("B")}});
    rejects([&] { link_mapping_from_json(wrong); }, "duplicate mapping.function_map");
    wrong = policy; wrong.object_value.back().second = arr({str("")});
    rejects([&] { link_mapping_from_json(wrong); }, "do_not_load_straps must contain");
    auto typed = type("N", "single");
    typed.has_bus = typed.has_role = typed.has_expect = true;  // Present empty != null.
    typed.has_speed_hz = true; typed.speed_hz = 400000;
    a = sheet("a", {"N"}); a.port_types = {typed};
    const auto json = link_result_json(run({a}, {{"N", {}}}));
    const auto& pt = field(field(json, "bindings").array_value[0], "ptype");
    require(field(pt, "bus").kind == JsonKind::String &&
            field(pt, "pair_with").kind == JsonKind::Null &&
            field(pt, "speed_hz").number_value == 400000,
            "serialization lost optional presence or non-checking metadata");
}

void compare_json(const JsonNode& actual, const JsonNode& expected, const std::string& path) {
    require(actual.kind == expected.kind, path + ": JSON kind differs");
    switch (expected.kind) {
        case JsonKind::Null: return;
        case JsonKind::String:
            require(actual.string_value == expected.string_value, path + ": text differs\nactual: " +
                    actual.string_value + "\nexpected: " + expected.string_value); return;
        case JsonKind::Bool:
            require(actual.bool_value == expected.bool_value, path + ": bool differs"); return;
        case JsonKind::Number:
            require(actual.number_value == expected.number_value, path + ": number differs"); return;
        case JsonKind::Array:
            require(actual.array_value.size() == expected.array_value.size(), path + ": array length differs");
            for (std::size_t i = 0; i < expected.array_value.size(); ++i)
                compare_json(actual.array_value[i], expected.array_value[i], path + "[" + std::to_string(i) + "]");
            return;
        case JsonKind::Object:
            require(actual.object_value.size() == expected.object_value.size(), path + ": object size differs");
            for (const auto& [key, value] : expected.object_value)
                compare_json(field(actual, key), value, path + "." + key);
            return;
    }
}

// Decode only fields consumed by pure link. Corpus cases intentionally include
// invalid port declarations to exercise all gates independently of the loader.
CircuitSheetIr corpus_sheet(const JsonNode& json) {
    auto out = sheet(field(json, "name").string_value);
    for (const auto& net : field(json, "nets").array_value)
        out.nets.push_back({field(net, "name").string_value, field(net, "net_class").string_value, {}});
    for (const auto& entry : field(json, "port_types").object_value) {
        const auto& value = entry.second;
        auto pt = type(entry.first, field(value, "kind").string_value);
        const auto optional_string = [&](const std::string& key, std::string& target, bool& present) {
            const auto& item = field(value, key); present = item.kind != JsonKind::Null;
            if (present) target = item.string_value;
        };
        optional_string("pair_with", pt.pair_with, pt.has_pair_with);
        optional_string("role", pt.role, pt.has_role);
        optional_string("bus", pt.bus, pt.has_bus);
        optional_string("expect", pt.expect, pt.has_expect);
        const auto& impedance = field(value, "impedance");
        pt.has_impedance = impedance.kind != JsonKind::Null;
        pt.impedance = static_cast<int32_t>(impedance.number_value);
        const auto& speed = field(value, "speed_hz");
        pt.has_speed_hz = speed.kind != JsonKind::Null;
        pt.speed_hz = static_cast<int32_t>(speed.number_value);
        const auto& level = field(value, "level_v");
        pt.has_level_v = level.kind != JsonKind::Null; pt.level_v = level.number_value;
        out.port_types.push_back(pt);
    }
    return out;
}

void corpus(const std::string& path) {
    const auto data = parse_json_file(path);
    for (const auto& test : data.array_value) {
        std::vector<CircuitSheetIr> sheets;
        for (const auto& value : field(test, "sheets").array_value) sheets.push_back(corpus_sheet(value));
        LinkSomNets som;
        for (const auto& [name, pins] : field(test, "som_nets").object_value) som[name] = strings(pins);
        LinkDiagnosticOrder order;
        const auto& hints = field(test, "order");
        order.missing_i2c_roles = strings(field(hints, "missing_i2c_roles"));
        for (const auto& item : field(hints, "pairs").array_value)
            order.pairs.push_back({static_cast<std::size_t>(field(item, "sheet_index").number_value),
                field(item, "net").string_value, strings(field(item, "members"))});
        const auto result = run(sheets, som, link_mapping_from_json(field(test, "mapping")), order);
        compare_json(link_result_json(result), field(test, "expected"), field(test, "name").string_value);
    }
    std::cout << "Python corpus parity: " << data.array_value.size() << " cases\n";
}

void snapshot(const std::string& subsystems, const std::string& contract,
              const std::string& mapping, const std::string& expected_path) {
    const auto expected = parse_json_file(expected_path);
    std::vector<CircuitSheetIr> sheets;
    for (const auto& name : strings(field(expected, "sheets")))
        sheets.push_back(load_circuit_json(std::filesystem::path(subsystems) / name / "circuit.json"));
    const auto result = link_sheets(sheets, parse_json_file(contract), parse_json_file(mapping));
    compare_json(link_result_json(result), expected, "snapshot");
    std::cout << "Python snapshot parity: " << sheets.size() << " sheets, " << result.bindings.size()
              << " bindings, " << result.rail_bindings.size() << " rails; all fields/report bytes match\n";
}
}  // namespace

int main(int argc, char** argv) {
    try {
        binding_contracts();
        rail_contracts();
        pair_contracts();
        bus_and_agreement_contracts();
        mapping_and_json_contracts();
        std::cout << "Native link contracts passed\n";
        if (argc == 3 && std::string(argv[1]) == "--corpus") corpus(argv[2]);
        else if (argc == 6 && std::string(argv[1]) == "--snapshot")
            snapshot(argv[2], argv[3], argv[4], argv[5]);
        else require(argc == 1, "usage: link_contracts [--corpus JSON | --snapshot SUBSYSTEMS CONTRACT MAPPING EXPECTED]");
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
