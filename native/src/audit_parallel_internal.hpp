#pragma once
#include <algorithm>
#include <atomic>
#include <exception>
#include <future>
#include <stdexcept>
#include <vector>

namespace schgen::audit_detail {
// Callbacks own disjoint output slots. Join every launched job, and report the
// earliest input-index failure, not whichever compiler finishes first. Reuse
// this bound for sequential audit phases; never nest the worker pools.
template<class Work> void for_each_input(std::size_t count,std::size_t worker_count,Work work) {
    if(worker_count<1||worker_count>4)throw std::invalid_argument("native audit workers must be between 1 and 4");
    if(worker_count==1||count<2){for(std::size_t i=0;i<count;++i)work(i);return;}
    std::atomic<std::size_t> next{0},first_failed{count};
    std::vector<std::exception_ptr> failed(count);
    std::vector<std::future<void>> workers;
    for(std::size_t w=0;w<std::min(count,worker_count);++w)
        workers.push_back(std::async(std::launch::async,[&]{
            for(;;){
                const auto i=next.fetch_add(1,std::memory_order_relaxed);
                // Every earlier index has already been claimed when i fails.
                // Finish those jobs; later jobs cannot change error priority.
                if(i>=count||i>=first_failed.load(std::memory_order_relaxed))return;
                try{work(i);}
                catch(...){
                    failed[i]=std::current_exception();
                    auto limit=first_failed.load(std::memory_order_relaxed);
                    while(i<limit&&!first_failed.compare_exchange_weak(limit,i,std::memory_order_relaxed)){}
                }
            }
        }));
    for(auto& worker:workers)worker.get();
    for(const auto& error:failed)if(error)std::rethrow_exception(error);
}
}
