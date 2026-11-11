#include "schgen/measure.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <map>
#include <set>

namespace schgen::measure {
namespace {

inline constexpr std::size_t first_field = 1, second_field = 2, third_field = 3;

struct Point {
    double x = 0, y = 0;
};

struct Extent {
    Rect box;
    bool any = false;
    void add(Point point) {
        if (!any) {
            box = {point.x, point.y, point.x, point.y};
            any = true;
            return;
        }
        box.x0 = std::min(box.x0, point.x);
        box.y0 = std::min(box.y0, point.y);
        box.x1 = std::max(box.x1, point.x);
        box.y1 = std::max(box.y1, point.y);
    }
};

const SexprList* as_list(const Sexpr& node) { return std::get_if<SexprList>(&node.v); }

std::string as_text(const Sexpr& node) {
    if (const auto* text = std::get_if<std::string>(&node.v)) return *text;
    if (const auto* symbol = std::get_if<Sexpr::Sym>(&node.v)) return symbol->name;
    if (const auto* value = std::get_if<double>(&node.v)) {
        if (*value == std::floor(*value)) return std::to_string(static_cast<long long>(*value));
        return std::to_string(*value);
    }
    return {};
}

double as_number(const Sexpr& node, const std::string& what) {
    if (const auto* value = std::get_if<double>(&node.v)) return *value;
    throw MeasureError("measure: number required for " + what);
}

bool tagged(const Sexpr& node, std::string_view name) {
    const auto* items = as_list(node);
    return items && !items->empty() && as_text(items->front()) == name;
}

const SexprList* child(const SexprList& items, std::string_view name) {
    for (const auto& item : items)
        if (tagged(item, name)) return as_list(item);
    return nullptr;
}

std::string field_text(const SexprList* items, std::size_t index) {
    return items && items->size() > index ? as_text((*items)[index]) : std::string();
}

bool ends_with(const std::string& text, std::string_view tail) {
    return text.size() >= tail.size() &&
           text.compare(text.size() - tail.size(), tail.size(), tail) == 0;
}

bool starts_with(const std::string& text, std::string_view head) {
    return text.size() >= head.size() && text.compare(0, head.size(), head) == 0;
}

Point point_of(const SexprList& items, const std::string& what) {
    if (items.size() <= second_field)
        throw MeasureError("measure: coordinate pair required for " + what);
    return {as_number(items[first_field], what), as_number(items[second_field], what)};
}

double snapped(double value) {
    const double tolerance = constants::touch_tolerance.value;
    if (std::fabs(value) < tolerance) return 0;
    if (std::fabs(value - 1) < tolerance) return 1;
    if (std::fabs(value + 1) < tolerance) return -1;
    return value;
}

Point turned(Point point, double degrees) {
    const double radians = degrees * constants::half_turn.value / constants::straight_angle.value;
    const double cosine = snapped(std::cos(radians)), sine = snapped(std::sin(radians));
    return {point.x * cosine + point.y * sine, -point.x * sine + point.y * cosine};
}

void corner_points(Point low, Point high, std::vector<Point>& points) {
    points.push_back({low.x, low.y});
    points.push_back({high.x, low.y});
    points.push_back({high.x, high.y});
    points.push_back({low.x, high.y});
}

void graphic_points(const SexprList& item, std::vector<Point>& points) {
    const std::string kind = as_text(item.front());
    if (ends_with(kind, "_circle")) {
        const auto* center = child(item, "center");
        const auto* rim = child(item, "end");
        if (!center || !rim) throw MeasureError("measure: circle needs center and end");
        const Point middle = point_of(*center, "circle center"), edge = point_of(*rim, "circle end");
        const double radius = std::hypot(edge.x - middle.x, edge.y - middle.y);
        corner_points({middle.x - radius, middle.y - radius},
                      {middle.x + radius, middle.y + radius}, points);
        return;
    }
    if (ends_with(kind, "_poly")) {
        const auto* list = child(item, "pts");
        if (!list) throw MeasureError("measure: polygon needs pts");
        for (const auto& node : *list)
            if (tagged(node, "xy")) points.push_back(point_of(*as_list(node), "polygon vertex"));
        return;
    }
    if (ends_with(kind, "_rect")) {
        const auto* start = child(item, "start");
        const auto* end = child(item, "end");
        if (!start || !end) throw MeasureError("measure: rectangle needs start and end");
        corner_points(point_of(*start, "rectangle start"), point_of(*end, "rectangle end"), points);
        return;
    }
    for (const char* name : {"start", "mid", "end"})
        if (const auto* at = child(item, name)) points.push_back(point_of(*at, name));
}

Rect read_outline(const SexprList& root) {
    Extent extent;
    for (const auto& node : root) {
        const auto* item = as_list(node);
        if (!item || item->empty() || !starts_with(as_text(item->front()), "gr_")) continue;
        if (field_text(child(*item, "layer"), first_field) != "Edge.Cuts") continue;
        std::vector<Point> points;
        graphic_points(*item, points);
        for (const auto& point : points) extent.add(point);
    }
    if (!extent.any) throw MeasureError("measure: board has no Edge.Cuts outline");
    return extent.box;
}

std::vector<Layer> read_copper(const SexprList& root) {
    const auto* layers = child(root, "layers");
    if (!layers) throw MeasureError("measure: board has no layer table");
    std::vector<Layer> out;
    for (std::size_t index = first_field; index < layers->size(); ++index) {
        const auto* row = as_list((*layers)[index]);
        const std::string name = field_text(row, first_field);
        if (ends_with(name, ".Cu")) out.push_back({name, field_text(row, second_field)});
    }
    if (out.empty()) throw MeasureError("measure: board has no copper layers");
    return out;
}

std::vector<Zone> read_zones(const SexprList& root) {
    std::vector<Zone> out;
    for (const auto& node : root) {
        if (!tagged(node, "zone")) continue;
        const auto& item = *as_list(node);
        Zone zone;
        zone.name = field_text(child(item, "name"), first_field);
        zone.net = field_text(child(item, "net_name"), first_field);
        for (const char* key : {"layer", "layers"})
            if (const auto* layers = child(item, key))
                for (std::size_t index = first_field; index < layers->size(); ++index)
                    zone.layers.push_back(as_text((*layers)[index]));
        const auto* polygon = child(item, "polygon");
        const auto* list = polygon ? child(*polygon, "pts") : nullptr;
        Extent extent;
        if (list)
            for (const auto& vertex : *list)
                if (tagged(vertex, "xy")) extent.add(point_of(*as_list(vertex), "zone vertex"));
        if (!extent.any) continue;
        zone.box = extent.box;
        out.push_back(std::move(zone));
    }
    return out;
}

std::map<long long, std::string> read_groups(const JsonNode& sheet_index) {
    if (sheet_index.kind != JsonKind::Object)
        throw MeasureError("measure: sheet index must be an object");
    std::map<long long, std::string> out;
    for (const auto& [name, value] : sheet_index.object_value) {
        if (value.kind != JsonKind::Number)
            throw MeasureError("measure: sheet index of " + name + " must be a number");
        if (!out.emplace(static_cast<long long>(value.number_value), name).second)
            throw MeasureError("measure: duplicate sheet index for " + name);
    }
    return out;
}

std::string group_of(const std::string& reference, const std::map<long long, std::string>& groups) {
    std::size_t first = 0;
    while (first < reference.size() && !std::isdigit(static_cast<unsigned char>(reference[first])))
        ++first;
    if (first == reference.size()) return {};
    for (std::size_t index = first; index < reference.size(); ++index)
        if (!std::isdigit(static_cast<unsigned char>(reference[index]))) return {};
    const long long number = std::stoll(reference.substr(first));
    const long long index = number / static_cast<long long>(constants::reference_stride.value);
    if (index == 0) return {};
    const auto found = groups.find(index);
    if (found == groups.end())
        throw MeasureError("measure: reference " + reference + " maps to no sheet index");
    return found->second;
}

Pad read_pad(const SexprList& entry, Point& local) {
    Pad pad;
    pad.number = field_text(&entry, first_field);
    const std::string kind = field_text(&entry, second_field);
    pad.through = kind == "thru_hole" || kind == "np_thru_hole";
    const auto* at = child(entry, "at");
    if (!at) throw MeasureError("measure: pad without position");
    local = point_of(*at, "pad position");
    if (const auto* size = child(entry, "size")) {
        const Point extent = point_of(*size, "pad size");
        pad.reach = std::max(extent.x, extent.y) / 2;
    }
    const auto* net = child(entry, "net");
    if (net && net->size() > first_field) pad.net = as_text(net->back());
    return pad;
}

Part read_part(const SexprList& item, const std::map<long long, std::string>& groups, bool& usable) {
    Part part;
    part.footprint = field_text(&item, first_field);
    const std::string side = field_text(child(item, "layer"), first_field);
    if (side == "F.Cu") part.face = Face::top;
    else if (side == "B.Cu") part.face = Face::bottom;
    else throw MeasureError("measure: footprint " + part.footprint + " is on neither outer copper layer");
    const auto* at = child(item, "at");
    if (!at) throw MeasureError("measure: footprint " + part.footprint + " has no position");
    const Point origin = point_of(*at, "footprint position");
    const double angle =
        at->size() > third_field ? as_number((*at)[third_field], "footprint angle") : 0;
    std::vector<Point> shape, locals;
    for (const auto& node : item) {
        const auto* entry = as_list(node);
        if (!entry || entry->empty()) continue;
        const std::string kind = as_text(entry->front());
        if (kind == "property" && field_text(entry, first_field) == "Reference") {
            part.reference = field_text(entry, second_field);
        } else if (starts_with(kind, "fp_")) {
            if (ends_with(field_text(child(*entry, "layer"), first_field), "CrtYd"))
                graphic_points(*entry, shape);
        } else if (kind == "pad") {
            Point local;
            part.pads.push_back(read_pad(*entry, local));
            locals.push_back(local);
        }
    }
    if (shape.empty()) {
        part.courtyard_from_pads = true;
        for (std::size_t index = 0; index < locals.size(); ++index) {
            const double reach = part.pads[index].reach;
            corner_points({locals[index].x - reach, locals[index].y - reach},
                          {locals[index].x + reach, locals[index].y + reach}, shape);
        }
    }
    usable = !shape.empty();
    if (!usable) return part;
    Extent extent;
    for (const auto& point : shape) {
        const Point global = turned(point, angle);
        extent.add({origin.x + global.x, origin.y + global.y});
    }
    part.courtyard = extent.box;
    std::set<std::string> numbers;
    for (std::size_t index = 0; index < locals.size(); ++index) {
        const Point global = turned(locals[index], angle);
        Pad& pad = part.pads[index];
        pad.x = origin.x + global.x;
        pad.y = origin.y + global.y;
        if (!pad.number.empty()) numbers.insert(pad.number);
        if (!pad.net.empty()) part.electrical = true;
    }
    part.pin_count = static_cast<int>(numbers.size());
    part.group = group_of(part.reference, groups);
    return part;
}

double number_field(const JsonNode& node, const std::string& key) {
    const auto* value = object_field(node, key);
    if (!value || value->kind != JsonKind::Number)
        throw MeasureError("measure: net class field " + key + " must be a number");
    return value->number_value;
}

void read_classes(const JsonNode& project, Board& board) {
    const auto* settings = object_field(project, "net_settings");
    if (!settings) throw MeasureError("measure: project file has no net_settings");
    const auto* classes = object_field(*settings, "classes");
    if (!classes || classes->kind != JsonKind::Array)
        throw MeasureError("measure: project file has no net classes");
    for (const auto& entry : classes->array_value)
        board.classes.push_back({require_string(entry, "name", false, "measure net class"),
                                 number_field(entry, "track_width"),
                                 number_field(entry, "clearance")});
    const auto* patterns = object_field(*settings, "netclass_patterns");
    if (!patterns || patterns->kind != JsonKind::Array) return;
    for (const auto& entry : patterns->array_value)
        board.patterns.push_back({require_string(entry, "pattern", false, "measure class pattern"),
                                  require_string(entry, "netclass", false, "measure class pattern")});
}

}

Board read_board(const Sexpr& pcb, const JsonNode& project, const JsonNode& sheet_index) {
    const auto* root = as_list(pcb);
    if (!root || !tagged(pcb, "kicad_pcb")) throw MeasureError("measure: not a kicad_pcb document");
    Board board;
    board.outline = read_outline(*root);
    board.copper = read_copper(*root);
    board.zones = read_zones(*root);
    read_classes(project, board);
    const auto groups = read_groups(sheet_index);
    for (const auto& node : *root) {
        if (!tagged(node, "footprint")) continue;
        bool usable = false;
        Part part = read_part(*as_list(node), groups, usable);
        if (usable) board.parts.push_back(std::move(part));
        else board.without_geometry.push_back(part.reference.empty() ? part.footprint : part.reference);
    }
    return board;
}

}
