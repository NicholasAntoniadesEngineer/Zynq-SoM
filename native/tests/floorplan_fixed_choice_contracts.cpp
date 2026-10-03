#include "floorplan_fixed_choice_fixture.hpp"
#include "floorplan_precision_fixture.hpp"
#include <iostream>
namespace {
using namespace schgen;
void require(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
}
int main(int argc,char** argv){try{
    auto in=fixed_choice_fixture::input();floorplan_detail::Engine engine(in);
    std::array<double,2> measured{};std::array<std::size_t,2> observations{};
    auto observer=std::make_shared<FloorplanExperiment>();in.experiment=observer;
    observer->unscoped_estimate=[&](double value){const auto pass=engine.plan.punch_free?1:0;measured[pass]=value;++observations[pass];};
    auto result=engine.run();require(result.punch_free&&observations[0]&&observations[1],"both fixed passes ran and free naturally won");
    require(measured[1]<measured[0],"winning estimate is genuinely smaller");
    bool checked=false,correct=false;
    for(auto& decision:result.accounting.decisions)if(decision.name=="plan_choice"){
        require(!checked,"one plan choice");checked=true;
        double conservative=-1,free=-1;
        for(auto& [key,value]:decision.inputs){if(key=="conservative_est"){conservative=value.number_value;value.number_value=0;}if(key=="free_est")free=value.number_value;}
        correct=conservative==py_round(measured[0],1)&&free==py_round(measured[1],1);
        std::cout<<"actual conservative="<<measured[0]<<" free="<<measured[1]<<"; recorded conservative="<<conservative<<" free="<<free<<'\n';
        // Optional private equivalence dump masks ONLY the corrected ledger
        // input and its mirrored text token; every other byte/counter remains.
        const std::string marker="conservative_est=";auto at=decision.text.find(marker);require(at!=std::string::npos,"ledger text token exists");at+=marker.size();const auto end=decision.text.find(' ',at);require(end!=std::string::npos,"ledger token terminated");decision.text.replace(at,end-at,"0");
    }
    require(checked,"plan choice exists");
    if(argc==2){std::ofstream out(argv[1],std::ios::binary);floorplan_precision_fixture::node(out,floorplan_plan_json(result));require(bool(out),"private dump write");}
    require(correct,"fixed plan_choice must retain the actual conservative estimate, not the free winner estimate");
    std::cout<<"fixed choice contracts PASS\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
