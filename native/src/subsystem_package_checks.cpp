#include "schgen/subsystem_package_checks.hpp"

#include <set>
#include <utility>

namespace schgen {
bool SubsystemLocalResult::ok() const {
    return errors.empty() && design_rules.decap.empty() && design_rules.ep.empty() &&
           design_rules.strap.empty();
}
std::string SubsystemLocalResult::summary() const {
    std::string text = ok() ? "PASS: local subsystem contracts" : "FAIL: local subsystem contracts";
    for (const auto& error : errors) text += "\n  " + error;
    for (const auto* findings : {&design_rules.decap, &design_rules.ep, &design_rules.strap})
        for (const auto& finding : *findings) text += "\n  " + finding;
    for (const auto* findings : {&design_rules.i2c, &design_rules.reset})
        for (const auto& finding : *findings) text += "\n  advisory: " + finding;
    return text;
}

SubsystemLocalResult check_subsystem_local(const SubsystemDefinition& definition,
    const AuthoringContext& context, const DesignRuleSymbolResolver& resolve) {
    SubsystemLocalResult result;
    try {
        if (definition.name.empty() || !definition.circuit)
            throw CircuitAuthoringError("missing native subsystem factory");
        const auto circuit = parse_circuit_ir(authored_circuit_json(
            definition.circuit(SubsystemMeta{}, context)));
        if (circuit.name != definition.name) result.errors.push_back("circuit name differs from package");
        if (circuit.parts.empty()) result.errors.push_back("netlist has no parts; implement the scaffold");
        const std::set<std::string> declared(definition.interface.begin(), definition.interface.end());
        if (declared.empty() || declared.count("") || declared.size() != definition.interface.size())
            result.errors.push_back("missing, empty, or duplicate abstract interface");
        std::set<std::string> external, all_nets;
        for (const auto& net : circuit.nets) {
            all_nets.insert(net.name);
            if (net.net_class != "signal") external.insert(net.name);
        }
        if (external != declared) result.errors.push_back("external nets differ from abstract interface");

        // DesignRuleIndex intentionally tolerates missing symbols for legacy
        // board callers. Local authoring tests must not inherit that skip.
        std::vector<SymbolDef> symbols;
        std::set<std::string> resolved;
        std::vector<std::pair<std::string, std::vector<std::string>>> pins;
        for (const auto& part : circuit.parts) {
            if (resolved.insert(part.lib_id).second) {
                auto symbol = resolve(part.lib_id);
                if (symbol.lib_id != part.lib_id || symbol.pins.empty())
                    throw CircuitAuthoringError("missing symbol pins for " + part.lib_id);
                symbols.push_back(std::move(symbol));
            }
            std::set<std::string> numbers;
            for (const auto& symbol : symbols) if (symbol.lib_id == part.lib_id)
                for (const auto& pin : symbol.pins) numbers.insert(pin.number);
            pins.emplace_back(part.ref, std::vector<std::string>(numbers.begin(), numbers.end()));
        }
        CircuitAuthor(circuit, context).validate(pins);
        result.design_rules = check_design_rules({circuit}, symbols);

        std::string unknown = "NOT_A_PORT";
        while (all_nets.count(unknown)) unknown += "_X";
        bool rejected = false;
        try { CircuitAuthor(circuit, context).bind({{unknown, "X"}}); }
        catch (const CircuitAuthoringError&) { rejected = true; }
        if (!rejected) result.errors.push_back("unknown direct bind accepted");
        JsonNode bind;
        bind.kind = JsonKind::Object;
        JsonNode target;
        target.kind = JsonKind::String;
        target.string_value = "X";
        bind.object_value.emplace_back(unknown, target);
        JsonNode meta;
        meta.kind = JsonKind::Object;
        meta.object_value.emplace_back("bind", bind);
        rejected = false;
        try { (void)definition.circuit(SubsystemMeta(meta), context); }
        catch (const CircuitAuthoringError&) { rejected = true; }
        if (!rejected) result.errors.push_back("factory ignores unknown metadata bind");

        AuthoringStrings mapping;
        bind.object_value.clear();
        std::size_t serial = 0;
        for (const auto& source : definition.interface) {
            std::string destination;
            do { destination = "SCAFFOLD_BOUND_" + std::to_string(serial++); }
            while (all_nets.count(destination));
            mapping.emplace_back(source, destination);
            target.string_value = destination;
            bind.object_value.emplace_back(source, target);
        }
        meta.object_value[0].second = bind;
        auto expected = CircuitAuthor(circuit, context);
        expected.bind(mapping);
        const auto actual = definition.circuit(SubsystemMeta(meta), context);
        if (!authoring_json_equal(authored_circuit_json(expected.finish()), authored_circuit_json(actual)))
            result.errors.push_back("factory does not apply positive metadata bind exactly");
    } catch (const std::exception& error) {
        result.errors.push_back(error.what());
    }
    return result;
}
} // namespace schgen
