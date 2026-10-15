#include "pcb_placement_internal.hpp"
#include "pcb_placement_orientations.hpp"
#include "schgen/pcb_placement_gates.hpp"
#include "schgen/ratsnest_gate.hpp"
#include "schgen/pcb_placement_search.hpp"

namespace schgen::pcb_placement {
namespace {
FloorplanTermIndex term_index(const Context &ctx) {
    using Key = std::tuple<std::string, std::string, std::string>;
    std::map<Key, FloorplanTerm> merged;
    auto add = [&](FloorplanTerm t) {
        auto [p, fresh] = merged.emplace(Key{t.kind, t.subject, t.target_raw}, t);
        if (fresh)
            return;
        auto &old = p->second;
        // Conjunction keeps the strongest requirement: upper limits shrink,
        // but minimum clearances grow. Keep its authored justification too.
        if (t.bound && (!old.bound ||
                       (t.kind == "far_min" ? *t.bound > *old.bound : *t.bound < *old.bound))) {
            old.bound = t.bound;
            old.basis = t.basis;
        }
        old.enforced = old.enforced || t.enforced;
        old.require_positive_facing = old.require_positive_facing || t.require_positive_facing;
        if (old.output_roles.empty())
            old.output_roles = t.output_roles;
        if (old.out_refs.empty())
            old.out_refs = t.out_refs;
    };
    const std::set<std::string> known{"flow", "downstream", "output_roles",
                                      "far",  "near_max",   "media_faces_near_max"};
    std::set<std::string> names;
    for (const auto &sc : ctx.in.floorplan.sheets)
        names.insert(sc.name);
    for (const auto &sheet : names) {
        auto found = ctx.in.contracts.find(sheet);
        if (found == ctx.in.contracts.end())
            continue;
        const auto &contract = found->second;
        const auto &ext = optional(contract, "external");
        for (const auto &[key, value] : ext.object_value) {
            (void)value;
            if (!known.count(key))
                throw PcbZoneInfeasible("placement contract " + sheet +
                                        ": unsupported external term kind " + key);
        }
        auto make = [&](const std::string &kind, const std::string &subject,
                        const std::string &target, const std::string &basis) {
            FloorplanTerm t;
            t.kind = kind;
            t.sheet = sheet;
            t.subject = subject;
            t.target_raw = target;
            t.basis = basis;
            t.enforced = ctx.wired.count(sheet);
            t.require_positive_facing = ctx.in.floorplan.compact_search && t.enforced && kind == "facing";
            return t;
        };
        const auto basis = text(contract, "contract", "?");
        const auto flow = strings(ext, "flow");
        for (std::size_t k = 1; k < flow.size(); ++k)
            add(make("flow_hop", flow[k - 1], flow[k], "flow chain [" + basis + "]"));
        for (const auto &n : optional(ext, "near_max").array_value) {
            auto t = make("near_max", sheet, text(n, "other", "?"), text(n, "basis"));
            t.bound = number(n, "max_mm");
            add(t);
        }
        for (const auto &n : optional(ext, "far").array_value) {
            auto t = make("far_min", sheet, text(n, "what", "?"), text(n, "basis"));
            t.bound = number(n, "min_mm");
            add(t);
        }
        auto downstream = text(ext, "downstream");
        auto roles = strings(ext, "output_roles");
        if (!downstream.empty() && !roles.empty()) {
            auto t = make("facing", sheet, downstream, "facing/output_roles [" + basis + "]");
            t.output_roles = roles;
            std::set<std::string> refs;
            for (const auto &[ref, role] : optional(contract, "roles").object_value)
                if (std::find(roles.begin(), roles.end(), role.string_value) != roles.end())
                    refs.insert(ref);
            const auto &map = ctx.board_refs.at(sheet);
            for (const auto &r : refs)
                if (map.count(r))
                    t.out_refs.push_back(map.at(r));
            add(t);
        }
    }
    if (ctx.in.floorplan.spec) {
        std::set<std::pair<std::string, std::string>> near;
        for (const auto &[key, t] : merged) {
            (void)key;
            if (t.kind == "near_max")
                near.insert({t.subject, t.target()});
        }
        for (const auto &[name, a] : ctx.in.floorplan.spec->interior)
            if (a.near && !a.near->empty() && !near.count({name, *a.near})) {
                FloorplanTerm t;
                t.kind = "near_intent";
                t.sheet = name;
                t.subject = name;
                t.target_raw = *a.near;
                t.basis = "carrier/floorplan.json near-intent (advisory)";
                add(t);
            }
    }
    FloorplanTermIndex index;
    for (const auto &[key, t] : merged) {
        (void)key;
        bool missing = false;
        for (const auto &n : {t.subject, t.target()})
            missing |= n != "@som" && !names.count(n);
        (missing ? index.na : t.enforced ? index.hard : index.soft).push_back(t);
    }
    return index;
}
FloorplanLocalMetrics metrics(const PcbZoneResult &zones, const Offsets &top, const Offsets &bottom,
                              const Rotations &extra, FloorplanPoint wh,
                              const std::map<std::string, std::string> &mirrors = {}) {
    FloorplanLocalMetrics result;
    result.zone_wh = wh;
    Offsets both = top;
    for (const auto &[r, xy] : bottom)
        both[r] = xy;
    PcbStageInput empty;
    Engine geometry(empty);
    for (const auto &[ref, xy] : both) {
        result.offsets.emplace_back(ref, xy.first, xy.second);
        auto source = mirrors.find(ref);
        std::string key;
        if (source != mirrors.end())
            key = source->second;
        else {
            auto p = zones.geometry.resolvable.find(ref);
            if (p == zones.geometry.resolvable.end())
                continue;
            key = p->second;
        }
        auto c = zones.geometry.conn_rot.find(ref), e = extra.find(ref);
        const auto boxes =
            values(geometry.pads(zones.footprints.at(key),
                                 normalize((c == zones.geometry.conn_rot.end() ? 0 : c->second) +
                                           (e == extra.end() ? 0 : e->second))));
        auto bounds = boxes_union(boxes);
        if (bounds)
            result.pad_union.emplace_back(ref, bounds->x0 + xy.first, bounds->y0 + xy.second,
                                          bounds->x1 + xy.first, bounds->y1 + xy.second);
    }
    return result;
}
} // namespace
} // namespace schgen::pcb_placement

namespace schgen {
FloorplanInput prepare_pcb_floorplan(const PcbPlacementInput &input, const PcbZoneResult &zones) {
    using namespace pcb_placement;
    if (input.floorplan.origin != FloorplanPoint{25, 25})
        throw PcbZoneInfeasible("PCB placement requires the 25 mm emission origin");
    Context ctx(input);
    FloorplanInput result = input.floorplan;
    result.geometry = zones.geometry;
    // Replace caller seed with the matching zone invocation; never carry stale
    // quality across shape indices or enable it in the default path.
    result.owned_shape_quality.clear();
    if (input.floorplan.compact_search)
        result.owned_shape_quality = zones.owned_shape_quality;
    for (const auto &[key, fp] : zones.footprints) {
        if (!fp)
            throw PcbZoneInfeasible("null footprint: " + key);
        result.footprints[key] = {fp->source, fp->document};
    }
    result.impedance_net_classes.clear();
    for (const auto &[net, c] : ctx.netclass_of)
        if (ctx.classes.at(c))
            result.impedance_net_classes[net] = c;
    FloorplanComposeInput compose;
    compose.corridors = result.compose.corridors;
    compose.index = term_index(ctx);
    compose.wired_participants = ctx.l4_exempt;
    std::set<std::string> sheets;
    for (const auto *all : {&result.geometry.top_off, &result.geometry.bot_off})
        for (const auto &[sheet, offset] : *all) {
            (void)offset;
            sheets.insert(sheet);
        }
    for (const auto &sheet : sheets)
        compose.metrics[sheet] =
            metrics(zones, result.geometry.top_off[sheet], result.geometry.bot_off[sheet],
                    result.geometry.zone_extra_rot, result.geometry.zone_box[sheet]);
    for (const auto &[sheet, shapes] : result.geometry.shapes)
        for (std::size_t k = 1; k < shapes.size(); ++k) {
            const auto &s = shapes[k];
            compose.shape_metrics[{sheet, static_cast<int>(k)}] =
                metrics(zones, s.top_off, s.bot_off, s.extra_rot, {s.w, s.h}, s.mirror);
        }
    std::map<std::string, std::set<std::string>> net_sheets;
    for (const auto &sheet : result.sheets)
        for (const auto &n : sheet.nets) {
            if (sheet.name.rfind("som_j", 0) == 0) {
                bool auxiliary = false;
                for (const auto &p : n.pins)
                    for (const auto &part : sheet.parts)
                        if (p.ref == part.ref && part.ref.rfind("J", 0) != 0 &&
                            part.footprint.find("MountingHole") == std::string::npos)
                            auxiliary = true;
                if (!auxiliary)
                    continue;
            }
            net_sheets[n.name].insert(sheet.name);
        }
    for (const auto &[net, members] : net_sheets) {
        (void)net;
        if (members.size() == 2)
            ++compose.channel_demand[{*members.begin(), *members.rbegin()}];
    }
    result.compose = std::move(compose);
    result.accounting.fallback_events.insert(result.accounting.fallback_events.end(),
                                             zones.fallback_events.begin(),
                                             zones.fallback_events.end());
    checked_quantization_merge(result.accounting.quantization_engagements, zones.quantization_engagements);
    return result;
}
static PcbPlacementResult build_pcb_model_once(const PcbPlacementInput &input, ExecutionFailureReceipt* failure,
                                               bool vertical_compaction) {
    // Each child failure owns only its operation, except floorplan which
    // explicitly inherits planning-zone accounting. Keep that transfer visible.
    ExecutionFailureReceipt child;
    ExecutionAccounting completed;
    try {
    auto zones = pcb_placement::build_zones_for_search(input,vertical_compaction,&child);
    completed={zones.quantization_engagements,zones.fallback_events};
    observe_pcb_experiment_checkpoint(input.experiment.get(), [] {
        PcbPlacementObservation row;
        row.stage = "zone_pack";
        return row;
    });
    // Solve the same face assignment and shape offers that placement consumes.
    // Sizing a top-preferred request with smaller two-face zones can publish
    // overlapping parts when the plan is rebound to the larger emitted zones.
    FloorplanInput prepared;
    try { prepared=prepare_pcb_floorplan(input, zones); }
    catch (const std::overflow_error&) { invalidate_execution_failure(&child);throw; }
    // generate_floorplan guarantees its failure receipt includes prepared's
    // seed even if the engine rejects during construction. Do not count that
    // same planning zone again at the parent boundary.
    completed=ExecutionAccounting{};
    FloorplanStage floorplan;
    try {floorplan = generate_floorplan(prepared,&child);}
    catch(const FloorplanPackingInfeasible&) {
        const auto experiment=input.floorplan.experiment;
        if(!experiment||experiment->contract_group_face_sheets.empty()||!child.captured||child.unavailable)throw;
        struct Expansion {std::string sheet;FloorplanZoneShape seed;std::size_t index,old_size;};
        std::vector<Expansion> selected;
        for(const auto& sheet:experiment->contract_group_face_sheets){
            const auto found=zones.geometry.shapes.find(sheet);
            if(found==zones.geometry.shapes.end())continue;
            const auto& offers=found->second;
            const auto first=std::find_if(offers.begin(),offers.end(),[](const auto& s){return s.tag.rfind("contract-bottom/",0)==0;});
            if(first!=offers.end())selected.push_back({sheet,offers.front(),static_cast<std::size_t>(first-offers.begin()),offers.size()});
        }
        if(selected.empty())throw;
        // The first failed receipt already owns original zone/caller work.
        completed=std::move(child.accounting);child={};
        completed.fallback_events.push_back("contract_group_orientation_retry");
        pcb_placement::Context expansion(input);expansion.pool=zones.footprints;
        bool changed=false;
        // Expand each eligible suffix in canonical sheet order, then replan
        // once with all offers together. Count the complete failed prefix and
        // every expansion, including a throw after earlier sheets succeeded.
        try {for(const auto& choice:selected){
            pcb_placement::append_rigid_zone_orientations(expansion,zones.geometry,choice.sheet,choice.seed,choice.index);
            changed|=zones.geometry.shapes.at(choice.sheet).size()!=choice.old_size;
        }}
        catch(...) {append_execution_accounting(completed,{expansion.quantization,{}},&child);throw;}
        append_execution_accounting(completed,{expansion.quantization,{}},&child);
        if(!changed)throw;
        prepared=prepare_pcb_floorplan(input,zones);
        // Replace the repeated seed: count original work exactly once, then
        // all new rotation and search work, including rejected alternatives.
        prepared.accounting.quantization_engagements=completed.quantization_engagements;
        prepared.accounting.fallback_events=completed.fallback_events;
        completed={};
        floorplan=generate_floorplan(prepared,&child); // At most one retry.
    }
    append_execution_accounting(completed,{floorplan.plan.accounting.quantization_engagements,floorplan.plan.accounting.fallback_events},&child);
    append_execution_accounting(completed,floorplan.documents.accounting,&child);
    observe_pcb_experiment_checkpoint(input.experiment.get(), [&] {
        PcbPlacementObservation row;
        row.stage = "plan_lattice";
        // Measure the same placement zones before shape binding.
        row.plan = measure_floorplan_experiment_plan(prepare_pcb_floorplan(input, zones), floorplan.plan);
        return row;
    });
    auto result=place_pcb_model_accounted(input, zones, floorplan,
        PcbZoneAccountingOwnership::IncludedInFloorplan,&child);
    const auto experiment=input.floorplan.experiment;
    if(input.floorplan.compact_search || !experiment || !experiment->multiscale_outline ||
       std::none_of(prepared.compose.index.hard.begin(),prepared.compose.index.hard.end(),
           [](const auto& t){return t.kind=="facing"&&t.enforced&&!t.require_positive_facing;}))
        return result;

    // Preserve successful incumbents. Only a resolved final facing failure
    // justifies the one stricter placement trial; unknown inputs never PASS.
    // Placement has already executed. An unrepresentable aggregate cannot
    // be reported as the earlier, smaller floorplan-only failure prefix.
    try {completed=pcb_placement_accounting(result);}
    catch(const std::overflow_error&){invalidate_execution_failure(&child);throw;}
    child={};
    ExecutionAccounting screening;
    PcbPlacementFlowResult flow;
    try {
        flow=check_pcb_placement_flow(PcbCheckInput(result.model),pcb_placement_gate_policy(input),
            nullptr,&screening.quantization_engagements);
    } catch(...) {append_execution_accounting(completed,screening,&child);throw;}
    append_execution_accounting(completed,screening,&child);
    append_execution_accounting(result.placement_accounting,screening,&child);
    if(!flow.facing_fail || !flow.unresolved.empty())return result;

    // A late half-turn may be unsafe even when its facing direction is right.
    // Reuse the prepared zones, but solve the actual positive-facing terms
    // before placement. Never discard the original model's executed work.
    for(auto& term:prepared.compose.index.hard)
        if(term.kind=="facing"&&term.enforced)term.require_positive_facing=true;
    completed.fallback_events.push_back("facing_replan_retry");
    prepared.accounting.quantization_engagements=completed.quantization_engagements;
    prepared.accounting.fallback_events=completed.fallback_events;
    completed={};child={};
    floorplan=generate_floorplan(prepared,&child); // One retry; no recursion.
    append_execution_accounting(completed,{floorplan.plan.accounting.quantization_engagements,
        floorplan.plan.accounting.fallback_events},&child);
    append_execution_accounting(completed,floorplan.documents.accounting,&child);
    observe_pcb_experiment_checkpoint(input.experiment.get(), [&] {
        PcbPlacementObservation row;row.stage="plan_lattice";
        row.plan=measure_floorplan_experiment_plan(prepared,floorplan.plan);return row;
    });
    return place_pcb_model_accounted(input, zones, floorplan,
        PcbZoneAccountingOwnership::IncludedInFloorplan,&child);
    } catch (...) {
        capture_execution_failure(failure,std::move(completed),&child);
        throw;
    }
}
FloorplanSpec pcb_edge_replan_spec(const FloorplanSpec& original,const FloorplanPlan& plan) {
    auto spec=original;
    spec.edges.clear();
    spec.ordered_edges.clear();
    std::map<std::string,std::vector<std::pair<double,std::string>>> runs;
    std::set<std::string> names;
    for(const auto& block:plan.edge_blocks) {
        if(block.edge.size()!=1||std::string("NESW").find(block.edge)==std::string::npos||
           !names.insert(block.name).second||!std::isfinite(block.x)||!std::isfinite(block.y))
            throw PcbZoneInfeasible("edge replan requires unique blocks with finite poses and valid edges");
        runs[block.edge].emplace_back(block.edge=="N"||block.edge=="S"?block.x:block.y,block.name);
    }
    for(const auto& entry:original.edge_of())
        if(!names.count(entry.first))throw PcbZoneInfeasible("edge replan lost declared block: "+entry.first);
    for(auto& [edge,run]:runs) {
        std::sort(run.begin(),run.end());
        for(const auto& item:run)spec.edges[edge].push_back(item.second);
    }
    spec.ordered_edges=spec.edges;
    return spec;
}
static PcbPlacementResult build_pcb_model_strategy(const PcbPlacementInput& input,ExecutionFailureReceipt* failure,
                                                   bool vertical_compaction) {
    ExecutionFailureReceipt first;
    try {return build_pcb_model_once(input,&first,vertical_compaction);}
    catch(const PcbEdgeGeometryMismatch& mismatch) {
        // One full-geometry retry, never recursive and never a geometry waiver.
        // The first receipt already owns its input seed, zones, packing and
        // rejected placement. Transfer it, rather than adding that seed twice.
        if(failure)*failure=first;
        if(!first.captured||first.unavailable)throw;
        auto retry=input;
        retry.floorplan.spec=mismatch.retry_spec;
        retry.floorplan.accounting.quantization_engagements=first.accounting.quantization_engagements;
        retry.floorplan.accounting.fallback_events=first.accounting.fallback_events;
        retry.floorplan.accounting.fallback_events.push_back("edge_geometry_replan_retry");
        return build_pcb_model_once(retry,failure,vertical_compaction);
    } catch(...) {
        if(failure)*failure=first;
        throw;
    }
}
PcbPlacementResult build_pcb_model(const PcbPlacementInput& input,ExecutionFailureReceipt* failure) {
    return build_pcb_model_strategy(input,failure,false);
}
PcbPlacementSearchResult search_pcb_models(const PcbPlacementInput& input,
    const std::vector<PcbPlacementSearchStrategy>& strategies,ExecutionFailureReceipt* failure) {
    PcbPlacementSearchResult out;
    std::optional<std::tuple<double,double,double,double>> best;
    ExecutionFailureReceipt child;
    ExecutionAccounting pending;
    try {
        for(std::size_t attempt=0;attempt<=strategies.size();++attempt) {
            auto trial=input;
            if(attempt) {
                auto policy=input.floorplan.experiment
                    ?std::make_shared<FloorplanExperiment>(*input.floorplan.experiment)
                    :std::make_shared<FloorplanExperiment>();
                const auto& strategy=strategies[attempt-1];
                if(strategy.shape_area_first)policy->shape_area_first=*strategy.shape_area_first;
                if(strategy.owned_extent_alternatives)policy->owned_extent_alternatives=*strategy.owned_extent_alternatives;
                if(strategy.contract_group_rotations)policy->contract_group_rotations=*strategy.contract_group_rotations;
                if(strategy.granular_minor_occupancy)policy->granular_minor_occupancy=true;
                if(strategy.dual_primary_reservations)policy->dual_primary_reservations=true;
                if(strategy.shape_choice_replays)policy->shape_choice_replays=*strategy.shape_choice_replays;
                trial.floorplan.experiment=std::move(policy);
            }
            child={};pending={};
            // Own the caller prefix here, including an early zone failure
            // before a model has reached floorplan's seed import boundary.
            if(!attempt)pending={input.floorplan.accounting.quantization_engagements,
                                input.floorplan.accounting.fallback_events};
            trial.floorplan.accounting.quantization_engagements.clear();
            trial.floorplan.accounting.fallback_events.clear();
            PcbPlacementSearchAttempt record;
            std::optional<PcbPlacementResult> candidate;
            try {candidate=build_pcb_model_strategy(trial,&child,attempt&&strategies[attempt-1].vertical_compaction);}
            catch(const FloorplanPackingInfeasible& error) {record.detail=error.what();}
            catch(const PcbZoneInfeasible& error) {record.detail=error.what();}
            if(!candidate) {
                if(!child.captured||child.unavailable) {
                    invalidate_execution_failure(&child);
                    throw std::runtime_error("model search: construction failure has no complete receipt");
                }
                append_execution_accounting(pending,child.accounting,&child);child={};
                record.status="construction_failed";
            } else {
                try {append_execution_accounting(pending,pcb_placement_accounting(*candidate),&child);}
                catch(const std::overflow_error&) {invalidate_execution_failure(&child);throw;}
                const auto gates=check_pcb_placement_gates(trial,candidate->model,&pending.quantization_engagements);
                const PcbCheckInput checked(candidate->model);
                const auto fanout=check_fanout(checked,0);
                const auto ratsnest=check_ratsnest(checked);
                const auto& m=candidate->model;
                const double area=m.board_w*m.board_h;
                if(!gates.ok()||gates.composition.hard_red||!fanout.ok||!ratsnest.off_board.empty()||
                   !std::isfinite(area)||m.board_w<=0||m.board_h<=0||
                   !std::isfinite(ratsnest.cross_mm)||ratsnest.cross_mm<0) {
                    record.status="screen_rejected";
                    record.detail="placement/compose/fanout/bounds or finite-ranking screen failed";
                } else {
                    const auto rank=std::make_tuple(area,m.board_w,m.board_h,ratsnest.cross_mm);
                    if(!best||rank<*best) {
                        best=rank;out.incumbent=std::move(candidate);out.incumbent_attempt=attempt;
                        record.status="incumbent";
                    } else record.status="not_improved";
                }
            }
            record.accounting=pending;
            append_execution_accounting(out.accounting,pending,&child);pending={};
            out.attempts.push_back(std::move(record));
        }
        return out;
    } catch(const std::overflow_error&) {
        invalidate_execution_failure(failure);
        throw;
    } catch(...) {
        if(child.unavailable)invalidate_execution_failure(failure);
        else {
            append_execution_accounting(out.accounting,pending,failure);
            capture_execution_failure(failure,std::move(out.accounting),&child);
        }
        throw;
    }
}
} // namespace schgen
