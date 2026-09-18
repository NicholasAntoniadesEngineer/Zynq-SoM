#include "schgen/atomic_file.hpp"

#include <algorithm>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <stdexcept>
#include <unistd.h>

namespace schgen {
void write_atomic_file(const std::string& path, const std::vector<uint8_t>& data) {
    const std::filesystem::path target(path);
    if (!target.parent_path().empty()) {
        std::filesystem::create_directories(target.parent_path());
    }
    std::string pattern = path + ".tmp.XXXXXX";
    int fd = ::mkstemp(pattern.data());
    if (fd < 0) {
        throw std::runtime_error("cannot create temporary file for " + path + ": "
                                 + std::strerror(errno));
    }
    try {
        std::size_t offset = 0;
        while (offset < data.size()) {
            const auto count = ::write(fd, data.data() + offset,
                                      std::min(data.size() - offset, std::size_t{1 << 20}));
            if (count < 0 && errno == EINTR) continue;
            if (count <= 0) throw std::runtime_error("write failed: " + path);
            offset += static_cast<std::size_t>(count);
        }
        if (::fsync(fd) != 0) throw std::runtime_error("flush failed: " + path);
        const int close_result = ::close(fd);
        fd = -1;
        if (close_result != 0) throw std::runtime_error("close failed: " + path);
        if (::rename(pattern.c_str(), path.c_str()) != 0) {
            throw std::runtime_error("publish failed: " + path + ": "
                                     + std::strerror(errno));
        }
    } catch (...) {
        if (fd >= 0) ::close(fd);
        ::unlink(pattern.c_str());
        throw;
    }
}
}
