#include "schgen/emit.hpp"

#include <stdexcept>

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

std::vector<std::string> split_ws(const std::string& text) {
    std::vector<std::string> out;
    std::string cur;
    for (char ch : text) {
        if (ch == ' ' || ch == '\t' || ch == '\n') {
            if (!cur.empty()) {
                out.push_back(cur);
                cur.clear();
            }
        } else {
            cur.push_back(ch);
        }
    }
    if (!cur.empty()) {
        out.push_back(cur);
    }
    return out;
}

Sexpr justify_node(const std::string& justify) {
    SexprList node{S("justify")};
    for (const auto& tok : split_ws(justify)) {
        node.push_back(Sexpr{Sexpr::Sym{tok}});
    }
    return Sexpr{std::move(node)};
}

Sexpr pts_node(const std::vector<std::pair<double, double>>& corners) {
    SexprList pts{S("pts")};
    for (const auto& p : corners) {
        pts.push_back(L({S("xy"), N(p.first), N(p.second)}));
    }
    return Sexpr{std::move(pts)};
}

}  // namespace

Sexpr emit_via(double x, double y, double size, double drill, double net,
               const std::string& uuid, bool locked) {
    SexprList node{
        S("via"),
        L({S("at"), N(x), N(y)}),
        L({S("size"), N(size)}),
        L({S("drill"), N(drill)}),
        L({S("layers"), T("F.Cu"), T("B.Cu")}),
    };
    if (locked) {
        node.push_back(L({S("locked"), S("yes")}));
    }
    node.push_back(L({S("net"), N(net)}));
    node.push_back(L({S("uuid"), T(uuid)}));
    return Sexpr{std::move(node)};
}

Sexpr emit_segment(double x1, double y1, double x2, double y2, double width,
                   const std::string& layer, double net,
                   const std::string& uuid) {
    return L({
        S("segment"),
        L({S("start"), N(x1), N(y1)}),
        L({S("end"), N(x2), N(y2)}),
        L({S("width"), N(width)}),
        L({S("layer"), T(layer)}),
        L({S("locked"), S("yes")}),
        L({S("net"), N(net)}),
        L({S("uuid"), T(uuid)}),
    });
}

Sexpr emit_gr_line(double ax, double ay, double bx, double by, double width,
                   const std::string& layer, const std::string& uuid) {
    return L({
        S("gr_line"),
        L({S("start"), N(ax), N(ay)}),
        L({S("end"), N(bx), N(by)}),
        L({S("stroke"), L({S("width"), N(width)}), L({S("type"), S("default")})}),
        L({S("layer"), T(layer)}),
        L({S("uuid"), T(uuid)}),
    });
}

Sexpr emit_edge_line(double ax, double ay, double bx, double by,
                     const std::string& uuid) {
    return emit_gr_line(ax, ay, bx, by, 0.1, "Edge.Cuts", uuid);
}

Sexpr emit_gr_text(const std::string& text, double x, double y, double rot,
                   const std::string& layer, const std::string& uuid,
                   double font_size, double thickness,
                   const std::string& justify) {
    SexprList effects{
        S("effects"),
        L({S("font"), L({S("size"), N(font_size), N(font_size)}),
           L({S("thickness"), N(thickness)})}),
    };
    if (!justify.empty()) {
        effects.push_back(justify_node(justify));
    }
    return L({
        S("gr_text"),
        T(text),
        L({S("at"), N(x), N(y), N(rot)}),
        L({S("layer"), T(layer)}),
        L({S("uuid"), T(uuid)}),
        Sexpr{std::move(effects)},
    });
}

Sexpr emit_fill_zone(double net, const std::string& net_name,
                     const std::string& zname, const std::string& layer,
                     const std::vector<std::pair<double, double>>& corners,
                     const std::string& uuid, double clearance, bool solid,
                     double min_thickness) {
    if (corners.size() < 3) {
        throw std::runtime_error("emit_fill_zone: polygon needs 3 points");
    }
    Sexpr connect = solid
        ? L({S("connect_pads"), S("yes"),
             L({S("clearance"), N(clearance)})})
        : L({S("connect_pads"), L({S("clearance"), N(clearance)})});
    return L({
        S("zone"),
        L({S("net"), N(net)}),
        L({S("net_name"), T(net_name)}),
        L({S("layer"), T(layer)}),
        L({S("uuid"), T(uuid)}),
        L({S("name"), T(zname)}),
        L({S("hatch"), S("edge"), N(0.5)}),
        connect,
        L({S("min_thickness"), N(min_thickness)}),
        L({S("filled_areas_thickness"), S("no")}),
        L({S("fill"), S("yes"), L({S("thermal_gap"), N(0.5)}),
           L({S("thermal_bridge_width"), N(0.5)})}),
        L({S("polygon"), pts_node(corners)}),
    });
}

Sexpr emit_keepout_zone(const std::vector<std::pair<double, double>>& corners,
                        const std::string& uuid, const std::string& name) {
    if (corners.size() < 3) {
        throw std::runtime_error("emit_keepout_zone: polygon needs 3 points");
    }
    return L({
        S("zone"),
        L({S("net"), N(0)}),
        L({S("net_name"), T("")}),
        L({S("layers"), T("F.Cu"), T("B.Cu")}),
        L({S("uuid"), T(uuid)}),
        L({S("name"), T(name)}),
        L({S("hatch"), S("edge"), N(0.5)}),
        L({S("connect_pads"), L({S("clearance"), N(0)})}),
        L({S("min_thickness"), N(0.25)}),
        L({S("keepout"),
           L({S("tracks"), S("allowed")}),
           L({S("vias"), S("allowed")}),
           L({S("pads"), S("allowed")}),
           L({S("copperpour"), S("allowed")}),
           L({S("footprints"), S("allowed")})}),
        L({S("fill"), L({S("thermal_gap"), N(0.5)}),
           L({S("thermal_bridge_width"), N(0.5)})}),
        L({S("polygon"), pts_node(corners)}),
    });
}

Sexpr emit_effects(double size, bool hide, const std::string& justify) {
    SexprList e{S("effects"), L({S("font"), L({S("size"), N(size), N(size)})})};
    if (!justify.empty()) {
        e.push_back(justify_node(justify));
    }
    if (hide) {
        e.push_back(L({S("hide"), S("yes")}));
    }
    return Sexpr{std::move(e)};
}

Sexpr emit_property(const std::string& name, const std::string& value,
                    double x, double y, double rot, bool hide) {
    return L({
        S("property"),
        T(name),
        T(value),
        L({S("at"), N(x), N(y), N(rot)}),
        emit_effects(1.27, hide, ""),
    });
}

Sexpr emit_sch_label(const std::string& tag, const std::string& name,
                     const std::string& shape, double x, double y, double rot,
                     const std::string& justify, const std::string& uuid) {
    SexprList node{Sexpr{Sexpr::Sym{tag}}, T(name)};
    if (!shape.empty()) {
        node.push_back(L({S("shape"), Sexpr{Sexpr::Sym{shape}}}));
    }
    node.push_back(L({S("at"), N(x), N(y), N(rot)}));
    node.push_back(emit_effects(1.27, false, justify));
    node.push_back(L({S("uuid"), T(uuid)}));
    return Sexpr{std::move(node)};
}

Sexpr emit_wire(double x0, double y0, double x1, double y1,
                const std::string& uuid) {
    return L({
        S("wire"),
        L({S("pts"), L({S("xy"), N(x0), N(y0)}), L({S("xy"), N(x1), N(y1)})}),
        L({S("stroke"), L({S("width"), N(0)}), L({S("type"), S("default")})}),
        L({S("uuid"), T(uuid)}),
    });
}

Sexpr emit_junction(double x, double y, const std::string& uuid) {
    return L({
        S("junction"),
        L({S("at"), N(x), N(y)}),
        L({S("diameter"), N(0)}),
        L({S("color"), N(0), N(0), N(0), N(0)}),
        L({S("uuid"), T(uuid)}),
    });
}

Sexpr emit_no_connect(double x, double y, const std::string& uuid) {
    return L({
        S("no_connect"),
        L({S("at"), N(x), N(y)}),
        L({S("uuid"), T(uuid)}),
    });
}

}  // namespace schgen
