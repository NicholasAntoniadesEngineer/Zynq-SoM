#pragma once

#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace schgen {

using ReorderPos = std::tuple<std::string, double, double>;
using ReorderReport = std::tuple<std::string, std::string, int, int>;

std::vector<std::tuple<std::string, std::string, double, bool,
                       std::vector<std::string>>>
group_interchangeable(
    const std::vector<
        std::tuple<std::string, std::string, std::string, double, bool>>& rows);

std::tuple<std::vector<ReorderPos>, std::vector<ReorderReport>>
reorder_interchangeable(
    const std::vector<ReorderPos>& pos,
    const std::vector<std::tuple<std::string, std::vector<std::string>>>&
        sheets,
    const std::vector<std::string>& skip_sheets,
    const std::vector<std::string>& conn_seated,
    const std::vector<
        std::tuple<std::string, std::string, std::string, double, bool>>&
        members,
    const std::vector<std::tuple<std::string, double, double, double, double>>&
        bboxes,
    const std::vector<std::tuple<std::string, std::vector<std::string>>>&
        pad_names,
    const std::vector<std::tuple<
        std::string, std::vector<std::tuple<std::string, double, double>>>>&
        pad_local,
    const std::vector<std::tuple<std::string, std::string, std::string>>&
        pin_net,
    const std::vector<std::tuple<
        std::string, std::vector<std::pair<std::string, std::string>>>>& nets,
    const std::vector<std::string>& resolvable);

}
