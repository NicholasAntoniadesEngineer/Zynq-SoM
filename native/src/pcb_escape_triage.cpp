#include "pcb_escape_internal.hpp"

namespace schgen {
PcbEscapeSignalClass classify_pcb_escape_signal(const std::string &net,
                                                const ProjectStrings &mapping,
                                                const PcbEscapeTriage &triage) {
    using namespace pcb_checks;
    const auto it =
        std::find_if(mapping.begin(), mapping.end(), [&](const auto &p) { return p.first == net; });
    const auto function = it == mapping.end() ? net : it->second;
    for (const auto &r : triage.rules)
        if (std::regex_match(function, r.pattern))
            return {net, function, r.klass, r.note};
    throw PcbEscapeError("uncurated DF40 signal net " + repr(net) + " (function " + repr(function) +
                         ") — add a curated class row to the board's escape_triage.json (LAW 7: "
                         "never a silent default)");
}
} // namespace schgen
