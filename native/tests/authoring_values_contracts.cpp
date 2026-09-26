// Value-only regression contracts for the helpers extracted from the model
// checker closure. Expectations below are literal contracts, not generated
// from the implementation under test. No model/geometry header or core archive
// is needed to compile and run this test.
#include "../src/authoring_values.hpp"
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <type_traits>

namespace {
namespace v = schgen::authoring_values;
using schgen::JsonKind;
std::size_t checks = 0;
void require(bool value, const std::string& why) {
    ++checks;
    if (!value) throw std::runtime_error(why);
}

void text_contracts() {
    for (const auto& [input, expected] : std::vector<std::pair<std::string, std::string>>{
            {"", "''"}, {"rail", "'rail'"}, {"don't", "\"don't\""},
            {"say \"yes\"", "'say \"yes\"'"}, {"'\"", "'\\'\"'"},
            {"a\\b", "'a\\\\b'"}, {"\n\r\t", "'\\n\\r\\t'"},
            {std::string("\0\1\x1f\x7f", 4), "'\\x00\\x01\\x1f\\x7f'"},
            {"café μ rail", "'café μ rail'"}, {"+3V3_MINI", "'+3V3_MINI'"}})
        require(v::repr(input) == expected, "repr literal mismatch");

    // Every Python whitespace codepoint admitted by the old helper, including
    // the four ASCII information separators. U+200B and U+FEFF are NOT spaces.
    const std::vector<std::string> spaces{
        "\t", "\n", "\v", "\f", "\r", "\x1c", "\x1d", "\x1e", "\x1f", " ",
        "\xc2\x85", "\xc2\xa0", "\xe1\x9a\x80", "\xe2\x80\x80", "\xe2\x80\x81",
        "\xe2\x80\x82", "\xe2\x80\x83", "\xe2\x80\x84", "\xe2\x80\x85", "\xe2\x80\x86",
        "\xe2\x80\x87", "\xe2\x80\x88", "\xe2\x80\x89", "\xe2\x80\x8a", "\xe2\x80\xa8",
        "\xe2\x80\xa9", "\xe2\x80\xaf", "\xe2\x81\x9f", "\xe3\x80\x80"};
    for (const auto& space : spaces) {
        require(v::trim(space + "P1.2" + space) == "P1.2", "Unicode trim boundary");
        require(v::trim(space).empty(), "all-whitespace trim");
        require(v::trim("x" + space + "y") == "x" + space + "y", "interior whitespace preserved");
    }
    for (const auto& nonspace : std::vector<std::string>{"\xe2\x80\x8b", "\xef\xbb\xbf", std::string("\0", 1)})
        require(v::trim(" " + nonspace + " ") == nonspace, "non-whitespace preserved");
    require(v::trim("").empty(), "empty trim");
    // Preserve old permissive decoding, including malformed byte advancement.
    require(v::trim("\xc0\xa0x\xc0\xa0") == "x", "overlong-space legacy behavior");
    require(v::trim(" \xe2\x80") == "\xe2\x80", "truncated UTF-8 preserved");
    std::size_t i = 0;
    require(v::codepoint("\xe2\x80x", i) == 0xe2 && i == 2, "malformed continuation advancement");
    i = 0;
    require(v::codepoint("\xf0\x9f\x98\x80", i) == 0x1f600 && i == 4, "four-byte codepoint");
    require(v::starts("+3V3", "+") && !v::starts("V+", "+"), "prefix direction");
    require(v::starts("", "") && !v::starts("", "x"), "empty prefix");
    require(!v::starts("GND", "GNDA"), "long prefix");
}

void number_contracts() {
    for (const auto& [value, expected] : std::vector<std::pair<double, std::string>>{
            {0.0, "0"}, {-0.0, "-0"}, {1.0, "1"}, {-1.0, "-1"},
            {0.1, "0.10000000000000001"}, {3.3, "3.2999999999999998"},
            {std::numeric_limits<double>::max(), "1.7976931348623157e+308"},
            {std::numeric_limits<double>::lowest(), "-1.7976931348623157e+308"},
            {std::numeric_limits<double>::min(), "2.2250738585072014e-308"},
            {std::numeric_limits<double>::denorm_min(), "4.9406564584124654e-324"},
            {std::numeric_limits<double>::infinity(), "inf"},
            {-std::numeric_limits<double>::infinity(), "-inf"}})
        require(v::number17(value) == expected, "17-digit diagnostic: expected " + expected + ", got " + v::number17(value));
    // NaN spellings are standard-library-specific (Apple libc++ uses
    // -nan(ind) for this negative quiet NaN). Require the exact platform token,
    // not a normalized or invented portable spelling.
    for (double value : {std::numeric_limits<double>::quiet_NaN(),
            std::copysign(std::numeric_limits<double>::quiet_NaN(), -1.0)}) {
        char expected[64];
        const auto result = std::to_chars(expected, expected + sizeof expected, value, std::chars_format::general, 17);
        require(result.ec == std::errc{} && v::number17(value) == std::string(expected, result.ptr), "platform NaN token unchanged");
    }
}

void containers() {
    std::vector<std::pair<std::string, int>> entries{{"same", 1}, {"same", 2}, {"last", 3}};
    require(v::find(entries, "same") == &entries[0].second, "first duplicate key wins");
    require(v::find(entries, "absent") == nullptr, "missing key");
    *v::find(entries, "last") = 4;
    require(entries[2].second == 4, "borrowed mutable entry");
    const auto& constant = entries;
    static_assert(std::is_same_v<decltype(v::find(constant, "same")), const int*>);
    require(*v::find(constant, "same") == 1, "const lookup");
    entries.clear();
    require(v::find(entries, "same") == nullptr, "empty lookup");
    require(v::j("false").kind == JsonKind::String && v::j("false").string_value == "false", "C-string overload");
    require(v::j(std::string("rail")).string_value == "rail", "string overload");
    require(v::j(false).kind == JsonKind::Bool && !v::j(false).bool_value, "bool overload");
    require(v::j(2.5).kind == JsonKind::Number && v::j(2.5).number_value == 2.5, "number overload");
    require(std::signbit(v::j(-0.0).number_value), "JSON preserves negative zero");
    require(v::obj().kind == JsonKind::Object && v::obj().object_value.empty(), "empty object not null");
    require(v::arr().kind == JsonKind::Array && v::arr().array_value.empty(), "empty array not null");
    const auto object = v::obj({{"z", v::j(true)}, {"a", v::arr({v::j("x"), v::j(1.0)})}, {"z", v::j(false)}});
    require(object.object_value.size() == 3 && object.object_value[0].first == "z" &&
        object.object_value[1].first == "a" && object.object_value[2].first == "z", "object order/duplicates retained");
    const auto& array = object.object_value[1].second.array_value;
    require(array.size() == 2 && array[0].string_value == "x" && array[1].number_value == 1.0, "nested array order");
    const auto strings = v::strings({"z", "a", "z", ""});
    require(strings.kind == JsonKind::Array && strings.array_value.size() == 4 &&
        strings.array_value[0].string_value == "z" && strings.array_value[1].string_value == "a" &&
        strings.array_value[2].string_value == "z" && strings.array_value[3].string_value.empty(), "string array exact order");
}
} // namespace

int main() {
    try {
        text_contracts(); number_contracts(); containers();
        std::cout << checks << " authoring value contracts passed (standalone, no core archive)\n";
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n'; return 1;
    }
}
