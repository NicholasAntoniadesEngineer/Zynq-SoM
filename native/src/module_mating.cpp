#include "schgen/module_mating.hpp"

#include "schgen/turn.hpp"

#include <algorithm>
#include <cmath>
#include <sstream>
#include <stdexcept>

namespace schgen {
namespace {

using mating_constants::mate_quantum;

std::map<std::string, const SomPad*> by_pin(const std::vector<SomPad>& pads) {
    std::map<std::string, const SomPad*> out;
    for (const auto& pad : pads) out.emplace(pad.pin, &pad);
    return out;
}

int side_of(double value) { return value > 0 ? 1 : value < 0 ? -1 : 0; }

std::string millimetres(double value) {
    std::ostringstream text;
    text << value << " mm";
    return text.str();
}

}

bool ModuleMatingJudgement::ok() const {
    return std::all_of(connectors.begin(), connectors.end(), [](const auto& c) { return c.findings.empty(); });
}

std::vector<SomPad> posed_footprint_pads(const PcbCheckFootprint& footprint, double x, double y, double turn) {
    std::vector<SomPad> out;
    for (const auto& [name, type, lx, ly, rotation, w, h] : footprint.pads) {
        (void)type;
        if (name.empty()) continue;
        const auto [dx, dy] = turn_point(lx, ly, -turn);
        const auto [ex, ey] = pad_half_extent(w, h, rotation + turn);
        out.push_back({name, x + dx, y + dy, ex + ex, ey + ey});
    }
    return out;
}

std::vector<MatePadFinding> module_row_consistency(const ModuleMate& mate, double* row_inset) {
    std::vector<MatePadFinding> findings;
    if (mate.receptacle.empty()) return {{"", "the module connector has no receptacle pads"}};
    double cx = 0.0, cy = 0.0;
    for (const auto& pad : mate.receptacle) {
        cx += pad.x;
        cy += pad.y;
    }
    cx /= static_cast<double>(mate.receptacle.size());
    cy /= static_cast<double>(mate.receptacle.size());
    const auto mates = by_pin(mate.mate);
    double inset = 0.0;
    for (const auto& socket : mate.receptacle) {
        const auto found = mates.find(socket.pin);
        if (found == mates.end()) {
            findings.push_back({socket.pin, "the mate footprint has no pad of this number"});
            continue;
        }
        const SomPad& plug = *found->second;
        const bool along_x = socket.w < socket.h;
        const double along = along_x ? plug.x - socket.x : plug.y - socket.y;
        const double across = along_x ? plug.y - socket.y : plug.x - socket.x;
        const double half_length = (along_x ? socket.h : socket.w) / 2;
        const int socket_side = side_of(along_x ? socket.y - cy : socket.x - cx);
        const int plug_side = side_of(along_x ? plug.y - cy : plug.x - cx);
        inset = std::max(inset, std::fabs(across));
        if (std::fabs(along) > mate_quantum.value)
            findings.push_back({socket.pin, "mate pad is " + millimetres(along) + " along the row from its receptacle pad"});
        if (std::fabs(across) > half_length)
            findings.push_back({socket.pin, "mate pad is " + millimetres(across) + " across the row, outside its receptacle pad (half length " +
                                                millimetres(half_length) + ")"});
        if (socket_side == 0 || plug_side != socket_side)
            findings.push_back({socket.pin, "mate pad is not on the row side of its receptacle pad"});
    }
    if (row_inset) *row_inset = inset;
    return findings;
}

ModuleConnectorGeom fit_module_mate(const ModuleConnectorGeom& receptacle, const PcbCheckFootprint& mate, const std::set<std::string>& pins) {
    ModuleMate base;
    base.connector = receptacle.ref;
    for (const auto& pad : receptacle.pads)
        if (pins.count(pad.pin)) base.receptacle.push_back(pad);
    if (base.receptacle.size() != pins.size())
        throw std::runtime_error("module mating: " + receptacle.ref + " has " + std::to_string(base.receptacle.size()) +
                                 " receptacle pads for " + std::to_string(pins.size()) + " interface pins");
    const auto sockets = by_pin(base.receptacle);
    struct Fit {
        double x = 0.0, y = 0.0;
        ModuleMate mate;
    };
    std::vector<Fit> fits;
    std::string rejected;
    for (double turn = 0; turn < mating_constants::quarter_turn.value * 4; turn += mating_constants::quarter_turn.value) {
        const auto local = by_pin(posed_footprint_pads(mate, 0, 0, turn));
        double sx = 0.0, sy = 0.0;
        bool complete = true;
        for (const auto& [pin, socket] : sockets) {
            const auto found = local.find(pin);
            if (found == local.end()) {
                complete = false;
                break;
            }
            sx += socket->x - found->second->x;
            sy += socket->y - found->second->y;
        }
        if (!complete) throw std::runtime_error("module mating: mate footprint " + mate.source + " lacks a pad for an interface pin of " +
                                                receptacle.ref);
        const double tx = sx / static_cast<double>(sockets.size()), ty = sy / static_cast<double>(sockets.size());
        ModuleMate candidate = base;
        candidate.turn = turn;
        for (const auto& pad : posed_footprint_pads(mate, tx, ty, turn))
            if (pins.count(pad.pin)) candidate.mate.push_back(pad);
        double inset = 0.0;
        const auto findings = module_row_consistency(candidate, &inset);
        if (findings.empty()) {
            fits.push_back({tx, ty, std::move(candidate)});
            continue;
        }
        rejected += " turn " + std::to_string(static_cast<int>(turn)) + ": " + std::to_string(findings.size()) +
                    " pins off, first pin " + findings.front().pin + " " + findings.front().detail + ";";
    }
    if (fits.size() != 1)
        throw std::runtime_error("module mating: " + receptacle.ref + " fits the mate footprint " + mate.source + " in " +
                                 std::to_string(fits.size()) + " orientations, exactly one is required;" + rejected);
    ModuleConnectorGeom out = receptacle;
    out.x = fits.front().x;
    out.y = fits.front().y;
    out.turn = fits.front().mate.turn;
    out.mate = fits.front().mate.mate;
    return out;
}

ModuleMatingJudgement judge_module_mating(const std::vector<ModuleMate>& mates,
                                          const std::map<std::string, const PcbCheckInstance*>& mating_parts,
                                          const std::optional<std::pair<double, double>>& origin) {
    ModuleMatingJudgement out;
    std::vector<std::pair<const ModuleMate*, std::vector<SomPad>>> placed;
    for (const auto& mate : mates) {
        MateConnectorJudgement judged;
        judged.connector = mate.connector;
        judged.ref = mate.ref;
        judged.pins = mate.receptacle.size();
        for (auto& finding : module_row_consistency(mate, &judged.row_inset)) judged.findings.push_back(std::move(finding));
        const auto found = mating_parts.find(mate.connector);
        if (found == mating_parts.end() || !found->second) {
            judged.findings.push_back({"", "no board part mates with this module connector"});
        } else if (!found->second->mod) {
            judged.findings.push_back({"", found->second->ref + " has no footprint"});
        } else if (found->second->side != "top" || found->second->mirror) {
            judged.findings.push_back({"", found->second->ref + " is not on the top face facing the module"});
        } else {
            judged.ref = found->second->ref;
            placed.emplace_back(&mate, posed_footprint_pads(*found->second->mod, found->second->x, found->second->y,
                                                            found->second->rotation));
        }
        out.connectors.push_back(std::move(judged));
    }
    if (origin) {
        out.origin = *origin;
    } else {
        double sx = 0.0, sy = 0.0;
        std::size_t count = 0;
        for (const auto& [mate, pads] : placed) {
            const auto board_pads = by_pin(pads);
            for (const auto& pad : mate->mate) {
                const auto hit = board_pads.find(pad.pin);
                if (hit == board_pads.end()) continue;
                sx += hit->second->x - pad.x;
                sy += hit->second->y - pad.y;
                ++count;
            }
        }
        if (count) out.origin = {sx / static_cast<double>(count), sy / static_cast<double>(count)};
    }
    for (const auto& entry : placed) {
        const ModuleMate* mate = entry.first;
        const auto& pads = entry.second;
        auto& judged = *std::find_if(out.connectors.begin(), out.connectors.end(),
                                     [&](const auto& c) { return c.connector == mate->connector; });
        const auto board_pads = by_pin(pads);
        for (const auto& pad : mate->mate) {
            const auto hit = board_pads.find(pad.pin);
            if (hit == board_pads.end()) {
                judged.findings.push_back({pad.pin, judged.ref + " has no pad of this number"});
                continue;
            }
            const double error = std::hypot(hit->second->x - out.origin.first - pad.x, hit->second->y - out.origin.second - pad.y);
            judged.worst_pad_error = std::max(judged.worst_pad_error, error);
            if (error > mate_quantum.value)
                judged.findings.push_back({pad.pin, judged.ref + " pad is " + millimetres(error) + " from the module's mate pad of the same number"});
        }
    }
    return out;
}

}
