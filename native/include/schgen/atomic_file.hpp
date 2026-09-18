#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace schgen {
// Publish a complete replacement without modifying existing mmap readers.
// Failure before rename leaves the destination unchanged.
void write_atomic_file(const std::string& path, const std::vector<uint8_t>& data);
}
