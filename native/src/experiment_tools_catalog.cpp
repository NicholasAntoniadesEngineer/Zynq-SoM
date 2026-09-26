#include "experiment_tools_internal.hpp"

namespace schgen {
std::filesystem::path experiment_circuit_json_path(const std::filesystem::path &handle) {
    return handle.parent_path().filename() == handle.stem() ? handle.parent_path()/"circuit.json"
        : handle.parent_path()/handle.stem()/"circuit.json";
}
NativeCircuitDump prepare_native_circuit_dump(const CircuitSheetIr &circuit, const std::filesystem::path &handle) {
    using namespace experiment_detail;
    ExperimentDocument document;
    document.data = authored_circuit_json(circuit);
    const auto roundtrip = parse_circuit_ir(document.data);
    if (!authoring_json_equal(authored_circuit_json(roundtrip), document.data))
        throw CircuitAuthoringError("circuit IR roundtrip drifted: " + handle.string());
    for (const auto &port : circuit.port_types)
        if (port.has_level_v) document.float_paths.insert("/port_types/" + pointer(port.net) + "/level_v");
    for (const auto &[rail, loads] : field(document.data, "loads").object_value)
        for (std::size_t i = 0; i < loads.array_value.size(); ++i)
            document.float_paths.insert("/loads/" + pointer(rail) + "/" + std::to_string(i) + "/0");
    return {experiment_circuit_json_path(handle), render_experiment_json(document, 2, false) + "\n"};
}
namespace {
std::vector<CarrierPackageFactory> factories(const ProjectPaths &paths, const std::string &project, ProjectAuthoringInput input) {
    if (input.project_root.empty()) input.project_root = paths.project_root;
    if (!input.context.pins) input.context.pins = make_authoring_context(paths.repository_root).pins;
    auto result = native_project_factories(project, input);
    std::sort(result.begin(), result.end(), [](const auto &a, const auto &b) { return a.name < b.name; });
    if (result.empty()) throw CircuitAuthoringError("no subsystems found");
    return result;
}
} // namespace
std::vector<NativeCircuitDump> prepare_native_circuit_dumps(const ProjectPaths &paths,
    const std::string &project, ProjectAuthoringInput input) {
    std::vector<NativeCircuitDump> result;
    for (const auto &factory : factories(paths, project, std::move(input)))
        result.push_back(prepare_native_circuit_dump(factory.circuit(), paths.subsystems_dir/factory.name/(factory.name+".py")));
    return result;
}
void publish_native_circuit_dump(const NativeCircuitDump &dump) {
    if (!dump.path.parent_path().empty()) std::filesystem::create_directories(dump.path.parent_path());
    experiment_detail::publish(dump.path, dump.bytes);
}
std::string run_dump_circuits(const ProjectPaths &paths, const std::string &project, ProjectAuthoringInput input) {
    std::vector<std::filesystem::path> written;
    for (const auto &factory : factories(paths, project, std::move(input))) {
        const auto dump = prepare_native_circuit_dump(factory.circuit(), paths.subsystems_dir/factory.name/(factory.name+".py"));
        publish_native_circuit_dump(dump); written.push_back(dump.path);
    }
    std::string output;
    for (const auto &path : written) {
        const auto relative = path.lexically_relative(paths.repository_root);
        if (relative.empty() || *relative.begin() == "..") throw ProjectError("dump path is outside repository: " + path.string());
        output += relative.generic_string() + "\n";
    }
    return output + "dumped " + std::to_string(written.size()) + " circuit.json files\n";
}
} // namespace schgen
