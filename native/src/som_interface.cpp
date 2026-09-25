#include "schgen/som_interface.hpp"

#include "schgen/atomic_file.hpp"
#include "schgen/json.hpp"

#include <libxml/parser.h>
#include <libxml/tree.h>

#include <algorithm>
#include <cerrno>
#include <climits>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iterator>
#include <memory>
#include <spawn.h>
#include <sys/wait.h>
#include <unistd.h>

extern char** environ;

namespace schgen {
namespace {
namespace fs = std::filesystem;

template <typename T>
T* lookup(std::vector<std::pair<std::string, T>>& items, const std::string& key) {
    for (auto& item : items) if (item.first == key) return &item.second;
    return nullptr;
}

template <typename T>
void put(std::vector<std::pair<std::string, T>>& items, const std::string& key, T value) {
    if (auto* old = lookup(items, key)) *old = std::move(value);
    else items.emplace_back(key, std::move(value));
}

bool contains(const std::vector<std::string>& refs, const std::string& ref) {
    return std::find(refs.begin(), refs.end(), ref) != refs.end();
}

bool named(const xmlNode* node, const char* name) {
    return node && node->type == XML_ELEMENT_NODE && !node->ns &&
        xmlStrEqual(node->name, BAD_CAST name);
}

xmlNode* child(xmlNode* node, const char* name) {
    for (auto* c = node ? node->children : nullptr; c; c = c->next)
        if (named(c, name)) return c;
    return nullptr;
}

std::optional<std::string> attribute(xmlNode* node, const char* key) {
    std::unique_ptr<xmlChar, decltype(xmlFree)> value(xmlGetNoNsProp(node, BAD_CAST key), xmlFree);
    if (!value) return std::nullopt;
    return reinterpret_cast<const char*>(value.get());
}

std::string attr(xmlNode* node, const char* key) {
    return attribute(node, key).value_or("");
}

// ElementTree's .text excludes child element contents and their tails, but
// joins adjacent text/CDATA across comments and processing instructions.
std::optional<std::string> element_text(xmlNode* node) {
    if (!node) return std::string{};
    std::optional<std::string> text;
    for (auto* c = node->children; c; c = c->next) {
        if (c->type == XML_ELEMENT_NODE) break;
        if (c->type == XML_TEXT_NODE || c->type == XML_CDATA_SECTION_NODE) {
            if (!text) text = "";
            if (c->content) *text += reinterpret_cast<const char*>(c->content);
        }
    }
    // ElementTree represents an empty CDATA section as None too.
    if (text && text->empty()) text.reset();
    return text;
}

using XmlDoc = std::unique_ptr<xmlDoc, decltype(&xmlFreeDoc)>;

XmlDoc parse_xml(std::string_view text, const std::string& source) {
    if (text.size() > INT_MAX) throw SomInterfaceError("SoM netlist XML too large: " + source);
    std::unique_ptr<xmlParserCtxt, decltype(&xmlFreeParserCtxt)> context(
        xmlNewParserCtxt(), xmlFreeParserCtxt);
    if (!context) throw SomInterfaceError("cannot allocate SoM XML parser");
    // No NOENT, DTDLOAD, XINCLUDE or recovery. Diagnostics stay local to this
    // context; do not install a process-global error handler/entity loader.
    XmlDoc doc(xmlCtxtReadMemory(context.get(), text.data(), static_cast<int>(text.size()),
        nullptr, nullptr, XML_PARSE_NONET | XML_PARSE_NOERROR | XML_PARSE_NOWARNING), xmlFreeDoc);
    if (!doc) {
        const auto* error = xmlCtxtGetLastError(context.get());
        std::string detail = error && error->message ? error->message : "invalid XML";
        while (!detail.empty() && (detail.back() == '\n' || detail.back() == '\r')) detail.pop_back();
        throw SomInterfaceError("invalid SoM netlist XML for " + source + ": " + detail);
    }
    if (doc->intSubset || doc->extSubset)
        throw SomInterfaceError("DTD is not allowed in SoM netlist XML for " + source);
    return doc;
}

// Python repr spelling for reference/libsource errors, including quote choice.
std::string repr(const std::string& value) {
    const char quote = value.find('\'') != std::string::npos && value.find('"') == std::string::npos
        ? '"' : '\'';
    std::string out(1, quote);
    constexpr char hex[] = "0123456789abcdef";
    for (unsigned char ch : value) {
        if (ch == '\\' || ch == quote) { out += '\\'; out += static_cast<char>(ch); }
        else if (ch == '\n') out += "\\n";
        else if (ch == '\r') out += "\\r";
        else if (ch == '\t') out += "\\t";
        else if (ch < 32 || ch == 127) {
            out += "\\x"; out += hex[ch >> 4]; out += hex[ch & 15];
        } else out += static_cast<char>(ch);
    }
    return out + quote;
}

struct TempDir {
    fs::path path;
    TempDir() {
        auto pattern = (fs::temp_directory_path() / "schgen_som_XXXXXX").string();
        if (!::mkdtemp(pattern.data()))
            throw SomInterfaceError("cannot create SoM temporary directory: " + std::string(std::strerror(errno)));
        path = pattern;
    }
    TempDir(const TempDir&) = delete;
    TempDir& operator=(const TempDir&) = delete;
    ~TempDir() { std::error_code ec; fs::remove_all(path, ec); }
};

std::string read(const fs::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw SomInterfaceError("cannot read SoM netlist file: " + path.string());
    std::string result{std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};
    if (in.bad()) throw SomInterfaceError("cannot read SoM netlist file: " + path.string());
    return result;
}

std::string stderr_tail(std::string text) {
    // subprocess text=True performs universal newline conversion before [-400:].
    std::string normalized;
    for (std::size_t i = 0; i < text.size(); ++i) {
        if (text[i] == '\r') {
            normalized += '\n';
            if (i + 1 < text.size() && text[i + 1] == '\n') ++i;
        } else normalized += text[i];
    }
    std::size_t start = normalized.size(), count = 0;
    while (start > 0 && count < 400) {
        --start;
        if ((static_cast<unsigned char>(normalized[start]) & 0xc0) != 0x80) ++count;
    }
    return normalized.substr(start);
}

struct SpawnActions {
    posix_spawn_file_actions_t actions{};
    SpawnActions() {
        const int error = posix_spawn_file_actions_init(&actions);
        if (error) throw SomInterfaceError("cannot initialize KiCad process: " + std::string(std::strerror(error)));
    }
    ~SpawnActions() { posix_spawn_file_actions_destroy(&actions); }
    void open(int fd, const fs::path& path, int flags) {
        const int error = posix_spawn_file_actions_addopen(&actions, fd, path.c_str(), flags, 0600);
        if (error) throw SomInterfaceError("cannot redirect KiCad process: " + std::string(std::strerror(error)));
    }
};

int run_kicad(std::vector<std::string> args, const fs::path& errors) {
    for (const auto& arg : args)
        if (arg.find('\0') != std::string::npos) throw SomInterfaceError("embedded null byte in KiCad argument");
    if (args.empty() || args.front().empty()) throw SomInterfaceError("kicad-cli executable is empty");
    std::vector<char*> argv;
    for (auto& arg : args) argv.push_back(arg.data());
    argv.push_back(nullptr);
    SpawnActions actions;
    actions.open(STDIN_FILENO, "/dev/null", O_RDONLY);
    actions.open(STDOUT_FILENO, "/dev/null", O_WRONLY);
    actions.open(STDERR_FILENO, errors, O_WRONLY | O_CREAT | O_TRUNC);
    pid_t pid = 0;
    const int error = ::posix_spawnp(&pid, argv[0], &actions.actions, nullptr, argv.data(), environ);
    if (error) throw SomInterfaceError("cannot execute " + args.front() + ": " + std::strerror(error));
    int status = 0;
    while (::waitpid(pid, &status, 0) < 0) {
        if (errno == EINTR) continue;
        throw SomInterfaceError("cannot wait for kicad-cli: " + std::string(std::strerror(errno)));
    }
    return WIFEXITED(status) ? WEXITSTATUS(status) : -WTERMSIG(status);
}

std::string export_xml(const fs::path& source, const SomExtractOptions& options) {
    TempDir temp;
    const auto output = temp.path / "som.net";
    const auto errors = temp.path / "stderr";
    const int status = run_kicad({options.kicad_cli, "sch", "export", "netlist", "--format",
                                 "kicadxml", "-o", output.string(), source.string()}, errors);
    if (status != 0)
        throw SomInterfaceError("kicad-cli failed on " + source.string() + ": " + stderr_tail(read(errors)));
    return read(output);
}

JsonNode object() { JsonNode n; n.kind = JsonKind::Object; return n; }
JsonNode string(const std::string& s) { JsonNode n; n.kind = JsonKind::String; n.string_value = s; return n; }
JsonNode nullable(const std::optional<std::string>& s) { return s ? string(*s) : JsonNode{}; }
JsonNode dictionary(const XdcStrings& values) {
    auto n = object();
    for (const auto& [key, value] : values) put(n.object_value, key, string(value));
    return n;
}

std::uint32_t codepoint(const std::string& text, std::size_t& i) {
    const auto lead = static_cast<unsigned char>(text[i++]);
    if (lead < 0x80) return lead;
    int count = lead >= 0xf0 ? 3 : lead >= 0xe0 ? 2 : 1;
    if (lead < 0xc2 || lead > 0xf4) throw SomInterfaceError("invalid UTF-8 in SoM JSON");
    std::uint32_t code = lead & (count == 3 ? 7 : count == 2 ? 15 : 31);
    for (int j = 0; j < count; ++j) {
        if (i == text.size() || (static_cast<unsigned char>(text[i]) & 0xc0) != 0x80)
            throw SomInterfaceError("invalid UTF-8 in SoM JSON");
        code = (code << 6) | (static_cast<unsigned char>(text[i++]) & 63);
    }
    if (code > 0x10ffff || (count == 1 && code < 0x80) ||
        (count == 2 && code < 0x800) || (count == 3 && code < 0x10000))
        throw SomInterfaceError("invalid UTF-8 in SoM JSON");
    return code;
}

std::string json_quote(const std::string& value) {
    constexpr char hex[] = "0123456789abcdef";
    std::string out = "\"";
    const auto escaped = [&](std::uint32_t code) {
        out += "\\u";
        for (int shift : {12, 8, 4, 0}) out += hex[(code >> shift) & 15];
    };
    for (std::size_t i = 0; i < value.size();) {
        auto ch = codepoint(value, i);
        if (ch == '"') out += "\\\"";
        else if (ch == '\\') out += "\\\\";
        else if (ch == '\b') out += "\\b";
        else if (ch == '\f') out += "\\f";
        else if (ch == '\n') out += "\\n";
        else if (ch == '\r') out += "\\r";
        else if (ch == '\t') out += "\\t";
        else if (ch < 32 || ch >= 127) {
            if (ch <= 0xffff) escaped(ch);
            else { ch -= 0x10000; escaped(0xd800 + (ch >> 10)); escaped(0xdc00 + (ch & 1023)); }
        } else out += static_cast<char>(ch);
    }
    return out + '"';
}

// The shared JSON reader emits each escaped UTF-16 surrogate separately. Join
// valid pairs at this boundary so non-BMP KiCad text round-trips as UTF-8.
std::string join_surrogates(const std::string& text) {
    std::string out;
    for (std::size_t i = 0; i < text.size();) {
        const auto start = i;
        const auto high = codepoint(text, i);
        if (high >= 0xd800 && high <= 0xdbff && i < text.size()) {
            auto next = i;
            const auto low = codepoint(text, next);
            if (low >= 0xdc00 && low <= 0xdfff) {
                const auto code = 0x10000 + ((high - 0xd800) << 10) + low - 0xdc00;
                out += static_cast<char>(0xf0 | (code >> 18));
                out += static_cast<char>(0x80 | ((code >> 12) & 63));
                out += static_cast<char>(0x80 | ((code >> 6) & 63));
                out += static_cast<char>(0x80 | (code & 63));
                i = next;
                continue;
            }
        }
        out.append(text, start, i - start);
    }
    return out;
}

std::string strip_refs_token(const std::string& text) {
    std::size_t first = text.size(), end = 0;
    for (std::size_t i = 0; i < text.size();) {
        const auto start = i, c = static_cast<std::size_t>(codepoint(text, i));
        const bool space = (c >= 9 && c <= 13) || (c >= 0x1c && c <= 0x20) ||
            c == 0x85 || c == 0xa0 || c == 0x1680 || (c >= 0x2000 && c <= 0x200a) ||
            c == 0x2028 || c == 0x2029 || c == 0x202f || c == 0x205f || c == 0x3000;
        if (!space) { first = std::min(first, start); end = i; }
    }
    return end == 0 ? "" : text.substr(first, end - first);
}

std::string dump(const JsonNode& n, std::size_t indent = 0) {
    if (n.kind == JsonKind::Null) return "null";
    if (n.kind == JsonKind::String) return json_quote(n.string_value);
    if (n.kind != JsonKind::Object) throw SomInterfaceError("unexpected SoM JSON node type");
    if (n.object_value.empty()) return "{}";
    std::vector<const std::pair<std::string, JsonNode>*> fields;
    for (const auto& field : n.object_value) fields.push_back(&field);
    std::stable_sort(fields.begin(), fields.end(), [](const auto* a, const auto* b) { return a->first < b->first; });
    std::string out = "{\n";
    for (std::size_t i = 0; i < fields.size(); ++i) {
        out += std::string(indent + 1, ' ') + json_quote(fields[i]->first) + ": " + dump(fields[i]->second, indent + 1);
        out += i + 1 == fields.size() ? "\n" : ",\n";
    }
    return out + std::string(indent, ' ') + '}';
}

const JsonNode& required(const JsonNode& n, const std::string& key, JsonKind kind, const std::string& where) {
    const auto* field = object_field(n, key);
    if (!field || field->kind != kind) throw SomInterfaceError(where + ": expected " + key);
    return *field;
}

std::optional<std::string> optional_text(const JsonNode& n, const std::string& key, const std::string& where) {
    const auto* field = object_field(n, key);
    if (!field) return std::string{};
    if (field->kind == JsonKind::Null) return std::nullopt;
    if (field->kind != JsonKind::String) throw SomInterfaceError(where + ": expected string or null for " + key);
    return join_surrogates(field->string_value);
}
}  // namespace

std::string export_kicad_netlist_xml(const fs::path& schematic, const SomExtractOptions& options) {
    return export_xml(schematic, options);
}

KicadErcResult run_kicad_erc(const fs::path& schematic, const SomExtractOptions& options) {
    TempDir temp;
    const auto output = temp.path / "erc.rpt", errors = temp.path / "stderr";
    KicadErcResult result;
    result.exit_code = run_kicad({options.kicad_cli, "sch", "erc", "--severity-error",
        "--exit-code-violations", "-o", output.string(), schematic.string()}, errors);
    result.stderr_text = read(errors);
    if (fs::exists(output)) result.report = read(output);
    else if (result.exit_code == 0)
        throw SomInterfaceError("kicad-cli ERC returned success without a report on " + schematic.string());
    return result;
}

KicadNetlist parse_kicad_netlist_xml(std::string_view xml, const std::string& source) {
    auto doc = parse_xml(xml, source);
    auto* nets = child(xmlDocGetRootElement(doc.get()), "nets");
    KicadNetlist result;
    for (auto* net = nets ? nets->children : nullptr; net; net = net->next) {
        if (net->type != XML_ELEMENT_NODE) continue;
        std::vector<KicadNetlistPin> pins;
        for (auto* node = net->children; node; node = node->next)
            if (named(node, "node")) pins.push_back({attr(node, "ref"), attr(node, "pin")});
        put(result, attr(net, "name"), std::move(pins));
    }
    return result;
}

SomInterface parse_som_interface_xml(std::string_view xml, const std::string& source,
                                     const std::vector<std::string>& refs) {
    auto doc = parse_xml(xml, source);
    auto* root = xmlDocGetRootElement(doc.get());
    SomInterface result;
    result.source = source;
    auto* comps = child(root, "components");
    for (auto* cmp = comps ? comps->children : nullptr; cmp; cmp = cmp->next) {
        if (cmp->type != XML_ELEMENT_NODE) continue;
        const auto ref = attr(cmp, "ref");
        if (contains(refs, ref))
            put(result.connectors, ref, SomConnector{element_text(child(cmp, "value")),
                                                     element_text(child(cmp, "footprint")), {}});
    }
    std::string missing;
    for (const auto& ref : refs) if (!lookup(result.connectors, ref)) {
        if (!missing.empty()) missing += ", ";
        missing += repr(ref);
    }
    if (!missing.empty()) throw SomInterfaceError("connector refs not found in SoM netlist: [" + missing + "]");
    auto* nets = child(root, "nets");
    for (auto* net = nets ? nets->children : nullptr; net; net = net->next) {
        if (net->type != XML_ELEMENT_NODE) continue;
        const auto name = attr(net, "name");
        for (auto* node = net->children; node; node = node->next) {
            if (!named(node, "node")) continue;
            if (auto* conn = lookup(result.connectors, attr(node, "ref")))
                put(conn->pins, attr(node, "pin"), name);
        }
    }
    return result;
}

SomZynq parse_som_zynq_xml(std::string_view xml, const std::string& source,
                          const std::string& zynq_ref, const std::vector<std::string>& jrefs) {
    auto doc = parse_xml(xml, source);
    auto* root = xmlDocGetRootElement(doc.get());
    SomZynq result;
    result.source = source;
    result.zynq_ref = zynq_ref;
    std::optional<std::pair<std::string, std::string>> libsource;
    auto* comps = child(root, "components");
    for (auto* cmp = comps ? comps->children : nullptr; cmp; cmp = cmp->next) {
        if (cmp->type != XML_ELEMENT_NODE || attr(cmp, "ref") != zynq_ref) continue;
        if (auto* ls = child(cmp, "libsource")) libsource = {attr(ls, "lib"), attr(ls, "part")};
        result.value = element_text(child(cmp, "value"));
    }
    if (!libsource) throw SomInterfaceError(zynq_ref + " not found in SoM netlist " + source);
    auto* parts = child(root, "libparts");
    for (auto* part = parts ? parts->children : nullptr; part; part = part->next) {
        if (part->type != XML_ELEMENT_NODE ||
            std::make_pair(attr(part, "lib"), attr(part, "part")) != *libsource) continue;
        auto* pins = child(part, "pins");
        for (auto* pin = pins ? pins->children : nullptr; pin; pin = pin->next)
            if (pin->type == XML_ELEMENT_NODE) put(result.pin_names, attr(pin, "num"), attr(pin, "name"));
    }
    if (result.pin_names.empty()) throw SomInterfaceError("libpart pin table for " + zynq_ref + " ((" +
        repr(libsource->first) + ", " + repr(libsource->second) + ")) missing from SoM netlist");
    auto* nets = child(root, "nets");
    for (auto* net = nets ? nets->children : nullptr; net; net = net->next) {
        if (net->type != XML_ELEMENT_NODE) continue;
        const auto name = attr(net, "name");
        for (auto* node = net->children; node; node = node->next) {
            if (!named(node, "node")) continue;
            const auto ref = attr(node, "ref");
            if (ref == zynq_ref) put(result.ball_net, attr(node, "pin"), name);
            else if (contains(jrefs, ref))
                put(result.jpin_net, ref + "." + attribute(node, "pin").value_or("None"), name);
        }
    }
    return result;
}

SomInterface extract_som_interface(const fs::path& som_sch, const std::vector<std::string>& refs,
                                   const SomExtractOptions& options) {
    return parse_som_interface_xml(export_kicad_netlist_xml(som_sch, options), som_sch.string(), refs);
}

SomZynq extract_som_zynq(const fs::path& som_sch, const std::string& zynq_ref,
                        const std::vector<std::string>& jrefs, const SomExtractOptions& options) {
    return parse_som_zynq_xml(export_kicad_netlist_xml(som_sch, options), som_sch.string(), zynq_ref, jrefs);
}

SomInterface load_som_interface(const fs::path& path) {
    return som_interface_from_json(parse_json_file(path.string()), path.string());
}

SomInterface som_interface_from_json(const JsonNode& root, const std::string& source) {
    const auto where = "SoM contract " + source;
    SomInterface result;
    result.source = join_surrogates(required(root, "source", JsonKind::String, where).string_value);
    const auto& connectors = required(root, "connectors", JsonKind::Object, where);
    for (const auto& [ref, data] : connectors.object_value) {
        const auto prefix = where + " " + ref;
        SomConnector conn;
        conn.value = optional_text(data, "value", prefix);
        conn.footprint = optional_text(data, "footprint", prefix);
        for (const auto& [pin, net] : required(data, "pins", JsonKind::Object, prefix).object_value) {
            if (net.kind != JsonKind::String) throw SomInterfaceError(prefix + "." + pin + ": expected net string");
            put(conn.pins, join_surrogates(pin), join_surrogates(net.string_value));
        }
        put(result.connectors, join_surrogates(ref), std::move(conn));
    }
    return result;
}

std::string som_interface_json(const SomInterface& data) {
    auto root = object(), connectors = object();
    for (const auto& [ref, conn] : data.connectors) {
        auto entry = object();
        entry.object_value = {{"value", nullable(conn.value)}, {"footprint", nullable(conn.footprint)},
                              {"pins", dictionary(conn.pins)}};
        put(connectors.object_value, ref, std::move(entry));
    }
    root.object_value = {{"source", string(data.source)}, {"connectors", std::move(connectors)}};
    return dump(root) + '\n';
}

std::string som_zynq_json(const SomZynq& data) {
    auto root = object();
    root.object_value = {{"zynq_ref", string(data.zynq_ref)}, {"value", nullable(data.value)},
                         {"source", string(data.source)}, {"pin_names", dictionary(data.pin_names)},
                         {"ball_net", dictionary(data.ball_net)}, {"jpin_net", dictionary(data.jpin_net)}};
    return dump(root) + '\n';
}

std::string write_som_interface(const fs::path& som_sch, const std::string& comma_refs,
                                const fs::path& output, const SomExtractOptions& options) {
    std::vector<std::string> refs;
    for (std::size_t start = 0; start <= comma_refs.size();) {
        auto end = comma_refs.find(',', start);
        if (end == std::string::npos) end = comma_refs.size();
        const auto token = strip_refs_token(comma_refs.substr(start, end - start));
        if (!token.empty()) refs.push_back(token);
        if (end == comma_refs.size()) break;
        start = end + 1;
    }
    auto data = extract_som_interface(som_sch, refs, options);
    const auto json = som_interface_json(data);
    write_atomic_file(output.string(), std::vector<std::uint8_t>(json.begin(), json.end()));
    std::size_t total = 0;
    for (const auto& item : data.connectors) total += item.second.pins.size();
    std::string report = "SoM interface: " + std::to_string(refs.size()) + " connectors, " +
        std::to_string(total) + " pins -> " + output.string() + '\n';
    std::sort(data.connectors.begin(), data.connectors.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
    for (const auto& [ref, conn] : data.connectors) {
        std::size_t count = 0;
        for (const auto& item : conn.pins) if (item.second.compare(0, 12, "unconnected-") != 0) ++count;
        report += "  " + ref + " (" + conn.value.value_or("None") + "): " + std::to_string(conn.pins.size()) +
            " pins, " + std::to_string(count) + " netted\n";
    }
    return report;
}

void apply_som_to_xdc(XdcInput& input, const SomZynq& live) {
    input.ball_net = live.ball_net;
    input.pin_names = live.pin_names;
    input.jpin_net = live.jpin_net;
    input.device = live.value.value_or("");
    input.zynq_ref = live.zynq_ref;
    input.som_source = live.source;
}

}  // namespace schgen
