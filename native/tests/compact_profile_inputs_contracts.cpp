// Exercise the diagnostic's actual loader, not a second copy of its logic.
#define main compact_stage_profile_entry
#include "compact_stage_profile.cpp"
#undef main
#include "historical_input_contracts.hpp"
#include "pcb_placement_requirements.hpp"

namespace {
void profile_option_contracts() {
    const auto options = [](std::vector<std::string> args) {
        std::vector<char*> raw;
        for (auto& arg : args) raw.push_back(arg.data());
        return parse(static_cast<int>(raw.size()), raw.data());
    };
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
}

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: profile-inputs REPOSITORY");
        profile_option_contracts();
        const auto paths = schgen::resolve_project_paths(argv[1], "carrier");
        const auto defaults = load(paths, {}, false);
        const auto compact = load(paths, {}, true);
        reviewed_profile_identity(defaults.input);
        reviewed_profile_identity(compact.input);
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
