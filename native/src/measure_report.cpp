#include "schgen/measure.hpp"

#include "schgen/json_text.hpp"

#include <algorithm>
#include <iomanip>
#include <limits>
#include <locale>
#include <sstream>

namespace schgen::measure {
namespace {

using json_text::array;
using json_text::names;
using json_text::object;
using json_text::pretty;
using json_text::text_value;

std::string trimmed(std::string text) {
    if (text.find('.') != std::string::npos && text.find('e') == std::string::npos) {
        while (text.back() == '0') text.pop_back();
        if (text.back() == '.') text.pop_back();
    }
    if (text == "-0") text = "0";
    return text;
}

std::string fixed(double value, const Constant& decimals) {
    std::ostringstream out;
    out.imbue(std::locale::classic());
    out << std::fixed << std::setprecision(static_cast<int>(decimals.value)) << value;
    return trimmed(out.str());
}

std::string exact(double value) {
    std::ostringstream out;
    out.imbue(std::locale::classic());
    out << std::setprecision(std::numeric_limits<double>::digits10) << value;
    return out.str();
}

std::string length(double value) { return fixed(value, constants::length_decimals); }

std::string ratio(double value) { return fixed(value, constants::ratio_decimals); }

std::string count(int value) { return std::to_string(value); }

std::string face_name(Face face) { return face == Face::top ? "top" : "bottom"; }

std::string face_json(const FaceMetrics& face) {
    return object({{"parts", count(face.parts)},
                   {"courtyard_mm2", length(face.courtyard)},
                   {"occupied_mm2", length(face.occupied)},
                   {"occupied_clearance_mm2", length(face.occupied_clearance)},
                   {"occupied_fanout_mm2", length(face.occupied_fanout)},
                   {"keepout_mm2", length(face.keepout)},
                   {"usable_mm2", length(face.usable)},
                   {"utilisation", ratio(face.utilisation)},
                   {"utilisation_fanout", ratio(face.utilisation_fanout)}});
}

std::string wire_json(const WireTotals& totals) {
    return object({{"nets", count(totals.nets)},
                   {"connections", count(totals.connections)},
                   {"euclid_mm", length(totals.euclid)},
                   {"manhattan_mm", length(totals.manhattan)},
                   {"cross_euclid_mm", length(totals.cross_euclid)},
                   {"cross_manhattan_mm", length(totals.cross_manhattan)}});
}

std::string options_json(const Options& options) {
    std::vector<std::string> keepouts;
    for (const auto& keepout : options.keepouts)
        keepouts.push_back(object({{"face", text_value(face_name(keepout.face))},
                                   {"zone", text_value(keepout.zone)}}));
    return object({{"keepouts", array(keepouts)},
                   {"power_classes", names(options.power_classes)},
                   {"excluded_groups", names(options.excluded_groups)}});
}

std::string subsystems_json(const SubsystemMetrics& subsystems) {
    std::vector<std::string> groups;
    for (const auto& group : subsystems.groups)
        groups.push_back(object({{"name", text_value(group.name)},
                                 {"parts", count(group.parts)},
                                 {"bottom_parts", count(group.bottom_parts)},
                                 {"courtyard_mm2", length(group.courtyard)},
                                 {"box_width_mm", length(group.box.width())},
                                 {"box_height_mm", length(group.box.height())},
                                 {"box_mm2", length(group.box.area())},
                                 {"box_ratio", ratio(group.box_ratio)},
                                 {"busiest_face_fill", ratio(group.busiest_fill)},
                                 {"excluded", group.excluded ? "true" : "false"}}));
    return object({{"box_total_mm2", length(subsystems.box_total)},
                   {"courtyard_total_mm2", length(subsystems.courtyard_total)},
                   {"box_ratio", ratio(subsystems.box_ratio)},
                   {"median_box_ratio", ratio(subsystems.median_ratio)},
                   {"box_share_of_face", ratio(subsystems.box_share)},
                   {"groups", array(groups)}});
}

std::string airwire_json(const AirwireMetrics& airwire) {
    std::vector<std::string> longest;
    for (const auto& net : airwire.longest)
        longest.push_back(object({{"net", text_value(net.net)},
                                  {"manhattan_mm", length(net.manhattan)},
                                  {"pads", count(net.pads)}}));
    return object({{"plane", wire_json(airwire.plane)},
                   {"power", wire_json(airwire.power)},
                   {"signal", wire_json(airwire.signal)},
                   {"longest_signal", array(longest)}});
}

std::string demand_json(const DemandMetrics& demand) {
    std::vector<std::string> rows;
    for (int row = 0; row < demand.rows; ++row) {
        std::vector<std::string> cells;
        for (int column = 0; column < demand.columns; ++column)
            cells.push_back(ratio(demand.bins[static_cast<std::size_t>(row) *
                                              static_cast<std::size_t>(demand.columns) +
                                              static_cast<std::size_t>(column)]));
        rows.push_back(array(cells));
    }
    return object({{"bin_mm", length(constants::demand_bin.value)},
                   {"columns", count(demand.columns)},
                   {"rows", count(demand.rows)},
                   {"default_pitch_mm", ratio(demand.default_pitch)},
                   {"mean", ratio(demand.mean)},
                   {"peak", ratio(demand.peak)},
                   {"high_quantile", ratio(demand.high)},
                   {"upper_quantile", ratio(demand.upper)},
                   {"median", ratio(demand.median)},
                   {"congested_bins", count(demand.congested)},
                   {"bins", array(rows)}});
}

std::string gaps_json(const std::vector<GapTier>& gaps) {
    std::vector<std::string> rows;
    for (const auto& tier : gaps)
        rows.push_back(object({{"need_mm", length(tier.need)},
                               {"parts", count(tier.parts)},
                               {"below_need", count(tier.below)},
                               {"min_mm", length(tier.minimum)},
                               {"lower_quartile_mm", length(tier.lower)},
                               {"median_mm", length(tier.median)},
                               {"upper_quartile_mm", length(tier.upper)},
                               {"max_mm", length(tier.maximum)}}));
    return array(rows);
}

std::string edges_json(const std::array<EdgeMetrics, edge_count>& edges) {
    std::vector<std::string> rows;
    for (const auto& edge : edges) {
        std::vector<std::string> parts;
        for (const auto& part : edge.parts)
            parts.push_back(object({{"reference", text_value(part.reference)},
                                    {"width_mm", length(part.width)}}));
        rows.push_back(object({{"name", text_value(edge.name)},
                               {"length_mm", length(edge.length)},
                               {"run_mm", length(edge.run)},
                               {"ratio", ratio(edge.ratio)},
                               {"parts", array(parts)}}));
    }
    return array(rows);
}

std::string constants_json() {
    std::vector<std::string> rows;
    for (const auto& entry : constants::registry)
        rows.push_back(object({{"name", text_value(entry.name)},
                               {"value", exact(entry.value)},
                               {"unit", text_value(entry.unit)},
                               {"proof", text_value(entry.proof)},
                               {"basis", text_value(entry.basis)}}));
    return array(rows);
}

std::string exempt_json() {
    std::vector<std::string> rows;
    for (const int value : constants::exempt_literals) rows.push_back(count(value));
    return array(rows);
}

struct Canvas {
    std::ostringstream out;
    double shift_x = 0, shift_y = 0;
    void box(Rect rect, const std::string& paint) {
        if (rect.area() <= 0) return;
        out << "<rect x=\"" << length(rect.x0 + shift_x) << "\" y=\"" << length(rect.y0 + shift_y)
            << "\" width=\"" << length(rect.width()) << "\" height=\"" << length(rect.height())
            << "\" " << paint << "/>\n";
    }
};

Rect limited(Rect rect, Rect limit) {
    return {std::max(rect.x0, limit.x0), std::max(rect.y0, limit.y0),
            std::min(rect.x1, limit.x1), std::min(rect.y1, limit.y1)};
}

std::string stroke(const std::string& colour) {
    return "fill=\"none\" stroke=\"" + colour + "\" stroke-width=\"" +
           length(constants::map_stroke.value) + "\"";
}

std::string fill(const std::string& colour, double opacity) {
    return "fill=\"" + colour + "\" fill-opacity=\"" + ratio(std::min(opacity, 1.0)) + "\"";
}

void draw_face(Canvas& canvas, const Board& board, const Report& report, Face face) {
    for (const auto& part : board.parts) {
        if (part.face == face) {
            canvas.box(limited(part.courtyard, board.outline),
                       fill("#1b7837", constants::part_opacity.value));
            continue;
        }
        for (const auto& pad : part.pads)
            if (pad.through)
                canvas.box(limited({pad.x - pad.reach, pad.y - pad.reach,
                                    pad.x + pad.reach, pad.y + pad.reach}, board.outline),
                           fill("#555555", 1));
    }
    for (const auto& keepout : report.options.keepouts) {
        if (keepout.face != face) continue;
        for (const auto& zone : board.zones)
            if (zone.name == keepout.zone)
                canvas.box(limited(zone.box, board.outline), stroke("#2166ac"));
    }
}

void draw_demand(Canvas& canvas, const Board& board, const Report& report) {
    const double bin = constants::demand_bin.value;
    for (int row = 0; row < report.demand.rows; ++row)
        for (int column = 0; column < report.demand.columns; ++column) {
            const double x = board.outline.x0 + column * bin, y = board.outline.y0 + row * bin;
            const double value = report.demand.bins[static_cast<std::size_t>(row) *
                                                    static_cast<std::size_t>(report.demand.columns) +
                                                    static_cast<std::size_t>(column)];
            canvas.box(limited({x, y, x + bin, y + bin}, board.outline), fill("#d7301f", value));
        }
}

}

std::string report_json(const Report& report, const std::vector<InputIdentity>& inputs) {
    std::vector<std::string> sources;
    for (const auto& input : inputs)
        sources.push_back(object({{"name", text_value(input.name)}, {"sha256", text_value(input.sha256)}}));
    const std::string board = object({{"width_mm", length(report.width)},
                                      {"height_mm", length(report.height)},
                                      {"area_mm2", length(report.area)},
                                      {"signal_layers", count(report.signal_layers)},
                                      {"power_layers", count(report.power_layers)},
                                      {"parts", count(report.parts)},
                                      {"through_hole_parts", count(report.through_parts)},
                                      {"courtyards_from_pads", count(report.pad_courtyards)},
                                      {"without_geometry", names(report.without_geometry)}});
    const std::string bounds = object({{"top_demand_mm2", length(report.bounds.top_demand)},
                                       {"bottom_demand_mm2", length(report.bounds.bottom_demand)},
                                       {"balanced_demand_mm2", length(report.bounds.balanced_demand)},
                                       {"outline_to_balanced", ratio(report.bounds.outline_ratio)},
                                       {"perimeter_run_mm", length(report.bounds.perimeter_run)},
                                       {"perimeter_ratio", ratio(report.bounds.perimeter_ratio)}});
    return pretty(object({{"schema", text_value("schgen.measure/1")},
                          {"inputs", array(sources)},
                          {"options", options_json(report.options)},
                          {"board", board},
                          {"faces", object({{"top", face_json(report.top)},
                                            {"bottom", face_json(report.bottom)}})},
                          {"subsystems", subsystems_json(report.subsystems)},
                          {"airwire", airwire_json(report.airwire)},
                          {"demand", demand_json(report.demand)},
                          {"gaps", gaps_json(report.gaps)},
                          {"edges", edges_json(report.edges)},
                          {"bounds", bounds},
                          {"constants", constants_json()},
                          {"exempt_literals", exempt_json()}}));
}

std::string report_map(const Board& board, const Report& report) {
    struct Panel {
        std::string caption;
        std::optional<Face> face;
    };
    const std::vector<Panel> panels{
        {"top face: " + count(report.top.parts) + " parts, utilisation " +
             ratio(report.top.utilisation_fanout) + " with fan-out halos", Face::top},
        {"bottom face seen from the top: " + count(report.bottom.parts) + " parts, utilisation " +
             ratio(report.bottom.utilisation_fanout) + " with fan-out halos", Face::bottom},
        {"routing demand: mean " + ratio(report.demand.mean) + ", peak " +
             ratio(report.demand.peak) + " of " + count(report.signal_layers) + " signal layers",
         std::nullopt}};
    const double margin = constants::map_margin.value, header = constants::map_header.value;
    const double panel_width = report.width + 2 * margin;
    const double panel_height = report.height + 2 * margin + header;
    const double total_width = panel_width * static_cast<double>(panels.size());
    Canvas canvas;
    canvas.out << "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\""
               << length(total_width * constants::map_scale.value) << "\" height=\""
               << length(panel_height * constants::map_scale.value) << "\" viewBox=\"0 0 "
               << length(total_width) << ' ' << length(panel_height) << "\">\n";
    canvas.box({0, 0, total_width, panel_height}, fill("#ffffff", 1));
    for (std::size_t index = 0; index < panels.size(); ++index) {
        const double left = panel_width * static_cast<double>(index) + margin;
        canvas.out << "<text x=\"" << length(left) << "\" y=\"" << length(header)
                   << "\" font-family=\"sans-serif\" font-size=\"" << length(constants::map_text.value)
                   << "\">" << panels[index].caption << "</text>\n";
        canvas.shift_x = left - board.outline.x0;
        canvas.shift_y = header + margin - board.outline.y0;
        canvas.box(board.outline, fill("#f4f4f4", 1));
        if (panels[index].face) draw_face(canvas, board, report, *panels[index].face);
        else draw_demand(canvas, board, report);
        canvas.box(board.outline, stroke("#222222"));
        canvas.shift_x = canvas.shift_y = 0;
    }
    canvas.out << "</svg>\n";
    return canvas.out.str();
}

}
