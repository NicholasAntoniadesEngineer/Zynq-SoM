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
void native_package_name(const std::string& name) {
    if(name.empty()||name.front()=='.'||name.front()=='_'||name.find_first_of("/\\")!=std::string::npos)
        throw CircuitAuthoringError("invalid native package name "+repr(name));
}
template<class T> std::set<std::string> native_package_names(const fs::path& root,const std::vector<T>& factories) {
    std::set<std::string> names;
    for(const auto& f:factories) {
        native_package_name(f.name);
        if(!names.insert(f.name).second)throw CircuitAuthoringError("duplicate authoring factory "+repr(f.name));
    }
    for(const auto& p:children(root)) {
        const auto name=p.filename().string();
        if(fs::is_directory(p)&&!model_checks::starts(name,".")&&!model_checks::starts(name,"_")&&!sync_duplicate(p))
            names.insert(name);
    }
    return names;
}
void native_companion(const fs::path& path,const CircuitSheetIr& built,std::vector<std::string>& errors) {
    const auto companion=load_circuit_json(path);
    if(!authoring_json_equal(authored_circuit_json(companion),authored_circuit_json(built)))
        errors.push_back("circuit.json differs from the native authoring factory");
}
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
bool SubsystemStructureResult::ok() const {
    return (mode==AuthoringPackageMode::legacy_python||!packages.empty())&&
        std::all_of(packages.begin(),packages.end(),[](const auto& p){return p.ok();});
}
std::size_t SubsystemStructureResult::n_ok() const {return std::count_if(packages.begin(),packages.end(),[](const auto& p){return p.ok();});}
bool CarrierPackageReport::ok() const {return missing.empty()&&errors.empty()&&has_circuit&&(!adapter||has_meta);}
bool CarrierStructureResult::ok() const {return !packages.empty()&&std::all_of(packages.begin(),packages.end(),[](const auto& p){return p.ok();});}
std::size_t CarrierStructureResult::n_ok() const {return std::count_if(packages.begin(),packages.end(),[](const auto& p){return p.ok();});}
std::size_t CarrierStructureResult::n_adapters() const {return std::count_if(packages.begin(),packages.end(),[](const auto& p){return p.adapter;});}
std::size_t CarrierStructureResult::n_locals() const {return packages.size()-n_adapters();}
std::vector<std::string> subsystem_required_files(const std::string& name,AuthoringPackageMode mode) {
    if(mode==AuthoringPackageMode::native_assets)return {"README.md",name+".cir"};
    return {name+".py","README.md","test_"+name+".py",name+".cir"};
}
std::vector<std::string> carrier_required_files(const std::string& name,bool adapter,AuthoringPackageMode mode) {
    if(mode==AuthoringPackageMode::native_assets) {
        if(adapter)return {"circuit.json"};
        return {"circuit.json","README.md",name+".cir"};
    }
    if(adapter)return {name+".py","test_"+name+".py"};
    return {name+".py","__init__.py","README.md","test_"+name+".py",name+".cir"};
}
SubsystemPackageReport check_subsystem_package(const std::string& name,const fs::path& library,const SubsystemPackageFactory* factory,AuthoringPackageMode mode) {
    SubsystemPackageReport r;r.name=name;r.path=library/name;
    const bool native=mode==AuthoringPackageMode::native_assets;
    if(native)native_package_name(name);
    for(const auto& file:subsystem_required_files(name,mode))
        if(!(native?fs::is_regular_file(r.path/file):fs::exists(r.path/file)))r.missing.push_back(file);
    if(!factory){r.errors.push_back("native authoring factory unavailable: "+name);return r;}
    if(factory->name!=name)throw CircuitAuthoringError("subsystem factory name mismatch");
    r.has_circuit=bool(factory->circuit_meta)||bool(factory->circuit);
    if(!r.has_circuit)return r;
    r.accepts_meta=bool(factory->circuit_meta);r.declared_interface=factory->interface;
    CircuitSheetIr c;
    try {
        c=factory->circuit_meta?factory->circuit_meta(SubsystemMeta{}):factory->circuit();
        if(native) {
            c=parse_circuit_ir(authored_circuit_json(c));
            if(c.name!=name)r.errors.push_back("native circuit name does not match package name");
            if(fs::exists(r.path/"circuit.json"))native_companion(r.path/"circuit.json",c,r.errors);
            const std::set<std::string> unique(r.declared_interface.begin(),r.declared_interface.end());
            if(unique.size()!=r.declared_interface.size())r.errors.push_back("duplicate name in native INTERFACE");
        }
    }
    catch(const std::exception& e){r.errors.push_back("circuit() build failed: "+error(e));return r;}
    std::set<std::string> external,declared(r.declared_interface.begin(),r.declared_interface.end());
    for(const auto& n:c.nets)if(n.net_class!="signal")external.insert(n.name);
    if(!declared.empty()) {
        for(const auto& n:external)if(!declared.count(n))r.interface_drift.push_back("net "+repr(n)+" is an external but not in the declared INTERFACE");
        for(const auto& n:declared)if(!external.count(n))r.interface_drift.push_back("INTERFACE name "+repr(n)+" is not an external net of the built circuit");
    }
    return r;
}
SubsystemStructureResult check_subsystem_structure(const fs::path& library,const std::vector<SubsystemPackageFactory>& factories,AuthoringPackageMode mode) {
    SubsystemStructureResult r;r.mode=mode;
    if(mode==AuthoringPackageMode::native_assets) {
        for(const auto& name:native_package_names(library,factories))
            r.packages.push_back(check_subsystem_package(name,library,factory_for(factories,name),mode));
        return r;
    }
    for(const auto& p:children(library))if(fs::is_directory(p)&&fs::exists(p/"__init__.py")&&!model_checks::starts(p.filename().string(),"_")) {
        const auto name=p.filename().string();r.packages.push_back(check_subsystem_package(name,library,factory_for(factories,name),mode));
    }
    return r;
}
CarrierPackageReport check_carrier_package(const std::string& name,const fs::path& base,const fs::path& library,const CarrierPackageFactory* factory,AuthoringPackageMode mode) {
    CarrierPackageReport r;r.name=name;r.path=base/name;r.adapter=fs::is_directory(library/name);
    if(mode==AuthoringPackageMode::native_assets) {
        native_package_name(name);
        // Metadata declares an adapter even if its library folder was removed.
        // Never silently reclassify such an incomplete adapter as a local.
        r.adapter=r.adapter||(factory&&factory->meta.has_value());
        for(const auto& file:carrier_required_files(name,r.adapter,mode))
            if(!fs::is_regular_file(r.path/file))r.missing.push_back(file);
        if(r.adapter)for(const auto& file:subsystem_required_files(name,mode))
            if(!fs::is_regular_file(library/name/file))r.missing.push_back("library/"+name+"/"+file);
        if(!factory){r.errors.push_back("native authoring factory unavailable: "+name);return r;}
        if(factory->name!=name)throw CircuitAuthoringError("carrier factory name mismatch");
        r.has_circuit=bool(factory->circuit);r.has_meta=factory->meta&&factory->meta->kind==JsonKind::Object;
        try {
            if(r.adapter&&r.has_meta)(void)SubsystemMeta(*factory->meta);
            if(r.has_circuit) {
                const auto c=parse_circuit_ir(authored_circuit_json(factory->circuit()));
                if(c.name!=name)r.errors.push_back("native circuit name does not match package name");
                if(fs::is_regular_file(r.path/"circuit.json"))native_companion(r.path/"circuit.json",c,r.errors);
            }
        } catch(const std::exception& e){r.errors.push_back(error(e));}
        return r;
    }
    auto netlist=r.adapter?base/(name+".py"):base/name/(name+".py");
    if(r.adapter) {
        r.path=netlist;
        for(const auto& file:carrier_required_files(name,true,mode))if(!fs::exists(base/file))r.missing.push_back(file);
        if(fs::is_directory(base/name)) {
            std::vector<std::string> entries;
            for(const auto& p:children(base/name))if(!sync_duplicate(p))entries.push_back(p.filename().string());
            if(entries!=std::vector<std::string>{"circuit.json"})r.missing.push_back(name+"/ (adapter companion must contain only circuit.json)");
        }
    } else {
        if(!fs::is_directory(r.path))r.missing.push_back(name+"/ (local must be a foldered package)");
        for(const auto& file:carrier_required_files(name,false,mode))if(!fs::exists(r.path/file))r.missing.push_back(file);
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
CarrierStructureResult check_carrier_structure(const fs::path& base,const fs::path& library,const std::vector<CarrierPackageFactory>& factories,AuthoringPackageMode mode) {
    if(mode==AuthoringPackageMode::native_assets) {
        CarrierStructureResult r;r.mode=mode;
        for(const auto& name:native_package_names(base,factories))
            r.packages.push_back(check_carrier_package(name,base,library,factory_for(factories,name),mode));
        return r;
    }
    std::set<std::string> names;
    for(const auto& p:children(base)) {
        const auto name=p.filename().string();
        if(model_checks::starts(name,".")||model_checks::starts(name,"_"))continue;
        if(fs::is_directory(p))names.insert(name);
        else if(p.extension()==".py"&&!model_checks::starts(name,"test_")&&p.stem()!="__init__")names.insert(p.stem().string());
    }
    CarrierStructureResult r;r.mode=mode;
    for(const auto& name:names)r.packages.push_back(check_carrier_package(name,base,library,factory_for(factories,name),mode));
    return r;
}
std::string SubsystemStructureResult::summary() const {
    const bool native=mode==AuthoringPackageMode::native_assets;
    std::vector<std::string> lines={"schgen subsystem-structure gate (REPORT-FIRST)",std::string(60,'='),"",
        "contract: each subsystems/<name>/ is a self-contained, project-agnostic package with",
        "  <name>.py (abstract-port netlist + circuit(meta=)) + README.md + test_<name>.py + <name>.cir,",
        "  and a declared abstract INTERFACE that matches the netlist's externals.",""};
    if(native)lines={"schgen subsystem-structure gate (NATIVE HARD)",std::string(60,'='),"",
        "contract: each native library package has README.md + <name>.cir,",
        "  a registered parameterized circuit factory and a matching abstract INTERFACE.",
        "  Optional circuit.json must match the live factory; Python files are not required.",""};
    if(packages.empty())lines.push_back("(no subsystems/ packages found)");
    for(const auto& p:packages) {
        lines.push_back(p.name+": "+(p.ok()?"OK":"INCOMPLETE"));
        if(!p.missing.empty())lines.push_back("  missing files: "+join(p.missing));
        if(!p.has_circuit)lines.push_back(native?"  no native circuit factory":"  no top-level circuit()");
        else if(!p.accepts_meta)lines.push_back(native?"  native factory does not accept metadata":"  circuit() does not accept a meta= argument");
        if(p.declared_interface.empty()&&p.has_circuit)lines.push_back("  no declared INTERFACE (abstract port/rail names)");
        for(const auto& d:p.interface_drift)lines.push_back("  interface drift: "+d);
        for(const auto& e:p.errors)lines.push_back("  error: "+e);
        if(!p.declared_interface.empty())lines.push_back("  interface ("+std::to_string(p.declared_interface.size())+"): "+join(p.declared_interface));
    }
    lines.push_back("");lines.push_back("SUBSYSTEM STRUCTURE: "+std::to_string(n_ok())+"/"+std::to_string(packages.size())+" package(s) complete ("+(ok()?"PASS":native?"FAIL":"REPORT")+")");
    return join(lines,"\n");
}
std::string CarrierStructureResult::summary() const {
    const bool native=mode==AuthoringPackageMode::native_assets;
    std::vector<std::string> lines={"schgen carrier-structure gate (HARD)",std::string(60,'='),"",
        "contract: each carrier subsystem matches the SHAPE its kind requires —",
        "  ADAPTER (has a generic subsystems/<name>/ library): FLAT <name>.py + test_<name>.py",
        "           (NOT foldered) with a callable circuit() + a META dict.",
        "           An IR-only <name>/circuit.json companion must match circuit() exactly.",
        "  LOCAL  (no generic library): foldered <name>/ with <name>.py + __init__.py +",
        "           README.md + test_<name>.py + <name>.cir and a callable circuit().",""};
    if(native)lines={"schgen carrier-structure gate (NATIVE HARD)",std::string(60,'='),"",
        "contract: every project package has circuit.json matching its live native factory.",
        "  ADAPTER: native metadata plus the generic library's README.md and <name>.cir.",
        "  LOCAL: package-local README.md and <name>.cir. Python files are not required.",""};
    for(const auto& p:packages)if(!p.ok()) {
        lines.push_back(p.name+" ["+p.kind()+"]: INCOMPLETE");
        if(!p.missing.empty())lines.push_back("  missing: "+join(p.missing));
        if(!p.has_circuit)lines.push_back(native?"  no native circuit factory":"  no callable circuit()");
        if(p.adapter&&p.has_circuit&&!p.has_meta)lines.push_back(native?"  adapter missing native metadata":"  adapter missing a META dict");
        for(const auto& e:p.errors)lines.push_back("  error: "+e);
    }
    lines.push_back("CARRIER STRUCTURE: "+std::to_string(n_ok())+"/"+std::to_string(packages.size())+
        " subsystem(s) complete ("+std::to_string(n_adapters())+(native?" native adapter(s) + ":" flat adapter(s) + ")+std::to_string(n_locals())+
        (native?" native local(s)) (":" foldered local(s)) (")+(ok()?"PASS":"FAIL")+")");return join(lines,"\n");
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
    auto out=obj({{"packages",packages},{"ok",j(r.ok())},{"n_ok",j(double(r.n_ok()))},{"summary",j(r.summary())}});
    if(r.mode==AuthoringPackageMode::native_assets)out.object_value.emplace_back("package_mode",j("native_assets"));
    return out;
}
JsonNode carrier_structure_json(const CarrierStructureResult& r) {
    using namespace model_checks;
    auto packages=arr();
    for(const auto& p:r.packages)packages.array_value.push_back(obj({{"name",j(p.name)},{"path",j(p.path.string())},
        {"adapter",j(p.adapter)},{"missing",strings(p.missing)},{"has_circuit",j(p.has_circuit)},
        {"has_meta",j(p.has_meta)},{"errors",strings(p.errors)},{"ok",j(p.ok())},{"kind",j(p.kind())}}));
    auto out=obj({{"packages",packages},{"ok",j(r.ok())},{"n_ok",j(double(r.n_ok()))},
        {"n_adapters",j(double(r.n_adapters()))},{"n_locals",j(double(r.n_locals()))},{"summary",j(r.summary())}});
    if(r.mode==AuthoringPackageMode::native_assets)out.object_value.emplace_back("package_mode",j("native_assets"));
    return out;
}
} // namespace schgen
