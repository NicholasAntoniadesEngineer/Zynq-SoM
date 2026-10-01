#include "pcb_placement_fixture.hpp"
#include "schgen/compose_repair.hpp"
#include "schgen/atomic_file.hpp"
#include <cstdlib>
#include <iostream>
#include <limits>
#include <unistd.h>

namespace {
using namespace schgen;
using namespace placement_fixture;
void require(bool ok, const std::string& why) {
    if (!ok) throw std::runtime_error(why);
}
QuantizationCounts projection(const PcbPlacementInput& input, const PcbModel& model) {
    const PcbCheckInput checked(model);
    const auto policy = pcb_placement_gate_policy(input);
    const auto index = pcb_final_compose_index(input, model);
    std::map<std::string, JsonNode> advisory;
    for (const auto& inst : model.insts) {
        auto p = policy.contracts.find(inst.sheet);
        if (p != policy.contracts.end()) advisory[p->first] = p->second;
    }
    QuantizationCounts terms, flow, advice, total;
    (void)measure_pcb_compose_terms(checked, index, policy, &terms);
    (void)check_pcb_placement_flow(checked, policy, nullptr, &flow);
    (void)check_pcb_placement_flow(checked, policy, &advisory, &advice);
    // Each branch must contribute: omitting any one forwarding edge must fail.
    for (const auto* part : {&terms, &flow, &advice}) {
        require(!part->empty(), "fixture must exercise all three measurement edges");
        checked_quantization_merge(total, *part);
    }
    return total;
}
void measurements(const std::filesystem::path& root, const std::string& project) {
    auto f = load(root, project);
    const auto base = pcb_model_from_json(f.model, f.expected_pool);
    const auto oracle = parse_json_file((root / "native/tests/data/compose_repair" /
                                       (project + "_strict.json")).string());
    for (const auto& row : field(oracle, "rows").array_value) {
        auto model = base;
        if (string(row, "name") == "moved_power_first")
            for (auto& inst : model.insts) if (inst.sheet == "power") { inst.x += 100; break; }
        if (string(row, "name") == "missing_power")
            model.insts.erase(std::remove_if(model.insts.begin(), model.insts.end(),
                [](const auto& inst) { return inst.sheet == "power"; }), model.insts.end());
        const auto expected = projection(f.input, model);
        QuantizationCounts actual{{"unrelated", 17}}, wanted = actual;
        checked_quantization_merge(wanted, expected);
        const auto measured = measure_compose_ledger(f.input, model, &actual);
        require(actual == wanted, "three-call exact projection");
        require(render_compose_json(measured, 1, true) == string(row, "ledger"), "immutable ledger bytes");
        require(render_compose_json(measure_compose_ledger(f.input, model), 1, true) ==
                string(row, "ledger"), "default API unchanged");
        (void)measure_compose_ledger(f.input, model, &actual);
        checked_quantization_merge(wanted, expected);
        require(actual == wanted, "caller accumulation, no reset");
        QuantizationCounts fresh;
        (void)measure_compose_ledger(f.input, model, &fresh);
        require(fresh == expected, "independent invocation ownership");
        QuantizationCounts saturated;
        for (const auto& entry : expected) saturated[entry.first] = std::numeric_limits<std::size_t>::max();
        bool rejected = false;
        try { (void)measure_compose_ledger(f.input, model, &saturated); }
        catch (const std::overflow_error&) { rejected = true; }
        require(rejected, "counter overflow propagates");
    }
}
struct Scratch {
    std::filesystem::path path;
    Scratch() {
        char name[] = "/private/tmp/compose-accounting-test.XXXXXX";
        auto p = mkdtemp(name);
        if (!p) throw std::runtime_error("mkdtemp");
        path = p;
    }
    ~Scratch() { std::error_code ec; std::filesystem::remove_all(path, ec); }
};
void publish(const std::filesystem::path& path, const std::string& bytes) {
    write_atomic_file(path.string(), {bytes.begin(), bytes.end()});
}
void commands(const std::filesystem::path& root) {
    auto f = load(root, "devkit_mini");
    const auto base = pcb_model_from_json(f.model, f.expected_pool);
    auto initial = base;
    initial.insts.erase(std::remove_if(initial.insts.begin(), initial.insts.end(),
        [](const auto& i) { return i.sheet != "uart_bridge" && i.sheet != "usb_uart_connector"; }), initial.insts.end());
    for (auto& i : initial.insts) if (i.sheet == "uart_bridge") i.x += 50.;
    const auto oracle = parse_json_file((root / "native/tests/data/compose_repair/workflow_strict.json").string());
    for (const auto& row : field(oracle, "drivers").array_value) for (bool collect : {false, true}) {
        Scratch tmp;
        ComposeCommandPaths paths{tmp.path / "floorplan.json", tmp.path / "ledger.json", tmp.path / "ledger.md"};
        publish(paths.spec, string(row, "original"));
        const auto mode = string(row, "mode");
        ComposeCommandOptions options;
        options.repair = true;
        options.dry_run = mode == "dry";
        QuantizationCounts actual{{"unrelated", 19}}, expected = actual;
        int builds = 0, runs = 0;
        ComposeCommandHost host;
        host.build_model = [&] {
            ++builds;
            auto input = f.input;
            input.floorplan.spec = floorplan_spec_from_json(parse_compose_document(read(paths.spec)).data, "floorplan.json");
            auto model = builds == 1 ? initial : base;
            if (builds > 1 && mode == "rejected") model.insts[0].x += 1000.;
            if (collect) checked_quantization_merge(expected, projection(input, model));
            return ComposeBoardSnapshot{input, model};
        };
        host.run_board = [&] {
            ++runs;
            std::string text;
            for (int i = 0; i < 2003; ++i) text += "µ";
            return ComposeBoardRun{mode == "failed" ? 7 : 0, mode == "failed" ? text + "tail" : ""};
        };
        const auto got = collect ? run_compose_command(options, paths, host, &actual)
                                 : run_compose_command(options, paths, host);
        require(actual == expected, mode + " initial/rebuilt measurement counts");
        require(builds == field(row, "build_calls").number_value &&
                runs == field(row, "board_calls").number_value, mode + " call budget");
        require(got.exit_code == field(row, "code").number_value, mode + " exit");
        require(got.output == string(row, "stdout"), mode + " immutable stdout");
        require(read(paths.spec) == string(row, "final_spec"), mode + " immutable spec");
        require(read(paths.ledger_json) == string(row, "ledger"), mode + " immutable JSON");
        require(read(paths.ledger_markdown) == string(row, "markdown"), mode + " immutable Markdown");
    }
}
}
int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: compose_measure_accounting_contracts REPO_ROOT");
        measurements(argv[1], "carrier");
        measurements(argv[1], "devkit_mini");
        commands(argv[1]);
        std::cout << "compose measurement accounting PASS\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
