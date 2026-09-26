#include "compose_repair_internal.hpp"

namespace schgen {
using namespace compose_detail;
ComposeCommandResult run_compose_command(const ComposeCommandOptions &options,const ComposeCommandPaths &paths,const ComposeCommandHost &host) {
    if(!host.build_model)throw std::invalid_argument("compose: native build_model host is required");
    ComposeCommandResult result;
    auto emit=[&](const std::string &s){result.output+=s;if(host.output)host.output(s);};
    // A malformed intent fails before measuring, even in dry-run mode.
    const auto moves=options.repair?parse_compose_allow_intent(options.allow_intent):std::vector<ComposeSpecEdit>{};
    emit(options.repair?"compose: measuring the emitted board (build_model + gates) ...\n":"compose: measuring the emitted board (build_model + gates)...\n");
    const auto initial=host.build_model();auto before=measure_compose_ledger(initial.input,initial.model);
    if(!options.repair) {
        write_compose_ledger(before,"measure",paths.ledger_json,paths.ledger_markdown);
        const auto &b=required(before.data,"board"),&agg=required(before.data,"aggregate_hard_margin");
        const auto &triggers=required(before.data,"repair_triggers").array_value;
        emit("compose: board "+fmt(jnum(required(b,"w")))+"x"+fmt(jnum(required(b,"h")))+" = "+scalar(before,required(b,"area_mm2"),"/board/area_mm2")+" mm^2; hard margin sum "+scalar(before,required(agg,"sum"),"/aggregate_hard_margin/sum")+" / min "+scalar(before,required(agg,"min"),"/aggregate_hard_margin/min")+" mm; "+std::to_string(triggers.size())+" trigger(s) -> "+paths.ledger_json.string()+"\n");
        for(const auto &t:triggers)emit("  TRIGGER: "+jstr(t)+"\n");
        for(const auto &s:required(before.data,"seat_consistency").array_value)emit("  SEAT-CONSISTENCY: "+jstr(s)+"\n");
        return result;
    }
    const auto original=read(paths.spec);
    const auto raw=parse_compose_document(original,paths.spec.string());
    const auto index=pcb_final_compose_index(initial.input,initial.model);
    const auto candidates=propose_compose_repairs(before,raw,moves);
    const auto &gated=required(before.data,"intent_gated").array_value;
    emit("compose: "+std::to_string(required(before.data,"repair_triggers").array_value.size())+" trigger(s), "+std::to_string(candidates.size())+" candidate edit(s), "+std::to_string(gated.size())+" intent-gated\n");
    for(const auto &g:gated)emit("  INTENT-GATED: "+jstr(g)+"\n");
    if(candidates.empty()){write_compose_ledger(before,"measure (no candidates)",paths.ledger_json,paths.ledger_markdown);return result;}
    std::vector<ComposeCandidate> predictions;
    for(const auto &e:candidates) {
        try {predictions.push_back(evaluate_compose_candidate(initial.input,raw,e,index));}
        catch(const std::exception &ex){ComposeCandidate c;c.edit=e;c.error=ex.what();predictions.push_back(c);}
    }
    const auto ranking=rank_compose_candidates(std::move(predictions));emit(ranking.output);
    if(options.dry_run||ranking.ranked.empty()){write_compose_ledger(before,"measure/dry-run",paths.ledger_json,paths.ledger_markdown);return result;}
    if(!host.run_board)throw std::invalid_argument("compose: apply requires the complete native board command host");
    // max_steps is deliberately unused: Python reserves it and tries only the
    // single best candidate. Do not turn failed predictions into a repair loop.
    const auto &best=ranking.ranked.front().edit;
    const auto edited=render_compose_json(best.apply(raw));
    if(read(paths.spec)!=original)throw std::runtime_error("compose: floorplan changed during prediction; refusing to overwrite it");
    emit("compose: applying "+best.describe()+"\n");
    publish(paths.spec,edited);
    bool pending=true;
    auto restore=[&]{
        if(!pending)return;
        // Never destroy a concurrent human edit while unwinding a failed run.
        if(read(paths.spec)!=edited)throw std::runtime_error("compose: floorplan changed during rebuild; refusing to overwrite it during rollback");
        publish(paths.spec,original);pending=false;
    };
    try {
        const auto run=host.run_board();bool ok=run.exit_code==0;ComposeDocument after;
        if(ok) {
            const auto rebuilt=host.build_model();after=measure_compose_ledger(rebuilt.input,rebuilt.model);
            const auto decision=accept_compose_repair(before,after,best.target_key?std::set<ComposeTermKey>{*best.target_key}:std::set<ComposeTermKey>{});
            ok=decision.ok;
            if(best.intent()&&!ok&&std::all_of(decision.reasons.begin(),decision.reasons.end(),[](const auto &s){return s.find("area grew")!=s.npos;})) {
                emit("compose: intent edit grew the board — ESCALATION to the orchestrator's wave judgment (IM5), reverting the file; measured growth:\n");
                for(const auto &r:decision.reasons)emit("  ESCALATE: "+r+"\n");
            }
            if(!ok)for(const auto &r:decision.reasons)emit("  REJECT: "+r+"\n");
        } else {
            // Python slices codepoints, not UTF-8 bytes.
            document_detail::codepoints(run.stdout_text);
            std::size_t count=0,start=run.stdout_text.size();
            while(start&&count<2000){--start;if((static_cast<unsigned char>(run.stdout_text[start])&0xc0)!=0x80)++count;}
            emit(run.stdout_text.substr(start)+"\ncompose: board build FAILED under the edit\n");
        }
        if(!ok) {
            restore();emit("compose: REVERTED carrier/floorplan.json\n");
            write_compose_ledger(before,"rejected: "+best.describe(),paths.ledger_json,paths.ledger_markdown);
            result.exit_code=1;return result;
        }
        if(read(paths.spec)!=edited)throw std::runtime_error("compose: floorplan changed during rebuild; cannot accept a different edit");
        // The independent decision commits the spec. A subsequent report I/O
        // failure must not restore the spec behind an already published
        // "applied" JSON history entry (JSON/Markdown are separate writes).
        pending=false;result.applied=true;
        write_compose_ledger(after,"applied: "+best.describe(),paths.ledger_json,paths.ledger_markdown);
        emit("compose: ACCEPTED (ledger updated) — commit is a human review step (reviewed-JSON-diff rule, D-1)\n");
        return result;
    } catch(...) {restore();throw;}
}
} // namespace schgen
