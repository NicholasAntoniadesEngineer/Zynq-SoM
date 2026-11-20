#include "schgen/vivado.hpp"

#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <stdexcept>

namespace {
void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}
template<class F> void rejects(F fn) {
    try { fn(); } catch (const std::runtime_error&) { return; }
    throw std::runtime_error("invalid Tcl input accepted");
}
}
int main(int argc, char** argv) {
    try {
        require(argc == 2, "expected golden fixture path");
        schgen::XdcOutput xdc;
        for (const auto& row : std::vector<std::vector<std::string>>{
                {"B_P", "J1.4", "B1", "IO_L2P_SRCC_34"},
                {"A_P", "J1.2", "A1", "IO_L1P_MRCC_34"},
                {"A_N", "J1.3", "A2", "IO_L1N_MRCC_34"},
                {"DATA", "J1.1", "C1", "IO_L3P_34"}}) {
            schgen::XdcPin pin;
            pin.net = row[0]; pin.jpin = row[1]; pin.ball = row[2];
            pin.pin_name = row[3]; pin.bank = "34";
            xdc.entries.push_back(pin);
        }
        std::ifstream file(argv[1]);
        require(file.good(), "cannot read golden");
        const std::string golden((std::istreambuf_iterator<char>(file)), {});
        auto render = [&](const std::map<std::string, double>& clocks) {
            return schgen::render_vivado(xdc, "xc7z020clg400-1", "U2", "pins.xdc",
                                         {"J1", "J2", "J3"}, clocks);
        };
        require(render({{"A_P", 10.0}}) == golden, "Vivado bytes differ from Python baseline");
        const auto text = render({});
        require(text.find("# create_clock -name A_P") < text.find("# create_clock -name B_P"),
                "clocks not sorted");
        require(text.find("create_clock -name A_N") == std::string::npos,
                "negative pair member received clock");
        require(render({{"A_P", 2.5}}).find("-period 2.5") != std::string::npos,
                "fractional clock period formatting");
        require(schgen::render_vivado({}, "part", "U2", "../pins.xdc", {"J9"})
                    .find("no clock-capable PL ports bound through J9") != std::string::npos,
                "empty clock population diagnostic");
        rejects([&] { render({{"A_P", 0.0}}); });
        rejects([&] { render({{"A_P", -1.0}}); });
        rejects([&] { render({{"A_P", std::numeric_limits<double>::infinity()}}); });
        rejects([&] { render({{"A_P", std::numeric_limits<double>::quiet_NaN()}}); });
        rejects([&] { render({{"A;exec", 1.0}}); });
        rejects([&] { schgen::render_vivado(xdc, "[exec bad]", "U2", "pins.xdc", {}); });
        rejects([&] { schgen::render_vivado(xdc, "part", "U2", "[exec bad]", {}); });
        rejects([&] { schgen::render_vivado(xdc, "", "U2", "pins.xdc", {}); });
        std::cout << "Vivado native contracts passed\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
