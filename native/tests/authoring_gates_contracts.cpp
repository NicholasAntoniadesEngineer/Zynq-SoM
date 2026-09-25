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
void require(bool ok,const std::string& why){if(!ok)throw std::runtime_error(why);}
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
void mutations(const fs::path& root) {
    Scratch s;const auto base=s.path/"carrier",lib=s.path/"lib";
    fs::create_directories(lib/"usb_pd");fs::create_directories(base);
    require(!check_carrier_structure(base,lib,{}).ok(),"empty carrier must fail");
    require(check_subsystem_structure(lib,{}).ok(),"empty discoverable library is report-first PASS");
    auto factories=project_factories(root,"carrier");
    auto it=std::find_if(factories.begin(),factories.end(),[](const auto& x){return x.name=="usb_pd";});
    require(it!=factories.end(),"oracle usb_pd");
    auto f=*it;
    for(const auto& name:carrier_required_files("usb_pd",true))write(base/name,"retained authoring artifact\n");
    auto check=[&]{return check_carrier_package("usb_pd",base,lib,&f);};
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
    auto r=check_carrier_package("usb_pd",base,lib,&changed);
    require(r.errors==std::vector<std::string>{"circuit.json differs from the adapter netlist"},"authoring mutation was ignored");
    // A second direction catches gates that compare an IR companion to itself.
    auto bad=bytes;const auto pos=bad.find("USB-PD:");require(pos!=std::string::npos,"title mutation target");bad.insert(pos,"changed ");
    write(base/"usb_pd/circuit.json",bad);require(!check().ok()&&check().errors.size()==1,"companion mutation was ignored");
    write(base/"usb_pd/circuit.json","{");require(!check().errors.empty(),"malformed companion accepted");
    write(base/"usb_pd/circuit.json",bytes);
    changed=f;changed.meta.reset();r=check_carrier_package("usb_pd",base,lib,&changed);
    require(!r.ok()&&r.has_circuit&&!r.has_meta,"missing META accepted");
    changed=f;changed.circuit={};r=check_carrier_package("usb_pd",base,lib,&changed);
    require(!r.ok()&&!r.has_circuit,"missing factory accepted");
    changed=f;changed.circuit=[]()->CircuitSheetIr{throw CircuitAuthoringError("intentional build failure");};
    r=check_carrier_package("usb_pd",base,lib,&changed);require(r.errors==std::vector<std::string>{"CircuitError: intentional build failure"},"factory exception lost");
    require(!check_carrier_package("usb_pd",base,lib,nullptr).ok(),"unregistered authoring accepted");
    fs::remove(base/"test_usb_pd.py");require(check().missing==std::vector<std::string>{"test_usb_pd.py"},"missing adapter test not detected");
    write(base/"widget.py","flat local");
    CarrierPackageFactory local{"widget",[]{CircuitAuthor c("widget");return c.finish();},std::nullopt};
    require(!check_carrier_package("widget",base,lib,&local).ok(),"flat local accepted");
    for(const auto& name:carrier_required_files("widget",false))write(base/"widget"/name,"");
    require(check_carrier_package("widget",base,lib,&local).ok(),"complete foldered local rejected");
    fs::remove(base/"widget/README.md");require(!check_carrier_package("widget",base,lib,&local).ok(),"missing local readme accepted");
    // Library gate uses actual constructor results and declared interfaces.
    const auto pkg=lib/"usb_pd";
    for(const auto& name:subsystem_required_files("usb_pd"))write(pkg/name,"");
    write(pkg/"__init__.py","");
    auto libs=native_subsystem_factories();
    auto l=*std::find_if(libs.begin(),libs.end(),[](const auto& x){return x.name=="usb_pd";});
    auto lr=check_subsystem_package("usb_pd",lib,&l);require(lr.ok(),"valid library rejected");
    l.interface.erase(l.interface.begin());l.interface.push_back("BOGUS");lr=check_subsystem_package("usb_pd",lib,&l);
    require(lr.interface_drift==std::vector<std::string>{"net '+VDD_LOGIC' is an external but not in the declared INTERFACE", "INTERFACE name 'BOGUS' is not an external net of the built circuit"},"interface drift not diagnosed");
    SubsystemStructureResult fail{{lr}};require(fail.exit_code()==0&&fail.exit_code(true)==1,"report-first/strict policy");
    l.interface.clear();require(!check_subsystem_package("usb_pd",lib,&l).ok(),"empty interface accepted");
    l.circuit=[build=l.circuit_meta]{return build(SubsystemMeta{});};l.circuit_meta={};
    lr=check_subsystem_package("usb_pd",lib,&l);require(lr.has_circuit&&!lr.accepts_meta&&!lr.ok(),"missing meta signature accepted");
    l.circuit=[]()->CircuitSheetIr{throw CircuitAuthoringError("intentional failure");};
    require(check_subsystem_package("usb_pd",lib,&l).errors==std::vector<std::string>{"circuit() build failed: CircuitError: intentional failure"},"library exception report");
    l.circuit={};lr=check_subsystem_package("usb_pd",lib,&l);require(!lr.has_circuit&&!lr.ok(),"no top-level circuit accepted");
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
}
int main(int argc,char** argv) {
    try {
        require(argc==2,"usage: authoring_gates_contracts REPOSITORY");const fs::path root=argv[1];
        require(open_part_catalog((root/"native/catalog.bin").string()),"open catalog");
        const auto library=parse_json_file((root/"native/tests/data/authoring/gate_library.json").string());
        auto result=check_subsystem_structure(root/"subsystems",native_subsystem_factories());
        require(result.ok()&&result.n_ok()==17,"real library gate failed: "+result.summary());
        check_report(subsystem_structure_json(result),library,root);
        for(const auto* project:{"carrier","devkit_mini"}) {
            const auto fixture=parse_json_file((root/"native/tests/data/authoring"/(std::string("gate_")+project+".json")).string());
            auto factories=project_factories(root,project);
            for(const auto& p:at(fixture,"packages").array_value) {
                auto f=std::find_if(factories.begin(),factories.end(),[&](const auto& x){return x.name==at(p,"name").string_value;});
                require(f!=factories.end(),"missing native project factory");
                require(authoring_json_equal(authored_circuit_json(f->circuit()),at(p,"circuit")),std::string(project)+":"+f->name+" differs from independent Python circuit output");
            }
            auto r=check_carrier_structure(root/project/"subsystems",root/"subsystems",factories);
            require(r.ok(),r.summary());check_report(carrier_structure_json(r),fixture,root);
            require(r.exit_code()==0&&r.n_locals()+r.n_adapters()==r.packages.size(),"gate count/exit");
            if(std::string(project)=="carrier")mutations(root);
            connectors(root,project);
        }
        close_part_catalog();
        std::cout<<"PASS: 17 library + 49 project package reports match Python; both report summaries and gate mutations verified\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
