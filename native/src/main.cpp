#include "schgen/catalog.hpp"
#include "schgen/circuit.hpp"
#include "schgen/legalize.hpp"
#include "schgen/occupancy.hpp"
#include "schgen/quantize.hpp"
#include "schgen/seat.hpp"
#include "schgen/sexpr.hpp"
#include "schgen/turn.hpp"
#include "schgen/project_cli.hpp"
#include "schgen/regression_cli.hpp"
#include "schgen/part_import.hpp"
#include "schgen/selftest_full.hpp"

#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc, char** argv) {
    try {
        if (argc == 1 || (argc == 2 && std::string(argv[1]) == "--help")) {
            std::cout << "usage: schgen <command>\n"
                         "  self-check\n"
                         "  check --tests-dir BUILD [--repo ROOT] [--project NAME_OR_PATH] [-o DIRECTORY]\n"
                         "  selftest [--project NAME] [SUBSYSTEM ...] [--kicad-cli PATH] [-o REPORT]\n"
                         "  catalog-compile <parts_dir> <catalog.bin>\n"
                         "  circuit-compile <circuits_dir> <circuits.bin>\n"
                         "  project-check [--repo ROOT] [--project NAME] [SUBSYSTEM ...]\n"
                         "  circuit-check [--repo ROOT] [--project NAME] [SUBSYSTEM ...]\n"
                         "  board-schematic [--project NAME] [SUBSYSTEM ...] -o DIRECTORY\n"
                         "  build NAME [--project NAME] [-o DIRECTORY] [--no-render]\n"
                         "  devkit --output DIRECTORY [--repo ROOT] [--no-render] (four-sheet example)\n"
                         "  dump-circuits [--project NAME] (publish live native-authored IR)\n"
                         "  nets [--project NAME] --output HEADER (C++ net-name contract)\n"
                         "  subsystem-check | carrier-check [--project NAME] (strict native package gates)\n"
                         "  chir-rung TAG | w11-sweep MM [SHEET ...] [--project NAME] (writes board; restores inputs)\n"
                         "  w12-bound TAG | w12-stageprobe TAG [SHEET ...] [--project NAME] [--cons-only] (private probes)\n"
                         "  pcb-stage [--project NAME] [--kicad-cli PATH] -o DIRECTORY (construction only)\n"
                         "  pcb-drc [--project NAME] [--pcb FILE] [-o REPORT]\n"
                         "  subsystem-new NAME [--repo DIRECTORY] (new C++ package; never overwrites)\n"
                         "  part-import --parts-root DIRECTORY (--from-json FILE | --lcsc ID) [--name NAME] [--overwrite] [--catalog FILE]\n"
                         "  render3d | model3d-check [--project NAME] [-o DIRECTORY]\n"
                         "  board-step [--project NAME] [--pcb FILE] --output FILE\n"
                         "  assembly | ratsnest | si-constraints [--project NAME] [-o DIRECTORY]\n"
                         "  fab-profile [--project NAME] [-o REPORT_DIRECTORY]\n"
                         "  manifest [--project NAME] [SUBSYSTEM ...] [-o FILE]\n"
                         "  gallery [--project NAME]\n"
                         "  diagram [--project NAME] [SUBSYSTEM ...] [-o FILE]\n"
                         "  preflight [--project NAME] [SUBSYSTEM ...] [--qty N] [--min-stock N] [--allow-missing]\n"
                         "  constraints [--project NAME] [SUBSYSTEM ...] [-o DIRECTORY]\n"
                         "  bom-values | footprint-pads | pin-completeness | symbol-law [--project NAME] [-o FILE]\n"
                         "  spice [--project NAME] [SUBSYSTEM ...] [--no-ngspice] [-o FILE]\n"
                         "  firmware | manual | testplan | power-sequence [--project NAME] [-o FILE]\n"
                         "  scfw [--project NAME] [-o DIRECTORY]\n"
                         "  powertree|part-rules [--project NAME] [SUBSYSTEM ...] [-o REPORT]\n"
                         "  thermal [--project NAME] [SUBSYSTEM ...] [--pcb FILE] [-o REPORT]\n"
                         "  design-rules|testpoints [--project NAME] [SUBSYSTEM ...] [-o REPORT]\n"
                         "  som-interface [--project NAME] [--som FILE] [--refs J1,J2,J3] [-o FILE]\n"
                         "  xdc|vivado [--project NAME] [--som FILE] [--contract FILE] [-o FILE]\n"
                         "  fpga [--project NAME] [-o DIRECTORY]  (XDC + Vivado, one live extraction)\n"
                         "  bom [--project NAME] [SUBSYSTEM ...] [-o FILE] [--allow-missing] [--qualified-refs]\n"
                         "  link [--project NAME] [SUBSYSTEM ...] [--contract FILE] [-o REPORT]\n"
                         "  devicetree [--project NAME] [--som FILE] [--contract FILE] [-o FILE]\n"
                         "  board [--project NAME] [-o DIRECTORY] [--no-render] [--timing] (native; incomplete audit integration fails explicitly)\n";
            return 0;
        }
        if (argc >= 2 && std::string(argv[1]) == "selftest-worker") {
            if (argc != 4) throw std::runtime_error("selftest-worker requires request and output paths");
            std::cout << schgen::selftest_worker_emit(schgen::parse_json_file(argv[2]), argv[3]);
            return 0;
        }
        if (const auto status = schgen::run_part_import_command(argc, argv)) return *status;
        if (const auto status = schgen::run_regression_command(argc, argv)) return *status;
        if (const auto status = schgen::run_project_command(argc, argv)) return *status;
        if (argc >= 2 && std::string(argv[1]) == "catalog-compile") {
            if (argc != 4) {
                throw std::runtime_error(
                    "usage: schgen catalog-compile <parts_dir> <catalog.bin>");
            }
            if (!schgen::compile_part_catalog(argv[2], argv[3])) {
                throw std::runtime_error("catalog-compile returned false");
            }
            std::cout << "catalog compiled " << argv[3] << "\n";
            return 0;
        }
        if (argc >= 2 && std::string(argv[1]) == "circuit-compile") {
            if (argc != 4) {
                throw std::runtime_error(
                    "usage: schgen circuit-compile <circuits_dir> <circuits.bin>");
            }
            if (!schgen::compile_circuit_catalog(argv[2], argv[3])) {
                throw std::runtime_error("circuit-compile returned false");
            }
            std::cout << "circuits compiled " << argv[3] << "\n";
            return 0;
        }
        if (argc != 2 || std::string(argv[1]) != "self-check") {
            throw std::runtime_error("unsupported command or arguments; use --help");
        }
        const schgen::Box4 a{0.0, 0.0, 10.0, 8.0};
        const schgen::Box4 b{12.0, 0.0, 16.0, 8.0};
        if (schgen::boxes_overlap(a, b, 0.3)) {
            throw std::runtime_error("schgen: separated boxes reported overlap");
        }
        if (!schgen::spot_free(a, 0.25, {b}, {}, {})) {
            throw std::runtime_error("schgen: spot_free rejected a free site");
        }
        schgen::Occupancy occ(160.0, 140.0, 0.3, 20.0, 3.32, 1.0, 0.05);
        occ.add(55.0, 45.0, 50.0, 50.0, {}, {}, 3, {});
        if (!occ.fits_hashed(10.0, 10.0, 16.0, 10.0, {}, {}, 3, {})) {
            throw std::runtime_error("schgen: occupancy rejected a free pose");
        }
        const auto turned = schgen::turn_box({1.0, -2.0, 9.0, 2.0}, 90.0);
        if (turned.x0 != -2.0 || turned.y0 != -9.0 || turned.x1 != 2.0
            || turned.y1 != -1.0) {
            throw std::runtime_error("schgen: turn_box missed a quarter turn");
        }
        if (schgen::outline_snap_up(161.0001) != 165.0) {
            throw std::runtime_error("schgen: outline_snap_up missed the 5 mm grid");
        }
        const auto axis = schgen::pair_axis(a, b);
        if (!axis.axis_x || !axis.a_first) {
            throw std::runtime_error("schgen: pair_axis flipped a separated pair");
        }
        const auto bf = schgen::bellman_ford(2, {0}, {1}, {1.0});
        if (!bf.feasible || bf.dist.size() != 2) {
            throw std::runtime_error("schgen: bellman_ford rejected a free edge");
        }
        const auto dfs = schgen::seat_dfs({{a}, {b}}, {}, 0.3, 1000);
        if (!dfs.solved || dfs.pick.size() != 2) {
            throw std::runtime_error("schgen: seat_dfs failed a free pair");
        }
        const std::string dumped = schgen::sexpr_dumps(
            schgen::sexpr_loads("(kicad_pcb (version 20241229))"));
        if (dumped.find("kicad_pcb") == std::string::npos) {
            throw std::runtime_error("schgen: sexpr roundtrip dropped the tag");
        }
        if (!schgen::cross_edge_fanout_hold(
                {{0.0, 10.0, 20.0, 8.0, {}, {}, 'N'},
                 {40.0, 10.0, 20.0, 8.0, {}, {}, 'S'}},
                0.3)) {
            throw std::runtime_error("schgen: cross_edge_fanout_hold rejected a free pair");
        }
        if (schgen::rects_overlap_any({{0.0, 0.0, 10.0, 8.0}},
                                      {{12.0, 0.0, 16.0, 8.0}}, 1e-6)) {
            throw std::runtime_error("schgen: rects_overlap_any flagged a gap");
        }
        std::cout << "schgen native occupancy+seat+route+sexpr+emit"
                  << " — kernel self-check ok\n";
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << "schgen: " << exc.what() << "\n";
        return 1;
    }
}
