#pragma once
#include "precision_receipt.hpp"
#include <memory>
#include <stdexcept>

namespace precision_receipt_contracts {
inline void require(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
struct ProducerFailure:std::runtime_error {using std::runtime_error::runtime_error;};
struct ImportFailure:std::runtime_error {using std::runtime_error::runtime_error;};
inline void run(){
    using schgen::QuantizationCounts;
    using schgen::board_pipeline_detail::with_precision_receipt;
    int producers=0,imports=0;
    const auto produce=[&](QuantizationCounts& counts){
        ++producers;schgen::checked_quantization_add(counts,"test_receipt");return std::make_unique<int>(7);
    };
    const auto inspect=[&](const QuantizationCounts& counts){
        ++imports;require(counts==QuantizationCounts{{"test_receipt",1}},"exact executed producer prefix imported");
    };
    const auto result=with_precision_receipt(produce,inspect);
    require(*result==7&&producers==1&&imports==1,"successful move-only result and exactly one import");

    producers=imports=0;bool producer_caught=false;
    try{with_precision_receipt([&](QuantizationCounts& counts)->int{
        ++producers;schgen::checked_quantization_add(counts,"test_receipt");throw ProducerFailure("producer");
    },inspect);}catch(const ProducerFailure&){producer_caught=true;}
    require(producer_caught&&producers==1&&imports==1,"producer failure retains prefix and original exception");

    producers=imports=0;bool import_caught=false;
    try{with_precision_receipt(produce,[&](const QuantizationCounts& counts){
        inspect(counts);
        if(imports==1)throw ImportFailure("first import failure");
        throw std::runtime_error("second import attempt masked first failure");
    });}catch(const ImportFailure& e){import_caught=std::string(e.what())=="first import failure";}
    require(import_caught&&producers==1&&imports==1,"successful producer import failure is never retried");

    producers=imports=0;import_caught=false;
    try{with_precision_receipt([&](QuantizationCounts& counts)->int{
        ++producers;schgen::checked_quantization_add(counts,"test_receipt");throw ProducerFailure("producer");
    },[&](const QuantizationCounts& counts){inspect(counts);throw ImportFailure("failed-prefix import");});
    }catch(const ImportFailure& e){import_caught=std::string(e.what())=="failed-prefix import";}
    require(import_caught&&producers==1&&imports==1,"failed producer attempts prefix import once; import error propagates");

    imports=0;
    require(with_precision_receipt([](QuantizationCounts&){return 9;},[&](const QuantizationCounts& counts){
        ++imports;require(counts.empty(),"no work fabricates no counts");
    })==9&&imports==1,"empty receipt remains empty");
}
}
