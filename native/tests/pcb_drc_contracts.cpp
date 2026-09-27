#include "schgen/pcb_drc.hpp"
#include <iostream>
#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <unistd.h>

namespace {
void require(bool value) { if (!value) throw std::runtime_error("DRC contract failed"); }
template<class F> void rejects(F action) {
    bool failed = false;
    try { action(); } catch (const std::exception&) { failed = true; }
    require(failed);
}
}
int main() {
    using namespace schgen;
    try {
        for (bool warnings : {false, true}) {
            const auto args = pcb_drc_arguments("a board.kicad_pcb", "/tmp/a report.json", warnings);
            require(std::count(args.begin(), args.end(), "--refill-zones") == 1);
            require(std::count(args.begin(), args.end(), "--severity-error") == 1);
            require(std::count(args.begin(), args.end(), "--severity-warning") == (warnings ? 1 : 0));
            require(args.back() == std::filesystem::absolute("a board.kicad_pcb").string());
            require(args[args.size()-2] == "/tmp/a report.json");
        }
        const std::string clean = R"({"violations":[],"unconnected_items":[]})";
        const auto empty = parse_pcb_drc_report(clean, {});
        require(empty.n_violations == 0 && empty.n_unconnected == 0 && empty.by_type.empty());
        const auto report = parse_pcb_drc_report(R"({"violations":[{"type":"silk_overlap"},{"type":"clearance"},{"type":"clearance"},{}],"unconnected_items":[{},{}]})", {0, "", std::string(450, 'x')});
        require(report.n_violations == 4 && report.n_unconnected == 2);
        require(report.by_type.at("clearance") == 2 && report.by_type.at("?") == 1);
        require(report.other_sample == std::vector<std::string>({"clearance", "clearance", "?"}));
        require(report.stderr_tail.size() == 400);
        require(!report.n_errors);
        require(empty.n_errors && *empty.n_errors == 0);
        const auto severities = parse_pcb_drc_report(R"({"violations":[{"type":"clearance","severity":"error"},{"type":"silk_overlap","severity":"warning"}],"unconnected_items":[]})", {});
        require(severities.n_errors && *severities.n_errors == 1 && severities.n_violations == 2);
        rejects([] { parse_pcb_drc_report(R"({"violations":[{"severity":"unknown"}],"unconnected_items":[]})", {}); });
        for (const auto* invalid : {"", "{", "[]", "{}", R"({"violations":[],"unconnected_items":null})", R"({"violations":[1],"unconnected_items":[]})", R"({"violations":[{"type":2}],"unconnected_items":[]})"})
            rejects([&] { parse_pcb_drc_report(invalid, {}); });
        for (int code : {-9, 1, 5}) rejects([&] { parse_pcb_drc_report(clean, {code, "", "failed"}); });
        // The child failure must survive even when no report was produced.
        // This also rejects a failed child before trusting any stale report.
        for (int code : {-5, 1, 133}) {
            bool diagnosed = false;
            try {
                read_pcb_drc_report("/nonexistent/schgen-drc-report.json",
                                    {code, "child stdout", "Swift runtime failure"});
            } catch (const ProcessError& error) {
                const std::string message = error.what();
                diagnosed = message.find("KiCad DRC failed (" + std::to_string(code) + ")") != std::string::npos &&
                            message.find("Swift runtime failure") != std::string::npos &&
                            message.find("child stdout") != std::string::npos;
            }
            require(diagnosed);
        }
        rejects([] { read_pcb_drc_report("/nonexistent/schgen-drc-report.json", {}); });
        auto scratch_pattern = (std::filesystem::temp_directory_path() / "schgen_drc_contract_XXXXXX").string();
        require(::mkdtemp(scratch_pattern.data()) != nullptr);
        struct Cleanup {
            std::filesystem::path path;
            ~Cleanup() { std::error_code error; std::filesystem::remove_all(path, error); }
        } cleanup{scratch_pattern};
        const auto report_path = cleanup.path / "drc.json";
        { std::ofstream output(report_path); output << clean; require(bool(output)); }
        require(read_pcb_drc_report(report_path, {}).n_errors == 0);
        rejects([&] { read_pcb_drc_report(report_path, {-5, "", "crashed with stale report"}); });
        { std::ofstream output(report_path); output << "{"; require(bool(output)); }
        rejects([&] { read_pcb_drc_report(report_path, {}); });
        std::string many = "{\"violations\":[";
        for (int i = 0; i < 20; ++i) { if (i) many += ','; many += "{\"type\":\"clearance\"}"; }
        many += "],\"unconnected_items\":[]}";
        require(parse_pcb_drc_report(many, {}).other_sample.size() == 12);
        rejects([] { run_pcb_drc("/nonexistent/schgen-board.kicad_pcb"); });
        std::cout << "DRC parsing, failure handling and sample bounds pass\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
