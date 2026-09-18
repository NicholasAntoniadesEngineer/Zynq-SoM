#include "schgen/project_outputs.hpp"
#include "schgen/project.hpp"
#include "schgen/json.hpp"
#include "schgen/som_interface.hpp"
#include "schgen/vivado.hpp"

#include <algorithm>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>

namespace {
std::string read(const std::filesystem::path& path) {
    std::ifstream file(path, std::ios::binary);
    if (!file) throw std::runtime_error("cannot read " + path.string());
    return {(std::istreambuf_iterator<char>(file)), {}};
}
void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}
const schgen::JsonNode& field(const schgen::JsonNode& node, const std::string& key) {
    const auto* value = schgen::object_field(node, key);
    if (!value) throw std::runtime_error("missing snapshot field " + key);
    return *value;
}
schgen::XdcStrings strings(const schgen::JsonNode& node) {
    require(node.kind == schgen::JsonKind::Object, "snapshot dictionary required");
    schgen::XdcStrings out;
    for (const auto& [key, value] : node.object_value) {
        require(value.kind == schgen::JsonKind::String, "snapshot string required");
        out.emplace_back(key, value.string_value);
    }
    return out;
}
}
int main(int argc, char** argv) {
    try {
        require(argc == 2, "expected repository root");
        const auto repository = std::filesystem::absolute(argv[1]).lexically_normal();
        const auto snapshot = schgen::parse_json_file(
            (repository / "native/tests/data/som_real_baseline.json").string());
        const auto& zynq = field(snapshot, "zynq");
        schgen::XdcInput live;
        live.device = field(zynq, "value").string_value;
        live.zynq_ref = field(zynq, "zynq_ref").string_value;
        live.pin_names = strings(field(zynq, "pin_names"));
        live.ball_net = strings(field(zynq, "ball_net"));
        live.jpin_net = strings(field(zynq, "jpin_net"));
        live.refs = {"J1", "J2", "J3"};
        for (const std::string name : {"carrier", "devkit_mini"}) {
            const auto paths = schgen::resolve_project_paths(repository, name);
            std::vector<schgen::CircuitSheetIr> sheets;
            for (const auto& item : schgen::load_project_circuits(paths)) sheets.push_back(item.circuit);
            const auto in = schgen::load_project_xdc_input(repository, paths.project_root,
                sheets, live, paths.som_schematic);
            auto banks = in.bank_rails, vcco = in.vcco_rails;
            std::sort(banks.begin(), banks.end());
            std::sort(vcco.begin(), vcco.end());
            require(banks == vcco, name + ": project and connector bank-rail policies diverged");
            for (const auto& [bank, rail] : banks) {
                const double volts = schgen::xdc_rail_volts(rail);
                require(volts == 3.3 || volts == 2.5 || volts == 1.8,
                        name + ": no LVCMOS standard for bank " + bank);
            }
            const auto out = schgen::generate_xdc(in);
            require(out.entries.size() == 156 && out.checks.size() == 6, name + ": XDC coverage changed");
            require(out.text == read(paths.fpga_dir / "Zynq_Carrier_pins.xdc"), name + ": XDC artifact changed");
            require(schgen::render_vivado(out, in.device, in.zynq_ref,
                "Zynq_Carrier_pins.xdc", in.refs) == read(paths.fpga_dir / "create_project.tcl"),
                name + ": Vivado artifact changed");
            auto drift = in;
            drift.jpin_net.front().second += "_CORRUPTED";
            bool rejected = false;
            try { (void)schgen::generate_xdc(drift); }
            catch (const schgen::XdcError&) { rejected = true; }
            require(rejected, name + ": live contract drift was accepted");
            std::cout << name << ": native project-to-XDC/Vivado artifact parity passed\n";
        }
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
