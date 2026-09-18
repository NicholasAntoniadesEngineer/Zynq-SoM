#include "schgen/footprint_library.hpp"
#include "schgen/pcb_scan.hpp"

#include <fstream>
#include <iterator>
#include <stdexcept>

namespace schgen {
const std::vector<std::string>& FootprintLibrary::pad_names(const std::string& path) {
    namespace fs = std::filesystem;
    const auto modified = fs::last_write_time(path);
    const auto size = fs::file_size(path);
    auto found = entries_.find(path);
    if (found != entries_.end() && found->second.modified == modified
        && found->second.size == size) return found->second.pads;
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("cannot read footprint: " + path);
    const std::string text{std::istreambuf_iterator<char>(input),
                           std::istreambuf_iterator<char>()};
    if (input.bad()) throw std::runtime_error("footprint read failed: " + path);
    auto pads = pad_names_from_text(text);
    if (fs::last_write_time(path) != modified || fs::file_size(path) != size) {
        throw std::runtime_error("footprint changed during read: " + path);
    }
    auto& entry = entries_[path];
    entry = Entry{modified, size, std::move(pads)};
    return entry.pads;
}
}
