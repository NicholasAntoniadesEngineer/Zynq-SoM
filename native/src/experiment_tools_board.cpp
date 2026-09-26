#include "experiment_tools_internal.hpp"

namespace schgen {
namespace {
using namespace experiment_detail;
std::vector<std::string> reds(const JsonNode &verdict) {
    std::vector<std::string> out;
    for (const auto &[key, value] : kind(verdict, JsonKind::Object).object_value) {
        if (value.kind != JsonKind::Object) continue;
        const auto *ok = object_field(value, "ok");
        if (ok && ok->kind == JsonKind::Bool && !ok->bool_value) out.push_back(key);
    }
    return out;
}
std::string board_dimensions(const JsonNode &v) {
    const auto w = jnum(required(v, "board_w")), h = jnum(required(v, "board_h"));
    return fmt(w) + "x" + fmt(h) + " area=" + fmt(w * h);
}
ExperimentBoardReport run(const ExperimentBoardPaths &paths, const ExperimentBoardHost &host,
    const std::string &argument, const std::vector<std::string> &sheets, bool sweep) {
    if (!host.run_board) throw std::invalid_argument("experiment: native board host is required");
    ExperimentBoardRequest request;
    if (sweep) request.ordinary_via_mm = parse_experiment_ordinary_via(argument);
    // Read both originals before any candidate write or native board invocation.
    const auto spec = read(paths.spec), baseline = read(paths.fallback_baseline);
    auto restore = [&] { publish(paths.spec, spec); publish(paths.fallback_baseline, baseline); };
    ExperimentBoardReport report;
    try {
        if (!sheets.empty())
            publish(paths.spec, render_experiment_json(experiment_either_side_spec(
                parse_compose_document(spec, paths.spec.string()), sheets), 1) + "\n");
        const auto result = host.run_board(request);
        const auto verdict = parse_compose_document(universal_newlines(read(paths.verdict)), paths.verdict.string());
        const auto pcb = read(paths.pcb);
        report = sweep ? format_w11_sweep(argument, sheets, result, verdict, pcb)
                       : format_chir_rung(argument, result, verdict, pcb);
    } catch (...) { restore(); throw; }
    restore();
    return report;
}
} // namespace
ExperimentBoardReport format_chir_rung(const std::string &tag, const ExperimentBoardRun &run,
    const ExperimentDocument &verdict, const std::string &pcb_bytes) {
    const auto stdout_text = universal_newlines(run.stdout_text), stderr_text = universal_newlines(run.stderr_text);
    ExperimentBoardReport out;
    out.pass_token = stdout_text.find("BOARD: PASS") != std::string::npos;
    out.board_exit_code = run.exit_code;
    const auto &v = verdict.data, &rn = required(v, "ratsnest");
    const auto pcb = universal_newlines(pcb_bytes);
    std::size_t vias = 0, at = 0;
    while ((at = pcb.find("\n\t(via", at)) != std::string::npos) { ++vias; at += 6; }
    const auto *fallbacks = object_field(v, "fallbacks");
    out.output = "RUNG " + tag + ": pass=" + (out.pass_token ? "True" : "False") + " md5=" + diagnostic_md5(pcb) + " " +
        board_dimensions(v) + " cross=" + scalar(verdict, required(rn, "cross_mm"), "/ratsnest/cross_mm") +
        " vias=" + std::to_string(vias) + " n_top=" + scalar(verdict, required(rn, "n_top"), "/ratsnest/n_top") +
        " n_bottom=" + scalar(verdict, required(rn, "n_bottom"), "/ratsnest/n_bottom") + " fallbacks=" +
        (fallbacks ? repr_value(verdict, *fallbacks, "/fallbacks") : "{}") + " reds=" + list_repr(reds(v)) + "\n";
    if (!out.pass_token)
        out.output += "RUNG " + tag + " STDOUT TAIL:\n" + tail_lines(stdout_text, 12) + "\n" + tail_characters(stderr_text, 2000) + "\n";
    return out;
}
ExperimentBoardReport format_w11_sweep(const std::string &argument, const std::vector<std::string> &sheets,
    const ExperimentBoardRun &run, const ExperimentDocument &verdict, const std::string &pcb_bytes) {
    const auto stdout_text = universal_newlines(run.stdout_text), stderr_text = universal_newlines(run.stderr_text);
    ExperimentBoardReport out;
    out.pass_token = stdout_text.find("BOARD: PASS") != std::string::npos;
    out.board_exit_code = run.exit_code;
    const auto &v = verdict.data, &rn = required(v, "ratsnest");
    const auto *fallbacks = object_field(v, "fallbacks");
    if (fallbacks) kind(*fallbacks, JsonKind::Object);
    const auto *rejected = fallbacks ? object_field(*fallbacks, "punch_free_plan_rejected") : nullptr;
    out.output = "SWEEP ord=" + argument + " sheets=" + (sheets.empty() ? "-" : document_detail::join(sheets, ",")) +
        ": pass=" + (out.pass_token ? "True" : "False") + " md5=" + diagnostic_md5(universal_newlines(pcb_bytes)) + " " +
        board_dimensions(v) + " cross=" + scalar(verdict, required(rn, "cross_mm"), "/ratsnest/cross_mm") +
        " n_bottom=" + scalar(verdict, required(rn, "n_bottom"), "/ratsnest/n_bottom") + " fb=" +
        (rejected ? (rejected->kind == JsonKind::String ? rejected->string_value : repr_value(verdict, *rejected, "/fallbacks/punch_free_plan_rejected")) : "None") + " reds=" + list_repr(reds(v)) + "\n";
    if (!out.pass_token)
        out.output += "STDOUT TAIL:\n" + tail_lines(stdout_text, 10) + "\n" + tail_characters(stderr_text, 1500) + "\n";
    return out;
}
ExperimentBoardReport run_chir_rung(const ExperimentBoardPaths &paths, const ExperimentBoardHost &host,
    const std::string &tag, const std::vector<std::string> &sheets) { return run(paths, host, tag, sheets, false); }
ExperimentBoardReport run_w11_sweep(const ExperimentBoardPaths &paths, const ExperimentBoardHost &host,
    const std::string &argument, const std::vector<std::string> &sheets) { return run(paths, host, argument, sheets, true); }
} // namespace schgen
