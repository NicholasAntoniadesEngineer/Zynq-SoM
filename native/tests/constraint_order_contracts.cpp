// Reuse the independent instrumented single-attempt oracle and rollback cases.
#define main original_retry_main
#include "compact_retry_contracts.cpp"
#undef main
#include "constraint_order_internal.hpp"

namespace {
void candidate_check(const Case& c) {
    auto in = input();
    auto experiment = std::make_shared<FloorplanExperiment>();
    experiment->compact_constraint_first = true;
    in.experiment = experiment;
    Engine e(in); setup(e, c);
    const auto start = layout(e.plan);
    const auto start_offers = offers(e);
    QuantizationCounts expected{{"entry-sentinel", 19}};
    std::vector<std::string> events{"entry-fallback"};
    std::optional<Result> accepted;
    std::size_t calls = 0;
    for (int order : {3,0,1,2}) {
        auto r = trial(in, c, order);
        calls += r.calls;
        auto delta = r.plan.accounting.quantization_engagements;
        delta.erase("entry-sentinel");
        checked_quantization_merge(expected, delta);
        events.insert(events.end(), r.plan.accounting.fallback_events.begin()+1,
                      r.plan.accounting.fallback_events.end());
        if (r.ok) { accepted = std::move(r); break; }
    }
    entries = 0; observing = true;
    const bool ok = e.attempt_pack(false);
    observing = false;
    require(entries == calls, "constraint schedule differs from actual scalar-entry count");
    require(ok == bool(accepted), "constraint schedule result mismatch");
    require(e.plan.accounting.quantization_engagements == expected, "constraint retry work lost/duplicated");
    require(e.plan.accounting.fallback_events == events, "constraint fallback identities/order changed");
    require(equal(layout(e.plan), accepted ? layout(accepted->plan) : start), "constraint layout rollback mismatch");
    require(offers(e) == (accepted ? accepted->side : start_offers), "constraint offers rollback mismatch");
    require(e.compact_order == 0, "constraint order leaked after return");
}
void isolation_check() {
    const Case c{70,50,{{29,16,3,4},{12,30,2,0},{30,18,3,2},{31,26,2,3},{7,7,1,3},{31,9,2,1}}};
    auto baseline = input(); baseline.compact_search = false;
    Engine a(baseline); setup(a,c); const bool original_ok = a.attempt_pack(false);
    auto enabled = baseline;
    auto experiment = std::make_shared<FloorplanExperiment>();
    experiment->compact_constraint_first = true;
    enabled.experiment = experiment;
    Engine b(enabled); setup(b,c);
    require(b.attempt_pack(false) == original_ok, "experiment changed noncompact result");
    require(equal(floorplan_plan_json(a.plan), floorplan_plan_json(b.plan)) && offers(a) == offers(b),
            "experiment changed noncompact state or work");
    baseline.compact_search = true;
    Engine first(baseline); setup(first,c); const bool before = first.attempt_pack(false);
    candidate_check(c);
    Engine second(baseline); setup(second,c);
    require(second.attempt_pack(false) == before &&
            equal(floorplan_plan_json(first.plan), floorplan_plan_json(second.plan)) && offers(first) == offers(second),
            "candidate solve contaminated a later baseline invocation");
}
} // namespace
int main() {
    try {
        require(original_retry_main() == 0, "existing retry contracts failed");
        FloorplanTermIndex terms;
        const auto add = [&](std::string a, std::string b, bool enforced) {
            FloorplanTerm t; t.subject = a; t.target_raw = b; t.kind = "near_max"; t.enforced = enforced;
            terms.hard.push_back(t);
        };
        add("a","b.pin",true); add("a","a.pin",true); add("b","c",false); add("c","a",true);
        terms.soft = terms.hard; terms.na = terms.hard;
        const auto counts = floorplan_detail::hard_constraint_incidence(terms);
        require(counts.at("a") == 3 && counts.at("b") == 1 && counts.at("c") == 1,
                "enforced hard incidence must count both endpoints, self once, and ignore soft/NA");
        FloorplanBlock a,b,c,d,e; a.name="a"; b.name="b"; c.name="c"; d.name="d"; e.name="e";
        std::vector<FloorplanBlock*> blocks{&e,&d,&b,&c,&a};
        floorplan_detail::sort_constraint_first(blocks,terms,
            {{"a",{1,1}},{"b",{2,2}},{"c",{3,3}},{"d",{99,99}},{"e",{99,99}}});
        require(blocks == std::vector<FloorplanBlock*>{&a,&c,&b,&e,&d}, "incidence/area/stable tie priority mismatch");
        candidate_check({80,70,{{8,6,2,1},{7,5,2,0}}});
        candidate_check({70,60,{{9,16,1,0},{18,27,2,1},{25,14,2,0},{11,29,1,1},{27,30,1,1},{31,7,1,0},{30,18,3,1}}});
        candidate_check({80,70,{{8,6,2,100},{90,80,1,0}}});
        isolation_check();
        exception_contract(true);
        std::cout << "constraint-first candidate: ordering, receipts, rollback and invocation isolation PASS\n";
    } catch (const std::exception& e) {
        observing = false; std::cerr << e.what() << '\n'; return 1;
    }
}
