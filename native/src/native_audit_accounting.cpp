#include "schgen/native_audit_state.hpp"

namespace schgen {
namespace {
void increment(NativeCounterMap& into,const std::string& name,std::uint64_t amount){
    const auto p=into.find(name);
    if(p==into.end())throw std::logic_error("native accounting: unregistered label '"+name+"'");
    if(amount>UINT64_MAX-p->second)throw std::overflow_error("native accounting: counter overflow for '"+name+"'");
    p->second+=amount;
}
NativeCounterMap add_counts(const NativeCounterMap& current,const NativeCounterMap& delta){
    auto next=current;for(const auto& [name,count]:delta)increment(next,name,count);return next;
}
NativeCounterMap event_counts(const NativeCounterMap& current,const std::vector<std::string>& events){
    auto next=current;for(const auto& name:events)increment(next,name,1);return next;
}
NativeCounterMap zeros(NativeCounterMap counts){for(auto& [name,n]:counts){(void)name;n=0;}return counts;}
void can_reset(std::uint64_t epoch){if(epoch==UINT64_MAX)throw std::overflow_error("native accounting: reset epoch overflow");}
}
void NativeFallbacks::record_count(const std::string& name,std::uint64_t n){std::lock_guard<std::mutex> guard(mutex_);increment(counts_,name,n);}
void NativeFallbacks::merge_counts(const NativeCounterMap& counts){std::lock_guard<std::mutex> guard(mutex_);auto next=add_counts(counts_,counts);counts_.swap(next);}
void NativeFallbacks::merge_events(const std::vector<std::string>& events){
    std::lock_guard<std::mutex> guard(mutex_);auto next=event_counts(counts_,events);auto log=events_;
    log.insert(log.end(),events.begin(),events.end());counts_.swap(next);events_.swap(log);
}
NativeFallbackCheckpoint NativeFallbacks::checkpoint()const{std::lock_guard<std::mutex> guard(mutex_);return {counts_,events_};}
std::vector<std::string> NativeFallbacks::snapshot()const{
    std::lock_guard<std::mutex> guard(mutex_);
    if(event_counts(zeros(counts_),events_)!=counts_)throw std::logic_error("fallbacks: compact counts require checkpoint(), not an event-only snapshot");
    return events_;
}
void NativeFallbacks::restore(const std::vector<std::string>& state){
    std::lock_guard<std::mutex> guard(mutex_);can_reset(epoch_);
    auto next=event_counts(zeros(counts_),state);auto events=state;
    counts_.swap(next);events_.swap(events);++epoch_;
}
void NativeFallbacks::restore_checkpoint(const NativeFallbackCheckpoint& state){
    std::lock_guard<std::mutex> guard(mutex_);can_reset(epoch_);
    auto next=add_counts(zeros(counts_),state.counts);const auto logged=event_counts(zeros(counts_),state.events);
    for(const auto& [name,count]:logged)if(next.at(name)<count)throw std::invalid_argument("fallbacks: checkpoint omits logged events for '"+name+"'");
    auto events=state.events;counts_.swap(next);events_.swap(events);++epoch_;
}
void NativeFallbacks::reset(){std::lock_guard<std::mutex> guard(mutex_);can_reset(epoch_);for(auto& [name,n]:counts_){(void)name;n=0;}events_.clear();++epoch_;}
void NativeQuantizations::record_count(const std::string& name,std::uint64_t n){std::lock_guard<std::mutex> guard(mutex_);increment(counts_,name,n);}
void NativeQuantizations::merge_counts(const NativeCounterMap& counts){std::lock_guard<std::mutex> guard(mutex_);auto next=add_counts(counts_,counts);counts_.swap(next);}
void NativeQuantizations::reset_engagements(){std::lock_guard<std::mutex> guard(mutex_);can_reset(epoch_);for(auto& [name,n]:counts_){(void)name;n=0;}++epoch_;}

bool NativeAccountingInbox::merge_once(const std::string& id,const NativeAccountingBatch& batch){
    if(id.empty())throw std::invalid_argument("native accounting: invocation ID must not be empty");
    std::scoped_lock guard(mutex_,quantize_.mutex_,fallbacks_.mutex_);
    if(!receipts_.empty()&&(quantize_epoch_!=quantize_.epoch_||fallback_epoch_!=fallbacks_.epoch_))
        throw std::logic_error("native accounting: registry restored/reset independently; reset the inbox for a new build");
    const auto p=receipts_.find(id);
    if(p!=receipts_.end()){
        if(p->second.quantization_engagements!=batch.quantization_engagements||p->second.fallback_events!=batch.fallback_events)
            throw std::logic_error("native accounting: changed payload for invocation '"+id+"'");
        return false;
    }
    // Prepare everything before any registry/receipt mutation. Unknown labels,
    // numeric overflow and allocation failures leave both registries intact.
    auto q=add_counts(quantize_.counts_,batch.quantization_engagements);
    auto f=event_counts(fallbacks_.counts_,batch.fallback_events);
    auto events=fallbacks_.events_;events.insert(events.end(),batch.fallback_events.begin(),batch.fallback_events.end());
    auto receipts=receipts_;receipts.emplace(id,batch);
    quantize_.counts_.swap(q);fallbacks_.counts_.swap(f);fallbacks_.events_.swap(events);receipts_.swap(receipts);
    quantize_epoch_=quantize_.epoch_;fallback_epoch_=fallbacks_.epoch_;return true;
}
void NativeAccountingInbox::reset(){
    std::scoped_lock guard(mutex_,quantize_.mutex_,fallbacks_.mutex_);can_reset(quantize_.epoch_);can_reset(fallbacks_.epoch_);
    for(auto& [name,n]:quantize_.counts_){(void)name;n=0;}for(auto& [name,n]:fallbacks_.counts_){(void)name;n=0;}
    fallbacks_.events_.clear();receipts_.clear();++quantize_.epoch_;++fallbacks_.epoch_;
    quantize_epoch_=quantize_.epoch_;fallback_epoch_=fallbacks_.epoch_;
}
} // namespace schgen
