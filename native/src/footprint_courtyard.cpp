#include "schgen/footprint_courtyard.hpp"

#include "part_import_internal.hpp"
#include "schgen/atomic_file.hpp"
#include "schgen/pcb_scan.hpp"

#include <iostream>
#include <set>

namespace schgen::courtyard {
namespace {
using namespace part_import_detail;

const char* const front_court = "F.CrtYd";
const char* const rear_court = "B.CrtYd";
const char* const front_body = "F.Fab";
const std::array<std::pair<Kind, const char*>, 5> kind_names{{{Kind::general, "general"},
                                                               {Kind::connector, "connector"},
                                                               {Kind::canned_capacitor, "canned_capacitor"},
                                                               {Kind::crystal, "crystal"},
                                                               {Kind::grid_array, "grid_array"}}};

int places() { return static_cast<int>(constants::extent_places.value); }

bool graphic(const S& node) {
    for (const char* name : {"fp_line", "fp_rect", "fp_poly", "fp_circle", "fp_arc"})
        if (tag(node, name)) return true;
    return false;
}

std::string layer_of(const S& node) {
    for (const auto& child : items(node))
        if (tag(child, "layer") && items(child).size() > 1)
            if (const auto* name = std::get_if<std::string>(&items(child)[1].v)) return *name;
    return {};
}

Edge edge_of(const S& line, const std::string& part) {
    std::array<double, 4> value{};
    std::size_t found = 0;
    for (const auto& child : items(line)) {
        const bool start = tag(child, "start");
        if (!start && !tag(child, "end")) continue;
        const auto& fields = items(child);
        if (fields.size() < 3 || !std::holds_alternative<double>(fields[1].v) || !std::holds_alternative<double>(fields[2].v))
            throw CourtyardError(part + ": a courtyard line has no numeric end point");
        value[start ? 0 : 2] = std::get<double>(fields[1].v);
        value[start ? 1 : 3] = std::get<double>(fields[2].v);
        ++found;
    }
    if (found != 2) throw CourtyardError(part + ": a courtyard line needs one start and one end");
    return {value[0], value[1], value[2], value[3]};
}

S line(const Edge& edge, double width, const char* layer) {
    return list({sym("fp_line"), list({sym("start"), num(edge.x0), num(edge.y0)}),
                 list({sym("end"), num(edge.x1), num(edge.y1)}), stroke(width), list({sym("layer"), str(layer)})});
}

bool holds(const Box4& outer, const Box4& inner) {
    return outer.x0 <= inner.x0 && outer.y0 <= inner.y0 && outer.x1 >= inner.x1 && outer.y1 >= inner.y1;
}

std::string text(const Box4& box) {
    std::ostringstream out;
    out.imbue(std::locale::classic());
    out << '(' << box.x0 << ' ' << box.y0 << ")..(" << box.x1 << ' ' << box.y1 << ')';
    return out.str();
}

double outward(double value, bool up) {
    const long long step = std::llround(constants::court_grid.value / constants::extent_quantum.value);
    const long long units = std::llround(value / constants::extent_quantum.value);
    long long cell = units / step;
    if (units % step != 0) {
        if (up && units > 0) ++cell;
        if (!up && units < 0) --cell;
    }
    return static_cast<double>(cell) / std::round(1 / constants::court_grid.value);
}

Box4 shell_of(const std::vector<Edge>& body) {
    Box4 shell{body.front().x0, body.front().y0, body.front().x0, body.front().y0};
    for (const auto& edge : body) {
        shell.x0 = std::min({shell.x0, edge.x0, edge.x1});
        shell.y0 = std::min({shell.y0, edge.y0, edge.y1});
        shell.x1 = std::max({shell.x1, edge.x0, edge.x1});
        shell.y1 = std::max({shell.y1, edge.y0, edge.y1});
    }
    return shell;
}

struct Plan {
    std::vector<std::size_t> dropped;
    std::size_t slot = 0;
    std::vector<S> drawn;
};

S applied(const S& footprint, const Plan& plan) {
    const auto& source = items(footprint);
    S out{SexprList{}};
    auto& nodes = items(out);
    for (std::size_t index = 0; index <= source.size(); ++index) {
        if (index == plan.slot) nodes.insert(nodes.end(), plan.drawn.begin(), plan.drawn.end());
        if (index == source.size() || std::find(plan.dropped.begin(), plan.dropped.end(), index) != plan.dropped.end()) continue;
        nodes.push_back(source[index]);
    }
    return out;
}

std::vector<std::pair<std::size_t, std::size_t>> child_spans(const std::string& stored, const std::string& part) {
    std::vector<std::pair<std::size_t, std::size_t>> spans;
    std::size_t depth = 0, begin = 0;
    bool quoted = false;
    for (std::size_t at = 0; at < stored.size(); ++at) {
        const char mark = stored[at];
        if (quoted) {
            if (mark == '\\') ++at;
            else if (mark == '"') quoted = false;
            continue;
        }
        if (mark == '"') quoted = true;
        else if (mark == '(') {
            if (depth++ == 1) begin = at;
        } else if (mark == ')') {
            if (depth == 0) throw CourtyardError(part + ": unbalanced footprint text");
            if (--depth == 1) spans.emplace_back(begin, at + 1);
        }
    }
    if (depth != 0 || quoted) throw CourtyardError(part + ": unbalanced footprint text");
    return spans;
}

std::string spliced(const std::string& stored, const S& footprint, const Plan& plan, const std::string& part) {
    const auto spans = child_spans(stored, part);
    const auto& source = items(footprint);
    std::vector<std::size_t> span_of(source.size() + 1, spans.size());
    std::size_t next = 0;
    for (std::size_t index = 0; index < source.size(); ++index)
        if (std::holds_alternative<SexprList>(source[index].v)) span_of[index] = next++;
    if (next != spans.size()) throw CourtyardError(part + ": footprint text and document disagree on their node count");
    const auto lead = [&](std::size_t begin) {
        while (begin > 0 && std::isspace(static_cast<unsigned char>(stored[begin - 1]))) --begin;
        return begin;
    };
    std::string addition;
    for (const auto& node : plan.drawn) addition += "\n\t" + sexpr_dumps(node, 1);
    const std::size_t closing = lead(stored.rfind(')'));
    const std::size_t entry = plan.slot < source.size() ? span_of[plan.slot] : spans.size();
    const std::size_t place = entry < spans.size() ? lead(spans[entry].first) : closing;
    std::string out;
    std::size_t copied = 0;
    bool placed = false;
    const auto insert = [&] {
        out += stored.substr(copied, place - copied) + addition;
        copied = place;
        placed = true;
    };
    for (const std::size_t index : plan.dropped) {
        const auto& span = spans.at(span_of[index]);
        const std::size_t start = lead(span.first);
        if (!placed && place <= start) insert();
        out += stored.substr(copied, start - copied);
        copied = span.second;
    }
    if (!placed) insert();
    out += stored.substr(copied);
    if (sexpr_dumps(sexpr_loads(out)) != sexpr_dumps(applied(footprint, plan)))
        throw CourtyardError(part + ": the rewritten footprint text does not read back as the derived footprint");
    return out;
}

Plan planned(const Sexpr& footprint, const std::vector<Edge>& provided, const PartRule& rule, const std::string& part);

std::string read(const std::filesystem::path& file) {
    try {
        return read_file(file);
    } catch (const PartImportError& error) {
        throw CourtyardError(error.what());
    }
}

struct Outcome {
    std::string part, bytes, row;
    bool changed = false;
};

Outcome derive(const std::filesystem::path& folder, const RuleTable& table) {
    const std::string part = folder.filename().string();
    const auto stored = read(folder / (part + ".kicad_mod"));
    const S document = sexpr_loads(stored);
    const auto payload = parse_json_text(read(folder / (part + ".easyeda.json")), part);
    const auto* wrapped = object_field(payload, "result");
    const JsonNode& result = wrapped ? *wrapped : payload;
    const S fresh = part_convert_footprint(result, part, part_import_info(result)).tree;
    const PartRule& rule = table.at(part);
    const Plan plan = planned(document, court_edges(fresh), rule, part);
    const Extents extents = measure(applied(document, plan));
    Outcome outcome;
    outcome.part = part;
    outcome.bytes = spliced(stored, document, plan, part);
    outcome.changed = outcome.bytes != stored;
    const double margin = std::min({extents.body->x0 - extents.court->x0, extents.body->y0 - extents.court->y0,
                                    extents.court->x1 - extents.body->x1, extents.court->y1 - extents.body->y1});
    std::ostringstream row;
    row.imbue(std::locale::classic());
    row << part << " kind=" << kind_name(rule.kind) << " courtyard=" << text(*extents.court)
        << " body_and_pads=" << text(*extents.body) << " pads=" << text(*extents.land) << " least_margin=" << margin
        << (outcome.changed ? " STALE" : " current");
    outcome.row = row.str();
    return outcome;
}
}

std::string kind_name(Kind kind) {
    for (const auto& [value, name] : kind_names)
        if (value == kind) return name;
    throw CourtyardError("unknown courtyard kind");
}

const PartRule& RuleTable::at(const std::string& part) const {
    const auto found = parts.find(part);
    if (found == parts.end())
        throw CourtyardError(part + ": no courtyard class in " + source + "; add it there with one of general, connector, canned_capacitor, crystal, grid_array");
    return found->second;
}

RuleTable parse_rules(const JsonNode& root, const std::string& source) {
    reject_unknown_keys(root, {"schema", "source", "parts"}, source);
    if (require_string(root, "schema", false, source) != rule_schema) throw CourtyardError(source + ": schema must be " + rule_schema);
    (void)require_string(root, "source", false, source);
    const JsonNode* parts = object_field(root, "parts");
    if (!parts || parts->kind != JsonKind::Object || parts->object_value.empty())
        throw CourtyardError(source + ": parts must be a non-empty object");
    RuleTable table;
    table.source = source;
    for (const auto& [part, row] : parts->object_value) {
        const std::string where = source + " " + part;
        reject_unknown_keys(row, {"kind", "body_mm", "body_source"}, where);
        const std::string kind = require_string(row, "kind", false, where);
        const auto named = std::find_if(kind_names.begin(), kind_names.end(), [&](const auto& entry) { return kind == entry.second; });
        if (named == kind_names.end()) throw CourtyardError(where + ": unknown kind " + kind);
        PartRule rule;
        rule.kind = named->first;
        if (const JsonNode* body = object_field(row, "body_mm")) {
            if (body->kind != JsonKind::Array || body->array_value.size() != 2 ||
                !std::all_of(body->array_value.begin(), body->array_value.end(), [](const JsonNode& side) {
                    return side.kind == JsonKind::Number && std::isfinite(side.number_value) && side.number_value > 0;
                }))
                throw CourtyardError(where + ": body_mm must be two positive lengths");
            (void)require_string(row, "body_source", false, where);
            rule.body = std::make_pair(body->array_value.front().number_value, body->array_value.back().number_value);
        } else if (object_field(row, "body_source")) {
            throw CourtyardError(where + ": body_source without body_mm");
        }
        if (!table.parts.emplace(part, rule).second) throw CourtyardError(where + ": listed twice");
    }
    return table;
}

RuleTable load_rules(const std::filesystem::path& file) {
    if (!std::filesystem::is_regular_file(file)) throw CourtyardError("the courtyard class file is missing: " + file.string());
    return parse_rules(parse_json_file(file.string()), file.string());
}

double clearance_of(Kind kind, const Box4& body) {
    switch (kind) {
    case Kind::connector: return constants::connector_clearance.value;
    case Kind::canned_capacitor: return constants::canned_clearance.value;
    case Kind::crystal: return constants::crystal_clearance.value;
    case Kind::grid_array: return constants::array_clearance.value;
    case Kind::general: break;
    }
    return std::max(body.x1 - body.x0, body.y1 - body.y0) < constants::small_extent.value ? constants::small_clearance.value
                                                                                           : constants::general_clearance.value;
}

Extents measure(const Sexpr& footprint) {
    Extents extents;
    extents.court = footprint_extent(footprint, FootprintExtent::court, places());
    extents.land = footprint_extent(footprint, FootprintExtent::land, places());
    extents.body = footprint_extent(footprint, FootprintExtent::body, places());
    return extents;
}

std::optional<std::string> defect(const Sexpr& footprint) {
    const Extents extents = measure(footprint);
    if (!extents.land) return std::nullopt;
    if (!extents.court) return "it has pads but no courtyard";
    if (!holds(*extents.court, *extents.land))
        return "its courtyard " + text(*extents.court) + " does not enclose its pads " + text(*extents.land);
    return std::nullopt;
}

void require_sound(const Sexpr& footprint, const std::string& source) {
    if (const auto why = defect(footprint)) throw CourtyardError("footprint " + source + " is refused: " + *why);
}

std::vector<Edge> court_edges(const Sexpr& footprint) {
    std::vector<Edge> edges;
    for (const auto& node : items(footprint)) {
        if (!graphic(node) || layer_of(node) != front_court) continue;
        if (!tag(node, "fp_line")) throw CourtyardError("the provider body outline holds a shape other than a line");
        edges.push_back(edge_of(node, "provider outline"));
    }
    return edges;
}

namespace {
Plan planned(const Sexpr& footprint, const std::vector<Edge>& provided, const PartRule& rule, const std::string& part) {
    if (!tag(footprint, "footprint")) throw CourtyardError(part + ": a footprint document is required");
    std::vector<Edge> body = provided;
    if (body.empty()) {
        if (!rule.body) throw CourtyardError(part + ": the provider draws no body outline and " + rule_file + " declares no body_mm");
        const double x = rule.body->first / 2, y = rule.body->second / 2;
        body = {{-x, -y, x, -y}, {x, -y, x, y}, {x, y, -x, y}, {-x, y, -x, -y}};
    } else if (rule.body) {
        throw CourtyardError(part + ": " + rule_file + " declares body_mm but the provider draws a body outline");
    }
    std::vector<S> drawn;
    std::set<std::string> known;
    for (const auto& edge : body) {
        drawn.push_back(line(edge, constants::body_stroke.value, front_body));
        known.insert(sexpr_dumps(drawn.back()));
    }
    Plan plan;
    const auto& source = items(footprint);
    for (std::size_t index = 0; index < source.size(); ++index) {
        const bool shape = graphic(source[index]);
        const std::string layer = shape ? layer_of(source[index]) : std::string();
        if (layer == rear_court) throw CourtyardError(part + ": a rear courtyard is not supported");
        if (shape && (layer == front_court || known.count(sexpr_dumps(source[index])))) plan.dropped.push_back(index);
    }
    const auto pad = std::find_if(source.begin(), source.end(), [](const S& node) { return tag(node, "pad"); });
    plan.slot = plan.dropped.empty() ? static_cast<std::size_t>(pad - source.begin()) : plan.dropped.front();
    plan.drawn = drawn;
    const auto reach = footprint_extent(applied(footprint, plan), FootprintExtent::body, places());
    if (!reach) throw CourtyardError(part + ": nothing to enclose");
    const double clearance = clearance_of(rule.kind, shell_of(body));
    const Box4 court{outward(reach->x0 - clearance, false), outward(reach->y0 - clearance, false),
                     outward(reach->x1 + clearance, true), outward(reach->y1 + clearance, true)};
    const std::array<Edge, 4> ring{{{court.x0, court.y0, court.x1, court.y0},
                                    {court.x1, court.y0, court.x1, court.y1},
                                    {court.x1, court.y1, court.x0, court.y1},
                                    {court.x0, court.y1, court.x0, court.y0}}};
    for (const auto& edge : ring) plan.drawn.push_back(line(edge, constants::court_stroke.value, front_court));
    if (const auto why = defect(applied(footprint, plan))) throw CourtyardError(part + ": " + *why);
    return plan;
}
}

Sexpr enclosed(const Sexpr& footprint, const std::vector<Edge>& body, const PartRule& rule, const std::string& part) {
    return applied(footprint, planned(footprint, body, rule, part));
}


std::optional<int> run_part_courtyard_command(int argc, char** argv) {
    if (argc < 2 || std::string(argv[1]) != "part-courtyard") return std::nullopt;
    std::filesystem::path root;
    std::vector<std::filesystem::path> files;
    bool write = false, help = false;
    for (int index = 2; index < argc; ++index) {
        const std::string option = argv[index];
        if (option == "--help" || option == "-h") {
            help = true;
            continue;
        }
        if (option == "--write") {
            write = true;
            continue;
        }
        if (option != "--parts-root" && option != "--footprint") throw CourtyardError("unknown part-courtyard option " + option);
        if (++index == argc || std::string(argv[index]).empty()) throw CourtyardError("missing value for " + option);
        if (option == "--footprint") files.emplace_back(argv[index]);
        else if (root.empty()) root = argv[index];
        else throw CourtyardError("duplicate option " + option);
    }
    if (help) {
        std::cout << "usage: schgen part-courtyard --parts-root DIRECTORY [--write]\n"
                     "       schgen part-courtyard --footprint FILE [--footprint FILE]...\n"
                     "Derive every part footprint's courtyard from its stored provider outline, its pads and\n"
                     "the clearance of its class in courtyard_classes.json. Without --write nothing is changed\n"
                     "and a stale footprint fails the command. --footprint only judges the named files.\n";
        return 0;
    }
    if (root.empty() == files.empty()) throw CourtyardError("part-courtyard requires --parts-root DIRECTORY or --footprint FILE");
    if (!files.empty()) {
        if (write) throw CourtyardError("--write applies to --parts-root only");
        std::size_t refused = 0;
        for (const auto& file : files) {
            const S document = sexpr_loads(read(file));
            const auto why = defect(document);
            const Extents extents = measure(document);
            std::cout << file.string() << ' ' << (why ? "REFUSED: " + *why : std::string("sound"));
            if (!why && extents.court && extents.body)
                std::cout << " courtyard=" << text(*extents.court) << " body_and_pads=" << text(*extents.body);
            std::cout << '\n';
            if (why) ++refused;
        }
        return refused ? 1 : 0;
    }
    const RuleTable table = load_rules(root / rule_file);
    std::set<std::filesystem::path> folders;
    for (const auto& entry : std::filesystem::directory_iterator(root))
        if (entry.is_directory() && std::filesystem::is_regular_file(entry.path() / (entry.path().filename().string() + ".kicad_mod")))
            folders.insert(entry.path());
    for (const auto& [part, rule] : table.parts) {
        (void)rule;
        if (!folders.count(root / part)) throw CourtyardError(part + ": listed in " + table.source + " but has no footprint under " + root.string());
    }
    std::size_t stale = 0;
    for (const auto& folder : folders) {
        const Outcome outcome = derive(folder, table);
        std::cout << outcome.row << '\n';
        if (!outcome.changed) continue;
        ++stale;
        if (write) write_atomic_file((folder / (outcome.part + ".kicad_mod")).string(), {outcome.bytes.begin(), outcome.bytes.end()});
    }
    std::cout << "COURTYARDS: " << folders.size() << " footprints, " << stale << (write ? " rewritten" : " stale") << '\n';
    return stale && !write ? 1 : 0;
}

}
