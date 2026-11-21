#pragma once

#include "schgen/json.hpp"

#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace schgen {

inline constexpr const char* board_schema = "schgen.board/1";
inline constexpr const char* board_file = "board.json";
inline constexpr const char* module_schema = "schgen.module/1";
inline constexpr const char* module_file = "module.json";
inline constexpr const char* module_interface_file = "som_interface.json";

struct BoardPair {
    std::string positive, negative, kind;
    std::optional<int> impedance;
};

struct BoardLoad {
    std::string connector, rail;
    double amps = 0.0;
    std::string note;
};

struct BoardModule {
    std::string folder;
    std::vector<BoardPair> pairs;
    std::vector<BoardLoad> loads;
};

struct ModuleReturnPath {
    int n_pairs = 0, n_pair_contacts = 0, n_fail = 0, worst_distance = 0;
};

struct PowerSupply {
    std::string rail;
    double volts = 0.0, amps = 0.0;
    std::string basis;
};

struct BoardSource {
    std::string rail;
    bool from_module = false;
    double volts = 0.0, amps = 0.0;
    std::string basis;
};

struct BoardRail {
    std::string rail;
    std::optional<double> volts;
    std::string basis;
};

struct BoardInlet {
    std::string rail, bulk;
};

struct BoardPower {
    std::vector<BoardSource> sources;
    std::vector<BoardRail> rails;
    std::optional<BoardInlet> inlet;
};

struct ModuleTriageRule {
    std::string pattern, klass, note;
};

struct ModuleDefinition {
    std::string schematic, pcb, connector_part, controller_ref, fpga_ref;
    BoardLoad draw;
    double sdio_level_v = 0.0;
    std::vector<std::string> sd_bus;
    std::vector<BoardPair> pairs;
    std::map<std::string, int> netted_contacts;
    ModuleReturnPath return_path;
    std::vector<ModuleTriageRule> escape_triage;
    std::vector<std::string> do_not_load_straps;
    std::string mate_symbol;
    std::map<std::string, std::string> mate_pad_names;
    std::vector<PowerSupply> supplies;
    std::vector<std::string> regulated_rails;
    std::string regulated_rails_basis;
};

struct BoardSheet {
    std::string name;
    std::string module_connector, title;
    JsonNode settings;
    std::optional<JsonNode> additions;
    bool from_module() const { return !module_connector.empty(); }
};

struct BoardFiles {
    std::string stem;
};

struct BoardFlags {
    bool root_readme = false;
    std::vector<std::string> owned_groups;
};

struct BoardHeader {
    BoardFiles files;
    BoardFlags flags;
    std::string module_folder;
};

inline const std::vector<std::string>& connector_handling_classes() {
    static const std::vector<std::string> classes{"grip_sides", "latch", "card", "flat_cable", "pins", "none"};
    return classes;
}

struct BoardAccess {
    std::string handling;
    double side_mm = 0, front_mm = 0;
    std::string basis;
};

struct BoardFunction {
    std::string sheet, reference, serves, basis;
};

struct BoardLayout {
    bool stated = false;
    std::vector<BoardAccess> access;
    std::vector<BoardFunction> functions;
};

struct BoardDefinition {
    std::string name;
    BoardLayout layout;
    BoardFiles files;
    BoardFlags flags;
    BoardModule module;
    ModuleDefinition module_definition;
    BoardPower power;
    std::vector<BoardSheet> sheets;
    const BoardSheet& sheet(const std::string& name) const;
};

const std::vector<DocumentKey>& board_document_keys();
BoardHeader board_header_of(const JsonNode& document, const std::string& source);
BoardHeader load_board_header(const std::filesystem::path& board_root);
std::filesystem::path module_root_in(const std::filesystem::path& repository, const std::filesystem::path& board_root);
std::filesystem::path module_root_of(const std::filesystem::path& board_root);
ModuleDefinition parse_module(const JsonNode& document, const std::string& source);
ModuleDefinition load_module(const std::filesystem::path& module_root);
ModuleDefinition load_board_module(const std::filesystem::path& board_root);
BoardPower parse_board_power(const JsonNode& node, const std::string& source);
BoardDefinition parse_board(const JsonNode& document, const std::string& source, ModuleDefinition module_definition);
BoardDefinition load_board(const std::filesystem::path& board_root);
BoardDefinition load_board(const std::filesystem::path& board_root, ModuleDefinition module);

}
