#pragma once

#include "schgen/json.hpp"
#include "schgen/part_facts.hpp"

#include <cstdint>
#include <filesystem>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace schgen {

struct AssemblyPart {
    bool in_library = false, buyable = false, preferred = false, audit_flag = false;
    std::string part_class, assembly_type, assembly_mode, pcba_type, jlc_package, mpn, msl, route, read_utc;
    std::int64_t jlc_stock = 0;
    std::optional<std::int64_t> lcsc_stock;
    double special_fee = 0.0;
    std::vector<std::string> source_urls;
};

struct AssemblyNeed {
    std::string item;
    std::vector<std::string> satisfied_by;
};

struct AssemblyFacts {
    std::set<PartClass> unplaced_classes;
    std::map<PartClass, AssemblyNeed> needs;
    std::map<std::string, AssemblyPart> parts;
    std::string file;
};

inline constexpr const char* assembly_facts_name = "assembly_facts.json";

AssemblyFacts parse_assembly_facts(const JsonNode& document, const std::string& file);
AssemblyFacts load_assembly_facts(const std::filesystem::path& file);
AssemblyFacts load_assembly_facts_in(const std::filesystem::path& parts_directory);
std::string assembly_facts_text(const AssemblyFacts& facts);
bool assembly_class_unplaced(const AssemblyFacts& facts, PartClass part_class);

}
