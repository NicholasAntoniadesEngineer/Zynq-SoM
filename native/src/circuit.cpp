#include "schgen/circuit.hpp"
#include "schgen/json.hpp"

#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <filesystem>
#include <fstream>
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

constexpr uint32_t kCircuitMagic = 0x43524353;
constexpr uint32_t kCircuitVersion = 1;
constexpr uint32_t kHeaderBytes = 128;
constexpr uint32_t kCircuitRecBytes = 64;
constexpr uint32_t kPartRecBytes = 40;
constexpr uint32_t kFieldRecBytes = 8;
constexpr uint32_t kPinNameRecBytes = 8;
constexpr uint32_t kPinNumRecBytes = 4;
constexpr uint32_t kNetRecBytes = 16;
constexpr uint32_t kNetPinRecBytes = 8;
constexpr uint32_t kNcRecBytes = 8;
constexpr uint32_t kPortRecBytes = 48;
constexpr uint32_t kHintRecBytes = 8;
constexpr uint32_t kLoadRecBytes = 16;
constexpr uint32_t kWaiverRecBytes = 12;
constexpr uint32_t kHashSlotBytes = 8;
constexpr uint32_t kEmptySlot = 0xFFFFFFFFu;
constexpr const char* kCircuitSchema = "schgen.circuit/1";

const std::vector<std::string> kWaiverKinds = {
    "tp_waivers", "decap_waivers", "pull_waivers", "reset_waivers",
    "strap_waivers", "ep_waivers", "thermal_waivers", "part_rule_waivers"};

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
            throw std::runtime_error("circuit: hash table overflow");
        }
    }
    return slots;
}

void poke_u32(std::vector<uint8_t>& buf, std::size_t offset, uint32_t value) {
    if (offset + 4 > buf.size()) {
        throw std::runtime_error("circuit: write past buffer end");
    }
    buf[offset] = static_cast<uint8_t>(value);
    buf[offset + 1] = static_cast<uint8_t>(value >> 8);
    buf[offset + 2] = static_cast<uint8_t>(value >> 16);
    buf[offset + 3] = static_cast<uint8_t>(value >> 24);
}

void poke_f64(std::vector<uint8_t>& buf, std::size_t offset, double value) {
    if (offset + 8 > buf.size()) {
        throw std::runtime_error("circuit: write past buffer end");
    }
    uint64_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    for (int i = 0; i < 8; ++i) {
        buf[offset + static_cast<std::size_t>(i)] =
            static_cast<uint8_t>(bits >> (8 * i));
    }
}

uint32_t read_u32(const uint8_t* data, std::size_t offset, std::size_t size) {
    if (offset + 4 > size) {
        throw std::runtime_error("circuit: read past mapped file");
    }
    return static_cast<uint32_t>(data[offset])
           | (static_cast<uint32_t>(data[offset + 1]) << 8)
           | (static_cast<uint32_t>(data[offset + 2]) << 16)
           | (static_cast<uint32_t>(data[offset + 3]) << 24);
}

double read_f64(const uint8_t* data, std::size_t offset, std::size_t size) {
    if (offset + 8 > size) {
        throw std::runtime_error("circuit: read past mapped file");
    }
    uint64_t bits = 0;
    for (int i = 0; i < 8; ++i) {
        bits |= static_cast<uint64_t>(data[offset + static_cast<std::size_t>(i)])
                << (8 * i);
    }
    double value = 0.0;
    std::memcpy(&value, &bits, sizeof(value));
    return value;
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
                    std::string("circuit: munmap failed: ") + std::strerror(errno));
            }
            map_base = nullptr;
        }
        if (file_desc >= 0) {
            if (close(file_desc) != 0) {
                throw std::runtime_error(
                    std::string("circuit: close failed: ") + std::strerror(errno));
            }
            file_desc = -1;
        }
        map_size = 0;
        file_path.clear();
        return true;
    }
};

CatalogFile g_circuits;

const char* pool_string(const uint8_t* data, uint32_t pool_off,
                        uint32_t pool_bytes, uint32_t str_off) {
    if (str_off >= pool_bytes) {
        throw std::runtime_error("circuit: string offset out of pool");
    }
    const char* start = reinterpret_cast<const char*>(data + pool_off + str_off);
    const char* end = reinterpret_cast<const char*>(data + pool_off + pool_bytes);
    if (std::find(start, end, '\0') == end) {
        throw std::runtime_error("circuit: unterminated interned string");
    }
    return start;
}

std::string opt_string_field(const JsonNode& node, const std::string& key,
                             bool* present, const std::string& prefix) {
    const JsonNode* field = object_field(node, key);
    if (field == nullptr) {
        throw std::runtime_error(prefix + ": missing required field '" + key + "'");
    }
    if (field->kind == JsonKind::Null) {
        *present = false;
        return std::string();
    }
    if (field->kind != JsonKind::String) {
        throw std::runtime_error(prefix + ": field '" + key + "' must be a string or null");
    }
    *present = true;
    return field->string_value;
}

int32_t opt_int32_field(const JsonNode& node, const std::string& key,
                        bool* present, const std::string& prefix) {
    const JsonNode* field = object_field(node, key);
    if (field == nullptr) {
        throw std::runtime_error(prefix + ": missing required field '" + key + "'");
    }
    if (field->kind == JsonKind::Null) {
        *present = false;
        return 0;
    }
    if (field->kind != JsonKind::Number) {
        throw std::runtime_error(prefix + ": field '" + key + "' must be a number or null");
    }
    if (std::trunc(field->number_value) != field->number_value) {
        throw std::runtime_error(prefix + ": field '" + key + "' must be an integer or null");
    }
    *present = true;
    return static_cast<int32_t>(field->number_value);
}

double opt_f64_field(const JsonNode& node, const std::string& key,
                     bool* present, const std::string& prefix) {
    const JsonNode* field = object_field(node, key);
    if (field == nullptr) {
        throw std::runtime_error(prefix + ": missing required field '" + key + "'");
    }
    if (field->kind == JsonKind::Null) {
        *present = false;
        return 0.0;
    }
    if (field->kind != JsonKind::Number) {
        throw std::runtime_error(prefix + ": field '" + key + "' must be a number or null");
    }
    *present = true;
    return field->number_value;
}

CircuitPinRefIr parse_pin_spec(const std::string& spec, const std::string& where) {
    const std::size_t dot = spec.find('.');
    if (dot == std::string::npos || dot == 0 || dot + 1 >= spec.size()) {
        throw std::runtime_error(where + ": bad pin spec '" + spec + "'");
    }
    CircuitPinRefIr pin;
    pin.ref = spec.substr(0, dot);
    pin.pin = spec.substr(dot + 1);
    return pin;
}

std::vector<std::string> require_string_array(const JsonNode& node,
                                              const std::string& key,
                                              const std::string& prefix) {
    const JsonNode* field = object_field(node, key);
    if (field == nullptr) {
        throw std::runtime_error(prefix + ": missing required field '" + key + "'");
    }
    if (field->kind != JsonKind::Array) {
        throw std::runtime_error(prefix + ": field '" + key + "' must be an array");
    }
    std::vector<std::string> out;
    for (const JsonNode& item : field->array_value) {
        if (item.kind != JsonKind::String || item.string_value.empty()) {
            throw std::runtime_error(prefix + ": " + key + " entries must be non-empty strings");
        }
        out.push_back(item.string_value);
    }
    return out;
}

std::vector<CircuitFieldIr> parse_fields(const JsonNode& node, const std::string& prefix) {
    const JsonNode* field = object_field(node, "fields");
    if (field == nullptr) {
        throw std::runtime_error(prefix + ": missing required field 'fields'");
    }
    if (field->kind != JsonKind::Object) {
        throw std::runtime_error(prefix + ": field 'fields' must be an object");
    }
    std::vector<CircuitFieldIr> out;
    for (const auto& kv : field->object_value) {
        if (kv.first.empty()) {
            throw std::runtime_error(prefix + ": fields keys must be non-empty strings");
        }
        if (kv.second.kind != JsonKind::String) {
            throw std::runtime_error(prefix + ": fields values must be strings");
        }
        CircuitFieldIr rec;
        rec.key = kv.first;
        rec.value = kv.second.string_value;
        out.push_back(std::move(rec));
    }
    return out;
}

std::vector<CircuitPinNameIr> parse_pin_names(const JsonNode& node,
                                              const std::string& prefix) {
    const JsonNode* field = object_field(node, "pin_names");
    if (field == nullptr) {
        throw std::runtime_error(prefix + ": missing required field 'pin_names'");
    }
    if (field->kind != JsonKind::Object) {
        throw std::runtime_error(prefix + ": field 'pin_names' must be an object");
    }
    std::vector<CircuitPinNameIr> out;
    for (const auto& kv : field->object_value) {
        if (kv.first.empty()) {
            throw std::runtime_error(prefix + ": pin_names keys must be non-empty strings");
        }
        if (kv.second.kind != JsonKind::Array) {
            throw std::runtime_error(prefix + ": pin_names values must be arrays");
        }
        CircuitPinNameIr rec;
        rec.name = kv.first;
        for (const JsonNode& item : kv.second.array_value) {
            if (item.kind != JsonKind::String || item.string_value.empty()) {
                throw std::runtime_error(
                    prefix + ": pin_names entries must be non-empty strings");
            }
            rec.numbers.push_back(item.string_value);
        }
        out.push_back(std::move(rec));
    }
    return out;
}

std::vector<CircuitHintIr> parse_hints(const JsonNode& node, const std::string& prefix) {
    const JsonNode* field = object_field(node, "hints");
    if (field == nullptr) {
        throw std::runtime_error(prefix + ": missing required field 'hints'");
    }
    if (field->kind != JsonKind::Object) {
        throw std::runtime_error(prefix + ": field 'hints' must be an object");
    }
    std::vector<CircuitHintIr> out;
    for (const auto& kv : field->object_value) {
        if (kv.first.empty() || kv.second.kind != JsonKind::String) {
            throw std::runtime_error(prefix + ": hints must map strings to strings");
        }
        CircuitHintIr rec;
        rec.net = kv.first;
        rec.style = kv.second.string_value;
        out.push_back(std::move(rec));
    }
    return out;
}

std::vector<CircuitLoadIr> parse_loads(const JsonNode& node, const std::string& prefix) {
    const JsonNode* field = object_field(node, "loads");
    if (field == nullptr) {
        throw std::runtime_error(prefix + ": missing required field 'loads'");
    }
    if (field->kind != JsonKind::Object) {
        throw std::runtime_error(prefix + ": field 'loads' must be an object");
    }
    std::vector<CircuitLoadIr> out;
    for (const auto& kv : field->object_value) {
        if (kv.first.empty() || kv.second.kind != JsonKind::Array
            || kv.second.array_value.empty()) {
            throw std::runtime_error(prefix + ": loads must map rails to non-empty arrays");
        }
        for (const JsonNode& row : kv.second.array_value) {
            if (row.kind != JsonKind::Array || row.array_value.size() != 2
                || row.array_value[0].kind != JsonKind::Number
                || row.array_value[1].kind != JsonKind::String) {
                throw std::runtime_error(prefix + ": loads entries must be [amps, note]");
            }
            CircuitLoadIr rec;
            rec.rail = kv.first;
            rec.amps = row.array_value[0].number_value;
            rec.note = row.array_value[1].string_value;
            out.push_back(std::move(rec));
        }
    }
    return out;
}

std::vector<CircuitWaiverIr> parse_waivers(const JsonNode& node,
                                           const std::string& prefix) {
    std::vector<CircuitWaiverIr> out;
    for (const std::string& kind : kWaiverKinds) {
        const JsonNode* field = object_field(node, kind);
        if (field == nullptr) {
            throw std::runtime_error(prefix + ": missing required field '" + kind + "'");
        }
        if (field->kind != JsonKind::Object) {
            throw std::runtime_error(prefix + ": field '" + kind + "' must be an object");
        }
        for (const auto& kv : field->object_value) {
            if (kv.first.empty() || kv.second.kind != JsonKind::String) {
                throw std::runtime_error(prefix + ": " + kind + " must map strings to strings");
            }
            CircuitWaiverIr rec;
            rec.kind = kind;
            rec.key = kv.first;
            rec.reason = kv.second.string_value;
            out.push_back(std::move(rec));
        }
    }
    return out;
}

CircuitSheetIr parse_circuit_json(const fs::path& path) {
    const JsonNode root = parse_json_file(path.string());
    static const std::set<std::string> allowed = {
        "schema", "name", "title", "parts", "nets", "nc", "port_types",
        "hints", "loads", "tp_waivers", "decap_waivers", "pull_waivers",
        "reset_waivers", "strap_waivers", "ep_waivers", "thermal_waivers",
        "part_rule_waivers"};
    reject_unknown_keys(root, allowed, "circuit " + path.string());
    CircuitSheetIr sheet;
    sheet.schema = require_string(root, "schema", false, "circuit");
    if (sheet.schema != kCircuitSchema) {
        throw std::runtime_error("circuit: " + path.string()
                                 + " schema must be " + std::string(kCircuitSchema));
    }
    sheet.name = require_string(root, "name", false, "circuit");
    sheet.title = require_string(root, "title", true, "circuit");
    const JsonNode* parts = object_field(root, "parts");
    if (parts == nullptr || parts->kind != JsonKind::Array) {
        throw std::runtime_error("circuit: field 'parts' must be an array");
    }
    static const std::set<std::string> part_keys = {
        "ref", "lib_id", "value", "footprint", "fields", "pin_names", "pin_numbers"};
    std::set<std::string> seen_refs;
    for (std::size_t i = 0; i < parts->array_value.size(); ++i) {
        const JsonNode& prec = parts->array_value[i];
        const std::string where = "circuit " + sheet.name + " parts[" + std::to_string(i) + "]";
        reject_unknown_keys(prec, part_keys, where);
        CircuitPartIr part;
        part.ref = require_string(prec, "ref", false, "circuit");
        if (!seen_refs.insert(part.ref).second) {
            throw std::runtime_error(where + ": duplicate reference '" + part.ref + "'");
        }
        part.lib_id = require_string(prec, "lib_id", false, "circuit");
        part.value = require_string(prec, "value", false, "circuit");
        part.footprint = require_string(prec, "footprint", true, "circuit");
        part.fields = parse_fields(prec, where);
        part.pin_names = parse_pin_names(prec, where);
        part.pin_numbers = require_string_array(prec, "pin_numbers", where);
        sheet.parts.push_back(std::move(part));
    }
    const JsonNode* nets = object_field(root, "nets");
    if (nets == nullptr || nets->kind != JsonKind::Array) {
        throw std::runtime_error("circuit: field 'nets' must be an array");
    }
    static const std::set<std::string> net_keys = {"name", "net_class", "pins"};
    std::set<std::string> seen_nets;
    for (std::size_t i = 0; i < nets->array_value.size(); ++i) {
        const JsonNode& nrec = nets->array_value[i];
        const std::string where = "circuit " + sheet.name + " nets[" + std::to_string(i) + "]";
        reject_unknown_keys(nrec, net_keys, where);
        CircuitNetIr net;
        net.name = require_string(nrec, "name", false, "circuit");
        if (!seen_nets.insert(net.name).second) {
            throw std::runtime_error(where + ": duplicate net '" + net.name + "'");
        }
        net.net_class = require_string(nrec, "net_class", false, "circuit");
        if (net.net_class != "power" && net.net_class != "ground"
            && net.net_class != "signal" && net.net_class != "port") {
            throw std::runtime_error(where + ": unknown net_class '" + net.net_class + "'");
        }
        for (const std::string& spec : require_string_array(nrec, "pins", where)) {
            net.pins.push_back(parse_pin_spec(spec, where));
        }
        sheet.nets.push_back(std::move(net));
    }
    for (const std::string& spec : require_string_array(root, "nc", "circuit")) {
        sheet.nc.push_back(parse_pin_spec(spec, "circuit nc"));
    }
    const JsonNode* ports = object_field(root, "port_types");
    if (ports == nullptr || ports->kind != JsonKind::Object) {
        throw std::runtime_error("circuit: field 'port_types' must be an object");
    }
    static const std::set<std::string> port_keys = {
        "kind", "pair_with", "impedance", "role", "bus", "speed_hz", "level_v", "expect"};
    for (const auto& kv : ports->object_value) {
        if (kv.first.empty()) {
            throw std::runtime_error("circuit: port_types keys must be non-empty strings");
        }
        const std::string where = "circuit " + sheet.name + " port_types[" + kv.first + "]";
        reject_unknown_keys(kv.second, port_keys, where);
        CircuitPortIr port;
        port.net = kv.first;
        port.kind = require_string(kv.second, "kind", false, "circuit");
        port.pair_with = opt_string_field(kv.second, "pair_with", &port.has_pair_with, where);
        port.impedance = opt_int32_field(kv.second, "impedance", &port.has_impedance, where);
        port.role = opt_string_field(kv.second, "role", &port.has_role, where);
        port.bus = opt_string_field(kv.second, "bus", &port.has_bus, where);
        port.speed_hz = opt_int32_field(kv.second, "speed_hz", &port.has_speed_hz, where);
        port.level_v = opt_f64_field(kv.second, "level_v", &port.has_level_v, where);
        port.expect = opt_string_field(kv.second, "expect", &port.has_expect, where);
        sheet.port_types.push_back(std::move(port));
    }
    sheet.hints = parse_hints(root, "circuit");
    sheet.loads = parse_loads(root, "circuit");
    sheet.waivers = parse_waivers(root, "circuit");
    return sheet;
}

void validate_header(const uint8_t* data, std::size_t size) {
    if (size < kHeaderBytes) {
        throw std::runtime_error("circuit: file shorter than header");
    }
    if (read_u32(data, 0, size) != kCircuitMagic) {
        throw std::runtime_error("circuit: bad magic");
    }
    if (read_u32(data, 4, size) != kCircuitVersion) {
        throw std::runtime_error("circuit: unsupported version");
    }
    if (read_u32(data, 8, size) != kHeaderBytes) {
        throw std::runtime_error("circuit: header size mismatch");
    }
}

std::vector<fs::path> find_circuit_json(const fs::path& root) {
    if (!fs::exists(root) || !fs::is_directory(root)) {
        throw std::runtime_error("circuit: circuits dir missing: " + root.string());
    }
    std::vector<fs::path> paths;
    for (const auto& entry : fs::recursive_directory_iterator(root)) {
        if (entry.is_regular_file() && entry.path().filename() == "circuit.json") {
            paths.push_back(entry.path());
        }
    }
    std::sort(paths.begin(), paths.end());
    if (paths.empty()) {
        throw std::runtime_error("circuit: no circuit.json under " + root.string());
    }
    return paths;
}

}  // namespace

bool compile_circuit_catalog(const std::string& circuits_dir,
                             const std::string& catalog_path) {
    try {
        const std::vector<fs::path> paths = find_circuit_json(fs::path(circuits_dir));
        std::vector<CircuitSheetIr> sheets;
        std::set<std::string> names;
        sheets.reserve(paths.size());
        for (const fs::path& path : paths) {
            CircuitSheetIr sheet = parse_circuit_json(path);
            if (!names.insert(sheet.name).second) {
                throw std::runtime_error("circuit: duplicate sheet name '" + sheet.name + "'");
            }
            sheets.push_back(std::move(sheet));
        }
        uint32_t part_count = 0;
        uint32_t field_count = 0;
        uint32_t pinname_count = 0;
        uint32_t pinnum_count = 0;
        uint32_t net_count = 0;
        uint32_t netpin_count = 0;
        uint32_t nc_count = 0;
        uint32_t port_count = 0;
        uint32_t hint_count = 0;
        uint32_t load_count = 0;
        uint32_t waiver_count = 0;
        for (const CircuitSheetIr& sheet : sheets) {
            part_count += static_cast<uint32_t>(sheet.parts.size());
            net_count += static_cast<uint32_t>(sheet.nets.size());
            nc_count += static_cast<uint32_t>(sheet.nc.size());
            port_count += static_cast<uint32_t>(sheet.port_types.size());
            hint_count += static_cast<uint32_t>(sheet.hints.size());
            load_count += static_cast<uint32_t>(sheet.loads.size());
            waiver_count += static_cast<uint32_t>(sheet.waivers.size());
            for (const CircuitPartIr& part : sheet.parts) {
                field_count += static_cast<uint32_t>(part.fields.size());
                pinnum_count += static_cast<uint32_t>(part.pin_numbers.size());
                for (const CircuitPinNameIr& pin_name : part.pin_names) {
                    pinname_count += static_cast<uint32_t>(pin_name.numbers.size());
                }
            }
            for (const CircuitNetIr& net : sheet.nets) {
                netpin_count += static_cast<uint32_t>(net.pins.size());
            }
        }
        const uint32_t circuit_count = static_cast<uint32_t>(sheets.size());
        const uint32_t hash_slots = next_pow2(std::max(4u, circuit_count * 2));
        const uint32_t circuit_off = kHeaderBytes;
        const uint32_t part_off = circuit_off + circuit_count * kCircuitRecBytes;
        const uint32_t field_off = part_off + part_count * kPartRecBytes;
        const uint32_t pinname_off = field_off + field_count * kFieldRecBytes;
        const uint32_t pinnum_off = pinname_off + pinname_count * kPinNameRecBytes;
        const uint32_t net_off = pinnum_off + pinnum_count * kPinNumRecBytes;
        const uint32_t netpin_off = net_off + net_count * kNetRecBytes;
        const uint32_t nc_off = netpin_off + netpin_count * kNetPinRecBytes;
        const uint32_t port_off = nc_off + nc_count * kNcRecBytes;
        const uint32_t hint_off = port_off + port_count * kPortRecBytes;
        const uint32_t load_off = hint_off + hint_count * kHintRecBytes;
        const uint32_t waiver_off = load_off + load_count * kLoadRecBytes;
        const uint32_t hash_off = waiver_off + waiver_count * kWaiverRecBytes;
        const uint32_t pool_off = hash_off + hash_slots * kHashSlotBytes;
        std::vector<uint8_t> buf(pool_off, 0);
        StringPool pool;
        poke_u32(buf, 0, kCircuitMagic);
        poke_u32(buf, 4, kCircuitVersion);
        poke_u32(buf, 8, kHeaderBytes);
        poke_u32(buf, 12, circuit_count);
        poke_u32(buf, 16, part_count);
        poke_u32(buf, 20, field_count);
        poke_u32(buf, 24, pinname_count);
        poke_u32(buf, 28, pinnum_count);
        poke_u32(buf, 32, net_count);
        poke_u32(buf, 36, netpin_count);
        poke_u32(buf, 40, nc_count);
        poke_u32(buf, 44, port_count);
        poke_u32(buf, 48, hint_count);
        poke_u32(buf, 52, load_count);
        poke_u32(buf, 56, waiver_count);
        poke_u32(buf, 60, hash_slots);
        poke_u32(buf, 68, circuit_off);
        poke_u32(buf, 72, part_off);
        poke_u32(buf, 76, field_off);
        poke_u32(buf, 80, pinname_off);
        poke_u32(buf, 84, pinnum_off);
        poke_u32(buf, 88, net_off);
        poke_u32(buf, 92, netpin_off);
        poke_u32(buf, 96, nc_off);
        poke_u32(buf, 100, port_off);
        poke_u32(buf, 104, hint_off);
        poke_u32(buf, 108, load_off);
        poke_u32(buf, 112, waiver_off);
        poke_u32(buf, 116, hash_off);
        poke_u32(buf, 120, pool_off);
        poke_u32(buf, 124, 0);
        uint32_t part_i = 0;
        uint32_t field_i = 0;
        uint32_t pinname_i = 0;
        uint32_t pinnum_i = 0;
        uint32_t net_i = 0;
        uint32_t netpin_i = 0;
        uint32_t nc_i = 0;
        uint32_t port_i = 0;
        uint32_t hint_i = 0;
        uint32_t load_i = 0;
        uint32_t waiver_i = 0;
        std::vector<uint32_t> hash_name(hash_slots, kEmptySlot);
        std::vector<uint32_t> hash_index(hash_slots, kEmptySlot);
        for (uint32_t sheet_i = 0; sheet_i < circuit_count; ++sheet_i) {
            const CircuitSheetIr& sheet = sheets[sheet_i];
            const uint32_t rec = circuit_off + sheet_i * kCircuitRecBytes;
            poke_u32(buf, rec + 0, pool.intern(sheet.name));
            poke_u32(buf, rec + 4, pool.intern(sheet.title));
            poke_u32(buf, rec + 8, part_i);
            poke_u32(buf, rec + 12, static_cast<uint32_t>(sheet.parts.size()));
            poke_u32(buf, rec + 16, net_i);
            poke_u32(buf, rec + 20, static_cast<uint32_t>(sheet.nets.size()));
            poke_u32(buf, rec + 24, nc_i);
            poke_u32(buf, rec + 28, static_cast<uint32_t>(sheet.nc.size()));
            poke_u32(buf, rec + 32, port_i);
            poke_u32(buf, rec + 36, static_cast<uint32_t>(sheet.port_types.size()));
            poke_u32(buf, rec + 40, hint_i);
            poke_u32(buf, rec + 44, static_cast<uint32_t>(sheet.hints.size()));
            poke_u32(buf, rec + 48, load_i);
            poke_u32(buf, rec + 52, static_cast<uint32_t>(sheet.loads.size()));
            poke_u32(buf, rec + 56, waiver_i);
            poke_u32(buf, rec + 60, static_cast<uint32_t>(sheet.waivers.size()));
            for (const CircuitPartIr& part : sheet.parts) {
                const uint32_t prec = part_off + part_i * kPartRecBytes;
                poke_u32(buf, prec + 0, pool.intern(part.ref));
                poke_u32(buf, prec + 4, pool.intern(part.lib_id));
                poke_u32(buf, prec + 8, pool.intern(part.value));
                poke_u32(buf, prec + 12, pool.intern(part.footprint));
                poke_u32(buf, prec + 16, field_i);
                poke_u32(buf, prec + 20, static_cast<uint32_t>(part.fields.size()));
                uint32_t name_rows = 0;
                for (const CircuitPinNameIr& pin_name : part.pin_names) {
                    name_rows += static_cast<uint32_t>(pin_name.numbers.size());
                }
                poke_u32(buf, prec + 24, pinname_i);
                poke_u32(buf, prec + 28, name_rows);
                poke_u32(buf, prec + 32, pinnum_i);
                poke_u32(buf, prec + 36, static_cast<uint32_t>(part.pin_numbers.size()));
                for (const CircuitFieldIr& field : part.fields) {
                    const uint32_t foff = field_off + field_i * kFieldRecBytes;
                    poke_u32(buf, foff + 0, pool.intern(field.key));
                    poke_u32(buf, foff + 4, pool.intern(field.value));
                    ++field_i;
                }
                for (const CircuitPinNameIr& pin_name : part.pin_names) {
                    for (const std::string& number : pin_name.numbers) {
                        const uint32_t noff = pinname_off + pinname_i * kPinNameRecBytes;
                        poke_u32(buf, noff + 0, pool.intern(pin_name.name));
                        poke_u32(buf, noff + 4, pool.intern(number));
                        ++pinname_i;
                    }
                }
                for (const std::string& number : part.pin_numbers) {
                    poke_u32(buf, pinnum_off + pinnum_i * kPinNumRecBytes,
                             pool.intern(number));
                    ++pinnum_i;
                }
                ++part_i;
            }
            for (const CircuitNetIr& net : sheet.nets) {
                const uint32_t noff = net_off + net_i * kNetRecBytes;
                poke_u32(buf, noff + 0, pool.intern(net.name));
                poke_u32(buf, noff + 4, pool.intern(net.net_class));
                poke_u32(buf, noff + 8, netpin_i);
                poke_u32(buf, noff + 12, static_cast<uint32_t>(net.pins.size()));
                for (const CircuitPinRefIr& pin : net.pins) {
                    const uint32_t poff = netpin_off + netpin_i * kNetPinRecBytes;
                    poke_u32(buf, poff + 0, pool.intern(pin.ref));
                    poke_u32(buf, poff + 4, pool.intern(pin.pin));
                    ++netpin_i;
                }
                ++net_i;
            }
            for (const CircuitPinRefIr& pin : sheet.nc) {
                const uint32_t noff = nc_off + nc_i * kNcRecBytes;
                poke_u32(buf, noff + 0, pool.intern(pin.ref));
                poke_u32(buf, noff + 4, pool.intern(pin.pin));
                ++nc_i;
            }
            for (const CircuitPortIr& port : sheet.port_types) {
                const uint32_t poff = port_off + port_i * kPortRecBytes;
                uint32_t flags = 0;
                if (port.has_pair_with) {
                    flags |= 1u;
                }
                if (port.has_impedance) {
                    flags |= 2u;
                }
                if (port.has_role) {
                    flags |= 4u;
                }
                if (port.has_bus) {
                    flags |= 8u;
                }
                if (port.has_speed_hz) {
                    flags |= 16u;
                }
                if (port.has_level_v) {
                    flags |= 32u;
                }
                if (port.has_expect) {
                    flags |= 64u;
                }
                poke_u32(buf, poff + 0, pool.intern(port.net));
                poke_u32(buf, poff + 4, pool.intern(port.kind));
                poke_u32(buf, poff + 8, pool.intern(port.has_pair_with ? port.pair_with : ""));
                poke_u32(buf, poff + 12, pool.intern(port.has_role ? port.role : ""));
                poke_u32(buf, poff + 16, pool.intern(port.has_bus ? port.bus : ""));
                poke_u32(buf, poff + 20, pool.intern(port.has_expect ? port.expect : ""));
                poke_u32(buf, poff + 24, flags);
                poke_u32(buf, poff + 28, static_cast<uint32_t>(port.impedance));
                poke_u32(buf, poff + 32, static_cast<uint32_t>(port.speed_hz));
                poke_f64(buf, poff + 36, port.level_v);
                poke_u32(buf, poff + 44, 0);
                ++port_i;
            }
            for (const CircuitHintIr& hint : sheet.hints) {
                const uint32_t hoff = hint_off + hint_i * kHintRecBytes;
                poke_u32(buf, hoff + 0, pool.intern(hint.net));
                poke_u32(buf, hoff + 4, pool.intern(hint.style));
                ++hint_i;
            }
            for (const CircuitLoadIr& load : sheet.loads) {
                const uint32_t loff = load_off + load_i * kLoadRecBytes;
                poke_u32(buf, loff + 0, pool.intern(load.rail));
                poke_u32(buf, loff + 4, pool.intern(load.note));
                poke_f64(buf, loff + 8, load.amps);
                ++load_i;
            }
            for (const CircuitWaiverIr& waiver : sheet.waivers) {
                const uint32_t woff = waiver_off + waiver_i * kWaiverRecBytes;
                poke_u32(buf, woff + 0, pool.intern(waiver.kind));
                poke_u32(buf, woff + 4, pool.intern(waiver.key));
                poke_u32(buf, woff + 8, pool.intern(waiver.reason));
                ++waiver_i;
            }
            uint32_t slot = fnv1a_32(sheet.name) & (hash_slots - 1);
            bool inserted = false;
            for (uint32_t probe = 0; probe < hash_slots; ++probe) {
                if (hash_name[slot] == kEmptySlot) {
                    hash_name[slot] = pool.intern(sheet.name);
                    hash_index[slot] = sheet_i;
                    inserted = true;
                    break;
                }
                slot = (slot + 1) & (hash_slots - 1);
            }
            if (!inserted) {
                throw std::runtime_error("circuit: hash insert failed for " + sheet.name);
            }
        }
        for (uint32_t slot = 0; slot < hash_slots; ++slot) {
            poke_u32(buf, hash_off + slot * kHashSlotBytes + 0, hash_name[slot]);
            poke_u32(buf, hash_off + slot * kHashSlotBytes + 4, hash_index[slot]);
        }
        poke_u32(buf, 64, static_cast<uint32_t>(pool.bytes.size()));
        buf.insert(buf.end(), pool.bytes.begin(), pool.bytes.end());
        const fs::path out_path(catalog_path);
        if (!out_path.parent_path().empty()) {
            fs::create_directories(out_path.parent_path());
        }
        std::ofstream out(out_path, std::ios::binary | std::ios::trunc);
        if (!out) {
            throw std::runtime_error("circuit: cannot write " + catalog_path);
        }
        out.write(reinterpret_cast<const char*>(buf.data()),
                  static_cast<std::streamsize>(buf.size()));
        if (!out) {
            throw std::runtime_error("circuit: write failed " + catalog_path);
        }
        return true;
    } catch (const std::exception& exc) {
        throw std::runtime_error(std::string("circuit compile failed: ") + exc.what());
    }
}

bool open_circuit_catalog(const std::string& catalog_path) {
    try {
        if (g_circuits.map_base != nullptr && g_circuits.file_path == catalog_path) {
            return true;
        }
        if (g_circuits.map_base != nullptr) {
            g_circuits.release();
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
            throw std::runtime_error("empty circuit catalog file");
        }
        void* mapped = mmap(nullptr, static_cast<std::size_t>(st.st_size), PROT_READ,
                            MAP_PRIVATE, fd, 0);
        if (mapped == MAP_FAILED) {
            close(fd);
            throw std::runtime_error(std::string("mmap failed: ") + std::strerror(errno));
        }
        g_circuits.file_desc = fd;
        g_circuits.map_base = static_cast<uint8_t*>(mapped);
        g_circuits.map_size = static_cast<std::size_t>(st.st_size);
        g_circuits.file_path = catalog_path;
        validate_header(g_circuits.map_base, g_circuits.map_size);
        return true;
    } catch (const std::exception& exc) {
        try {
            g_circuits.release();
        } catch (...) {
            std::abort();
        }
        throw std::runtime_error(std::string("circuit open failed: ") + exc.what());
    }
}

bool close_circuit_catalog() {
    try {
        return g_circuits.release();
    } catch (const std::exception& exc) {
        throw std::runtime_error(std::string("circuit close failed: ") + exc.what());
    }
}

CircuitSheetIr lookup_circuit_catalog(const std::string& name) {
    try {
        if (g_circuits.map_base == nullptr) {
            throw std::runtime_error("circuit catalog is not open");
        }
        if (name.empty()) {
            throw std::runtime_error("circuit name must not be empty");
        }
        const uint8_t* data = g_circuits.map_base;
        const std::size_t size = g_circuits.map_size;
        const uint32_t circuit_count = read_u32(data, 12, size);
        const uint32_t hash_slots = read_u32(data, 60, size);
        const uint32_t string_bytes = read_u32(data, 64, size);
        const uint32_t circuit_off = read_u32(data, 68, size);
        const uint32_t part_off = read_u32(data, 72, size);
        const uint32_t field_off = read_u32(data, 76, size);
        const uint32_t pinname_off = read_u32(data, 80, size);
        const uint32_t pinnum_off = read_u32(data, 84, size);
        const uint32_t net_off = read_u32(data, 88, size);
        const uint32_t netpin_off = read_u32(data, 92, size);
        const uint32_t nc_off = read_u32(data, 96, size);
        const uint32_t port_off = read_u32(data, 100, size);
        const uint32_t hint_off = read_u32(data, 104, size);
        const uint32_t load_off = read_u32(data, 108, size);
        const uint32_t waiver_off = read_u32(data, 112, size);
        const uint32_t hash_off = read_u32(data, 116, size);
        const uint32_t pool_off = read_u32(data, 120, size);
        auto interned = [&](uint32_t off) {
            return std::string(pool_string(data, pool_off, string_bytes, off));
        };
        uint32_t slot = fnv1a_32(name) & (hash_slots - 1);
        uint32_t sheet_index = kEmptySlot;
        for (uint32_t probe = 0; probe < hash_slots; ++probe) {
            const uint32_t name_off = read_u32(
                data, hash_off + slot * kHashSlotBytes + 0, size);
            if (name_off == kEmptySlot) {
                break;
            }
            if (name == pool_string(data, pool_off, string_bytes, name_off)) {
                sheet_index = read_u32(data, hash_off + slot * kHashSlotBytes + 4, size);
                break;
            }
            slot = (slot + 1) & (hash_slots - 1);
        }
        if (sheet_index == kEmptySlot || sheet_index >= circuit_count) {
            throw std::runtime_error("unknown circuit '" + name + "'");
        }
        const uint32_t rec = circuit_off + sheet_index * kCircuitRecBytes;
        CircuitSheetIr sheet;
        sheet.schema = kCircuitSchema;
        sheet.name = interned(read_u32(data, rec + 0, size));
        sheet.title = interned(read_u32(data, rec + 4, size));
        const uint32_t part_index = read_u32(data, rec + 8, size);
        const uint32_t part_n = read_u32(data, rec + 12, size);
        const uint32_t net_index = read_u32(data, rec + 16, size);
        const uint32_t net_n = read_u32(data, rec + 20, size);
        const uint32_t nc_index = read_u32(data, rec + 24, size);
        const uint32_t nc_n = read_u32(data, rec + 28, size);
        const uint32_t port_index = read_u32(data, rec + 32, size);
        const uint32_t port_n = read_u32(data, rec + 36, size);
        const uint32_t hint_index = read_u32(data, rec + 40, size);
        const uint32_t hint_n = read_u32(data, rec + 44, size);
        const uint32_t load_index = read_u32(data, rec + 48, size);
        const uint32_t load_n = read_u32(data, rec + 52, size);
        const uint32_t waiver_index = read_u32(data, rec + 56, size);
        const uint32_t waiver_n = read_u32(data, rec + 60, size);
        sheet.parts.reserve(part_n);
        for (uint32_t i = 0; i < part_n; ++i) {
            const uint32_t prec = part_off + (part_index + i) * kPartRecBytes;
            CircuitPartIr part;
            part.ref = interned(read_u32(data, prec + 0, size));
            part.lib_id = interned(read_u32(data, prec + 4, size));
            part.value = interned(read_u32(data, prec + 8, size));
            part.footprint = interned(read_u32(data, prec + 12, size));
            const uint32_t field_index = read_u32(data, prec + 16, size);
            const uint32_t field_n = read_u32(data, prec + 20, size);
            const uint32_t pinname_index = read_u32(data, prec + 24, size);
            const uint32_t pinname_n = read_u32(data, prec + 28, size);
            const uint32_t pinnum_index = read_u32(data, prec + 32, size);
            const uint32_t pinnum_n = read_u32(data, prec + 36, size);
            for (uint32_t fi = 0; fi < field_n; ++fi) {
                const uint32_t foff = field_off + (field_index + fi) * kFieldRecBytes;
                CircuitFieldIr field;
                field.key = interned(read_u32(data, foff + 0, size));
                field.value = interned(read_u32(data, foff + 4, size));
                part.fields.push_back(std::move(field));
            }
            for (uint32_t ni = 0; ni < pinname_n; ++ni) {
                const uint32_t noff = pinname_off + (pinname_index + ni) * kPinNameRecBytes;
                const std::string pname = interned(read_u32(data, noff + 0, size));
                const std::string pnum = interned(read_u32(data, noff + 4, size));
                if (part.pin_names.empty() || part.pin_names.back().name != pname) {
                    CircuitPinNameIr rec;
                    rec.name = pname;
                    rec.numbers.push_back(pnum);
                    part.pin_names.push_back(std::move(rec));
                } else {
                    part.pin_names.back().numbers.push_back(pnum);
                }
            }
            for (uint32_t ni = 0; ni < pinnum_n; ++ni) {
                part.pin_numbers.push_back(interned(read_u32(
                    data, pinnum_off + (pinnum_index + ni) * kPinNumRecBytes, size)));
            }
            sheet.parts.push_back(std::move(part));
        }
        sheet.nets.reserve(net_n);
        for (uint32_t i = 0; i < net_n; ++i) {
            const uint32_t noff = net_off + (net_index + i) * kNetRecBytes;
            CircuitNetIr net;
            net.name = interned(read_u32(data, noff + 0, size));
            net.net_class = interned(read_u32(data, noff + 4, size));
            const uint32_t pin_index = read_u32(data, noff + 8, size);
            const uint32_t pin_n = read_u32(data, noff + 12, size);
            for (uint32_t pi = 0; pi < pin_n; ++pi) {
                const uint32_t poff = netpin_off + (pin_index + pi) * kNetPinRecBytes;
                CircuitPinRefIr pin;
                pin.ref = interned(read_u32(data, poff + 0, size));
                pin.pin = interned(read_u32(data, poff + 4, size));
                net.pins.push_back(std::move(pin));
            }
            sheet.nets.push_back(std::move(net));
        }
        sheet.nc.reserve(nc_n);
        for (uint32_t i = 0; i < nc_n; ++i) {
            const uint32_t noff = nc_off + (nc_index + i) * kNcRecBytes;
            CircuitPinRefIr pin;
            pin.ref = interned(read_u32(data, noff + 0, size));
            pin.pin = interned(read_u32(data, noff + 4, size));
            sheet.nc.push_back(std::move(pin));
        }
        sheet.port_types.reserve(port_n);
        for (uint32_t i = 0; i < port_n; ++i) {
            const uint32_t poff = port_off + (port_index + i) * kPortRecBytes;
            CircuitPortIr port;
            port.net = interned(read_u32(data, poff + 0, size));
            port.kind = interned(read_u32(data, poff + 4, size));
            port.pair_with = interned(read_u32(data, poff + 8, size));
            port.role = interned(read_u32(data, poff + 12, size));
            port.bus = interned(read_u32(data, poff + 16, size));
            port.expect = interned(read_u32(data, poff + 20, size));
            const uint32_t flags = read_u32(data, poff + 24, size);
            port.has_pair_with = (flags & 1u) != 0;
            port.has_impedance = (flags & 2u) != 0;
            port.has_role = (flags & 4u) != 0;
            port.has_bus = (flags & 8u) != 0;
            port.has_speed_hz = (flags & 16u) != 0;
            port.has_level_v = (flags & 32u) != 0;
            port.has_expect = (flags & 64u) != 0;
            port.impedance = static_cast<int32_t>(read_u32(data, poff + 28, size));
            port.speed_hz = static_cast<int32_t>(read_u32(data, poff + 32, size));
            port.level_v = read_f64(data, poff + 36, size);
            sheet.port_types.push_back(std::move(port));
        }
        sheet.hints.reserve(hint_n);
        for (uint32_t i = 0; i < hint_n; ++i) {
            const uint32_t hoff = hint_off + (hint_index + i) * kHintRecBytes;
            CircuitHintIr hint;
            hint.net = interned(read_u32(data, hoff + 0, size));
            hint.style = interned(read_u32(data, hoff + 4, size));
            sheet.hints.push_back(std::move(hint));
        }
        sheet.loads.reserve(load_n);
        for (uint32_t i = 0; i < load_n; ++i) {
            const uint32_t loff = load_off + (load_index + i) * kLoadRecBytes;
            CircuitLoadIr load;
            load.rail = interned(read_u32(data, loff + 0, size));
            load.note = interned(read_u32(data, loff + 4, size));
            load.amps = read_f64(data, loff + 8, size);
            sheet.loads.push_back(std::move(load));
        }
        sheet.waivers.reserve(waiver_n);
        for (uint32_t i = 0; i < waiver_n; ++i) {
            const uint32_t woff = waiver_off + (waiver_index + i) * kWaiverRecBytes;
            CircuitWaiverIr waiver;
            waiver.kind = interned(read_u32(data, woff + 0, size));
            waiver.key = interned(read_u32(data, woff + 4, size));
            waiver.reason = interned(read_u32(data, woff + 8, size));
            sheet.waivers.push_back(std::move(waiver));
        }
        return sheet;
    } catch (const std::exception& exc) {
        throw std::runtime_error(std::string("circuit lookup failed: ") + exc.what());
    }
}

std::size_t circuit_catalog_count() {
    try {
        if (g_circuits.map_base == nullptr) {
            throw std::runtime_error("circuit catalog is not open");
        }
        return read_u32(g_circuits.map_base, 12, g_circuits.map_size);
    } catch (const std::exception& exc) {
        throw std::runtime_error(std::string("circuit count failed: ") + exc.what());
    }
}

}  // namespace schgen
