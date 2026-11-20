#include "schgen/subsystem_authoring.hpp"
#include "schgen/subsystem_registration.hpp"
#include "schgen/subsystem_data.hpp"
#include <algorithm>

namespace schgen {
const std::vector<SubsystemDefinition>& subsystem_definitions() {
    static const std::vector<SubsystemDefinition> definitions = append_configured_subsystem_definitions({
    });
    return definitions;
}
namespace {
bool compiled(const std::string& name) {
    const auto& all = subsystem_definitions();
    return std::any_of(all.begin(), all.end(), [&](const SubsystemDefinition& d) { return d.name == name; });
}
JsonNode filed_document(const std::string& name, const AuthoringContext& context) {
    const std::filesystem::path file = context.library / name / subsystem_data_file;
    if (context.library.empty() || !std::filesystem::is_regular_file(file))
        throw CircuitAuthoringError("unknown subsystem " + name);
    JsonNode document = parse_json_file(file.string());
    if (subsystem_data_definition(document, file.string()).name != name)
        throw CircuitAuthoringError("subsystem file " + file.string() + ": its name differs from its folder " + name);
    return document;
}
SubsystemDefinition filed(const std::string& name, const AuthoringContext& context) {
    return subsystem_data_definition(filed_document(name, context), name);
}
}
const SubsystemDefinition& subsystem_definition(const std::string& name) {
    for (const auto& d : subsystem_definitions()) if (d.name == name) return d;
    throw CircuitAuthoringError("unknown subsystem " + name);
}
SubsystemDefinition subsystem_definition(const std::string& name, const AuthoringContext& context) {
    const std::filesystem::path file = context.library / name / subsystem_data_file;
    const bool on_file = !context.library.empty() && std::filesystem::is_regular_file(file);
    if (compiled(name) && on_file)
        throw CircuitAuthoringError("subsystem " + name + " is defined twice: compiled in and by " + file.string());
    return compiled(name) ? subsystem_definition(name) : filed(name, context);
}
std::vector<SubsystemDefinition> subsystem_library(const AuthoringContext& context) {
    std::vector<SubsystemDefinition> all = subsystem_definitions();
    for (SubsystemDefinition& definition : subsystem_data_definitions(context.library)) {
        if (compiled(definition.name))
            throw CircuitAuthoringError("subsystem " + definition.name + " is defined twice: compiled in and by a file");
        all.push_back(std::move(definition));
    }
    std::sort(all.begin(), all.end(), [](const SubsystemDefinition& a, const SubsystemDefinition& b) { return a.name < b.name; });
    return all;
}
CircuitSheetIr author_subsystem(const std::string& name, const SubsystemMeta& meta, const AuthoringContext& context) {
    if (!compiled(name)) return author_subsystem_data(filed_document(name, context), meta, context);
    if (!context.library.empty() && std::filesystem::is_regular_file(context.library / name / subsystem_data_file))
        throw CircuitAuthoringError("subsystem " + name + " is defined twice: compiled in and by a file");
#ifdef SCHGEN_CONFIGURED_SUBSYSTEMS
    // Existing extension API remains usable. A configured build's source-purity
    // check FAILS CLOSED on this erased dispatch until that build supplies named
    // checked dispatch and a reviewed constructor scope; this is not a waiver.
    return subsystem_definition(name).circuit(meta,context);
#else
    throw CircuitAuthoringError("unregistered native subsystem constructor target "+name);
#endif
}
} // namespace schgen
