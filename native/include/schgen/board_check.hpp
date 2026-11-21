#pragma once

#include <filesystem>
#include <string>
#include <vector>

namespace schgen {

enum class RequirementStatus { present, missing, invalid, absent, blocked };

struct BoardRequirement {
    std::string file, item;
    bool required = true;
    RequirementStatus status = RequirementStatus::blocked;
    std::string message;
};

struct BoardDefinitionCheck {
    std::string board;
    std::vector<BoardRequirement> rows;
    bool ok() const;
    std::string text() const;
};

const char* requirement_status_name(RequirementStatus status);
BoardDefinitionCheck check_board_definition(const std::filesystem::path& repository, const std::filesystem::path& board_root,
                                            const std::filesystem::path& run_config);

}
