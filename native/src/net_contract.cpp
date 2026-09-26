#include "schgen/net_contract.hpp"
#include "schgen/atomic_file.hpp"

#include <algorithm>
#include <map>
#include <set>

namespace schgen {
namespace {
bool alpha(unsigned char c) { return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z'); }
bool digit(unsigned char c) { return c >= '0' && c <= '9'; }
bool keyword(const std::string& value) {
    // C++17 keywords, alternative tokens, and later/contextual keywords kept
    // escaped for portable consumers. NULL is defined by standard headers.
    static const std::set<std::string> words{
        "alignas", "alignof", "and", "and_eq", "asm", "auto", "bitand", "bitor",
        "bool", "break", "case", "catch", "char", "char8_t", "char16_t", "char32_t",
        "class", "compl", "concept", "const", "consteval", "constexpr", "constinit",
        "const_cast", "continue", "co_await", "co_return", "co_yield", "decltype",
        "default", "delete", "do", "double", "dynamic_cast", "else", "enum",
        "explicit", "export", "extern", "false", "final", "float", "for", "friend",
        "goto", "if", "import", "inline", "int", "long", "module", "mutable",
        "namespace", "new", "noexcept", "not", "not_eq", "nullptr", "operator",
        "or", "or_eq", "override", "private", "protected", "public", "register",
        "reinterpret_cast", "requires", "return", "short", "signed", "sizeof",
        "static", "static_assert", "static_cast", "struct", "switch", "template",
        "this", "thread_local", "throw", "true", "try", "typedef", "typeid",
        "typename", "union", "unsigned", "using", "virtual", "void", "volatile",
        "wchar_t", "while", "xor", "xor_eq", "NULL"};
    return words.count(value) != 0;
}
bool safe_identifier(const std::string& value) {
    if (value.empty() || !alpha(static_cast<unsigned char>(value.front())) ||
        value.find("__") != std::string::npos || keyword(value)) return false;
    return std::all_of(value.begin(), value.end(), [](unsigned char c) {
        return alpha(c) || digit(c) || c == '_';
    });
}
std::string literal(const std::string& value) {
    std::string out = "\"";
    for (const unsigned char c : value) {
        if (c == '\\' || c == '"' || c == '?') { out += '\\'; out += static_cast<char>(c); }
        else if (c >= 32 && c <= 126) out += static_cast<char>(c);
        else {
            // Fixed-width octal cannot consume following digits/hex characters.
            out += '\\'; out += static_cast<char>('0' + ((c >> 6) & 7));
            out += static_cast<char>('0' + ((c >> 3) & 7)); out += static_cast<char>('0' + (c & 7));
        }
    }
    return out + '"';
}
struct ByteOrder {
    bool operator()(const std::string& a, const std::string& b) const {
        // UTF-8 byte order agrees with Python's codepoint order for valid input;
        // explicit unsigned bytes also make arbitrary caller-owned bytes stable.
        return std::lexicographical_compare(a.begin(), a.end(), b.begin(), b.end(),
            [](unsigned char x, unsigned char y) { return x < y; });
    }
};
using Names = std::set<std::string, ByteOrder>;
std::vector<NetContractEntry> entries(const Names& names, const std::string& domain) {
    std::vector<NetContractEntry> out;
    std::map<std::string, std::string> used;
    for (const auto& name : names) {
        const auto identifier = net_contract_identifier(name);
        const auto [previous, inserted] = used.emplace(identifier, name);
        if (!inserted)
            throw NetContractError("net contract: " + domain + " identifier collision " + literal(identifier) +
                " between " + literal(previous->second) + " and " + literal(name));
        out.push_back({name, identifier});
    }
    return out;
}
void validate_namespace(const std::string& value) {
    std::size_t start = 0;
    for (;;) {
        const auto end = value.find("::", start);
        const auto component = value.substr(start, end == std::string::npos ? end : end - start);
        if (!safe_identifier(component) || component == "std")
            throw NetContractError("net contract: unsafe C++ namespace " + literal(value));
        if (end == std::string::npos) return;
        start = end + 2;
    }
}
std::string section(const std::string& domain, const std::vector<NetContractEntry>& values) {
    std::string text = "namespace " + domain + " {\n";
    for (const auto& entry : values)
        text += "inline constexpr ::std::string_view " + entry.identifier + "{" + literal(entry.name) +
            ", " + std::to_string(entry.name.size()) + "};\n";
    return text + "} // namespace " + domain + "\n\n";
}
std::string inventory(const std::string& domain, const std::string& name,
                      const std::vector<NetContractEntry>& values) {
    std::string text = "inline constexpr ::std::array<::std::string_view, " + std::to_string(values.size()) +
        "> " + name + "{{\n";
    for (const auto& entry : values) text += "    " + domain + "::" + entry.identifier + ",\n";
    return text + "}};\n";
}
} // namespace

NetContractInput load_net_contract_input(const ProjectPaths& paths) {
    NetContractInput out;
    for (auto& sheet : load_project_circuits(paths)) out.circuits.push_back(std::move(sheet.circuit));
    out.som = load_som_interface(paths.som_interface_file);
    return out;
}

std::string net_contract_identifier(const std::string& name) {
    if (name.empty()) return "net_empty";
    std::string legacy;
    bool ascii = true;
    for (const unsigned char c : name) {
        if (c > 127) ascii = false;
        legacy += c == '+' ? 'P' : (alpha(c) || digit(c) || c == '_' ? static_cast<char>(c) : '_');
    }
    if (ascii && safe_identifier(legacy)) return legacy;
    const char* hex = "0123456789abcdef";
    std::string out = "net_x";
    for (const unsigned char c : name) { out += hex[c >> 4]; out += hex[c & 15]; }
    return out;
}

NetContractDocument generate_net_contract_header(const NetContractInput& input,
                                                const std::string& name_space) {
    validate_namespace(name_space);
    Names som, rails;
    for (const auto& [ref, connector] : input.som.connectors) {
        (void)ref;
        for (const auto& [pin, name] : connector.pins) { (void)pin; som.insert(name); }
    }
    for (const auto& circuit : input.circuits) for (const auto& net : circuit.nets)
        if (net.net_class == "power" && !net.name.empty() && net.name.front() == '+') rails.insert(net.name);
    NetContractDocument out;
    out.som = entries(som, "SOM"); out.rails = entries(rails, "RAILS");
    out.header = "// GENERATED net contract from authored circuit IR and the SoM contract.\n"
        "// C++17; regenerate using the native net-contract authoring API.\n"
        "// Original net-name bytes are preserved; do not edit generated constants.\n"
        "#pragma once\n\n#include <array>\n#include <string_view>\n\nnamespace " + name_space + " {\n\n" +
        section("SOM", out.som) + section("RAILS", out.rails) +
        inventory("SOM", "som_names", out.som) + inventory("RAILS", "rail_names", out.rails) +
        "\n} // namespace " + name_space + "\n";
    return out;
}

NetContractDocument write_net_contract_header(const NetContractInput& input,
    const std::filesystem::path& output, const std::string& name_space) {
    namespace fs = std::filesystem;
    const auto extension = output.extension().string();
    if (output.empty() || output.string().find('\0') != std::string::npos ||
        (extension != ".hpp" && extension != ".h" && extension != ".hh" && extension != ".hxx"))
        throw NetContractError("net contract: output must name a C++ header (.h/.hh/.hpp/.hxx)");
    const auto status = fs::symlink_status(output);
    if (fs::exists(status) && !fs::is_regular_file(status))
        throw NetContractError("net contract: refuse symlink or non-file output " + output.string());
    auto document = generate_net_contract_header(input, name_space);
    write_atomic_file(output.string(), {document.header.begin(), document.header.end()});
    return document;
}
} // namespace schgen
