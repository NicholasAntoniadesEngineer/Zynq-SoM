#include "schgen/pcb_drc.hpp"
#include <iostream>
#include <algorithm>

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
        std::string many = "{\"violations\":[";
        for (int i = 0; i < 20; ++i) { if (i) many += ','; many += "{\"type\":\"clearance\"}"; }
        many += "],\"unconnected_items\":[]}";
        require(parse_pcb_drc_report(many, {}).other_sample.size() == 12);
        rejects([] { run_pcb_drc("/nonexistent/schgen-board.kicad_pcb"); });
        std::cout << "DRC parsing, failure handling and sample bounds pass\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
