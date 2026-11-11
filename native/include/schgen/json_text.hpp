#pragma once

#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace schgen::json_text {

using Field = std::pair<std::string, std::string>;

std::string text_value(std::string_view text);
std::string integer(long long value);
std::string boolean(bool value);
std::string number(double value);
std::string object(const std::vector<Field>& fields);
std::string array(const std::vector<std::string>& values);
std::string names(const std::vector<std::string>& values);
std::string pretty(const std::string& compact);

}
