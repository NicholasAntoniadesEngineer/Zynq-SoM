#pragma once

#include <filesystem>
#include <string>
#include <unordered_map>
#include <vector>

namespace schgen {
// Per-generator cache. Normal file edits invalidate by size/mtime; clear after
// tools that deliberately preserve both. Never caches a failed read.
class FootprintLibrary {
public:
    const std::vector<std::string>& pad_names(const std::string& path);
    void clear() { entries_.clear(); }
private:
    struct Entry {
        std::filesystem::file_time_type modified;
        std::uintmax_t size;
        std::vector<std::string> pads;
    };
    std::unordered_map<std::string, Entry> entries_;
};
}
