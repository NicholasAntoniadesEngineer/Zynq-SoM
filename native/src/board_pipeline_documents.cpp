#include "board_pipeline_internal.hpp"
#include "schgen/board_files.hpp"
#include "schgen/gallery.hpp"
#include "schgen/i2c_inventory.hpp"
#include "schgen/native_render.hpp"
#include "schgen/model3d.hpp"
#include "schgen/sheet_roles.hpp"

namespace schgen::board_pipeline_detail {
void golden_stage(Context& c){
    c.attempt("golden",[&]{
        if(c.options.no_render){
            const std::string reason="--no-render: no current-run visual comparison; existing images and baseline left unchanged";
            c.report("golden.txt","SKIP: "+reason);
            c.status("golden",BoardGateStatus::skipped,reason);return;
        }
        const auto r=check_board_golden(c.renders,c.options.bless,c.paths.project_root/"renders/golden.json");
        c.report("golden.txt",r.summary());c.gate("golden",r.match,r.summary());
    });
}
void manifest_stage(Context& c){
    c.attempt("manifest",[&]{if(!c.power||!c.testpoints)throw ProjectError("power/coverage facts unavailable");
        check_i2c_address_collisions(c.circuits);
        ManufacturingManifestInput in;in.file_stem=c.paths.file_stem;in.sheets=c.circuits;in.power=*c.power;
        if(!c.controller)throw ProjectError("controller pin map unavailable; the module_pin_map stage did not complete");in.stm32=*c.controller;in.xdc=c.xdc;
        in.coverage={c.testpoints->covered(),c.testpoints->required.size(),c.testpoints->waived.size()};
        if(c.xdc)in.device=c.xdc->device;run_manufacturing_manifest(in,c.out,c.out/"manifest.json",c.require_power_policy());
        c.manifest_input=std::move(in);
        c.gate("manifest",true,"artifacts hashed after SI; final reports rehashed at publication");});
}
void document_stages(Context& c){
    c.attempt("xdc",[&]{if(!c.som)throw ProjectError("module interface unavailable; the link stage did not run");
        const auto refs=som_interface_refs(*c.som);
        const auto live=extract_som_zynq(c.paths.som_schematic,c.paths.module.fpga_ref,refs,c.options.extraction);c.fpga_live=live;
        XdcInput raw;raw.refs=refs;raw.pins_file=board_file_name(c.paths.file_stem,BoardFileKind::PinConstraints);apply_som_to_xdc(raw,live);
        const auto xi=load_project_xdc_input(c.paths.repository_root,c.paths.project_root,c.sheets,raw,c.paths.som_schematic,c.paths.som_interface_file);
        const auto xo=generate_xdc(xi);publish_text(c.out/"fpga"/xi.pins_file,xo.text);c.xdc_pins=xo.entries;
        ManufacturingXdc manifest;manifest.count=xo.entries.size();manifest.device=xi.device;
        std::set<int> banks;for(const auto& pin:xo.entries)banks.insert(std::stoi(pin.bank));manifest.banks.assign(banks.begin(),banks.end());c.xdc=manifest;
        c.gate("xdc",true,join(xo.checks,"\n"));});
    c.attempt("power_sequence",[&]{if(!c.power||!c.link)throw ProjectError("power or link result unavailable");const auto rail=module_supply_rail(c.paths.module.draw,c.link->mapping);publish_text(c.docs/"power_sequence.svg",render_power_sequence_svg(build_power_sequence(c.circuits,*c.power,rail,c.require_power_policy()),load_project_config(c.paths).name,c.power->ok(),c.require_power_policy()));c.gate("power_sequence",true,"power sequence published");});
    c.attempt("floorplan",[&]{if(!c.pcb)throw ProjectError("no solved floorplan available; refusing a second geometry solve");
        write_floorplan_documents(c.pcb->placement.floorplan.documents,c.docs);c.gate("floorplan",true,"existing solved plan documents published; no additional counts");});
    c.attempt("model3d",[&]{const auto r=run_model3d(c.paths.parts_dir,c.paths.project_root,c.reports,c.options.model_directory.empty()?default_model3d_directory():c.options.model_directory);c.gate("model3d",r.ok,r.report());});
    c.attempt("render3d",[&]{if(c.options.no_render){c.status("render3d",BoardGateStatus::skipped,"--no-render");return;}if(!c.pcb_published)throw ProjectError("PCB unavailable");
        Render3dOptions ro;ro.kicad_cli=c.options.extraction.kicad_cli;if(!c.options.model_directory.empty())ro.model_directory=c.options.model_directory;
        ro.source_project_directory=c.paths.project_root;
        const auto r=render_board_3d(c.out/board_file_name(c.paths.file_stem,BoardFileKind::Pcb),c.renders,ro);c.gate("render3d",r.ok(),r.summary());});
    c.attempt("gallery",[&]{auto paths=c.paths;paths.project_root=c.out;if(c.out!=c.paths.project_root){paths.root_readme=false;paths.repository_root=c.out.parent_path();}
        const auto input=load_gallery_input(paths,c.circuits);const auto changed=write_gallery(input);c.gate("gallery",true,gallery_summary(input,changed));});
    c.attempt("si",[&]{if(!c.pcb_published)throw ProjectError("PCB emission must precede SI extension");const auto r=run_si_constraints(c.circuits,c.paths.project_root/"research/si_spec.json",c.manufacturing/board_file_name(c.paths.file_stem,BoardFileKind::DesignRules),c.manufacturing/"SI_CONSTRAINTS.md");c.gate("si",r.verdict.ok,r.verdict.summary());});
    c.attempt("i2c_bus_map",[&]{const PartFacts& facts=default_part_facts();const auto inventory=build_i2c_inventory(c.circuits,facts);
        publish_text(c.reports/"i2c_bus_map.txt",inventory.text());
        auto errors=verify_i2c_inventory(inventory,c.circuits,facts);for(const auto& collision:i2c_address_collisions(inventory))errors.push_back(collision);
        c.gate("i2c_bus_map",errors.empty(),std::to_string(inventory.devices.size())+" devices on "+std::to_string(inventory.buses.size())+" buses; "+std::to_string(inventory.bridges.size())+" bridged lines; "+std::to_string(inventory.pullups.size())+" pull-ups"+(errors.empty()?"":"; "+join(errors,"; ")));});
    c.attempt("module_pin_map",[&]{if(!c.som||!c.link||!c.fpga_live||!c.xdc)throw ProjectError("module interface, link or constraints result unavailable");
        c.controller=stm32_pin_map(extract_som_zynq(c.paths.som_schematic,c.paths.module.controller_ref,som_interface_refs(*c.som),c.options.extraction),*c.som);
        const auto module_sheets=sheet_module_connectors(c.require_roles());
        const ModulePinInputs inputs{*c.som,c.link->mapping,c.sheets,module_sheets,*c.fpga_live,*c.controller};
        const auto map=build_module_pin_map(inputs);publish_text(c.reports/"module_pin_map.txt",map.text());
        const auto errors=verify_module_pin_map(map,inputs,c.xdc_pins);
        const auto open=std::count_if(map.rows.begin(),map.rows.end(),[](const ModulePinRow& row){return row.board_net==module_pin_map_empty_cell;});
        c.gate("module_pin_map",errors.empty(),std::to_string(map.rows.size())+" pins on "+std::to_string(c.som->connectors.size())+" connectors; "+std::to_string(open)+" without a board net"+(errors.empty()?"":"; "+join(errors,"; ")));});
    manifest_stage(c);
    golden_stage(c);
    c.attempt("contract_coverage_lint",[&]{
        if(!c.pcb)throw ProjectError("authored PCB contracts unavailable for coverage lint");
        const auto policy=pcb_placement_gate_policy(c.pcb->inputs);
        const auto lint=check_board_contract_coverage(c.sheets,policy.contracts,policy.ref_maps,
                                                    c.options.enforce_coverage_lint);
        c.report("contract_coverage_lint.txt",lint.report);
        c.gate("contract_coverage_lint",lint.ok(),lint.report);
    });
}
}
