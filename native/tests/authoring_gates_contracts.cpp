#include "schgen/authoring_gates.hpp"
#include "schgen/project_authoring.hpp"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <unistd.h>

namespace {
namespace fs=std::filesystem;
using namespace schgen;
std::size_t checks=0;
void require(bool ok,const std::string& why){++checks;if(!ok)throw std::runtime_error(why);}
const JsonNode& at(const JsonNode& n,const std::string& key){auto p=object_field(n,key);require(p!=nullptr,"missing fixture "+key);return *p;}
void write(const fs::path& p,const std::string& text){fs::create_directories(p.parent_path());std::ofstream out(p,std::ios::binary);out<<text;out.close();require(bool(out),"write fixture "+p.string());}
std::string read(const fs::path& p){std::ifstream in(p,std::ios::binary);require(bool(in),"read "+p.string());return {std::istreambuf_iterator<char>(in),{}};}
struct Scratch {
    fs::path path;
    Scratch(){std::string pattern="/private/tmp/schgen-authoring-gates-XXXXXX";auto p=::mkdtemp(pattern.data());require(p!=nullptr,"mkdtemp");path=p;}
    ~Scratch(){std::error_code ignored;fs::remove_all(path,ignored);}
};
void check_report(const JsonNode& actual,const JsonNode& expected,const fs::path& root) {
    require(at(actual,"summary").string_value==at(expected,"summary").string_value,"Python summary bytes differ");
    const auto& a=at(actual,"packages").array_value;
    const auto& b=at(expected,"packages").array_value;
    require(a.size()==b.size(),"package discovery count differs");
    for(std::size_t i=0;i<a.size();++i)for(const auto& [key,value]:a[i].object_value) {
        auto wanted=at(b[i],key);
        if(key=="path")wanted.string_value=(root/wanted.string_value).string();
        require(authoring_json_equal(value,wanted),"package report differs: "+at(a[i],"name").string_value+"."+key);
    }
}
std::vector<CarrierPackageFactory> project_factories(const fs::path& root,const std::string& project) {
    ProjectAuthoringInput input;input.project_root=root/project;
    return native_project_factories(project,input);
}
void default_mode_contracts(const fs::path& root) {
    constexpr auto native=AuthoringPackageMode::native_assets;
    SubsystemStructureResult library_default;
    CarrierStructureResult carrier_default;
    require(library_default.mode==native&&!library_default.ok()&&library_default.exit_code()==1,
        "default empty library result must fail closed");
    require(carrier_default.mode==native&&!carrier_default.ok()&&carrier_default.exit_code()==1,
        "default empty carrier result must fail closed");
    SubsystemPackageReport bad;bad.errors={"intentional failed package"};
    SubsystemStructureResult failed{{bad}};
    require(!failed.ok()&&failed.exit_code()==1&&failed.exit_code(true)==1,
        "default failed library result must not use report-first exit status");
    require(subsystem_required_files("widget")==std::vector<std::string>{"README.md","widget.cir"},
        "default library requirements retained Python");
    require(carrier_required_files("widget",true)==std::vector<std::string>{"circuit.json"},
        "default adapter requirements retained Python");
    require(carrier_required_files("widget",false)==std::vector<std::string>{"circuit.json","README.md","widget.cir"},
        "default local requirements retained Python");

    Scratch s;const auto empty=s.path/"empty",missing=s.path/"missing";
    fs::create_directories(empty);
    auto libraries=native_subsystem_factories();
    for(const auto& path:{empty,missing}) {
        const auto no_library=check_subsystem_structure(path,{});
        const auto no_project=check_carrier_structure(path,root/"subsystems",{});
        require(no_library.mode==native&&!no_library.ok()&&no_library.exit_code()==1,
            "default empty/missing library accepted");
        require(no_project.mode==native&&!no_project.ok()&&no_project.exit_code()==1,
            "default empty/missing project accepted");
        const auto absent=check_subsystem_structure(path,libraries);
        require(absent.mode==native&&absent.packages.size()==libraries.size()&&!absent.ok()&&absent.exit_code()==1,
            "default discovery lost registered missing library packages");
        for(const auto& package:absent.packages)
            require(!package.missing.empty(),"missing registered library lacks missing-asset diagnostic");
    }
    for(const auto& factory:libraries) {
        require(check_subsystem_package(factory.name,root/"subsystems",&factory).ok(),
            "default real library package failed: "+factory.name);
        const auto absent=check_subsystem_package(factory.name,missing,&factory);
        require(!absent.ok()&&!absent.missing.empty(),"default missing library package accepted");
    }
    for(const auto* project:{"carrier","devkit_mini"}) {
        const auto factories=project_factories(root,project);
        for(const auto& path:{empty,missing}) {
            const auto absent=check_carrier_structure(path,root/"subsystems",factories);
            require(absent.mode==native&&absent.packages.size()==factories.size()&&!absent.ok()&&absent.exit_code()==1,
                "default discovery lost registered missing project packages");
            for(const auto& package:absent.packages)
                require(!package.missing.empty(),"missing registered project lacks missing-asset diagnostic");
        }
        for(const auto& factory:factories) {
            require(check_carrier_package(factory.name,root/project/"subsystems",root/"subsystems",&factory).ok(),
                std::string(project)+": default real project package failed: "+factory.name);
            const auto absent=check_carrier_package(factory.name,missing,root/"subsystems",&factory);
            require(!absent.ok()&&!absent.missing.empty(),"default missing project package accepted");
        }
    }
    require(!fs::exists(missing),"default gate created its missing input directory");
}
// Legacy discovery/report compatibility is tested only in this inert layout.
// No retained .py source is copied, imported, evaluated or required in ROOT.
// The independent oracle selects the population/shape; live native factories
// still construct every circuit. Companion bytes remain independent inputs.
void legacy_reports(const fs::path& root,const JsonNode& library) {
    constexpr auto mode=AuthoringPackageMode::legacy_python;
    const std::string inert="INERT LEGACY LAYOUT MARKER - NOT EXECUTABLE SOURCE\n";
    Scratch s;
    for(const auto& row:at(library,"packages").array_value) {
        const auto name=at(row,"name").string_value;
        const auto base=s.path/"subsystems"/name;
        for(const auto& file:std::vector<std::string>{"__init__.py",name+".py","test_"+name+".py","README.md",name+".cir"})
            write(base/file,inert);
    }
    auto report=check_subsystem_structure(s.path/"subsystems",native_subsystem_factories(),mode);
    require(report.ok()&&report.n_ok()==17,"inert legacy library gate failed: "+report.summary());
    check_report(subsystem_structure_json(report),library,s.path);
    write_authoring_gate_report(s.path/"library-report.txt",report.summary());
    require(read(s.path/"library-report.txt")==at(library,"summary").string_value+"\n","legacy library publication bytes changed");
    for(const auto* project:{"carrier","devkit_mini"}) {
        const auto fixture=parse_json_file((root/"native/tests/data/authoring"/(std::string("gate_")+project+".json")).string());
        const auto base=s.path/project/"subsystems";
        for(const auto& row:at(fixture,"packages").array_value) {
            const auto name=at(row,"name").string_value;
            if(at(row,"adapter").bool_value) {
                write(base/(name+".py"),inert);write(base/("test_"+name+".py"),inert);
                write(base/name/"circuit.json",read(root/project/"subsystems"/name/"circuit.json"));
            } else {
                for(const auto& file:std::vector<std::string>{"__init__.py",name+".py","test_"+name+".py","README.md",name+".cir"})
                    write(base/name/file,inert);
            }
        }
        const auto r=check_carrier_structure(base,s.path/"subsystems",project_factories(root,project),mode);
        require(r.ok(),"inert legacy project gate failed: "+r.summary());
        check_report(carrier_structure_json(r),fixture,s.path);
        write_authoring_gate_report(s.path/(std::string(project)+"-report.txt"),r.summary());
        require(read(s.path/(std::string(project)+"-report.txt"))==at(fixture,"summary").string_value+"\n","legacy project publication bytes changed");
    }
    for(const auto& entry:fs::recursive_directory_iterator(s.path))
        if(entry.path().extension()==".py")require(read(entry.path())==inert,"legacy fixture contains executable source");
}
void mutations(const fs::path& root) {
    constexpr auto mode=AuthoringPackageMode::legacy_python;
    Scratch s;const auto base=s.path/"carrier",lib=s.path/"lib";
    fs::create_directories(lib/"usb_pd");fs::create_directories(base);
    require(!check_carrier_structure(base,lib,{},mode).ok(),"empty carrier must fail");
    require(check_subsystem_structure(lib,{},mode).ok(),"empty discoverable library is report-first PASS");
    auto factories=project_factories(root,"carrier");
    auto it=std::find_if(factories.begin(),factories.end(),[](const auto& x){return x.name=="usb_pd";});
    require(it!=factories.end(),"oracle usb_pd");
    auto f=*it;
    for(const auto& name:carrier_required_files("usb_pd",true,mode))write(base/name,"retained authoring artifact\n");
    auto check=[&]{return check_carrier_package("usb_pd",base,lib,&f,mode);};
    require(check().ok(),"flat adapter without companion must pass");
    fs::create_directories(base/"usb_pd");
    require(!check().ok()&&!check().missing.empty(),"empty companion must fail");
    const auto bytes=read(root/"carrier/subsystems/usb_pd/circuit.json");
    write(base/"usb_pd/circuit.json",bytes);
    require(check().ok(),"independent native adapter must equal JSON companion");
    write(base/"usb_pd/circuit 2.json","bad duplicate deliberately ignored");
    require(check().ok(),"sync duplicate must not add companion code");
    write(base/"usb_pd/hidden.py","unapproved companion code");
    require(!check().ok()&&!check().missing.empty(),"extra companion code accepted");
    fs::remove(base/"usb_pd/hidden.py");
    auto changed=f;changed.circuit=[build=f.circuit]{auto c=build();c.title+=" edited";return c;};
    auto r=check_carrier_package("usb_pd",base,lib,&changed,mode);
    require(r.errors==std::vector<std::string>{"circuit.json differs from the adapter netlist"},"authoring mutation was ignored");
    // A second direction catches gates that compare an IR companion to itself.
    auto bad=bytes;const auto pos=bad.find("USB-PD:");require(pos!=std::string::npos,"title mutation target");bad.insert(pos,"changed ");
    write(base/"usb_pd/circuit.json",bad);require(!check().ok()&&check().errors.size()==1,"companion mutation was ignored");
    write(base/"usb_pd/circuit.json","{");require(!check().errors.empty(),"malformed companion accepted");
    write(base/"usb_pd/circuit.json",bytes);
    changed=f;changed.meta.reset();r=check_carrier_package("usb_pd",base,lib,&changed,mode);
    require(!r.ok()&&r.has_circuit&&!r.has_meta,"missing META accepted");
    changed=f;changed.circuit={};r=check_carrier_package("usb_pd",base,lib,&changed,mode);
    require(!r.ok()&&!r.has_circuit,"missing factory accepted");
    changed=f;changed.circuit=[]()->CircuitSheetIr{throw CircuitAuthoringError("intentional build failure");};
    r=check_carrier_package("usb_pd",base,lib,&changed,mode);require(r.errors==std::vector<std::string>{"CircuitError: intentional build failure"},"factory exception lost");
    require(!check_carrier_package("usb_pd",base,lib,nullptr,mode).ok(),"unregistered authoring accepted");
    fs::remove(base/"test_usb_pd.py");require(check().missing==std::vector<std::string>{"test_usb_pd.py"},"missing adapter test not detected");
    write(base/"widget.py","flat local");
    CarrierPackageFactory local{"widget",[]{CircuitAuthor c("widget");return c.finish();},std::nullopt};
    require(!check_carrier_package("widget",base,lib,&local,mode).ok(),"flat local accepted");
    for(const auto& name:carrier_required_files("widget",false,mode))write(base/"widget"/name,"");
    require(check_carrier_package("widget",base,lib,&local,mode).ok(),"complete foldered local rejected");
    fs::remove(base/"widget/README.md");require(!check_carrier_package("widget",base,lib,&local,mode).ok(),"missing local readme accepted");
    // Library gate uses actual constructor results and declared interfaces.
    const auto pkg=lib/"usb_pd";
    for(const auto& name:subsystem_required_files("usb_pd",mode))write(pkg/name,"");
    write(pkg/"__init__.py","");
    auto libs=native_subsystem_factories();
    auto l=*std::find_if(libs.begin(),libs.end(),[](const auto& x){return x.name=="usb_pd";});
    auto lr=check_subsystem_package("usb_pd",lib,&l,mode);require(lr.ok(),"valid library rejected");
    l.interface.erase(l.interface.begin());l.interface.push_back("BOGUS");lr=check_subsystem_package("usb_pd",lib,&l,mode);
    require(lr.interface_drift==std::vector<std::string>{"net '+VDD_LOGIC' is an external but not in the declared INTERFACE", "INTERFACE name 'BOGUS' is not an external net of the built circuit"},"interface drift not diagnosed");
    SubsystemStructureResult fail{{lr},mode};require(fail.exit_code()==0&&fail.exit_code(true)==1,"report-first/strict policy");
    l.interface.clear();require(!check_subsystem_package("usb_pd",lib,&l,mode).ok(),"empty interface accepted");
    l.circuit=[build=l.circuit_meta]{return build(SubsystemMeta{});};l.circuit_meta={};
    lr=check_subsystem_package("usb_pd",lib,&l,mode);require(lr.has_circuit&&!lr.accepts_meta&&!lr.ok(),"missing meta signature accepted");
    l.circuit=[]()->CircuitSheetIr{throw CircuitAuthoringError("intentional failure");};
    require(check_subsystem_package("usb_pd",lib,&l,mode).errors==std::vector<std::string>{"circuit() build failed: CircuitError: intentional failure"},"library exception report");
    l.circuit={};lr=check_subsystem_package("usb_pd",lib,&l,mode);require(!lr.has_circuit&&!lr.ok(),"no top-level circuit accepted");
    write_authoring_gate_report(s.path/"reports/gate.txt",fail.summary());
    require(read(s.path/"reports/gate.txt")==fail.summary()+"\n","report publication bytes");
    auto rendered=fail.summary();fail.packages[0].errors.push_back("later mutation");
    require(fail.summary()!=rendered,"summary must observe current reports");
}
void connectors(const fs::path& root,const std::string& project) {
    const auto fixture=parse_json_file((root/"native/tests/data/authoring"/("connector_"+project+".json")).string());
    for(const auto& row:at(fixture,"cases").array_value) {
        auto som=load_som_interface(root/project/"som_interface.json");
        auto mapping=link_mapping_from_json(parse_json_file((root/project/"som_mapping.json").string()));
        auto policy=project_connector_policy(project);const auto ref=at(row,"ref").string_value;
        if(auto edits=object_field(row,"pin_edits"))for(auto& [key,c]:som.connectors)if(key==ref)
            for(const auto& [pin,value]:edits->object_value) {
                const auto pin_name=pin;
                auto p=std::find_if(c.pins.begin(),c.pins.end(),[&](const auto& x){return x.first==pin_name;});
                require(p!=c.pins.end(),"pin edit did not target input");p->second=value.string_value;
            }
        if(auto edits=object_field(row,"map_edit"))for(const auto& [pin,value]:edits->object_value)mapping.function_map[pin]=value.string_value;
        if(auto p=object_field(row,"module_draw_a"))policy.module_draw_a=p->number_value;
        if(auto p=object_field(row,"sdio_level_v"))policy.sdio_level_v=p->number_value;
        auto run=[&]{return author_som_connector(ref,"dynamic","dynamic fixture",som,mapping,policy);};
        if(auto expected=object_field(row,"error")) {
            bool rejected=false;try{run();}catch(const CircuitAuthoringError& e){rejected=true;require(expected->string_value==e.what(),"connector error differs from Python");}
            require(rejected,"repeated SoM signal accepted");
        } else require(authoring_json_equal(authored_circuit_json(run()),at(row,"circuit")),project+": dynamic connector parameters ignored");
    }
    ProjectAuthoringInput input;input.project_root=root/project;
    input.som=load_som_interface(input.project_root/"som_interface.json");
    input.mapping=link_mapping_from_json(parse_json_file((input.project_root/"som_mapping.json").string()));
    input.project_root="/this/path/does/not/exist";
    require(!author_project_subsystem(project,"som_j1",input).parts.empty(),"caller supplied contract was ignored");
    input.mapping->function_map["ZYNQ_PS_MIO7/VM0"]="ILLEGAL_STRAP_LOAD";
    bool failed=false;try{author_project_subsystem(project,"som_j1",input);}catch(const CircuitAuthoringError&){failed=true;}
    require(failed,"voltage-mode strap remapping accepted");
}
void native_packages(const fs::path& root) {
    constexpr auto mode=AuthoringPackageMode::native_assets;
    Scratch s;const auto library=s.path/"library";
    auto libraries=native_subsystem_factories();
    for(const auto& f:libraries)for(const auto& file:subsystem_required_files(f.name,mode))
        write(library/f.name/file,read(root/"subsystems"/f.name/file));
    auto lib_result=check_subsystem_structure(library,libraries,mode);
    require(lib_result.ok()&&lib_result.n_ok()==17,"native library without any Python failed: "+lib_result.summary());
    require(lib_result.exit_code()==0&&lib_result.summary().find(".py")==std::string::npos,"native summary describes Python package shape");
    require(at(subsystem_structure_json(lib_result),"package_mode").string_value=="native_assets","native JSON report lacks mode");
    require(check_subsystem_structure(library,libraries,AuthoringPackageMode::legacy_python).packages.empty(),"legacy discovery contract changed");
    auto empty=check_subsystem_structure(s.path/"empty",{},mode);
    require(!empty.ok()&&empty.exit_code()==1,"empty native library must fail closed, not report-first");
    require(!check_carrier_structure(s.path/"empty",library,{},mode).ok(),"empty native project accepted");
    auto missing=check_subsystem_structure(s.path/"absent",libraries,mode);
    require(missing.packages.size()==libraries.size()&&!missing.ok(),"missing registered asset folders disappeared");
    // A directory named README.md is not a required file.
    fs::remove(library/"camera/README.md");fs::create_directory(library/"camera/README.md");
    require(!check_subsystem_structure(library,libraries,mode).ok(),"native required-file directory accepted");
    fs::remove(library/"camera/README.md");write(library/"camera/README.md",read(root/"subsystems/camera/README.md"));
    write(library/"ghost/README.md","unregistered");write(library/"ghost/ghost.cir","* fixture\n.end\n");
    require(!check_subsystem_structure(library,libraries,mode).ok(),"unregistered native library folder accepted");
    fs::remove_all(library/"ghost");
    auto duplicates=libraries;duplicates.push_back(libraries.front());
    bool rejected=false;try{(void)check_subsystem_structure(library,duplicates,mode);}catch(const CircuitAuthoringError&){rejected=true;}
    require(rejected,"duplicate native registry accepted");
    auto lib=libraries.front();lib.interface.push_back(lib.interface.front());
    require(!check_subsystem_package(lib.name,library,&lib,mode).ok(),"duplicate native interface accepted");
    lib=libraries.front();lib.circuit=[build=lib.circuit_meta]{return build(SubsystemMeta{});};lib.circuit_meta={};
    require(!check_subsystem_package(lib.name,library,&lib,mode).ok(),"nonparameterized native library accepted");

    for(const auto* project:{"carrier","devkit_mini"}) {
        const auto project_root=s.path/project,base=project_root/"subsystems";
        write(project_root/"som_interface.json",read(root/project/"som_interface.json"));
        write(project_root/"som_mapping.json",read(root/project/"som_mapping.json"));
        ProjectAuthoringInput input;input.project_root=project_root;
        auto factories=native_project_factories(project,input);
        for(const auto& f:factories)for(const auto& file:carrier_required_files(f.name,f.meta.has_value(),mode))
            write(base/f.name/file,read(root/project/"subsystems"/f.name/file));
        auto result=check_carrier_structure(base,library,factories,mode);
        require(result.ok()&&result.packages.size()==factories.size(),"no-Python project assets rejected: "+result.summary());
        require(result.summary().find(".py")==std::string::npos,"native project summary describes Python files");
        require(at(carrier_structure_json(result),"package_mode").string_value=="native_assets","project report mode");
        // Independent factory and JSON mutations must both invalidate the gate.
        auto f=*std::find_if(factories.begin(),factories.end(),[](const auto& x){return x.name=="power";});
        const auto path=base/"power/circuit.json";const auto bytes=read(path);
        fs::remove(path);require(!check_carrier_package(f.name,base,library,&f,mode).ok(),"missing native JSON accepted");
        write(path,"{");require(!check_carrier_package(f.name,base,library,&f,mode).errors.empty(),"malformed native JSON accepted");
        write(path,bytes);
        auto changed=f;changed.circuit=[build=f.circuit]{auto c=build();c.title+=" changed";return c;};
        auto report=check_carrier_package(f.name,base,library,&changed,mode);
        require(report.errors==std::vector<std::string>{"circuit.json differs from the native authoring factory"},"native snapshot compared against itself");
        changed=f;changed.meta=JsonNode{};
        require(!check_carrier_package(f.name,base,library,&changed,mode).ok(),"invalid native adapter metadata accepted");
        changed=f;changed.meta->object_value.push_back({"bad_key",JsonNode{}});
        require(!check_carrier_package(f.name,base,library,&changed,mode).errors.empty(),"metadata schema ignored");
        changed=f;changed.circuit={};
        require(!check_carrier_package(f.name,base,library,&changed,mode).ok(),"missing native project callable accepted");
        changed=f;changed.circuit=[]()->CircuitSheetIr{throw CircuitAuthoringError("native throw");};
        require(check_carrier_package(f.name,base,library,&changed,mode).errors==std::vector<std::string>{"CircuitError: native throw"},"native exception lost");
        changed=f;changed.circuit=[build=f.circuit]{auto c=build();c.name="not_power";return c;};
        require(!check_carrier_package(f.name,base,library,&changed,mode).ok(),"mismatched native circuit name accepted");
        fs::rename(library/"power",s.path/"held_power");
        report=check_carrier_package(f.name,base,library,&f,mode);
        require(report.adapter&&!report.ok()&&!report.missing.empty(),"missing library reclassified adapter as local");
        fs::rename(s.path/"held_power",library/"power");
        require(!check_carrier_package(f.name,base,library,nullptr,mode).ok(),"native package without registry accepted");
        fs::remove(base/"mechanical/mechanical.cir");
        require(!check_carrier_structure(base,library,factories,mode).ok(),"missing local circuit contract accepted");
        write(base/"mechanical/mechanical.cir",read(root/project/"subsystems/mechanical/mechanical.cir"));
        require(check_carrier_structure(base,library,factories,mode).ok(),"restored native package failed");
        write_authoring_gate_report(s.path/(std::string(project)+".txt"),result.summary());
        require(read(s.path/(std::string(project)+".txt"))==result.summary()+"\n","native summary publication bytes");
    }
    // Optional library JSON gets the same independent comparison, not a bypass.
    const auto widget=library/"widget";
    write(widget/"README.md","fixture");write(widget/"widget.cir","* fixture\n.end\n");
    const std::string widget_json=R"({"schema":"schgen.circuit/1","name":"widget","title":"widget","parts":[],"nets":[{"name":"GND","net_class":"ground","pins":[]}],"nc":[],"port_types":{},"hints":{},"loads":{},"tp_waivers":{},"decap_waivers":{},"pull_waivers":{},"reset_waivers":{},"strap_waivers":{},"ep_waivers":{},"thermal_waivers":{},"part_rule_waivers":{}})";
    write(widget/"circuit.json",widget_json);
    SubsystemPackageFactory factory{"widget",{"GND"},[](const SubsystemMeta& m){CircuitAuthor c("widget");c.net("GND");return m.finish(c);},{}};
    require(check_subsystem_package("widget",library,&factory,mode).ok(),"valid optional native library JSON rejected");
    factory.circuit_meta=[](const SubsystemMeta& m){CircuitAuthor c("widget","changed");c.net("GND");return m.finish(c);};
    require(!check_subsystem_package("widget",library,&factory,mode).errors.empty(),"library companion drift ignored");
    for(const auto& p:fs::recursive_directory_iterator(s.path))
        require(p.path().extension()!=".py","no-Python proof accidentally retained Python assets");
}
}
int main(int argc,char** argv) {
    try {
        require(argc==2,"usage: authoring_gates_contracts REPOSITORY");const fs::path root=argv[1];
        require(open_part_catalog((root/"native/catalog.bin").string()),"open catalog");
        default_mode_contracts(root);
        const auto library=parse_json_file((root/"native/tests/data/authoring/gate_library.json").string());
        constexpr auto mode=AuthoringPackageMode::native_assets;
        auto result=check_subsystem_structure(root/"subsystems",native_subsystem_factories());
        require(result.ok()&&result.n_ok()==17,"real library gate failed: "+result.summary());
        require(result.exit_code()==0&&result.mode==mode,"real repository must use the native hard gate");
        legacy_reports(root,library);
        for(const auto* project:{"carrier","devkit_mini"}) {
            const auto fixture=parse_json_file((root/"native/tests/data/authoring"/(std::string("gate_")+project+".json")).string());
            auto factories=project_factories(root,project);
            for(const auto& p:at(fixture,"packages").array_value) {
                auto f=std::find_if(factories.begin(),factories.end(),[&](const auto& x){return x.name==at(p,"name").string_value;});
                require(f!=factories.end(),"missing native project factory");
                require(authoring_json_equal(authored_circuit_json(f->circuit()),at(p,"circuit")),std::string(project)+":"+f->name+" differs from independent Python circuit output");
            }
            auto r=check_carrier_structure(root/project/"subsystems",root/"subsystems",factories);
            require(r.ok(),r.summary());
            require(r.mode==mode&&r.packages.size()==at(fixture,"packages").array_value.size(),"real native package census changed");
            require(r.exit_code()==0&&r.n_locals()+r.n_adapters()==r.packages.size(),"gate count/exit");
            if(std::string(project)=="carrier")mutations(root);
            connectors(root,project);
        }
        native_packages(root);
        close_part_catalog();
        std::cout<<"PASS: "<<checks<<" assertions; 17 library + 49 project native packages, independent circuit oracles, inert legacy report bytes and no-Python asset contracts verified\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
