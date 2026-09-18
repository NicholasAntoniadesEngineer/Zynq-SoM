#include "schgen/constraints.hpp"
#include <iostream>

namespace {
std::size_t checks = 0;
void require(bool condition, const std::string& detail) {
    ++checks; if (!condition) throw std::runtime_error(detail);
}
const schgen::JsonNode& field(const schgen::JsonNode& n, const std::string& key) {
    const auto* p = schgen::object_field(n,key);
    require(p != nullptr,"missing " + key); return *p;
}
}
int main(int argc,char** argv) {
    using namespace schgen;
    try {
        require(argc == 3,"usage: constraints_contracts REPOSITORY FIXTURES");
        const auto fixtures = parse_json_file((std::filesystem::path(argv[2])/"projects.json").string());
        for (const auto& name : {"carrier","devkit_mini"}) {
            const auto paths = resolve_project_paths(argv[1],std::filesystem::path(name));
            auto circuits = load_project_circuits(paths);
            const auto spec_path = paths.project_root/"research/si_spec.json";
            const auto specs = needs_signal_specs(circuits) ? load_signal_specs(spec_path) : std::vector<PairSignalSpec>{};
            const auto result = generate_layout_constraints(circuits,specs,spec_path.string());
            require(result.csv == field(field(fixtures,name),"csv").string_value,std::string(name)+" CSV bytes differ");
            require(result.dru == field(field(fixtures,name),"dru").string_value,std::string(name)+" rule bytes differ");
            if (needs_signal_specs(circuits)) {
                bool failed = false;
                try { generate_layout_constraints(circuits,{},"missing targets"); }
                catch (const ProjectError& error) { failed = std::string(error.what()).find("no per-kind default") != std::string::npos; }
                require(failed,"missing researched target silently accepted");
            }
        }
        CircuitSheetIr c; c.name="x"; c.title="CSV quoting";
        c.nets.push_back({"BUS,\"A\"","port",{}});
        CircuitPortIr p; p.net=c.nets.front().name; p.kind="sd_bus"; p.has_level_v=true; p.level_v=1.8;
        p.has_bus=true; p.bus="sd\nline"; p.has_speed_hz=true; p.speed_hz=50000000;
        c.port_types.push_back(p);
        auto out=generate_layout_constraints({{"sheet",{},c}},{},"unused");
        require(out.port_count==1,"port count differs");
        require(out.csv.find("\"BUS,\"\"A\"\"\"")!=std::string::npos,"CSV quoting lost punctuation");
        require(out.csv.find("SD_1V8")!=std::string::npos,"SD voltage class differs");
        require(out.csv.find("2.5")!=std::string::npos,"SD explicit uncited policy changed");
        require(out.csv.find("speed=50000000Hz; level=1.8V")!=std::string::npos,"port metadata lost");
        c.port_types.front().has_level_v=false;
        bool rejected=false;try{generate_layout_constraints({{"sheet",{},c}},{},"");}catch(const ProjectError&){rejected=true;}
        require(rejected,"missing SD voltage accepted");
        PairSignalSpec pair;pair.match_tol_mil=20;pair.intra_pair_skew_mil=5;
        require(pair.match_tol_mm()==0.508&&pair.intra_pair_skew_mm()==0.127,"SI unit conversion differs");
        require(differential_geometry(90)->width_mm==0.2611,"90-ohm width differs");
        require(differential_geometry(100)->gap_mm==0.2032,"100-ohm gap differs");
        require(!differential_geometry(85),"uncited impedance fabricated geometry");
        std::cout<<"layout constraints: "<<checks<<" checks passed\n";return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
