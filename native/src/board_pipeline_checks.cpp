#include "board_pipeline_internal.hpp"
#include "schgen/bom.hpp"
#include "schgen/part_checks.hpp"
#include "schgen/bom_values.hpp"
#include "schgen/pin_completeness.hpp"
#include "schgen/footprint_pads.hpp"

namespace schgen::board_pipeline_detail {
void electrical_stages(Context& c){
    c.attempt("bom_footprints",[&]{const auto r=generate_bom(c.sheets,true);publish_text(c.manufacturing/"bom_jlc.csv",r.csv);
        c.gate("bom_footprints",r.missing_footprints.empty(),std::to_string(r.rows.size())+" line items; missing footprints: "+join(r.missing_footprints)+"; missing LCSC (advisory): "+join(r.missing_lcsc));});
    c.attempt("power_tree",[&]{c.power=run_power_checks(c.circuits,c.reports,c.docs);c.gate("power_tree",c.power->ok(),power_report(*c.power));});
    c.attempt("rail_ampacity",[&]{if(!c.som||!c.link)throw ProjectError("SoM/link inputs unavailable");
        const auto r=analyze_rail_ampacity(c.circuits,*c.som,c.link->mapping);c.report("rail_ampacity.txt",r.report());c.gate("rail_ampacity",r.ok(),r.report());});
    c.attempt("testpoints",[&]{c.testpoints=check_testpoint_coverage(c.sheets);c.report("testpoints.txt",c.testpoints->report());c.gate("testpoints",c.testpoints->ok(),c.testpoints->report());});
    c.attempt("design_rules",[&]{const auto r=check_design_rules(c.sheets,[&](const std::string& id)->const SymbolDef&{return c.library.get(id);});c.report("design_rules.txt",r.report());c.gate("design_rules",r.ok(),r.report());});
    c.attempt("part_rules",[&]{if(!c.power)throw ProjectError("power result unavailable");const auto r=run_part_checks(c.circuits,c.reports,&*c.power);c.gate("part_rules",r.ok(),part_rules_report(r));});
    c.attempt("bom_values",[&]{const auto r=run_bom_values(c.circuits,load_bom_value_catalog(c.paths.repository_root/"schgen/verify/data/lcsc_values.json"),c.reports);c.gate("bom_values",r.ok,r.report());});
    c.attempt("footprint_pads",[&]{auto o=c.options.pcb.footprints;if(o.parts_dir.empty())o.parts_dir=c.paths.parts_dir;
        if(o.library_tables.empty())o.library_tables.push_back(c.paths.repository_root/"som/fp-lib-table");
        if(o.kicad_footprint_root.empty())for(const auto* root:{"/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints","/usr/share/kicad/footprints","/usr/local/share/kicad/footprints"})if(fs::is_directory(root)){o.kicad_footprint_root=root;break;}
        o.aliases.emplace("Capacitor_SMD:C_1206_3225Metric","Capacitor_SMD:C_1206_3216Metric");
        const auto r=run_footprint_pads(c.circuits,c.library,o,c.reports);c.gate("footprint_pads",r.ok,r.report());});
    c.attempt("pin_completeness",[&]{const auto r=run_pin_completeness(c.circuits,c.library,load_nc_allowlist(c.paths.repository_root/"schgen/verify/data/nc_allowlist.json"),c.reports);c.gate("pin_completeness",r.ok,r.report());});
    c.attempt("spice",[&]{c.spice=run_spice_checks(c.circuits,c.reports,c.options.spice);c.gate("spice",c.spice->ok(),spice_report(*c.spice,ngspice_available().has_value()));});
}
}
