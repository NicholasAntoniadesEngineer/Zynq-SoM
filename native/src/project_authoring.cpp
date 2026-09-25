#include "schgen/project_authoring.hpp"
#include "model_checks_internal.hpp"

namespace schgen {
namespace {
const ProjectSubsystemDefinition& definition(const std::string& project,const std::string& name) {
    for(const auto& d:project_subsystem_definitions())if(d.project==project&&d.name==name)return d;
    throw CircuitAuthoringError("unknown project subsystem "+project+":"+name);
}
JsonNode metadata(const ProjectSubsystemDefinition& d,const ProjectAuthoringInput& input) {
    const auto i=input.metadata.find(d.name);return i==input.metadata.end()?d.meta:i->second;
}
}
CircuitSheetIr author_som_connector(const std::string& ref,const std::string& name,const std::string& title,
    const SomInterface& som,const LinkMapping& mapping,const ConnectorAuthoringPolicy& policy,const AuthoringContext& context) {
    using model_checks::repr;
    const auto conn=std::find_if(som.connectors.begin(),som.connectors.end(),[&](const auto& c){return c.first==ref;});
    if(conn==som.connectors.end())throw CircuitAuthoringError("missing SoM connector "+ref);
    for(const auto& strap:mapping.do_not_load_straps)
        if(mapping.function_map.count(strap)||mapping.pudc_straps.count(strap)||mapping.vcco_rail_map.count(strap)||mapping.rebound_som_rails.count(strap))
            throw CircuitAuthoringError("som_conn_gen: MIO voltage-mode straps must stay unmapped — "+repr(strap));
    auto pins=conn->second.pins;
    auto numeric=[](const std::string& pin){std::size_t used=0;auto n=std::stoll(pin,&used);if(used!=pin.size())throw CircuitAuthoringError("noninteger connector pin "+pin);return n;};
    for(const auto& p:pins)(void)numeric(p.first);
    std::stable_sort(pins.begin(),pins.end(),[&](const auto& a,const auto& b){return numeric(a.first)<numeric(b.first);});
    CircuitAuthor c(name,title,context);AuthoringPartSelection selection;selection.ref=ref;c.use_part(policy.part,selection);
    for(const auto* pin:{"101","102","103","104"})c.nc({ref+"."+pin});
    std::set<std::string> seen;
    for(const auto& [pin,som_net]:pins) {
        if(mapping.isolated_som_rails.count(som_net)){c.nc({ref+"."+pin});continue;}
        auto net=som_net;
        for(const auto* map:{&mapping.rebound_som_rails,&mapping.vcco_rail_map,&mapping.function_map,&mapping.pudc_straps}) {
            auto i=map->find(som_net);if(i!=map->end()){net=i->second;break;}
        }
        const auto cls=CircuitAuthor::classify(net);
        if(cls=="power"||cls=="ground")c.net(net,{ref+"."+pin});
        else {
            if(!seen.insert(net).second)throw CircuitAuthoringError(ref+": contract net "+repr(net)+" repeats on this connector — the engine's connector fan assumes one row per signal; extend it");
            c.port(net,{ref+"."+pin});
        }
    }
    const auto has=[&](const std::string& net){return std::any_of(c.view().nets.begin(),c.view().nets.end(),[&](const auto& n){return n.name==net;});};
    for(const auto& p:policy.pairs)if(has(p.positive)&&has(p.negative)) {
        AuthoringPort t;t.kind=p.kind;t.pair_with=p.negative;t.impedance=p.impedance;c.port_type(p.positive,t);
    }
    if(std::all_of(policy.sd_bus.begin(),policy.sd_bus.end(),has))for(const auto& s:policy.sd_bus) {
        AuthoringPort t;t.kind="sd_bus";t.bus="SDIO";t.level_v=policy.sdio_level_v;c.port_type(s,t);
    }
    if(ref=="J1")c.draws("+5V_SOM",policy.module_draw_a,"SoM module (Zynq+DDR3L+PHYs) ~10 W class at the regulated 4.65 V (P0 rebind) — estimate, refine at bring-up");
    auto loads=policy.loads;
    std::stable_sort(loads.begin(),loads.end(),[](const auto& a,const auto& b){return a.rail<b.rail;});
    for(const auto& l:loads)if(l.connector==ref&&has(l.rail))c.draws(l.rail,l.amps,l.note);
    return c.finish();
}
CircuitSheetIr author_project_subsystem(const std::string& project,const std::string& name,const ProjectAuthoringInput& input) {
    const auto& d=definition(project,name);
    const SubsystemMeta meta(metadata(d,input));
    if(!d.connector_ref.empty()) {
        if(input.project_root.empty()&&(!input.som||!input.mapping))throw CircuitAuthoringError("SoM authoring needs project_root or explicit som and mapping");
        const auto som=input.som?*input.som:load_som_interface(input.project_root/"som_interface.json");
        const auto map=input.mapping?*input.mapping:link_mapping_from_json(parse_json_file((input.project_root/"som_mapping.json").string()));
        const auto policy=input.connector_policy?*input.connector_policy:project_connector_policy(project);
        CircuitAuthor c(author_som_connector(d.connector_ref,d.name,d.connector_title,som,map,policy,input.context),input.context);
        return meta.finish(c);
    }
    auto c=d.adapter?author_subsystem(name,meta,input.context):d.circuit(meta,input.context);
    if(project=="devkit_mini"&&name=="power") {
        CircuitAuthor add(std::move(c),input.context);
        for(const auto* net:{"EN_5V0","EN_3V3","EN_1V8"})add.testpoint(net);
        c=add.finish();
    }
    return c;
}
std::vector<CarrierPackageFactory> native_project_factories(const std::string& project,const ProjectAuthoringInput& input) {
    std::vector<CarrierPackageFactory> out;
    for(const auto& d:project_subsystem_definitions())if(d.project==project)
        out.push_back({d.name,[project,name=d.name,input]{return author_project_subsystem(project,name,input);},d.adapter?std::optional<JsonNode>(metadata(d,input)):std::nullopt});
    if(out.empty())throw CircuitAuthoringError("unknown authoring project "+project);
    return out;
}
} // namespace schgen
