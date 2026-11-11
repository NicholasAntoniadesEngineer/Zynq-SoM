#pragma once

#include <string_view>

namespace schgen {

struct NamedConstant {
    std::string_view name;
    double value;
    std::string_view unit;
    std::string_view proof;
    std::string_view basis;
};

}
