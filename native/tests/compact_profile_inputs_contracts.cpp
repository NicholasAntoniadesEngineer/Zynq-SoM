// Exercise the diagnostic's actual loader, not a second copy of its logic.
#define main compact_stage_profile_entry
#include "compact_stage_profile.cpp"
#undef main

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: profile-inputs REPOSITORY");
        const auto paths = schgen::resolve_project_paths(argv[1], "carrier");
        const auto defaults = load(paths, {}, false);
        const auto compact = load(paths, {}, true);
        if (defaults.input.floorplan.compact_search || !defaults.input.owned_groups.empty() ||
            !compact.input.floorplan.compact_search || compact.input.owned_groups.size() != 2)
            throw std::runtime_error("profile input loading omitted mode-specific ownership");
        const auto zones = schgen::build_pcb_zone_geometry(compact.input);
        std::size_t alternatives = 0;
        for (const auto& [sheet, shapes] : zones.geometry.shapes) {
            (void)sheet;
            for (const auto& shape : shapes)
                alternatives += shape.tag.find("/owned-pins-") != std::string::npos;
        }
        if (alternatives != 56)
            throw std::runtime_error("profile does not exercise the 56 live owned alternatives");
        std::cout << "PASS actual profile loader: default no ownership; compact two groups, 56 alternatives\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
