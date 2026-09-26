#include "schgen/authoring_purity.hpp"
#include "authoring_purity_clang.hpp"

#include <algorithm>
#include <exception>
#include <fstream>
#include <iterator>
#include <map>
#include <set>
#include <sstream>
#include <tuple>
#include <utility>

namespace schgen {
namespace {
using namespace purity_clang;
namespace fs = std::filesystem;
bool starts(const std::string& s, const std::string& p) { return s.compare(0, p.size(), p) == 0; }
bool function(const std::string& k) {
    return k == "FunctionDecl" || k == "CXXMethod" || k == "CXXConstructor" ||
           k == "CXXDestructor" || k == "CXXConversion" || k == "FunctionTemplate";
}
bool data_declaration(const std::string& k) {
    return k == "StructDecl" || k == "ClassDecl" || k == "ClassTemplate" ||
           k == "TypedefDecl" || k == "TypeAliasDecl" || k == "EnumDecl" || k == "FieldDecl";
}
bool cpp(const fs::path& p) {
    const auto e = p.extension().string(); return e == ".cpp" || e == ".cc" || e == ".cxx" || e == ".C";
}
std::string source_path(const fs::path& root, const fs::path& path) {
    if (path.empty()) return {};
    const auto p = fs::weakly_canonical(path).lexically_relative(root).generic_string();
    return p.empty() || p == ".." || starts(p, "../") ? fs::weakly_canonical(path).generic_string() : p;
}
std::string checked_path(const fs::path& root, const std::string& value, bool directory = false) {
    const fs::path p(value);
    if (p.empty() || p.is_absolute() || p.lexically_normal() != p)
        throw std::runtime_error("expected normalized root-relative path: " + value);
    const auto resolved = source_path(root, root / p);
    if (resolved != value || (directory ? !fs::is_directory(root / p) : !fs::is_regular_file(root / p)))
        throw std::runtime_error("missing, escaping or aliased scope path: " + value);
    return value;
}
bool circuit_result(const std::string& type) {
    // This is the compiler's canonical result type, not source-token scanning.
    for (const std::string name : {"CircuitSheetIr", "CircuitAuthor"}) {
    for (auto pos = type.find(name); pos != type.npos; pos = type.find(name, pos + name.size())) {
        const auto ident = [](char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                                             (c >= '0' && c <= '9') || c == '_'; };
        if ((pos == 0 || !ident(type[pos - 1])) &&
            (pos + name.size() == type.size() || !ident(type[pos + name.size()]))) return true;
    }
    }
    return false;
}
const std::set<std::string> banned_names = {
    "placer", "Placement", "Spacing", "_Builder", "_Engine", "PlacedPart", "PlacedPower",
    "PlacedDesign", "Wire", "Junction", "HierLabel", "LocalLabel", "NoConnect", "Box", "Seg",
    "SheetGeometry", "body_box_page", "pin_page_position", "place", "route", "emit",
    "SchematicPlacement", "SchematicRoute", "PlacedSheet", "PcbPlacement", "OccupancyGrid"
};
struct Site { std::string file; unsigned line = 0, column = 0; };
struct Pending { Site site; std::string entity, usr, owner; };
struct OwnedFinding { std::string owner; AuthoringPurityFinding finding; };
struct Scanner {
    Api& api;
    fs::path root;
    const AuthoringPurityScope& scope;
    AuthoringPurityResult& result;
    std::set<std::string> allowed, units, providers, provider_headers, definitions, seen_constructors, registered, infrastructure;
    std::map<std::string,std::string> identities;
    std::set<std::string> capability_uses;
    std::vector<Cursor> ancestry;
    std::set<std::string> roots, function_definitions;
    std::map<std::string, std::set<std::string>> edges;
    std::map<std::string, std::size_t> references;
    std::vector<OwnedFinding> deferred;
    std::string owner;
    std::vector<Pending> pending;
    std::set<std::string> seen_findings, included;
    std::exception_ptr exception;
    std::string main_file;
    bool audit = false;
    bool full_census = true;
    std::vector<fs::path> system_roots;
    std::map<void*, std::string> file_paths;
    std::map<std::string, std::string> input_bytes;
    void* translation_unit = nullptr;
    std::set<std::string> defined_constructors;
    std::set<std::string> visited_definitions;

    Scanner(Api& a, fs::path r, const AuthoringPurityScope& s, AuthoringPurityResult& out)
        : api(a), root(std::move(r)), scope(s), result(out),
          registered(s.constructors.begin(), s.constructors.end()),
          infrastructure(s.infrastructure.begin(), s.infrastructure.end()) {
        for (const auto& f : s.units) { checked_path(root, f); units.insert(f); allowed.insert(f); }
        for (const auto& f : s.providers) { checked_path(root, f); providers.insert(f); allowed.insert(f); }
        for (const auto& f : s.headers) { checked_path(root, f); allowed.insert(f); }
        for (const auto& f : s.provider_headers) { checked_path(root,f); allowed.insert(f); provider_headers.insert(f); }
        if (units.empty() || registered.empty() || s.census_roots.empty())
            throw std::runtime_error("a nonempty unit, constructor and census-root scope is required");
        if (units.size() != s.units.size() || providers.size() != s.providers.size() ||
            allowed.size() != s.units.size() + s.providers.size() + s.headers.size() + s.provider_headers.size() ||
            registered.size() != s.constructors.size() || infrastructure.size() != s.infrastructure.size())
            throw std::runtime_error("duplicate scope entry");
        for (const auto& key : registered) if (infrastructure.count(key))
            throw std::runtime_error("constructor cannot also be infrastructure: " + key);
    }
    std::string kind(Cursor c) { return api.text(api.getCursorKindSpelling(c.kind)); }
    std::string spelling(Cursor c) { return api.text(api.getCursorSpelling(c)); }
    std::string usr(Cursor c) { return api.text(api.getCursorUSR(c)); }
    std::string file_path(void* f) {
        if (!f) return {};
        auto found = file_paths.find(f);
        if (found != file_paths.end()) return found->second;
        auto path = source_path(root, api.text(api.getFileName(f)));
        file_paths.emplace(f, path); return path;
    }
    Site site(Location loc) {
        void* f = nullptr; unsigned line = 0, column = 0, offset = 0;
        api.getExpansionLocation(loc, &f, &line, &column, &offset);
        return {file_path(f), line, column};
    }
    Site site(Cursor c) { return site(api.getCursorLocation(c)); }
    std::string name(Cursor c) {
        std::vector<std::string> names;
        for (unsigned n = 0; !api.Cursor_isNull(c) && n < 100; ++n) {
            const auto k = kind(c);
            if (k == "TranslationUnit") break;
            auto s = spelling(c);
            if (!s.empty()) names.push_back(std::move(s));
            c = api.getCursorSemanticParent(c);
        }
        std::string out;
        for (auto i = names.rbegin(); i != names.rend(); ++i) { if (!out.empty()) out += "::"; out += *i; }
        return out;
    }
    std::string canonical(Type t) { return api.text(api.getTypeSpelling(api.getCanonicalType(t))); }
    std::string identity(Cursor c) { return site(c).file + "::" + name(c) + " | " + canonical(api.getCursorType(c)); }
    bool circuit_api(Cursor c) {
        // Object copy/move constructors are implementation dependencies, not
        // additional subsystem factories merely because they take an IR rvalue.
        if (kind(c) == "CXXConstructor") return false;
        if (circuit_result(canonical(api.getCursorResultType(c)))) return true;
        // Mutating output parameters are another constructor shape. Canonical
        // pointee constness comes from the compiler, not spelling like "const".
        const auto count = api.Cursor_getNumArguments(c);
        for (int i = 0; i < count; ++i) {
            auto t = api.getCanonicalType(api.getCursorType(api.Cursor_getArgument(c, static_cast<unsigned>(i))));
            auto pointee = api.getPointeeType(t);
            if (pointee.kind && !api.isConstQualifiedType(pointee) && circuit_result(canonical(pointee))) return true;
        }
        return false;
    }
    void issue(const std::string& code, const Site& s, const std::string& entity, const std::string& detail, bool global = false) {
        const auto key = code + ":" + s.file + ":" + std::to_string(s.line) + ":" +
                         std::to_string(s.column) + ":" + entity + ":" + detail + ":" + (global ? "" : owner);
        if (seen_findings.insert(key).second) {
            AuthoringPurityFinding f{code, s.file, entity, detail, s.line, s.column};
            if (global || owner.empty()) result.findings.push_back(std::move(f));
            else deferred.push_back({owner, std::move(f)});
        }
    }
    static unsigned visitor(Cursor c, Cursor, void* opaque) {
        auto& s = *static_cast<Scanner*>(opaque);
        try { s.visit(c); return 1; /* Continue; recursion is explicit. */ }
        catch (...) { s.exception = std::current_exception(); return 0; }
    }
    void children(Cursor c) {
        api.visitChildren(c, visitor, this);
        if (exception) std::rethrow_exception(exception);
    }
    bool system(Cursor c) {
        return api.Location_isInSystemHeader(api.getCursorLocation(c)) != 0 && trusted_system_path(site(c).file);
    }
    bool trusted_system_path(const std::string& path) const {
        if (!fs::path(path).is_absolute()) return false;
        for (const auto& dir : system_roots) {
            const auto r = fs::path(path).lexically_relative(dir).generic_string();
            if (!r.empty() && r != ".." && !starts(r, "../")) return true;
        }
        return false;
    }
    std::vector<Cursor> direct_children(Cursor c) {
        std::vector<Cursor> out;
        api.visitChildren(c, [](Cursor child, Cursor, void* data)->unsigned {
            static_cast<std::vector<Cursor>*>(data)->push_back(child); return 1;
        }, &out);
        return out;
    }
    bool capability_call(Cursor call) {
        // Only inspect the receiver subtree, not arbitrary argument references
        // that could smuggle an approved field into an unrelated erased call.
        auto receiver=direct_children(call);
        if (receiver.empty()) return false;
        Cursor node=receiver.front();
        for (unsigned depth=0;depth<16;++depth) {
            const auto k=kind(node);
            if (k=="MemberRefExpr") {
                const auto field=api.getCursorReferenced(node);
                if (api.Cursor_isNull(field) || kind(field)!="FieldDecl") return false;
                const auto key=identity(field);
                for (const auto& capability:scope.capabilities) if (capability.field==key && capability.caller==identities[owner]) {
                    capability_uses.insert(key); return true;
                }
                return false;
            }
            if (k!="UnexposedExpr" && k!="ParenExpr") return false;
            receiver=direct_children(node);
            if (receiver.size()!=1) return false;
            node=receiver.front();
        }
        return false;
    }
    void capability_reference(Cursor target, const Site& here) {
        if (kind(target)!="FieldDecl") return;
        const auto key=identity(target);
        for (const auto& capability:scope.capabilities) if (capability.field==key) {
            // A validated receiver may be tested or invoked, not overwritten,
            // extracted, swapped, or handed to another callable. The runtime
            // validator may inspect target<T>(); it does not invoke the field.
            std::string operation;
            for (auto p=ancestry.rbegin()+1;p!=ancestry.rend();++p) {
                const auto k=kind(*p);
                if (function(k)) break;
                if (k=="CallExpr") {
                    const auto call_target=api.getCursorReferenced(*p);
                    if (!api.Cursor_isNull(call_target) && system(call_target)) operation=spelling(call_target);
                    break;
                }
                if (k=="MemberRefExpr") {
                    const auto method=api.getCursorReferenced(*p);
                    if (!api.Cursor_isNull(method) && function(kind(method)) && system(method)) continue;
                }
                if (k!="UnexposedExpr" && k!="ParenExpr") break;
            }
            const bool use=identities[owner]==capability.caller && (operation=="operator()" || operation=="operator bool");
            const bool guard=identities[owner]==capability.runtime_guard && operation=="target";
            if (!use && !guard) issue("capability-escape",here,key,"named callback can only be tested/invoked at its reviewed site or inspected by its runtime guard");
        }
    }
    void reference(Cursor c, Cursor target, bool call) {
        const auto here = site(c);
        if (api.Cursor_isNull(target)) {
            if (call) issue("unresolved-call", here, spelling(c), "compiler cannot resolve a direct target");
            return;
        }
        const auto n = name(target), k = kind(target), short_name = spelling(target);
        if (kind(c)=="MemberRefExpr") capability_reference(target,here);
        if (banned_names.count(short_name))
            issue("forbidden-entity", here, n, "geometry/placement/emission or manual placer API");
        const bool fn = function(k);
        if (call && !fn) issue("indirect-call", here, n, "function pointer or unresolved callable dispatch");
        if (call && k == "CXXMethod" && api.CXXMethod_isVirtual(target) && !system(target))
            issue("virtual-call", here, n, "runtime receiver target is not proven");
        if (system(target)) {
            // Standard containers/algorithms are trusted toolchain machinery;
            // user arguments/lambda bodies/function references are still walked.
            // Type-erased/dynamic dispatch has no compiler-visible target here.
            const auto parent = api.getCursorSemanticParent(target);
            const auto parent_name = spelling(parent);
            if (call && ((short_name == "operator()" &&
                (parent_name == "function" || parent_name == "move_only_function" ||
                 parent_name == "__bind" || parent_name == "__bind_r")) ||
                short_name == "invoke" || short_name == "apply" || short_name == "async" ||
                parent_name == "thread" || parent_name == "jthread") && !capability_call(c))
                issue("indirect-call", here, n, "type-erased or deferred callback requires a statically closed authoring boundary");
            return;
        }
        const auto origin = site(target);
        if (units.count(here.file) && provider_headers.count(origin.file))
            issue("private-provider-api",here,n,"constructor reached a private metadata-provider declaration directly");
        if (!allowed.count(origin.file)) {
            issue("unreviewed-dependency", here, n, "declaration is outside checked files: " + origin.file);
            return;
        }
        const bool variable = k == "VarDecl";
        if (!fn && !variable && !data_declaration(k)) return;
        // Retain a compiler-resolved specialization when libclang provides it;
        // its dependent calls have concrete types. Falling back to the generic
        // pattern would lose precisely the callee evidence we are checking.
        const auto specialized_definition = api.getCursorDefinition(target);
        const auto templ = api.getSpecializedCursorTemplate(target);
        const auto base = !api.Cursor_isNull(specialized_definition) || api.Cursor_isNull(templ) ? target : templ;
        auto id = usr(base);
        if (id.empty()) {
            issue("unresolved-identity", here, n, "compiler omitted declaration identity"); return;
        }
        auto def = api.getCursorDefinition(base);
        if (!api.Cursor_isNull(def) && allowed.count(site(def).file)) visit(def);
        else if (data_declaration(k)) visit(target);
        if (owner.empty()) roots.insert(id); else edges[owner].insert(id);
        pending.push_back({here, n, id, owner});
    }
    void visit(Cursor c) {
        if (system(c)) return;
        struct PathGuard {
            std::vector<Cursor>& path;
            PathGuard(std::vector<Cursor>& value, Cursor node):path(value) { path.push_back(node); }
            ~PathGuard() { path.pop_back(); }
        } path_guard(ancestry,c);
        const auto k = kind(c), short_name = spelling(c);
        const auto s = site(c);
        const bool fn = function(k);
        if (fn && api.isCursorDefinition(c) && !s.file.empty() && !fs::path(s.file).is_absolute() &&
            circuit_api(c)) {
            const auto key = identity(c);
            if (seen_constructors.insert(key).second) result.constructor_census.push_back(key);
            if (api.isCursorDefinition(c) && audit) defined_constructors.insert(key);
            if (!registered.count(key) && !infrastructure.count(key)) {
                const auto previous_owner = owner;
                owner = usr(c);
                issue("unregistered-constructor", s, key, "IR-producing/mutating declaration lacks reviewed constructor/infrastructure classification", full_census || units.count(s.file));
                owner = previous_owner;
            }
            if (registered.count(key) && !allowed.count(s.file))
                issue("unchecked-constructor", s, key, "registered constructor must be in a fully checked unit", true);
        }
        if (!audit) { children(c); return; }
        if (!s.file.empty() && !allowed.count(s.file)) return; // Include already fails; never bless its definitions.
        const bool definition = ((fn || (k == "VarDecl" && !short_name.empty())) && api.isCursorDefinition(c)) || data_declaration(k);
        const auto id = definition || fn ? usr(c) : std::string{};
        if (definition) {
            identities[id]=identity(c);
            for (const auto& capability:scope.capabilities)
                if (capability.target==identities[id] || capability.runtime_guard==identities[id]) roots.insert(id);
        }
        struct OwnerGuard {
            std::string& current; std::string old; bool switched;
            OwnerGuard(std::string& value, const std::string& next, bool change)
                : current(value), old(change ? std::move(value) : std::string{}), switched(change) { if (change) current = next; }
            ~OwnerGuard() { if (switched) current = std::move(old); }
        } guard(owner, id, fn || (definition && (data_declaration(k) || owner.empty())));
        if (definition && (units.count(s.file) || registered.count(identity(c)))) roots.insert(id);
        if (banned_names.count(short_name) &&
            (fn || k == "VarDecl" || k == "FieldDecl" || k == "StructDecl" || k == "ClassDecl" ||
             k == "TypedefDecl" || k == "TypeAliasDecl"))
            issue("forbidden-declaration", s, name(c), "manual placer/geometry declarations are outside netlist authoring", units.count(main_file) != 0);
        if (k == "GCCAsmStmt" || k == "MSAsmStmt")
            issue("opaque-operation", s, name(c), "compiler cursor evidence cannot resolve inline assembly targets");
        if (definition) {
            if (id.empty()) issue("unresolved-identity", s, name(c), "definition has no compiler identity");
            if (!visited_definitions.insert(id).second) return;
            definitions.insert(id); if (fn) function_definitions.insert(id);
        }
        const bool call = k == "CallExpr";
        if (call || k == "DeclRefExpr" || k == "MemberRefExpr" || k == "TypeRef" || k == "TemplateRef") {
            ++references[owner];
            reference(c, api.getCursorReferenced(c), call);
        }
        children(c);
    }
    static void inclusion(void* file, Location* stack, unsigned depth, void* opaque) {
        auto& s = *static_cast<Scanner*>(opaque);
        try {
            const auto path = s.file_path(file);
            const bool project = !fs::path(path).is_absolute();
            if (project) {
                std::size_t size = 0;
                const char* data = s.api.getFileContents(s.translation_unit, file, &size);
                if (!data && size != 0) throw std::runtime_error("compiler omitted source bytes for " + path);
                std::string bytes(data ? data : "", size);
                const auto prior = s.input_bytes.emplace(path, bytes);
                if (!prior.second && prior.first->second != bytes)
                    s.issue("source-changed", {path, 0, 0}, {}, "compiler observed different bytes in two translation units");
            }
            if (depth == 0 || !s.units.count(s.main_file)) return;
            // A system header may include other system headers. Project headers
            // cannot turn themselves into trusted machinery with -isystem: paths
            // inside root are always policy-controlled below.
            const auto from = s.site(stack[0]);
            if (!project) {
                if (!s.trusted_system_path(path) || !s.api.Location_isInSystemHeader(s.api.getLocationForOffset(s.translation_unit, file, 0)))
                    s.issue("unreviewed-header", from, path, "external non-system header is outside the reviewed closure");
                return;
            }
            if (s.included.insert(path).second) s.result.included_project_headers.push_back(path);
            if (!s.allowed.count(path) || s.provider_headers.count(path)) s.issue("unreviewed-header", from, path, "not in the reviewed netlist-only header closure");
        } catch (...) { s.exception = std::current_exception(); }
    }
    void finish_closure() {
        for (const auto& capability:scope.capabilities) {
            if (!capability_uses.count(capability.field))
                issue("stale-capability",{},capability.field,"declared named callback site was not observed",true);
            for (const auto* required:{&capability.target,&capability.runtime_guard}) {
                const auto found=std::find_if(identities.begin(),identities.end(),[&](const auto& entry){return entry.second==*required && function_definitions.count(entry.first);});
                if (found==identities.end()) issue("unchecked-capability",{},*required,"named capability target/guard has no checked body",true);
            }
            result.checked_capabilities.push_back(capability.field+" -> "+capability.target);
        }
        std::set<std::string> active = roots;
        std::vector<std::string> queue(active.begin(), active.end());
        for (std::size_t i = 0; i < queue.size(); ++i) {
            const auto next = edges.find(queue[i]);
            if (next != edges.end()) for (const auto& target : next->second)
                if (active.insert(target).second) queue.push_back(target);
        }
        for (const auto& id : function_definitions) result.checked_bodies += active.count(id);
        for (const auto& [id, count] : references) if (id.empty() || active.count(id)) result.checked_references += count;
        for (const auto& f : deferred) if (active.count(f.owner)) result.findings.push_back(f.finding);
        for (const auto& p : pending) if ((p.owner.empty() || active.count(p.owner)) && !definitions.count(p.usr))
            issue("unchecked-helper", p.site, p.entity, "no compiler-resolved body in the reviewed closure (" + p.usr + ")", true);
    }
};
void validate_arguments(const std::vector<std::string>& args) {
    for (std::size_t i = 0; i < args.size(); ++i) {
        const auto& a = args[i];
        if (a == "-I" || a == "-isystem" || a == "-iquote" || a == "-D" || a == "-U" || a == "-isysroot" || a == "-resource-dir" || a == "-target") {
            if (++i == args.size() || args[i].empty() || args[i][0] == '@' || args[i][0] == '-')
                throw std::runtime_error("missing/opaque argument after " + a);
            continue;
        }
        if ((a.size() > 2 && (starts(a, "-I") || starts(a, "-D") || starts(a, "-U"))) ||
            starts(a, "-stdlib=") || starts(a, "-mmacosx-version-min=") || starts(a, "-march=") || starts(a, "-mcpu=") ||
            a == "-O0" || a == "-O1" || a == "-O2" || a == "-O3" || a == "-Os" || a == "-Oz" || a == "-Og" ||
            a == "-pthread" || a == "-fPIC" || a == "-fpic" || a == "-fPIE" || a == "-fpie") continue;
        throw std::runtime_error("unsupported purity front-end argument: " + a);
    }
}
} // namespace

static AuthoringPurityResult inspect_authoring_purity(const std::filesystem::path& input_root,
    const AuthoringPurityScope& scope, const std::vector<AuthoringPurityCommand>& commands,
    const AuthoringPurityOptions& options, bool full_census) {
    AuthoringPurityResult result;
    try {
        const auto root = std::filesystem::canonical(input_root);
        Api api(options.libclang); result.compiler = api.text(api.getClangVersion());
        Scanner scanner(api, root, scope, result);
        scanner.full_census = full_census;
        for (const auto& directory : options.system_include_directories) {
            const auto dir = fs::canonical(directory);
            if (!fs::is_directory(dir) || !fs::path(source_path(root, dir)).is_absolute())
                throw std::runtime_error("toolchain include directory must be outside the source root: " + directory);
            scanner.system_roots.push_back(dir);
        }
        std::set<std::string> supplied;
        for (const auto& command : commands) {
            checked_path(root, command.file); validate_arguments(command.arguments);
            if (!supplied.insert(command.file).second) throw std::runtime_error("duplicate compile command: " + command.file);
        }
        for (const auto& unit : scope.units) if (!supplied.count(unit))
            scanner.issue("missing-command", {unit, 0, 0}, {}, "checked authoring unit has no compiler command");
        for (const auto& unit : scope.providers) if (!supplied.count(unit))
            scanner.issue("missing-command", {unit, 0, 0}, {}, "shared provider has no compiler command");
        for (const auto& dir : scope.census_roots) {
            checked_path(root, dir, true);
            if (!full_census) continue;
            for (const auto& entry : std::filesystem::recursive_directory_iterator(root / dir))
                if (entry.is_regular_file() && cpp(entry.path())) {
                    const auto f = source_path(root, entry.path());
                    if (!supplied.count(f)) scanner.issue("missing-command", {f, 0, 0}, {}, "C++ source escaped the constructor census");
                }
        }
        void* index = api.createIndex(0, 0);
        if (!index) throw std::runtime_error("libclang could not create an index");
        struct IndexOwner { Api& api; void* value; ~IndexOwner() { api.disposeIndex(value); } } index_owner{api, index};
        for (const auto& command : commands) {
            scanner.main_file = command.file;
            scanner.audit = scanner.units.count(command.file) != 0 || scanner.providers.count(command.file) != 0;
            if (!full_census && !scanner.audit) continue;
            scanner.visited_definitions.clear();
            scanner.file_paths.clear();
            std::vector<std::string> flags = {"-x", "c++", "-std=c++17", "-ffp-contract=off", "-fno-modules"};
            for (const auto& dir : scanner.system_roots) { flags.push_back("-isystem"); flags.push_back(dir.string()); }
            flags.insert(flags.end(), command.arguments.begin(), command.arguments.end());
            std::vector<const char*> argv; for (const auto& f : flags) argv.push_back(f.c_str());
            void* tu = nullptr;
            // DetailedPreprocessingRecord=1. Census-only bodies also must parse:
            // skipping them loses auto-return deduction and constructor census.
            const auto error = api.parseTranslationUnit2(index, (root / command.file).c_str(), argv.data(),
                static_cast<int>(argv.size()), nullptr, 0, 1U, &tu);
            struct TuOwner { Api& api; void* value; ~TuOwner() { if (value) api.disposeTranslationUnit(value); } } tu_owner{api, tu};
            if (error || !tu) {
                scanner.issue("compiler-failure", {command.file, 0, 0}, {}, "libclang parse error " + std::to_string(error)); continue;
            }
            ++result.parsed_units;
            scanner.translation_unit = tu;
            bool errors = false;
            for (unsigned i = 0; i < api.getNumDiagnostics(tu); ++i) {
                void* d = api.getDiagnostic(tu, i);
                if (api.getDiagnosticSeverity(d) >= 3) {
                    errors = true;
                    scanner.issue("compiler-error", scanner.site(api.getDiagnosticLocation(d)), {}, api.text(api.formatDiagnostic(d, 3)));
                }
                api.disposeDiagnostic(d);
            }
            api.getInclusions(tu, Scanner::inclusion, &scanner);
            if (scanner.exception) std::rethrow_exception(scanner.exception);
            if (!errors) scanner.children(api.getTranslationUnitCursor(tu));
        }
        scanner.finish_closure();
        for (const auto& key : scope.constructors) if (!scanner.seen_constructors.count(key))
            scanner.issue("stale-constructor", {}, key, "registered compiler identity was not observed");
        for (const auto& key : scope.constructors) if (scanner.seen_constructors.count(key) && !scanner.defined_constructors.count(key))
            scanner.issue("unchecked-constructor", {}, key, "no checked constructor definition was observed");
        for (const auto& key : scope.infrastructure) if (full_census && !scanner.seen_constructors.count(key))
            scanner.issue("stale-classification", {}, key, "infrastructure compiler identity was not observed");
        // Compare actual compiler buffers, not source hashes used as success
        // waivers. This detects edits during a long audit or between TUs.
        for (const auto& [file, bytes] : scanner.input_bytes) {
            std::ifstream input(root / file, std::ios::binary);
            const std::string current{std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
            if (!input || current != bytes) scanner.issue("source-changed", {file, 0, 0}, {}, "disk bytes no longer match compiler evidence");
        }
        if (full_census) for (const auto& dir : scope.census_roots)
            for (const auto& entry : std::filesystem::recursive_directory_iterator(root / dir))
                if (entry.is_regular_file() && cpp(entry.path()) && !supplied.count(source_path(root, entry.path())))
                    scanner.issue("missing-command", {source_path(root, entry.path()), 0, 0}, {}, "C++ source escaped the constructor census");
    } catch (const std::exception& e) {
        result.findings.push_back({"incomplete-evidence", {}, {}, e.what(), 0, 0});
    }
    std::sort(result.constructor_census.begin(), result.constructor_census.end());
    std::sort(result.included_project_headers.begin(), result.included_project_headers.end());
    std::sort(result.findings.begin(), result.findings.end(), [](const auto& a, const auto& b) {
        return std::tie(a.file, a.line, a.column, a.code, a.entity, a.detail) <
               std::tie(b.file, b.line, b.column, b.code, b.entity, b.detail);
    });
    return result;
}
AuthoringPurityResult check_authoring_purity(const std::filesystem::path& root,
    const AuthoringPurityScope& scope, const std::vector<AuthoringPurityCommand>& commands,
    const AuthoringPurityOptions& options) {
    return inspect_authoring_purity(root, scope, commands, options, true);
}
AuthoringPurityResult check_authoring_purity_closure(const std::filesystem::path& root,
    const AuthoringPurityScope& scope, const std::vector<AuthoringPurityCommand>& commands,
    const AuthoringPurityOptions& options) {
    return inspect_authoring_purity(root, scope, commands, options, false);
}
std::string AuthoringPurityResult::report() const {
    std::ostringstream out;
    out << (ok() ? "PASS" : "FAIL") << " native authoring source purity: " << parsed_units << " units, "
        << checked_bodies << " bodies, " << checked_references << " references, " << findings.size() << " findings\n";
    out << "compiler: " << (compiler.empty() ? "unavailable" : compiler) << '\n';
    if (!checked_capabilities.empty()) {
        out << "native context: " << (native_context_verified ? "actual callback targets/owner verified" : "source-only inspection; runtime context precondition not executed") << '\n';
        for (const auto& capability:checked_capabilities) out << "capability: " << capability << '\n';
    }
    for (const auto& f : findings) out << f.file << ':' << f.line << ':' << f.column << " [" << f.code << "] "
        << f.entity << ": " << f.detail << '\n';
    return out.str();
}
} // namespace schgen
