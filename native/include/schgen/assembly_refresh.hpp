#pragma once

#include "schgen/assembly_facts.hpp"

#include <functional>
#include <optional>
#include <string>
#include <vector>

namespace schgen {

struct AssemblyRequest {
    std::string url;
    std::optional<std::string> body;
};

using AssemblyTransport = std::function<std::string(const AssemblyRequest&)>;
using AssemblyClock = std::function<std::string()>;

struct AssemblyRefreshResult {
    AssemblyFacts facts;
    std::vector<std::string> changes, failures;
};

AssemblyPart read_assembly_part(const std::string& code, const AssemblyTransport& transport, const std::string& read_utc);
AssemblyRefreshResult refresh_assembly_facts(const AssemblyFacts& old, const std::vector<std::string>& codes,
                                             const AssemblyTransport& transport, const AssemblyClock& clock);
AssemblyTransport live_assembly_transport();
std::string assembly_utc_now();
std::optional<int> run_assembly_refresh_command(int argc, char** argv);

namespace assembly_endpoint {
inline constexpr const char* search = "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList";
inline constexpr const char* part_page = "https://jlcpcb.com/partdetail/x/";
inline constexpr const char* lcsc_detail = "https://wmsc.lcsc.com/ftps/wm/product/detail?productCode=";
}

}
