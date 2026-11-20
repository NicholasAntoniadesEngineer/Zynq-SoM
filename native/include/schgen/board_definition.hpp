#pragma once

#include "schgen/json.hpp"

#include <filesystem>
#include <optional>
#include <string>
#include <vector>

namespace schgen {

inline constexpr const char* board_schema = "schgen.board/1";
inline constexpr const char* board_file = "board.json";

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
    std::string connector_part;
    BoardLoad draw;
    double sdio_level_v = 0.0;
    std::vector<std::string> sd_bus;
    std::vector<BoardPair> pairs;
    std::vector<BoardLoad> loads;
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
    bool root_readme = false, owned_groups = false;
};

struct BoardHeader {
    BoardFiles files;
    BoardFlags flags;
};

struct BoardDefinition {
    std::string name;
    BoardFiles files;
    BoardFlags flags;
    BoardModule module;
    std::vector<BoardSheet> sheets;
    const BoardSheet& sheet(const std::string& name) const;
};

BoardHeader board_header_of(const JsonNode& document, const std::string& source);
BoardHeader load_board_header(const std::filesystem::path& board_root);
BoardDefinition parse_board(const JsonNode& document, const std::string& source);
BoardDefinition load_board(const std::filesystem::path& board_root);

}
