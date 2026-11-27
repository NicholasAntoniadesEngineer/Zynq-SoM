#include "schgen/part_facts.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

using namespace schgen;

namespace fixture {
constexpr double plug_width = 12.5, access_side = 25, path_depth = 6, path_width = 3, path_clear = 1.5;
constexpr double cell_diameter = 12.5, holder_height = 4;
const std::string holder = "KH-CR1220-2";
const std::string good_path =
    "{\"entry\": {\"face\": \"-X\", \"cite\": \"fixture drawing, view A\"}, \"depth\": {\"mm\": 6, \"cite\": \"fixture drawing, plug length\"}, "
    "\"width\": {\"mm\": 3, \"cite\": \"fixture drawing, plug width\"}, \"clear_height\": {\"mm\": 1.5, \"cite\": \"fixture drawing, plug underside\"}}";
const std::string head = "{\"schema\": \"schgen.part_facts/6\", \"classes\": {\"P1:P1\": \"connector\", \"Device:R\": \"resistor\"}, ";
const std::string tail = ", \"stated_heights\": {}, \"plug_paths\": PATHS, \"thermal\": {}, \"thermal_copper\": {}, \"ep_vias\": {}, \"isolation\": {}, \"regulators\": {}, \"zeners\": {}, \"reference_pins\": {}, \"control_grid\": {}, \"model_overrides\": {}, \"footprint_aliases\": {}, \"i2c_devices\": {}, \"i2c_bridges\": {}, \"lands\": {}, \"electrical_spacing\": {\"source\": \"fixture\", \"column\": \"B2\", \"basis\": \"fixture\", \"rows\": [{\"max_volts\": 30, \"spacing_mm\": 0.1}]}}";
const std::string good_entry =
    "{\"mating_face\": \"-X\", \"edge_pinned\": true, \"overmold\": false, \"pad_row_face_check\": true, "
    "\"handling\": \"grip_sides\", \"mating\": {\"plug_width_mm\": 12.5, \"plug_depth_mm\": null, \"plug_height_mm\": null, "
    "\"cite\": \"fixture drawing\"}, \"access\": {\"side_mm\": 25, \"front_mm\": 0, \"cite\": \"fixture standard\"}, "
    "\"description\": \"fixture socket\", \"numbered_label\": \"SOCK\", \"pair_label\": \"PAIR\"}";
const std::string plain_entry =
    "{\"mating_face\": \"+Z\", \"face_cite\": \"fixture drawing, top view\", \"edge_pinned\": false, \"overmold\": true, \"pad_row_face_check\": false, \"handling\": \"none\", "
    "\"access\": {\"side_mm\": 0, \"front_mm\": 0, \"cite\": \"fixture: mated once at assembly\"}}";
}

void require(bool condition, const std::string& what) {
    if (!condition) throw std::runtime_error("connector facts contract failed: " + what);
}

template <typename Action>
void refuses(Action action, const std::string& names, const std::string& what) {
    try {
        action();
    } catch (const std::runtime_error& error) {
        require(std::string(error.what()).find(names) != std::string::npos, what + " names " + names);
        return;
    }
    throw std::runtime_error("connector facts contract failed: " + what);
}

std::string tail_with(const std::string& paths) {
    const std::string mark = "PATHS";
    std::string text = fixture::tail;
    text.replace(text.find(mark), mark.size(), paths);
    return text;
}

PartFacts facts_from(const std::filesystem::path& scratch, const std::string& connectors, const std::string& paths = "{}") {
    const auto file = scratch / "facts.json";
    std::ofstream(file, std::ios::binary) << fixture::head << "\"connectors\": " << connectors << tail_with(paths);
    return load_part_facts(file);
}

void plug_paths_are_read_and_refused(const std::filesystem::path& scratch) {
    std::filesystem::create_directories(scratch / "P1");
    const auto inboard = [&] {
        std::string text = fixture::good_entry;
        const std::string pinned = "\"edge_pinned\": true", described = "\"description\": \"fixture socket\", ";
        text.replace(text.find(pinned), pinned.size(), "\"edge_pinned\": false");
        text.erase(text.find(described), described.size());
        return "{\"P1\": " + text + "}";
    }();
    const auto path_with = [&](const std::string& from, const std::string& to) {
        std::string text = fixture::good_path;
        text.replace(text.find(from), from.size(), to);
        return "{\"P1\": " + text + "}";
    };
    const PartFacts good = facts_from(scratch, inboard, "{\"P1\": " + fixture::good_path + "}");
    const PlugPathFact& path = part_fact_of(good.plug_paths, "P1", "plug_paths");
    require(!connector_fact_of(good.connectors, "P1").edge_pinned, "a connector mated from the side may sit inside the board once it states a plug path");
    require(path.face == "-X" && path.face_cite == "fixture drawing, view A" && plug_path_vector(path) == std::make_pair(-1, 0),
            "a plug path carries the side it is entered from and that side's cite");
    require(path.depth_mm == fixture::path_depth && path.depth_cite == "fixture drawing, plug length", "a plug path carries its depth and cite");
    require(path.width_mm == fixture::path_width && path.width_cite == "fixture drawing, plug width", "a plug path carries its stated width and cite");
    require(path.clear_height_mm == fixture::path_clear && path.clear_height_cite == "fixture drawing, plug underside",
            "a plug path carries its clear height and cite");
    const PartFacts bare = facts_from(scratch, inboard, path_with("\"width\": {\"mm\": 3, \"cite\": \"fixture drawing, plug width\"}, ", ""));
    require(!part_fact_of(bare.plug_paths, "P1", "plug_paths").width_mm, "an unstated width stays unstated, to be taken from the body");
    refuses([&] { facts_from(scratch, inboard); }, "must be edge-pinned", "a side-mated connector inside the board with no plug path is refused");
    refuses([&] { facts_from(scratch, inboard, path_with("\"-X\"", "\"+Y\"")); }, "mating_face",
            "a plug path on another side than the mating face is refused");
    refuses([&] { facts_from(scratch, inboard, path_with("\"-X\"", "\"+Z\"")); }, "face", "a plug path from above is refused");
    refuses([&] { facts_from(scratch, inboard, path_with("\"mm\": 6", "\"mm\": 0")); }, "above zero", "a plug path of no depth is refused");
    refuses([&] { facts_from(scratch, inboard, path_with("\"mm\": 1.5", "\"mm\": -1")); }, "negative", "a negative clear height is refused");
    refuses([&] { facts_from(scratch, inboard, path_with(", \"cite\": \"fixture drawing, plug length\"", "")); }, "cite",
            "a depth without a cite is refused");
    refuses([&] { facts_from(scratch, inboard, path_with(", \"cite\": \"fixture drawing, view A\"", "")); }, "cite",
            "an entry side without a cite is refused");
    refuses([&] { facts_from(scratch, inboard, path_with(", \"cite\": \"fixture drawing, plug width\"", "")); }, "cite",
            "a width without a cite is refused");
    refuses([&] { facts_from(scratch, inboard, path_with(", \"cite\": \"fixture drawing, plug underside\"", "")); }, "cite",
            "a clear height without a cite is refused");
    refuses([&] { facts_from(scratch, inboard, path_with("\"depth\"", "\"reach\"")); }, "reach", "an unknown key is refused");
    refuses([&] { facts_from(scratch, inboard, path_with("\"mm\": 6", "\"mm\": 6, \"margin\": 1")); }, "margin",
            "an unknown key inside a figure is refused");
    refuses([&] { facts_from(scratch, inboard, "{\"P9\": " + fixture::good_path + "}"); }, "P9", "a plug path for a part with no folder is refused");
    const auto file = scratch / "pathless.json";
    std::string tail = tail_with("{}");
    const std::string section = "\"plug_paths\": {}, ";
    tail.erase(tail.find(section), section.size());
    std::ofstream(file, std::ios::binary) << fixture::head << "\"connectors\": {\"P1\": " << fixture::good_entry << "}" << tail;
    refuses([&] { load_part_facts(file); }, "plug_paths", "a facts file without the section is refused");
}

void entries_are_read(const std::filesystem::path& scratch) {
    const PartFacts good = facts_from(scratch, "{\"P1\": " + fixture::good_entry + "}");
    const ConnectorFact& fact = connector_fact_of(good.connectors, "P1");
    require(fact.mating_face == "-X" && fact.edge_pinned && !fact.overmold && fact.pad_row_face_check,
            "an entry carries its face and its flags");
    require(fact.description == "fixture socket" && fact.numbered_label == "SOCK" && fact.pair_label == "PAIR",
            "an entry carries its optional strings");
    require(mating_face_vector(fact) == std::make_pair(-1, 0), "a -X face is the vector (-1, 0)");
    require(fact.handling == "grip_sides" && fact.mating && fact.mating->plug_width_mm == fixture::plug_width && !fact.mating->plug_depth_mm &&
                fact.mating->cite == "fixture drawing",
            "an entry carries its handling class and its cited plug envelope");
    require(fact.access && fact.access->side_mm == fixture::access_side && fact.access->front_mm == 0, "an entry carries its own access clearance");
    const PartFacts plain = facts_from(scratch, "{\"P1\": " + fixture::plain_entry + "}");
    const ConnectorFact& other = connector_fact_of(plain.connectors, "P1");
    require(!other.description && !other.numbered_label && !other.pair_label, "absent optional strings stay absent");
    require(other.handling == "none" && !other.mating && other.access && other.access->side_mm == 0, "an absent envelope stays absent and a zero access is stated");
    require(mating_face_vector(other) == std::make_pair(0, 0), "a face mated from above has no direction in the board plane");
    require(connector_fact(plain.connectors, "Device:R") == nullptr, "a name without an entry has no fact");
    refuses([&] { connector_fact_of(plain.connectors, "R1"); }, "R1", "a required fact for an unknown name is refused");
}

void entries_are_refused(const std::filesystem::path& scratch) {
    const auto with = [&](const std::string& from, const std::string& to) {
        std::string text = fixture::good_entry;
        text.replace(text.find(from), from.size(), to);
        return "{\"P1\": " + text + "}";
    };
    refuses([&] { facts_from(scratch, with("\"overmold\"", "\"overmolded\"")); }, "overmolded", "an unknown key is refused");
    refuses([&] { facts_from(scratch, with("\"edge_pinned\": true", "\"edge_pinned\": \"yes\"")); }, "edge_pinned",
            "a flag that is not true or false is refused");
    refuses([&] { facts_from(scratch, with("\"-X\"", "\"-Z\"")); }, "mating_face", "a face through the board is refused");
    refuses([&] { facts_from(scratch, with("\"-X\"", "\"+Z\"")); }, "edge-pinned", "a connector mated from above cannot be edge-pinned");
    refuses([&] { facts_from(scratch, "{\"P1\": " + [&] { std::string text = fixture::plain_entry; const std::string cite = "\"face_cite\": \"fixture drawing, top view\", "; text.erase(text.find(cite), cite.size()); return text; }() + "}"); },
            "face_cite", "a connector said to mate from above without a source is refused");
    refuses([&] { facts_from(scratch, with("\"edge_pinned\": true", "\"edge_pinned\": false")); }, "must be edge-pinned",
            "a connector mated from the side that is not edge-pinned is refused");
    refuses([&] { facts_from(scratch, with("\"handling\": \"grip_sides\", ", "")); }, "handling", "an entry without a handling class is refused");
    refuses([&] { facts_from(scratch, with("\"grip_sides\"", "\"gloves\"")); }, "handling", "an unknown handling class is refused");
    refuses([&] { facts_from(scratch, with("\"cite\": \"fixture drawing\"", "\"cite\": null")); }, "cite",
            "a stated plug dimension without a cite is refused");
    refuses([&] { facts_from(scratch, with("\"access\": {\"side_mm\": 25, \"front_mm\": 0, \"cite\": \"fixture standard\"}, ", "")); }, "access",
            "a connector without an access clearance is refused");
    refuses([&] { facts_from(scratch, with(", \"cite\": \"fixture standard\"", "")); }, "cite", "an access clearance without a cite is refused");
    refuses([&] { facts_from(scratch, with("\"description\": \"fixture socket\"", "\"description\": 4")); }, "description",
            "a description that is not text is refused");
    refuses([&] { facts_from(scratch, with("\"description\": \"fixture socket\", ", "")); }, "description",
            "an edge-pinned connector without a description is refused");
    refuses([&] { facts_from(scratch, with("\"mating_face\": \"-X\", ", "")); }, "mating_face", "an entry without a face is refused");
    refuses([&] { facts_from(scratch, "{\"P2\": " + fixture::plain_entry + "}"); }, "P2",
            "an entry without a connector symbol is refused");
    refuses([&] { facts_from(scratch, "{}"); }, "P1:P1", "a connector symbol without an entry is refused");
    refuses([&] { facts_from(scratch, "[]"); }, "connectors", "a section that is not an object is refused");
    refuses([&] { facts_from(scratch, "{\"P1\": 3}"); }, "P1", "an entry that is not an object is refused");
    const auto file = scratch / "missing.json";
    std::ofstream(file, std::ios::binary) << fixture::head.substr(0, fixture::head.size() - 2) << tail_with("{}");
    refuses([&] { load_part_facts(file); }, "connectors", "a facts file without the section is refused");
}

void repository_entries_are_whole(const std::filesystem::path& repository) {
    const ConnectorFacts connectors = load_connector_facts(repository / "parts");
    require(!connectors.empty(), "the repository states connector facts");
    const PartFacts facts = load_part_facts(repository / "parts" / "part_facts.json");
    for (const auto& [name, fact] : connectors) {
        require(facts.classes.at(name + ":" + name) == PartClass::connector, name + " is a connector symbol");
        require(!fact.edge_pinned || fact.description, name + " is described when it is edge-pinned");
        const auto vector = mating_face_vector(fact);
        const bool from_above = vector.first == 0 && vector.second == 0;
        require(from_above || (vector.first == 0) != (vector.second == 0), name + " faces along one axis or is mated from above");
        require(!from_above || !fact.edge_pinned, name + " is not edge-pinned when it is mated from above");
        require(from_above || fact.edge_pinned || facts.plug_paths.count(name) != 0,
                name + " is edge-pinned or states a plug path when it is mated from the side");
    }
    const PlugPathFact& holder = part_fact_of(facts.plug_paths, fixture::holder, "plug_paths");
    require(facts.classes.at(fixture::holder + ":" + fixture::holder) == PartClass::battery_holder, "the cell holder is not a connector");
    require(plug_path_vector(holder) == std::make_pair(-1, 0), "the cell holder is entered over its flat side");
    require(holder.depth_mm == fixture::cell_diameter && holder.width_mm == fixture::cell_diameter,
            "the cell holder's path is one cell long and one cell wide");
    require(holder.clear_height_mm == fixture::holder_height, "parts no taller than the holder body may stand in its path");
    for (const auto& [name, path] : facts.plug_paths)
        require(!path.face_cite.empty() && !path.depth_cite.empty() && !path.clear_height_cite.empty() &&
                    (!path.width_mm || (path.width_cite && !path.width_cite->empty())),
                name + " cites every figure of its plug path");
}

}

int main(int argc, char** argv) {
    try {
        if (argc != 3) throw std::runtime_error("usage: part_connector_facts_contracts REPOSITORY SCRATCH");
        const std::filesystem::path scratch = argv[2];
        std::filesystem::remove_all(scratch);
        std::filesystem::create_directories(scratch);
        entries_are_read(scratch);
        entries_are_refused(scratch);
        plug_paths_are_read_and_refused(scratch);
        repository_entries_are_whole(std::filesystem::absolute(argv[1]));
        std::cout << "connector facts contracts ok\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 1;
    }
}
