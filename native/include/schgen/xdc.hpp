#pragma once

#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace schgen {
using XdcStrings = std::vector<std::pair<std::string, std::string>>;

struct XdcPort {
    std::string net, sheet, kind = "single";
    std::optional<std::string> pair_with;
    std::optional<int> impedance;
    int type_index = -1;
};

struct XdcInput {
    std::vector<std::pair<std::string, XdcStrings>> connectors;
    XdcStrings ball_net, pin_names, jpin_net, function_map, bank_rails, vcco_rails;
    std::vector<XdcPort> ports;
    std::vector<std::string> refs;
    // Optional diagnostic presentation order. The Python adapter supplies its
    // historical set iteration order; standalone callers use sorted bank IDs.
    std::vector<std::string> drift_order;
    std::string device, zynq_ref;
    // Filesystem presentation is supplied by the caller; the engine does no I/O.
    std::string contract_path, contract_source, som_source;
};

struct XdcPin {
    std::string net, jpin, ball, pin_name, bank, iostd;
    std::vector<std::string> consumers;
    XdcPort type;
};

struct XdcOutput {
    std::vector<XdcPin> entries;
    std::vector<std::string> checks;
    std::string text;
};

class XdcError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

double xdc_rail_volts(const std::string& rail);
std::pair<std::string, bool> xdc_pin_traits(const std::string& pin_name);
XdcOutput generate_xdc(const XdcInput& input);
}  // namespace schgen
