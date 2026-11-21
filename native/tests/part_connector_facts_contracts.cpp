#include "schgen/part_facts.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

using namespace schgen;

namespace fixture {
const std::string head = "{\"schema\": \"schgen.part_facts/4\", \"classes\": {\"P1:P1\": \"connector\", \"Device:R\": \"resistor\"}, ";
const std::string tail = ", \"stated_heights\": {}, \"thermal\": {}, \"thermal_copper\": {}, \"ep_vias\": {}, \"isolation\": {}, \"regulators\": {}, \"zeners\": {}, \"reference_pins\": {}, \"control_grid\": {}, \"model_overrides\": {}, \"footprint_aliases\": {}, \"i2c_devices\": {}, \"i2c_bridges\": {}}";
const std::string good_entry =
    "{\"mating_face\": \"-X\", \"edge_pinned\": true, \"overmold\": false, \"pad_row_face_check\": true, "
    "\"description\": \"fixture socket\", \"numbered_label\": \"SOCK\", \"pair_label\": \"PAIR\"}";
const std::string plain_entry =
    "{\"mating_face\": \"+Y\", \"edge_pinned\": false, \"overmold\": true, \"pad_row_face_check\": false}";
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

PartFacts facts_from(const std::filesystem::path& scratch, const std::string& connectors) {
    const auto file = scratch / "facts.json";
    std::ofstream(file, std::ios::binary) << fixture::head << "\"connectors\": " << connectors << fixture::tail;
    return load_part_facts(file);
}

void entries_are_read(const std::filesystem::path& scratch) {
    const PartFacts good = facts_from(scratch, "{\"P1\": " + fixture::good_entry + "}");
    const ConnectorFact& fact = connector_fact_of(good.connectors, "P1");
    require(fact.mating_face == "-X" && fact.edge_pinned && !fact.overmold && fact.pad_row_face_check,
            "an entry carries its face and its flags");
    require(fact.description == "fixture socket" && fact.numbered_label == "SOCK" && fact.pair_label == "PAIR",
            "an entry carries its optional strings");
    require(mating_face_vector(fact) == std::make_pair(-1, 0), "a -X face is the vector (-1, 0)");
    const PartFacts plain = facts_from(scratch, "{\"P1\": " + fixture::plain_entry + "}");
    const ConnectorFact& other = connector_fact_of(plain.connectors, "P1");
    require(!other.description && !other.numbered_label && !other.pair_label, "absent optional strings stay absent");
    require(mating_face_vector(other) == std::make_pair(0, 1), "a +Y face is the vector (0, 1)");
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
    refuses([&] { facts_from(scratch, with("\"-X\"", "\"+Z\"")); }, "mating_face", "a face off the four directions is refused");
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
    std::ofstream(file, std::ios::binary) << fixture::head.substr(0, fixture::head.size() - 2) << fixture::tail;
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
        require((vector.first == 0) != (vector.second == 0), name + " faces along exactly one axis");
    }
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
        repository_entries_are_whole(std::filesystem::absolute(argv[1]));
        std::cout << "connector facts contracts ok\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 1;
    }
}
