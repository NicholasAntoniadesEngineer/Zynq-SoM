#include "schgen/authoring_gates.hpp"
#include "schgen/atomic_file.hpp"
#include "model_checks_internal.hpp"

namespace schgen {
namespace {
namespace fs = std::filesystem;
using model_checks::repr;
std::string join(const std::vector<std::string>& items,const std::string& sep=", ") {
    std::string out;for(const auto& s:items){if(!out.empty())out+=sep;out+=s;}return out;
}
std::vector<fs::path> children(const fs::path& path) {
    std::vector<fs::path> out;
    if(fs::is_directory(path))for(const auto& entry:fs::directory_iterator(path))out.push_back(entry.path());
    std::sort(out.begin(),out.end());return out;
}
template<class T> const T* factory_for(const std::vector<T>& entries,const std::string& name) {
    const T* result=nullptr;
    for(const auto& entry:entries)if(entry.name==name){if(result)throw CircuitAuthoringError("duplicate authoring factory "+repr(name));result=&entry;}
    return result;
}
std::string error(const std::exception& e) {
    return std::string(dynamic_cast<const CircuitAuthoringError*>(&e)?"CircuitError: ":"RuntimeError: ")+e.what();
}
bool sync_duplicate(const fs::path& p) {return std::regex_search(p.stem().string(),std::regex(R"( [0-9]+$)"));}
}
std::vector<SubsystemPackageFactory> native_subsystem_factories(const AuthoringContext& context) {
    std::vector<SubsystemPackageFactory> out;
    for(const auto& d:subsystem_definitions())out.push_back({d.name,d.interface,[build=d.circuit,context](const SubsystemMeta& meta){return build(meta,context);},{}});
    return out;
}
CarrierPackageFactory native_subsystem_adapter(const std::string& name,const JsonNode& meta,const AuthoringContext& context) {
    // Defer parsing/build errors until gate evaluation, as for a Python module.
    return {name,[name,meta,context]{return author_subsystem(name,SubsystemMeta(meta),context);},meta};
}
bool SubsystemPackageReport::ok() const {
    return missing.empty()&&interface_drift.empty()&&errors.empty()&&has_circuit&&accepts_meta&&!declared_interface.empty();
}
bool SubsystemStructureResult::ok() const {return std::all_of(packages.begin(),packages.end(),[](const auto& p){return p.ok();});}
std::size_t SubsystemStructureResult::n_ok() const {return std::count_if(packages.begin(),packages.end(),[](const auto& p){return p.ok();});}
bool CarrierPackageReport::ok() const {return missing.empty()&&errors.empty()&&has_circuit&&(!adapter||has_meta);}
bool CarrierStructureResult::ok() const {return !packages.empty()&&std::all_of(packages.begin(),packages.end(),[](const auto& p){return p.ok();});}
std::size_t CarrierStructureResult::n_ok() const {return std::count_if(packages.begin(),packages.end(),[](const auto& p){return p.ok();});}
std::size_t CarrierStructureResult::n_adapters() const {return std::count_if(packages.begin(),packages.end(),[](const auto& p){return p.adapter;});}
std::size_t CarrierStructureResult::n_locals() const {return packages.size()-n_adapters();}
std::vector<std::string> subsystem_required_files(const std::string& name) {return {name+".py","README.md","test_"+name+".py",name+".cir"};}
std::vector<std::string> carrier_required_files(const std::string& name,bool adapter) {
    if(adapter)return {name+".py","test_"+name+".py"};
    return {name+".py","__init__.py","README.md","test_"+name+".py",name+".cir"};
}
SubsystemPackageReport check_subsystem_package(const std::string& name,const fs::path& library,const SubsystemPackageFactory* factory) {
    SubsystemPackageReport r;r.name=name;r.path=library/name;
    for(const auto& file:subsystem_required_files(name))if(!fs::exists(r.path/file))r.missing.push_back(file);
    if(!factory){r.errors.push_back("native authoring factory unavailable: "+name);return r;}
    if(factory->name!=name)throw CircuitAuthoringError("subsystem factory name mismatch");
    r.has_circuit=bool(factory->circuit_meta)||bool(factory->circuit);
    if(!r.has_circuit)return r;
    r.accepts_meta=bool(factory->circuit_meta);r.declared_interface=factory->interface;
    CircuitSheetIr c;
    try {c=factory->circuit_meta?factory->circuit_meta(SubsystemMeta{}):factory->circuit();}
    catch(const std::exception& e){r.errors.push_back("circuit() build failed: "+error(e));return r;}
    std::set<std::string> external,declared(r.declared_interface.begin(),r.declared_interface.end());
    for(const auto& n:c.nets)if(n.net_class!="signal")external.insert(n.name);
    if(!declared.empty()) {
        for(const auto& n:external)if(!declared.count(n))r.interface_drift.push_back("net "+repr(n)+" is an external but not in the declared INTERFACE");
        for(const auto& n:declared)if(!external.count(n))r.interface_drift.push_back("INTERFACE name "+repr(n)+" is not an external net of the built circuit");
    }
    return r;
}
SubsystemStructureResult check_subsystem_structure(const fs::path& library,const std::vector<SubsystemPackageFactory>& factories) {
    SubsystemStructureResult r;
    for(const auto& p:children(library))if(fs::is_directory(p)&&fs::exists(p/"__init__.py")&&!model_checks::starts(p.filename().string(),"_")) {
        const auto name=p.filename().string();r.packages.push_back(check_subsystem_package(name,library,factory_for(factories,name)));
    }
    return r;
}
CarrierPackageReport check_carrier_package(const std::string& name,const fs::path& base,const fs::path& library,const CarrierPackageFactory* factory) {
    CarrierPackageReport r;r.name=name;r.path=base/name;r.adapter=fs::is_directory(library/name);
    auto netlist=r.adapter?base/(name+".py"):base/name/(name+".py");
    if(r.adapter) {
        r.path=netlist;
        for(const auto& file:carrier_required_files(name,true))if(!fs::exists(base/file))r.missing.push_back(file);
        if(fs::is_directory(base/name)) {
            std::vector<std::string> entries;
            for(const auto& p:children(base/name))if(!sync_duplicate(p))entries.push_back(p.filename().string());
            if(entries!=std::vector<std::string>{"circuit.json"})r.missing.push_back(name+"/ (adapter companion must contain only circuit.json)");
        }
    } else {
        if(!fs::is_directory(r.path))r.missing.push_back(name+"/ (local must be a foldered package)");
        for(const auto& file:carrier_required_files(name,false))if(!fs::exists(r.path/file))r.missing.push_back(file);
    }
    if(!fs::exists(netlist))return r;
    if(!factory){r.errors.push_back("native authoring factory unavailable: "+name);return r;}
    if(factory->name!=name)throw CircuitAuthoringError("carrier factory name mismatch");
    r.has_circuit=bool(factory->circuit);r.has_meta=factory->meta&&factory->meta->kind==JsonKind::Object;
    if(r.has_circuit) {
        try {
            const auto c=factory->circuit();
            if(r.adapter&&fs::is_directory(base/name)) {
                const auto companion=load_circuit_json(base/name/"circuit.json");
                if(!authoring_json_equal(authored_circuit_json(companion),authored_circuit_json(c)))
                    r.errors.push_back("circuit.json differs from the adapter netlist");
            }
        }catch(const std::exception& e){r.errors.push_back(error(e));}
    }
    return r;
}
CarrierStructureResult check_carrier_structure(const fs::path& base,const fs::path& library,const std::vector<CarrierPackageFactory>& factories) {
    std::set<std::string> names;
    for(const auto& p:children(base)) {
        const auto name=p.filename().string();
        if(model_checks::starts(name,".")||model_checks::starts(name,"_"))continue;
        if(fs::is_directory(p))names.insert(name);
        else if(p.extension()==".py"&&!model_checks::starts(name,"test_")&&p.stem()!="__init__")names.insert(p.stem().string());
    }
    CarrierStructureResult r;
    for(const auto& name:names)r.packages.push_back(check_carrier_package(name,base,library,factory_for(factories,name)));
    return r;
}
std::string SubsystemStructureResult::summary() const {
    std::vector<std::string> lines={"schgen subsystem-structure gate (REPORT-FIRST)",std::string(60,'='),"",
        "contract: each subsystems/<name>/ is a self-contained, project-agnostic package with",
        "  <name>.py (abstract-port netlist + circuit(meta=)) + README.md + test_<name>.py + <name>.cir,",
        "  and a declared abstract INTERFACE that matches the netlist's externals.",""};
    if(packages.empty())lines.push_back("(no subsystems/ packages found)");
    for(const auto& p:packages) {
        lines.push_back(p.name+": "+(p.ok()?"OK":"INCOMPLETE"));
        if(!p.missing.empty())lines.push_back("  missing files: "+join(p.missing));
        if(!p.has_circuit)lines.push_back("  no top-level circuit()");
        else if(!p.accepts_meta)lines.push_back("  circuit() does not accept a meta= argument");
        if(p.declared_interface.empty()&&p.has_circuit)lines.push_back("  no declared INTERFACE (abstract port/rail names)");
        for(const auto& d:p.interface_drift)lines.push_back("  interface drift: "+d);
        for(const auto& e:p.errors)lines.push_back("  error: "+e);
        if(!p.declared_interface.empty())lines.push_back("  interface ("+std::to_string(p.declared_interface.size())+"): "+join(p.declared_interface));
    }
    lines.push_back("");lines.push_back("SUBSYSTEM STRUCTURE: "+std::to_string(n_ok())+"/"+std::to_string(packages.size())+" package(s) complete ("+(ok()?"PASS":"REPORT")+")");
    return join(lines,"\n");
}
std::string CarrierStructureResult::summary() const {
    std::vector<std::string> lines={"schgen carrier-structure gate (HARD)",std::string(60,'='),"",
        "contract: each carrier subsystem matches the SHAPE its kind requires —",
        "  ADAPTER (has a generic subsystems/<name>/ library): FLAT <name>.py + test_<name>.py",
        "           (NOT foldered) with a callable circuit() + a META dict.",
        "           An IR-only <name>/circuit.json companion must match circuit() exactly.",
        "  LOCAL  (no generic library): foldered <name>/ with <name>.py + __init__.py +",
        "           README.md + test_<name>.py + <name>.cir and a callable circuit().",""};
    for(const auto& p:packages)if(!p.ok()) {
        lines.push_back(p.name+" ["+p.kind()+"]: INCOMPLETE");
        if(!p.missing.empty())lines.push_back("  missing: "+join(p.missing));
        if(!p.has_circuit)lines.push_back("  no callable circuit()");
        if(p.adapter&&p.has_circuit&&!p.has_meta)lines.push_back("  adapter missing a META dict");
        for(const auto& e:p.errors)lines.push_back("  error: "+e);
    }
    lines.push_back("CARRIER STRUCTURE: "+std::to_string(n_ok())+"/"+std::to_string(packages.size())+
        " subsystem(s) complete ("+std::to_string(n_adapters())+" flat adapter(s) + "+std::to_string(n_locals())+
        " foldered local(s)) ("+(ok()?"PASS":"FAIL")+")");return join(lines,"\n");
}
void write_authoring_gate_report(const fs::path& path,const std::string& summary) {
    if(!path.parent_path().empty())fs::create_directories(path.parent_path());
    const auto bytes=summary+"\n";
    write_atomic_file(path.string(),std::vector<uint8_t>(bytes.begin(),bytes.end()));
}
JsonNode subsystem_structure_json(const SubsystemStructureResult& r) {
    using namespace model_checks;
    auto packages=arr();
    for(const auto& p:r.packages)packages.array_value.push_back(obj({{"name",j(p.name)},{"path",j(p.path.string())},
        {"missing",strings(p.missing)},{"has_circuit",j(p.has_circuit)},{"accepts_meta",j(p.accepts_meta)},
        {"declared_interface",strings(p.declared_interface)},{"interface_drift",strings(p.interface_drift)},
        {"errors",strings(p.errors)},{"ok",j(p.ok())}}));
    return obj({{"packages",packages},{"ok",j(r.ok())},{"n_ok",j(double(r.n_ok()))},{"summary",j(r.summary())}});
}
JsonNode carrier_structure_json(const CarrierStructureResult& r) {
    using namespace model_checks;
    auto packages=arr();
    for(const auto& p:r.packages)packages.array_value.push_back(obj({{"name",j(p.name)},{"path",j(p.path.string())},
        {"adapter",j(p.adapter)},{"missing",strings(p.missing)},{"has_circuit",j(p.has_circuit)},
        {"has_meta",j(p.has_meta)},{"errors",strings(p.errors)},{"ok",j(p.ok())},{"kind",j(p.kind())}}));
    return obj({{"packages",packages},{"ok",j(r.ok())},{"n_ok",j(double(r.n_ok()))},
        {"n_adapters",j(double(r.n_adapters()))},{"n_locals",j(double(r.n_locals()))},{"summary",j(r.summary())}});
}
} // namespace schgen
