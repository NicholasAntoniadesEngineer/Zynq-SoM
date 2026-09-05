#pragma once

#include "schgen/sexpr.hpp"

#include <string>
#include <vector>

namespace schgen {

Sexpr emit_via(double x, double y, double size, double drill, double net,
               const std::string& uuid, bool locked);
Sexpr emit_segment(double x1, double y1, double x2, double y2, double width,
                   const std::string& layer, double net,
                   const std::string& uuid);
Sexpr emit_edge_line(double ax, double ay, double bx, double by,
                     const std::string& uuid);
Sexpr emit_wire(double x0, double y0, double x1, double y1,
                const std::string& uuid);
Sexpr emit_junction(double x, double y, const std::string& uuid);
Sexpr emit_no_connect(double x, double y, const std::string& uuid);

}  // namespace schgen
