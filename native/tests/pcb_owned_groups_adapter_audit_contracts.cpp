#include "schgen/native_audit_state.hpp"
#include <iostream>

int main(int argc, char** argv) {
    using namespace schgen;
    try {
        if (argc != 2) throw std::runtime_error("usage: adapter-audit SOURCE-ROOT");
        CppAuditOptions options;
        options.workers = 1;
        options.timeout = std::chrono::milliseconds{120000};
        options.flags = {"-I" + (std::filesystem::path(argv[1]) / "native/include").string(),
            "-I" + (std::filesystem::path(argv[1]) / "native/src").string(), "-ffp-contract=off"};
        const auto scan = scan_cpp_audit_sources(argv[1],
            {{"native/src/pcb_owned_groups_adapter.cpp"}}, options);
        if (scan.n_files != 1 || !scan.quantization.empty() || !scan.constants.empty())
            throw std::runtime_error("adapter introduced unregistered precision or policy storage");
        std::cout << "PASS compiler adapter census: one production source, zero raw quantization/policy storage findings\n";
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
