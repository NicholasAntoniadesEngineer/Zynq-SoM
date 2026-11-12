#include "schgen/measure.hpp"

#include "schgen/atomic_file.hpp"
#include "schgen/pcb_checks.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>

namespace schgen {
namespace {

using measure::MeasureError;

const char* const usage =
    "usage: schgen measure --pcb FILE --project-file FILE --sheet-index FILE\n"
    "         [--keepout top|bottom:ZONE]... [--power-class NAME]... [--exclude-group NAME]...\n"
    "         [-o REPORT.json] [--map MAP.svg]\n"
    "  Measures a placed board from its emitted files only. Without -o the report goes to stdout.\n";

struct Arguments {
    std::string pcb, project, sheet_index, output, map;
    measure::Options options;
};

std::string read_text(const std::string& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) throw MeasureError("measure: cannot read " + path);
    return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}

void write_text(const std::string& path, const std::string& text) {
    write_atomic_file(path, std::vector<uint8_t>(text.begin(), text.end()));
}

measure::Keepout parse_keepout(const std::string& value) {
    const auto split = value.find(':');
    if (split == std::string::npos || split + 1 == value.size())
        throw MeasureError("measure: --keepout requires top:ZONE or bottom:ZONE");
    const std::string face = value.substr(0, split);
    measure::Keepout keepout;
    if (face == "top") keepout.face = measure::Face::top;
    else if (face == "bottom") keepout.face = measure::Face::bottom;
    else throw MeasureError("measure: --keepout face must be top or bottom");
    keepout.zone = value.substr(split + 1);
    return keepout;
}

std::optional<Arguments> parse(int argc, char** argv) {
    Arguments arguments;
    for (int index = 2; index < argc; ++index) {
        const std::string name = argv[index];
        if (name == "--help" || name == "-h") return std::nullopt;
        if (index + 1 == argc) throw MeasureError("measure: " + name + " requires a value");
        const std::string value = argv[++index];
        if (name == "--pcb") arguments.pcb = value;
        else if (name == "--project-file") arguments.project = value;
        else if (name == "--sheet-index") arguments.sheet_index = value;
        else if (name == "-o" || name == "--output") arguments.output = value;
        else if (name == "--map") arguments.map = value;
        else if (name == "--keepout") arguments.options.keepouts.push_back(parse_keepout(value));
        else if (name == "--power-class") arguments.options.power_classes.push_back(value);
        else if (name == "--exclude-group") arguments.options.excluded_groups.push_back(value);
        else throw MeasureError("measure: unknown option " + name);
    }
    if (arguments.pcb.empty() || arguments.project.empty() || arguments.sheet_index.empty())
        throw MeasureError("measure: --pcb, --project-file and --sheet-index are required");
    return arguments;
}

measure::InputIdentity identity(const std::string& path, const std::string& text) {
    return {std::filesystem::path(path).filename().string(), pcb_sha256(text)};
}

}

std::optional<int> run_measure_command(int argc, char** argv) {
    if (argc < 2 || std::string(argv[1]) != "measure") return std::nullopt;
    const auto arguments = parse(argc, argv);
    if (!arguments) {
        std::cout << usage;
        return 0;
    }
    const std::string pcb = read_text(arguments->pcb);
    const std::string project = read_text(arguments->project);
    const std::string sheet_index = read_text(arguments->sheet_index);
    const measure::Board board = measure::read_board(
        sexpr_loads(pcb), parse_json_text(project, arguments->project),
        parse_json_text(sheet_index, arguments->sheet_index));
    const measure::Report report = measure::measure_board(board, arguments->options);
    const std::string json = measure::report_json(
        report, {identity(arguments->pcb, pcb), identity(arguments->project, project),
                 identity(arguments->sheet_index, sheet_index)});
    if (!arguments->map.empty()) write_text(arguments->map, measure::report_map(board, report));
    if (arguments->output.empty()) {
        std::cout << json;
        return 0;
    }
    write_text(arguments->output, json);
    std::cout << "measure: " << report.width << " x " << report.height << " mm, "
              << report.parts << " parts, report " << arguments->output << "\n";
    return 0;
}

}
