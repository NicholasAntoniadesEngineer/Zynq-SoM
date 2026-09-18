#include "schgen/atomic_file.hpp"
#include "schgen/catalog.hpp"
#include "schgen/circuit.hpp"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <vector>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

namespace fs = std::filesystem;
void require(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}
std::vector<uint8_t> read(const fs::path& path) {
    std::ifstream in(path, std::ios::binary);
    require(bool(in), "cannot read fixture");
    return {std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};
}
struct TempDir {
    fs::path path;
    TempDir() {
        auto pattern = (fs::temp_directory_path() / "schgen-catalog-XXXXXX").string();
        require(::mkdtemp(pattern.data()) != nullptr, "mkdtemp failed");
        path = pattern;
    }
    ~TempDir() { std::error_code ec; fs::remove_all(path, ec); }
};
int main(int argc, char** argv) {
    try {
        require(argc == 2, "expected repository path");
        TempDir tmp;
        const auto output = (tmp.path / "mapped.bin").string();
        schgen::write_atomic_file(output, {1, 2, 3, 4});
        const int fd = ::open(output.c_str(), O_RDONLY);
        require(fd >= 0, "open failed");
        void* mapping = ::mmap(nullptr, 4, PROT_READ, MAP_PRIVATE, fd, 0);
        ::close(fd);
        require(mapping != MAP_FAILED, "mmap failed");
        schgen::write_atomic_file(output, {9});
        const auto* bytes = static_cast<const uint8_t*>(mapping);
        const bool unchanged = bytes[0] == 1 && bytes[3] == 4;
        ::munmap(mapping, 4);
        require(unchanged, "replacement modified existing mapped reader");
        require(read(output) == std::vector<uint8_t>{9}, "new reader missed replacement");

        const auto blocked = tmp.path / "directory.bin";
        fs::create_directory(blocked);
        schgen::write_atomic_file((blocked / "keep").string(), {7});
        bool failed = false;
        try { schgen::write_atomic_file(blocked.string(), {8}); }
        catch (const std::runtime_error&) { failed = true; }
        require(failed && read(blocked / "keep") == std::vector<uint8_t>{7},
                "failed publication damaged destination");
        for (const auto& entry : fs::directory_iterator(tmp.path)) {
            require(entry.path().filename().string().find(".tmp.") == std::string::npos,
                    "failed publication leaked temporary file");
        }

        const fs::path repo(argv[1]);
        const auto parts = (tmp.path / "parts.bin").string();
        schgen::compile_part_catalog((repo / "parts").string(), parts);
        const auto part_bytes = read(parts);
        schgen::open_part_catalog(parts);
        const auto part_count = schgen::part_catalog_count();
        schgen::compile_part_catalog((repo / "parts").string(), parts);
        require(part_count > 0 && schgen::part_catalog_count() == part_count,
                "part reader changed during rebuild");
        require(read(parts) == part_bytes, "part rebuild is not deterministic");
        schgen::close_part_catalog();

        const auto circuits = (tmp.path / "circuits.bin").string();
        const auto source = (repo / "carrier/subsystems").string();
        schgen::compile_circuit_catalog(source, circuits);
        const auto circuit_bytes = read(circuits);
        schgen::open_circuit_catalog(circuits);
        const auto circuit_count = schgen::circuit_catalog_count();
        schgen::compile_circuit_catalog(source, circuits);
        require(circuit_count > 0 && schgen::circuit_catalog_count() == circuit_count,
                "circuit reader changed during rebuild");
        require(read(circuits) == circuit_bytes, "circuit rebuild is not deterministic");
        schgen::close_circuit_catalog();
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << exc.what() << '\n';
        return 1;
    }
}
