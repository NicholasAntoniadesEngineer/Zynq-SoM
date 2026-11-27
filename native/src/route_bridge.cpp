#include "schgen/route_bridge.hpp"

#include "schgen/route_check.hpp"

#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <map>
#include <regex>
#include <sstream>

namespace schgen::route {
namespace {

const char* const setup_schema = "schgen.route.setup/1";
const char* const usage = "usage: schgen route-try BOARD PROJECT SETUP [BOARD_OUT]\n"
                          "  routes a KiCad board file under the rules and net classes of its project file, with the search\n"
                          "  settings of a route setup file, then judges the copper with the independent route check.\n"
                          "  The layer count, plane layers, net classes and clearances are all read from the two KiCad files.\n"
                          "  With BOARD_OUT the copper is added to a copy of the board.\n";

std::string slurp(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw RouteError("route: cannot read " + path);
    return std::string((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
}

std::string copper_text(const Board& board, const std::vector<Item>& copper, const std::map<std::string, int>& numbers) {
    std::ostringstream out;
    out << std::fixed << std::setprecision(6);
    std::size_t serial = 0;
    const auto mm = [](Nm value) { return layout::to_mm(value); };
    const auto identity = [&] {
        std::ostringstream text;
        text << "5c68656e-726f-4575-8000-" << std::hex << std::setw(12) << std::setfill('0') << ++serial;
        return text.str();
    };
    for (const Item& item : copper) {
        const std::string& name = board.nets.at(static_cast<std::size_t>(item.net)).name;
        const auto number = numbers.find(name);
        if (number == numbers.end()) throw RouteError("route: the board file has no net named " + name);
        if (item.kind == ItemKind::via) {
            out << "\t(via\n\t\t(at " << mm(item.shape.core[0].x) << " " << mm(item.shape.core[0].y) << ")\n\t\t(size " << mm(2 * item.shape.radius) << ")\n\t\t(drill "
                << mm(item.drill) << ")\n\t\t(layers \"" << board.rules.layers[item.first].name << "\" \"" << board.rules.layers[item.last].name << "\")\n\t\t(net "
                << number->second << ")\n\t\t(uuid \"" << identity() << "\")\n\t)\n";
            continue;
        }
        const Point from = item.shape.core[0], to = item.shape.count > 1 ? item.shape.core[1] : item.shape.core[0];
        out << "\t(segment\n\t\t(start " << mm(from.x) << " " << mm(from.y) << ")\n\t\t(end " << mm(to.x) << " " << mm(to.y) << ")\n\t\t(width " << mm(2 * item.shape.radius)
            << ")\n\t\t(layer \"" << board.rules.layers[item.first].name << "\")\n\t\t(net " << number->second << ")\n\t\t(uuid \"" << identity() << "\")\n\t)\n";
    }
    return out.str();
}

}

RunSetup read_setup(const JsonNode& root) {
    const JsonNode* schema = object_field(root, "schema");
    if (!schema || schema->string_value != setup_schema) throw RouteError(std::string("route setup: schema must be ") + setup_schema);
    reject_unknown_keys(root, {"schema", "pitch_mm", "passes", "search_budget"}, "route setup");
    const auto number = [&](const char* key) {
        const JsonNode* found = object_field(root, key);
        if (!found || found->kind != JsonKind::Number || found->number_value <= 0) throw RouteError(std::string("route setup: '") + key + "' must be a positive number");
        return found->number_value;
    };
    RunSetup setup;
    setup.search.pitch = layout::to_nm(number("pitch_mm"));
    setup.search.budget = static_cast<std::size_t>(number("search_budget"));
    setup.passes = static_cast<std::size_t>(number("passes"));
    return setup;
}

std::string with_copper(const std::string& board_text, const Board& board, const std::vector<Item>& copper) {
    std::map<std::string, int> numbers;
    static const std::regex net(R"rx(\n\t\(net (\d+) "([^"]*)"\))rx");
    for (std::sregex_iterator match(board_text.begin(), board_text.end(), net), last; match != last; ++match) numbers[(*match)[2].str()] = std::stoi((*match)[1].str());
    const std::size_t end = board_text.rfind(')');
    if (end == std::string::npos) throw RouteError("route: the board file is not a KiCad board");
    return board_text.substr(0, end) + copper_text(board, copper, numbers) + board_text.substr(end);
}

std::optional<int> run_route_command(int argc, char** argv) {
    if (argc < 2 || std::string(argv[1]) != "route-try") return std::nullopt;
    if (argc != 5 && argc != 6) {
        std::cout << usage;
        return argc == 3 && std::string(argv[2]) == "--help" ? 0 : 2;
    }
    const std::string text = slurp(argv[2]);
    ReadNotes notes;
    const Board board = board_from_pcb(sexpr_loads(text), parse_json_file(argv[3]), &notes);
    const RunSetup setup = read_setup(parse_json_file(argv[4]));
    World world(board);
    std::cout << "route: " << board.rules.layers.size() << " copper layers (" << notes.planes << " planes), " << board.nets.size() << " nets in " << board.rules.classes.size()
              << " classes, " << notes.footprints << " footprints, " << notes.pads << " pads, " << notes.tracks << " tracks and " << notes.vias << " vias already on the board, "
              << notes.keepouts << " keep-outs\n";
    for (const std::string& note : notes.approximated) std::cout << "  approximated: " << note << "\n";
    const RunReport run = route_all(world, setup);
    std::cout << run.summary(board);
    const CheckReport judged = verify(board, world.routed());
    const std::string report = judged.summary();
    std::cout << report.substr(0, report.find("  open nets")) << "  open nets: " << judged.opens.size() << "\n  stray copper: " << judged.strays.size() << "\n";
    if (argc == 6) {
        std::ofstream(argv[5], std::ios::binary) << with_copper(text, board, world.routed());
        std::cout << "  copper written into " << argv[5] << "\n";
    }
    return run.complete() && judged.ok() ? 0 : 1;
}

}
