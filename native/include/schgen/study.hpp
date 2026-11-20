#pragma once

#include "schgen/json.hpp"
#include "schgen/named_constant.hpp"
#include "schgen/run_config.hpp"
#include "schgen/stackup.hpp"

#include <array>
#include <filesystem>
#include <optional>
#include <string>
#include <vector>

namespace schgen::study {

namespace constants {
inline constexpr NamedConstant lower_impedance{"lower_impedance", 90, "ohm", "report",
    "lower differential impedance the comparison lists a pair width for"};
inline constexpr NamedConstant upper_impedance{"upper_impedance", 100, "ohm", "report",
    "upper differential impedance the comparison lists a pair width for"};
inline constexpr std::array study_registry{lower_impedance, upper_impedance};
}

inline constexpr const char* layers_subject = "layers";
inline constexpr const char* stackups_option = "--stackups";
inline constexpr const char* study_folder = "study";
inline constexpr const char* reports_folder = "reports";
inline constexpr const char* verdict_report = "board_verdicts.json";
inline constexpr const char* squeeze_report = "layout_squeeze.txt";
inline constexpr const char* table_schema = "schgen.study.layers/1";

struct Cell {
    std::string key, title, text;
    JsonNode value;
};

struct Row {
    std::string stackup;
    std::filesystem::path output;
    std::vector<Cell> cells;
    std::vector<std::string> notes;
};

std::vector<std::string> stackups_of(const RunConfig& config, const RunArguments& request);
RunConfig row_config(const RunConfig& config, const std::string& board, const std::string& stackup);
std::filesystem::path table_file(const RunConfig& config, const std::string& board, const std::string& extension);
std::vector<Cell> stackup_cells(const Stackup& stackup);
std::vector<Cell> layout_cells(const std::optional<std::string>& report);
std::vector<Cell> gate_cells(const std::optional<JsonNode>& verdict, int status, std::vector<std::string>& notes);
Row measured_row(const Stackup& stackup, const std::filesystem::path& output, int status);
std::string table(const std::string& board, const std::vector<Row>& rows);
std::string document(const std::string& board, const std::vector<Row>& rows);

}

namespace schgen {

std::optional<int> study_command(int argc, char** argv);

}
