#include "schgen/project_outputs.hpp"

#include "schgen/atomic_file.hpp"
#include "schgen/json.hpp"
#include "schgen/link.hpp"

#include <algorithm>
#include <limits>
#include <map>
#include <stdexcept>

namespace schgen {
namespace {
const JsonNode& field(const JsonNode& node, const std::string& key, JsonKind kind,
                      const std::string& source) {
    const auto* value = object_field(node, key);
    if (node.kind != JsonKind::Object || !value || value->kind != kind)
        throw std::runtime_error(source + ": missing or invalid " + key);
    return *value;
}
XdcStrings strings(const JsonNode& object, const std::string& source) {
    if (object.kind != JsonKind::Object) throw std::runtime_error(source + ": expected object");
    XdcStrings out;
    for (const auto& [name, value] : object.object_value) {
        if (name.empty() || value.kind != JsonKind::String || value.string_value.empty())
            throw std::runtime_error(source + ": expected nonempty string mapping for " + name);
        out.emplace_back(name, value.string_value);
    }
    return out;
}
std::string source_name(const std::filesystem::path& path,
                         const std::filesystem::path& repository) {
    const auto relative = std::filesystem::weakly_canonical(path).lexically_relative(
        std::filesystem::weakly_canonical(repository));
    if (!relative.empty() && *relative.begin() != "..") return relative.generic_string();
    return path.string();
}
}

XdcInput load_project_xdc_input(const std::filesystem::path& repository,
                                const std::filesystem::path& project,
                                const std::vector<CircuitSheetIr>& sheets,
                                XdcInput live,
                                const std::filesystem::path& som,
                                const std::filesystem::path& contract) {
    const auto contract_path = contract.empty() ? project / "som_interface.json" : contract;
    const auto mapping_path = project / "som_mapping.json";
    const auto project_path = project / "project.json";
    const auto contract_data = parse_json_file(contract_path.string());
    const auto& connectors = field(contract_data, "connectors", JsonKind::Object,
                                    contract_path.string());
    live.connectors.clear();
    for (const auto& [ref, connector] : connectors.object_value) {
        live.connectors.emplace_back(ref, strings(
            field(connector, "pins", JsonKind::Object, contract_path.string() + ": " + ref),
            contract_path.string() + ": " + ref));
    }
    const auto mapping = parse_json_file(mapping_path.string());
    // Connector authoring used to enforce protected boot straps at import.
    // Data-driven commands must retain that gate without executing authoring.
    (void)link_mapping_from_json(mapping);
    if (require_string(mapping, "schema", false, mapping_path.string()) != "schgen.som_mapping.v1")
        throw std::runtime_error(mapping_path.string() + ": unsupported schema");
    live.function_map = strings(field(mapping, "function_map", JsonKind::Object,
                                      mapping_path.string()), mapping_path.string());
    const auto straps = strings(field(mapping, "pudc_straps", JsonKind::Object,
                                      mapping_path.string()), mapping_path.string());
    for (const auto& strap : straps) {
        const auto found = std::find_if(live.function_map.begin(), live.function_map.end(),
            [&](const auto& item) { return item.first == strap.first; });
        if (found == live.function_map.end()) live.function_map.push_back(strap);
        else found->second = strap.second;
    }
    live.vcco_rails = strings(field(mapping, "vcco_rail_map", JsonKind::Object,
                                    mapping_path.string()), mapping_path.string());
    for (auto& [bank, rail] : live.vcco_rails) {
        (void)rail;
        if (bank.compare(0, 6, "+VCCO_") == 0) bank.erase(0, 6);
    }
    const auto project_data = parse_json_file(project_path.string());
    const auto& fpga = field(project_data, "fpga", JsonKind::Object, project_path.string());
    live.bank_rails = strings(field(fpga, "bank_rails", JsonKind::Object,
                                    project_path.string()), project_path.string());
    live.ports.clear();
    for (const auto& sheet : sheets) {
        std::map<std::string, const CircuitPortIr*> types;
        for (const auto& type : sheet.port_types) types.emplace(type.net, &type);
        for (const auto& net : sheet.nets) {
            if (net.net_class != "port") continue;
            XdcPort port;
            port.net = net.name;
            port.sheet = sheet.name;
            if (live.ports.size() > static_cast<std::size_t>(std::numeric_limits<int>::max()))
                throw std::runtime_error("too many XDC consumer ports");
            port.type_index = static_cast<int>(live.ports.size());
            const auto type = types.find(net.name);
            if (type != types.end()) {
                port.kind = type->second->kind;
                if (type->second->has_pair_with) port.pair_with = type->second->pair_with;
                if (type->second->has_impedance) port.impedance = type->second->impedance;
            }
            live.ports.push_back(std::move(port));
        }
    }
    live.contract_path = contract_path.string();
    live.contract_source = source_name(contract_path, repository);
    live.som_source = source_name(som, repository);
    return live;
}

void publish_text(const std::filesystem::path& target, const std::string& text) {
    write_atomic_file(target.string(), std::vector<uint8_t>(text.begin(), text.end()));
}
}
