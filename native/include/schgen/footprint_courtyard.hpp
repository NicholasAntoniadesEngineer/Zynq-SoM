#pragma once

#include "schgen/json.hpp"
#include "schgen/named_constant.hpp"
#include "schgen/seat.hpp"
#include "schgen/sexpr.hpp"

#include <array>
#include <cstdint>
#include <filesystem>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace schgen::courtyard {

class CourtyardError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

namespace constants {
inline constexpr NamedConstant general_clearance{"general_clearance", 0.25, "mm", "standard",
    "KiCad Library Convention F5.3 item 5 (klc.kicad.org/footprint/f5/f5.3, revision 3.0.60 of 2026-01-30): unless otherwise specified, clearance is 0.25mm"};
inline constexpr NamedConstant small_clearance{"small_clearance", 0.15, "mm", "standard",
    "KiCad Library Convention F5.3 item 5: this shrinks to 0.15mm for parts smaller than 1.5mm in any dimension"};
inline constexpr NamedConstant small_extent{"small_extent", 1.5, "mm", "standard",
    "KiCad Library Convention F5.3 item 5: the size under which the smaller clearance applies; taken as the body's larger side, because the wording it replaced in revision 3.0.60 was parts smaller than 0603"};
inline constexpr NamedConstant connector_clearance{"connector_clearance", 0.5, "mm", "standard",
    "KiCad Library Convention F5.3 item 7: connectors should have a clearance of 0.5mm, in addition to the clearance required for mating"};
inline constexpr NamedConstant canned_clearance{"canned_clearance", 0.5, "mm", "standard",
    "KiCad Library Convention F5.3 item 8: canned capacitors should have a clearance of 0.5mm"};
inline constexpr NamedConstant crystal_clearance{"crystal_clearance", 0.5, "mm", "standard",
    "KiCad Library Convention F5.3 item 9: crystals should have a clearance of 0.5mm"};
inline constexpr NamedConstant array_clearance{"array_clearance", 1.0, "mm", "standard",
    "KiCad Library Convention F5.3 item 10: BGA devices, including WLCSP and similar, should have a clearance of 1.0mm"};
inline constexpr NamedConstant court_stroke{"court_stroke", 0.05, "mm", "standard",
    "KiCad Library Convention F5.3 item 1: courtyard uses 0.05mm line width"};
inline constexpr NamedConstant court_grid{"court_grid", 0.01, "mm", "standard",
    "KiCad Library Convention F5.3 item 2: all courtyard line elements are placed on a 0.01mm grid"};
inline constexpr NamedConstant body_stroke{"body_stroke", 0.1, "mm", "standard",
    "KiCad Library Convention F5.2 item 1 (klc.kicad.org/footprint/f5/f5.2): fabrication outline uses line width between 0.10mm and 0.15mm, recommended 0.10mm"};
inline constexpr NamedConstant extent_quantum{"extent_quantum", 1e-6, "mm", "physical",
    "one nanometre, the resolution of a KiCad board file; extents are snapped to it before the courtyard grid is applied"};
inline constexpr NamedConstant extent_places{"extent_places", 6, "decimal places", "physical",
    "decimal places of one nanometre written in millimetres"};
inline constexpr std::array court_registry{general_clearance, small_clearance, small_extent, connector_clearance,
                                           canned_clearance, crystal_clearance, array_clearance, court_stroke,
                                           court_grid, body_stroke, extent_quantum, extent_places};
}

inline constexpr const char* rule_file = "courtyard_classes.json";
inline constexpr const char* rule_schema = "schgen.courtyard_classes/1";

enum class Kind : std::uint8_t { general, connector, canned_capacitor, crystal, grid_array };

struct PartRule {
    Kind kind = Kind::general;
    std::optional<std::pair<double, double>> body;
};

struct RuleTable {
    std::string source;
    std::map<std::string, PartRule> parts;
    const PartRule& at(const std::string& part) const;
};

struct Edge {
    double x0 = 0, y0 = 0, x1 = 0, y1 = 0;
};

struct Extents {
    std::optional<Box4> court, land, body;
};

std::string kind_name(Kind kind);
RuleTable parse_rules(const JsonNode& root, const std::string& source);
RuleTable load_rules(const std::filesystem::path& file);
double clearance_of(Kind kind, const Box4& body);

Extents measure(const Sexpr& footprint);
std::optional<std::string> defect(const Sexpr& footprint);
void require_sound(const Sexpr& footprint, const std::string& source);

std::vector<Edge> court_edges(const Sexpr& footprint);
Sexpr enclosed(const Sexpr& footprint, const std::vector<Edge>& body, const PartRule& rule, const std::string& part);

std::optional<int> run_part_courtyard_command(int argc, char** argv);

}
