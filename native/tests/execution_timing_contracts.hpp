#pragma once
#include "schgen/execution_timing.hpp"
#include <stdexcept>
#include <numeric>
#include <type_traits>
#include <memory>

namespace execution_timing_contracts {
inline schgen::ExecutionTimings::Clock::time_point instant{};
inline auto now(){return instant;}
inline void advance(int seconds){instant+=std::chrono::seconds(seconds);}
inline void run(){
    using T=schgen::ExecutionTimings;
    static_assert(!std::is_copy_constructible_v<T> && !std::is_copy_assignable_v<T>);
    static_assert(!std::is_move_constructible_v<T> && !std::is_move_assignable_v<T>);
    static_assert(!std::is_copy_constructible_v<T::Scope> && !std::is_move_constructible_v<T::Scope>);
    const auto require=[](bool ok){if(!ok)throw std::runtime_error("exclusive timing contract failed");};
    T::Rows rows;T timing(true,rows,&now);
    {
        T::Scope root(&timing,"other");advance(2);
        {T::Scope input(&timing,"inputs");advance(3);
            {T::Scope audit(&timing,"authoring_audit");advance(11);}advance(5);}
        try{T::Scope audit(&timing,"source_audit");advance(7);throw std::runtime_error("failed audit");}
        catch(const std::runtime_error&){}
        {T::Scope repeated(&timing,"inputs");advance(1);}
        advance(4);root.finish();root.finish();advance(100);
    }
    require(rows==T::Rows{{"other",6},{"inputs",9},{"authoring_audit",11},{"source_audit",7}});
    const auto total=std::accumulate(rows.begin(),rows.end(),0.,[](double n,const auto& r){return n+r.second;});
    require(total==33); // The 100 seconds outside the closed root are excluded.
    T::Rows absent;T disabled(false,absent,&now);bool executed=false;
    {T::Scope a(&disabled,"audit");executed=true;advance(10);}
    require(executed&&absent.empty());
    {T::Scope a(nullptr,"optional observer");advance(1);}
    // Reentrant labels aggregate exclusive intervals rather than double count.
    T::Rows same;T recursive(true,same,&now);
    {T::Scope a(&recursive,"same");advance(1);{T::Scope b(&recursive,"same");advance(2);}advance(3);}
    require(same==T::Rows{{"same",6}});
    T::Rows early;T early_owner(true,early,&now);
    {
        T::Scope root(&early_owner,"root");advance(2);
        {T::Scope parent(&early_owner,"parent");advance(3);
            {T::Scope child(&early_owner,"child");advance(4);
                parent.finish();advance(5);root.finish();advance(6);}
            advance(10);}
    }
    require(early==T::Rows{{"root",2},{"parent",3},{"child",15}});
    // Destruction of a non-current parent must not leave a dangling link.
    T::Rows detached;T detached_owner(true,detached,&now);
    auto parent=std::make_unique<T::Scope>(&detached_owner,"parent");advance(1);
    {T::Scope child(&detached_owner,"child");advance(2);parent.reset();advance(3);}
    require(detached==T::Rows{{"parent",1},{"child",5}});
}
}
