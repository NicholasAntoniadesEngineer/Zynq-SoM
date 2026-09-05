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

Sexpr emit_iso_void_zone(const std::vector<std::pair<double, double>>& corners,
                         const std::string& uuid, const std::string& name,
                         const std::string& layer, double min_thickness) {
    if (corners.size() < 3) {
        throw std::runtime_error("emit_iso_void_zone: polygon needs 3 points");
    }
    return L({
        S("zone"),
        L({S("net"), N(0)}),
        L({S("net_name"), T("")}),
        L({S("layers"), T(layer)}),
        L({S("uuid"), T(uuid)}),
        L({S("name"), T(name)}),
        L({S("hatch"), S("edge"), N(0.5)}),
        L({S("connect_pads"), L({S("clearance"), N(0)})}),
        L({S("min_thickness"), N(min_thickness)}),
        L({S("keepout"),
           L({S("tracks"), S("allowed")}),
           L({S("vias"), S("allowed")}),
           L({S("pads"), S("allowed")}),
           L({S("copperpour"), S("not_allowed")}),
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

Sexpr emit_sheet(double x, double y, double w, double h,
                 const std::string& uuid, const std::string& name,
                 const std::string& file, const std::string& inst_project,
                 const std::string& path, const std::string& page,
                 const std::vector<SheetPin>& pins) {
    SexprList node{
        S("sheet"),
        L({S("at"), N(x), N(y)}),
        L({S("size"), N(w), N(h)}),
        L({S("exclude_from_sim"), S("no")}),
        L({S("in_bom"), S("yes")}),
        L({S("on_board"), S("yes")}),
        L({S("dnp"), S("no")}),
        L({S("fields_autoplaced"), S("yes")}),
        L({S("stroke"), L({S("width"), N(0.1524)}), L({S("type"), S("solid")})}),
        L({S("fill"), L({S("color"), N(0), N(0), N(0), N(0.0)})}),
        L({S("uuid"), T(uuid)}),
        L({S("property"), T("Sheetname"), T(name),
           L({S("at"), N(x), N(y - 0.7116), N(0)}),
           emit_effects(1.27, false, "left bottom")}),
        L({S("property"), T("Sheetfile"), T(file),
           L({S("at"), N(x), N(y + h + 0.5846), N(0)}),
           emit_effects(1.27, false, "left top")}),
    };
    for (const auto& pin : pins) {
        node.push_back(L({
            S("pin"),
            T(pin.name),
            Sexpr{Sexpr::Sym{pin.shape}},
            L({S("at"), N(pin.x), N(pin.y), N(pin.rot)}),
            emit_effects(1.27, false, pin.justify),
            L({S("uuid"), T(pin.uuid)}),
        }));
    }
    node.push_back(L({
        S("instances"),
        L({S("project"), T(inst_project),
           L({S("path"), T(path), L({S("page"), T(page)})})}),
    }));
    return Sexpr{std::move(node)};
}

Sexpr emit_symbol(const std::string& lib_id, double x, double y, double rot,
                  const std::string& uuid, const std::string& ref,
                  double ref_x, double ref_y, double ref_rot, bool hide_ref,
                  const std::string& value, double val_x, double val_y,
                  double val_rot, bool hide_val, const std::string& footprint,
                  const std::vector<std::pair<std::string, std::string>>&
                      extra_fields,
                  const std::vector<std::pair<std::string, std::string>>& pins,
                  const std::string& inst_project,
                  const std::string& inst_path) {
    SexprList node{
        S("symbol"),
        L({S("lib_id"), T(lib_id)}),
        L({S("at"), N(x), N(y), N(rot)}),
        L({S("unit"), N(1)}),
        L({S("exclude_from_sim"), S("no")}),
        L({S("in_bom"), S("yes")}),
        L({S("on_board"), S("yes")}),
        L({S("dnp"), S("no")}),
        L({S("uuid"), T(uuid)}),
        emit_property("Reference", ref, ref_x, ref_y, ref_rot, hide_ref),
        emit_property("Value", value, val_x, val_y, val_rot, hide_val),
        emit_property("Footprint", footprint, x, y, 0.0, true),
    };
    for (const auto& field : extra_fields) {
        node.push_back(emit_property(field.first, field.second, x, y, 0.0,
                                     true));
    }
    for (const auto& pin : pins) {
        node.push_back(L({S("pin"), T(pin.first),
                          L({S("uuid"), T(pin.second)})}));
    }
    node.push_back(L({
        S("instances"),
        L({S("project"), T(inst_project),
           L({S("path"), T(inst_path), L({S("reference"), T(ref)}),
              L({S("unit"), N(1)})})}),
    }));
    return Sexpr{std::move(node)};
}

std::string flip_layer_token(const std::string& name) {
    if (name.size() >= 2 && name[0] == 'F' && name[1] == '.') {
        return "B." + name.substr(2);
    }
    if (name.size() >= 2 && name[0] == 'B' && name[1] == '.') {
        return name;
    }
    return name;
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

Sexpr emit_layers_node() {
    struct Layer {
        int idx;
        const char* name;
        const char* ltype;
        const char* user;
    };
    const Layer layers[] = {
        {0, "F.Cu", "signal", "L1 (Sig)"},
        {1, "In1.Cu", "power", "L2 (GND)"},
        {2, "In2.Cu", "power", "L3 (PWR)"},
        {31, "B.Cu", "signal", "L4 (Sig)"},
        {32, "B.Adhes", "user", "B.Adhesive"},
        {33, "F.Adhes", "user", "F.Adhesive"},
        {34, "B.Paste", "user", nullptr},
        {35, "F.Paste", "user", nullptr},
        {36, "B.SilkS", "user", "B.Silkscreen"},
        {37, "F.SilkS", "user", "F.Silkscreen"},
        {38, "B.Mask", "user", nullptr},
        {39, "F.Mask", "user", nullptr},
        {40, "Dwgs.User", "user", "User.Drawings"},
        {41, "Cmts.User", "user", "User.Comments"},
        {42, "Eco1.User", "user", "User.Eco1"},
        {43, "Eco2.User", "user", "User.Eco2"},
        {44, "Edge.Cuts", "user", nullptr},
        {45, "Margin", "user", nullptr},
        {46, "B.CrtYd", "user", "B.Courtyard"},
        {47, "F.CrtYd", "user", "F.Courtyard"},
        {48, "B.Fab", "user", nullptr},
        {49, "F.Fab", "user", nullptr},
    };
    SexprList node{S("layers")};
    for (const Layer& layer : layers) {
        SexprList entry{N(static_cast<double>(layer.idx)), T(layer.name),
                        S(layer.ltype)};
        if (layer.user != nullptr) {
            entry.push_back(T(layer.user));
        }
        node.push_back(Sexpr{std::move(entry)});
    }
    return Sexpr{std::move(node)};
}

Sexpr emit_stackup_node() {
    auto cu = [](const char* name, double th) {
        return L({S("layer"), T(name), L({S("type"), T("copper")}),
                  L({S("thickness"), N(th)})});
    };
    auto diel = [](const char* name, const char* dtype, double th, double er) {
        return L({S("layer"), T(name), L({S("type"), T(dtype)}),
                  L({S("thickness"), N(th)}), L({S("material"), T("FR4")}),
                  L({S("epsilon_r"), N(er)}), L({S("loss_tangent"), N(0.02)})});
    };
    return L({
        S("stackup"),
        L({S("layer"), T("F.SilkS"), L({S("type"), T("Top Silk Screen")})}),
        L({S("layer"), T("F.Paste"), L({S("type"), T("Top Solder Paste")})}),
        L({S("layer"), T("F.Mask"), L({S("type"), T("Top Solder Mask")}),
           L({S("thickness"), N(0.01)})}),
        cu("F.Cu", 0.035),
        diel("dielectric 1", "prepreg", 0.2104, 4.6),
        cu("In1.Cu", 0.0152),
        diel("dielectric 2", "core", 1.065, 4.6),
        cu("In2.Cu", 0.0152),
        diel("dielectric 3", "prepreg", 0.2104, 4.6),
        cu("B.Cu", 0.035),
        L({S("layer"), T("B.Mask"), L({S("type"), T("Bottom Solder Mask")}),
           L({S("thickness"), N(0.01)})}),
        L({S("layer"), T("B.Paste"), L({S("type"), T("Bottom Solder Paste")})}),
        L({S("layer"), T("B.SilkS"), L({S("type"), T("Bottom Silk Screen")})}),
        L({S("copper_finish"), T("ENIG")}),
        L({S("dielectric_constraints"), S("no")}),
    });
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
