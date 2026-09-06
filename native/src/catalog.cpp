#include "schgen/catalog.hpp"

#include <algorithm>
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <string_view>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <utility>
#include <vector>

namespace schgen {
namespace {

namespace fs = std::filesystem;

constexpr uint32_t kCatalogMagic = 0x54434753;
constexpr uint32_t kCatalogVersion = 1;
constexpr uint32_t kHeaderBytes = 64;
constexpr uint32_t kPartRecordBytes = 64;
constexpr uint32_t kPinRecordBytes = 12;
constexpr uint32_t kModelRecordBytes = 4;
constexpr uint32_t kHashSlotBytes = 8;
constexpr uint32_t kEmptySlot = 0xFFFFFFFFu;
constexpr const char* kPartSchema = "schgen.part/1";

enum class JsonKind {
    Null,
    Bool,
    Number,
    String,
    Array,
    Object
};

struct JsonNode {
    JsonKind kind = JsonKind::Null;
    bool bool_value = false;
    double number_value = 0.0;
    std::string string_value;
    std::vector<JsonNode> array_value;
    std::vector<std::pair<std::string, JsonNode>> object_value;
};

struct JsonParser {
    std::string_view text;
    std::size_t index = 0;
    std::string source_name;

    [[noreturn]] void fail(const std::string& detail) const {
        throw std::runtime_error("catalog json " + source_name + ": " + detail);
    }

    bool at_end() const {
        return index >= text.size();
    }

    std::size_t skip_ws() {
        while (index < text.size()) {
            const char ch = text[index];
            if (ch != ' ' && ch != '\t' && ch != '\r' && ch != '\n') {
                break;
            }
            ++index;
        }
        return index;
    }

    void expect(char wanted) {
        skip_ws();
        if (at_end() || text[index] != wanted) {
            fail(std::string("expected '") + wanted + "'");
        }
        ++index;
    }

    JsonNode parse_value();

    JsonNode parse_string() {
        if (at_end() || text[index] != '"') {
            fail("expected string");
        }
        ++index;
        std::string out;
        while (!at_end()) {
            const unsigned char ch = static_cast<unsigned char>(text[index]);
            ++index;
            if (ch == '"') {
                JsonNode node;
                node.kind = JsonKind::String;
                node.string_value = std::move(out);
                return node;
            }
            if (ch == '\\') {
                if (at_end()) {
                    fail("unterminated string escape");
                }
                const char esc = text[index];
                ++index;
                if (esc == '"' || esc == '\\' || esc == '/') {
                    out.push_back(esc);
                } else if (esc == 'b') {
                    out.push_back('\b');
                } else if (esc == 'f') {
                    out.push_back('\f');
                } else if (esc == 'n') {
                    out.push_back('\n');
                } else if (esc == 'r') {
                    out.push_back('\r');
                } else if (esc == 't') {
                    out.push_back('\t');
                } else if (esc == 'u') {
                    if (index + 4 > text.size()) {
                        fail("truncated unicode escape");
                    }
                    uint32_t code = 0;
                    for (int digit_i = 0; digit_i < 4; ++digit_i) {
                        const char hex = text[index];
                        ++index;
                        code <<= 4;
                        if (hex >= '0' && hex <= '9') {
                            code |= static_cast<uint32_t>(hex - '0');
                        } else if (hex >= 'a' && hex <= 'f') {
                            code |= static_cast<uint32_t>(hex - 'a' + 10);
                        } else if (hex >= 'A' && hex <= 'F') {
                            code |= static_cast<uint32_t>(hex - 'A' + 10);
                        } else {
                            fail("invalid unicode escape");
                        }
                    }
                    if (code <= 0x7Fu) {
                        out.push_back(static_cast<char>(code));
                    } else if (code <= 0x7FFu) {
                        out.push_back(static_cast<char>(0xC0u | (code >> 6)));
                        out.push_back(static_cast<char>(0x80u | (code & 0x3Fu)));
                    } else {
                        out.push_back(static_cast<char>(0xE0u | (code >> 12)));
                        out.push_back(static_cast<char>(0x80u | ((code >> 6) & 0x3Fu)));
                        out.push_back(static_cast<char>(0x80u | (code & 0x3Fu)));
                    }
                } else {
                    fail("invalid string escape");
                }
                continue;
            }
            if (ch < 0x20) {
                fail("unescaped control character in string");
            }
            out.push_back(static_cast<char>(ch));
        }
        fail("unterminated string");
    }

    JsonNode parse_number() {
        const std::size_t start = index;
        if (!at_end() && text[index] == '-') {
            ++index;
        }
        if (at_end() || text[index] < '0' || text[index] > '9') {
            fail("invalid number");
        }
        if (text[index] == '0') {
            ++index;
        } else {
            while (!at_end() && text[index] >= '0' && text[index] <= '9') {
                ++index;
            }
        }
        if (!at_end() && text[index] == '.') {
            ++index;
            if (at_end() || text[index] < '0' || text[index] > '9') {
                fail("invalid number fraction");
            }
            while (!at_end() && text[index] >= '0' && text[index] <= '9') {
                ++index;
            }
        }
        if (!at_end() && (text[index] == 'e' || text[index] == 'E')) {
            ++index;
            if (!at_end() && (text[index] == '+' || text[index] == '-')) {
                ++index;
            }
            if (at_end() || text[index] < '0' || text[index] > '9') {
                fail("invalid number exponent");
            }
            while (!at_end() && text[index] >= '0' && text[index] <= '9') {
                ++index;
            }
        }
        JsonNode node;
        node.kind = JsonKind::Number;
        node.number_value = std::stod(std::string(text.substr(start, index - start)));
        return node;
    }

    JsonNode parse_array() {
        expect('[');
        JsonNode node;
        node.kind = JsonKind::Array;
        skip_ws();
        if (!at_end() && text[index] == ']') {
            ++index;
            return node;
        }
        while (true) {
            node.array_value.push_back(parse_value());
            skip_ws();
            if (at_end()) {
                fail("unterminated array");
            }
            if (text[index] == ']') {
                ++index;
                return node;
            }
            if (text[index] != ',') {
                fail("expected comma in array");
            }
            ++index;
        }
    }

    JsonNode parse_object() {
        expect('{');
        JsonNode node;
        node.kind = JsonKind::Object;
        skip_ws();
        if (!at_end() && text[index] == '}') {
            ++index;
            return node;
        }
        std::set<std::string> seen;
        while (true) {
            skip_ws();
            JsonNode key = parse_string();
            if (seen.count(key.string_value) != 0) {
                fail("duplicate key '" + key.string_value + "'");
            }
            seen.insert(key.string_value);
            expect(':');
            node.object_value.emplace_back(key.string_value, parse_value());
            skip_ws();
            if (at_end()) {
                fail("unterminated object");
            }
            if (text[index] == '}') {
                ++index;
                return node;
            }
            if (text[index] != ',') {
                fail("expected comma in object");
            }
            ++index;
        }
    }
};

JsonNode JsonParser::parse_value() {
    skip_ws();
    if (at_end()) {
        fail("unexpected end of file");
    }
    const char ch = text[index];
    if (ch == '"') {
        return parse_string();
    }
    if (ch == '{') {
        return parse_object();
    }
    if (ch == '[') {
        return parse_array();
    }
    if (ch == '-' || (ch >= '0' && ch <= '9')) {
        return parse_number();
    }
    if (text.substr(index, 4) == "true") {
        index += 4;
        JsonNode node;
        node.kind = JsonKind::Bool;
        node.bool_value = true;
        return node;
    }
    if (text.substr(index, 5) == "false") {
        index += 5;
        JsonNode node;
        node.kind = JsonKind::Bool;
        node.bool_value = false;
        return node;
    }
    if (text.substr(index, 4) == "null") {
        index += 4;
        JsonNode node;
        node.kind = JsonKind::Null;
        return node;
    }
    fail("invalid value");
}

JsonNode parse_json_file(const fs::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        throw std::runtime_error("catalog: cannot read " + path.string());
    }
    std::string text((std::istreambuf_iterator<char>(in)),
                     std::istreambuf_iterator<char>());
    if (text.empty()) {
        throw std::runtime_error("catalog: empty file " + path.string());
    }
    JsonParser parser;
    parser.text = text;
    parser.source_name = path.string();
    JsonNode root = parser.parse_value();
    parser.skip_ws();
    if (!parser.at_end()) {
        parser.fail("trailing content after top-level value");
    }
    return root;
}

const JsonNode* object_field(const JsonNode& node, const std::string& key) {
    if (node.kind != JsonKind::Object) {
        throw std::runtime_error("catalog: expected object for field '" + key + "'");
    }
    for (const auto& field : node.object_value) {
        if (field.first == key) {
            return &field.second;
        }
    }
    return nullptr;
}

std::string require_string(const JsonNode& node, const std::string& key,
                           bool allow_empty) {
    const JsonNode* field = object_field(node, key);
    if (field == nullptr) {
        throw std::runtime_error("catalog: missing required field '" + key + "'");
    }
    if (field->kind != JsonKind::String) {
        throw std::runtime_error("catalog: field '" + key + "' must be a string");
    }
    if (!allow_empty && field->string_value.empty()) {
        throw std::runtime_error("catalog: field '" + key + "' must not be empty");
    }
    return field->string_value;
}

void reject_unknown_keys(const JsonNode& node,
                         const std::set<std::string>& allowed,
                         const std::string& where) {
    if (node.kind != JsonKind::Object) {
        throw std::runtime_error("catalog: " + where + " must be an object");
    }
    for (const auto& field : node.object_value) {
        if (allowed.count(field.first) == 0) {
            throw std::runtime_error("catalog: unknown key '" + field.first
                                     + "' in " + where);
        }
    }
}

CatalogPart parse_part_json(const fs::path& path) {
    const JsonNode root = parse_json_file(path);
    static const std::set<std::string> allowed = {
        "schema", "mpn", "safe_name", "lcsc", "description", "manufacturer",
        "package", "jlc_class", "prefix", "datasheet", "product_url",
        "lib_id", "footprint", "models_3d", "pins"};
    reject_unknown_keys(root, allowed, path.string());
    const std::string schema = require_string(root, "schema", false);
    if (schema != kPartSchema) {
        throw std::runtime_error("catalog: " + path.string()
                                 + " schema must be " + std::string(kPartSchema));
    }
    CatalogPart part;
    part.mpn = require_string(root, "mpn", false);
    part.safe_name = require_string(root, "safe_name", false);
    part.lcsc = require_string(root, "lcsc", false);
    part.description = require_string(root, "description", false);
    part.manufacturer = require_string(root, "manufacturer", false);
    part.package = require_string(root, "package", false);
    part.jlc_class = require_string(root, "jlc_class", true);
    part.prefix = require_string(root, "prefix", false);
    part.datasheet = require_string(root, "datasheet", false);
    part.product_url = require_string(root, "product_url", true);
    part.lib_id = require_string(root, "lib_id", false);
    part.footprint = require_string(root, "footprint", false);
    const JsonNode* models = object_field(root, "models_3d");
    if (models == nullptr) {
        throw std::runtime_error("catalog: missing required field 'models_3d'");
    }
    if (models->kind != JsonKind::Array) {
        throw std::runtime_error("catalog: field 'models_3d' must be an array");
    }
    for (const JsonNode& model : models->array_value) {
        if (model.kind != JsonKind::String || model.string_value.empty()) {
            throw std::runtime_error("catalog: models_3d entries must be non-empty strings");
        }
        part.models_3d.push_back(model.string_value);
    }
    const JsonNode* pins = object_field(root, "pins");
    if (pins == nullptr) {
        throw std::runtime_error("catalog: missing required field 'pins'");
    }
    if (pins->kind != JsonKind::Array || pins->array_value.empty()) {
        throw std::runtime_error("catalog: field 'pins' must be a non-empty array");
    }
    static const std::set<std::string> pin_keys = {"num", "name", "etype"};
    for (const JsonNode& pin_node : pins->array_value) {
        reject_unknown_keys(pin_node, pin_keys, "pin");
        CatalogPin pin;
        pin.number = require_string(pin_node, "num", false);
        pin.name = require_string(pin_node, "name", false);
        pin.etype = require_string(pin_node, "etype", false);
        part.pins.push_back(std::move(pin));
    }
    return part;
}

uint32_t fnv1a_32(std::string_view text) {
    uint32_t hash = 2166136261u;
    for (unsigned char ch : text) {
        hash ^= static_cast<uint32_t>(ch);
        hash *= 16777619u;
    }
    return hash;
}

uint32_t next_pow2(uint32_t value) {
    uint32_t slots = 1;
    while (slots < value) {
        slots <<= 1;
        if (slots == 0) {
            throw std::runtime_error("catalog: hash table overflow");
        }
    }
    return slots;
}

void poke_u32(std::vector<uint8_t>& buf, std::size_t offset, uint32_t value) {
    if (offset + 4 > buf.size()) {
        throw std::runtime_error("catalog: write past buffer end");
    }
    buf[offset] = static_cast<uint8_t>(value);
    buf[offset + 1] = static_cast<uint8_t>(value >> 8);
    buf[offset + 2] = static_cast<uint8_t>(value >> 16);
    buf[offset + 3] = static_cast<uint8_t>(value >> 24);
}

uint32_t read_u32(const uint8_t* data, std::size_t offset, std::size_t size) {
    if (offset + 4 > size) {
        throw std::runtime_error("catalog: read past mapped file");
    }
    return static_cast<uint32_t>(data[offset])
           | (static_cast<uint32_t>(data[offset + 1]) << 8)
           | (static_cast<uint32_t>(data[offset + 2]) << 16)
           | (static_cast<uint32_t>(data[offset + 3]) << 24);
}

struct StringPool {
    std::vector<char> bytes;
    std::map<std::string, uint32_t> interned;

    StringPool() {
        bytes.push_back('\0');
        interned.emplace(std::string(), 0);
    }

    uint32_t intern(const std::string& text) {
        const auto it = interned.find(text);
        if (it != interned.end()) {
            return it->second;
        }
        const uint32_t offset = static_cast<uint32_t>(bytes.size());
        bytes.insert(bytes.end(), text.begin(), text.end());
        bytes.push_back('\0');
        interned.emplace(text, offset);
        return offset;
    }
};

struct CatalogFile {
    int file_desc = -1;
    uint8_t* map_base = nullptr;
    std::size_t map_size = 0;
    std::string file_path;

    bool release() {
        if (map_base != nullptr) {
            if (munmap(map_base, map_size) != 0) {
                throw std::runtime_error(
                    std::string("catalog: munmap failed: ") + std::strerror(errno));
            }
            map_base = nullptr;
        }
        if (file_desc >= 0) {
            if (close(file_desc) != 0) {
                throw std::runtime_error(
                    std::string("catalog: close failed: ") + std::strerror(errno));
            }
            file_desc = -1;
        }
        map_size = 0;
        file_path.clear();
        return true;
    }
};

CatalogFile g_catalog;

const char* pool_string(const uint8_t* data, uint32_t pool_off,
                        uint32_t pool_bytes, uint32_t str_off) {
    if (str_off >= pool_bytes) {
        throw std::runtime_error("catalog: string offset out of pool");
    }
    const char* start = reinterpret_cast<const char*>(data + pool_off + str_off);
    const char* end = reinterpret_cast<const char*>(data + pool_off + pool_bytes);
    if (std::find(start, end, '\0') == end) {
        throw std::runtime_error("catalog: unterminated interned string");
    }
    return start;
}

void validate_header(const uint8_t* data, std::size_t size) {
    if (size < kHeaderBytes) {
        throw std::runtime_error("catalog: file shorter than header");
    }
    const uint32_t magic = read_u32(data, 0, size);
    if (magic != kCatalogMagic) {
        throw std::runtime_error("catalog: bad magic");
    }
    const uint32_t version = read_u32(data, 4, size);
    if (version != kCatalogVersion) {
        throw std::runtime_error("catalog: unsupported version");
    }
    const uint32_t header_bytes = read_u32(data, 8, size);
    if (header_bytes != kHeaderBytes) {
        throw std::runtime_error("catalog: header size mismatch");
    }
    const uint32_t part_count = read_u32(data, 12, size);
    const uint32_t pin_count = read_u32(data, 16, size);
    const uint32_t model_count = read_u32(data, 20, size);
    const uint32_t hash_slots = read_u32(data, 24, size);
    const uint32_t string_bytes = read_u32(data, 28, size);
    const uint32_t part_off = read_u32(data, 32, size);
    const uint32_t pin_off = read_u32(data, 36, size);
    const uint32_t model_off = read_u32(data, 40, size);
    const uint32_t hash_off = read_u32(data, 44, size);
    const uint32_t pool_off = read_u32(data, 48, size);
    if (hash_slots == 0 || (hash_slots & (hash_slots - 1)) != 0) {
        throw std::runtime_error("catalog: hash_slots must be a power of two");
    }
    auto fits = [&](uint32_t off, uint64_t bytes) {
        if (static_cast<uint64_t>(off) + bytes > size) {
            throw std::runtime_error("catalog: table overruns file");
        }
    };
    fits(part_off, static_cast<uint64_t>(part_count) * kPartRecordBytes);
    fits(pin_off, static_cast<uint64_t>(pin_count) * kPinRecordBytes);
    fits(model_off, static_cast<uint64_t>(model_count) * kModelRecordBytes);
    fits(hash_off, static_cast<uint64_t>(hash_slots) * kHashSlotBytes);
    fits(pool_off, string_bytes);
}

}  // namespace

bool compile_part_catalog(const std::string& parts_dir,
                          const std::string& catalog_path) {
    try {
        const fs::path root(parts_dir);
        if (!fs::is_directory(root)) {
            throw std::runtime_error("catalog: parts directory missing: " + parts_dir);
        }
        std::vector<fs::path> json_paths;
        for (const auto& entry : fs::directory_iterator(root)) {
            if (!entry.is_directory()) {
                continue;
            }
            const fs::path json_path = entry.path() / "part.json";
            if (!fs::is_regular_file(json_path)) {
                throw std::runtime_error(
                    "catalog: " + entry.path().filename().string()
                    + " has no part.json");
            }
            json_paths.push_back(json_path);
        }
        if (json_paths.empty()) {
            throw std::runtime_error("catalog: no part.json files under " + parts_dir);
        }
        std::sort(json_paths.begin(), json_paths.end());
        std::vector<CatalogPart> parts;
        parts.reserve(json_paths.size());
        std::set<std::string> mpns;
        std::set<std::string> safe_names;
        for (const fs::path& json_path : json_paths) {
            CatalogPart part = parse_part_json(json_path);
            if (!mpns.insert(part.mpn).second) {
                throw std::runtime_error("catalog: duplicate mpn " + part.mpn);
            }
            if (!safe_names.insert(part.safe_name).second) {
                throw std::runtime_error(
                    "catalog: duplicate safe_name " + part.safe_name);
            }
            parts.push_back(std::move(part));
        }
        std::sort(parts.begin(), parts.end(),
                  [](const CatalogPart& a, const CatalogPart& b) {
                      return a.safe_name < b.safe_name;
                  });
        StringPool pool;
        uint32_t pin_count = 0;
        uint32_t model_count = 0;
        for (const CatalogPart& part : parts) {
            pin_count += static_cast<uint32_t>(part.pins.size());
            model_count += static_cast<uint32_t>(part.models_3d.size());
        }
        const uint32_t part_count = static_cast<uint32_t>(parts.size());
        const uint32_t hash_slots = next_pow2(part_count * 4);
        const uint32_t part_off = kHeaderBytes;
        const uint32_t pin_off = part_off + part_count * kPartRecordBytes;
        const uint32_t model_off = pin_off + pin_count * kPinRecordBytes;
        uint32_t hash_off = model_off + model_count * kModelRecordBytes;
        if (hash_off % 8u != 0) {
            hash_off += 8u - (hash_off % 8u);
        }
        const uint32_t pool_off = hash_off + hash_slots * kHashSlotBytes;
        std::vector<uint8_t> buf(pool_off, 0);
        poke_u32(buf, 0, kCatalogMagic);
        poke_u32(buf, 4, kCatalogVersion);
        poke_u32(buf, 8, kHeaderBytes);
        poke_u32(buf, 12, part_count);
        poke_u32(buf, 16, pin_count);
        poke_u32(buf, 20, model_count);
        poke_u32(buf, 24, hash_slots);
        poke_u32(buf, 32, part_off);
        poke_u32(buf, 36, pin_off);
        poke_u32(buf, 40, model_off);
        poke_u32(buf, 44, hash_off);
        poke_u32(buf, 48, pool_off);
        uint32_t pin_index = 0;
        uint32_t model_index = 0;
        std::vector<uint32_t> hash_mpn(hash_slots, kEmptySlot);
        std::vector<uint32_t> hash_part(hash_slots, kEmptySlot);
        for (uint32_t part_i = 0; part_i < part_count; ++part_i) {
            const CatalogPart& part = parts[part_i];
            const uint32_t rec = part_off + part_i * kPartRecordBytes;
            poke_u32(buf, rec + 0, pool.intern(part.mpn));
            poke_u32(buf, rec + 4, pool.intern(part.safe_name));
            poke_u32(buf, rec + 8, pool.intern(part.lcsc));
            poke_u32(buf, rec + 12, pool.intern(part.description));
            poke_u32(buf, rec + 16, pool.intern(part.manufacturer));
            poke_u32(buf, rec + 20, pool.intern(part.package));
            poke_u32(buf, rec + 24, pool.intern(part.jlc_class));
            poke_u32(buf, rec + 28, pool.intern(part.prefix));
            poke_u32(buf, rec + 32, pool.intern(part.datasheet));
            poke_u32(buf, rec + 36, pool.intern(part.product_url));
            poke_u32(buf, rec + 40, pool.intern(part.lib_id));
            poke_u32(buf, rec + 44, pool.intern(part.footprint));
            poke_u32(buf, rec + 48, pin_index);
            poke_u32(buf, rec + 52, static_cast<uint32_t>(part.pins.size()));
            poke_u32(buf, rec + 56, model_index);
            poke_u32(buf, rec + 60, static_cast<uint32_t>(part.models_3d.size()));
            for (const CatalogPin& pin : part.pins) {
                const uint32_t poff = pin_off + pin_index * kPinRecordBytes;
                poke_u32(buf, poff + 0, pool.intern(pin.number));
                poke_u32(buf, poff + 4, pool.intern(pin.name));
                poke_u32(buf, poff + 8, pool.intern(pin.etype));
                ++pin_index;
            }
            for (const std::string& model : part.models_3d) {
                const uint32_t moff = model_off + model_index * kModelRecordBytes;
                poke_u32(buf, moff, pool.intern(model));
                ++model_index;
            }
            auto insert_key = [&](const std::string& key) {
                uint32_t slot = fnv1a_32(key) & (hash_slots - 1);
                for (uint32_t probe = 0; probe < hash_slots; ++probe) {
                    if (hash_mpn[slot] == kEmptySlot) {
                        hash_mpn[slot] = pool.intern(key);
                        hash_part[slot] = part_i;
                        return true;
                    }
                    slot = (slot + 1) & (hash_slots - 1);
                }
                return false;
            };
            if (!insert_key(part.safe_name)) {
                throw std::runtime_error(
                    "catalog: hash insert failed for " + part.safe_name);
            }
            if (part.mpn != part.safe_name && !insert_key(part.mpn)) {
                throw std::runtime_error(
                    "catalog: hash insert failed for " + part.mpn);
            }
        }
        for (uint32_t slot = 0; slot < hash_slots; ++slot) {
            poke_u32(buf, hash_off + slot * kHashSlotBytes + 0, hash_mpn[slot]);
            poke_u32(buf, hash_off + slot * kHashSlotBytes + 4, hash_part[slot]);
        }
        poke_u32(buf, 28, static_cast<uint32_t>(pool.bytes.size()));
        buf.insert(buf.end(), pool.bytes.begin(), pool.bytes.end());
        const fs::path out_path(catalog_path);
        if (!out_path.parent_path().empty()) {
            fs::create_directories(out_path.parent_path());
        }
        std::ofstream out(out_path, std::ios::binary | std::ios::trunc);
        if (!out) {
            throw std::runtime_error("catalog: cannot write " + catalog_path);
        }
        out.write(reinterpret_cast<const char*>(buf.data()),
                  static_cast<std::streamsize>(buf.size()));
        if (!out) {
            throw std::runtime_error("catalog: write failed " + catalog_path);
        }
        return true;
    } catch (const std::exception& exc) {
        throw std::runtime_error(std::string("catalog compile failed: ") + exc.what());
    }
}

bool open_part_catalog(const std::string& catalog_path) {
    try {
        if (g_catalog.map_base != nullptr && g_catalog.file_path == catalog_path) {
            return true;
        }
        if (g_catalog.map_base != nullptr) {
            g_catalog.release();
        }
        const int fd = open(catalog_path.c_str(), O_RDONLY);
        if (fd < 0) {
            throw std::runtime_error(std::string("open failed: ") + std::strerror(errno)
                                     + " (" + catalog_path + ")");
        }
        struct stat st {};
        if (fstat(fd, &st) != 0) {
            close(fd);
            throw std::runtime_error(std::string("fstat failed: ") + std::strerror(errno));
        }
        if (st.st_size <= 0) {
            close(fd);
            throw std::runtime_error("empty catalog file");
        }
        void* mapped = mmap(nullptr, static_cast<std::size_t>(st.st_size), PROT_READ,
                            MAP_PRIVATE, fd, 0);
        if (mapped == MAP_FAILED) {
            close(fd);
            throw std::runtime_error(std::string("mmap failed: ") + std::strerror(errno));
        }
        g_catalog.file_desc = fd;
        g_catalog.map_base = static_cast<uint8_t*>(mapped);
        g_catalog.map_size = static_cast<std::size_t>(st.st_size);
        g_catalog.file_path = catalog_path;
        validate_header(g_catalog.map_base, g_catalog.map_size);
        return true;
    } catch (const std::exception& exc) {
        try {
            g_catalog.release();
        } catch (...) {
            std::abort();
        }
        throw std::runtime_error(std::string("catalog open failed: ") + exc.what());
    }
}

bool close_part_catalog() {
    try {
        return g_catalog.release();
    } catch (const std::exception& exc) {
        throw std::runtime_error(std::string("catalog close failed: ") + exc.what());
    }
}

CatalogPart lookup_part_catalog(const std::string& mpn) {
    try {
        if (g_catalog.map_base == nullptr) {
            throw std::runtime_error("catalog is not open");
        }
        if (mpn.empty()) {
            throw std::runtime_error("mpn must not be empty");
        }
        const uint8_t* data = g_catalog.map_base;
        const std::size_t size = g_catalog.map_size;
        const uint32_t part_count = read_u32(data, 12, size);
        const uint32_t hash_slots = read_u32(data, 24, size);
        const uint32_t string_bytes = read_u32(data, 28, size);
        const uint32_t part_off = read_u32(data, 32, size);
        const uint32_t pin_off = read_u32(data, 36, size);
        const uint32_t model_off = read_u32(data, 40, size);
        const uint32_t hash_off = read_u32(data, 44, size);
        const uint32_t pool_off = read_u32(data, 48, size);
        uint32_t slot = fnv1a_32(mpn) & (hash_slots - 1);
        uint32_t part_index = kEmptySlot;
        for (uint32_t probe = 0; probe < hash_slots; ++probe) {
            const uint32_t mpn_off = read_u32(
                data, hash_off + slot * kHashSlotBytes + 0, size);
            if (mpn_off == kEmptySlot) {
                break;
            }
            const char* key = pool_string(data, pool_off, string_bytes, mpn_off);
            if (mpn == key) {
                part_index = read_u32(data, hash_off + slot * kHashSlotBytes + 4, size);
                break;
            }
            slot = (slot + 1) & (hash_slots - 1);
        }
        if (part_index == kEmptySlot || part_index >= part_count) {
            throw std::runtime_error("unknown mpn '" + mpn + "'");
        }
        const uint32_t rec = part_off + part_index * kPartRecordBytes;
        auto field = [&](uint32_t extra) {
            const uint32_t off = read_u32(data, rec + extra, size);
            return std::string(pool_string(data, pool_off, string_bytes, off));
        };
        CatalogPart part;
        part.mpn = field(0);
        part.safe_name = field(4);
        part.lcsc = field(8);
        part.description = field(12);
        part.manufacturer = field(16);
        part.package = field(20);
        part.jlc_class = field(24);
        part.prefix = field(28);
        part.datasheet = field(32);
        part.product_url = field(36);
        part.lib_id = field(40);
        part.footprint = field(44);
        const uint32_t pin_index = read_u32(data, rec + 48, size);
        const uint32_t pin_n = read_u32(data, rec + 52, size);
        const uint32_t model_index = read_u32(data, rec + 56, size);
        const uint32_t model_n = read_u32(data, rec + 60, size);
        part.pins.reserve(pin_n);
        for (uint32_t i = 0; i < pin_n; ++i) {
            const uint32_t poff = pin_off + (pin_index + i) * kPinRecordBytes;
            CatalogPin pin;
            pin.number = pool_string(data, pool_off, string_bytes,
                                     read_u32(data, poff + 0, size));
            pin.name = pool_string(data, pool_off, string_bytes,
                                   read_u32(data, poff + 4, size));
            pin.etype = pool_string(data, pool_off, string_bytes,
                                    read_u32(data, poff + 8, size));
            part.pins.push_back(std::move(pin));
        }
        part.models_3d.reserve(model_n);
        for (uint32_t i = 0; i < model_n; ++i) {
            const uint32_t moff = model_off + (model_index + i) * kModelRecordBytes;
            part.models_3d.emplace_back(pool_string(
                data, pool_off, string_bytes, read_u32(data, moff, size)));
        }
        return part;
    } catch (const std::exception& exc) {
        throw std::runtime_error(std::string("catalog lookup failed: ") + exc.what());
    }
}

std::size_t part_catalog_count() {
    try {
        if (g_catalog.map_base == nullptr) {
            throw std::runtime_error("catalog is not open");
        }
        return read_u32(g_catalog.map_base, 12, g_catalog.map_size);
    } catch (const std::exception& exc) {
        throw std::runtime_error(std::string("catalog count failed: ") + exc.what());
    }
}

}  // namespace schgen
