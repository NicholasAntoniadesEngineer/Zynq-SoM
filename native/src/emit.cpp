#include "schgen/emit.hpp"

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

Sexpr emit_edge_line(double ax, double ay, double bx, double by,
                     const std::string& uuid) {
    return L({
        S("gr_line"),
        L({S("start"), N(ax), N(ay)}),
        L({S("end"), N(bx), N(by)}),
        L({S("stroke"), L({S("width"), N(0.1)}), L({S("type"), S("default")})}),
        L({S("layer"), T("Edge.Cuts")}),
        L({S("uuid"), T(uuid)}),
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
