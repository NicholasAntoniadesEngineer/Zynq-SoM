#include "schgen/pcb_owned_groups.hpp"
#include "schgen/placement_requirements.hpp"
#include "schgen/board_pcb.hpp"
#include "schgen/board_schematic.hpp"
#include <iostream>
#include <limits>

int main(int argc,char** argv) {
    using namespace schgen;
    try {
        if(argc!=3||!open_part_catalog(argv[2]))throw std::runtime_error("usage: owned-live REPOSITORY CATALOG");
        const auto paths=resolve_project_paths(argv[1],"carrier");
        const auto stage=prepare_board_pcb(paths);
        const PcbCheckInput all(stage.placement.model);
        const auto index=load_sheet_index(paths);
        std::map<std::string,int> bands(index.begin(),index.end());
        std::map<std::pair<std::string,std::string>,std::string> extracted;
        for(const auto& [net,pins]:stage.inputs.netlist)for(const auto& p:pins)
            if(!extracted.emplace(std::make_pair(p.ref,p.pin),net).second)throw std::runtime_error("duplicate extracted pin");
        std::size_t covered=0;
        for(const auto* sheet:{"board_aux","bringup_rails"}) {
            auto req=parse_placement_requirements(parse_json_file((paths.subsystems_dir/sheet/"placement_requirements.json").string()));
            const auto expected=carrier_surface_requirement_declaration(sheet);
            const CircuitSheetIr* circuit=nullptr;
            for(const auto& source:stage.circuits)if(source.name==sheet)circuit=&source.circuit;
            if(!circuit)throw std::runtime_error("missing live circuit");
            std::map<std::string,std::string> refs,nets;
            for(const auto& p:circuit->parts)refs[p.ref]=board_renamed_ref(p.ref,bands.at(sheet),sheet);
            for(const auto& n:circuit->nets)for(const auto& p:n.pins) {
                const auto& mapped=extracted.at({refs.at(p.ref),p.pin});
                auto [it,inserted]=nets.emplace(n.name,mapped);
                if(!inserted&&it->second!=mapped)throw std::runtime_error("split extracted net");
            }
            std::map<std::string,CatalogPart> catalog;
            for(const auto& [ref,mpn]:expected.owner_mpn){(void)ref;catalog.emplace(mpn,lookup_part_catalog(mpn));}
            PcbCheckModel zone;zone.net_numbers=stage.placement.model.net_numbers;
            Box4 b{std::numeric_limits<double>::infinity(),std::numeric_limits<double>::infinity(),-std::numeric_limits<double>::infinity(),-std::numeric_limits<double>::infinity()};
            for(std::size_t i=0;i<stage.placement.model.insts.size();++i)if(stage.placement.model.insts[i].sheet==sheet) {
                zone.insts.push_back(stage.placement.model.insts[i]);const auto box=all.courtyard_at(i);
                b.x0=std::min(b.x0,box.x0);b.x1=std::max(b.x1,box.x1);b.y0=std::min(b.y0,box.y0);b.y1=std::max(b.y1,box.y1);
            }
            zone.origin_x=b.x0;zone.origin_y=b.y0;zone.board_w=b.x1-b.x0;zone.board_h=b.y1-b.y0;
            const auto before=check_placement_requirements(req,expected,*circuit,catalog,PcbCheckInput(zone),refs,nets);
            if(!before.hard_requirements_met())throw std::runtime_error(before.summary());
            std::vector<OwnedCapPlacement> rows;OwnedGroupOptions options;options.compact=true;options.clearance=stage.inputs.floorplan.place_clear;
            for(const auto& r:req.ownership) {
                const auto role=r.role=="shared_output_bulk"?OwnedCapRole::OutputBulk:OwnedCapRole::Bypass;
                rows.push_back({refs.at(r.owner),r.pin,refs.at(r.cap),r.cap_pin,r.return_pin,nets.at(r.rail),nets.at(r.return_net),role});
                if(role==OwnedCapRole::Bypass)options.movable_caps.insert(refs.at(r.cap));
            }
            for(const auto& r:req.top_switches){options.fixed_refs.insert(refs.at(r));options.top_refs.insert(refs.at(r));}
            auto result=construct_owned_group_candidates(zone,rows,options);covered+=rows.size();
            std::cout<<sheet<<": "<<result.alternatives.size()<<" bounded alternatives, "<<rows.size()<<" declared owners\n";
            for(const auto& d:result.diagnostics)std::cout<<d<<'\n';
            if(result.alternatives.empty())throw std::runtime_error("no real-footprint owned alternative");
            for(const auto& candidate:result.alternatives) {
                const auto report=check_placement_requirements(req,expected,*circuit,catalog,PcbCheckInput(candidate.model),refs,nets);
                if(!report.hard_requirements_met())throw std::runtime_error(report.summary());
                std::cout<<candidate.tag<<" local extent "<<zone.board_w<<'x'<<zone.board_h<<" -> "<<candidate.model.board_w<<'x'<<candidate.model.board_h<<'\n';
                for(const auto& m:report.measurements)std::cout<<candidate.tag<<' '<<m.owner<<'.'<<m.owner_pin<<" -> "<<m.member<<'.'<<m.member_pin<<" gap="<<m.planar_pad_box_gap_mm<<" sides="<<m.owner_side<<'/'<<m.member_side<<" UNVERIFIED\n";
                for(std::size_t i=0;i<zone.insts.size();++i)if(zone.insts[i].pad_nets!=candidate.model.insts[i].pad_nets)throw std::runtime_error("pin net changed");
                // Read-only downstream screening in original whole-board
                // context. These two gates do not replace the full pipeline.
                auto whole=stage.placement.model;
                for(auto& inst:whole.insts)for(const auto& moved:candidate.model.insts)if(inst.ref==moved.ref){inst.x=moved.x;inst.y=moved.y;}
                const auto mech=check_placement_mech(PcbCheckInput(whole));
                const auto old_fanout=check_fanout(all,std::nullopt);
                const auto fanout=check_fanout(PcbCheckInput(whole),old_fanout.n_starved);
                std::cout<<candidate.tag<<" whole-context mechanical="<<(mech.ok?"PASS":"FAIL")
                    <<" fanout-nonregression="<<(fanout.ok?"PASS":"FAIL")<<" (relative to prepared incumbent; configured ratchet/full candidate gates pending)\n";
                if(!mech.ok)throw std::runtime_error(mech.summary());
                if(!fanout.ok)throw std::runtime_error(fanout.summary());
            }
        }
        close_part_catalog();if(covered!=6)throw std::runtime_error("six explicit owners not covered");
        std::cout<<"PASS six live declarations, runtime identity gate; local candidates only, NOT whole-board acceptance\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
