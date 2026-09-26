#pragma once
#include <chrono>
#include <string>
#include <utility>
#include <vector>

namespace schgen {
// Single-owner wall-clock partition. Nested scopes pause their parent; worker
// batches must be timed around launch/join by their owner, never by each worker.
// Observes execution only: disabled timing never disables the measured action.
class ExecutionTimings {
public:
    using Clock = std::chrono::steady_clock;
    using Rows = std::vector<std::pair<std::string,double>>;
    using Now = Clock::time_point (*)();
    ExecutionTimings(bool enabled, Rows& rows, Now now = &Clock::now)
        : enabled_(enabled), rows_(rows), now_(now) {}
    // Live scopes retain this object's address; copying or moving the owner
    // would split its active-scope chain and corrupt exclusive accounting.
    ExecutionTimings(const ExecutionTimings&) = delete;
    ExecutionTimings& operator=(const ExecutionTimings&) = delete;
    ExecutionTimings(ExecutionTimings&&) = delete;
    ExecutionTimings& operator=(ExecutionTimings&&) = delete;
    class Scope {
    public:
        Scope(ExecutionTimings* owner, const std::string& name) {
            if (!owner || !owner->enabled_) return;
            index_ = 0;
            while (index_ < owner->rows_.size() && owner->rows_[index_].first != name) ++index_;
            if (index_ == owner->rows_.size()) owner->rows_.emplace_back(name, 0.0);
            owner->settle();
            owner_ = owner; previous_ = owner->active_; owner->active_ = this;
        }
        Scope(const Scope&) = delete;
        Scope& operator=(const Scope&) = delete;
        ~Scope() { finish(); }
        void finish() noexcept {
            if (!owner_) return;
            owner_->settle();
            // A parent may be explicitly closed before its child. Unlink only
            // this scope, leaving the child's interval active and preventing
            // it from later resuming a closed (or destroyed) parent.
            auto** link = &owner_->active_;
            while (*link && *link != this) link = &(*link)->previous_;
            if (*link) *link = previous_;
            owner_ = nullptr;
        }
    private:
        friend class ExecutionTimings;
        ExecutionTimings* owner_ = nullptr;
        Scope* previous_ = nullptr;
        std::size_t index_ = 0;
    };
private:
    void settle() noexcept {
        const auto now = now_();
        if (active_) rows_[active_->index_].second += std::chrono::duration<double>(now-last_).count();
        last_ = now;
    }
    bool enabled_;
    Rows& rows_;
    Now now_;
    Scope* active_ = nullptr;
    Clock::time_point last_{};
};
}
