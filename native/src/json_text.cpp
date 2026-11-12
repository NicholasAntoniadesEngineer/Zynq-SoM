#include "schgen/json_text.hpp"

#include <iomanip>
#include <limits>
#include <locale>
#include <sstream>

namespace schgen::json_text {
namespace {

bool flat_container(const std::string& text, std::size_t open) {
    bool in_string = false, escaped = false;
    for (std::size_t index = open + 1; index < text.size(); ++index) {
        const char letter = text[index];
        if (in_string) {
            if (escaped) escaped = false;
            else if (letter == '\\') escaped = true;
            else if (letter == '"') in_string = false;
            continue;
        }
        if (letter == '"') in_string = true;
        else if (letter == '{' || letter == '[') return false;
        else if (letter == '}' || letter == ']') return true;
    }
    return true;
}

}

std::string text_value(std::string_view text) {
    std::string out = "\"";
    for (const char letter : text) {
        if (letter == '"' || letter == '\\') {
            out += '\\';
            out += letter;
        } else if (letter == '\n') {
            out += "\\n";
        } else if (letter == '\t') {
            out += "\\t";
        } else {
            out += letter;
        }
    }
    return out + '"';
}

std::string integer(long long value) { return std::to_string(value); }

std::string boolean(bool value) { return value ? "true" : "false"; }

std::string number(double value) {
    std::ostringstream out;
    out.imbue(std::locale::classic());
    out << std::setprecision(std::numeric_limits<double>::digits10) << value;
    return out.str();
}

std::string object(const std::vector<Field>& fields) {
    std::string out = "{";
    for (const auto& [key, value] : fields) {
        if (out.size() > 1) out += ',';
        out += text_value(key) + ':' + value;
    }
    return out + '}';
}

std::string array(const std::vector<std::string>& values) {
    std::string out = "[";
    for (const auto& value : values) {
        if (out.size() > 1) out += ',';
        out += value;
    }
    return out + ']';
}

std::string names(const std::vector<std::string>& values) {
    std::vector<std::string> rows;
    for (const auto& value : values) rows.push_back(text_value(value));
    return array(rows);
}

std::string pretty(const std::string& compact) {
    std::string out;
    std::vector<char> flat;
    std::size_t depth = 0;
    bool in_string = false, escaped = false;
    const auto line = [&] { out += '\n' + std::string(depth * 2, ' '); };
    for (std::size_t index = 0; index < compact.size(); ++index) {
        const char letter = compact[index];
        if (in_string) {
            out += letter;
            if (escaped) escaped = false;
            else if (letter == '\\') escaped = true;
            else if (letter == '"') in_string = false;
            continue;
        }
        if (letter == '"') {
            in_string = true;
            out += letter;
        } else if (letter == '{' || letter == '[') {
            flat.push_back(flat_container(compact, index) ? 1 : 0);
            out += letter;
            if (!flat.back()) {
                ++depth;
                line();
            }
        } else if (letter == '}' || letter == ']') {
            if (!flat.back()) {
                --depth;
                line();
            }
            flat.pop_back();
            out += letter;
        } else if (letter == ',') {
            out += letter;
            if (flat.back()) out += ' ';
            else line();
        } else if (letter == ':') {
            out += ": ";
        } else {
            out += letter;
        }
    }
    return out + '\n';
}

}
