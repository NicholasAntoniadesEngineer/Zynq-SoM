// Instrument ONLY precision_ops.cpp with -finstrument-functions -fno-inline.
// The observer is test-only and never supplies production accounting.
#include "connector_precision_fixture.hpp"
#include "schgen/native_audit_state.hpp"
#include "schgen/precision_ops.hpp"
#include <array>
#include <atomic>
#include <cstring>
#include <iostream>

namespace {
using namespace schgen;
const std::string mech="mechanical_direction_component", stage="stage_direction_component";
std::array<std::atomic<std::size_t>,2> entries{};
std::atomic<bool> observing{false};
std::size_t checks=0;
void require(bool ok,const std::string& why){++checks;if(!ok)throw std::runtime_error(why);}
void begin(){for(auto& n:entries)n=0;observing=true;}
QuantizationCounts end(){observing=false;QuantizationCounts out;if(entries[0])out[mech]=entries[0];if(entries[1])out[stage]=entries[1];return out;}
QuantizationCounts selected(const QuantizationCounts& values){QuantizationCounts out;for(const auto& [k,n]:values)if(k==mech||k==stage)out[k]=n;return out;}
std::uint64_t bits(double x){std::uint64_t v;std::memcpy(&v,&x,sizeof(v));return v;}
template<class F> void rejects(F f,const std::string& why){bool threw=false;try{f();}catch(const std::invalid_argument&){threw=true;}catch(const std::out_of_range&){threw=true;}require(threw,why);}
void scalars(){
    for(int i=-2048;i<=2048;++i)for(double x:{i*.5,std::nextafter(i*.5,-INFINITY),std::nextafter(i*.5,INFINITY)}){
        require(mechanical_direction_component(x)==static_cast<int>(py_round(x,0)),"legacy mechanical round then narrow");
        require(bits(stage_direction_component(x))==bits(std::round(x)),"legacy stage rounding bits");
    }
    require(mechanical_direction_component(.5)==0&&mechanical_direction_component(-.5)==0,"ties-even at signed half");
    require(stage_direction_component(.5)==1&&stage_direction_component(-.5)==-1,"ties-away at signed half");
    require(mechanical_direction_component(2.5)==2&&stage_direction_component(2.5)==3,"rounding laws stay distinct");
    for(double x:{INFINITY,-INFINITY,NAN})rejects([&]{mechanical_direction_component(x);},"nonfinite narrowing rejects");
    const double hi=std::numeric_limits<int>::max(),lo=std::numeric_limits<int>::min();
    require(mechanical_direction_component(hi+.25)==std::numeric_limits<int>::max(),"validate rounded value, not pre-round input");
    require(mechanical_direction_component(lo-.5)==std::numeric_limits<int>::min(),"negative ties-even lower boundary");
    rejects([&]{mechanical_direction_component(hi+.5);},"upper overflow after round");
    rejects([&]{mechanical_direction_component(std::nextafter(lo-.5,-INFINITY));},"lower overflow after round");
    require(bits(stage_direction_component(-0.0))==bits(-0.0)&&std::isinf(stage_direction_component(INFINITY))&&std::isnan(stage_direction_component(NAN)),"stage IEEE behavior remains unchanged");
}
void registry(){
    NativeQuantizations q;register_native_quantizations(q);require(q.declarations().size()==34,"28 existing plus six actual floorplan scalar functions");
    for(const auto& name:{mech,stage}){
        const auto ds=q.declarations();const auto it=std::find_if(ds.begin(),ds.end(),[&](const auto& d){return d.name==name;});
        require(it!=ds.end()&&it->arity==1&&it->symbol=="native/src/precision_ops.cpp::schgen::"+name,"exact scalar implementation and arity");
        begin();const auto value=q.invoke(name,{.5});const auto observed=end();
        require(observed==QuantizationCounts{{name,1}}&&value==(name==mech?0:1),"callback executes its actual primitive exactly once");
    }
}
void mechanical_mutations(){
    PcbCheckModel model;model.board_w=model.board_h=100;
    PcbCheckInstance part;part.ref="J1";part.value="HDMI-019S";part.x=50;part.y=124;
    part.mod=pcb_check_footprint("connector.kicad_mod",R"((footprint "connector" (fp_rect (start -1 -1) (end 1 1) (layer "F.CrtYd"))))");
    model.insts={part};
    for(double rotation:{0.,180.}){
        model.insts[0].rotation=rotation;begin();const auto result=check_placement_mech(PcbCheckInput(model));const auto observed=end();
        require(result.ok==(rotation==0)&&result.bad_connectors.size()==(rotation==0?0:1),"mechanical facing mutation preserves verdict");
        require(observed==QuantizationCounts{{mech,2}}&&result.quantization_engagements==observed,"failed mechanical verdict still owns its actual calls");
    }
    model.insts[0].rotation=0;model.insts[0].y=90;begin();const auto recessed=check_placement_mech(PcbCheckInput(model));const auto work=end();
    require(!recessed.ok&&recessed.quantization_engagements==work&&work==QuantizationCounts{{mech,2}},"recessed connector cannot pass and retains real counts");
    model.insts[0].value="nonconnector";model.insts[0].mod.reset();begin();const auto skipped=check_placement_mech(PcbCheckInput(model));const auto unused=end();
    require(skipped.n_connectors==0&&skipped.quantization_engagements.empty()&&unused.empty(),"skipped nonconnector fabricates no engagements");
}
void rotations(std::ostream& output){
    for(const auto* value:{"TYPE-C-31-M-12","HDMI-019S","AFC07-S40FCA-00","KH-5224-8P8C-D","TF-01A","SFW15R-1STE1LF","ZX-SH1.0-4PWT","DS1024-2x6R2","XT60PW-M","unknown"}){
        const bool xt=std::string(value)=="XT60PW-M";
        const std::map<std::string,std::size_t> expected=xt?std::map<std::string,std::size_t>{{"N",3},{"E",2},{"S",6},{"W",4}}:std::map<std::string,std::size_t>{{"N",5},{"E",3},{"S",2},{"W",5}};
        for(const auto* edge:{"N","E","S","W","n","e","s","w","","bad"}){
            std::string key=edge;if(key.size()==1&&key[0]>='a'&&key[0]<='z')key[0]=static_cast<char>(key[0]-'a'+'A');
            const auto found=expected.find(key);QuantizationCounts wanted;if(found!=expected.end())wanted[stage]=found->second;
            QuantizationCounts counts;begin();const auto rot=pcb_stage::connector_rotation(value,edge,counts);const auto observed=end();
            require(counts==wanted&&observed==wanted,"independent cardinal short-circuit call table");
            begin();const auto legacy=pcb_stage::connector_rotation(value,edge);const auto unaccounted=end();
            require(legacy==rot&&unaccounted==wanted&&counts==wanted,"unaccounted API preserves math without mutating caller counters");
            output<<"ROTATION "<<std::quoted(value)<<' '<<std::quoted(edge)<<' '<<rot<<'\n';
        }
    }
    QuantizationCounts full{{stage,std::numeric_limits<std::size_t>::max()}};
    bool threw=false;begin();try{pcb_stage::connector_rotation("XT60PW-M","E",full);}catch(const std::overflow_error&){threw=true;}const auto observed=end();
    require(threw&&observed.empty()&&full.at(stage)==std::numeric_limits<std::size_t>::max(),"overflow rejects before executing unbooked primitive");
}
void show(const QuantizationCounts& counts){std::cout<<'{';bool first=true;for(const auto& [k,n]:counts){if(!first)std::cout<<',';first=false;std::cout<<std::quoted(k)<<':'<<n;}std::cout<<'}';}
QuantizationCounts decoded(const JsonNode& node){QuantizationCounts out;for(const auto& [k,n]:node.object_value)out[k]=static_cast<std::size_t>(n.number_value);return out;}
void boards(const std::filesystem::path& root,bool capture){
    using namespace placement_fixture;
    std::ostringstream output;output<<std::setprecision(17);rotations(output);
    JsonNode additive;if(!capture)additive=parse_json_file((root/"native/tests/data/connector_precision/additive_counts.json").string());
    bool first=true;if(capture)std::cout<<"{\n";
    for(const auto& variant:std::vector<std::pair<std::string,bool>>{{"devkit_mini",false},{"carrier",false},{"devkit_mini",true}}){
        auto fixture=load(root,variant.first);if(variant.second)fixture.input.two_side=false;
        const auto name=variant.first+(variant.second?"_single":"");
        begin();const auto result=build_pcb_model(fixture.input);const auto mechanical=check_placement_mech(PcbCheckInput(result.model));const auto measured=end();
        const auto total=pcb_placement_accounting(result);auto complete=selected(total.quantization_engagements);checked_quantization_merge(complete,mechanical.quantization_engagements);
        require(complete==measured,"exported production counts equal independently observed scalar entries "+name);
        require(mechanical.quantization_engagements==QuantizationCounts{{mech,2*static_cast<std::size_t>(mechanical.n_connectors)}},"each visited connector actually evaluates two direction components");
        require(!mechanical.quantization_engagements.count(stage)&&!total.quantization_engagements.count(mech),"solver and mechanical receipt ownership disjoint");
        if(!capture)require(complete==decoded(field(additive,name)),"separate additive fixture "+name);
        if(capture){if(!first)std::cout<<",\n";first=false;std::cout<<std::quoted(name)<<':';show(complete);}
        output<<"BOARD "<<name<<'\n';connector_fixture::mechanical(output,mechanical);
        connector_fixture::counts(output,"FLOORPLAN",result.floorplan.plan.accounting.quantization_engagements);
        connector_fixture::counts(output,"ZONE",result.zone_accounting.quantization_engagements);
        connector_fixture::counts(output,"PLACEMENT",result.placement_accounting.quantization_engagements);
        connector_fixture::counts(output,"AGGREGATE",total.quantization_engagements);
        NativeQuantizations q;NativeFallbacks f;register_native_quantizations(q);register_native_fallbacks(f);NativeAccountingInbox inbox(q,f);
        begin();require(inbox.merge_once("pcb/placement",total),"actual placement receipt imports once");
        const NativeAccountingBatch mb{native_counter_batch(mechanical.quantization_engagements),{}};
        require(inbox.merge_once("pcb/geometry/mechanical",mb)&&!inbox.merge_once("pcb/geometry/mechanical",mb),"mechanical receipt imports once with replay rejection");
        require(end().empty(),"imports never execute scalar math");
        for(const auto& label:{mech,stage})require(q.engagements().at(label)==AuditInteger::decimal(std::to_string(complete.at(label))),"exact independent count after receipts");
        const auto before=q.engagements();begin();const auto probe=check_placement_mech(PcbCheckInput(result.model));const auto observed=end();
        require(observed==probe.quantization_engagements&&q.engagements()==before&&pcb_placement_accounting(result).quantization_engagements==total.quantization_engagements,"observational recheck stays invocation-local");
    }
    if(capture)std::cout<<"\n}\n";
    require(output.str()==read(root/"native/tests/data/connector_precision/legacy_output.txt"),"all legacy mechanical records, summaries, selection results and prior counter ownership byteexact");
}
}
extern "C" void __cyg_profile_func_enter(void* fn,void*){if(!observing.load(std::memory_order_relaxed))return;if(fn==reinterpret_cast<void*>(&schgen::mechanical_direction_component))++entries[0];else if(fn==reinterpret_cast<void*>(&schgen::stage_direction_component))++entries[1];}
extern "C" void __cyg_profile_func_exit(void*,void*){}
int main(int argc,char** argv){try{if(argc<2||argc>3||(argc==3&&std::string(argv[2])!="--capture-additive"))throw std::runtime_error("repo [--capture-additive]");scalars();registry();mechanical_mutations();boards(argv[1],argc==3);std::cerr<<checks<<" connector precision contracts passed\n";return 0;}catch(const std::exception& e){std::cerr<<"Connector precision FAILED: "<<e.what()<<'\n';return 1;}}
