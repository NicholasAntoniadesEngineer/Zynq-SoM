#include "selftest_full_internal.hpp"

namespace schgen::selftesting {
namespace {
std::string quote(const std::string& text) {
    std::string out = "\"";
    constexpr char hex[] = "0123456789abcdef";
    for (unsigned char c : text) {
        if (c == '"' || c == '\\') { out += '\\'; out += char(c); }
        else if (c < 32) { out += "\\u00"; out += hex[c >> 4]; out += hex[c & 15]; }
        else out += char(c);
    }
    return out + '"';
}
JsonNode pins(const std::vector<CircuitPinRefIr>& values) {
    auto out = arr();
    for (const auto& p : values) out.array_value.push_back(j(pin(p)));
    return out;
}
JsonNode verdict(const SelftestStackVerdict& v) {
    return obj({{"failures", strings(v.failures)}, {"passed", strings(v.passed)},
                {"green", j(v.green())}});
}
JsonNode determinism(const SelftestDeterminism& d) {
    return obj({{"ok", j(d.ok)}, {"diagnostic", j(d.diagnostic)}});
}
} // namespace

std::string json_text(const JsonNode& n) {
    switch (n.kind) {
    case JsonKind::Null: return "null";
    case JsonKind::Bool: return n.bool_value ? "true" : "false";
    case JsonKind::String: return quote(n.string_value);
    case JsonKind::Number: {
        if (!std::isfinite(n.number_value)) throw std::invalid_argument("selftest: nonfinite JSON number");
        char b[128]; const auto r = std::to_chars(b, b + sizeof b, n.number_value);
        if (r.ec != std::errc{}) throw std::runtime_error("selftest: JSON number out of range");
        return {b, r.ptr};
    }
    case JsonKind::Array: {
        std::vector<std::string> items;
        for (const auto& item : n.array_value) items.push_back(json_text(item));
        return "[" + join(items, ",") + "]";
    }
    case JsonKind::Object: {
        std::vector<std::string> items;
        for (const auto& [key, value] : n.object_value) items.push_back(quote(key) + ":" + json_text(value));
        return "{" + join(items, ",") + "}";
    }
    }
    throw std::invalid_argument("selftest: invalid JSON type");
}

JsonNode circuit_json(const CircuitSheetIr& c) {
    auto parts = arr(), nets = arr(), ports = obj(), hints = obj(), loads = obj();
    for (const auto& p : c.parts) {
        auto fields = obj(), names = obj();
        for (const auto& v : p.fields) fields.object_value.emplace_back(v.key, j(v.value));
        for (const auto& v : p.pin_names) names.object_value.emplace_back(v.name, strings(v.numbers));
        parts.array_value.push_back(obj({{"ref", j(p.ref)}, {"lib_id", j(p.lib_id)},
            {"value", j(p.value)}, {"footprint", j(p.footprint)}, {"fields", fields},
            {"pin_names", names}, {"pin_numbers", strings(p.pin_numbers)}}));
    }
    for (const auto& n : c.nets)
        nets.array_value.push_back(obj({{"name", j(n.name)}, {"net_class", j(n.net_class)}, {"pins", pins(n.pins)}}));
    for (const auto& p : c.port_types) {
        ports.object_value.emplace_back(p.net, obj({{"kind", j(p.kind)},
            {"pair_with", p.has_pair_with ? j(p.pair_with) : JsonNode{}},
            {"impedance", p.has_impedance ? j(double(p.impedance)) : JsonNode{}},
            {"role", p.has_role ? j(p.role) : JsonNode{}},
            {"bus", p.has_bus ? j(p.bus) : JsonNode{}},
            {"speed_hz", p.has_speed_hz ? j(double(p.speed_hz)) : JsonNode{}},
            {"level_v", p.has_level_v ? j(p.level_v) : JsonNode{}},
            {"expect", p.has_expect ? j(p.expect) : JsonNode{}}}));
    }
    for (const auto& h : c.hints) hints.object_value.emplace_back(h.net, j(h.style));
    for (const auto& l : c.loads) {
        auto* items = find(loads.object_value, l.rail);
        if (!items) { loads.object_value.emplace_back(l.rail, arr()); items = &loads.object_value.back().second; }
        items->array_value.push_back(arr({j(l.amps), j(l.note)}));
    }
    auto out = obj({{"schema", j(c.schema)}, {"name", j(c.name)}, {"title", j(c.title)},
        {"parts", parts}, {"nets", nets}, {"nc", pins(c.nc)}, {"port_types", ports},
        {"hints", hints}, {"loads", loads}});
    for (const auto& kind : {"tp_waivers", "decap_waivers", "pull_waivers", "reset_waivers",
                            "strap_waivers", "ep_waivers", "thermal_waivers", "part_rule_waivers"}) {
        auto ws = obj();
        for (const auto& w : c.waivers) if (w.kind == kind) ws.object_value.emplace_back(w.key, j(w.reason));
        out.object_value.emplace_back(kind, ws);
    }
    return out;
}

// Bounded, line-based diagnostic; the verdict always compares the complete bytes.
std::string drift_diff(const std::string& a, const std::string& b,
                       const std::string& aname, const std::string& bname) {
    const auto al = lines(a), bl = lines(b);
    std::size_t i = 0;
    while (i < al.size() && i < bl.size() && al[i] == bl[i]) ++i;
    std::vector<std::string> out = {"--- " + aname, "+++ " + bname,
        "@@ first differing line " + std::to_string(i + 1) + " @@"};
    for (std::size_t k = i; k < std::min(al.size(), i + 4); ++k) out.push_back("-" + al[k]);
    for (std::size_t k = i; k < std::min(bl.size(), i + 4); ++k) out.push_back("+" + bl[k]);
    if (al == bl && a != b) out.push_back("(end-of-file newline differs)");
    return join(out, "\n    ");
}
} // namespace schgen::selftesting

namespace schgen {
JsonNode selftest_full_result_json(const SelftestFullResult& r) {
    using namespace selftesting;
    auto sheets = arr(), proofs = arr();
    for (const auto& s : r.sheets) {
        auto mutations = arr();
        for (const auto& m : s.mutations) mutations.array_value.push_back(obj({
            {"name", j(m.name)}, {"description", j(m.description)},
            {"verdict", verdict(m.verdict)}, {"killed", j(m.killed)}}));
        sheets.array_value.push_back(obj({{"name", j(s.name)}, {"baseline", verdict(s.baseline)},
            {"mutations", mutations}, {"problems", strings(s.problems)},
            {"injected", j(double(s.injected))}, {"killed", j(double(s.killed))},
            {"determinism", determinism(s.determinism)}, {"hashseed", determinism(s.hashseed)},
            {"report", j(s.report)}}));
    }
    for (const auto& p : r.models.proofs) proofs.array_value.push_back(obj({
        {"name", j(p.name)}, {"baseline_ok", j(p.baseline_ok)},
        {"mutation_killed", j(p.mutation_killed)}, {"diagnostic", j(p.diagnostic)}}));
    return obj({{"ok", j(r.ok())}, {"exit_code", j(double(r.exit_code()))},
        {"injected", j(double(r.injected))}, {"killed", j(double(r.killed))},
        {"scratch", j(r.scratch.string())}, {"report", j(r.report)},
        {"problems", strings(r.problems)}, {"sheets", sheets},
        {"models", obj({{"proofs", proofs}, {"problems", strings(r.models.problems)},
            {"injected", j(double(r.models.injected))}, {"killed", j(double(r.models.killed))},
            {"report", j(r.models.report)}})}});
}
} // namespace schgen
