#include "board_pipeline_internal.hpp"
#include "schgen/devicetree.hpp"
#include "schgen/vivado.hpp"
#include "schgen/gallery.hpp"
#include "schgen/native_render.hpp"
#include "schgen/model3d.hpp"

namespace schgen::board_pipeline_detail {
void document_stages(Context& c){
    std::optional<SomZynq> live;std::optional<XdcInput> xi;std::optional<XdcOutput> xo;
    c.attempt("xdc",[&]{live=extract_som_zynq(c.paths.som_schematic,"U2",{"J1","J2","J3"},c.options.extraction);
        XdcInput raw;raw.refs={"J1","J2","J3"};apply_som_to_xdc(raw,*live);
        xi=load_project_xdc_input(c.paths.repository_root,c.paths.project_root,c.sheets,raw,c.paths.som_schematic,c.paths.som_interface_file);
        xo=generate_xdc(*xi);publish_text(c.out/"fpga/Zynq_Carrier_pins.xdc",xo->text);
        ManufacturingXdc manifest;manifest.count=xo->entries.size();manifest.device=xi->device;
        std::set<int> banks;for(const auto& pin:xo->entries)banks.insert(std::stoi(pin.bank));manifest.banks.assign(banks.begin(),banks.end());c.xdc=manifest;
        c.gate("xdc",true,join(xo->checks,"\n"));});
    c.attempt("vivado",[&]{if(!xi||!xo)throw ProjectError("validated live XDC inputs unavailable");
        publish_text(c.out/"fpga/create_project.tcl",render_vivado(*xo,xi->device,xi->zynq_ref,"Zynq_Carrier_pins.xdc",xi->refs));c.gate("vivado",true,"project Tcl published");});
    c.attempt("devicetree",[&]{if(!live)throw ProjectError("live SoM extraction unavailable");const auto r=generate_devicetree(load_devicetree_input(c.paths.repository_root,c.paths.project_root,*live,c.paths.som_interface_file));publish_text(c.out/"firmware/carrier_pl.dtsi",r.text);c.gate("devicetree",true,"device tree published");});
    c.attempt("firmware",[&]{FirmwareDocsInput in;in.sheets=c.circuits;
        in.firmware_sources={c.paths.som_interface_file.string(),c.paths.som_schematic.string()+" (U9 pin map, live kicad-cli extraction)"};
        for(const auto& sc:c.circuits)in.firmware_sources.push_back(sc.path.string());
        in.stm32=stm32_pin_map(extract_som_zynq(c.paths.som_schematic,"U9",{"J1","J2","J3"},c.options.extraction),load_som_interface(c.paths.som_interface_file));
        c.firmware=in;publish_text(c.out/"firmware/zynq_carrier_contract.h",render_firmware_contract(in));c.gate("firmware",true,"contract published; absent optional inputs: "+join(firmware_absent_inputs(in)));});
    FirmwareDocsInput partial;partial.sheets=c.circuits;
    c.attempt("manual",[&]{const auto missing=manual_missing_requirements(partial);if(!missing.empty()){c.status("manual",BoardGateStatus::skipped,"project has no "+join(missing));return;}
        if(!c.firmware)throw ProjectError("firmware facts unavailable");publish_text(c.docs/"BRINGUP.md",render_bringup_manual(*c.firmware));c.gate("manual",true,"bring-up manual published");});
    c.attempt("scfw",[&]{const auto missing=scfw_missing_requirements(partial);if(!missing.empty()){c.status("scfw",BoardGateStatus::skipped,"project has no "+join(missing));return;}
        if(!c.firmware)throw ProjectError("firmware facts unavailable");const auto docs=render_scfw(*c.firmware);for(const auto& d:docs)publish_text(c.out/"firmware/sc"/d.path,d.text);c.gate("scfw",true,std::to_string(docs.size())+" files published");});
    c.attempt("testplan",[&]{if(!c.testpoints||!c.spice)throw ProjectError("coverage/SPICE results unavailable");ProjectStrings probes;for(const auto& [net,locations]:c.testpoints->have)probes.emplace_back(net,join(locations));
        publish_text(c.docs/"TEST_PLAN.md",render_test_plan(c.firmware?*c.firmware:partial,*c.spice,probes));c.gate("testplan",true,"test plan published from current checks");});
    c.attempt("power_sequence",[&]{if(!c.power)throw ProjectError("power result unavailable");publish_text(c.docs/"power_sequence.svg",render_power_sequence_svg(build_power_sequence(c.circuits,*c.power),c.power->ok()));c.gate("power_sequence",true,"power sequence published");});
    c.attempt("floorplan",[&]{if(!c.pcb)throw ProjectError("no solved floorplan available; refusing a second geometry solve");
        write_floorplan_documents(c.pcb->placement.floorplan.documents,c.docs);c.gate("floorplan",true,"existing solved plan documents published; no additional counts");});
    c.attempt("model3d",[&]{const auto r=run_model3d(c.paths.parts_dir,c.paths.project_root,c.reports,c.options.model_directory.empty()?default_model3d_directory():c.options.model_directory);c.gate("model3d",r.ok,r.report());});
    c.attempt("render3d",[&]{if(c.options.no_render){c.status("render3d",BoardGateStatus::skipped,"--no-render");return;}if(!c.pcb_published)throw ProjectError("PCB unavailable");
        Render3dOptions ro;ro.kicad_cli=c.options.extraction.kicad_cli;if(!c.options.model_directory.empty())ro.model_directory=c.options.model_directory;
        ro.source_project_directory=c.paths.project_root;
        const auto r=render_board_3d(c.out/"Zynq_Carrier.kicad_pcb",c.renders,ro);c.gate("render3d",r.ok(),r.summary());});
    c.attempt("gallery",[&]{auto paths=c.paths;paths.project_root=c.out;if(c.out!=c.paths.project_root){paths.is_default_project=false;paths.repository_root=c.out.parent_path();}
        const auto input=load_gallery_input(paths,c.circuits);const auto changed=write_gallery(input);c.gate("gallery",true,gallery_summary(input,changed));});
    c.attempt("si",[&]{if(!c.pcb_published)throw ProjectError("PCB emission must precede SI extension");const auto r=run_si_constraints(c.circuits,c.paths.project_root/"research/si_spec.json",c.manufacturing/"Zynq_Carrier_pcb.kicad_dru",c.manufacturing/"SI_CONSTRAINTS.md");c.gate("si",r.verdict.ok,r.verdict.summary());});
    c.attempt("manifest",[&]{if(!c.power||!c.testpoints||!c.firmware)throw ProjectError("power/coverage/live STM32 facts unavailable");
        ManufacturingManifestInput in;in.sheets=c.circuits;in.power=*c.power;in.stm32=c.firmware->stm32;in.xdc=c.xdc;
        in.coverage={c.testpoints->covered(),c.testpoints->required.size(),c.testpoints->waived.size()};
        if(c.xdc)in.device=c.xdc->device;run_manufacturing_manifest(in,c.out,c.out/"manifest.json");c.gate("manifest",true,"current artifacts hashed after SI publication");});
    c.attempt("golden",[&]{const auto r=check_board_golden(c.renders,c.options.bless,c.paths.project_root/"renders/golden.json");c.report("golden.txt",r.summary());c.gate("golden",r.match,r.summary());});
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
