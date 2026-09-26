#include "schgen/process.hpp"
#include "schgen/subsystem_scaffold.hpp"

#include <fstream>
#include <exception>
#include <iostream>
#include <iterator>
#include <unistd.h>

namespace {
namespace fs = std::filesystem;
using namespace schgen;
std::size_t assertions = 0;
void require(bool condition, const std::string& message) {
    ++assertions;
    if (!condition) throw std::runtime_error(message);
}
struct Scratch {
    fs::path path;
    Scratch() {
        auto pattern = (fs::temp_directory_path() / "schgen-scaffold-build-XXXXXX").string();
        const auto created = ::mkdtemp(pattern.data());
        require(created != nullptr, "allocate isolated build"); path = created;
    }
    ~Scratch() {
        if (std::uncaught_exceptions()) {
            std::cerr << "Failed scaffold build evidence retained: " << path << '\n';
            return;
        }
        std::error_code ignored; fs::remove_all(path, ignored);
    }
};
std::string read(const fs::path& path) {
    std::ifstream in(path, std::ios::binary);
    require(bool(in), "read " + path.string());
    return {std::istreambuf_iterator<char>(in), {}};
}
void write(const fs::path& path, const std::string& text) {
    std::ofstream out(path, std::ios::binary); out << text; out.close();
    require(bool(out), "write private build input " + path.string());
}
std::string replaced(std::string text, const std::string& from, const std::string& to) {
    const auto at = text.find(from);
    require(at != std::string::npos, "private integration patch target missing: " + from);
    text.replace(at, from.size(), to); return text;
}
std::string rename_widget(std::string text) {
    for (std::size_t at = 0; (at = text.find("widget", at)) != std::string::npos; at += 5)
        text.replace(at, 6, "class");
    return text;
}
std::string quoted(const fs::path& path) {
    const auto text = path.string();
    require(text.find_first_of("\";\n\r") == std::string::npos, "unsupported private CMake path");
    return "\"" + text + "\"";
}
ProcessResult run(const std::vector<std::string>& argv, bool success, const std::string& expected = {}) {
    const auto result = run_process(argv, std::chrono::milliseconds(60000));
    const auto output = result.stdout_text + result.stderr_text;
    require((result.exit_code == 0) == success, "unexpected process result for " + argv.front() + "\n" + output);
    if (!expected.empty()) require(output.find(expected) != std::string::npos, "missing diagnostic " + expected + "\n" + output);
    return result;
}
void exercise(const fs::path& repo, const fs::path& archive, const fs::path& cmake) {
    Scratch scratch;
    const bool had_widget = fs::exists(repo / "subsystems/widget");
    const bool had_class = fs::exists(repo / "subsystems/class");
    // Including spaces makes path quoting part of the actual compiler proof.
    const auto src = scratch.path / "source with spaces";
    const auto build = scratch.path / "build with spaces";
    const auto library = scratch.path / "library with spaces";
    fs::create_directory(src); fs::create_directory(library);
    const auto widget = scaffold_subsystem(library, "widget");
    const auto keyword = scaffold_subsystem(library, "class");
    fs::copy_file(archive, scratch.path / "core.a"); // immutable private archive for the entire proof
    const auto integration = read(repo / "native/tests/subsystem_scaffold_INTEGRATION.md");
    const auto marker = integration.find("<!-- BEGIN TESTED CMAKE MODULE -->");
    require(marker != std::string::npos, "CMake integration block missing");
    const auto start = integration.find("```cmake\n", marker) + 9;
    const auto end = integration.find("\n```", start);
    require(end != std::string::npos && end > start, "CMake integration block malformed");
    write(src / "SubsystemPackages.cmake", integration.substr(start, end - start) + "\n");
    auto registry = read(repo / "native/src/subsystem_authoring.cpp");
    if (registry.find("append_configured_subsystem_definitions") == std::string::npos) {
        registry = replaced(registry, "#include \"schgen/subsystem_authoring.hpp\"",
            "#include \"schgen/subsystem_authoring.hpp\"\n#include \"schgen/subsystem_registration.hpp\"");
        registry = replaced(registry, "definitions = {", "definitions = append_configured_subsystem_definitions({");
        registry = replaced(registry, "    };\n    return definitions;", "    });\n    return definitions;");
    }
    write(src / "subsystem_authoring.cpp", registry);
    std::string project = "cmake_minimum_required(VERSION 3.18)\nproject(scaffold_proof LANGUAGES CXX)\n"
        "set(CMAKE_CXX_STANDARD 17)\nset(CMAKE_CXX_STANDARD_REQUIRED ON)\nset(CMAKE_CXX_EXTENSIONS OFF)\n"
        "include(CTest)\nadd_library(schgen_core STATIC subsystem_authoring.cpp\n";
    for (const auto* name : {"subsystem_registration.cpp", "subsystem_package_checks.cpp"})
        project += quoted(repo / "native/src" / name) + "\n";
    project += ")\ntarget_include_directories(schgen_core PUBLIC " + quoted(repo / "native/include") + ")\n"
        "target_compile_options(schgen_core PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)\n"
        "target_link_libraries(schgen_core PUBLIC " + quoted(scratch.path / "core.a") + " xml2 pthread)\n"
        "include(SubsystemPackages.cmake)\nschgen_configure_subsystem_packages(schgen_core " + quoted(repo) + ")\n";
    write(src / "CMakeLists.txt", project);
    auto configure = [&](const std::string& packages, bool success, const std::string& message = {}) {
        std::vector<std::string> args{cmake.string(), "-S", src.string(), "-B", build.string(),
            "-DBUILD_TESTING=ON", "-DSCHGEN_SUBSYSTEM_LIBRARY_ROOT=" + library.string(),
            "-DSCHGEN_SUBSYSTEM_PACKAGES=" + packages};
#ifdef __APPLE__
        // The archive deployment target comes from its owning build, read-only.
        const auto cache = read(repo / "native/build/CMakeCache.txt");
        const auto target_key = std::string("CMAKE_OSX_DEPLOYMENT_TARGET:STRING=");
        const auto at = cache.find(target_key);
        if (at != std::string::npos) {
            const auto value = at + target_key.size();
            args.push_back("-DCMAKE_OSX_DEPLOYMENT_TARGET=" + cache.substr(value, cache.find('\n', value) - value));
        }
#endif
        run(args, success, message);
    };
    const auto ctest = cmake.parent_path() / "ctest";
    require(fs::is_regular_file(ctest), "ctest alongside selected cmake is required");
    auto compile = [&] {
        // This fixture rewrites and restores the same sources repeatedly.
        // Each mutation must actually compile, even with a coarse-timestamp
        // backend; an incremental no-op cannot prove a negative control.
        run({cmake.string(), "--build", build.string(), "--clean-first", "--parallel", "2", "--target",
            "schgen_subsystem_widget_test", "schgen_subsystem_class_test"}, true);
    };
    auto test = [&](bool success, const std::string& message) {
        run({ctest.string(), "--test-dir", build.string(), "--output-on-failure", "-R", "^native_subsystem_(widget|class)$"},
            success, message);
    };
    configure("widget;class", true);
    compile(); test(false, "fill in the widget netlist");
    const auto implemented = read(repo / "native/tests/data/subsystem_scaffold/implemented_widget.cpp");
    write(widget.package / "widget.cpp", implemented);
    write(keyword.package / "class.cpp", rename_widget(implemented));
    compile(); test(true, "100% tests passed");
    write(widget.package / "widget.cpp", replaced(implemented, "return meta.finish(c);",
        "(void)meta; return c.finish();"));
    compile(); test(false, "factory ignores unknown metadata bind");
    write(widget.package / "widget.cpp", replaced(implemented, "c.net(\"GND\", {\"C1.2\"});", "c.nc({\"C1.2\"});"));
    compile(); test(false, "external nets differ from abstract interface");
    write(widget.package / "widget.cpp", implemented);
    compile(); test(true, "100% tests passed");
    configure("widget;widget", false, "Duplicate selected subsystem package");
    configure("../widget", false, "Invalid portable subsystem package name");
    configure("missing", false, "Missing native subsystem package");
    // A package that has assets/source but forgets registration must not build
    // a misleading all-green suite without any corresponding test target.
    const auto package_cmake = read(widget.package / "CMakeLists.txt");
    write(widget.package / "CMakeLists.txt", "# deliberately missing registration\n");
    configure("widget", false, "Package did not explicitly register a live factory");
    write(widget.package / "CMakeLists.txt", package_cmake);
    fs::rename(widget.package / "widget.cir", widget.package / "saved.cir");
    configure("widget", false, "Missing native subsystem asset");
    fs::rename(widget.package / "saved.cir", widget.package / "widget.cir");
    configure("widget;class", true);
    compile(); test(true, "100% tests passed");
    // Selection alone is insufficient without the production registry hook.
    write(src / "subsystem_authoring.cpp", replaced(registry,
        "append_configured_subsystem_definitions({", "std::vector<SubsystemDefinition>({"));
    compile(); test(false, "unknown subsystem widget");
    write(src / "subsystem_authoring.cpp", registry);
    compile(); test(true, "100% tests passed");
    require(fs::exists(repo / "subsystems/widget") == had_widget && fs::exists(repo / "subsystems/class") == had_class,
            "smoke test unexpectedly published repository sources");
}
} // namespace
int main(int argc, char** argv) {
    try {
        require(argc == 4, "usage: subsystem_scaffold_build_contracts REPOSITORY CORE_ARCHIVE CMAKE_EXECUTABLE");
        exercise(fs::absolute(argv[1]), fs::absolute(argv[2]), fs::absolute(argv[3]));
        std::cout << "PASS: " << assertions << " isolated generated C++ / registry / CMake / CTest contracts\n";
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
