#include "schgen/placement_integrity.hpp"

#include <sstream>

namespace schgen::rules {
namespace {

constexpr Rule rule{
    "protect-first-after-connector", "protection",
    "A protection part that serves a connector pin sits on the connector's face, and no other part on that net is nearer the connector pin than it is.",
    "A surge must meet the clamp before anything else; every millimetre and every via ahead of the clamp adds inductance, and so volts, to what the protected parts see.",
    "ST USBLC6-2 datasheet, layout section, https://www.st.com/resource/en/datasheet/usblc6-2.pdf; "
    "TI SLVA680, ESD Protection Layout Guide, https://www.ti.com/lit/an/slva680/slva680.pdf",
    "primary vendor document", Enforcement::measured};

RuleResult check(const RuleContext& context) {
    RuleResult result{&rule, 0, context.unresolved({"protect"}), {}};
    for (const Service* service : context.serving({"protect"})) {
        const std::size_t part = service->part, owner = service->owner;
        if (!context.connector(owner)) {
            result.measurements.push_back(context.label(part) + " protects " + service->pin +
                                          ", which is not a connector pin; its order is not judged");
            continue;
        }
        ++result.checked;
        if (context.rear(part) != context.rear(owner))
            result.findings.push_back({context.label(part), "is on the " + context.face(part) + " face, but the connector pin " +
                                                                service->pin + " it protects is on the " + context.face(owner)});
        const std::string net = context.net_at(owner, service->pads.front());
        if (net.empty()) {
            result.findings.push_back({context.label(part), "protects " + service->pin + ", which carries no net"});
            continue;
        }
        const auto own = context.net_gap(owner, service->pads, part, net);
        if (!own) {
            result.findings.push_back({context.label(part), "protects " + service->pin + " but has no pad on its net " + net});
            continue;
        }
        std::optional<std::size_t> nearer;
        double least = *own - constants::judging_resolution.value;
        for (std::size_t other = 0; other < context.parts().size(); ++other) {
            if (other == part || other == owner || !context.placed(other)) continue;
            const auto gap = context.net_gap(owner, service->pads, other, net);
            if (!gap || *gap >= least) continue;
            least = *gap;
            nearer = other;
        }
        std::ostringstream row;
        row << context.label(part) << " is " << *own << " mm from " << service->pin << " on net " << net;
        result.measurements.push_back(row.str());
        if (!nearer) continue;
        std::ostringstream detail;
        detail << "is " << *own << " mm from " << service->pin << " on net " << net << ", but " << context.label(*nearer)
               << " is nearer at " << least << " mm";
        result.findings.push_back({context.label(part), detail.str()});
    }
    return result;
}

}

extern const RuleEntry protect_first_after_connector{rule, check};

}
