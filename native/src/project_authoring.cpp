#include "schgen/project_authoring.hpp"
#include "authoring_values.hpp"
#include "schgen/subsystem_data.hpp"
#include <algorithm>

namespace schgen {
std::vector<ProjectSubsystemDefinition> project_subsystem_definitions(const std::filesystem::path& project_root) {
    if(project_root.empty())throw CircuitAuthoringError("project authoring needs the board folder");
    return project_subsystem_definitions(load_board(project_root));
}
std::vector<ProjectSubsystemDefinition> project_subsystem_definitions(const BoardDefinition& board) {
    std::vector<ProjectSubsystemDefinition> out;
    for(const BoardSheet& sheet:board.sheets)
        out.push_back({board.name,sheet.name,!sheet.from_module(),sheet.settings,sheet.module_connector,sheet.title,sheet.additions});
    return out;
}
std::vector<std::filesystem::path> board_folders(const std::filesystem::path& repository) {
    std::vector<std::filesystem::path> folders;
    for(const auto& entry:std::filesystem::directory_iterator(repository))
        if(entry.is_directory()&&std::filesystem::is_regular_file(entry.path()/board_file))folders.push_back(entry.path());
    std::sort(folders.begin(),folders.end());
    return folders;
}
ConnectorAuthoringPolicy connector_policy_of(const BoardDefinition& board) {
    ConnectorAuthoringPolicy p;const ModuleDefinition& module=board.module_definition;
    p.part=module.connector_part;
    p.module_draw_connector=module.draw.connector;p.module_draw_rail=module.draw.rail;
    p.module_draw_note=module.draw.note;p.module_draw_a=module.draw.amps;
    p.sdio_level_v=module.sdio_level_v;p.sd_bus=module.sd_bus;
    for(const auto* pairs:{&module.pairs,&board.module.pairs})for(const BoardPair& pair:*pairs)
        p.pairs.push_back({pair.positive,pair.negative,pair.kind,pair.impedance?std::optional<int32_t>(*pair.impedance):std::nullopt});
    for(const BoardLoad& load:board.module.loads)p.loads.push_back({load.connector,load.rail,load.amps,load.note});
    return p;
}
ConnectorAuthoringPolicy project_connector_policy(const std::filesystem::path& project_root) {
    return connector_policy_of(load_board(project_root));
}
namespace {
ProjectSubsystemDefinition definition(const std::string& project,const std::string& name,const ProjectAuthoringInput& input) {
    for(auto& d:input.board?project_subsystem_definitions(*input.board):project_subsystem_definitions(input.project_root)) {
        if(d.project!=project)throw CircuitAuthoringError("the board definition describes "+d.project+", not "+project);
        if(d.name==name)return d;
    }
    throw CircuitAuthoringError("unknown project subsystem "+project+":"+name);
}
JsonNode metadata(const ProjectSubsystemDefinition& d,const ProjectAuthoringInput& input) {
    const auto i=input.metadata.find(d.name);return i==input.metadata.end()?d.meta:i->second;
}
}
CircuitSheetIr author_som_connector(const std::string& ref,const std::string& name,const std::string& title,
    const SomInterface& som,const LinkMapping& mapping,const ConnectorAuthoringPolicy& policy,const AuthoringContext& context) {
    using authoring_values::repr;
    const auto conn=std::find_if(som.connectors.begin(),som.connectors.end(),[&](const std::pair<std::string,SomConnector>& c){return c.first==ref;});
    if(conn==som.connectors.end())throw CircuitAuthoringError("missing SoM connector "+ref);
    for(const auto& strap:mapping.do_not_load_straps)
        if(mapping.function_map.count(strap)||mapping.pudc_straps.count(strap)||mapping.vcco_rail_map.count(strap)||mapping.rebound_som_rails.count(strap))
            throw CircuitAuthoringError("som_conn_gen: MIO voltage-mode straps must stay unmapped — "+repr(strap));
    auto pins=conn->second.pins;
    auto numeric=[](const std::string& pin){std::size_t used=0;auto n=std::stoll(pin,&used);if(used!=pin.size())throw CircuitAuthoringError("noninteger connector pin "+pin);return n;};
    for(const auto& p:pins)(void)numeric(p.first);
    std::stable_sort(pins.begin(),pins.end(),[&](const std::pair<std::string,std::string>& a,const std::pair<std::string,std::string>& b){return numeric(a.first)<numeric(b.first);});
    CircuitAuthor c(name,title,context);AuthoringPartSelection selection;selection.ref=ref;c.use_part(policy.part,selection);
    for(const auto* pin:{"101","102","103","104"})c.nc({ref+"."+pin});
    std::set<std::string> seen;
    const auto bound=[&](const std::string& som_net){
        for(const auto* map:{&mapping.rebound_som_rails,&mapping.vcco_rail_map,&mapping.function_map,&mapping.pudc_straps}) {
            auto i=map->find(som_net);if(i!=map->end())return i->second;
        }
        return som_net;
    };
    for(const auto& [pin,som_net]:pins) {
        if(mapping.isolated_som_rails.count(som_net)){c.nc({ref+"."+pin});continue;}
        const auto net=bound(som_net);
        const auto cls=CircuitAuthor::classify(net);
        if(cls=="power"||cls=="ground")c.net(net,{ref+"."+pin});
        else {
            if(!seen.insert(net).second)throw CircuitAuthoringError(ref+": contract net "+repr(net)+" repeats on this connector — the engine's connector fan assumes one row per signal; extend it");
            c.port(net,{ref+"."+pin});
        }
    }
    const auto has=[&](const std::string& net){return std::any_of(c.view().nets.begin(),c.view().nets.end(),[&](const CircuitNetIr& n){return n.name==net;});};
    for(const auto& p:policy.pairs)if(has(p.positive)&&has(p.negative)) {
        AuthoringPort t;t.kind=p.kind;t.pair_with=p.negative;t.impedance=p.impedance;c.port_type(p.positive,t);
    }
    if(std::all_of(policy.sd_bus.begin(),policy.sd_bus.end(),has))for(const auto& s:policy.sd_bus) {
        AuthoringPort t;t.kind="sd_bus";t.bus="SDIO";t.level_v=policy.sdio_level_v;c.port_type(s,t);
    }
    if(ref==policy.module_draw_connector)c.draws(bound(policy.module_draw_rail),policy.module_draw_a,policy.module_draw_note);
    auto loads=policy.loads;
    std::stable_sort(loads.begin(),loads.end(),[](const ConnectorAuthoringLoad& a,const ConnectorAuthoringLoad& b){return a.rail<b.rail;});
    for(const auto& l:loads)if(l.connector==ref&&has(l.rail))c.draws(l.rail,l.amps,l.note);
    return c.finish();
}
CircuitSheetIr author_project_subsystem(const std::string& project,const std::string& name,const ProjectAuthoringInput& input) {
    const auto d=definition(project,name,input);
    const SubsystemMeta meta(metadata(d,input));
    if(!d.connector_ref.empty()) {
        if(input.project_root.empty()&&(!input.som||!input.mapping))throw CircuitAuthoringError("SoM authoring needs project_root or explicit som and mapping");
        const auto som=input.som?*input.som:load_som_interface(module_root_of(input.project_root)/module_interface_file);
        const auto map=input.mapping?*input.mapping:link_mapping_from_json(parse_json_file((input.project_root/"som_mapping.json").string()),input.board?input.board->module_definition.do_not_load_straps:load_board_module(input.project_root).do_not_load_straps);
        const auto policy=input.connector_policy?*input.connector_policy:input.board?connector_policy_of(*input.board):project_connector_policy(input.project_root);
        CircuitAuthor c(author_som_connector(d.connector_ref,d.name,d.connector_title,som,map,policy,input.context),input.context);
        return meta.finish(c);
    }
    auto c=author_subsystem(name,meta,input.context);
    if(d.additions)c=extend_subsystem_data(std::move(c),*d.additions,input.context);
    return c;
}
std::vector<CarrierPackageFactory> native_project_factories(const std::string& project,const ProjectAuthoringInput& input) {
    std::vector<CarrierPackageFactory> out;
    for(const auto& d:input.board?project_subsystem_definitions(*input.board):project_subsystem_definitions(input.project_root))if(d.project==project)
        out.push_back({d.name,[project,name=d.name,input]{return author_project_subsystem(project,name,input);},d.adapter?std::optional<JsonNode>(metadata(d,input)):std::nullopt});
    if(out.empty())throw CircuitAuthoringError("unknown authoring project "+project);
    return out;
}
} // namespace schgen
