#include "schgen/devicetree.hpp"

#include "schgen/json.hpp"
#include "schgen/link.hpp"

#include <algorithm>
#include <cstdint>
#include <map>
#include <optional>
#include <set>
#include <utility>

namespace schgen {
namespace {
namespace fs = std::filesystem;

std::string repr(const std::string& text) {
    const char quote = text.find('\'') != std::string::npos && text.find('"') == std::string::npos ? '"' : '\'';
    constexpr char hex[] = "0123456789abcdef";
    std::string out(1, quote);
    for (unsigned char c : text) {
        if (c == quote || c == '\\') { out += '\\'; out += static_cast<char>(c); }
        else if (c == '\n') out += "\\n";
        else if (c == '\r') out += "\\r";
        else if (c == '\t') out += "\\t";
        else if (c < 32 || c == 127) { out += "\\x"; out += hex[c >> 4]; out += hex[c & 15]; }
        else out += static_cast<char>(c);
    }
    return out + quote;
}

struct Integer {
    bool negative;
    std::string digits;
};

std::uint32_t next_codepoint(const std::string& text, std::size_t& i) {
    const auto lead = static_cast<unsigned char>(text[i++]);
    if (lead < 0x80) return lead;
    const auto count = lead >= 0xf0 ? 3 : lead >= 0xe0 ? 2 : 1;
    if (lead < 0xc2 || lead > 0xf4) throw DeviceTreeError("invalid UTF-8 in device-tree input");
    std::uint32_t value = lead & (count == 3 ? 7 : count == 2 ? 15 : 31);
    for (int j = 0; j < count; ++j) {
        if (i == text.size() || (static_cast<unsigned char>(text[i]) & 0xc0) != 0x80)
            throw DeviceTreeError("invalid UTF-8 in device-tree input");
        value = (value << 6) | (static_cast<unsigned char>(text[i++]) & 63);
    }
    return value;
}

int decimal(std::uint32_t code) {
    // Unicode 16 Nd runs (Python's re \d / int semantics). Each run starts at
    // decimal zero and contains ten consecutive digits, even for math alphabets.
    constexpr std::uint32_t zeros[]{
        0x30, 0x660, 0x6f0, 0x7c0, 0x966, 0x9e6, 0xa66, 0xae6, 0xb66,
        0xbe6, 0xc66, 0xce6, 0xd66, 0xde6, 0xe50, 0xed0, 0xf20, 0x1040,
        0x1090, 0x17e0, 0x1810, 0x1946, 0x19d0, 0x1a80, 0x1a90, 0x1b50,
        0x1bb0, 0x1c40, 0x1c50, 0xa620, 0xa8d0, 0xa900, 0xa9d0, 0xa9f0,
        0xaa50, 0xabf0, 0xff10, 0x104a0, 0x10d30, 0x10d40, 0x11066,
        0x110f0, 0x11136, 0x111d0, 0x112f0, 0x11450, 0x114d0, 0x11650,
        0x116c0, 0x116d0, 0x116da, 0x11730, 0x118e0, 0x11950, 0x11bf0,
        0x11c50, 0x11d50, 0x11da0, 0x11f50, 0x16130, 0x16a60, 0x16ac0,
        0x16b50, 0x16d70, 0x1ccf0, 0x1d7ce, 0x1d7d8, 0x1d7e2, 0x1d7ec,
        0x1d7f6, 0x1e140, 0x1e2f0, 0x1e4f0, 0x1e5f1, 0x1e950, 0x1fbf0};
    for (auto zero : zeros) if (code >= zero && code < zero + 10) return static_cast<int>(code - zero);
    return -1;
}

bool integer_space(std::uint32_t c) {
    return (c >= 9 && c <= 13) || c == 32 || c == 0x85 || c == 0xa0 || c == 0x1680 ||
        (c >= 0x2000 && c <= 0x200a) || c == 0x2028 || c == 0x2029 ||
        c == 0x202f || c == 0x205f || c == 0x3000;
}

Integer integer(const std::string& text) {
    std::vector<std::uint32_t> codes;
    for (std::size_t i = 0; i < text.size();) codes.push_back(next_codepoint(text, i));
    std::size_t i = 0, end = codes.size();
    while (i < end && integer_space(codes[i])) ++i;
    while (end > i && integer_space(codes[end - 1])) --end;
    bool negative = false;
    if (i < end && (codes[i] == '+' || codes[i] == '-')) { negative = codes[i] == '-'; ++i; }
    std::string digits;
    bool previous = false;
    for (; i < end; ++i) {
        const auto c = codes[i];
        const auto digit = decimal(c);
        if (digit >= 0) { digits += static_cast<char>('0' + digit); previous = true; }
        else if (c == '_' && previous) previous = false;
        else break;
    }
    if (digits.empty() || !previous || i < end)
        throw DeviceTreeError("invalid literal for int() with base 10: " + repr(text));
    const auto nonzero = digits.find_first_not_of('0');
    if (nonzero == std::string::npos) return {false, "0"};
    return {negative, digits.substr(nonzero)};
}

std::optional<std::string> mio_index(const std::string& net) {
    const std::string prefix = "ZYNQ_PS_MIO";
    for (std::size_t pos = 0; (pos = net.find(prefix, pos)) != std::string::npos;) {
        pos += prefix.size();
        std::string digits;
        for (auto i = pos; i < net.size();) {
            const auto digit = decimal(next_codepoint(net, i));
            if (digit < 0) break;
            digits += static_cast<char>('0' + digit);
        }
        if (!digits.empty()) return integer(digits).digits;
    }
    return std::nullopt;
}

bool less(const Integer& a, const Integer& b) {
    if (a.negative != b.negative) return a.negative;
    if (a.digits == b.digits) return false;
    const bool smaller = a.digits.size() == b.digits.size() ? a.digits < b.digits : a.digits.size() < b.digits.size();
    return a.negative ? !smaller : smaller;
}

std::string pad(const std::string& text, std::size_t width) {
    const auto length = static_cast<std::size_t>(std::count_if(text.begin(), text.end(),
        [](unsigned char c) { return (c & 0xc0) != 0x80; }));
    return text + std::string(length >= width ? 0 : width - length, ' ');
}

void replace_all(std::string& text, const std::string& from, const std::string& to) {
    for (std::size_t pos = 0; (pos = text.find(from, pos)) != std::string::npos; pos += to.size())
        text.replace(pos, from.size(), to);
}

const JsonNode& field(const JsonNode& n, const std::string& name, JsonKind kind, const std::string& where) {
    const auto* value = object_field(n, name);
    if (n.kind != JsonKind::Object || !value || value->kind != kind)
        throw DeviceTreeError(where + ": missing or invalid " + name);
    return *value;
}

void merge(XdcStrings& target, const JsonNode& n) {
    for (const auto& [key, value] : n.object_value) {
        const auto found = std::find_if(target.begin(), target.end(),
            [name = key](const auto& item) { return item.first == name; });
        if (found == target.end()) target.emplace_back(key, value.string_value);
        else found->second = value.string_value;
    }
}

std::string source_name(const fs::path& path, const fs::path& repository) {
    const auto relative = fs::weakly_canonical(path).lexically_relative(fs::weakly_canonical(repository));
    if (!relative.empty() && *relative.begin() != "..") return relative.generic_string();
    return path.string();
}

std::string render(const DeviceTreeInput& in, const DeviceTreeOutput& out) {
    std::vector<std::string> lines{
        "/*",
        " * carrier_pl.dtsi -- Zynq-7000 PS device-tree fragment for the",
        " * carrier.  GENERATED -- DO NOT EDIT.",
        " *",
        " * generated-by: schgen devicetree (native/src/devicetree.cpp)",
        " * regenerate:   native/bin/schgen devicetree",
        " * PS device:    " + in.live.value.value_or("None") + " (from the SoM netlist)",
        " * sources:",
        " *   contract : " + in.contract_source + " (net <- J pin, same walk as schgen firmware/xdc)",
        " *   ball map : " + in.som_source + " (kicad-cli; PS = reaches no PL ball)",
        " *   renames  : " + in.mapping_source + " function_map + pudc_straps (MIO -> carrier function net)",
        " *",
        " * This is the PS-side twin of carrier/fpga/Zynq_Carrier_pins.xdc:",
        " * the XDC owns every carrier net that reaches a PL ball; THIS",
        " * fragment documents the PS-side nets the XDC drops -- the",
        " * microSD bus and the bare PS MIO pins routed out on J1.",
        " *",
        " * The overlay bodies below are COMMENTED templates: the MIO/EMIO",
        " * routing is fixed on the SoM, so paste the relevant node(s)",
        " * into your board .dts and uncomment.  The pinmux table is the",
        " * authoritative carrier-signal <-> MIO-index map.",
        " */", "", "/dts-v1/;", "/plugin/;", "",
        "/* " + std::string(72, '=') + " */",
        "/* PS pinmux table -- carrier signal <-> Zynq PS MIO index (J1 pins).      */",
        "/* (the MIO index is parsed from the contract net name; sorted by index)  */",
        "/* " + std::string(72, '-') + " */",
        "/*   MIO  J1 pin   carrier net (function)       note */"};
    for (const auto& row : out.mio_rows) {
        const auto note = row.function != row.raw ? "renamed from " + row.raw :
            row.raw.find_first_of("/\\") != std::string::npos ? "VMODE boot strap (on-SoM, carrier NC)" :
            "spare PS MIO (bare to J1)";
        lines.push_back("/* MIO" + pad(row.index, 2) + "  " + pad(row.jpin, 7) + "  " + pad(row.function, 28) + " " + note + " */");
    }
    lines.push_back("/* " + std::string(72, '=') + " */");
    lines.emplace_back();
    std::map<std::string, std::string> uart;
    for (const auto& row : out.mio_rows) uart[row.function] = row.index;
    if (uart.count("ZYNQ_PS_UART0_RXD") && uart.count("ZYNQ_PS_UART0_TXD")) {
        const std::vector<std::string> block{
            "/* ---- PS UART0 console -- MIO console group (uart_bridge) ---------- */",
            "/* The carrier brings PS UART0 out on the SoM console MIO pair, routed   */",
            "/* to the FT232 USB-UART bridge (carrier uart_bridge sheet).            */",
            "/*",
            " * &uart0 {   // PS UART0 = uart@e0000000 (UG585)",
            " *     status = \"okay\";",
            " *     // MIO" + uart.at("ZYNQ_PS_UART0_RXD") + " = ZYNQ_PS_UART0_RXD (Zynq RX), MIO" +
                uart.at("ZYNQ_PS_UART0_TXD") + " = ZYNQ_PS_UART0_TXD (Zynq TX)",
            " * };", " */", ""};
        lines.insert(lines.end(), block.begin(), block.end());
    }
    const std::vector<std::string> sdio{
        "/* ---- microSD -- PS SD-host controller (sdhci) ------------------------ */",
        "/* The carrier SDIO_* 4-bit bus runs at 1.8 V straight into the Zynq PS    */",
        "/* (carrier/PLAN.md round 2).  Card-detect is a PL/EMIO net (bank 13,        */",
        "/* J2.17) the XDC constrains as a get_ports pin -- noted here for the cd     */",
        "/* story but routed through the PL, not a PS MIO.                            */"};
    lines.insert(lines.end(), sdio.begin(), sdio.end());
    lines.push_back("/* " + std::string(72, '-') + " */");
    lines.push_back("/* role   J1 pin   carrier net */");
    for (const auto& row : out.sdio_rows)
        lines.push_back("/* " + pad(row.role, 5) + "  " + pad(row.jpin, 7) + "  " + row.net + " */");
    const std::vector<std::string> footer{
        "/* cd     J2.17    SD_CARD_DETECT (PL/EMIO -- constrained by the XDC) */",
        "/*",
        " * &sdhci0 {   // PS SDIO0 = sdhci@e0100000 (UG585)",
        " *     status = \"okay\";",
        " *     bus-width = <4>;          // SDIO_D0..D3",
        " *     // 1.8 V signaling (carrier/PLAN.md round 2)",
        " *     no-1-8-v;                 // delete if the SoM level-shifts",
        " *     // card-detect: SD_CARD_DETECT is a PL/EMIO net (bank 13, J2.17),",
        " *     // so cd is wired through the PL fabric, not a PS MIO --",
        " *     // drive it from your EMIO gpio or use broken-cd/non-removable.",
        " *     broken-cd;", " * };", " */"};
    lines.insert(lines.end(), footer.begin(), footer.end());
    std::string text;
    for (const auto& line : lines) text += line + '\n';
    replace_all(text, "—", "--");
    replace_all(text, "→", "->");
    return text;
}
}  // namespace

DeviceTreeInput load_devicetree_input(const fs::path& repository, const fs::path& project,
                                     const SomZynq& live, const fs::path& contract,
                                     const std::vector<std::string>& refs) {
    const auto contract_path = contract.empty() ? project / "som_interface.json" : contract;
    const auto mapping_path = project / "som_mapping.json";
    DeviceTreeInput in;
    in.contract = load_som_interface(contract_path);
    in.live = live;
    in.refs = refs;
    const auto mapping = parse_json_file(mapping_path.string());
    const auto where = mapping_path.string();
    // The old Python module import asserted that voltage-mode boot straps
    // remained unmapped. Share the full native policy gate with link/XDC,
    // including rail/rebound aliases, while retaining original JSON order here.
    try { (void)link_mapping_from_json(mapping); }
    catch (const std::runtime_error& error) { throw DeviceTreeError(where + ": " + error.what()); }
    merge(in.function_map, field(mapping, "function_map", JsonKind::Object, where));
    merge(in.function_map, field(mapping, "pudc_straps", JsonKind::Object, where));
    in.contract_path = contract_path.string();
    in.contract_source = source_name(contract_path, repository);
    in.som_source = source_name(live.source, repository);
    in.mapping_source = source_name(mapping_path, repository);
    return in;
}

DeviceTreeOutput generate_devicetree(const DeviceTreeInput& in) {
    std::map<std::string, std::string> pin_names, functions;
    for (const auto& item : in.live.pin_names) pin_names[item.first] = item.second;
    for (const auto& item : in.function_map) functions[item.first] = item.second;
    std::set<std::string> pl_nets;
    for (const auto& [ball, net] : in.live.ball_net) {
        const auto found = pin_names.find(ball);
        if (found != pin_names.end() && found->second.compare(0, 3, "IO_") == 0) pl_nets.insert(net);
    }
    std::vector<std::string> net_order;
    std::map<std::string, std::vector<std::string>> net_pins;
    for (const auto& ref : in.refs) {
        const auto found = std::find_if(in.contract.connectors.begin(), in.contract.connectors.end(),
            [&](const auto& item) { return item.first == ref; });
        if (found == in.contract.connectors.end()) throw DeviceTreeError(ref + " missing from " + in.contract_path);
        for (const auto& [pin, net] : found->second.pins) {
            if (net.compare(0, 12, "unconnected-") == 0) continue;
            if (!net_pins.count(net)) net_order.push_back(net);
            net_pins[net].push_back(ref + "." + pin);
        }
    }
    // Validate every location before sorting, including nets not used below.
    // Stable equal-number ties preserve contract insertion order.
    for (const auto& net : net_order) {
        struct Location { std::string ref, full; Integer pin; };
        std::vector<Location> rows;
        for (const auto& location : net_pins.at(net)) {
            const auto dot = location.find('.'), next = location.find('.', dot + 1);
            rows.push_back({location.substr(0, dot), location, integer(location.substr(dot + 1, next - dot - 1))});
        }
        std::stable_sort(rows.begin(), rows.end(), [](const auto& a, const auto& b) {
            return a.ref == b.ref ? less(a.pin, b.pin) : a.ref < b.ref;
        });
        auto& locations = net_pins.at(net);
        locations.clear();
        for (const auto& row : rows) locations.push_back(row.full);
    }
    DeviceTreeOutput out;
    for (const auto& [net, role] : XdcStrings{{"SDIO_CLK", "clk"}, {"SDIO_CMD", "cmd"},
            {"SDIO_D0", "dat0"}, {"SDIO_D1", "dat1"}, {"SDIO_D2", "dat2"}, {"SDIO_D3", "dat3"}}) {
        if (!net_pins.count(net)) throw DeviceTreeError("SDIO line " + repr(net) +
            " absent from the contract — the microSD bus is incomplete (expected all of "
            "['SDIO_CLK', 'SDIO_CMD', 'SDIO_D0', 'SDIO_D1', 'SDIO_D2', 'SDIO_D3'])");
        if (pl_nets.count(net)) throw DeviceTreeError("SDIO line " + repr(net) +
            " reaches a PL ball — it is not a PS net; the XDC, not this fragment, owns it");
        out.sdio_rows.push_back({net, role, net_pins.at(net).front()});
    }
    for (const auto& net : net_order) {
        const auto index = mio_index(net);
        if (!index) continue;
        if (pl_nets.count(net)) throw DeviceTreeError(repr(net) +
            " carries a PS MIO index but reaches a PL ball — contract/SoM disagree on PS vs PL");
        const auto function = functions.find(net);
        out.mio_rows.push_back({*index, net,
            function == functions.end() ? net : function->second, net_pins.at(net).front()});
    }
    std::stable_sort(out.mio_rows.begin(), out.mio_rows.end(), [](const auto& a, const auto& b) {
        return a.index == b.index ? a.raw < b.raw : less({false, a.index}, {false, b.index});
    });
    if (out.mio_rows.empty()) throw DeviceTreeError(
        "no ZYNQ_PS_MIO* net in the contract — the PS pinmux walk found nothing; the contract is stale or PS pins were renamed");
    std::map<std::string, std::string> seen;
    for (const auto& row : out.mio_rows) {
        const auto previous = seen.find(row.index);
        if (previous != seen.end()) throw DeviceTreeError("MIO" + row.index + " claimed twice: " +
            repr(previous->second) + " and " + repr(row.raw));
        seen[row.index] = row.raw;
    }
    out.text = render(in, out);
    return out;
}

}  // namespace schgen
