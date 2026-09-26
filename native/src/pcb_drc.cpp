#include "schgen/pcb_drc.hpp"
#include "schgen/json.hpp"
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <set>
#include <unistd.h>

namespace schgen {
namespace {
struct DrcScratch {
    std::filesystem::path path;
    DrcScratch() {
        auto pattern = (std::filesystem::temp_directory_path() / "schgen_drc_XXXXXX").string();
        if (!::mkdtemp(pattern.data())) throw ProcessError("cannot create DRC scratch directory");
        path = pattern;
    }
    ~DrcScratch() { std::error_code error; std::filesystem::remove_all(path, error); }
};
const JsonNode& required_array(const JsonNode& document, const std::string& name) {
    const auto* value = object_field(document, name);
    if (!value || value->kind != JsonKind::Array)
        throw ProcessError("invalid KiCad DRC report: missing/non-array " + name);
    return *value;
}
}
PcbDrcResult parse_pcb_drc_report(const std::string& report, const ProcessResult& process) {
    // No --exit-code-violations is requested: every nonzero status is a tool failure.
    if (process.exit_code != 0)
        throw ProcessError("KiCad DRC failed (" + std::to_string(process.exit_code) + "): " + process.stderr_text);
    const auto document = parse_json_text(report, "KiCad DRC report");
    if (document.kind != JsonKind::Object) throw ProcessError("invalid KiCad DRC report root");
    const auto& violations = required_array(document, "violations");
    const auto& unconnected = required_array(document, "unconnected_items");
    PcbDrcResult result;
    result.returncode = process.exit_code;
    result.n_violations = violations.array_value.size();
    result.n_unconnected = unconnected.array_value.size();
    const std::set<std::string> sampled_out{"silk_overlap", "silk_over_copper", "courtyards_overlap", "footprint_type_mismatch"};
    for (const auto& violation : violations.array_value) {
        if (violation.kind != JsonKind::Object) throw ProcessError("invalid DRC violation record");
        const auto* type = object_field(violation, "type");
        const auto* severity = object_field(violation, "severity");
        if (!severity) result.n_errors.reset();
        else {
            if (severity->kind != JsonKind::String ||
                (severity->string_value != "error" && severity->string_value != "warning"))
                throw ProcessError("invalid DRC violation severity");
            if (result.n_errors && severity->string_value == "error") ++*result.n_errors;
        }
        if (type && type->kind != JsonKind::String) throw ProcessError("invalid DRC violation type");
        const std::string name = type ? type->string_value : "?";
        ++result.by_type[name];
        if (!sampled_out.count(name) && result.other_sample.size() < 12) result.other_sample.push_back(name);
    }
    result.stderr_tail = process.stderr_text.substr(process.stderr_text.size() > 400 ? process.stderr_text.size() - 400 : 0);
    return result;
}
std::vector<std::string> pcb_drc_arguments(const std::filesystem::path& board,
        const std::filesystem::path& report, bool include_warnings) {
    std::vector<std::string> args{"kicad-cli", "pcb", "drc", "--format", "json", "--severity-error"};
    if (include_warnings) args.push_back("--severity-warning");
    args.insert(args.end(), {"--refill-zones", "-o", report.string(), std::filesystem::absolute(board).string()});
    return args;
}
PcbDrcResult run_pcb_drc(const std::filesystem::path& board, std::chrono::milliseconds timeout, bool include_warnings) {
    if (!std::filesystem::is_regular_file(board)) throw ProcessError("DRC board file does not exist: " + board.string());
    DrcScratch scratch;
    const auto report = scratch.path / "drc.json";
    const auto process = run_process(pcb_drc_arguments(board, report, include_warnings), timeout);
    std::ifstream input(report, std::ios::binary);
    if (!input) throw ProcessError("KiCad DRC produced no readable report: " + process.stderr_text);
    const std::string bytes{std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
    if (input.bad()) throw ProcessError("cannot read KiCad DRC report");
    return parse_pcb_drc_report(bytes, process);
}
}
