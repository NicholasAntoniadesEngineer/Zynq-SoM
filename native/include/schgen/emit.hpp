#pragma once

#include "schgen/sexpr.hpp"

#include <string>
#include <utility>
#include <vector>

namespace schgen {

Sexpr emit_via(double x, double y, double size, double drill, double net,
               const std::string& uuid, bool locked);
Sexpr emit_segment(double x1, double y1, double x2, double y2, double width,
                   const std::string& layer, double net,
                   const std::string& uuid);
Sexpr emit_gr_line(double ax, double ay, double bx, double by, double width,
                   const std::string& layer, const std::string& uuid);
Sexpr emit_edge_line(double ax, double ay, double bx, double by,
                     const std::string& uuid);
Sexpr emit_gr_text(const std::string& text, double x, double y, double rot,
                   const std::string& layer, const std::string& uuid,
                   double font_size, double thickness,
                   const std::string& justify);
Sexpr emit_fill_zone(double net, const std::string& net_name,
                     const std::string& zname, const std::string& layer,
                     const std::vector<std::pair<double, double>>& corners,
                     const std::string& uuid, double clearance, bool solid,
                     double min_thickness);
Sexpr emit_keepout_zone(const std::vector<std::pair<double, double>>& corners,
                        const std::string& uuid, const std::string& name);
Sexpr emit_effects(double size, bool hide, const std::string& justify);
Sexpr emit_property(const std::string& name, const std::string& value,
                    double x, double y, double rot, bool hide);
Sexpr emit_sch_label(const std::string& tag, const std::string& name,
                     const std::string& shape, double x, double y, double rot,
                     const std::string& justify, const std::string& uuid);
Sexpr emit_wire(double x0, double y0, double x1, double y1,
                const std::string& uuid);
Sexpr emit_junction(double x, double y, const std::string& uuid);
Sexpr emit_no_connect(double x, double y, const std::string& uuid);

}  // namespace schgen
