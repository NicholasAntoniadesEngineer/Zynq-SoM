// Instrument quantize.cpp and native_audit_quantize.cpp only. No production
// observer or global receipt: these thread-local counters independently watch
// the real registered scalar function entries in this executable.
#include "floorplan_internal.hpp"
#include "native_audit_quantize_internal.hpp"
#include "ledger_accounting_fixture.hpp"
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {
thread_local bool observing=false;
thread_local std::size_t via_entries=0,tolerance_entries=0;
void require(bool yes,const char* why){if(!yes)throw std::runtime_error(why);}
void begin(){via_entries=0;tolerance_entries=0;observing=true;}
void end(){observing=false;}
template<class F> void overflow(F run){bool caught=false;try{run();}catch(const std::overflow_error&){caught=true;}end();require(caught,"expected counter overflow");}
schgen::FloorplanInput input(){schgen::FloorplanInput x;x.som.w=x.som.h=20;return x;}
void ledger(){
    const auto in=input();
    schgen::floorplan_detail::Engine engine(in);
    engine.ledger_open();
    begin();engine.ledger_initial(100,100);end();
    require(via_entries==2,"both actual ledger via-cost scalar entries observed");
    require(engine.plan.accounting.quantization_engagements.at("est_via_cost")==via_entries,"ledger receipt equals entries");
    for(const std::size_t allowance:{std::size_t{0},std::size_t{1}}){
        schgen::floorplan_detail::Engine rejected(in);rejected.ledger_open();
        rejected.plan.accounting.quantization_engagements["est_via_cost"]=std::numeric_limits<std::size_t>::max()-allowance;
        begin();overflow([&]{rejected.ledger_initial(100,100);});
        require(via_entries==allowance,"overflow stops before unbooked scalar; first-call prefix retained");
        require(rejected.plan.accounting.quantization_engagements.at("est_via_cost")==std::numeric_limits<std::size_t>::max(),"counter never wraps");
    }
}
void tolerance(){
    const auto in=input();schgen::floorplan_detail::Engine engine(in);
    engine.initialize();engine.prepare_geometry();engine.board_size(100,100);
    begin();const bool accepted=engine.attempt_pack(false);end();
    require(accepted,"empty legal board control packs");
    require(tolerance_entries==1,"packer calls registered tolerance function, not copied literal");
    require(engine.plan.accounting.quantization_engagements.at("run_overflow_tol")==tolerance_entries,"tolerance receipt equals entries");
    engine.plan.accounting.quantization_engagements["run_overflow_tol"]=std::numeric_limits<std::size_t>::max();
    begin();overflow([&]{engine.attempt_pack(false);});
    require(tolerance_entries==0,"overflow prevents tolerance scalar execution");
    require(schgen::native_run_overflow_tol()==0.1,"unchanged exact tolerance value");
}
}
extern "C" void __cyg_profile_func_enter(void* function,void*){
    if(!observing)return;
    if(function==reinterpret_cast<void*>(&schgen::est_via_cost))++via_entries;
    if(function==reinterpret_cast<void*>(&schgen::native_run_overflow_tol))++tolerance_entries;
}
extern "C" void __cyg_profile_func_exit(void*,void*){}
int main(){try{ledger_accounting_fixture::contracts();ledger();tolerance();std::cout<<"floorplan receipt contracts PASS\n";}catch(const std::exception& e){end();std::cerr<<e.what()<<'\n';return 1;}}
