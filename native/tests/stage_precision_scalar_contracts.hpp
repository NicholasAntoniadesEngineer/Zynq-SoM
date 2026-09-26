#pragma once
#include "stage_precision_registration.hpp"
namespace stage_test {
using Round=double(*)(double,QuantizationCounts*);
using Narrow=int(*)(double,QuantizationCounts*);
const std::array<Round,15> round_ops{{stage_shift_precision4dp,
    stage_root_pose_precision4dp,
    stage_connector_alignment_delta_precision4dp,
    stage_connector_clearance_line_precision4dp,
    stage_connector_clearance_delta_precision4dp,
    stage_ldo_pose_precision4dp,
    stage_power_mirror_pose_precision4dp,
    stage_layout_width_precision4dp,
    stage_hot_leftover_pose_precision4dp,
    stage_hot_extent_precision4dp,
    stage_proximity_leftover_pose_precision4dp,
    stage_proximity_rebase_precision4dp,
    stage_proximity_extent_precision4dp,
    stage_proximity_face_shift_precision4dp,
    stage_refit_pad_precision3dp}};
const std::array<Narrow,2> narrow_ops{{stage_candidate_radius_trunc,stage_seat_radius_trunc}};
void observe(void* fn){
    for(std::size_t i=0;i<round_ops.size();++i)if(fn==reinterpret_cast<void*>(round_ops[i])){++entries[i];return;}
    for(std::size_t i=0;i<narrow_ops.size();++i)if(fn==reinterpret_cast<void*>(narrow_ops[i])){++entries[i+15];return;}
}
template<class Error,class F> void rejects(F f,const std::string& why){bool threw=false;try{f();}catch(const Error&){threw=true;}require(threw,why);}
void scalar_contracts(){
    for(std::size_t i=0;i<round_ops.size();++i){
        const int digits=i==14?3:4;const double scale=i==14?1000.:10000.;
        for(int k=-512;k<=512;++k){
            const auto midpoint=(k+.5)/scale;
            for(double v:{std::nextafter(midpoint,-INFINITY),midpoint,std::nextafter(midpoint,INFINITY)}){
                QuantizationCounts q;begin();const auto got=round_ops[i](v,&q);const auto actual=end();
                require(bits(got)==bits(py_round(v,digits))&&q==actual&&q==QuantizationCounts{{names[i],1}},"halfway neighbor bits and real scalar entry "+names[i]);
            }
        }
        for(double v:{0.,-0.,1e-300,-1e-300,1e300,-1e300,double(INFINITY),double(-INFINITY),double(NAN)})
            require(bits(round_ops[i](v,nullptr))==bits(py_round(v,digits)),"IEEE bits "+names[i]);
        QuantizationCounts full{{names[i],SIZE_MAX}};begin();
        rejects<std::overflow_error>([&]{round_ops[i](1.,&full);},"counter overflow");
        require(end()==QuantizationCounts{{names[i],1}}&&full.at(names[i])==SIZE_MAX,"entered failing scalar cannot wrap producer count");
    }
    for(std::size_t i=0;i<narrow_ops.size();++i){
        for(double v:{-10.9,-.9,-0.,0.,.9,1.,59.999,60.999,61.1,double(INT32_MAX)+.75,double(INT32_MIN)-.75}){
            QuantizationCounts q;begin();const int got=narrow_ops[i](v,&q);const auto calls=end();
            require(got==static_cast<int>(v)&&q==calls&&q==QuantizationCounts{{names[i+15],1}},"defined truncation retained");
        }
        for(double v:{double(INFINITY),double(-INFINITY),double(NAN)})
            rejects<std::invalid_argument>([&]{narrow_ops[i](v,nullptr);},"nonfinite conversion rejects");
        for(double v:{double(INT32_MAX)+1,double(INT32_MIN)-1,1e300,-1e300})
            rejects<std::out_of_range>([&]{narrow_ops[i](v,nullptr);},"undefined narrowing rejects");
        QuantizationCounts q;begin();rejects<std::out_of_range>([&]{narrow_ops[i](1e300,&q);},"bad attempted radius");
        require(end()==q&&q==QuantizationCounts{{names[i+15],1}},"attempted invalid radius counted once");
        require(std::min(narrow_ops[i](60.9,nullptr),60)==60,"cap stays after conversion");
    }
    NativeQuantizations registry;register_native_quantizations(registry);
    require(registry.declarations().size()==83,"64 prior plus nineteen placement operations");
    const auto declarations=registry.declarations();
    for(std::size_t i=0;i<names.size();++i){
        const auto d=std::find_if(declarations.begin(),declarations.end(),[&](const auto& x){return x.name==names[i];});
        require(d!=declarations.end()&&d->arity==1&&d->symbol=="native/src/stage_precision.cpp::schgen::"+names[i],"genuine scalar identity/arity");
        begin();const auto result=registry.invoke(names[i],{1.23455});const auto calls=end();
        const auto expected=i<15?py_round(1.23455,i==14?3:4):1.;
        require(bits(result)==bits(expected)&&calls==QuantizationCounts{{names[i],1}},"registry calls actual scalar exactly once");
        begin();rejects<std::invalid_argument>([&]{registry.invoke(names[i],{});},"arity rejects");require(end().empty(),"bad arity executes no scalar");
    }
}
void ownership_contracts(){
    const QuantizationCounts prior{{"legalize_pose_quantum",2},{"stage_direction_component",3},
        {"stage_shift_precision4dp_typo",4},{"legalize_position_precision4dp_typo",5}};
    auto mixed=prior;for(const auto& name:names)mixed[name]=7;
    require(select(mixed,false)==prior,"stage adapter separates only seventeen exact names");
    mixed["legalize_position_precision4dp"]=9;
    require(legalize_precision_fixture::select(select(mixed,false),false)==prior,"snapshot retains historical and unknown names, never family prefix waivers");
    auto in=small();pcb_stage::Engine a(in);const pcb_stage::Parts original{a.part("A",0,1.23455,-0.)};
    begin();const auto shifted=pcb_stage::shifted(original,.000049,-.00005,a.quantization);const auto calls=end();
    require(calls==QuantizationCounts{{names[0],2}}&&a.quantization==calls&&bits(shifted[0].x)==bits(py_round(1.23455+.000049,4)),"shift has two separate exact boundaries");
    auto b=a;begin();(void)pcb_stage::shifted(original,0,0,b.quantization);const auto more=end();
    require(more==calls&&a.quantization==calls&&b.quantization.at(names[0])==4,"copied engine owns subsequent calls independently");
    NativeQuantizations q;NativeFallbacks f;register_native_quantizations(q);
    register_native_fallbacks(f);
    NativeAccountingInbox inbox(q,f);PcbStageResult result;result.quantization_engagements=a.quantization;
    begin();require(inbox.merge_once("stage",result)&&!inbox.merge_once("stage",result),"actual stage receipt imports once");require(end().empty(),"receipt replay executes no precision math");
    require(q.engagements().at(names[0])==AuditInteger(2),"receipt contains exact stage work");
    std::array<QuantizationCounts,2> independent;begin();std::array<std::thread,2> workers;
    for(std::size_t i=0;i<workers.size();++i)workers[i]=std::thread([&,i]{for(int k=0;k<20;++k)(void)pcb_stage::shifted(original,0,0,independent[i]);});
    for(auto& worker:workers)worker.join();require(end()==QuantizationCounts{{names[0],80}}&&independent[0]==QuantizationCounts{{names[0],40}}&&independent[1]==independent[0],"concurrent invocations share no sink");
}
} // namespace stage_test
