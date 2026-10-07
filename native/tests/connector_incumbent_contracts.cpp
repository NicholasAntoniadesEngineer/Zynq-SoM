// Test-only instrumentation: floorplan_geometry.cpp, precision_ops.cpp and
// native_audit_quantize.cpp. No production callbacks or external memoization.
#include "floorplan_internal.hpp"
#include "native_audit_quantize_internal.hpp"
#include "schgen/precision_ops.hpp"
#include <cstring>
#include <algorithm>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <type_traits>

namespace incumbent_test {
using namespace schgen;
using floorplan_detail::Engine;
void require(bool ok, const std::string& message) { if (!ok) throw std::runtime_error(message); }
struct Writer {
    std::ostringstream out;
    Writer() { out << std::setprecision(17); }
    template<class T, std::enable_if_t<std::is_arithmetic_v<T>, int> = 0>
    void put(T x) { out << x << ' '; }
    void put(const std::string& x) { out << std::quoted(x) << ' '; }
    template<class... T> void values(const T&... x) { (put(x), ...); }
    template<class A, class B> void put(const std::pair<A,B>& x) { values(x.first,x.second); }
    template<class... T> void put(const std::tuple<T...>& x) { std::apply([&](const auto&... v) { values(v...); },x); }
    template<class T> void put(const std::optional<T>& x) { put(bool(x)); if(x) put(*x); }
    template<class T> void range(const T& x) { put(x.size()); for(const auto& v:x) put(v); }
    template<class T> void put(const std::vector<T>& x) { range(x); }
    template<class K, class V> void put(const std::map<K,V>& x) { range(x); }
    template<class T, std::size_t N> void put(const std::array<T,N>& x) { range(x); }
    void put(const Box4& b) { values(b.x0,b.y0,b.x1,b.y1); }
    void put(const Halo& h) { values(h.w,h.e,h.n,h.s); }
    void put(const Comp& c) { values(c.dx,c.dy,c.w,c.h,c.mask,c.reach,c.inset); }
    void put(const floorplan_detail::CachedFootprint& f) { values(f.bbox,f.pins,f.has_thru,f.pads); }
    void put(const floorplan_detail::Shape& s) { values(s.w,s.h,s.reach,s.inset,s.side,s.comps); }
    void put(const floorplan_detail::SideOffer& s) { values(s.offered,s.chosen,s.shape,s.incumbent,s.challenger); }
    void put(const floorplan_detail::CrossPart& p) {
        values(static_cast<int>(p.owner),p.ref,p.sheet,p.key,p.footprint,p.base_side,
            p.owner_index,p.offset,p.shape_offsets,p.pad_positions);
    }
    void put(const floorplan_detail::CrossNetPin& p) { values(p.part,p.pin); }
    void put(const floorplan_detail::CrossNet& n) { values(n.name,n.pins,n.via_cost); }
    void put(const JsonNode& n) {
        put(static_cast<int>(n.kind));
        switch(n.kind) {
        case JsonKind::Null: break;
        case JsonKind::Bool: put(n.bool_value); break;
        case JsonKind::Number: put(n.number_value); break;
        case JsonKind::String: put(n.string_value); break;
        case JsonKind::Array: put(n.array_value); break;
        case JsonKind::Object: put(n.object_value); break;
        }
    }
};
std::string static_state(const Engine& e) {
    Writer w;
    // Every Engine member other than plan/side_offers is covered explicitly.
    w.put(reinterpret_cast<std::uintptr_t>(&e.in));
    for(const auto& [name,sheet]:e.sheets) w.values(name,reinterpret_cast<std::uintptr_t>(sheet));
    w.values(e.footprint_cache,e.zbox,e.edge_of,e.affinity,e.som_pull,e.channel_demand,
        e.components,e.shape_sets,e.cross_parts,e.cross_nets,e.nets_by_sheet,e.connector_pad_boxes,
        e.far_ceil,e.max_reach,e.raw_area,e.n_sub,e.n_impedance,e.impedance_classes,e.offset,e.compact_order);
    return w.out.str();
}
std::string plan_state(FloorplanPlan p) {
    p.accounting.quantization_engagements.clear(); p.accounting.fallback_events.clear();
    Writer w; w.put(floorplan_plan_json(p));
    // Include optional pull fields even when the export-presence flags omit them.
    for(const auto* blocks:{&p.edge_blocks,&p.interior_blocks}) for(const auto& b:*blocks) if(b.pull)
        w.values(b.pull->face,b.pull->exclusive,b.pull->face_present,b.pull->exclusive_present);
    return w.out.str();
}
std::string offers(const Engine& e) { Writer w; w.put(e.side_offers); return w.out.str(); }
thread_local bool watching=false,busy=false,observer_failed=false;
thread_local Engine* active=nullptr;
thread_local std::size_t fallback_entries=0,tolerance_entries=0,position_entries=0,pad_entries=0;
thread_local std::vector<std::string> event_names;
void* fallback_address=nullptr;
void setup() {
    struct Member { void* code; std::ptrdiff_t adjustment; };
    const auto method=&Engine::fallback;
    static_assert(sizeof(method)==sizeof(Member),"requires GNU/Clang Itanium member-pointer ABI");
    Member m{};std::memcpy(&m,&method,sizeof m);
    require(m.code && m.adjustment==0,"nonvirtual unadjusted Engine::fallback");fallback_address=m.code;
}
void begin(Engine* e) {
    active=e;fallback_entries=tolerance_entries=position_entries=pad_entries=0;
    event_names.clear();observer_failed=false;watching=true;
}
void end() { watching=false;active=nullptr;require(!observer_failed,"independent observer failed"); }
std::size_t count(const QuantizationCounts& q,const std::string& key) {const auto i=q.find(key);return i==q.end()?0:i->second;}
void receipt(const FloorplanAccounting& a,const FloorplanAccounting& prefix,bool names) {
    require(count(a.quantization_engagements,"run_overflow_tol")-count(prefix.quantization_engagements,"run_overflow_tol")==tolerance_entries,"tolerance receipt != actual scalar entries");
    require(count(a.quantization_engagements,"estimate_position_precision")-count(prefix.quantization_engagements,"estimate_position_precision")==position_entries,"position receipt != actual scalar entries");
    require(count(a.quantization_engagements,"estimate_pad_precision")-count(prefix.quantization_engagements,"estimate_pad_precision")==pad_entries,"pad receipt != actual scalar entries");
    require(a.fallback_events.size()==prefix.fallback_events.size()+fallback_entries,"fallback receipt != actual calls");
    if(names) {
        auto expected=prefix.fallback_events;expected.insert(expected.end(),event_names.begin(),event_names.end());
        require(a.fallback_events==expected,"fallback identities/order changed");
    }
}
struct Injected : std::runtime_error { Injected():std::runtime_error("connector trial injected failure") {} };
FloorplanInput small(bool compact) {
    FloorplanInput in;in.som.w=in.som.h=20;in.compact_search=compact;
    in.spec=FloorplanSpec{};in.spec->outline={{100,100}};in.spec->edges["N"]={"edge"};
    for(const auto* name:{"edge","logic"}) {
        CircuitSheetIr s;s.name=name;in.sheets.push_back(s);in.geometry.zone_box[name]={12,8};
        FloorplanZoneShape shape;shape.w=12;shape.h=8;in.geometry.shapes[name]={shape,shape};
    }
    in.accounting.fallback_events={"interior_reseat_retry","legalize_only_compaction","interior_reseat_retry"};
    return in;
}
void unit(bool compact,bool fail_pack) {
    auto in=small(compact);auto observer=std::make_shared<FloorplanExperiment>();in.experiment=observer;
    if(fail_pack) {
        // Only the alternate north connector has an oversized fanout. The
        // unchanged east connector forces a genuine cross-edge rejection.
        CircuitSheetIr s;s.name="other_edge";in.sheets.push_back(s);
        in.spec->edges["E"]={s.name};in.geometry.zone_box[s.name]={12,8};
        in.footprints["wide"]={"synthetic-wide",sexpr_loads(R"((footprint "wide"
            (pad "1" smd rect (at 0 0) (size 1 1))
            (pad "2" smd rect (at 1 0) (size 1 1))
            (pad "3" smd rect (at 2 0) (size 1 1))))")};
        in.geometry.resolvable["U999"]="wide";
        in.geometry.bbox_of["U999"]={-1000,-1000,1000,1000};
        in.geometry.shapes.at("edge")[1].top_off["U999"]={0,0};
    }
    Engine engine(in);engine.initialize();engine.prepare_geometry();engine.prepare_cross();engine.board_size(100,100);
    require(engine.attempt_pack(true),"synthetic accepted initial plan");
    engine.plan.composition={"accepted composition"};engine.plan.spilled={"accepted spill diagnostic"};
    engine.side_offers["sentinel"]={"accepted offers","top",7,3.0,4.0};
    const auto before=plan_state(engine.plan),side_before=offers(engine),other_before=static_state(engine);
    const auto prefix=engine.plan.accounting;
    std::size_t attempts=0;bool packed=false;
    observer->attempt_completed=[&](const auto& row) {
        ++attempts;packed=row.packed;
        // Explicit receipt-only sentinel tests retention after a rejected trial.
        engine.fallback("legalize_only_compaction");
        (void)engine.quantize("fixed_part_grid",1.234);
        engine.plan.composition={"trial composition"};
        engine.side_offers["sentinel"]={"trial offers","bottom",1,8.0,9.0};
    };
    // Independently execute exactly the attempted mirror, without restoration.
    auto reference=engine;observer->attempt_completed=[&](const auto& row) {
        ++attempts;packed=row.packed;reference.fallback("legalize_only_compaction");
        (void)reference.quantize("fixed_part_grid",1.234);
        reference.plan.composition={"trial composition"};
        reference.side_offers["sentinel"]={"trial offers","bottom",1,8.0,9.0};
    };
    const double base=reference.estimate();
    auto& b=reference.plan.edge_blocks.front();
    std::tie(b.fanout_reach,b.fanout_inset)=reference.fanout(in.geometry.shapes.at("edge")[1],false);b.shape_idx=1;
    const bool fits=reference.attempt_pack(true);
    require(!(fits&&reference.estimate()<base-1e-6),"synthetic mirror must reject");
    const auto wanted=reference.plan.accounting;
    observer->attempt_completed=[&](const auto& row) {
        ++attempts;packed=row.packed;engine.fallback("legalize_only_compaction");
        (void)engine.quantize("fixed_part_grid",1.234);
        engine.plan.composition={"trial composition"};
        engine.side_offers["sentinel"]={"trial offers","bottom",1,8.0,9.0};
    };
    attempts=0;begin(&engine);engine.choose_connector_shapes();end();
    require(attempts==1&&packed==fits,"one real mirror attempt; no restoration attempt");
    require(!fail_pack||!fits,"forced actual pack rejection exercised");
    require(plan_state(engine.plan)==before&&offers(engine)==side_before,"complete accepted plan and side offers restored");
    require(static_state(engine)==other_before,"unexpected mutable Engine member");
    require(engine.plan.accounting.quantization_engagements==wanted.quantization_engagements&&engine.plan.accounting.fallback_events==wanted.fallback_events,"trial receipt exact, no omitted/doubled work");
    receipt(engine.plan.accounting,prefix,true);
}
void failure(bool compact,bool at_estimate) {
    auto in=small(compact);auto observer=std::make_shared<FloorplanExperiment>();in.experiment=observer;
    std::size_t attempts=0,estimates=0;
    observer->attempt_completed=[&](const auto&) {if(++attempts==2&&!at_estimate)throw Injected();};
    observer->unscoped_estimate=[&](double) {if(++estimates==2&&at_estimate)throw Injected();};
    Engine e(in);bool threw=false;begin(&e);
    try {(void)e.run();}catch(const Injected&){threw=true;}end();
    require(threw&&attempts==2,"throw from actual connector trial");receipt(e.plan.accounting,in.accounting,true);
    const auto expected=e.plan.accounting;const auto calls=tolerance_entries;
    attempts=estimates=0;ExecutionFailureReceipt failed;threw=false;begin(nullptr);
    try {(void)build_floorplan(in,&failed);}catch(const Injected&){threw=true;}end();
    require(threw&&failed.captured&&!failed.unavailable&&tolerance_entries==calls,"original exception and public failure receipt");
    require(failed.accounting.quantization_engagements==expected.quantization_engagements&&failed.accounting.fallback_events==expected.fallback_events,"public exception transport exact prefix");
    FloorplanAccounting a;a.quantization_engagements=failed.accounting.quantization_engagements;a.fallback_events=failed.accounting.fallback_events;
    receipt(a,in.accounting,false);
}
} // namespace incumbent_test
extern "C" void __cyg_profile_func_enter(void* fn,void*) {
    using namespace incumbent_test;if(!watching||busy)return;
    if(fn==fallback_address)++fallback_entries;
    if(fn==reinterpret_cast<void*>(&schgen::native_run_overflow_tol))++tolerance_entries;
    if(fn==reinterpret_cast<void*>(&schgen::estimate_position_precision))++position_entries;
    if(fn==reinterpret_cast<void*>(&schgen::estimate_pad_precision))++pad_entries;
}
extern "C" void __cyg_profile_func_exit(void* fn,void*) {
    using namespace incumbent_test;if(!watching||busy||fn!=fallback_address||!active)return;busy=true;
    try {event_names.push_back(active->plan.accounting.fallback_events.back());}catch(...){observer_failed=true;}
    busy=false;
}
int main() {
    try {
        incumbent_test::setup();
        for(bool compact:{false,true}) {
            for(bool failed:{false,true})incumbent_test::unit(compact,failed);
            for(bool estimate:{false,true})incumbent_test::failure(compact,estimate);
        }
        std::cout<<"PASS complete incumbent state, exact trial accounting, actual calls and failure transport\n";
    }catch(const std::exception& e){incumbent_test::watching=false;std::cerr<<e.what()<<'\n';return 1;}
}
