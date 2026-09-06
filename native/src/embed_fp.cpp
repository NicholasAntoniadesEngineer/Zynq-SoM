#include "schgen/embed_fp.hpp"

#include "schgen/emit.hpp"
#include "schgen/occupancy.hpp"
#include "schgen/turn.hpp"

#include <cstddef>
#include <cstdint>
#include <functional>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace schgen {
namespace {

Sexpr S(const char* name) {
    return Sexpr{Sexpr::Sym{name}};
}

Sexpr N(double value) {
    return Sexpr{value};
}

Sexpr T(const std::string& text) {
    return Sexpr{text};
}

Sexpr L(std::vector<Sexpr> items) {
    return Sexpr{std::move(items)};
}

bool is_sym(const Sexpr& node, const char* name) {
    return std::holds_alternative<Sexpr::Sym>(node.v)
        && std::get<Sexpr::Sym>(node.v).name == name;
}

bool is_tagged_list(const Sexpr& node, const char* name) {
    if (!std::holds_alternative<SexprList>(node.v)) {
        return false;
    }
    const SexprList& lst = std::get<SexprList>(node.v);
    return !lst.empty() && is_sym(lst[0], name);
}

const SexprList* find_tagged_child(const SexprList& node, const char* tag) {
    for (const Sexpr& child : node) {
        if (!std::holds_alternative<SexprList>(child.v)) {
            continue;
        }
        const SexprList& lst = std::get<SexprList>(child.v);
        if (!lst.empty() && is_sym(lst[0], tag)) {
            return &lst;
        }
    }
    return nullptr;
}

double require_number(const Sexpr& node, const char* where) {
    if (!std::holds_alternative<double>(node.v)) {
        throw std::runtime_error(std::string(where) + ": number required");
    }
    return std::get<double>(node.v);
}

Sexpr make_at_node(double instance_x, double instance_y,
                   double instance_rotation) {
    SexprList at_node{S("at"), N(instance_x), N(instance_y)};
    // Python: `+ ([inst.rotation] if inst.rotation else [])` — 0.0 / -0.0
    // omitted; any other value (including NaN) is kept.
    if (instance_rotation != 0.0) {
        at_node.push_back(N(instance_rotation));
    }
    return Sexpr{std::move(at_node)};
}

void insert_at(SexprList& out, std::size_t index, Sexpr node) {
    if (index >= out.size()) {
        out.push_back(std::move(node));
        return;
    }
    out.insert(out.begin() + static_cast<std::ptrdiff_t>(index),
               std::move(node));
}

}  // namespace

Sexpr embed_footprint_body(Sexpr footprint_tree, double instance_x,
                           double instance_y, double instance_rotation,
                           const std::string& instance_side,
                           const std::string& footprint_uuid) {
    if (!std::holds_alternative<SexprList>(footprint_tree.v)) {
        throw std::runtime_error("embed_footprint_body: footprint list required");
    }
    SexprList& src = std::get<SexprList>(footprint_tree.v);
    if (src.empty() || !is_sym(src[0], "footprint")) {
        throw std::runtime_error("embed_footprint_body: footprint list required");
    }

    SexprList body;
    body.reserve(src.size());
    for (Sexpr& child : src) {
        if (is_tagged_list(child, "at")) {
            continue;
        }
        body.push_back(std::move(child));
    }

    Sexpr at_node = make_at_node(instance_x, instance_y, instance_rotation);
    SexprList assembled;
    assembled.reserve(body.size() + 1);
    bool inserted = false;
    for (Sexpr& child : body) {
        const bool insert_after =
            !inserted && is_tagged_list(child, "layer");
        assembled.push_back(std::move(child));
        if (insert_after) {
            assembled.push_back(std::move(at_node));
            inserted = true;
        }
    }
    if (!inserted) {
        insert_at(assembled, 1, std::move(at_node));
    }

    Sexpr tree{std::move(assembled)};
    if (instance_side == "bottom") {
        flip_to_bottom(tree);
    }
    set_or_add(tree, L({S("uuid"), T(footprint_uuid)}));
    return tree;
}

std::optional<PadGeom> pad_geom(const Sexpr& pad_node) {
    if (!std::holds_alternative<SexprList>(pad_node.v)) {
        throw std::runtime_error("pad_geom: pad list required");
    }
    const SexprList& node = std::get<SexprList>(pad_node.v);
    const SexprList* at = find_tagged_child(node, "at");
    const SexprList* size = find_tagged_child(node, "size");
    if (at == nullptr || at->size() < 3 || size == nullptr
        || size->size() < 3) {
        return std::nullopt;
    }
    const double at_x = require_number((*at)[1], "pad_geom at x");
    const double at_y = require_number((*at)[2], "pad_geom at y");
    const double size_w = require_number((*size)[1], "pad_geom size w");
    const double size_h = require_number((*size)[2], "pad_geom size h");
    // pad_half_size: at[3] only if it is a number; else 0.0.
    const double pad_deg =
        (at->size() > 3 && std::holds_alternative<double>((*at)[3].v))
            ? std::get<double>((*at)[3].v)
            : 0.0;
    const auto half = pad_half_extent(size_w, size_h, pad_deg);
    return PadGeom{at_x, at_y, half.first, half.second};
}

std::pair<double, double> beside_offset(
    double courtyard_hx, double courtyard_hy, const Box4& target,
    const std::string& direction, double gap,
    const std::optional<double>& along_center) {
    const double target_center_x = (target.x0 + target.x1) / 2.0;
    const double target_center_y = (target.y0 + target.y1) / 2.0;
    double offset_x = 0.0;
    double offset_y = 0.0;
    if (direction == "L") {
        offset_x = target.x0 - gap - courtyard_hx;
        offset_y = along_center.has_value() ? *along_center : target_center_y;
    } else if (direction == "R") {
        offset_x = target.x1 + gap + courtyard_hx;
        offset_y = along_center.has_value() ? *along_center : target_center_y;
    } else if (direction == "U") {
        offset_y = target.y0 - gap - courtyard_hy;
        offset_x = along_center.has_value() ? *along_center : target_center_x;
    } else {
        offset_y = target.y1 + gap + courtyard_hy;
        offset_x = along_center.has_value() ? *along_center : target_center_x;
    }
    return {py_round(offset_x, 4), py_round(offset_y, 4)};
}

namespace {

std::string py_str(const Sexpr& node) {
    if (std::holds_alternative<std::string>(node.v)) {
        return std::get<std::string>(node.v);
    }
    if (std::holds_alternative<Sexpr::Sym>(node.v)) {
        return std::get<Sexpr::Sym>(node.v).name;
    }
    if (std::holds_alternative<double>(node.v)) {
        const double value = std::get<double>(node.v);
        const auto as_int = static_cast<std::int64_t>(value);
        if (static_cast<double>(as_int) == value) {
            return std::to_string(as_int);
        }
        return sexpr_fmt_num(value);
    }
    if (std::holds_alternative<bool>(node.v)) {
        return std::get<bool>(node.v) ? "True" : "False";
    }
    throw std::runtime_error("embed_footprint_decorate: cannot stringify");
}

void hide_reference_property(SexprList& prop) {
    for (Sexpr& child : prop) {
        if (!is_tagged_list(child, "hide")) {
            continue;
        }
        SexprList& hide = std::get<SexprList>(child.v);
        if (hide.size() < 2) {
            hide.push_back(S("yes"));
        } else {
            hide[1] = S("yes");
        }
        return;
    }
    insert_at(prop, 3, L({S("hide"), S("yes")}));
}

void rotate_pad_node(SexprList& pad, double footprint_rotation) {
    for (Sexpr& child : pad) {
        if (!is_tagged_list(child, "at")) {
            continue;
        }
        SexprList& at = std::get<SexprList>(child.v);
        const double current =
            (at.size() > 3 && std::holds_alternative<double>(at[3].v))
                ? std::get<double>(at[3].v)
                : 0.0;
        const double next = rotate_pad_angle(current, footprint_rotation);
        if (at.size() > 3) {
            at[3] = N(next);
        } else {
            at.push_back(N(next));
        }
        return;
    }
}

bool is_gfx_head(const Sexpr& head) {
    return is_sym(head, "fp_text") || is_sym(head, "fp_line")
        || is_sym(head, "fp_rect") || is_sym(head, "fp_circle")
        || is_sym(head, "fp_arc") || is_sym(head, "fp_poly");
}

}  // namespace

Sexpr embed_footprint_decorate(
    Sexpr footprint_tree, const std::string& instance_ref,
    const std::string& instance_value, double instance_rotation,
    bool hide_reference,
    const std::unordered_map<std::string, std::pair<int, std::string>>&
        pad_nets,
    const std::unordered_map<int, std::pair<int, std::string>>& inherit,
    const std::function<std::string(const std::string&)>& uid) {
    if (!std::holds_alternative<SexprList>(footprint_tree.v)) {
        throw std::runtime_error(
            "embed_footprint_decorate: footprint list required");
    }
    if (!uid) {
        throw std::runtime_error("embed_footprint_decorate: uid required");
    }
    SexprList& out = std::get<SexprList>(footprint_tree.v);
    int pad_seq = 0;
    int prop_seq = 0;
    for (Sexpr& node : out) {
        if (!std::holds_alternative<SexprList>(node.v)) {
            continue;
        }
        SexprList& lst = std::get<SexprList>(node.v);
        if (lst.empty()) {
            continue;
        }
        if (is_sym(lst[0], "property") && lst.size() > 2) {
            const std::string name = py_str(lst[1]);
            if (name == "Reference") {
                lst[2] = T(instance_ref);
                if (hide_reference) {
                    hide_reference_property(lst);
                }
            } else if (name == "Value") {
                lst[2] = T(instance_value);
            }
            restamp_uuid(node, uid("fp:" + instance_ref + ":prop:"
                                  + std::to_string(prop_seq)));
            ++prop_seq;
        } else if (is_sym(lst[0], "pad") && lst.size() > 1) {
            const std::string pad_name = py_str(lst[1]);
            int num = 0;
            std::string nname;
            auto found = pad_nets.find(pad_name);
            if (found != pad_nets.end()) {
                num = found->second.first;
                nname = found->second.second;
            }
            if (num == 0 && nname.empty()) {
                auto inherited = inherit.find(pad_seq);
                if (inherited != inherit.end()) {
                    num = inherited->second.first;
                    nname = inherited->second.second;
                }
            }
            set_pad_net(node, num, nname);
            if (instance_rotation != 0.0) {
                rotate_pad_node(lst, instance_rotation);
            }
            restamp_uuid(node, uid("fp:" + instance_ref + ":pad:"
                                  + std::to_string(pad_seq)));
            ++pad_seq;
        } else if (is_gfx_head(lst[0])) {
            restamp_uuid(node, uid("fp:" + instance_ref + ":gfx:"
                                  + std::to_string(pad_seq) + ":"
                                  + std::to_string(prop_seq)));
        }
    }
    return footprint_tree;
}

}  // namespace schgen
