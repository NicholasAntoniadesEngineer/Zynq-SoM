#include "schgen/native_audit_state.hpp"
#include "schgen/atomic_file.hpp"
#include <iostream>
#include <unistd.h>

namespace {
using namespace schgen;
namespace fs = std::filesystem;
std::size_t checks = 0;
void require(bool ok, const std::string& why) {
    ++checks;
    if (!ok) throw std::runtime_error(why);
}
struct Scratch {
    fs::path path;
    Scratch() {
        auto name = (fs::temp_directory_path() / "schgen-enum-auditor-XXXXXX").string();
        if (!::mkdtemp(name.data())) throw std::runtime_error("mkdtemp");
        path = name;
    }
    ~Scratch() { std::error_code e; fs::remove_all(path, e); }
};
void contracts() {
    Scratch tmp;
    NativeLedger empty;
    NativeQuantizations none;
    const auto scan = [&](const std::string& source) {
        const auto text = "namespace policy { " + source + " double marker(){return 0;} }\n";
        write_atomic_file((tmp.path / "enum.cpp").string(), {text.begin(), text.end()});
        return scan_cpp_audit_sources(tmp.path, {{"enum.cpp"}});
    };
    // Run physical-value negatives BEFORE the ordinal-state correction. A broad
    // exemption for enums, or only counting explicitly initialized members,
    // fails these independent checks.
    for (const auto& source : {
            "enum class PhysicalPitch { Sparse=8, Dense=4 };",
            "enum class PhysicalPitch { Sparse=8, Next };",
            "enum class PhysicalPitch { Zero=0, Next };",
            "enum class PhysicalPitch : unsigned { Top=1u<<0, Bottom=1u<<1 };",
            "enum { Clearance=4, Width=8 };"}) {
        const auto census = scan(source);
        require(census.constants.size() == 2, "explicit numeric enum and numeric successors remain policy");
        require(!check_native_audits(census, empty, none).ok, "uncovered physical enum values reject");
    }
    auto census = scan("enum class PhysicalPitch { First, Second, Millimetres=4, Successor };");
    require(census.constants.size() == 4, "a numeric seed makes the entire enum conservative policy");
    census = scan("struct Bounds { enum class PhysicalPitch { Clearance=4, Successor }; };");
    require(check_native_audits(census, empty, none).buried.size() == 2,
            "class-scoped physical values remain buried without exact coverage");
    // Pure unseeded ordinal labels are language identity, not numerical policy.
    for (const auto& source : {
            "enum class Owner { Zone, SomJack, Decoupling, MountingHole };",
            "struct Part { enum class Owner { Zone, SomJack, Decoupling, MountingHole }; };",
            "enum class State : unsigned { Idle, Ready, Finished };",
            "enum { IDLE, READY, FINISHED };"}) {
        const auto ordinal = scan(source);
        require(ordinal.constants.empty(), "unseeded category ordinals are identity state");
        require(check_native_audits(ordinal, empty, none).ok, "ordinary category labels pass without invented declarations");
    }
    census = scan("double f(){enum class State {Idle,Busy};constexpr double gap=static_cast<int>(State::Busy)+4.2;return gap;}");
    require(census.constants.size() == 1 && census.constants.front().symbol == "enum.cpp::policy::f::gap",
            "using an ordinal in derived engineering arithmetic does not hide that constant");
    require(!check_native_audits(census, empty, none).buried.empty(),
            "derived hidden engineering value still rejects");
}
} // namespace

int main() {
    try {
        contracts();
        std::cout << checks << " C++ enum storage contracts passed\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "C++ enum storage FAILED after " << checks << " checks: " << e.what() << '\n';
        return 1;
    }
}
