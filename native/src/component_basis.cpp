#include "schgen/component_basis.hpp"
#include "model_checks_internal.hpp"
#include <algorithm>
#include <cctype>
#include <regex>
#include <sstream>

namespace schgen {
namespace {
std::string sheet_key(const std::string& scope, const std::string& sheet) { return scope + "/" + sheet; }
bool blank(const std::string& s) {
    return std::all_of(s.begin(), s.end(), [](unsigned char c) { return std::isspace(c); });
}
bool magnitude(const CircuitPartIr& p) {
    if(p.lib_id == "Device:R" || p.lib_id == "Device:C" || p.lib_id == "Device:L") return true;
    // Numeric catalog identifiers (e.g. Molex 878311420) are not magnitudes.
    // Catalog passives still need coverage even if their value ceases to be SI.
    const auto colon = p.lib_id.find(':');
    const auto symbol = p.lib_id.substr(colon == std::string::npos ? 0 : colon + 1);
    if(symbol == "R" || symbol == "C" || symbol == "L") return true;
    if(!p.ref.empty() && (p.ref[0] == 'R' || p.ref[0] == 'C' || p.ref[0] == 'L') &&
       p.ref.size() > 1 && std::isdigit(static_cast<unsigned char>(p.ref[1]))) return true;
    static const std::regex si(R"(^[0-9]+(\.[0-9]+)?([pnumkKMGµ][0-9]*(R|F|H|Hz)?|R|F|H|Hz)$)");
    return std::regex_match(p.value, si);
}
bool dimension(const ComponentBasisDeclaration& d, const ComponentBasisUse& u) {
    if(u.attribute == "speed_hz") return d.numeric && d.unit == "Hz";
    if(u.attribute == "impedance") return d.numeric && d.unit == "ohm";
    if(u.attribute != "value" || d.numeric) return false;
    if(u.type == "Device:R") return d.unit == "ohm";
    if(u.type == "Device:C") return d.unit == "F";
    if(u.type == "Device:L" || (!u.target.empty() && u.target[0] == 'L')) return d.unit == "H";
    return true;
}
}
ComponentBasisResult audit_component_basis(const std::vector<ComponentBasisInput>& input,
    const std::set<std::string>& scopes, const ComponentBasisPolicy& policy) {
    ComponentBasisResult r;
    std::map<std::string, const ComponentBasisDeclaration*> declarations;
    const std::set<std::string> units{"ohm","F","H","Hz"}, classes{"datasheet","measured","policy"};
    for(const auto& d : policy.declarations) {
        if(!declarations.emplace(d.name, &d).second) r.broken.push_back(d.name + ": duplicate declaration");
        if(blank(d.name) || blank(d.value) || blank(d.basis) || blank(d.site))
            r.broken.push_back(d.name + ": empty name, value, basis or provenance");
        if(!units.count(d.unit)) r.broken.push_back(d.name + ": unknown unit " + d.unit);
        if(!classes.count(d.klass)) r.broken.push_back(d.name + ": unknown source class " + d.klass);
    }
    std::set<std::string> all_sheets, expected, policy_scopes;
    for(const auto& s : policy.sheets) {
        const auto key = sheet_key(s.scope, s.name);
        if(!all_sheets.insert(key).second) r.broken.push_back(key + ": duplicate sheet expectation");
        policy_scopes.insert(s.scope);
        if(scopes.count(s.scope)) expected.insert(key);
    }
    if(scopes.empty()) r.broken.push_back("no audit scopes requested");
    for(const auto& scope : scopes) if(!policy_scopes.count(scope)) r.broken.push_back("unknown scope " + scope);
    std::map<std::string, const CircuitSheetIr*> circuits;
    for(const auto& in : input) {
        const auto key = sheet_key(in.scope, in.sheet);
        if(!expected.count(key)) r.broken.push_back(key + ": unexpected live sheet");
        if(!circuits.emplace(key, &in.circuit).second) r.broken.push_back(key + ": duplicate live sheet");
    }
    r.n_files = circuits.size();
    for(const auto& key : expected) if(!circuits.count(key)) r.broken.push_back(key + ": missing live sheet");
    std::set<std::string> used, relevant, globally_used, targets;
    std::map<std::string, std::set<std::string>> covered;
    for(const auto& u : policy.uses) {
        const auto key = sheet_key(u.scope, u.sheet);
        if(!all_sheets.count(key)) r.broken.push_back(key + ": use lacks sheet expectation");
        globally_used.insert(u.declaration);
        if(!scopes.count(u.scope)) continue;
        relevant.insert(u.declaration);
        ++r.n_sites;
        const auto where = key + ":" + u.target + "." + u.attribute;
        if(!targets.insert(where).second) r.broken.push_back(where + ": duplicate obligation");
        const auto di = declarations.find(u.declaration);
        if(di == declarations.end()) { r.undeclared.push_back(where + " -> " + u.declaration); continue; }
        const auto& d = *di->second;
        if(!dimension(d,u)) r.broken.push_back(where + ": declaration dimension/type mismatch " + d.name);
        const auto ci = circuits.find(key);
        if(ci == circuits.end()) continue;
        const auto& c = *ci->second;
        if(u.attribute == "value") {
            covered[key].insert(u.target);
            const auto part = std::find_if(c.parts.begin(), c.parts.end(), [&](const auto& p) { return p.ref == u.target; });
            if(part == c.parts.end()) { r.broken.push_back(where + ": expected component missing"); continue; }
            used.insert(d.name);
            if(part->lib_id != u.type) r.broken.push_back(where + ": component type " + part->lib_id + " != " + u.type);
            if(part->value != d.value) r.broken.push_back(where + ": emitted " + part->value + " != " + d.name + "=" + d.value);
        } else if(u.attribute == "speed_hz" || u.attribute == "impedance") {
            const auto port = std::find_if(c.port_types.begin(), c.port_types.end(), [&](const auto& p) { return p.net == u.target; });
            const auto net = std::find_if(c.nets.begin(), c.nets.end(), [&](const auto& n) { return n.name == u.target; });
            if(port == c.port_types.end() || net == c.nets.end() || net->pins.empty()) {
                r.broken.push_back(where + ": live connected port missing"); continue;
            }
            used.insert(d.name);
            const bool has = u.attribute == "speed_hz" ? port->has_speed_hz : port->has_impedance;
            const auto value = u.attribute == "speed_hz" ? port->speed_hz : port->impedance;
            if(!has || std::to_string(value) != d.value || port->kind != u.type)
                r.broken.push_back(where + ": emitted port policy differs from " + d.name);
        } else r.broken.push_back(where + ": unknown obligation attribute");
    }
    for(const auto& [key, c] : circuits) {
        std::set<std::string> refs, nets, ports;
        for(const auto& p : c->parts) {
            if(!refs.insert(p.ref).second) r.broken.push_back(key + ":" + p.ref + ": duplicate live component");
            if(magnitude(p) && !covered[key].count(p.ref))
                r.raw.push_back(key + ":" + p.ref + " -> '" + p.value + "' (no basis obligation)");
        }
        for(const auto& n : c->nets) if(!nets.insert(n.name).second) r.broken.push_back(key + ":" + n.name + ": duplicate net");
        for(const auto& p : c->port_types) if(!ports.insert(p.net).second) r.broken.push_back(key + ":" + p.net + ": duplicate port");
    }
    for(const auto& [name, d] : declarations) {
        (void)d;
        if(!globally_used.count(name)) r.unused.push_back(name + ": no declared consumer");
        else if(relevant.count(name) && !used.count(name)) r.unused.push_back(name + ": no live consumer");
    }
    r.n_registered = relevant.size();
    return r;
}
std::vector<ComponentBasisInput> author_component_basis_inputs(const std::filesystem::path& root) {
    const auto context = make_authoring_context(root);
    std::vector<ComponentBasisInput> out;
    for(const auto& d : subsystem_definitions()) out.push_back({"library", d.name, author_subsystem(d.name, SubsystemMeta{}, context)});
    for(const auto& d : project_subsystem_definitions()) {
        ProjectAuthoringInput input; input.context = context; input.project_root = root / d.project;
        out.push_back({d.project, d.name, author_project_subsystem(d.project, d.name, input)});
    }
    return out;
}
std::string component_basis_report(const ComponentBasisResult& r) {
    std::ostringstream out;
    out << "COMPONENT BASIS: " << (r.ok() ? "PASS" : "FAIL") << " — " << r.n_registered
        << " declarations, " << r.n_files << " live circuits, " << r.n_sites << " obligations";
    for(const auto& s : r.raw) out << "\n  RAW component: " << s;
    for(const auto& s : r.undeclared) out << "\n  UNREGISTERED: " << s;
    for(const auto& s : r.unused) out << "\n  DEAD registration: " << s;
    for(const auto& s : r.broken) out << "\n  BROKEN: " << s;
    return out.str();
}
JsonNode component_basis_result_json(const ComponentBasisResult& r) {
    using namespace model_checks;
    return obj({{"ok",j(r.ok())},{"n_registered",j(double(r.n_registered))},{"n_files",j(double(r.n_files))},{"n_sites",j(double(r.n_sites))},
        {"raw",strings(r.raw)},{"undeclared",strings(r.undeclared)},{"unused",strings(r.unused)},{"broken",strings(r.broken)}});
}
JsonNode component_basis_policy_json(const ComponentBasisPolicy& p) {
    using namespace model_checks;
    auto declarations = arr(), uses = arr(), sheets = arr();
    for(const auto& d : p.declarations) declarations.array_value.push_back(obj({
        {"name",j(d.name)},{"value",j(d.value)},{"unit",j(d.unit)},{"basis",j(d.basis)},{"klass",j(d.klass)},
        {"numeric",j(d.numeric)},{"site",j(d.site)}}));
    for(const auto& u : p.uses) uses.array_value.push_back(strings({u.scope,u.sheet,u.target,u.attribute,u.declaration,u.type}));
    for(const auto& s : p.sheets) sheets.array_value.push_back(strings({s.scope,s.name}));
    return obj({{"declarations",declarations},{"uses",uses},{"sheets",sheets}});
}
} // namespace schgen
