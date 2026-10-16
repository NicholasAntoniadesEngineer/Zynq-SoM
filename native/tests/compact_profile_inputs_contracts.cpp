// Exercise the diagnostic's actual loader, not a second copy of its logic.
#define main compact_stage_profile_entry
#include "compact_stage_profile.cpp"
#undef main
#include "historical_input_contracts.hpp"
#include "pcb_placement_requirements.hpp"
#include "schgen/board_schematic.hpp"
#include <cstdlib>
#include <sstream>
#include <unistd.h>

namespace {
void profile_option_contracts() {
    if(nonsearch_events({})!=0 ||
       nonsearch_events({"legalize_joint_retry","legalize_joint_budget"})!=0 ||
       nonsearch_events({"thermal_via_lattice","legalize_joint_retry","thermal_via_lattice"})!=2 ||
       nonsearch_events({"legalize_unreviewed_path"})!=1)
        throw std::runtime_error("profile must expose every non-search event without deduplication or prefix exemptions");
    const auto options = [](std::vector<std::string> args) {
        std::vector<char*> raw;
        for (auto& arg : args) raw.push_back(arg.data());
        return parse(static_cast<int>(raw.size()), raw.data());
    };
    if(options({"profile","--repo",".","--compact-search","on","--floorplan-spec","candidate.json"}).floorplan_spec!=std::filesystem::path("candidate.json"))
        throw std::runtime_error("explicit floorplan path lost");
    bool empty_spec=false;
    try{(void)options({"profile","--repo",".","--compact-search","on","--floorplan-spec",""});}catch(const std::invalid_argument&){empty_spec=true;}
    if(!empty_spec)throw std::runtime_error("empty explicit spec path accepted");
    if(options({"profile","--repo",".","--compact-search","on","--owned-shape","board_aux=tag"}).owned_shapes.at("board_aux")!="tag")
        throw std::runtime_error("owned shape restriction lost tag");
    const auto multiple=options({"profile","--repo",".","--compact-search","on","--owned-shape","board_aux=tag","--owned-shape","bringup_rails=tag2"});
    const auto bottom=options({"profile","--repo",".","--compact-search","on",
        "--require-bottom-sheet","power_mon","--require-bottom-sheet","bringup_modules"});
    if(bottom.require_bottom_sheets!=std::set<std::string>{"power_mon","bringup_modules"})
        throw std::runtime_error("distinct bottom requirements must coexist");
    for(const auto& args:std::vector<std::vector<std::string>>{
        {"profile","--repo",".","--compact-search","on","--require-bottom-sheet","power_mon","--require-bottom-sheet","power_mon"},
        {"profile","--repo",".","--compact-search","on","--require-bottom-sheet",""},
        {"profile","--repo",".","--compact-search","on","--thermal-trace","on","--observers","off"}}) {
        bool rejected=false;try{(void)options(args);}catch(const std::invalid_argument&){rejected=true;}
        if(!rejected)throw std::runtime_error("invalid bottom requirement or thermal trace accepted");
    }
    if(multiple.owned_shapes!=std::map<std::string,std::string>{{"board_aux","tag"},{"bringup_rails","tag2"}})
        throw std::runtime_error("distinct subsystem shape restrictions must coexist");
    if(!options({"profile","--repo",".","--compact-search","off"}).observers||
       options({"profile","--repo",".","--compact-search","off","--observers","off"}).observers)
        throw std::runtime_error("observer mode default/selection mismatch");
    for(const auto& args:std::vector<std::vector<std::string>>{
        {"profile","--repo",".","--compact-search","off","--observers","typo"},
        {"profile","--repo",".","--compact-search","off","--observers","off","--observers","on"},
        {"profile","--repo",".","--compact-search","off","--observers","off","--owned-selection-trace","on"}}){
        bool rejected=false;try{(void)options(args);}catch(const std::invalid_argument&){rejected=true;}
        if(!rejected)throw std::runtime_error("invalid observer options accepted");
    }
    for(const auto& args:std::vector<std::vector<std::string>>{
        {"profile","--repo",".","--compact-search","off","--owned-shape","board_aux=tag"},
        {"profile","--repo",".","--compact-search","on","--owned-shape","=tag"},
        {"profile","--repo",".","--compact-search","on","--owned-shape","board_aux="},
        {"profile","--repo",".","--compact-search","on","--owned-shape","board_aux=a=b"},
        {"profile","--repo",".","--compact-search","on","--owned-shape","board_aux=a","--owned-shape","board_aux=b"}}){
        bool rejected=false;try{(void)options(args);}catch(const std::invalid_argument&){rejected=true;}
        if(!rejected)throw std::runtime_error("invalid owned shape restriction accepted");
    }
    if(options({"profile","--repo",".","--compact-search","on"}).owned_face_cohesion||
       !options({"profile","--repo",".","--compact-search","on","--owned-face-cohesion","on"}).owned_face_cohesion)
        throw std::runtime_error("owned face cohesion default/selection mismatch");
    for(const auto& [mode,value]:std::vector<std::pair<std::string,std::string>>{{"off","on"},{"both","on"},{"on","typo"}}){
        bool rejected=false;
        try{(void)options({"profile","--repo",".","--compact-search",mode,"--owned-face-cohesion",value});}
        catch(const std::invalid_argument&){rejected=true;}
        if(!rejected)throw std::runtime_error("invalid face cohesion option accepted");
    }
    if(options({"profile","--repo",".","--compact-search","on"}).owned_quality_first||
       !options({"profile","--repo",".","--compact-search","on","--owned-quality-first","on"}).owned_quality_first)
        throw std::runtime_error("quality-first default/selection mismatch");
    for(const auto& [mode,value]:std::vector<std::pair<std::string,std::string>>{{"off","on"},{"both","on"},{"on","typo"}}){
        bool rejected=false;
        try{(void)options({"profile","--repo",".","--compact-search",mode,"--owned-quality-first",value});}
        catch(const std::invalid_argument&){rejected=true;}
        if(!rejected)throw std::runtime_error("invalid quality-first option accepted");
    }
    if(options({"profile","--repo",".","--compact-search","on"}).owned_selection_trace||
       !options({"profile","--repo",".","--compact-search","on","--owned-selection-trace","on"}).owned_selection_trace)
        throw std::runtime_error("owned selection trace default/selection mismatch");
    if(options({"profile","--repo",".","--compact-search","on"}).failed_first_retry||
       !options({"profile","--repo",".","--compact-search","on","--interior-order","3","--failed-first-retry","on"}).failed_first_retry)
        throw std::runtime_error("failed-first retry default/selection mismatch");
    const auto combined=options({"profile","--repo",".","--compact-search","on","--interior-order","3",
        "--failed-first-retry","on","--reseat-poses","8","--reseat-frontier","4096",
        "--reseat-continuations","2","--reseat-victim-shapes","on"});
    if(!combined.failed_first_retry||!combined.reseat_pose_limits->victim_shapes||combined.reseat_pose_limits->continuations!=2)
        throw std::runtime_error("combined recovery options lost a requested strategy");
    for(const auto& args:std::vector<std::vector<std::string>>{
        {"profile","--repo",".","--compact-search","on","--failed-first-retry","on"},
        {"profile","--repo",".","--compact-search","off","--interior-order","3","--failed-first-retry","on"},
        {"profile","--repo",".","--compact-search","on","--interior-order","3","--failed-first-retry","typo"}}){
        bool rejected=false;try{(void)options(args);}catch(const std::invalid_argument&){rejected=true;}
        if(!rejected)throw std::runtime_error("invalid failed-first retry option accepted");
    }
    bool invalid_trace=false;
    const auto portfolio=options({"profile","--repo",".","--compact-search","on",
        "--search-strategy","extent","--search-strategy","estimator-first"});
    if(portfolio.search_strategies!=std::vector<std::string>{"extent","estimator-first"})
        throw std::runtime_error("explicit portfolio strategy order lost");
    const auto combination=search_strategy("extent+estimator-first");
    if(!combination.owned_extent_alternatives.value_or(false)||combination.shape_area_first!=false)
        throw std::runtime_error("combined model-search strategy lost an override");
    if(!search_strategy("vertical+extent").vertical_compaction)
        throw std::runtime_error("vertical search-strategy override lost");
    if(!search_strategy("granular-minor+vertical").granular_minor_occupancy)
        throw std::runtime_error("granular minority occupancy strategy lost");
    (void)options({"profile","--repo",".","--compact-search","on","--search-strategy","granular-minor"});
    if(!search_strategy("granular-minor+dual-primary").dual_primary_reservations)
        throw std::runtime_error("dual primary reservation strategy override lost");
    if(!search_strategy("component-primary").component_primary_reservations)
        throw std::runtime_error("component primary reservation strategy override lost");
    (void)options({"profile","--repo",".","--compact-search","on","--search-strategy","granular-minor","--search-strategy","granular-minor+dual-primary"});
    for(const auto& args:std::vector<std::vector<std::string>>{
        {"profile","--repo",".","--compact-search","on","--search-strategy","unknown"},
        {"profile","--repo",".","--compact-search","on","--search-strategy","dual-primary"},
        {"profile","--repo",".","--compact-search","on","--search-strategy","dual-primary+granular-minor","--search-strategy","granular-minor+dual-primary"},
        {"profile","--repo",".","--compact-search","on","--search-strategy","extent+"},
        {"profile","--repo",".","--compact-search","on","--search-strategy","extent+extent"},
        {"profile","--repo",".","--compact-search","on","--search-strategy","area-first+estimator-first"},
        {"profile","--repo",".","--compact-search","on","--search-strategy","extent+rotations"},
        {"profile","--repo",".","--compact-search","on","--search-strategy","vertical"},
        {"profile","--repo",".","--compact-search","on","--search-strategy","extent+area-first","--search-strategy","area-first+extent"},
        {"profile","--repo",".","--compact-search","on","--search-strategy","granular-minor+extent","--search-strategy","extent+granular-minor"},
        {"profile","--repo",".","--compact-search","off","--search-strategy","extent"},
        {"profile","--repo",".","--compact-search","on","--search-strategy","rotations"},
        {"profile","--repo",".","--compact-search","on","--search-strategy","extent","--search-strategy","extent"},
        {"profile","--repo",".","--compact-search","on","--search-strategy","extent","--thermal-trace","on"},
        {"profile","--repo",".","--compact-search","on","--search-strategy","extent","--owned-selection-trace","on"}}) {
        bool rejected=false;try{(void)options(args);}catch(const std::invalid_argument&){rejected=true;}
        if(!rejected)throw std::runtime_error("ambiguous/invalid model portfolio accepted");
    }
    if(options({"profile","--repo",".","--compact-search","on","--interior-order","3","--shape-choice-replays","8"}).shape_choice_replays!=8)
        throw std::runtime_error("shape replay limit lost");
    for(const auto* value:{"0","-1","1.5","8x","999999999999999999999999999"}) {
        bool rejected=false;
        try{(void)options({"profile","--repo",".","--compact-search","on","--interior-order","3","--shape-choice-replays",value});}
        catch(const std::invalid_argument&){rejected=true;}
        if(!rejected)throw std::runtime_error("invalid shape replay limit accepted");
    }
    if(options({"profile","--repo",".","--compact-search","on"}).shape_area_first||
       !options({"profile","--repo",".","--compact-search","on","--shape-area-first","on"}).shape_area_first)
        throw std::runtime_error("shape-area-first default/selection mismatch");
    for(const auto& [mode,value]:std::vector<std::pair<std::string,std::string>>{{"off","on"},{"both","on"},{"on","typo"}}) {
        bool rejected=false;
        try{(void)options({"profile","--repo",".","--compact-search",mode,"--shape-area-first",value});}
        catch(const std::invalid_argument&){rejected=true;}
        if(!rejected)throw std::runtime_error("invalid shape-area-first option accepted");
    }
    try{(void)options({"profile","--repo",".","--compact-search","on","--owned-selection-trace","typo"});}
    catch(const std::invalid_argument&){invalid_trace=true;}
    if(!invalid_trace)throw std::runtime_error("invalid owned selection trace accepted");
    if(options({"profile","--repo",".","--compact-search","on"}).edge_feasibility||
       !options({"profile","--repo",".","--compact-search","on","--edge-feasibility","on"}).edge_feasibility)
        throw std::runtime_error("initial edge feasibility default/selection mismatch");
    for(const auto& [mode,value]:std::vector<std::pair<std::string,std::string>>{{"off","on"},{"both","on"},{"on","typo"}}){
        bool rejected=false;
        try{(void)options({"profile","--repo",".","--compact-search",mode,"--edge-feasibility",value});}
        catch(const std::invalid_argument&){rejected=true;}
        if(!rejected)throw std::runtime_error("invalid initial edge feasibility option accepted");
    }
    if (options({"profile","--repo",".","--compact-search","on"}).constraint_first ||
        !options({"profile","--repo",".","--compact-search","on","--constraint-first","on"}).constraint_first ||
        options({"profile","--repo",".","--compact-search","both","--constraint-first","off"}).constraint_first)
        throw std::runtime_error("constraint-first option default/explicit selection mismatch");
    for (const auto& [mode, value] : std::vector<std::pair<std::string,std::string>>{
             {"off","on"},{"both","on"},{"on","typo"}}) {
        bool rejected = false;
        try { (void)options({"profile","--repo",".","--compact-search",mode,"--constraint-first",value}); }
        catch (const std::invalid_argument&) { rejected = true; }
        if (!rejected) throw std::runtime_error("invalid constraint-first option accepted");
    }
    const auto valid=options({"profile","--repo",".","--compact-search","off","--outline-mm","168x160.5"});
    const auto seeded=options({"profile","--repo",".","--compact-search","on","--initial-outline-mm","168x159"});
    if(options({"profile","--repo",".","--compact-search","off"}).multiscale_outline||
       !options({"profile","--repo",".","--compact-search","off","--multiscale-outline","on"}).multiscale_outline)
        throw std::runtime_error("multiscale default/opt-in mismatch");
    for(const auto& args:std::vector<std::vector<std::string>>{
        {"profile","--repo",".","--compact-search","off","--multiscale-outline","typo"},
        {"profile","--repo",".","--compact-search","off","--multiscale-outline","on","--outline-mm","168x160"}}) {
        bool rejected=false;try{(void)options(args);}catch(const std::invalid_argument&){rejected=true;}
        if(!rejected)throw std::runtime_error("invalid multiscale profile options accepted");
    }
    if(seeded.outline||seeded.initial_outline!=schgen::FloorplanPoint{168,159})throw std::runtime_error("seed confused with fixed outline");
    bool mixed=false;
    try{(void)options({"profile","--repo",".","--compact-search","on","--outline-mm","168x159","--initial-outline-mm","168x160"});}
    catch(const std::invalid_argument&){mixed=true;}
    if(!mixed)throw std::runtime_error("fixed outline and seed must not coexist");
    if(options({"profile","--repo",".","--compact-search","on"}).edge_translation||
       !options({"profile","--repo",".","--compact-search","on","--edge-translation","on"}).edge_translation)
        throw std::runtime_error("edge-translation default/opt-in mismatch");
    for(const auto& [mode,value]:std::vector<std::pair<std::string,std::string>>{{"off","on"},{"both","on"},{"on","typo"}}) {
        bool rejected=false;
        try{(void)options({"profile","--repo",".","--compact-search",mode,"--edge-translation",value});}
        catch(const std::invalid_argument&){rejected=true;}
        if(!rejected)throw std::runtime_error("invalid edge-translation option accepted");
    }
    if(valid.outline!=schgen::FloorplanPoint{168,160.5})throw std::runtime_error("explicit outline parsed incorrectly");
    for(const auto* value:{"168","168x","x160","1x2x3","0x10","-1x10","nanx10","10xinf","1e999x10","10x2junk"}) {
        bool rejected=false;
        try{(void)options({"profile","--repo",".","--compact-search","off","--outline-mm",value});}
        catch(const std::invalid_argument&){rejected=true;}
        if(!rejected)throw std::runtime_error("invalid diagnostic outline accepted");
    }
    schgen::PcbPlacementInput source;
    source.floorplan.spec.emplace();source.floorplan.spec->outline={{200,190}};
    source.floorplan.spec->edges["N"]={"usb","hdmi"};
    source.floorplan.spec->ordered_edges["N"]={"hdmi","usb"};
    source.floorplan.spec->source="immutable policy";
    const auto original=source.floorplan.spec->outline;
    const auto changed=trial_input(source,true,valid.outline);
    const auto unchanged=trial_input(source,false,std::nullopt);
    if(source.floorplan.spec->outline!=original || source.floorplan.compact_search ||
       changed.floorplan.spec->outline!=valid.outline || !changed.floorplan.compact_search ||
       unchanged.floorplan.spec->outline!=original ||
       changed.floorplan.spec->edges!=source.floorplan.spec->edges ||
       changed.floorplan.spec->ordered_edges!=source.floorplan.spec->ordered_edges ||
       changed.floorplan.spec->source!=source.floorplan.spec->source)
        throw std::runtime_error("outline trial mutated source or changed an unrequested outline");
    source.floorplan.spec.reset();
    const auto fresh=trial_input(source,false,valid.outline);
    if(source.floorplan.spec || !fresh.floorplan.spec || fresh.floorplan.spec->outline!=valid.outline)
        throw std::runtime_error("outline override failed on an input without an explicit spec");
}
void reviewed_profile_identity(const schgen::PcbPlacementInput& input) {
    const auto& sheets = input.floorplan.sheets;
    if (std::count_if(sheets.begin(), sheets.end(), [](const auto& s) {
            return s.name == "board_aux"; }) != 1)
        throw std::runtime_error("profile must load exactly one board_aux sheet");
    const auto& sheet = *std::find_if(sheets.begin(), sheets.end(), [](const auto& s) {
        return s.name == "board_aux"; });
    // The shared guard requires unique C1/LCSC records and Device:C,
    // 10u / C_0805_2012Metric / C15850 BEFORE any historical projection.
    // Inspect the actual loader result, not a separately authored circuit.
    (void)historical_input_contracts::project(sheet, "carrier");
}
void reviewed_profile_counts(const std::map<std::string, std::size_t>& counts) {
    const std::map<std::string, std::size_t> expected{{"board_aux", 36}, {"bringup_rails", 24}};
    if (counts != expected)
        throw std::runtime_error("profile must exercise board_aux=36, bringup_rails=24 owned alternatives only");
}
void observer_free_equivalence(const schgen::PcbPlacementInput& input){
    std::array<std::string,2> hashes,receipts;
    for(int mode=0;mode<2;++mode){
        std::ostringstream capture;
        auto* saved=std::cout.rdbuf(capture.rdbuf());
        try{hashes[mode]=trial(input,false,1,1,mode==0);}
        catch(...){std::cout.rdbuf(saved);throw;}
        std::cout.rdbuf(saved);
        std::istringstream lines(capture.str());std::string line;
        while(std::getline(lines,line)){
            if(line.rfind("receipt ",0)==0||line.rfind("fallback",0)==0)receipts[mode]+=line+'\n';
            if(mode==1&&(line.rfind("stage ",0)==0||line.rfind("edge_search ",0)==0||line.rfind("work completed_outer_attempts=",0)==0))
                throw std::runtime_error("disabled observer published fabricated observations");
        }
        if(mode==1&&capture.str().find("observer_counts=unavailable")==std::string::npos)
            throw std::runtime_error("disabled observations must be explicitly unavailable");
    }
    if(hashes[0]!=hashes[1]||receipts[0].empty()||receipts[0]!=receipts[1])
        throw std::runtime_error("diagnostic observer mode changed PCB output or production receipts");
}
}

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: profile-inputs REPOSITORY");
        profile_option_contracts();
        const auto paths = schgen::resolve_project_paths(argv[1], "carrier");
        auto pattern=(std::filesystem::temp_directory_path()/"profile-inputs.XXXXXX").string();
        const auto created=::mkdtemp(pattern.data());
        if(!created)throw std::runtime_error("private profile schematic scratch creation failed");
        const std::filesystem::path scratch=created;
        std::cout<<"fresh schematic scratch="<<scratch<<'\n';
        const auto index=schgen::load_sheet_index(paths);
        std::vector<schgen::BoardSheetInput> inputs;
        for(const auto& circuit:schgen::load_project_circuits(paths)) {
            const auto band=std::find_if(index.begin(),index.end(),[&](const auto& row){return row.first==circuit.name;});
            if(band==index.end())throw std::runtime_error("missing persistent sheet reference band");
            inputs.push_back({circuit.circuit,band->second,std::nullopt});
        }
        schgen::SymbolLibrary library(paths.repository_root);
        schgen::BoardSchematicOptions schematic_options;
        schematic_options.root_name="Zynq_Carrier";schematic_options.sheet_subdir="schematic";
        schematic_options.reports_dir=scratch/"reports";
        const auto schematic=schgen::build_board_schematic(inputs,library,scratch/"generated",schematic_options);
        if(!schematic.ok())throw std::runtime_error("fresh profile schematic failed: "+schematic.report);
        const auto defaults = load(paths, {}, false, schematic.root_path);
        const auto explicit_input = load(paths, {}, true, schematic.root_path,
            paths.repository_root/"native/benchmarks/carrier-168x159-initial-edge.floorplan.json");
        if(!explicit_input.input.floorplan.spec||explicit_input.input.floorplan.spec->outline!=schgen::FloorplanPoint{168,159})
            throw std::runtime_error("explicit profiler spec was not loaded");
        const auto compact = load(paths, {}, true, schematic.root_path);
        reviewed_profile_identity(defaults.input);
        reviewed_profile_identity(compact.input);
        observer_free_equivalence(defaults.input);
        if (defaults.input.floorplan.compact_search || !defaults.input.owned_groups.empty() ||
            !compact.input.floorplan.compact_search || compact.input.owned_groups.size() != 2)
            throw std::runtime_error("profile input loading omitted mode-specific ownership");
        const auto zones = schgen::build_pcb_zone_geometry(compact.input);
        std::map<std::string, std::size_t> alternatives;
        for (const auto& [sheet, shapes] : zones.geometry.shapes) {
            for (const auto& shape : shapes)
                if (shape.tag.find("/owned-pins-") != std::string::npos) ++alternatives[sheet];
        }
        reviewed_profile_counts(alternatives);
        // Exercise the real opt-in Engine path, not a second translation copy.
        auto candidate=trial_input(compact.input,true,schgen::FloorplanPoint{168,159});
        auto observer=std::make_shared<schgen::FloorplanExperiment>();
        observer->compact_constraint_first=true;candidate.floorplan.experiment=observer;
        bool baseline_rejected=false;
        try{(void)schgen::build_pcb_model(candidate);}catch(const schgen::FloorplanError&){baseline_rejected=true;}
        if(!baseline_rejected)throw std::runtime_error("edge-translation witness no longer requires repair");
        std::size_t candidates=0,repairs=0;
        observer->compact_edge_translation=true;
        observer->edge_translation_completed=[&](std::size_t n,char edge,double shift) {
            if(n>32||(!edge&&shift!=0))throw std::runtime_error("invalid bounded edge observation");
            candidates+=n;repairs+=edge!='\0';
        };
        const auto repaired=schgen::build_pcb_model(candidate);
        const auto events=schgen::pcb_placement_accounting(repaired).fallback_events;
        if(!repairs||candidates<repairs||repairs!=static_cast<std::size_t>(std::count(events.begin(),events.end(),"edge_run_translation")))
            throw std::runtime_error("edge callback and actual fallback ledger disagree");
        placement_requirements_test::physical(candidate,repaired.model,[](bool ok,const std::string& why){if(!ok)throw std::runtime_error(why);});
        if(compact.input.floorplan.experiment||(compact.input.floorplan.spec&&compact.input.floorplan.spec->outline==candidate.floorplan.spec->outline))
            throw std::runtime_error("edge experiment leaked into original prepared inputs");
        // The total alone cannot qualify the reviewed distribution or identity.
        auto rejects = [](auto action) {
            bool rejected = false;
            try { action(); } catch (const std::runtime_error&) { rejected = true; }
            if (!rejected) throw std::runtime_error("profile identity/count mutation escaped");
        };
        auto redistributed = alternatives;
        --redistributed.at("board_aux"); ++redistributed.at("bringup_rails");
        rejects([&] { reviewed_profile_counts(redistributed); });
        auto unrelated = alternatives;
        --unrelated.at("board_aux"); unrelated["unreviewed_sheet"] = 1;
        rejects([&] { reviewed_profile_counts(unrelated); });
        for (int mutation = 0; mutation != 3; ++mutation) {
            auto changed = compact.input;
            auto& sheet = *std::find_if(changed.floorplan.sheets.begin(), changed.floorplan.sheets.end(),
                [](const auto& s) { return s.name == "board_aux"; });
            auto& c1 = *std::find_if(sheet.parts.begin(), sheet.parts.end(), [](const auto& p) { return p.ref == "C1"; });
            if (mutation == 0) c1.value = "100n";
            if (mutation == 1) c1.footprint = "Capacitor_SMD:C_0603_1608Metric";
            if (mutation == 2) for (auto& f : c1.fields) if (f.key == "LCSC") f.value = "C14663";
            rejects([&] { reviewed_profile_identity(changed); });
        }
        std::cout << "PASS actual profile loader: reviewed C1 10u/0805/C15850; default no ownership; "
            "compact board_aux=36 + bringup_rails=24, 60 alternatives; identity/count mutations rejected\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
