#include "schgen/json.hpp"
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>
#include <unistd.h>

namespace {
struct Scratch {
    std::filesystem::path directory;
    Scratch() {
        auto name = (std::filesystem::temp_directory_path() / "schgen-json-unicode-XXXXXX").string();
        if (!::mkdtemp(name.data())) throw std::runtime_error("cannot allocate test directory");
        directory = name;
    }
    ~Scratch() { std::error_code error; std::filesystem::remove_all(directory, error); }
};
}
int main() {
    try {
        Scratch scratch;
        const auto path = scratch.directory / "input.json";
        auto parse = [&](const std::string& text) {
            { std::ofstream output(path, std::ios::binary); output << text;
              if (!output) throw std::runtime_error("cannot write test input"); }
            return schgen::parse_json_file(path.string());
        };
        const std::vector<std::pair<std::string, std::string>> cases = {
            {R"("\u0000")", std::string(1, '\0')},
            {R"("\u007f")", "\x7f"}, {R"("\u0080")", "\xc2\x80"},
            {R"("\u07ff")", "\xdf\xbf"}, {R"("\u0800")", "\xe0\xa0\x80"},
            {R"("\ud7ff")", "\xed\x9f\xbf"}, {R"("\ue000")", "\xee\x80\x80"},
            {R"("\ud800\udc00")", "\xf0\x90\x80\x80"},
            {R"("\ud83d\ude80")", "\xf0\x9f\x9a\x80"},
            {R"("\uDBFF\uDFFF")", "\xf4\x8f\xbf\xbf"},
            {R"("a\ud83d\ude80z")", "a\xf0\x9f\x9a\x80z"},
            {"\"\xf0\x9f\x9a\x80\"", "\xf0\x9f\x9a\x80"}
        };
        for (const auto& [encoded, expected] : cases)
            if (parse(encoded).string_value != expected) throw std::runtime_error("Unicode scalar mismatch");
        const std::vector<std::string> invalid = {
            R"("\ud800")", R"("\udc00")", R"("\udfff")", R"("\ud800x")",
            R"("\ud800\n")", R"("\ud800\u0041")", R"("\ud800\ud800")",
            R"("\ud800\u12")", R"("\ud800\uXXXX")", R"("\ud800\u")",
            R"({"\ud83d\ude80":1,"🚀":2})"
        };
        for (const auto& encoded : invalid) {
            bool rejected = false;
            try { (void)parse(encoded); } catch (const std::runtime_error&) { rejected = true; }
            if (!rejected) throw std::runtime_error("invalid Unicode or duplicate decoded key accepted");
        }
        const auto object = parse(R"({"\ud83d\ude80":"payload"})");
        const auto* value = schgen::object_field(object, "🚀");
        if (!value || value->string_value != "payload") throw std::runtime_error("decoded Unicode key missing");
        std::cout << "JSON Unicode: 24 contracts passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n'; return 1;
    }
}
