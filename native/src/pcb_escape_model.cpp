#include "pcb_escape_internal.hpp"

namespace schgen {
using namespace pcb_escape;
PcbEscapeInput::PcbEscapeInput(const PcbModel &m, ReturnPathResult v1,
                               std::map<std::string, PcbEscapeSignalClass> triage,
                               std::string bytes)
    : geometry_(m), keepout_(m.som_keepout), classes_(m.classes), return_path_(std::move(v1)),
      triage_(std::move(triage)), interface_bytes_(std::move(bytes)) {}
int PcbEscapeSignalClass::rank() const {
    if (klass == "GENUINE")
        return 0;
    if (klass == "MODERATE")
        return 1;
    if (klass == "LOW")
        return 2;
    throw PcbEscapeError("uncurated SI class " + repr(klass));
}
const PcbEscapeSignalClass &PcbEscapeInput::classify(const std::string &net) const {
    auto it = triage_.find(net);
    if (it == triage_.end())
        throw PcbEscapeError("uncurated DF40 signal net " + repr(net) +
                             " — supply its curated SI class (LAW 7: never a silent default)");
    it->second.rank();
    return it->second;
}
ContactGeom pcb_escape_contact_geometry(const PcbCheckFootprint &fp) {
    std::vector<std::tuple<double, double, double, double>> pads;
    const auto name = std::filesystem::path(fp.source).filename().string();
    // Strict validation is deliberately separate from scan_pad_nodes, whose
    // general-purpose defaults cannot invent connector contact geometry.
    for (const auto &p : *list(fp.document))
        if (tag(p, "pad")) {
            auto at = child(p, "at"), size = child(p, "size");
            if (!at || !size)
                throw PcbEscapeError(name + " pad " + atom(list(p)->at(1)) +
                                     ": no at/size — contact geometry underivable");
            pads.emplace_back(number(*at, 1), number(*at, 2), number(*size, 1), number(*size, 2));
        }
    if (pads.empty())
        throw PcbEscapeError(name + ": no pads — contact geometry underivable");
    try {
        return contact_geometry(pads);
    } catch (const std::runtime_error &e) {
        throw PcbEscapeError(name + ": " + e.what());
    }
}
Box4 pcb_escape_corridor_local(const PcbCheckFootprint &fp) {
    std::vector<std::pair<double, double>> uv;
    for (const auto &[pad, p] : positions(fp)) {
        (void)pad;
        uv.push_back(p);
    }
    return corridor_local_from_uv(uv, radius, .15);
}
Box4 pcb_escape_corridor_board(const PcbCheckFootprint &fp, double x, double y, double rotation) {
    return corridor_board_rect(pcb_escape_corridor_local(fp), x, y, rotation == 0 ? 0.0 : rotation);
}
PcbEscapePlan PcbEscapePlanResult::for_checks() const {
    PcbEscapePlan p;
    p.netted_counts = netted_counts;
    p.genuine_pairs = genuine_pairs;
    p.content_key = content_key;
    for (const auto &[ref, rows] : lanes) {
        auto &out = p.lanes[ref];
        for (const auto &r : rows)
            out.push_back(r);
    }
    for (const auto &r : pairs)
        p.pairs.push_back(r);
    return p;
}
} // namespace schgen
