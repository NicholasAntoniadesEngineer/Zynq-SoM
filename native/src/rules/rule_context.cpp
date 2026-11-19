#include "schgen/roles.hpp"
#include "schgen/rules.hpp"

#include "schgen/pack.hpp"
#include "schgen/seat.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <limits>

namespace schgen::rules {
namespace {

const char* const capacitor_class = "C";
const char* const inductor_class = "L";
const char* const connector_class = "J";
const std::array<std::string_view, 3> input_heads{"VIN", "PVIN", "IN"};

bool input_name(const std::string& name) {
    std::string upper = name;
    std::transform(upper.begin(), upper.end(), upper.begin(), [](unsigned char letter) { return std::toupper(letter); });
    if (upper == input_heads.back()) return true;
    return std::any_of(input_heads.begin(), input_heads.end() - 1, [&](std::string_view head) {
        return upper.compare(0, head.size(), head) == 0;
    });
}

}

RuleContext::RuleContext(const PcbCheckInput& input, const PcbModel& model, const Stackup& stackup,
                         const layout::AuthoredIntent& intent)
    : input_(input), model_(model), stackup_(stackup), pin_names_(intent.pin_names) {
    const auto& all = parts();
    std::map<std::string, std::size_t> index;
    for (std::size_t part = 0; part < all.size(); ++part) index.emplace(all[part].ref, part);
    const auto refuse = [&](const layout::ServiceInput& service, const std::string& why) {
        unresolved_.emplace_back(service.role, Finding{service.part + " (" + service.sheet + ")", why});
    };
    for (const auto& service : intent.services) {
        const auto member = index.find(service.part);
        if (member == index.end()) {
            refuse(service, "has the authored role " + service.role + " but is not on the board");
            continue;
        }
        if (!placed(member->second)) {
            refuse(service, "has the authored role " + service.role + " but no footprint");
            continue;
        }
        if (input_.geometry_at(member->second).pad_boxes.empty()) {
            refuse(service, "has the authored role " + service.role + " but no pads to measure from");
            continue;
        }
        Service entry{member->second, 0, service.role, {}, {}};
        if (!service.owner.empty()) {
            const auto owner = index.find(service.owner);
            if (owner == index.end() || !placed(owner->second)) {
                refuse(service, "serves " + service.owner + "." + service.pin + ", which is not a placed part");
                continue;
            }
            if (!input_.geometry_at(owner->second).pad_boxes.count(service.pin)) {
                refuse(service, "serves " + service.owner + "." + service.pin + ", but " + service.owner +
                                    " has no pad of that name");
                continue;
            }
            entry.owner = owner->second;
            entry.pin = service.owner + "." + service.pin;
            entry.pads = {service.pin};
            services_.push_back(std::move(entry));
            continue;
        }
        const std::string net = net_at(entry.part, service.via);
        if (net.empty()) {
            refuse(service, "serves the net on its pad " + service.via + ", which carries no net");
            continue;
        }
        double best = std::numeric_limits<double>::max();
        for (std::size_t other = 0; other < all.size(); ++other) {
            const bool eligible = service.to_module ? module_connector(other)
                                                    : all[other].sheet != all[entry.part].sheet &&
                                                          all[other].pad_nets.size() > 2;
            if (other == entry.part || !eligible || !placed(other)) continue;
            std::vector<std::string> pads;
            for (const auto& [pad, bound] : all[other].pad_nets)
                if (bound.second == net && input_.geometry_at(other).pad_boxes.count(pad)) pads.push_back(pad);
            if (pads.empty()) continue;
            const double gap = *pad_gap(other, pads, entry.part);
            if (gap >= best) continue;
            best = gap;
            entry.owner = other;
            entry.pads = std::move(pads);
            entry.pin = all[other].ref + " on " + net;
        }
        if (entry.pads.empty()) {
            refuse(service, "serves net " + net + ", but no " + (service.to_module ? "module connector" : "part on another sheet") +
                                " has a pad on it");
            continue;
        }
        services_.push_back(std::move(entry));
    }
    std::vector<std::size_t> owners;
    for (const auto& service : services_)
        if (role_rule(service.role).marks_regulator && all[service.owner].pad_nets.size() > 2 &&
            std::find(owners.begin(), owners.end(), service.owner) == owners.end())
            owners.push_back(service.owner);
    std::sort(owners.begin(), owners.end());
    const auto nearest_first = [&](std::size_t owner, const std::string& pad, std::vector<std::size_t>& members) {
        std::stable_sort(members.begin(), members.end(), [&](std::size_t first, std::size_t second) {
            return *pad_gap(owner, {pad}, first) < *pad_gap(owner, {pad}, second);
        });
    };
    for (const std::size_t owner : owners) {
        Regulator regulator;
        regulator.part = owner;
        for (const auto& service : services_) {
            if (service.owner != owner) continue;
            regulator.supports.push_back(service.part);
            if (!role_rule(service.role).marks_regulator) continue;
            if (inductor(service.part)) regulator.inductors.push_back(service.part);
            RegulatorOutput output{service.part, {}, {}};
            for (const auto& load : services_) {
                if (load.owner != service.part || !capacitor(load.part)) continue;
                output.pad = load.pads.front();
                output.capacitors.push_back(load.part);
            }
            if (output.capacitors.empty()) continue;
            nearest_first(output.member, output.pad, output.capacitors);
            regulator.outputs.push_back(std::move(output));
        }
        for (const auto& [pad, box] : input_.geometry_at(owner).pad_boxes) {
            const std::string name = pin_name(owner, pad);
            if (!input_name(name)) continue;
            RegulatorInput entry{pad, name, {}};
            for (const auto& service : services_)
                if (service.owner == owner && service.pads.front() == pad && capacitor(service.part) &&
                    role_rule(service.role).loop_capacitor)
                    entry.capacitors.push_back(service.part);
            nearest_first(owner, pad, entry.capacitors);
            regulator.inputs.push_back(std::move(entry));
        }
        regulators_.push_back(std::move(regulator));
    }
}

std::vector<const Service*> RuleContext::serving(const std::vector<std::string_view>& roles) const {
    std::vector<const Service*> found;
    for (const auto& service : services_)
        if (std::find(roles.begin(), roles.end(), service.role) != roles.end()) found.push_back(&service);
    return found;
}

std::vector<Finding> RuleContext::unresolved(const std::vector<std::string_view>& roles) const {
    std::vector<Finding> found;
    for (const auto& [role, finding] : unresolved_)
        if (std::find(roles.begin(), roles.end(), role) != roles.end()) found.push_back(finding);
    return found;
}

bool RuleContext::placed(std::size_t part) const { return parts()[part].mod != nullptr; }

bool RuleContext::rear(std::size_t part) const { return parts()[part].side == "bottom"; }

bool RuleContext::ground_beneath(std::size_t part) const { return stackup_.ground_referenced(rear(part)); }

bool RuleContext::module_connector(std::size_t part) const {
    return pcb_is_df40_part(parts()[part].sheet, static_cast<int>(parts()[part].pad_nets.size()));
}

bool RuleContext::capacitor(std::size_t part) const { return ref_prefix(parts()[part].ref) == capacitor_class; }

bool reads_as_inductor(const std::string& reference) { return ref_prefix(reference) == inductor_class; }

bool RuleContext::inductor(std::size_t part) const { return reads_as_inductor(parts()[part].ref); }

bool RuleContext::connector(std::size_t part) const {
    return ref_prefix(parts()[part].ref) == connector_class && !module_connector(part);
}

std::string RuleContext::label(std::size_t part) const { return parts()[part].ref + " (" + parts()[part].sheet + ")"; }

std::string RuleContext::face(std::size_t part) const { return rear(part) ? "rear" : "top"; }

std::string RuleContext::neighbour(std::size_t part) const {
    const CopperLayer& layer = stackup_.reference_of(rear(part));
    return layer.name + " is a " + copper_role_name(layer.role) + " layer";
}

std::string RuleContext::pin_name(std::size_t part, const std::string& pad) const {
    const auto names = pin_names_.find(parts()[part].ref);
    if (names == pin_names_.end()) return {};
    const auto found = names->second.find(pad);
    return found == names->second.end() ? std::string() : found->second;
}

std::string RuleContext::net_at(std::size_t part, const std::string& pad) const {
    const auto found = parts()[part].pad_nets.find(pad);
    return found == parts()[part].pad_nets.end() ? std::string() : found->second.second;
}

Box4 RuleContext::courtyard(std::size_t part) const { return input_.courtyard_at(part); }

Box4 RuleContext::body(std::size_t part) const {
    const Box4 court = input_.courtyard_at(part), pads = input_.pad_bbox_at(part);
    return {std::min(court.x0, pads.x0), std::min(court.y0, pads.y0), std::max(court.x1, pads.x1),
            std::max(court.y1, pads.y1)};
}

double RuleContext::overlap(std::size_t first, std::size_t second) const {
    const Box4 a = courtyard(first), b = courtyard(second);
    return std::min(std::min(a.x1, b.x1) - std::max(a.x0, b.x0), std::min(a.y1, b.y1) - std::max(a.y0, b.y0));
}

double RuleContext::centre_distance(std::size_t first, std::size_t second) const {
    const Box4 a = courtyard(first), b = courtyard(second);
    return std::hypot((a.x0 + a.x1 - b.x0 - b.x1) / 2, (a.y0 + a.y1 - b.y0 - b.y1) / 2);
}

std::optional<double> RuleContext::pad_gap(std::size_t owner, const std::vector<std::string>& pads,
                                           std::size_t member) const {
    std::optional<double> best;
    const auto& anchors = input_.geometry_at(owner).pad_boxes;
    for (const auto& pad : pads) {
        const auto anchor = anchors.find(pad);
        if (anchor == anchors.end()) continue;
        for (const auto& [name, box] : input_.geometry_at(member).pad_boxes) {
            const double gap = box_gap(anchor->second, box);
            if (!best || gap < *best) best = gap;
        }
    }
    return best;
}

std::optional<double> RuleContext::net_gap(std::size_t owner, const std::vector<std::string>& pads,
                                           std::size_t member, const std::string& net) const {
    std::optional<double> best;
    const auto& anchors = input_.geometry_at(owner).pad_boxes;
    for (const auto& pad : pads) {
        const auto anchor = anchors.find(pad);
        if (anchor == anchors.end()) continue;
        for (const auto& [name, box] : input_.geometry_at(member).pad_boxes) {
            if (net_at(member, name) != net) continue;
            const double gap = box_gap(anchor->second, box);
            if (!best || gap < *best) best = gap;
        }
    }
    return best;
}

}
