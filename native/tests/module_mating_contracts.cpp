#include "schgen/board_definition.hpp"
#include "schgen/board_schematic.hpp"
#include "schgen/footprint_pads.hpp"
#include "schgen/json.hpp"
#include "schgen/module_mating.hpp"
#include "schgen/project.hpp"
#include "schgen/quantize.hpp"
#include "schgen/sexpr.hpp"
#include "schgen/som_interface.hpp"

#include <algorithm>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>

namespace {

using namespace schgen;

const char* const project_name = "carrier";
const char* const footprint_table = "fp-lib-table";
constexpr double half_turn = 180;

std::size_t checks = 0;

void require(bool ok, const std::string& why) {
    ++checks;
    if (!ok) throw std::runtime_error("module mating contract: " + why);
}

std::string read(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("cannot read " + path.string());
    return {std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};
}

PcbCheckFootprintPtr footprint(const std::filesystem::path& file) { return pcb_check_footprint(file.string(), read(file)); }

struct Live {
    std::vector<ModuleMate> mates;
    std::vector<ModuleConnectorGeom> jacks;
    std::map<std::string, PcbCheckFootprintPtr> carrier_footprint, mate_footprint, part_footprint;
    std::map<std::string, std::string> carrier_ref;
    std::map<std::string, std::set<std::string>> pins;
    double module_w = 0.0;
};

Live live(const std::filesystem::path& root) {
    Live out;
    const auto paths = resolve_project_paths(root, std::string(project_name));
    const auto iface = som_interface_from_json(parse_json_file(paths.som_interface_file.string()), paths.som_interface_file.string());
    std::vector<std::string> names;
    for (const auto& [ref, connector] : iface.connectors) names.push_back(ref);
    const auto som = extract_som_scan(read(paths.som_pcb), names);
    out.module_w = som.w;
    FootprintResolutionOptions module_tables;
    module_tables.library_tables = {paths.module_root / footprint_table};
    const auto module_libraries = load_footprint_library_tables(module_tables);
    FootprintResolutionOptions part_tables = module_tables;
    part_tables.parts_dir = paths.parts_dir;
    const auto part_libraries = load_footprint_library_tables(part_tables);
    for (const auto& jack : som.js) {
        const auto& connector = std::find_if(iface.connectors.begin(), iface.connectors.end(),
                                             [&](const auto& row) { return row.first == jack.ref; })->second;
        const auto file = resolve_footprint(connector.footprint.value_or(""), module_libraries, module_tables);
        require(file.has_value(), "the module interface's mate footprint for " + jack.ref + " resolves in the module folder");
        out.mate_footprint[jack.ref] = footprint(*file);
        for (const auto& [pin, net] : connector.pins) { (void)net; out.pins[jack.ref].insert(pin); }
        const auto fitted = fit_module_mate(jack, *out.mate_footprint[jack.ref], out.pins[jack.ref]);
        out.jacks.push_back(fitted);
        ModuleMate mate;
        mate.connector = jack.ref;
        mate.turn = fitted.turn;
        mate.mate = fitted.mate;
        for (const auto& pad : fitted.pads)
            if (out.pins[jack.ref].count(pad.pin)) mate.receptacle.push_back(pad);
        out.mates.push_back(std::move(mate));
    }
    const auto board = load_board(paths.project_root);
    const auto index = load_sheet_index(paths);
    const auto circuits = load_project_circuits(paths);
    for (const auto& sheet : board.sheets) {
        if (!sheet.from_module()) continue;
        const auto circuit = std::find_if(circuits.begin(), circuits.end(), [&](const auto& c) { return c.name == sheet.name; });
        const auto band = std::find_if(index.begin(), index.end(), [&](const auto& row) { return row.first == sheet.name; });
        require(circuit != circuits.end() && band != index.end() && circuit->circuit.parts.size() == 1,
                "module connector sheet " + sheet.name + " holds exactly one part");
        const auto& part = circuit->circuit.parts.front();
        const auto file = resolve_footprint(part.footprint, part_libraries, part_tables);
        require(file.has_value(), sheet.name + " footprint " + part.footprint + " resolves");
        out.carrier_footprint[sheet.module_connector] = footprint(*file);
        const auto library = part.lib_id.substr(0, part.lib_id.find(':'));
        const auto own = parse_json_file((paths.parts_dir / library / "part.json").string());
        const auto* own_id = object_field(own, "footprint");
        require(own_id && own_id->kind == JsonKind::String, library + " part.json states its footprint");
        const auto own_file = resolve_footprint(own_id->string_value, part_libraries, part_tables);
        require(own_file.has_value(), "the part folder footprint of " + library + " resolves");
        out.part_footprint[sheet.module_connector] = footprint(*own_file);
        out.carrier_ref[sheet.module_connector] = board_renamed_ref(part.ref, band->second, sheet.name);
    }
    for (auto& mate : out.mates) mate.ref = out.carrier_ref.at(mate.connector);
    require(out.carrier_ref.size() == out.mates.size(), "every module connector has one carrier sheet");
    return out;
}

std::vector<PcbCheckInstance> ideal(const Live& data, bool mate_footprint) {
    std::vector<PcbCheckInstance> out;
    for (const auto& jack : data.jacks) {
        PcbCheckInstance instance;
        instance.ref = data.carrier_ref.at(jack.ref);
        instance.mod = (mate_footprint ? data.mate_footprint : data.carrier_footprint).at(jack.ref);
        instance.x = quantization_policy::kPageOriginMm + jack.x;
        instance.y = quantization_policy::kPageOriginMm + jack.y;
        instance.rotation = jack.turn;
        out.push_back(instance);
    }
    return out;
}

ModuleMatingJudgement judge(const Live& data, const std::vector<PcbCheckInstance>& parts, bool declared = true) {
    std::map<std::string, const PcbCheckInstance*> carrier;
    for (const auto& mate : data.mates)
        for (const auto& part : parts)
            if (part.ref == mate.ref) carrier[mate.connector] = &part;
    const std::pair<double, double> origin{quantization_policy::kPageOriginMm, quantization_policy::kPageOriginMm};
    return judge_module_mating(data.mates, carrier, declared ? std::optional<std::pair<double, double>>(origin) : std::nullopt);
}

void show(const std::string& label, const ModuleMatingJudgement& judged) {
    std::cout << label << ": " << (judged.ok() ? "PASS" : "FAIL") << "\n";
    for (const auto& connector : judged.connectors) {
        std::cout << "  " << connector.ref << " mates module " << connector.connector << ": worst pad error "
                  << connector.worst_pad_error << " mm, row inset " << connector.row_inset << " mm, " << connector.findings.size()
                  << " findings";
        if (!connector.findings.empty())
            std::cout << "; first: pin " << connector.findings.front().pin << " " << connector.findings.front().detail;
        std::cout << "\n";
    }
}

std::vector<PcbCheckInstance> judged_board(const Live& data, const std::filesystem::path& file) {
    const auto document = sexpr_loads(read(file));
    std::vector<PcbCheckInstance> out;
    const auto& top = std::get<SexprList>(document.v);
    const auto head = [](const Sexpr& node) -> std::string {
        if (!std::holds_alternative<SexprList>(node.v)) return {};
        const auto& list = std::get<SexprList>(node.v);
        return list.empty() || !std::holds_alternative<Sexpr::Sym>(list.front().v) ? std::string{}
                                                                                    : std::get<Sexpr::Sym>(list.front().v).name;
    };
    for (const auto& node : top) {
        if (head(node) != "footprint") continue;
        const auto& list = std::get<SexprList>(node.v);
        std::string ref;
        std::vector<double> at;
        for (const auto& child : list) {
            if (head(child) == "property") {
                const auto& row = std::get<SexprList>(child.v);
                if (row.size() > 2 && std::get<std::string>(row[1].v) == "Reference") ref = std::get<std::string>(row[2].v);
            } else if (head(child) == "at" && at.empty()) {
                const auto& row = std::get<SexprList>(child.v);
                for (std::size_t i = 1; i < row.size(); ++i) at.push_back(std::get<double>(row[i].v));
            }
        }
        const bool wanted = std::any_of(data.mates.begin(), data.mates.end(), [&](const auto& mate) { return mate.ref == ref; });
        if (!wanted) continue;
        PcbCheckInstance instance;
        instance.ref = ref;
        instance.mod = pcb_check_footprint(file.string() + ":" + ref, sexpr_dumps(node));
        instance.x = at.at(0);
        instance.y = at.at(1);
        instance.rotation = at.size() > 2 ? at[2] : 0.0;
        out.push_back(instance);
    }
    return out;
}

}

int main(int argc, char** argv) {
    try {
        if (argc < 2) throw std::runtime_error("usage: module-mating REPOSITORY [BOARD_EXPECTED_TO_FAIL]...");
        const Live data = live(argv[1]);
        for (const auto& jack : data.jacks)
            std::cout << "module " << jack.ref << ": mate origin (" << jack.x << ", " << jack.y << ") in the module frame, turn "
                      << jack.turn << "; receptacle at (" << jack.pcb_x << ", " << jack.pcb_y << ") rot " << jack.rot
                      << " on the module board\n";
        const auto mate_ideal = judge(data, ideal(data, true));
        show("module-declared mate footprint at the fitted poses", mate_ideal);
        require(mate_ideal.ok(), "the declared mate footprint at its fitted pose mates every pin");
        for (const auto& connector : mate_ideal.connectors)
            require(connector.worst_pad_error <= mating_constants::mate_quantum.value && connector.row_inset > 0 &&
                        connector.row_inset < mating_constants::self_alignment.value,
                    connector.connector + " is exact and its row inset is a real land-pattern difference");
        const auto circuit_ideal = judge(data, ideal(data, false));
        show("carrier circuit footprints at the fitted poses", circuit_ideal);
        require(circuit_ideal.ok(), "the carrier circuits' module connector footprints number their pads like the module mate");
        require(judge(data, ideal(data, true), false).ok(), "a fitted module origin agrees with the declared one");

        auto shifted = ideal(data, true);
        shifted.front().x += quantization_policy::kGridMm;
        show("one connector shifted one placement grid step", judge(data, shifted));
        require(!judge(data, shifted).ok() && !judge(data, shifted, false).ok(), "a one-grid-step shift of one connector fails");

        auto swapped = ideal(data, true);
        std::swap(swapped[0].x, swapped[1].x);
        std::swap(swapped[0].y, swapped[1].y);
        std::swap(swapped[0].rotation, swapped[1].rotation);
        show("two connectors swapped", judge(data, swapped));
        require(!judge(data, swapped).ok() && !judge(data, swapped, false).ok(), "swapping two connectors fails");

        auto turned = ideal(data, true);
        turned.back().rotation += half_turn;
        show("one connector turned 180 degrees", judge(data, turned));
        require(!judge(data, turned).ok() && !judge(data, turned, false).ok(), "a connector turned half a turn fails");

        auto renumbered = ideal(data, true);
        const auto foreign = data.part_footprint.at(data.jacks.front().ref);
        renumbered.front().mod = foreign;
        show("one connector with the part folder's perimeter-numbered land pattern", judge(data, renumbered));
        require(!judge(data, renumbered).ok() && !judge(data, renumbered, false).ok(), "a land pattern numbered unlike the module mate fails");

        auto mirrored = ideal(data, true);
        for (std::size_t i = 0; i < mirrored.size(); ++i) {
            mirrored[i].x = quantization_policy::kPageOriginMm + data.module_w - data.jacks[i].x;
            mirrored[i].rotation = data.jacks[i].w < data.jacks[i].h ? half_turn / 2 : 0.0;
        }
        show("mirrored module frame (the old convention)", judge(data, mirrored));
        require(!judge(data, mirrored).ok() && !judge(data, mirrored, false).ok(), "a mirrored module placement fails");
        for (const auto& jack : data.jacks) {
            ModuleConnectorGeom flipped = jack;
            for (auto& pad : flipped.pads) pad.x = data.module_w - pad.x;
            bool rejected = false;
            try {
                (void)fit_module_mate(flipped, *data.mate_footprint.at(jack.ref), data.pins.at(jack.ref));
            } catch (const std::runtime_error&) {
                rejected = true;
            }
            require(rejected, "a mirrored receptacle " + jack.ref + " has no mating orientation");
        }

        for (int index = 2; index < argc; ++index) {
            const auto judged = judge(data, judged_board(data, argv[index]), false);
            show(std::string("board ") + argv[index], judged);
            require(!judged.ok(), std::string(argv[index]) + " is expected to fail module mating");
        }
        std::cout << "PASS " << checks << " module mating checks\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 1;
    }
}
