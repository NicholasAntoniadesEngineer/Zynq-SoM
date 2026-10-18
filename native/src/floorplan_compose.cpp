#include "floorplan_internal.hpp"
#include "schgen/legalize_precision.hpp"
#include "schgen/board_decision_policy.hpp"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <limits>

namespace schgen {
namespace {
using namespace board_decision_policy::compose;

void finite(double value, const std::string& where) {
    if (!std::isfinite(value))
        throw FloorplanError("floorplan compose: non-finite " + where);
}
void point(FloorplanPoint p, const std::string& where) {
    finite(p.first, where); finite(p.second, where);
}
void rectangle(const Box4& r, const std::string& where) {
    point({r.x0, r.y0}, where); point({r.x1, r.y1}, where);
    if (r.x0 > r.x1 || r.y0 > r.y1)
        throw FloorplanError("floorplan compose: inverted rectangle " + where);
}
void validate(const FloorplanLegalizeInput& in) {
    if(in.joint_separation_states&&(!*in.joint_separation_states||*in.joint_separation_states>std::numeric_limits<std::size_t>::max()/2))
        throw FloorplanError("floorplan compose: invalid joint separation state limit");
    finite(in.board_w, "board width"); finite(in.board_h, "board height");
    finite(in.clear, "clearance"); point(in.origin, "origin");
    if (in.board_w <= 0 || in.board_h <= 0 || in.clear < 0)
        throw FloorplanError("floorplan compose: invalid board dimensions/clearance");
    rectangle(in.som_core_page, "SoM core");
    std::set<std::string> fixed_names;
    for (const auto& [name, r] : in.fixed_rects) {
        if (name.empty() || name.front() == '#' || !fixed_names.insert(name).second)
            throw FloorplanError("floorplan compose: invalid or duplicate fixed name " + name);
        rectangle(r, name);
    }
    for (const auto& [name, r] : in.som_j_rects) rectangle(r, name);
    for (const auto& [name, p] : in.fixed_poses) point(p, name);
    for (const auto& [name, body] : in.primary_fanout) {
        if (name.empty() || name.front() == '#' || body.mask < 0 || body.mask > 3)
            throw FloorplanError("floorplan compose: invalid primary fanout identity/mask " + name);
        if(body.occupied_mask<0||body.occupied_mask>3||
           (body.occupied_mask&&((!body.mask&&!body.component_only)||(body.occupied_mask&body.mask)!=body.mask)))
            throw FloorplanError("floorplan compose: invalid complete occupancy mask " + name);
        if(body.component_only&&
           (body.mask||!body.occupied_mask||!body.children||body.children->empty()))
            throw FloorplanError("floorplan compose: incomplete component-only reservations "+name);
        if(body.children) {
            int faces=body.mask;
            for(const auto& child:*body.children) {
                for(double v:{child.dx,child.dy,child.w,child.h})finite(v,name+" child reservation");
                if(child.w<=0||child.h<=0||child.mask<1||child.mask>3)
                    throw FloorplanError("floorplan compose: invalid child reservation "+name);
                for(const auto& h:{child.reach,child.inset})for(double v:{h.w,h.e,h.n,h.s})finite(v,name+" child fanout");
                faces|=child.mask;
            }
            if((!body.mask&&!body.component_only)||faces!=body.occupied_mask)
                throw FloorplanError("floorplan compose: child reservation face census mismatch "+name);
        }
        for (const auto& halo : {body.reach, body.inset})
            for (double value : {halo.w, halo.e, halo.n, halo.s}) {
                finite(value, name + " primary fanout");
                if(body.component_only&&value!=0)
                    throw FloorplanError("floorplan compose: component-only fanout must belong to children "+name);
            }
    }
    for (const auto& [name, m] : in.metrics) {
        point(m.zone_wh, name);
        std::set<std::string> refs;
        for (const auto& [ref, x, y] : m.offsets) {
            point({x, y}, name + "/" + ref);
            if (!refs.insert(ref).second)
                throw FloorplanError("floorplan compose: duplicate metric offset " + name + "/" + ref);
        }
        for (const auto& [ref, x0, y0, x1, y1] : m.pad_union) {
            rectangle({x0, y0, x1, y1}, name + "/" + ref);
            if (!refs.count(ref))
                throw FloorplanError("floorplan compose: pad union has no offset " + name + "/" + ref);
        }
    }
    const std::set<std::string> kinds{"flow_hop", "near_max", "near_intent", "far_min", "facing"};
    for (const auto* terms : {&in.index.hard, &in.index.soft}) for (const auto& t : *terms) {
        if (!kinds.count(t.kind))
            throw FloorplanError("floorplan compose: unknown term kind " + t.kind);
        if(t.prefer_short_flow&&t.kind!="flow_hop")
            throw FloorplanError("floorplan compose: flow preference on non-flow term");
        if (t.subject.empty() || t.target().empty())
            throw FloorplanError("floorplan compose: empty term endpoint");
        if (t.bound) finite(*t.bound, "term bound");
    }
    for (const auto& [pair, demand] : in.channel_demand) {
        (void)pair;
        if (demand < 0) throw FloorplanError("floorplan compose: negative channel demand");
    }
}

std::vector<FloorplanTermEval> evaluate(const FloorplanLegalizeInput& in,
                                       const FloorplanOffsets& poses, QuantizationCounts* counts = nullptr,
                                       bool enforced_only = false) {
    std::vector<const FloorplanTerm*> terms;
    std::vector<EvalTermIn> rows;
    for (const auto* group : {&in.index.hard, &in.index.soft}) for (const auto& t : *group) {
        if(enforced_only&&!t.enforced)continue;
        terms.push_back(&t);
        rows.push_back({t.kind, t.subject, t.target(), t.bound.value_or(0), t.bound.has_value(), t.out_refs});
    }
    std::vector<EvalMetric> metrics;
    for (const auto& [name, m] : in.metrics) metrics.push_back({name, m.offsets, m.pad_union});
    std::vector<EvalTermIn> strict_rows, guarded_rows;
    std::vector<std::size_t> strict_indices, guarded_indices;
    for (std::size_t i = 0; i < terms.size(); ++i) {
        const auto& t = *terms[i];
        const bool strict = t.kind == "facing" && (!t.enforced || t.require_positive_facing);
        (strict ? strict_rows : guarded_rows).push_back(rows[i]);
        (strict ? strict_indices : guarded_indices).push_back(i);
    }
    std::vector<EvalTermOut> values;
    if (strict_rows.empty()) {
        // Preserve the legacy call, guards, row order and exact work receipts.
        values = evaluate_terms(in.board_w, in.board_h, in.som_core_page,
            {poses.begin(), poses.end()}, metrics, rows, {{"ethernet", 14}, {"power_som", 25}},
            {in.som_j_rects.begin(), in.som_j_rects.end()}, in.origin.first, in.origin.second, counts);
    } else {
        values.resize(rows.size());
        if (!guarded_rows.empty()) {
            const auto evaluated = evaluate_terms(in.board_w, in.board_h, in.som_core_page,
                {poses.begin(), poses.end()}, metrics, guarded_rows, {{"ethernet", 14}, {"power_som", 25}},
                {in.som_j_rects.begin(), in.som_j_rects.end()}, in.origin.first, in.origin.second, counts);
            for (std::size_t i = 0; i < guarded_indices.size(); ++i)
                values[guarded_indices[i]] = evaluated[i];
        }
        // Strict facing and advisory measurements lose L4 deferral: an advisory
        // must report its real negative value, not a guarded false-green.
        // Far/flow guards remain intact.
        // Evaluate each row once and import actual work even on rejection.
        const auto evaluated = evaluate_terms(in.board_w, in.board_h, in.som_core_page,
            {poses.begin(), poses.end()}, metrics, strict_rows, {},
            {in.som_j_rects.begin(), in.som_j_rects.end()}, in.origin.first, in.origin.second, counts);
        for (std::size_t i = 0; i < strict_indices.size(); ++i)
            values[strict_indices[i]] = evaluated[i];
    }
    std::vector<FloorplanTermEval> out;
    for (std::size_t i = 0; i < values.size(); ++i) {
        const auto& e = values[i];
        out.push_back({*terms[i], e.measured, e.bound, e.margin, e.ok, e.note});
    }
    return out;
}

std::string float_text(double value) {
    if (std::isinf(value)) return value < 0 ? "-inf" : "inf";
    char buffer[64];
    const auto r = std::to_chars(buffer, buffer + sizeof(buffer), value);
    if (r.ec != std::errc{}) throw FloorplanError("floorplan compose: cannot format margin");
    std::string s(buffer, r.ptr);
    if (s.find_first_of(".eE") == std::string::npos) s += ".0";
    return s;
}

struct TaggedEdge {
    NamedEdge edge;
    std::string kind;
    std::string source{};
};

enum class FacingAllocation { seed, y_capacity, x_capacity };
class Composer {
public:
    Composer(const FloorplanLegalizeInput& input,
             const std::vector<FloorplanLegalizeVar>& variables,
             std::vector<std::string>& output_log, QuantizationCounts* counts = nullptr,
             bool pad_seed_hulls = false, bool perpendicular_order = false,bool reservation_geometry=false,bool facing_cuts=false,
             FacingAllocation allocation=FacingAllocation::seed,
             std::optional<std::size_t> flipped_facing=std::nullopt)
        : in(input), log(output_log), counts(counts), fixed(input.fixed_poses), pad_seed_hulls(pad_seed_hulls), perpendicular_order(perpendicular_order), reservation_geometry(reservation_geometry) {
        for (const auto& v : variables) {
            if (v.name.empty() || v.name.front() == '#' || !by_name.emplace(v.name, &v).second)
                throw FloorplanError("floorplan compose: invalid or duplicate movable name " + v.name);
            for (double x : {v.w, v.h, v.x, v.y}) finite(x, v.name);
            point(v.seed, v.name + " seed");
            if (v.w <= 0 || v.h <= 0)
                throw FloorplanError("floorplan compose: nonpositive movable dimensions " + v.name);
            seed_rect[v.name] = {v.x, v.y, v.x + v.w, v.y + v.h};
        }
        for (const auto& [name, r] : in.fixed_rects) {
            if (by_name.count(name))
                throw FloorplanError("floorplan compose: name is both fixed and movable " + name);
            frect[name] = r;
        }
        for (const auto& [name, r] : in.som_j_rects) fixed[name] = {r.x0, r.y0};
        for (const auto& [name, v] : by_name) {
            names.push_back(name); pos_x.push_back(v->x); pos_y.push_back(v->y);
        }
        if (!in.primary_fanout.empty()) {
            for (const auto& name : names)
                if (!in.primary_fanout.count(name))
                    throw FloorplanError("floorplan compose: missing movable primary fanout " + name);
            for (const auto& [name, box] : frect) {
                (void)box;
                if (!in.primary_fanout.count(name))
                    throw FloorplanError("floorplan compose: missing fixed primary fanout " + name);
            }
            for (const auto& [name, body] : in.primary_fanout) {
                (void)body;
                if (!by_name.count(name) && !frect.count(name))
                    throw FloorplanError("floorplan compose: unknown primary fanout " + name);
            }
        }
        // A decomposed physical body must never pass through a coarse-only
        // solve/qualification, even when its envelopes happen not to overlap.
        reservation_geometry=reservation_geometry||std::any_of(in.primary_fanout.begin(),in.primary_fanout.end(),
            [](const auto& entry){return entry.second.component_only;});
        this->reservation_geometry=reservation_geometry;
        if(reservation_geometry)for(const auto& [name,body]:in.primary_fanout)if(body.children) {
            const auto variable=by_name.find(name);
            const auto box=variable==by_name.end()?frect.at(name):seed_rect.at(name);
            const double w=variable==by_name.end()?box.x1-box.x0:variable->second->w;
            const double h=variable==by_name.end()?box.y1-box.y0:variable->second->h;
            if(body.component_only)for(const auto& c:*body.children)
                if(c.dx<0||c.dy<0||c.dx+c.w>w||c.dy+c.h>h)
                    throw FloorplanError("floorplan compose: component outside declared envelope "+name);
            auto& out=local_reservations[name];out.reserve(1+body.children->size());
            out.push_back({0,0,w,h,body.reach,body.inset,body.mask,body.mask,true});
            for(const auto& c:*body.children)out.push_back({c.dx,c.dy,c.w,c.h,c.reach,c.inset,c.mask,body.mask,false});
        }
        if(facing_cuts)build_facing_cuts(allocation,flipped_facing);
    }

    bool changed_flip_order() const {return flip_order_differs;}
    using FacingCutKey=std::vector<std::tuple<bool,std::string,std::string,double>>;
    FacingCutKey facing_cut_key() const {
        // Compare exact emitted constraints, not allocation names or epsilon
        // proximity. A failed run can mutate positions and separation choices,
        // but these constructor-built facing cuts remain immutable.
        FacingCutKey result;
        for(const bool x:{true,false})for(const auto& e:x?facing_x:facing_y)
            result.emplace_back(x,e.edge.src,e.edge.dst,e.edge.cost);
        return result;
    }
    bool same_near_axes(const Composer& other) const {
        for(const bool x:{true,false}) {
            const auto a=extra(x),b=other.extra(x);
            if(a.size()!=b.size())return false;
            for(std::size_t i=0;i<a.size();++i)
                if(a[i].kind!=b[i].kind||a[i].edge.src!=b[i].edge.src||
                   a[i].edge.dst!=b[i].edge.dst||a[i].edge.cost!=b[i].edge.cost)return false;
        }
        return true;
    }
    bool full_authored_bounds_differ() {
        // These edges depend on immutable metrics and seed/fixed poses, not
        // search results. Compare actual emitted constraints, not term labels
        // or similar-looking failed search counters. Count all preparation.
        const bool old_distance=distance_envelope,old_full=full_distance_envelope;
        distance_envelope=true;
        const auto key=[&](bool full) {
            full_distance_envelope=full;
            std::vector<std::tuple<bool,std::string,std::string,std::string,double>> result;
            for(const bool x:{true,false})for(const auto& e:extra(x))
                result.emplace_back(x,e.kind,e.edge.src,e.edge.dst,e.edge.cost);
            return result;
        };
        const auto guarded=key(false),authored=key(true);
        distance_envelope=old_distance;full_distance_envelope=old_full;
        return guarded!=authored;
    }

    bool run(std::vector<FloorplanLegalizeVar>& movable,bool joint=false,bool authored_distance=false) {
        distance_envelope = joint;
        full_distance_envelope = joint&&authored_distance;
        if (movable.empty() || (in.index.hard.empty()&&
            std::none_of(in.index.soft.begin(),in.index.soft.end(),[](const auto& t){return t.prefer_short_flow;})&&
            std::none_of(in.primary_fanout.begin(),in.primary_fanout.end(),
                [](const auto& entry){return entry.second.component_only;}))) return true;
        std::vector<Box4> seeds, fixed_boxes;
        std::vector<std::string> fixed_names;
        for (const auto& name : names) seeds.push_back(seed_rect.at(name));
        for (const auto& [name, r] : frect) { fixed_names.push_back(name); fixed_boxes.push_back(r); }
        std::vector<std::tuple<std::string, std::string, int>> demand;
        for (const auto& [pair, n] : in.channel_demand) demand.emplace_back(pair.first, pair.second, n);
        std::vector<std::pair<std::string, std::string>> near;
        std::vector<std::vector<RepairSep>> domains;
        for (const auto& t : in.index.hard) if (t.kind == "near_max") near.emplace_back(t.subject, t.target());
        for (const auto& s : legalize_build_seps(names, seeds, fixed_names, fixed_boxes, demand, near,
                                                in.clear, channel_min_nets, channel_floor, channel_per_net)) {
            RepairSep sep{s.axis == "x", s.lo, s.hi, s.gap, s.flippable};
            sep.reverse_on_flip=perpendicular_order&&reverse_perpendicular(sep.lo,sep.hi,sep.axis_x);
            if (!in.primary_fanout.empty()) {
                const auto key=[](const std::string& name) { return name.front()=='#'?name.substr(1):name; };
                const auto& low=in.primary_fanout.at(key(s.lo));
                const auto& high=in.primary_fanout.at(key(s.hi));
                // A primary face alone cannot prove disjoint occupancy: a
                // mixed-face group or THT pad may reserve the opposite face.
                // Net-count channel widths are planar routing heuristics, not
                // hardware separation requirements across disjoint faces.
                // Explicit hard terms remain separate extra edges/qualification;
                // unknown masks and logical exclusions cannot use this proof.
                if(low.occupied_mask&&high.occupied_mask&&
                   !(low.occupied_mask&high.occupied_mask))continue;
                if (occ_pair_active(low.mask,low.mask,true,high.mask,high.mask,true)) {
                    const auto gap=[&](bool x) {
                        return std::max(s.gap,fanout_sep(low.reach,low.inset,high.reach,high.inset,x?'E':'S'));
                    };
                    sep.gap=gap(sep.axis_x);
                    sep.flipped_gap=sep.reverse_on_flip?
                        std::max(s.gap,fanout_sep(high.reach,high.inset,low.reach,low.inset,sep.axis_x?'S':'E')):
                        gap(!sep.axis_x);
                }
                // Opposite primary faces use their complete selected physical
                // reservations, not a net-count channel around both envelopes.
                // Exact child clearance/fanout and hard-term checks remain.
                if(reservation_geometry&&reservation_pair(key(s.lo),key(s.hi))) {
                    if(auto pocket=reservation_seed_seps(sep.lo,sep.hi,joint)) {
                        for(const auto& child:*pocket) {
                            seps.push_back(child.front());
                            if(joint)domains.push_back(child);
                        }
                        continue;
                    }
                    sep.projected_gap=true;
                    sep.gap=reservation_gap(sep.lo,sep.hi,sep.axis_x);
                    sep.flipped_gap=sep.reverse_on_flip?
                        reservation_gap(sep.hi,sep.lo,!sep.axis_x):reservation_gap(sep.lo,sep.hi,!sep.axis_x);
                }
            }
            if(joint){
                std::vector<RepairSep> domain{sep};
                if(s.flippable)for(const bool reverse:{false,true})for(const bool x:{true,false}){
                    const auto lo=reverse?s.hi:s.lo,hi=reverse?s.lo:s.hi;
                    if(x==sep.axis_x&&lo==sep.lo&&hi==sep.hi)continue;
                    RepairSep alternative{x,lo,hi,s.gap,false};
                    if(!in.primary_fanout.empty()){
                        const auto key=[](const std::string& name){return name.front()=='#'?name.substr(1):name;};
                        const auto& low=in.primary_fanout.at(key(lo));const auto& high=in.primary_fanout.at(key(hi));
                        if(occ_pair_active(low.mask,low.mask,true,high.mask,high.mask,true))
                            alternative.gap=std::max(s.gap,fanout_sep(low.reach,low.inset,high.reach,high.inset,x?'E':'S'));
                        if(reservation_geometry&&reservation_pair(key(lo),key(hi))){
                            alternative.projected_gap=true;alternative.gap=reservation_gap(lo,hi,x);
                        }
                    }
                    domain.push_back(std::move(alternative));
                }
                domains.push_back(std::move(domain));
            }
            seps.push_back(std::move(sep));
        }
        if(joint){
            std::vector<NamedEdge> ex,ey;for(const auto& e:extra(true))ex.push_back(e.edge);for(const auto& e:extra(false))ey.push_back(e.edge);
            JointSeparationWork work;auto candidate=movable;bool accepted=false;
            try{
                const auto result=legalize_joint_separations(names,sizes(true),sizes(false),in.board_w,in.board_h,in.clear,
                    domains,{frect.begin(),frect.end()},ex,ey,*in.joint_separation_states,&work,
                    [&](const auto& choices,const auto& x,const auto& y){
                        seps.clear();for(std::size_t i=0;i<choices.size();++i)seps.push_back(domains[i][choices[i]]);
                        pos_x=x;pos_y=y;descend(true);
                        if(!edges_ok(true,pos_x)||!edges_ok(false,pos_y))return false;
                        return finish(candidate,fixed_names,fixed_boxes,true);
                    });
                accepted=result.ok;
            }catch(...){if(in.joint_retry_completed)in.joint_retry_completed(work,false);throw;}
            log.push_back("joint separation: generated="+std::to_string(work.generated)+" visited="+std::to_string(work.visited)+
                " axes="+std::to_string(work.axis_solves)+" proposals="+std::to_string(work.qualifications)+
                " axis_reuse="+std::to_string(work.axis_cache_hits)+
                " domain_probes="+std::to_string(work.domain_probes)+" domain_rejections="+std::to_string(work.domain_rejections)+
                " rejected="+std::to_string(work.qualification_rejections)+" capped="+std::to_string(work.budget_exhausted));
            if(in.joint_retry_completed)in.joint_retry_completed(work,accepted);
            if(accepted)movable=std::move(candidate);
            return accepted;
        }
        if (!edges_ok(true, pos_x) || !edges_ok(false, pos_y)) {
            if (!repair(true, pos_x) || !repair(false, pos_y)) return false;
            descend(true);
            // Y repair can move a separation onto X after X was solved.
            // Coordinate descent cannot always restore feasibility: a chain
            // may need several bodies to move together before any one body's
            // interval is nonempty. Solve the final constraint assignment,
            // without allowing another flip to invalidate the opposite axis.
            bool reconciled=false;
            for(bool x:{true,false})if(!edges_ok(x,x?pos_x:pos_y)) {
                log.push_back(std::string("repair: reconcile ")+(x?"x":"y")+" constraints without flips");
                if(!repair(x,x?pos_x:pos_y,0))return false;
                reconciled=true;
            }
            if(reconciled)descend(true);
            for (bool x : {true, false}) for (const auto& e : edges(x)) {
                if (violated(e.edge, x ? pos_x : pos_y)) {
                    log.push_back(std::string("REJECT: ") + (x ? "x" : "y") +
                        "-edge unsatisfied after axis solve (" + e.kind + " " + e.edge.src + "|" +
                        e.edge.dst + ") — fixed-axis reconciliation failed");
                    return false;
                }
            }
        }
        return finish(movable,fixed_names,fixed_boxes);
    }
    bool finish(std::vector<FloorplanLegalizeVar>& movable,const std::vector<std::string>& fixed_names,
                const std::vector<Box4>& fixed_boxes,bool force_exact=false){
        const auto red = reds();
        if (!red.empty()) {
            std::string message = "REJECT: hard red after legalization: ";
            for (std::size_t i = 0; i < std::min<std::size_t>(4, red.size()); ++i) {
                const auto& e = red[i];
                if (i) message += "; ";
                message += e.term.kind + " " + e.term.subject + "->" + e.term.target_raw +
                    " margin " + float_text(e.margin);
            }
            log.push_back(std::move(message)); return false;
        }
        std::optional<std::pair<std::vector<double>,std::vector<double>>> precompact;
        if (in.compact) {
            if(in.compaction_started)in.compaction_started();
            auto keep_x = pos_x, keep_y = pos_y;
            descend(false);
            if (!reds().empty() || !edges_ok(true, pos_x) || !edges_ok(false, pos_y)) {
                pos_x = keep_x; pos_y = keep_y;
                log.push_back("compaction REVERTED (would break a hard term or separation)");
            } else {
                precompact=std::make_pair(std::move(keep_x),std::move(keep_y));
                log.push_back("compacted (wired hop pulls applied)");
            }
        }
        std::vector<Box4> boxes;
        const auto emit_grid=[&]{
            boxes.clear();
            for (std::size_t i = 0; i < names.size(); ++i) {
                const double x = legalize_trial_pose_precision4dp(pos_x[i], counts), y = legalize_trial_pose_precision4dp(pos_y[i], counts);
                const auto& v = *by_name.at(names[i]);
                boxes.push_back({x, y, x + v.w, y + v.h});
                pos_x[i]=x;pos_y[i]=y;
            }
        };
        emit_grid();
        const auto exact_holds=[&]{return physical_seps_ok()&&edges_ok(true,pos_x)&&edges_ok(false,pos_y)&&reds().empty();};
        const bool exact_required=force_exact||!in.primary_fanout.empty()||!facing_x.empty()||!facing_y.empty();
        bool exact_ok=!exact_required||exact_holds();
        // Optional compaction must not discard a feasible pre-compaction pose
        // merely because its grid-rounded result violates exact geometry.
        // Restore and independently recheck; never relax the failed predicate.
        if(precompact&&!exact_ok){
            pos_x=std::move(precompact->first);pos_y=std::move(precompact->second);
            log.push_back("compaction REVERTED (output-grid geometry or hard term)");
            emit_grid();
            exact_ok=exact_holds();
        }
        // Difference constraints and forward physical sums may associate
        // decimal-grid arithmetic differently. Try one actual output-grid
        // step at a movable separation endpoint, never an acceptance epsilon.
        // Each trial starts from the incumbent and must satisfy every exact
        // predicate; later child-geometry checks remain authoritative too.
        if (!exact_ok) {
            std::set<std::tuple<std::string,bool,bool>> tried;
            const auto endpoint=[&](const std::string& name,bool x,bool high) {
                if(name.front()=='#') {
                    const auto& b=frect.at(name.substr(1));
                    return x?(high?b.x1:b.x0):(high?b.y1:b.y0);
                }
                const auto i=static_cast<std::size_t>(std::lower_bound(names.begin(),names.end(),name)-names.begin());
                const auto& v=*by_name.at(name);
                return (x?pos_x[i]:pos_y[i])+(high?(x?v.w:v.h):0.);
            };
            for (const auto& sep : seps) {
                const double lower=endpoint(sep.lo,sep.axis_x,true)+sep.gap;
                const double upper=endpoint(sep.hi,sep.axis_x,false);
                if(lower<=upper||lower-upper>.0001)continue;
                for (bool high : {true,false}) {
                    const auto& name=high?sep.hi:sep.lo;
                    if(name.front()=='#')continue;
                    if(!tried.emplace(name,sep.axis_x,high).second)continue;
                    const auto i=static_cast<std::size_t>(std::lower_bound(names.begin(),names.end(),name)-names.begin());
                    auto& axis=sep.axis_x?pos_x:pos_y;
                    const auto incumbent=axis;
                    auto& coordinate=axis[i];
                    const double saved=coordinate;
                    coordinate=legalize_trial_pose_precision4dp(saved+(high?.0001:-.0001),counts);
                    log.push_back("output-grid trial: "+name+(sep.axis_x?" x ":" y ")+float_text(saved)+" -> "+float_text(coordinate));
                    exact_ok=coordinate!=saved&&std::isfinite(coordinate)&&exact_holds();
                    if(!exact_ok&&coordinate!=saved&&std::isfinite(coordinate)) {
                        // Propagate contact pressure along this axis. Each
                        // endpoint can move by one tick at most, so cycles or
                        // fixed anchors terminate rather than drifting poses.
                        std::set<std::string> moved{name};
                        bool complete=false;
                        for(std::size_t step=0;step<=names.size();++step) {
                            const auto link=std::find_if(seps.begin(),seps.end(),[&](const auto& s){
                                return s.axis_x==sep.axis_x&&endpoint(s.lo,s.axis_x,true)+s.gap>endpoint(s.hi,s.axis_x,false);
                            });
                            if(link==seps.end()){complete=true;break;}
                            const auto& next=high?link->hi:link->lo;
                            if(next.front()=='#'||!moved.insert(next).second)break;
                            const auto j=static_cast<std::size_t>(std::lower_bound(names.begin(),names.end(),next)-names.begin());
                            const double old=axis[j];
                            axis[j]=legalize_trial_pose_precision4dp(old+(high?.0001:-.0001),counts);
                            log.push_back("output-grid propagated: "+next+(sep.axis_x?" x ":" y ")+float_text(old)+" -> "+float_text(axis[j]));
                            if(axis[j]==old||!std::isfinite(axis[j]))break;
                        }
                        exact_ok=complete&&exact_holds();
                    }
                    if(exact_ok){emit_grid();log.push_back("output-grid trial accepted by exact predicates");break;}
                    axis=incumbent;
                    log.push_back("output-grid trial rejected; incumbent restored");
                }
                if(exact_ok)break;
            }
        }
        if (!exact_ok) {
            log.push_back("REJECT: final output-grid pose violates physical separation or hard term");
            return false;
        }
        std::vector<int> moving_masks(names.size()),fixed_masks(fixed_names.size());
        if(!in.primary_fanout.empty()) {
            for(std::size_t i=0;i<names.size();++i)moving_masks[i]=in.primary_fanout.at(names[i]).occupied_mask;
            for(std::size_t i=0;i<fixed_names.size();++i)fixed_masks[i]=in.primary_fanout.at(fixed_names[i]).occupied_mask;
        }
        const auto disjoint=[](int a,int b){return a&&b&&!(a&b);};
        for (std::size_t i = 0; i < boxes.size(); ++i) {
            std::vector<Box4> others;
            others.reserve(boxes.size()-i-1+fixed_boxes.size());
            for(std::size_t j=i+1;j<boxes.size();++j)
                if(!disjoint(moving_masks[i],moving_masks[j])&&
                   !(reservation_geometry&&reservation_pair(names[i],names[j])))others.push_back(boxes[j]);
            for(std::size_t j=0;j<fixed_boxes.size();++j)
                if(!disjoint(moving_masks[i],fixed_masks[j])&&
                   !(reservation_geometry&&reservation_pair(names[i],fixed_names[j])))others.push_back(fixed_boxes[j]);
            if (rects_overlap_any({boxes[i]}, others, 1e-6)) {
                log.push_back("REJECT: final rect overlap"); return false;
            }
        }
        if(reservation_geometry) {
            std::vector<std::vector<Rect>> groups;
            const auto add=[&](const std::string& name,const Box4& box) {
                const auto& body=in.primary_fanout.at(name);
                const std::vector<Comp> empty;
                const auto variable=by_name.find(name);
                const double w=variable==by_name.end()?box.x1-box.x0:variable->second->w;
                const double h=variable==by_name.end()?box.y1-box.y0:variable->second->h;
                groups.push_back(pairs_entity(box.x0,box.y0,w,h,
                    body.reach,body.inset,body.mask,body.children?*body.children:empty,counts));
            };
            for(std::size_t i=0;i<names.size();++i)add(names[i],boxes[i]);
            for(std::size_t i=0;i<fixed_names.size();++i)add(fixed_names[i],fixed_boxes[i]);
            if(!pairs_hold(groups,names.size(),in.clear)) {
                log.push_back("REJECT: final selected child reservation collision");return false;
            }
        }
        for (auto& v : movable) {
            const auto i = static_cast<std::size_t>(std::lower_bound(names.begin(), names.end(), v.name) - names.begin());
            v.x = boxes[i].x0; v.y = boxes[i].y0;
        }
        log.push_back("accept: all hard terms green"); return true;
    }

private:
    const FloorplanLegalizeInput& in;
    std::vector<std::string>& log;
    QuantizationCounts* counts;
    FloorplanOffsets fixed;
    std::map<std::string, const FloorplanLegalizeVar*> by_name;
    std::map<std::string, Box4> seed_rect, frect;
    std::vector<std::string> names;
    std::vector<double> pos_x, pos_y;
    std::vector<RepairSep> seps;
    std::map<std::string,std::vector<Rect>> local_reservations;
    std::vector<TaggedEdge> facing_x,facing_y;
    void build_facing_cuts(FacingAllocation allocation,std::optional<std::size_t> flipped_facing) {
        struct Endpoint { FloorplanPoint local,pose; bool moving; };
        const auto endpoint=[&](const std::string& name)->std::optional<Endpoint> {
            if(name=="@som")return Endpoint{{(in.som_core_page.x0+in.som_core_page.x1)/2-in.origin.first,
                (in.som_core_page.y0+in.som_core_page.y1)/2-in.origin.second},{0,0},false};
            const auto jack=in.som_j_rects.find(name);
            if(jack!=in.som_j_rects.end())return Endpoint{{(jack->second.x0+jack->second.x1)/2,
                (jack->second.y0+jack->second.y1)/2},{0,0},false};
            const auto metric=in.metrics.find(name);if(metric==in.metrics.end())return std::nullopt;
            const auto center=predicted_centroid(0,0,0,0,metric->second.offsets,nullptr,counts);
            if(!center)return std::nullopt;
            const auto variable=by_name.find(name);
            if(variable!=by_name.end())return Endpoint{*center,{variable->second->x,variable->second->y},true};
            const auto pose=fixed.find(name);
            if(pose==fixed.end())return std::nullopt;
            return Endpoint{*center,pose->second,false};
        };
        std::size_t term_index=0;
        for(const auto& term:in.index.hard) {
            if(term.kind!="facing"||!term.enforced||!term.require_positive_facing)continue;
            const auto selected=flipped_facing&&*flipped_facing==term_index
                ?(allocation==FacingAllocation::y_capacity?FacingAllocation::x_capacity:FacingAllocation::y_capacity):allocation;
            ++term_index;
            const auto s=endpoint(term.subject),t=endpoint(term.target());
            const auto metric=in.metrics.find(term.subject);
            if(!s||!t||(!s->moving&&!t->moving)||metric==in.metrics.end())continue;
            const auto output=predicted_centroid(0,0,0,0,metric->second.offsets,&term.out_refs,counts);
            if(!output)continue;
            const double dx=output->first-s->local.first,dy=output->second-s->local.second;
            const double norm=std::hypot(dx,dy);if(norm==0)continue;
            finite(norm,"facing direction norm");
            const double ax=dx/norm,ay=dy/norm;
            // Facing requires a positive direction, not clear mm of projected
            // distance. Reserve one emitted coordinate-lattice step per active
            // axis for rounding; physical board/obstacle clearances remain in
            // their own bounds, and the exact facing gate still decides.
            const double projection_margin=.0001*(std::abs(ax)+std::abs(ay));
            const double rx=t->pose.first+t->local.first-s->pose.first-s->local.first;
            const double ry=t->pose.second+t->local.second-s->pose.second-s->local.second;
            // Split the dot-product slack between the active axes. Each
            // static cut preserves its share independently, so later Y moves
            // cannot invalidate the X contribution. This is a sufficient,
            // seed-centred restriction, not a complete half-plane solver.
            const double slack=(ax*rx+ay*ry-projection_margin)/((ax!=0)+(ay!=0));
            finite(slack,"facing projection slack");
            double share_x=ax*rx-slack,share_y=ay*ry-slack;
            if(ax!=0&&ay!=0) {
                const auto range=[&](const Endpoint& e,const std::string& name,bool x) {
                    const double local=x?e.local.first:e.local.second;
                    if(!e.moving) {
                        const double value=local+(x?e.pose.first:e.pose.second);
                        return std::make_pair(value,value);
                    }
                    const auto* v=by_name.at(name);
                    const double lo=in.clear,hi=(x?in.board_w-v->w:in.board_h-v->h)-in.clear;
                    const double other_lo=in.clear,other_hi=(x?in.board_h-v->h:in.board_w-v->w)-in.clear;
                    struct Blocked {double lo,hi,cross_lo,cross_hi;};
                    std::vector<Blocked> blocked;
                    // Free space can change only at an obstacle contact or
                    // board boundary. Sweep those coordinates, combining the
                    // perpendicular open intervals of all active obstacles.
                    // This also detects strips covered by several rectangles.
                    std::vector<double> contacts{lo,hi};
                    for(const auto& [fixed_name,b]:frect) {
                        if(!in.primary_fanout.empty()) {
                            const auto& a=in.primary_fanout.at(name);
                            const auto& f=in.primary_fanout.at(fixed_name);
                            // An envelope of component-only geometry or a
                            // different face does not prove a blocked strip.
                            if(a.component_only||f.component_only||!(a.mask&f.mask))continue;
                        }
                        const double a=(x?b.x0-v->w:b.y0-v->h)-in.clear;
                        const double z=(x?b.x1:b.y1)+in.clear;
                        blocked.push_back({a,z,(x?b.y0-v->h:b.x0-v->w)-in.clear,
                                             (x?b.y1:b.x1)+in.clear});
                        if(a>=lo&&a<=hi)contacts.push_back(a);
                        if(z>=lo&&z<=hi)contacts.push_back(z);
                    }
                    std::sort(contacts.begin(),contacts.end());
                    contacts.erase(std::unique(contacts.begin(),contacts.end()),contacts.end());
                    std::sort(blocked.begin(),blocked.end(),[](const auto& a,const auto& b){
                        return std::tie(a.cross_lo,a.cross_hi)<std::tie(b.cross_lo,b.cross_hi);
                    });
                    const auto available=[&](double coordinate) {
                        double cursor=other_lo;
                        for(const auto& b:blocked) {
                            if(!(b.lo<coordinate&&coordinate<b.hi))continue;
                            if(b.cross_lo>=cursor)break; // Open intervals retain exact contact.
                            if(cursor<b.cross_hi)cursor=b.cross_hi;
                            if(cursor>other_hi)return false;
                        }
                        return cursor<=other_hi;
                    };
                    double lower=lo,upper=hi;
                    const auto first=std::find_if(contacts.begin(),contacts.end(),available);
                    if(first!=contacts.end()) {
                        lower=*first;
                        upper=*std::find_if(contacts.rbegin(),contacts.rend(),available);
                    }
                    // No free contact is not an acceptance verdict. Retain
                    // broad bounds and let the exact solver reject the layout.
                    return std::make_pair(local+lower,local+upper);
                };
                const auto capacity=[&](bool x,double a) {
                    const auto sr=range(*s,term.subject,x),tr=range(*t,term.target(),x);
                    return a*(a>0?tr.second-sr.first:tr.first-sr.second);
                };
                const double max_x=capacity(true,ax),max_y=capacity(false,ay);
                finite(max_x,"facing x capacity");finite(max_y,"facing y capacity");
                // Preserve the seed split when possible. Otherwise transfer
                // projection to the other axis instead of imposing a cut
                // already contradicted by a board wall. These remain sufficient
                // half-plane cuts; exact final facing and geometry still decide.
                const double low=projection_margin-max_y;
                if(low<=max_x) {
                    // A seed-centred split can exclude a legal pocket behind
                    // an obstacle. Failure-only retries explore the two ends
                    // of the board-feasible allocation interval, without
                    // relaxing the total projection or exact final checks.
                    share_x=selected==FacingAllocation::y_capacity?low:
                        selected==FacingAllocation::x_capacity?max_x:std::clamp(share_x,low,max_x);
                    share_y=projection_margin-share_x;
                }
            }
            for(const bool x:{true,false}) {
                const double a=x?ax:ay;if(a==0)continue;
                const double local=x?t->local.first-s->local.first:t->local.second-s->local.second;
                const double share=x?share_x:share_y;
                const bool positive=a>0;
                const auto& source=positive?*t:*s;const auto& dest=positive?*s:*t;
                double cost=positive?local-share/a:-local+share/a;
                if(!source.moving)cost+=x?source.pose.first:source.pose.second;
                if(!dest.moving)cost-=x?dest.pose.first:dest.pose.second;
                finite(cost,"facing projection bound");
                // Difference bounds live on the same output lattice as the
                // poses. Round toward the safe side before solving, never
                // accept a rounded pose against a looser continuous cut.
                double quantized=legalize_bound_precision4dp(cost,counts);
                if(quantized>cost)quantized=legalize_bound_precision4dp(quantized-.0001,counts);
                cost=quantized;
                const std::string src=source.moving?(positive?term.target():term.subject):"#0";
                const std::string dst=dest.moving?(positive?term.subject:term.target()):"#0";
                (x?facing_x:facing_y).push_back({{src,dst,cost},"facing",term.subject+" -> "+term.target()});
            }
        }
    }
    bool reservation_pair(const std::string& a,const std::string& b) const {
        if(in.primary_fanout.empty())return false;
        const auto& low=in.primary_fanout.at(a);const auto& high=in.primary_fanout.at(b);
        return low.occupied_mask&&high.occupied_mask&&low.children&&high.children&&
            (low.component_only||high.component_only||(low.mask&&high.mask&&!(low.mask&high.mask)));
    }
    std::optional<std::vector<std::vector<RepairSep>>> reservation_seed_seps(const std::string& low,const std::string& high,bool joint) const {
        const auto key=[](const std::string& name){return name.front()=='#'?name.substr(1):name;};
        const auto box=[&](const std::string& name)->const Box4& {
            return name.front()=='#'?frect.at(key(name)):seed_rect.at(name);
        };
        const auto& a=local_reservations.at(key(low));const auto& b=local_reservations.at(key(high));
        // A common direction represents this seed, not every legal placement.
        // Joint search must also be able to enter a child pocket from outside
        // the other group's envelope. Only the legacy strategy uses the
        // cheaper common-direction projection as a replacement domain.
        if(!joint)for(bool reverse:{false,true})for(bool x:{true,false}) {
            const auto& lo=reverse?high:low;const auto& hi=reverse?low:high;
            const auto& lb=box(lo);const auto& hb=box(hi);
            const double size=x?lb.x1-lb.x0:lb.y1-lb.y0;
            if((x?hb.x0-lb.x0:hb.y0-lb.y0)>=size+reservation_gap(lo,hi,x))return std::nullopt;
        }
        std::vector<std::vector<RepairSep>> result;
        for(const auto& first:a)for(const auto& second:b) {
            if(!occ_pair_active(first.mask,first.pmask,first.main,second.mask,second.pmask,second.main))continue;
            std::optional<std::size_t> witness;
            std::vector<RepairSep> domain;
            for(bool reverse:{false,true})for(bool x:{true,false}) {
                const auto& l=reverse?second:first;const auto& h=reverse?first:second;
                const auto& lo=reverse?high:low;const auto& hi=reverse?low:high;
                const auto& lb=box(lo);const auto& hb=box(hi);
                const double bound=(x?l.x+l.w-h.x:l.y+l.h-h.y)+
                    std::max(in.clear,fanout_sep(l.reach,l.inset,h.reach,h.inset,x?'E':'S'));
                finite(bound,"child separation witness");
                if(!witness&&(x?hb.x0-lb.x0:hb.y0-lb.y0)>=bound)witness=domain.size();
                RepairSep sep{x,lo,hi,bound-(x?lb.x1-lb.x0:lb.y1-lb.y0),false};
                sep.projected_gap=true;domain.push_back(sep);
            }
            // A legacy single-direction attempt needs a seed witness. Joint
            // search can repair an overlapping seed through the complete
            // disjunction; none of these alternatives certifies the seed.
            if(!witness&&!joint)return std::nullopt;
            // Keep the legacy seed witness first. Joint search may choose
            // another correctly offset child direction to enter a different
            // pocket; exact physical qualification still checks every child.
            if(witness)std::rotate(domain.begin(),domain.begin()+*witness,domain.begin()+*witness+1);
            result.push_back(std::move(domain));
        }
        if(result.empty())return std::nullopt;
        return result;
    }
    double reservation_gap(const std::string& low,const std::string& high,bool x) const {
        // Linear raw-offset bounds propose a pose only. Child positions are
        // rounded by the real occupancy kernel at final validation; no epsilon
        // or rounded local-offset proxy may turn a collision into acceptance.
        const auto& a=local_reservations.at(low.front()=='#'?low.substr(1):low);
        const auto& b=local_reservations.at(high.front()=='#'?high.substr(1):high);
        std::optional<double> bound;
        for(const auto& l:a)for(const auto& h:b) {
            if(!occ_pair_active(l.mask,l.pmask,l.main,h.mask,h.pmask,h.main))continue;
            const double value=(x?l.x+l.w-h.x:l.y+l.h-h.y)+
                std::max(in.clear,fanout_sep(l.reach,l.inset,h.reach,h.inset,x?'E':'S'));
            finite(value,"reservation projection");bound=bound?std::max(*bound,value):value;
        }
        if(!bound)throw FloorplanError("floorplan compose: empty reservation separation");
        const double gap=*bound-(x?a.front().w:a.front().h);finite(gap,"reservation gap");return gap;
    }
    bool reverse_perpendicular(const std::string& lo,const std::string& hi,bool was_x) const {
        const auto box=[&](const std::string& name)->const Box4& {
            return name.front()=='#'?frect.at(name.substr(1)):seed_rect.at(name);
        };
        const auto& a=box(lo);const auto& b=box(hi);
        return was_x?a.y0>b.y0:a.x0>b.x0;
    }

    std::vector<double> sizes(bool x) const {
        std::vector<double> out;
        for (const auto& n : names) out.push_back(x ? by_name.at(n)->w : by_name.at(n)->h);
        return out;
    }
    std::optional<Box4> hull(const std::string& name) const {
        const auto m = in.metrics.find(name);
        return m == in.metrics.end() ? std::nullopt : pad_union_hull(m->second.pad_union);
    }
    FloorplanPoint fixed_pose(const std::string& name) const {
        const auto p = fixed.find(name);
        if (p == fixed.end()) throw FloorplanError("floorplan compose: missing fixed pose " + name);
        return p->second;
    }
    Box4 seed_or_fixed(const std::string& name, const Box4& h) const {
        const auto s = seed_rect.find(name);
        if (s != seed_rect.end()) {
            if(!pad_seed_hulls)return s->second;
            return {s->second.x0+h.x0,s->second.y0+h.y0,
                    s->second.x0+h.x1,s->second.y0+h.y1};
        }
        const auto p = fixed_pose(name);
        return {p.first + h.x0, p.second + h.y0, p.first + h.x1, p.second + h.y1};
    }
    std::vector<TaggedEdge> extra(bool x) const {
        std::vector<TaggedEdge> out=x?facing_x:facing_y;
        for (const auto& t : in.index.hard) {
            if (t.kind != "near_max") continue;
            const auto s = t.subject, g = t.target();
            const auto jr = floorplan_detail::starts(g, "som_j") ? in.som_j_rects.find(g) : in.som_j_rects.end();
            const auto hs = hull(s);
            const auto hg = jr == in.som_j_rects.end() ? hull(g) :
                std::optional<Box4>{{0, 0, jr->second.x1 - jr->second.x0, jr->second.y1 - jr->second.y0}};
            const double authored = t.bound.value_or(0);
            // Early strategies seek extra margin, but the final joint fallback
            // needs the full authored envelope: retaining a heuristic guard
            // there would exclude physically valid authored-legal placements.
            // Exact final Euclidean distance remains an acceptance condition.
            const double bound = full_distance_envelope || authored < guard_mm ? authored : authored - guard_mm;
            const bool sm = by_name.count(s), gm = by_name.count(g);
            if (!hs || !hg || bound < 0 || (!sm && !gm)) continue;
            const auto sr = seed_or_fixed(s, *hs);
            const auto gr = jr == in.som_j_rects.end() ? seed_or_fixed(g, *hg) : jr->second;
            const auto sp = sm ? std::nullopt : std::optional<FloorplanPoint>{fixed_pose(s)};
            const auto gp = gm ? std::nullopt : std::optional<FloorplanPoint>{fixed_pose(g)};
            for (const auto& e : near_max_edges(s, g, bound, x, *hs, *hg, sr, gr, sm, gm, sp, gp, distance_envelope))
                out.push_back({{e.src, e.dst, e.cost}, e.perp ? "near_max-perp" : "near_max",
                    in.report_infeasible_cycle?s+" -> "+g:std::string{}});
        }
        return out;
    }
    std::vector<TaggedEdge> edges(bool x) const {
        std::vector<SepSpec> spec;
        for (const auto& s : seps) spec.push_back({s.axis_x, s.lo, s.hi, s.gap});
        std::vector<TaggedEdge> out;
        for (const auto& e : wall_sep_edges(x, names, sizes(x), x ? in.board_w : in.board_h,
                                           in.clear, spec, {frect.begin(), frect.end()})) {
            double cost=e.cost;
            if (!in.primary_fanout.empty() && e.kind=="sep") {
                const auto& sep=seps.at(static_cast<std::size_t>(e.sep_index));
                const bool low_fixed=sep.lo.front()=='#',high_fixed=sep.hi.front()=='#';
                if (low_fixed || high_fixed) {
                    // The solver and final occupancy check associate sums
                    // differently. Choose an actual output-grid coordinate
                    // satisfying the forward physical inequality, not an epsilon.
                    const auto& fixed_rect=frect.at((low_fixed?sep.lo:sep.hi).substr(1));
                    const auto& variable=*by_name.at(low_fixed?sep.hi:sep.lo);
                    const double size=x?variable.w:variable.h;
                    const double anchor=low_fixed?(x?fixed_rect.x1:fixed_rect.y1):
                                                   (x?fixed_rect.x0:fixed_rect.y0);
                    const auto holds=[&](double q) {
                        return low_fixed?anchor+sep.gap<=q:q+size+sep.gap<=anchor;
                    };
                    double q=legalize_bound_precision4dp(low_fixed?-cost:cost,counts);
                    if (!holds(q))
                        q=legalize_bound_precision4dp(q+(low_fixed?.0001:-.0001),counts);
                    // Extreme coordinates may not resolve a grid tick. Leave
                    // the bound unchanged; final exact checks reject if needed.
                    if (std::isfinite(q)&&holds(q)) cost=low_fixed?-q:q;
                }
            }
            out.push_back({{e.src, e.dst, cost}, e.kind});
        }
        const auto more = extra(x); out.insert(out.end(), more.begin(), more.end());
        return out;
    }
    bool physical_seps_ok() const {
        const auto endpoint=[&](const std::string& name,bool x,bool high) {
            if (name.front()=='#') {
                const auto& box=frect.at(name.substr(1));
                return x?(high?box.x1:box.x0):(high?box.y1:box.y0);
            }
            const auto i=static_cast<std::size_t>(std::lower_bound(names.begin(),names.end(),name)-names.begin());
            const auto& v=*by_name.at(name);
            return (x?pos_x[i]:pos_y[i])+(high?(x?v.w:v.h):0.);
        };
        for (const auto& sep:seps) {
            const auto lower=endpoint(sep.lo,sep.axis_x,true)+sep.gap;
            const auto upper=endpoint(sep.hi,sep.axis_x,false);
            if (!(lower<=upper)) {
                if(in.report_infeasible_cycle)log.push_back("physical separation: "+sep.lo+" -> "+sep.hi+
                    (sep.axis_x?" x ":" y ")+float_text(lower)+" > "+float_text(upper));
                return false;
            }
        }
        return true;
    }
    bool violated(const NamedEdge& e, const std::vector<double>& pos) const {
        auto value = [&](const std::string& name) {
            if (name == "#0") return 0.0;
            const auto n = std::lower_bound(names.begin(), names.end(), name);
            if (n == names.end() || *n != name)
                throw FloorplanError("floorplan compose: unknown constraint endpoint " + name);
            return pos.at(static_cast<std::size_t>(n - names.begin()));
        };
        return value(e.dst) - value(e.src) > e.cost + 1e-9;
    }
    bool edges_ok(bool x, const std::vector<double>& pos) const {
        for (const auto& e : edges(x)) if (violated(e.edge, pos)) return false;
        return true;
    }
    bool repair(bool x, std::vector<double>& pos, int flip_budget=repair_max) {
        std::vector<NamedEdge> additional;
        const auto additional_terms=extra(x);
        for (const auto& e : additional_terms) additional.push_back(e.edge);
        auto r = legalize_repair_axis(x, names, sizes(x), x ? in.board_w : in.board_h,
            in.clear, seps, {frect.begin(), frect.end()}, additional, flip_budget);
        for(const auto& [lo,hi,was_x]:r.flips)
            flip_order_differs|=reverse_perpendicular(lo,hi,was_x);
        if(perpendicular_order)for(const auto& [lo,hi,was_x]:r.flips)
            log.push_back("repair: flip "+lo+"|"+hi+" off "+(was_x?"x":"y")+
                (reverse_perpendicular(lo,hi,was_x)?" (perpendicular endpoints reversed)":""));
        seps = std::move(r.seps);
        if (!r.ok) {
            log.push_back(std::string("INFEASIBLE ") + (x ? "x" : "y") +
                (flip_budget==0 ? ": final separation assignment has a negative cycle (no flips allowed)" :
                 r.fail == "exhausted" ? ": REPAIR_MAX exhausted" : ": negative cycle"));
            if(in.report_infeasible_cycle)for(std::size_t i=0;i<r.infeasible_cycle.size();++i) {
                const auto& edge=r.infeasible_cycle[i];
                auto origin=r.infeasible_cycle_origins.at(i);
                if(origin.rfind("extra[",0)==0)for(const auto& term:additional_terms)
                    if(term.edge.src==edge.src&&term.edge.dst==edge.dst&&term.edge.cost==edge.cost)
                        origin+="; "+term.kind+" "+term.source;
                log.push_back(std::string("cycle ")+(x?"x":"y")+": "+edge.dst+" - "+edge.src+" <= "+float_text(edge.cost)+
                    " ["+origin+"]");
                // A fixed endpoint is collapsed to #0 in the difference
                // graph. Preserve its actual geometry in diagnostic evidence
                // so a failed separation can be distinguished from a bad
                // near bound without rerunning a different placement.
                for(const auto& sep:seps)if(origin=="separation "+sep.lo+" -> "+sep.hi){
                    const auto describe=[&](const std::string& name){
                        const auto& box=name.front()=='#'?frect.at(name.substr(1)):seed_rect.at(name);
                        return name+" ["+float_text(box.x0)+","+float_text(box.y0)+","+
                            float_text(box.x1)+","+float_text(box.y1)+"]";
                    };
                    log.push_back("cycle seed: "+describe(sep.lo)+" -> "+describe(sep.hi)+
                        " gap="+float_text(sep.gap));
                    break;
                }
            }
            return false;
        }
        pos = std::move(r.pos);
        if(!perpendicular_order)for (const auto& [lo, hi, was_x] : r.flips)
            log.push_back("repair: flip " + lo + "|" + hi + " off " + (was_x ? "x" : "y"));
        return true;
    }
    FloorplanPoint cent_off(const std::string& name) const {
        const auto m = in.metrics.find(name);
        if (m != in.metrics.end() && !m->second.offsets.empty())
            return centroid_offset(m->second.offsets, 0, 0);
        const auto v = by_name.find(name);
        return v == by_name.end() ? FloorplanPoint{0, 0} : FloorplanPoint{v->second->w / 2, v->second->h / 2};
    }
    void descend(bool seed_only) {
        std::vector<NamedEdge> ex, ey;
        for (const auto& e : edges(true)) ex.push_back(e.edge);
        for (const auto& e : edges(false)) ey.push_back(e.edge);
        std::vector<double> sx, sy;
        std::vector<std::pair<std::string, FloorplanPoint>> centers;
        for (const auto& n : names) {
            const auto& seed = by_name.at(n)->seed;
            sx.push_back(seed.first); sy.push_back(seed.second); centers.emplace_back(n, cent_off(n));
        }
        for (const auto& [n, r] : frect) { (void)r; centers.emplace_back(n, cent_off(n)); }
        std::vector<std::pair<std::string, std::string>> hops;
        if (!seed_only) for(const auto* terms:{&in.index.hard,&in.index.soft})for (const auto& t : *terms)
            if (t.kind == "flow_hop"&&(terms==&in.index.hard||t.prefer_short_flow)) hops.emplace_back(t.subject, t.target());
        const auto& core = in.som_core_page;
        auto result = legalize_descend_passes_accounted(names, pos_x, pos_y, sx, sy, ex, ey, hops, centers,
            {fixed.begin(), fixed.end()}, (core.x0 + core.x1) / 2 - in.origin.first,
            (core.y0 + core.y1) / 2 - in.origin.second, true, seed_only, hop_weight, seed_weight, median_passes, counts);
        pos_x = std::move(result.first); pos_y = std::move(result.second);
    }
    std::vector<FloorplanTermEval> reds() const {
        auto poses = fixed;
        for (std::size_t i = 0; i < names.size(); ++i)
            poses[names[i]] = {legalize_trial_pose_precision4dp(pos_x[i], counts), legalize_trial_pose_precision4dp(pos_y[i], counts)};
        // Feasibility consumes only enforced terms. Public diagnostics still
        // evaluate every term; do not repeatedly measure advisory rows merely
        // to discard them here during each rejected search proposal.
        auto out = evaluate(in, poses, counts, true);
        out.erase(std::remove_if(out.begin(), out.end(), [](const auto& e) { return !e.term.enforced || e.ok; }), out.end());
        return out;
    }
    bool pad_seed_hulls = false;
    bool distance_envelope = false;
    bool full_distance_envelope = false;
    bool perpendicular_order = false;
    bool flip_order_differs = false;
    bool reservation_geometry = false;
};

bool compose_with_bounded_retries(const FloorplanLegalizeInput& input,
        std::vector<FloorplanLegalizeVar>& movable,std::vector<std::string>& log,
        QuantizationCounts* counts=nullptr) {
    // Preserve every accepted incumbent. Body-derived axes remain a useful
    // search strategy, but can falsely reject when local pads favour another
    // axis. Try that geometry once, from unchanged caller poses, on rejection.
    // A final distinct strategy reverses flipped pairs to follow their
    // perpendicular seed order. A final physical-reservation strategy may run
    // after all conservative strategies fail, followed by one strict-facing
    // projection strategy: at most five legacy composer attempts, followed
    // only when explicitly enabled by state-bounded joint strategies. Full
    // authored-distance retries run only after margin-seeking strategies fail.
    Composer original(input,movable,log,counts);
    if(original.run(movable))return true;
    Composer alternative(input,movable,log,counts,true);
    // Different hulls can still yield identical constraints. Do not execute
    // or report a second solver attempt when it would repeat the same work.
    if(!original.same_near_axes(alternative)) {
        // Retain the failed first attempt's diagnostics and executed accounting.
        log.push_back("retry: near constraints use selected pad-hull axes");
        if(alternative.run(movable))return true;
    }
    if(original.changed_flip_order()) {
        log.push_back("retry: flipped separations follow perpendicular seed order");
        if(Composer(input,movable,log,counts,false,true).run(movable))return true;
    }
    const bool candidate=[&] {
        // Fixed/fixed pairs cannot be repaired by this solve. Stop at the
        // first relevant pair instead of sweeping a quadratic fixed set.
        for(const auto& v:movable) {
            const auto ai=input.primary_fanout.find(v.name);
            if(ai==input.primary_fanout.end())continue;
            const auto& a=ai->second;
            for(const auto& [bn,b]:input.primary_fanout) {
                if(bn==v.name)continue;
                if((a.component_only||b.component_only||(a.mask&&b.mask&&!(a.mask&b.mask)))&&a.children&&b.children&&
                   (a.occupied_mask&b.occupied_mask))return true;
            }
        }
        return false;
    }();
    if(candidate) {
        log.push_back("retry: selected child-face reservation geometry");
        if(input.reservation_retry_started)input.reservation_retry_started();
        if(Composer(input,movable,log,counts,false,false,true).run(movable))return true;
    }
    const bool facing=std::any_of(input.index.hard.begin(),input.index.hard.end(),[](const auto& t){
        return t.kind=="facing"&&t.enforced&&t.require_positive_facing;
    });
    if(facing){
        log.push_back("retry: strict facing projection cuts");
        if(input.facing_retry_started)input.facing_retry_started();
        if(Composer(input,movable,log,counts,false,false,candidate,true).run(movable))return true;
    }
    if(!input.joint_separation_states)return false;
    log.push_back("retry: bounded joint separation choices");
    if(input.joint_retry_started)input.joint_retry_started();
    if(Composer(input,movable,log,counts,false,false,candidate,false).run(movable,true))return true;
    // Projection cuts are sufficient but not necessary. Combine them with
    // joint separation only after the unrestricted strategy fails; never
    // prune its successful incumbents or hide either strategy's work.
    if(facing) {
        log.push_back("retry: joint separation with strict facing projection cuts");
        if(input.joint_retry_started)input.joint_retry_started();
        if(Composer(input,movable,log,counts,false,false,candidate,true).run(movable,true))return true;
    }
    // Extra margin is a preference, not a feasibility requirement. Preserve
    // successful guarded strategies, then search the full authored envelope.
    const bool guarded=std::any_of(input.index.hard.begin(),input.index.hard.end(),[](const auto& t){
        return t.kind=="near_max"&&t.bound&&*t.bound>=guard_mm;
    });
    if(!guarded)return false;
    Composer proximity_probe(input,movable,log,counts,false,false,candidate,false);
    if(!proximity_probe.full_authored_bounds_differ()) {
        log.push_back("skip: full authored proximity emits identical moving constraints");
        return false;
    }
    log.push_back("retry: joint separation with full authored proximity bounds");
    if(input.joint_retry_started)input.joint_retry_started();
    if(Composer(input,movable,log,counts,false,false,candidate,false).run(movable,true,true))return true;
    if(!facing)return false;
    log.push_back("retry: full authored proximity with strict facing projection cuts");
    if(input.joint_retry_started)input.joint_retry_started();
    return Composer(input,movable,log,counts,false,false,candidate,true).run(movable,true,true);
}
bool compose_with_facing_extremes(const FloorplanLegalizeInput& input,
        std::vector<FloorplanLegalizeVar>& movable,std::vector<std::string>& log,
        QuantizationCounts* counts=nullptr) {
    if(!input.joint_separation_states)return false;
    const bool facing=std::any_of(input.index.hard.begin(),input.index.hard.end(),[](const auto& t) {
        return t.kind=="facing"&&t.enforced&&t.require_positive_facing;
    });
    if(!facing)return false;
    // Only reached after the complete original portfolio failed. Each trial
    // receives the caller's state budget, reports all actual work through the
    // existing joint callbacks and preserves the caller's poses on rejection.
    // Extreme allocations add opportunities, not a complete half-plane solver.
    std::vector<std::pair<FacingAllocation,std::optional<std::size_t>>> allocations{
        {FacingAllocation::y_capacity,std::nullopt},{FacingAllocation::x_capacity,std::nullopt}};
    const std::size_t terms=std::count_if(input.index.hard.begin(),input.index.hard.end(),[](const auto& t){
        return t.kind=="facing"&&t.enforced&&t.require_positive_facing;
    });
    // Linear one-term deviations, not an exponential Cartesian campaign.
    // With two facing relationships this covers both mixed allocations.
    if(terms>1)for(const auto base:{FacingAllocation::y_capacity,FacingAllocation::x_capacity})
        for(std::size_t term=0;term<terms;++term)allocations.emplace_back(base,term);
    std::set<Composer::FacingCutKey> seen;
    for(const auto& [allocation,flipped]:allocations) {
        Composer candidate(input,movable,log,counts,false,false,!input.primary_fanout.empty(),true,allocation,flipped);
        // Keep the actual preparation work, but neither execute nor report a
        // duplicate solver attempt (e.g. a purely axial facing requirement).
        if(!seen.insert(candidate.facing_cut_key()).second)continue;
        log.push_back(std::string(allocation==FacingAllocation::y_capacity?
            "retry: joint facing Y-capacity allocation":"retry: joint facing X-capacity allocation")+
            (flipped?" with opposite allocation for term "+std::to_string(*flipped):""));
        if(input.joint_retry_started)input.joint_retry_started();
        if(candidate.run(movable,true,true))return true;
    }
    return false;
}
}  // namespace

std::vector<FloorplanTermEval> floorplan_evaluate_terms(
        const FloorplanLegalizeInput& input, const FloorplanOffsets& poses) {
    validate(input);
    for (const auto& [name, p] : poses) point(p, name);
    return evaluate(input, poses);
}

bool floorplan_legalize_compact(const FloorplanLegalizeInput& input,
        std::vector<FloorplanLegalizeVar>& movable, std::vector<std::string>& log) {
    validate(input);
    if(compose_with_bounded_retries(input, movable, log))return true;
    return compose_with_facing_extremes(input,movable,log);
}
bool floorplan_legalize_compact_accounted(const FloorplanLegalizeInput& input,
        std::vector<FloorplanLegalizeVar>& movable, std::vector<std::string>& log,
        QuantizationCounts& counts) {
    validate(input);
    if(compose_with_bounded_retries(input, movable, log, &counts))return true;
    return compose_with_facing_extremes(input,movable,log,&counts);
}
}  // namespace schgen
