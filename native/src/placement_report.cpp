#include "schgen/placement_report.hpp"

#include <iomanip>
#include <locale>
#include <sstream>

namespace schgen {

std::string placement_report_number(double value) {
    std::ostringstream out;
    out.imbue(std::locale::classic());
    out << std::fixed << std::setprecision(static_cast<int>(placement_report_constants::report_decimals.value)) << value;
    std::string text = out.str();
    if (text.front() == '-' && text.find_first_not_of("-0.") == std::string::npos) text.erase(text.begin());
    return text;
}

std::string placement_report_row(const std::vector<std::string>& cells) {
    std::string row;
    for (const std::string& cell : cells) row += (row.empty() ? "" : "\t") + cell;
    return row;
}

}
