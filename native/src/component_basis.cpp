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
const char* const basis_schema = "schgen.component_basis/1";
const char* const basis_file = "component_basis.json";
const char* const library_scope = "library";
const char* const library_folder = "subsystems";
const std::set<std::string> library_keys{"schema","declarations","uses","sheets","board_scope_only"}, board_keys{"schema","uses","sheets"},
    declaration_keys{"name","value","unit","basis","class","numeric"}, use_keys{"sheet","target","attribute","declaration","type"};
const JsonNode& basis_array(const JsonNode& root, const std::string& key, const std::string& file) {
    const auto* v = object_field(root, key);
    if(!v) throw ModelCheckError(file + ": missing required field '" + key + "'");
    if(v->kind != JsonKind::Array) throw ModelCheckError(file + ": field '" + key + "' must be an array");
    return *v;
}
std::string basis_row(const std::string& file, const std::string& key, std::size_t index) {
    return file + " " + key + " row " + std::to_string(index + 1);
}
void read_basis_file(const std::filesystem::path& path, const std::string& scope, bool library, ComponentBasisPolicy& policy) {
    const auto file = path.string();
    if(!std::filesystem::is_regular_file(path)) throw ModelCheckError("the component basis file is missing: " + file);
    const auto root = parse_json_file(file);
    reject_unknown_keys(root, library ? library_keys : board_keys, file);
    if(require_string(root, "schema", false, file) != basis_schema) throw ModelCheckError(file + ": schema must be " + basis_schema);
    std::set<std::string> declared;
    if(library) {
        const auto& rows = basis_array(root, "declarations", file);
        for(std::size_t i = 0; i < rows.array_value.size(); ++i) {
            const auto& row = rows.array_value[i];
            const auto where = basis_row(file, "declarations", i);
            reject_unknown_keys(row, declaration_keys, where);
            ComponentBasisDeclaration d;
            d.name = require_string(row, "name", false, where); d.value = require_string(row, "value", false, where);
            d.unit = require_string(row, "unit", false, where); d.basis = require_string(row, "basis", false, where);
            d.klass = require_string(row, "class", false, where);
            const auto* numeric = object_field(row, "numeric");
            if(!numeric) throw ModelCheckError(where + ": missing required field 'numeric'");
            if(numeric->kind != JsonKind::Bool) throw ModelCheckError(where + ": field 'numeric' must be a boolean");
            d.numeric = numeric->bool_value;
            d.site = std::string(library_folder) + "/" + basis_file + ":" + d.name;
            if(!declared.insert(d.name).second) throw ModelCheckError(where + ": declaration " + d.name + " is listed twice");
            policy.declarations.push_back(std::move(d));
        }
    } else for(const auto& d : policy.declarations) declared.insert(d.name);
    std::set<std::string> sheets;
    const auto& sheet_rows = basis_array(root, "sheets", file);
    for(std::size_t i = 0; i < sheet_rows.array_value.size(); ++i) {
        const auto& row = sheet_rows.array_value[i];
        const auto where = basis_row(file, "sheets", i);
        if(row.kind != JsonKind::String) throw ModelCheckError(where + ": must be a string");
        if(row.string_value.empty()) throw ModelCheckError(where + ": must not be empty");
        if(!sheets.insert(row.string_value).second) throw ModelCheckError(where + ": sheet " + row.string_value + " is listed twice");
        policy.sheets.push_back({scope, row.string_value});
    }
    if(library) {
        const auto& only_rows = basis_array(root, "board_scope_only", file);
        std::set<std::string> only;
        for(std::size_t i = 0; i < only_rows.array_value.size(); ++i) {
            const auto& row = only_rows.array_value[i];
            const auto where = basis_row(file, "board_scope_only", i);
            if(row.kind != JsonKind::String) throw ModelCheckError(where + ": must be a string");
            if(row.string_value.empty()) throw ModelCheckError(where + ": must not be empty");
            if(!only.insert(row.string_value).second) throw ModelCheckError(where + ": " + row.string_value + " is listed twice");
            policy.board_scope_only.push_back(row.string_value);
        }
    }
    const auto& use_rows = basis_array(root, "uses", file);
    for(std::size_t i = 0; i < use_rows.array_value.size(); ++i) {
        const auto& row = use_rows.array_value[i];
        const auto where = basis_row(file, "uses", i);
        reject_unknown_keys(row, use_keys, where);
        ComponentBasisUse u;
        u.scope = scope; u.sheet = require_string(row, "sheet", false, where); u.target = require_string(row, "target", false, where);
        u.attribute = require_string(row, "attribute", false, where); u.declaration = require_string(row, "declaration", false, where);
        u.type = require_string(row, "type", false, where);
        if(!sheets.count(u.sheet)) throw ModelCheckError(where + ": sheet " + u.sheet + " is not in this file's sheets");
        if(!declared.count(u.declaration)) throw ModelCheckError(where + ": declaration " + u.declaration + " does not exist");
        policy.uses.push_back(std::move(u));
    }
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
ComponentBasisPolicy load_component_basis_policy(const std::filesystem::path& repository) {
    ComponentBasisPolicy policy;
    read_basis_file(repository / library_folder / basis_file, library_scope, true, policy);
    for(const auto& folder : board_folders(repository)) read_basis_file(folder / basis_file, folder.filename().string(), false, policy);
    for(const auto& name : policy.board_scope_only)
        if(std::none_of(policy.sheets.begin(), policy.sheets.end(), [&](const ComponentBasisSheet& s) { return s.scope != library_scope && s.name == name; }))
            throw ModelCheckError((repository / library_folder / basis_file).string() + ": board_scope_only " + name + " is in the sheets of no board");
    return policy;
}
std::set<std::string> component_basis_scopes(const std::filesystem::path& repository) {
    std::set<std::string> scopes{library_scope};
    for(const auto& folder : board_folders(repository)) scopes.insert(folder.filename().string());
    return scopes;
}
std::vector<ComponentBasisInput> author_component_basis_inputs(const std::filesystem::path& root, const ComponentBasisPolicy& policy) {
    const auto context = make_authoring_context(root);
    std::vector<ComponentBasisInput> out;
    const auto file = (root / library_folder / basis_file).string();
    const auto library = subsystem_library(context);
    const auto is_library = [&](const std::string& name) {
        return std::any_of(library.begin(), library.end(), [&](const auto& d) { return d.name == name; });
    };
    for(const auto& s : policy.sheets)
        if(s.scope == library_scope && !is_library(s.name)) throw ModelCheckError(file + ": sheets names " + s.name + ", which is not a library subsystem");
    for(const auto& name : policy.board_scope_only)
        if(!is_library(name)) throw ModelCheckError(file + ": board_scope_only names " + name + ", which is not a library subsystem");
    for(const auto& d : library) {
        const bool listed = std::any_of(policy.sheets.begin(), policy.sheets.end(), [&](const ComponentBasisSheet& s) { return s.scope == library_scope && s.name == d.name; });
        const bool board_only = std::find(policy.board_scope_only.begin(), policy.board_scope_only.end(), d.name) != policy.board_scope_only.end();
        if(listed == board_only)
            throw ModelCheckError("library subsystem " + d.name + (listed ? " is in both sheets and board_scope_only of " : " is neither in sheets nor in board_scope_only of ") + file);
        if(listed) out.push_back({library_scope, d.name, author_subsystem(d.name, SubsystemMeta{}, context)});
    }
    for(const auto& folder : board_folders(root))
        for(const auto& d : project_subsystem_definitions(folder)) {
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
