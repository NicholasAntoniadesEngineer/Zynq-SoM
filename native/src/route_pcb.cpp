#include "schgen/route_bridge.hpp"

#include <algorithm>
#include <cmath>
#include <map>

namespace schgen::route {
namespace {

const char* const copper_suffix = ".Cu";
const char* const default_class = "Default";
constexpr double half_turn = 180.0, nano = 1e6;

Nm nm(double millimetres) { return static_cast<Nm>(std::llround(millimetres * nano)); }

const SexprList* list_of(const Sexpr& node) { return std::get_if<SexprList>(&node.v); }

std::string head(const Sexpr& node) {
    const SexprList* items = list_of(node);
    if (!items || items->empty()) return {};
    const auto* symbol = std::get_if<Sexpr::Sym>(&items->front().v);
    return symbol ? symbol->name : std::string();
}

std::string text_at(const Sexpr& node, std::size_t index) {
    const SexprList* items = list_of(node);
    if (!items || index >= items->size()) return {};
    if (const auto* text = std::get_if<std::string>(&(*items)[index].v)) return *text;
    if (const auto* symbol = std::get_if<Sexpr::Sym>(&(*items)[index].v)) return symbol->name;
    return {};
}

std::optional<double> number_at(const Sexpr& node, std::size_t index) {
    const SexprList* items = list_of(node);
    if (!items || index >= items->size()) return std::nullopt;
    if (const auto* value = std::get_if<double>(&(*items)[index].v)) return *value;
    return std::nullopt;
}

const Sexpr* child(const Sexpr& node, const std::string& name) {
    const SexprList* items = list_of(node);
    if (!items) return nullptr;
    for (const Sexpr& entry : *items)
        if (head(entry) == name) return &entry;
    return nullptr;
}

std::vector<const Sexpr*> children(const Sexpr& node, const std::string& name) {
    std::vector<const Sexpr*> found;
    if (const SexprList* items = list_of(node))
        for (const Sexpr& entry : *items)
            if (head(entry) == name) found.push_back(&entry);
    return found;
}

double need(const Sexpr& node, std::size_t index, const std::string& what) {
    const auto value = number_at(node, index);
    if (!value) throw RouteError("route: the board file has a " + what + " without a number");
    return *value;
}

struct Frame {
    double x = 0, y = 0, turn = 0;
};

Point turned(double x, double y, double degrees, const Frame& frame) {
    const double angle = degrees * std::acos(-1.0) / half_turn;
    return {nm(frame.x) + static_cast<Nm>(std::llround((x * std::cos(angle) + y * std::sin(angle)) * nano)),
            nm(frame.y) + static_cast<Nm>(std::llround((-x * std::sin(angle) + y * std::cos(angle)) * nano))};
}

Shape oriented(Point centre, double half_x, double half_y, double degrees, Nm radius) {
    const Frame at{layout::to_mm(centre.x), layout::to_mm(centre.y), 0};
    if (half_x <= 0 && half_y <= 0) return disc(centre, radius);
    if (half_y <= 0) return capsule(turned(-half_x, 0, degrees, at), turned(half_x, 0, degrees, at), radius);
    if (half_x <= 0) return capsule(turned(0, -half_y, degrees, at), turned(0, half_y, degrees, at), radius);
    Shape shape;
    shape.core = {turned(-half_x, -half_y, degrees, at), turned(half_x, -half_y, degrees, at), turned(half_x, half_y, degrees, at), turned(-half_x, half_y, degrees, at)};
    shape.count = core_limit;
    shape.radius = radius;
    return shape;
}

const JsonNode& member(const JsonNode& node, const std::string& key, const std::string& where) {
    const JsonNode* found = object_field(node, key);
    if (!found) throw RouteError("route: the project file has no '" + key + "' in " + where);
    return *found;
}

Nm length(const JsonNode& node, const std::string& key, const std::string& where) {
    const JsonNode& value = member(node, key, where);
    if (value.kind != JsonKind::Number) throw RouteError("route: '" + key + "' in " + where + " of the project file is not a number");
    return nm(value.number_value);
}

}

Board board_from_pcb(const Sexpr& pcb, const JsonNode& project, ReadNotes* notes) {
    ReadNotes local;
    ReadNotes& read = notes ? *notes : local;
    Board board;
    std::map<std::string, std::size_t> layer_of;
    const Sexpr* layers = child(pcb, "layers");
    if (!layers) throw RouteError("route: the board file states no layers");
    for (const Sexpr& entry : *list_of(*layers)) {
        const std::string name = text_at(entry, 1);
        if (name.size() <= std::string(copper_suffix).size() || name.compare(name.size() - std::string(copper_suffix).size(), std::string::npos, copper_suffix) != 0) continue;
        layer_of.emplace(name, board.rules.layers.size());
        board.rules.layers.push_back({name, LayerKind::signal, no_net});
    }
    std::map<int, int> net_of;
    std::map<std::string, int> named;
    for (const Sexpr* entry : children(pcb, "net")) {
        const int number = static_cast<int>(need(*entry, 1, "net"));
        const std::string name = text_at(*entry, 2);
        if (number == 0 || name.empty()) continue;
        net_of.emplace(number, static_cast<int>(board.nets.size()));
        named.emplace(name, static_cast<int>(board.nets.size()));
        board.nets.push_back({name, 0});
    }
    const JsonNode& settings = member(project, "net_settings", "the file");
    std::map<std::string, std::size_t> class_of;
    const std::vector<JsonNode>& stated = member(settings, "classes", "net_settings").array_value;
    for (const bool wanted_default : {true, false})
        for (const JsonNode& entry : stated) {
            const std::string name = member(entry, "name", "a net class").string_value;
            if ((name == default_class) != wanted_default) continue;
            const ViaKind kind{name, length(entry, "via_diameter", "net class " + name), length(entry, "via_drill", "net class " + name), 0, board.rules.layers.size() - 1};
            std::size_t via_index = 0;
            for (; via_index < board.rules.vias.size(); ++via_index)
                if (board.rules.vias[via_index].pad == kind.pad && board.rules.vias[via_index].drill == kind.drill) break;
            if (via_index == board.rules.vias.size()) board.rules.vias.push_back(kind);
            class_of.emplace(name, board.rules.classes.size());
            board.rules.classes.push_back({name, length(entry, "track_width", "net class " + name), length(entry, "clearance", "net class " + name), via_index, 0, 0});
            if (object_field(entry, "diff_pair_width") && object_field(entry, "diff_pair_gap")) {
                board.rules.classes.back().pair_width = length(entry, "diff_pair_width", "net class " + name);
                board.rules.classes.back().pair_gap = length(entry, "diff_pair_gap", "net class " + name);
            }
        }
    if (!class_of.count(default_class)) throw RouteError("route: the project file has no Default net class");
    if (const JsonNode* patterns = object_field(settings, "netclass_patterns"))
        for (const JsonNode& entry : patterns->array_value) {
            const auto net = named.find(member(entry, "pattern", "a net class pattern").string_value);
            const auto found = class_of.find(member(entry, "netclass", "a net class pattern").string_value);
            if (net != named.end() && found != class_of.end()) board.nets[static_cast<std::size_t>(net->second)].net_class = found->second;
        }
    const JsonNode& rules = member(member(member(project, "board", "the file"), "design_settings", "board"), "rules", "design_settings");
    board.rules.edge_clearance = length(rules, "min_copper_edge_clearance", "rules");
    board.rules.hole_clearance = length(rules, "min_hole_clearance", "rules");
    board.rules.hole_spacing = length(rules, "min_hole_to_hole", "rules");
    board.rules.least_track = length(rules, "min_track_width", "rules");
    const std::size_t rear = board.rules.layers.size() - 1;
    const auto net_index = [&](const Sexpr& node) {
        const Sexpr* net = child(node, "net");
        if (!net) return no_net;
        const auto found = net_of.find(static_cast<int>(need(*net, 1, "net reference")));
        return found == net_of.end() ? no_net : found->second;
    };
    std::optional<Box> outline;
    const auto widen = [&](double x, double y) {
        const Point at{nm(x), nm(y)};
        outline = outline ? layout::united(*outline, Box{at.x, at.y, at.x, at.y}) : Box{at.x, at.y, at.x, at.y};
    };
    for (const char* kind : {"gr_rect", "gr_line", "gr_poly", "gr_arc"})
        for (const Sexpr* entry : children(pcb, kind)) {
            const Sexpr* layer = child(*entry, "layer");
            if (!layer || text_at(*layer, 1) != "Edge.Cuts") continue;
            for (const char* point : {"start", "end", "mid"})
                if (const Sexpr* at = child(*entry, point)) widen(need(*at, 1, "outline point"), need(*at, 2, "outline point"));
            if (const Sexpr* points = child(*entry, "pts"))
                for (const Sexpr* at : children(*points, "xy")) widen(need(*at, 1, "outline point"), need(*at, 2, "outline point"));
        }
    if (!outline) throw RouteError("route: the board file has no outline on Edge.Cuts");
    board.outline = *outline;
    for (const Sexpr* footprint : children(pcb, "footprint")) {
        ++read.footprints;
        const Sexpr* at = child(*footprint, "at");
        if (!at) throw RouteError("route: a footprint has no position");
        const Frame frame{need(*at, 1, "footprint position"), need(*at, 2, "footprint position"), number_at(*at, 3).value_or(0)};
        std::string reference;
        for (const Sexpr* property : children(*footprint, "property"))
            if (text_at(*property, 1) == "Reference") reference = text_at(*property, 2);
        const Sexpr* own = child(*footprint, "clearance");
        const Nm part_clearance = own ? nm(need(*own, 1, "footprint clearance")) : 0;
        for (const Sexpr* pad : children(*footprint, "pad")) {
            ++read.pads;
            const std::string name = text_at(*pad, 1), type = text_at(*pad, 2), form = text_at(*pad, 3);
            const Sexpr* where = child(*pad, "at");
            const Sexpr* size = child(*pad, "size");
            if (!where || !size) throw RouteError("route: pad " + reference + "." + name + " has no position or size");
            const Point centre = turned(need(*where, 1, "pad position"), need(*where, 2, "pad position"), frame.turn, frame);
            const double angle = number_at(*where, 3).value_or(0);
            const double wide = need(*size, 1, "pad size"), tall = need(*size, 2, "pad size");
            Item item;
            item.kind = ItemKind::pad;
            item.net = net_index(*pad);
            item.owner = reference + "." + name;
            const Sexpr* local = child(*pad, "clearance");
            item.clearance = local ? nm(need(*local, 1, "pad clearance")) : part_clearance;
            const bool drilled = type == "thru_hole" || type == "np_thru_hole";
            if (const Sexpr* drill = child(*pad, "drill")) {
                const bool oval = text_at(*drill, 1) == "oval";
                const double first = need(*drill, oval ? 2 : 1, "drill"), second = number_at(*drill, oval ? 3 : 2).value_or(first);
                item.drill = nm(std::max(first, second));
            }
            if (drilled) {
                item.first = 0;
                item.last = rear;
            } else {
                const Sexpr* on = child(*pad, "layers");
                bool front = false, back = false;
                if (on)
                    for (std::size_t index = 1; index < list_of(*on)->size(); ++index) {
                        const std::string layer = text_at(*on, index);
                        front = front || layer == "F.Cu" || layer == "*.Cu";
                        back = back || layer == "B.Cu" || layer == "*.Cu";
                    }
                if (!front && !back) continue;
                item.first = front ? 0 : rear;
                item.last = back ? rear : 0;
            }
            if (type == "np_thru_hole") {
                item.net = no_net;
                item.shape = disc(centre, std::max(item.drill, nm(std::max(wide, tall))) / 2);
            } else if (form == "circle") {
                item.shape = disc(centre, nm(wide) / 2);
            } else if (form == "oval") {
                const double round = std::min(wide, tall) / 2;
                item.shape = oriented(centre, wide / 2 - round, tall / 2 - round, angle, nm(round));
            } else if (form == "roundrect") {
                const Sexpr* ratio = child(*pad, "roundrect_rratio");
                const double round = (ratio ? need(*ratio, 1, "corner ratio") : 0) * std::min(wide, tall);
                item.shape = oriented(centre, wide / 2 - round, tall / 2 - round, angle, nm(round));
            } else if (form == "custom") {
                double x0 = -wide / 2, y0 = -tall / 2, x1 = wide / 2, y1 = tall / 2;
                std::size_t corners = 0;
                if (const Sexpr* primitives = child(*pad, "primitives"))
                    for (const Sexpr& primitive : *list_of(*primitives)) {
                        const Sexpr* stroke = child(primitive, "width");
                        const double half = stroke ? need(*stroke, 1, "primitive width") / 2 : 0;
                        const auto take = [&](double x, double y) {
                            x0 = std::min(x0, x - half);
                            y0 = std::min(y0, y - half);
                            x1 = std::max(x1, x + half);
                            y1 = std::max(y1, y + half);
                            ++corners;
                        };
                        if (const Sexpr* points = child(primitive, "pts"))
                            for (const Sexpr* at : children(*points, "xy")) take(need(*at, 1, "pad outline"), need(*at, 2, "pad outline"));
                        for (const char* point : {"start", "end", "center", "mid"})
                            if (const Sexpr* at = child(primitive, point)) take(need(*at, 1, "pad outline"), need(*at, 2, "pad outline"));
                    }
                const Frame home{layout::to_mm(centre.x), layout::to_mm(centre.y), 0};
                item.shape.core = {turned(x0, y0, angle, home), turned(x1, y0, angle, home), turned(x1, y1, angle, home), turned(x0, y1, angle, home)};
                item.shape.count = core_limit;
                read.approximated.push_back(item.owner + " (custom pad taken as the rectangle around its " + std::to_string(corners) + " outline points)");
            } else {
                if (form != "rect") read.approximated.push_back(item.owner + " (" + form + " pad taken as its size rectangle)");
                item.shape = oriented(centre, wide / 2, tall / 2, angle, 0);
            }
            board.fixed.push_back(std::move(item));
        }
    }
    for (const Sexpr* entry : children(pcb, "segment")) {
        const Sexpr* start = child(*entry, "start");
        const Sexpr* end = child(*entry, "end");
        const Sexpr* width = child(*entry, "width");
        const Sexpr* layer = child(*entry, "layer");
        const auto found = layer ? layer_of.find(text_at(*layer, 1)) : layer_of.end();
        if (!start || !end || !width || found == layer_of.end()) throw RouteError("route: a track in the board file is incomplete");
        ++read.tracks;
        board.fixed.push_back({ItemKind::track, net_index(*entry), found->second, found->second,
                               capsule({nm(need(*start, 1, "track")), nm(need(*start, 2, "track"))},
                                       {nm(need(*end, 1, "track")), nm(need(*end, 2, "track"))}, nm(need(*width, 1, "track")) / 2),
                               0, "track", 0});
    }
    for (const Sexpr* entry : children(pcb, "via")) {
        const Sexpr* at = child(*entry, "at");
        const Sexpr* size = child(*entry, "size");
        const Sexpr* drill = child(*entry, "drill");
        const Sexpr* span = child(*entry, "layers");
        if (!at || !size || !drill || !span) throw RouteError("route: a via in the board file is incomplete");
        const auto first = layer_of.find(text_at(*span, 1)), last = layer_of.find(text_at(*span, 2));
        if (first == layer_of.end() || last == layer_of.end()) throw RouteError("route: a via names a layer the board does not have");
        ++read.vias;
        board.fixed.push_back({ItemKind::via, net_index(*entry), std::min(first->second, last->second), std::max(first->second, last->second),
                               disc({nm(need(*at, 1, "via")), nm(need(*at, 2, "via"))}, nm(need(*size, 1, "via")) / 2),
                               nm(need(*drill, 1, "via")), "via", 0});
    }
    for (const Sexpr* zone : children(pcb, "zone")) {
        std::vector<std::size_t> on;
        for (const char* key : {"layer", "layers"})
            if (const Sexpr* listed = child(*zone, key))
                for (std::size_t index = 1; index < list_of(*listed)->size(); ++index) {
                    const auto found = layer_of.find(text_at(*listed, index));
                    if (found != layer_of.end()) on.push_back(found->second);
                }
        const Sexpr* polygon = child(*zone, "polygon");
        const Sexpr* points = polygon ? child(*polygon, "pts") : nullptr;
        std::optional<Box> hull;
        if (points)
            for (const Sexpr* at : children(*points, "xy")) {
                const Point corner{nm(need(*at, 1, "zone corner")), nm(need(*at, 2, "zone corner"))};
                hull = hull ? layout::united(*hull, Box{corner.x, corner.y, corner.x, corner.y}) : Box{corner.x, corner.y, corner.x, corner.y};
            }
        if (!hull) continue;
        if (const Sexpr* keepout = child(*zone, "keepout")) {
            const Sexpr* tracks = child(*keepout, "tracks");
            if (!tracks || text_at(*tracks, 1) != "not_allowed") continue;
            const Sexpr* name = child(*zone, "name");
            for (const std::size_t layer : on) {
                ++read.keepouts;
                board.fixed.push_back({ItemKind::keepout, no_net, layer, layer, rectangle(*hull), 0, name ? text_at(*name, 1) : std::string("rule area"), 0});
            }
            if (points && children(*points, "xy").size() != core_limit) read.approximated.push_back("a rule area with a polygon outline is taken as its bounding rectangle");
            continue;
        }
        const int net = net_index(*zone);
        if (net == no_net) continue;
        for (const std::size_t layer : on) {
            if (layer == 0 || layer == rear) continue;
            const bool whole = hull->x1 - hull->x0 >= (board.outline.x1 - board.outline.x0) / 2 && hull->y1 - hull->y0 >= (board.outline.y1 - board.outline.y0) / 2;
            if (!whole) continue;
            if (board.rules.layers[layer].kind == LayerKind::plane && board.rules.layers[layer].plane_net != net)
                throw RouteError("route: layer " + board.rules.layers[layer].name + " carries planes of two nets, which is not supported yet");
            if (board.rules.layers[layer].kind != LayerKind::plane) ++read.planes;
            board.rules.layers[layer] = {board.rules.layers[layer].name, LayerKind::plane, net};
        }
    }
    board.validate();
    return board;
}

}
