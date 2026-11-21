#include "schgen/board_power.hpp"
#include "schgen/link.hpp"
#include "schgen/sheet_roles.hpp"
#include "model_checks_internal.hpp"

namespace schgen {
using namespace model_checks;

namespace {
const char* const power_class = "power";
const std::vector<std::string_view> pass_through_kinds{"load_switch", "efuse"};
const std::vector<PartClass> pass_through_classes{PartClass::resistor, PartClass::inductor, PartClass::ferrite};

[[noreturn]] void refuse(const std::string& what) { throw ModelCheckError("board power: " + what); }

std::string bound(const std::map<std::string, std::string>& rebound, const std::string& rail) {
    const auto found = rebound.find(rail);
    return found == rebound.end() ? rail : found->second;
}

PowerPolicy policy_from(const BoardPower& power, const ModuleDefinition& module, const std::map<std::string, std::string>& rebound) {
    PowerPolicy policy = default_power_policy();
    std::map<std::string, const PowerSupply*> supplies;
    for (const auto& supply : module.supplies) supplies[bound(rebound, supply.rail)] = &supply;
    std::set<std::string> taken;
    for (const auto& source : power.sources) {
        if (!source.from_module) {
            policy.sources.emplace_back(source.rail, PowerSource{source.volts, source.amps, source.basis});
            continue;
        }
        const auto found = supplies.find(source.rail);
        if (found == supplies.end()) refuse("source " + source.rail + " names the module as supplier, but the module file supplies no such rail");
        taken.insert(source.rail);
        policy.sources.emplace_back(source.rail, PowerSource{found->second->volts, found->second->amps, found->second->basis});
    }
    for (const auto& [rail, supply] : supplies) {
        (void)supply;
        if (!taken.count(rail)) refuse("the module supplies " + rail + " but the board power.sources does not take it");
    }
    for (const auto& rail : power.rails) policy.rails.emplace_back(rail.rail, PowerRail{rail.volts, "entry: " + rail.basis});
    for (const auto& [rail, source] : policy.sources) {
        if (find(policy.rails, rail)) refuse("rail " + rail + " is both a source and a power.rails entry");
        policy.rails.emplace_back(rail, PowerRail{source.volts, "source: " + source.note});
    }
    if (power.inlet) policy.inlet = PowerInlet{power.inlet->rail, power.inlet->bulk};
    for (const auto& rail : module.regulated_rails) policy.module_rails.push_back(bound(rebound, rail));
    policy.module_rails_basis = module.regulated_rails_basis;
    return policy;
}

std::string volts_text(double volts) { return g(volts); }
}

PowerPolicy explicit_power_policy(const BoardPower& power, const ModuleDefinition& module) {
    return policy_from(power, module, {});
}

PowerPolicy board_power_policy(const BoardPower& power, const ModuleDefinition& module,
        const std::map<std::string, std::string>& rebound_module_rails, const std::vector<std::string>& module_sheets,
        const std::vector<ProjectCircuit>& sheets, const PartFacts& facts) {
    PowerPolicy policy = policy_from(power, module, rebound_module_rails);
    policy.module_sheets = module_sheets;
    std::map<std::string, std::set<std::string>> nets;
    for (const auto& sheet : sheets) for (const auto& net : sheet.circuit.nets) nets[net.name].insert(net.net_class);
    for (const auto& [rail, entry] : policy.rails) {
        (void)entry;
        if (!nets.count(rail)) refuse("rail " + rail + " is stated in the board power data but no sheet of the board has that net");
    }
    if (policy.inlet) for (const auto& rail : {policy.inlet->rail, policy.inlet->bulk})
        if (!nets.count(rail)) refuse("power.inlet names " + rail + " but no sheet of the board has that net");
    std::map<std::string, PowerRail> known;
    std::set<std::string> stated;
    for (const auto& [rail, entry] : policy.rails) { known[rail] = entry; stated.insert(rail); }
    const auto detected = detect_power_regulators(sheets, policy);
    struct Producer { std::string who, in, out; std::optional<double> fixed; bool passes = false; std::optional<FeedbackDivider> divider; };
    std::vector<Producer> producers;
    for (const auto& reg : detected.regs) {
        const auto sheet = std::find_if(sheets.begin(), sheets.end(), [&](const auto& s) { return s.name == reg.sheet; });
        ModelSheetIndex idx(sheet->circuit);
        const RegulatorFact* fact = part_fact(policy.regulators, catalogue_part_number(*idx.part(reg.ref)));
        Producer producer{reg.sheet + ":" + reg.ref + " (" + reg.value + ")", reg.vin, reg.vout, fact->out_v, false, std::nullopt};
        producer.passes = std::find(pass_through_kinds.begin(), pass_through_kinds.end(), fact->kind) != pass_through_kinds.end();
        if (fact->fb_vref) producer.divider = feedback_divider(sheet->circuit, reg.ref, reg.vout, *fact->fb_vref);
        producers.push_back(producer);
    }
    for (const auto& bridge : detected.bridges) {
        const auto sheet = std::find_if(sheets.begin(), sheets.end(), [&](const auto& s) { return s.name == bridge.sheet; });
        ModelSheetIndex idx(sheet->circuit);
        const auto* part = idx.part(bridge.ref);
        const PartClass klass = symbol_class(facts, part->lib_id, bridge.sheet + ":" + bridge.ref);
        if (std::find(pass_through_classes.begin(), pass_through_classes.end(), klass) == pass_through_classes.end()) continue;
        const std::string who = bridge.sheet + ":" + bridge.ref + " (" + std::string(part_class_name(klass)) + ")";
        producers.push_back({who, bridge.from, bridge.to, std::nullopt, true, std::nullopt});
        producers.push_back({who, bridge.to, bridge.from, std::nullopt, true, std::nullopt});
    }
    std::map<std::string, std::string> driver;
    for (const auto& producer : producers) {
        if (producer.divider) {
            if (!stated.count(producer.out))
                refuse("rail " + producer.out + " is the output of adjustable regulator " + producer.who + " (feedback divider " +
                       producer.divider->top_ref + "/" + producer.divider->bottom_ref + " sets " + volts_text(producer.divider->volts) +
                       " V); state its target voltage in power.rails");
            known[producer.out].basis += "; feedback divider " + producer.divider->top_ref + "/" + producer.divider->bottom_ref +
                                        " of " + producer.who + " sets " + volts_text(producer.divider->volts) + " V";
        }
    }
    bool changed = true;
    while (changed) {
        changed = false;
        for (const auto& producer : producers) {
            if (producer.divider) continue;
            std::optional<double> volts;
            std::string basis;
            if (producer.fixed) { volts = producer.fixed; basis = "fixed output of " + producer.who; }
            else if (producer.passes) {
                const auto in = known.find(producer.in);
                if (in == known.end()) continue;
                volts = in->second.volts;
                basis = "pass-through " + producer.who + " from " + producer.in;
            } else continue;
            const auto out = known.find(producer.out);
            if (out == known.end()) {
                known[producer.out] = PowerRail{volts, basis};
                driver[producer.out] = producer.who;
                changed = true;
                continue;
            }
            if (out->second.volts != volts)
                refuse("rail " + producer.out + " resolves to two voltages: " + (out->second.volts ? volts_text(*out->second.volts) : "null") +
                       " V (" + out->second.basis + ") and " + (volts ? volts_text(*volts) : "null") + " V (" + basis + ")");
            const bool echo = (driver.count(producer.out) && driver.at(producer.out) == producer.who) ||
                              (driver.count(producer.in) && driver.at(producer.in) == producer.who);
            if (!echo && stated.count(producer.out))
                refuse("rail " + producer.out + " has two homes: " + out->second.basis + ", and " + basis);
        }
    }
    std::vector<std::string> missing;
    for (const auto& [name, classes] : nets)
        if (classes.count(power_class) && !known.count(name)) missing.push_back(name);
    if (!missing.empty())
        refuse("power-class net(s) with no source, no producer the tool can compute and no power.rails entry: " + join(missing, ", "));
    policy.rails.clear();
    for (const auto& [name, rail] : known) policy.rails.emplace_back(name, rail);
    return policy;
}

PowerPolicy load_board_power_policy(const ProjectPaths& paths, const std::vector<ProjectCircuit>& sheets, const SheetRoles& roles) {
    const BoardDefinition board = load_board(paths.project_root, paths.module);
    const auto mapping_file = paths.project_root / "som_mapping.json";
    const LinkMapping mapping = link_mapping_from_json(parse_json_file(mapping_file.string()), board.module_definition.do_not_load_straps);
    std::vector<std::string> module_sheets;
    for (const auto& sheet : sheets) if (module_connector_sheet(roles, sheet.name)) module_sheets.push_back(sheet.name);
    return board_power_policy(board.power, board.module_definition, mapping.rebound_som_rails, module_sheets, sheets, default_part_facts());
}

}
