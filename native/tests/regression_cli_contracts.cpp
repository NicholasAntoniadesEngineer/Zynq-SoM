// Process doubles live ONLY in this test executable, require a private fixture
// marker, and are never linked into schgen. Production has no injected runner.
// CTest itself is real except explicitly named malformed-evidence negatives.
#include "schgen/regression_cli.hpp"
#include "schgen/process.hpp"

#include <chrono>
#include <csignal>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/stat.h>
#include <thread>
#include <tuple>
#include <unistd.h>

namespace {
namespace fs = std::filesystem;
using namespace schgen;
std::size_t checks = 0;
const std::vector<std::string> live_names{
    "native_regression_rc_smoke", "native_selftest_full_contracts",
    "native_board_live_contracts", "native_board_pipeline_live_contracts",
    "native_render_models_live_contracts", "native_example_devkit_live_contracts",
    "native_single_sheet_live"};
const std::vector<std::string> ci_names{
    "native_ci_cache", "native_ci_environment", "native_ci_cli",
    "native_ci_smoke_contracts", "native_ci_bootstrap_rejections",
    "native_ci_smoke_reject_arguments"};
void require(bool ok, const std::string& why) { ++checks; if (!ok) throw std::runtime_error(why); }
std::string read(const fs::path& path) {
    std::ifstream input(path, std::ios::binary);
    require(static_cast<bool>(input), "cannot read " + path.string());
    return {std::istreambuf_iterator<char>(input), {}};
}
void write(const fs::path& path, const std::string& text) {
    std::ofstream output(path, std::ios::binary); output << text; output.close();
    require(static_cast<bool>(output), "cannot write " + path.string());
}
std::string option(int argc, char** argv, const std::string& key) {
    for (int i = 1; i + 1 < argc; ++i) if (argv[i] == key) return argv[i + 1];
    return {};
}
void fixture_only(const fs::path& root) {
    if (read(root / "REGRESSION_CLI_TEST_FIXTURE") != "TEST PROCESS DOUBLES ONLY\n")
        throw std::runtime_error("not a regression contract process fixture");
}
int fixture_board(int argc, char** argv) {
    const fs::path repo = option(argc, argv, "--repo"); fixture_only(repo);
    const std::string stage = argv[1], mode = read(repo / "mode");
    std::ofstream calls(repo / "calls", std::ios::app); calls << stage << '\n'; calls.close();
    require(fs::current_path() == fs::canonical(repo), "child cwd was not repository");
    for (int i = 0; i < argc; ++i)
        require(std::string(argv[i]) != "--no-render" && std::string(argv[i]) != "--skip-audits", "gate/render bypass");
    require(!option(argc, argv, "--output").empty(), "child output boundary missing");
    if (stage == "selftest") require(std::string(argv[argc - 1]) == "--keep", "selftest evidence must be kept");
    // Raw bytes prove no newline/UTF-8 conversion and PASS text is not a verdict.
    const std::string raw{"BOARD: PASS\r\n\0\xff", 15};
    std::cout.write(raw.data(), static_cast<std::streamsize>(raw.size())); std::cout.flush();
    std::cerr << "fixture " << stage << " diagnostic\r\n" << std::flush;
    if (mode == "board-fail" && stage == "board") return 17;
    if (mode == "selftest-fail" && stage == "selftest") return 23;
    if (mode == "signal" && stage == "board") { ::raise(SIGTERM); return 99; }
    if ((mode == "timeout" && stage == "board") || (mode == "selftest-timeout" && stage == "selftest")) {
        const auto child = ::fork(); require(child >= 0, "fork failed");
        if (child == 0) {
            std::this_thread::sleep_for(std::chrono::seconds{2});
            write(repo / "DESCENDANT_SURVIVED", "bad"); ::_exit(0);
        }
        write(repo / "grandchild.pid", std::to_string(child));
        for (;;) ::pause();
    }
    return 0;
}
int fixture_ctest(int argc, char** argv) {
    const fs::path build = option(argc, argv, "--test-dir");
    const auto root = build.parent_path(); fixture_only(root);
    const auto mode = read(root / "mode");
    bool list = false;
    for (int i = 1; i < argc; ++i) if (std::string(argv[i]) == "--show-only=json-v1") list = true;
    if (mode == "bad-inventory") { std::cout << "{}"; return 0; }
    if (mode == "inventory-fail") return 19;
    if (mode == "inventory-timeout") {
        std::cerr << "partial inventory diagnostic" << std::flush;
        for (;;) ::pause();
    }
    if (list) {
        std::vector<std::string> args{read(root / "real-ctest")};
        for (int i = 1; i < argc; ++i) args.push_back(argv[i]);
        const auto result = run_process_bytes(args);
        std::cout << result.stdout_text; std::cerr << result.stderr_text; return result.exit_code;
    }
    std::cout << "100% tests passed (deliberate TEST-ONLY forged evidence)\n";
    const auto junit = option(argc, argv, "--output-junit");
    if (mode == "missing-junit") return 0;
    if (mode == "dtd-junit") { write(junit, "<!DOCTYPE testsuite [<!ENTITY e 'bad'>]><testsuite/>"); return 0; }
    std::string xml = "<testsuite tests=\"8\" failures=\"0\" disabled=\"0\">";
    for (const auto& name : live_names) xml += "<testcase name=\"" + name + "\" status=\"run\"/>";
    xml += "<testcase name=\"wrong-name\" status=\"run\"/></testsuite>";
    write(junit, xml); return 0;
}
struct Capture {
    std::ostringstream out, err;
    std::streambuf *old_out, *old_err;
    Capture() : old_out(std::cout.rdbuf(out.rdbuf())), old_err(std::cerr.rdbuf(err.rdbuf())) {}
    ~Capture() { std::cout.rdbuf(old_out); std::cerr.rdbuf(old_err); }
};
struct Result { std::optional<int> code; std::string out, err; };
Result invoke(std::vector<std::string> args) {
    std::vector<char*> argv; for (auto& arg : args) argv.push_back(arg.data()); argv.push_back(nullptr);
    Capture capture;
    const auto result = run_regression_command(static_cast<int>(args.size()), argv.data());
    return {result, capture.out.str(), capture.err.str()};
}
std::string cmake_quote(const std::string& s) {
    std::string out = "\"";
    for (const auto c : s) { if (c == '\\' || c == '\"' || c == '$') out += '\\'; out += c; }
    return out + '"';
}
void configure(const fs::path& repo, const fs::path& self, const std::string& cmake,
               const std::string& variant = {}, const fs::path& source = "native") {
    fs::create_directories(repo / source);
    write(repo / "REGRESSION_CLI_TEST_FIXTURE", "TEST PROCESS DOUBLES ONLY\n");
    write(repo / "mode", "pass");
    std::string file = "cmake_minimum_required(VERSION 3.21)\nproject(RegressionProcessFixture NONE)\ninclude(CTest)\n";
    if (variant != "empty") {
        for (const auto& name : live_names) {
            if (variant == "missing" && name == "native_regression_rc_smoke") continue;
            file += "add_test(NAME " + name + " COMMAND " + cmake_quote(self.string()) +
                " --regression-contract-test " + cmake_quote(repo.string()) + " " + name + ")\n";
        }
        file += "add_test(NAME extra_native_contract COMMAND " + cmake_quote(self.string()) +
                " --regression-contract-test " + cmake_quote(repo.string()) + " extra_native_contract)\n";
        file += "set_tests_properties(extra_native_contract PROPERTIES SKIP_RETURN_CODE 77)\n";
        if (variant == "disabled") file += "set_tests_properties(native_board_live_contracts PROPERTIES DISABLED TRUE)\n";
        if (variant == "unbuilt") file += "add_test(NAME unbuilt_native_contract COMMAND /no-such-native-contract-binary)\n";
        if (variant == "shell") file += "add_test(NAME invalid_shell_contract COMMAND /bin/sh -c exit)\n";
    }
    if (source == "native/ci") {
        write(repo / "native/CMakeLists.txt", file);
        file = "cmake_minimum_required(VERSION 3.21)\nproject(RegressionCIProcessFixture NONE)\ninclude(CTest)\nadd_subdirectory(.. engine)\n";
        for (const auto& name : ci_names) {
            if (variant == "missing:" + name) continue;
            file += "add_test(NAME " + name + " COMMAND " +
                (variant == "unbuilt:" + name ? cmake_quote("/no-such-native-contract-binary") : cmake_quote(self.string())) +
                " --regression-contract-test " + cmake_quote(repo.string()) + " " + name + ")\n";
            if (variant == "disabled:" + name)
                file += "set_tests_properties(" + name + " PROPERTIES DISABLED TRUE)\n";
            if (name == "native_ci_smoke_reject_arguments")
                file += "set_tests_properties(" + name + " PROPERTIES WILL_FAIL TRUE)\n";
            if (name == "native_ci_cache" || name == "native_ci_environment")
                file += "set_tests_properties(" + name + " PROPERTIES FIXTURES_SETUP native_ci_ready)\n";
            if (name == "native_ci_cli")
                file += "set_tests_properties(" + name + " PROPERTIES FIXTURES_REQUIRED native_ci_ready)\n";
        }
        file += "get_property(engine_tests DIRECTORY \"${CMAKE_CURRENT_SOURCE_DIR}/..\" PROPERTY TESTS)\n"
                "if(engine_tests)\nset_property(TEST ${engine_tests} DIRECTORY \"${CMAKE_CURRENT_SOURCE_DIR}/..\" APPEND PROPERTY FIXTURES_REQUIRED native_ci_ready)\nendif()\n";
    }
    write(repo / source / "CMakeLists.txt", file);
    const auto result = run_process({cmake, "-S", (repo / source).string(), "-B", (repo / "build").string(),
        "-DBUILD_TESTING=ON", "-DSCHGEN_BUILD_PYTHON:BOOL=OFF"});
    require(result.exit_code == 0, "actual CMake fixture configuration failed: " + result.stderr_text);
}
fs::path logs(const Result& result) {
    const auto start = result.out.find("REGRESSION LOGS: ");
    require(start != std::string::npos, "log location missing: " + result.err);
    const auto begin = start + std::string("REGRESSION LOGS: ").size();
    return result.out.substr(begin, result.out.find('\n', begin) - begin);
}
void contracts(const fs::path& scratch, const fs::path& self, const std::string& cmake, const std::string& ctest) {
    const auto repo = scratch / "fixture repo with spaces";
    configure(repo, self, cmake); write(repo / "real-ctest", ctest);
    auto base = std::vector<std::string>{self.string(), "check", "--repo", repo.string(),
        "--tests-dir", (repo / "build").string(), "--ctest", ctest,
        "--output", (scratch / "logs ; $(never)").string(), "--timeout", "10"};
    auto result = invoke({"cannot-exist", "check", "--help"});
    require(result.code == 0 && result.out.find("--tests-dir") != std::string::npos && result.out.find("RC smoke") != std::string::npos, "specific help without validation/spawn");
    require(result.out.find("ROOT/native/ci") != std::string::npos &&
        result.out.find("SCHGEN_BUILD_PYTHON explicitly OFF") != std::string::npos, "help omits exact build policy");
    require(!invoke({self.string(), "board"}).code, "foreign command claimed");
    require(!invoke({self.string(), "--project", "check", "board"}).code, "option value claimed as command");
    require(!run_regression_command(0, nullptr), "empty invocation claimed");
    result = invoke({self.string(), "check"});
    require(result.code == 2 && result.err.find("--tests-dir") != std::string::npos, "explicit build directory required");
    for (const auto& extra : std::vector<std::vector<std::string>>{
            {"--tests-dir", "repeat"}, {"-o", "repeat"}, {"--no-render"}, {"--skip-audits"},
            {"-R", "smoke"}, {"--project"}, {"--unknown"}, {"unrequested-subsystem"}}) {
        auto args = base; args.insert(args.end(), extra.begin(), extra.end());
        require(invoke(args).code == 2, "invalid/duplicate option accepted");
    }
    for (const std::string value : {"0", "-1", "1.5", "nan", "86401", "1000000000000000", "+1"}) {
        auto args = base; args.back() = value;
        require(invoke(args).code == 2, "unbounded/invalid timeout accepted");
    }
    auto args = base; args.insert(args.end(), {"--project", "project ; $(touch UNEXPECTED) ' literal", "--config", "Release"});
    result = invoke(args);
    require(result.code == 0, "fixture orchestration failed: " + result.err + result.out);
    require(result.out.find("all 8 CTest contracts") != std::string::npos, "all tests including non-required extra not run");
    require(read(repo / "calls") == "board\nselftest\n", "native stages wrong order/count");
    const auto run = logs(result);
    require(read(run / "01-board.stdout") == std::string("BOARD: PASS\r\n\0\xff", 15), "raw bytes not preserved");
    require(read(run / "01-board.argv").find("project ; $(touch UNEXPECTED) ' literal") != std::string::npos, "literal argument lost");
    require(read(run / "03-ctest.argv").find("--stop-on-failure") != std::string::npos, "CTest not fail-fast");
    require(read(run / "03-ctest.argv").find("--no-tests=error") != std::string::npos, "empty suite could pass");
    require(read(run / "result.txt") == "PASS\ncontracts=8\n", "no verified summary");
    require(!fs::exists(repo / "UNEXPECTED"), "shell metacharacters executed");
    require(fs::exists(run / "ctest-results.xml"), "JUnit evidence missing");
    result = invoke(base); require(result.code == 0 && logs(result) != run && fs::exists(run / "result.txt"), "second run overwrote prior evidence");
    // Leading global options and argv0 via PATH resolve to the actual invoker,
    // not a hard-coded native/bin/schgen or a reconstructed executable name.
    const auto saved_path = std::getenv("PATH") ? std::getenv("PATH") : "";
    const std::string old_path = saved_path;
    const auto alias = scratch / "regression-fixture-program"; fs::create_symlink(self, alias);
    ::setenv("PATH", (scratch.string() + ":" + old_path).c_str(), 1);
    args = base; args[0] = alias.filename().string(); args.erase(args.begin() + 1); args.insert(args.begin() + 5, "check");
    result = invoke(args);
    ::setenv("PATH", old_path.c_str(), 1);
    require(result.code == 0, "PATH/global-option dispatch failed: " + result.err);
    for (const auto& [mode, code, calls] : std::vector<std::tuple<std::string,int,std::string>>{
            {"board-fail",17,"board\n"}, {"selftest-fail",23,"board\nselftest\n"},
            {"signal",128 + SIGTERM,"board\n"}, {"ctest-fail",8,"board\nselftest\n"},
            {"ctest-skip",2,"board\nselftest\n"}}) {
        write(repo / "mode", mode); write(repo / "calls", ""); result = invoke(base);
        require(result.code == code, mode + " wrong status: " + result.err);
        require(read(repo / "calls") == calls, mode + " did not stop at first failure");
        require(result.out.find("REGRESSION PASS") == std::string::npos, mode + " false PASS");
        require(!fs::exists(logs(result) / "result.txt"), mode + " synthesized success file");
        if (mode == "ctest-fail") require(read(logs(result) / "03-ctest.stdout").find("extra_native_contract") == std::string::npos, "CTest continued after failure");
    }
    write(repo / "mode", "timeout"); write(repo / "calls", ""); args = base; args.back() = "1";
    const auto started = std::chrono::steady_clock::now(); result = invoke(args);
    require(result.code == 124, "timeout status not 124: " + result.err);
    require(std::chrono::steady_clock::now() - started < std::chrono::seconds{5}, "timeout was not bounded");
    require(read(logs(result) / "01-board.stdout").find("BOARD: PASS") != std::string::npos, "timeout discarded partial stdout");
    require(read(logs(result) / "01-board.stderr").find("diagnostic") != std::string::npos, "timeout discarded partial stderr");
    require(read(logs(result) / "01-board.status").find("timeout=true") != std::string::npos, "timeout metadata missing");
    std::this_thread::sleep_for(std::chrono::milliseconds{1200});
    require(!fs::exists(repo / "DESCENDANT_SURVIVED"), "timeout failed to kill descendant process group");
    write(repo / "mode", "selftest-timeout"); write(repo / "calls", ""); result = invoke(args);
    require(result.code == 124 && read(repo / "calls") == "board\nselftest\n", "selftest timeout did not fail-fast");
    require(fs::exists(logs(result) / "02-selftest.stderr") && !fs::exists(logs(result) / "03-ctest.stdout"), "selftest timeout lost logs or started CTest");
    write(repo / "mode", "ctest-timeout"); write(repo / "calls", ""); result = invoke(args);
    require(result.code == 124 && read(repo / "calls") == "board\nselftest\n", "whole CTest timeout not bounded");
    require(read(logs(result) / "03-ctest.status").find("timeout=true") != std::string::npos, "CTest timeout status lost");
    std::this_thread::sleep_for(std::chrono::milliseconds{3400});
    require(!fs::exists(repo / "CTEST_DESCENDANT_SURVIVED"), "timed-out CTest left its test running");
    write(repo / "mode", "pass");
    args = base; args[0] = (scratch / "missing-program").string(); require(invoke(args).code == 2, "missing invoker accepted");
    const auto bad_program = scratch / "not-an-executable-format"; write(bad_program, "TEST INVALID EXECUTABLE FORMAT\n");
    ::chmod(bad_program.c_str(), 0700); args[0] = bad_program.string(); result = invoke(args);
    require(result.code == 126 && read(logs(result) / "01-board.status").find("spawn_error=") != std::string::npos, "spawn failure not truthful/retained");
    // Evidence-forgery mocks are confined to this marked fixture executable.
    for (const auto& [mode, code] : std::vector<std::pair<std::string,int>>{
            {"bad-inventory",2}, {"inventory-fail",19}, {"missing-junit",2}, {"wrong-junit",2}, {"dtd-junit",2}}) {
        write(repo / "mode", mode); write(repo / "calls", ""); args = base; args[7] = self.string(); result = invoke(args);
        require(result.code == code && result.out.find("REGRESSION PASS") == std::string::npos, "forged evidence accepted: " + mode + result.err);
        if (mode == "bad-inventory" || mode == "inventory-fail") require(read(repo / "calls").empty(), "preflight error ran board");
    }
    write(repo / "mode", "inventory-timeout"); write(repo / "calls", ""); args = base; args[7] = self.string(); args.back() = "1";
    result = invoke(args);
    require(result.code == 124 && read(repo / "calls").empty(), "inventory timeout ran board");
    require(read(logs(result) / "00-inventory.stderr") == "partial inventory diagnostic", "inventory timeout lost logs");
    for (const std::string variant : {"missing", "empty", "disabled", "unbuilt", "shell"}) {
        const auto other = scratch / variant; configure(other, self, cmake, variant);
        args = base; args[3] = other.string(); args[5] = (other / "build").string(); result = invoke(args);
        require(result.code == 2 && !fs::exists(other / "calls"), "incomplete/disabled build ran board: " + variant);
    }
    args = base; args[3] = (scratch / "missing").string();
    require(invoke(args).code == 2, "build from different repository accepted");
    const auto bad_dir = scratch / "empty-build"; fs::create_directory(bad_dir); args = base; args[5] = bad_dir.string();
    require(invoke(args).code == 2, "non-CTest directory accepted");
    const auto not_directory = scratch / "not-an-output-directory"; write(not_directory, "preserve");
    args = base; args[9] = not_directory.string(); result = invoke(args);
    require(result.code == 2 && read(not_directory) == "preserve", "invalid output path overwritten");
}

// Mutate only real CMake-generated caches in private marked test repositories.
// The production driver still reads actual CTest evidence and spawns processes.
std::string cache_value(const std::string& cache, const std::string& key,
                        const std::optional<std::string>& value) {
    std::istringstream input(cache); std::string result; bool found = false;
    for (std::string line; std::getline(input, line);) {
        if (line.rfind(key + ':', 0) == 0) {
            require(!found, "duplicate key in original CMake fixture cache"); found = true;
            if (!value) continue;
            line = line.substr(0, line.find('=') + 1) + *value;
        }
        result += line + '\n';
    }
    require(found, "fixture cache has no " + key); return result;
}
void build_roots_contracts(const fs::path& scratch, const fs::path& self,
                           const std::string& cmake, const std::string& ctest) {
    const auto arguments = [&](const fs::path& repo) {
        return std::vector<std::string>{self.string(), "check", "--repo", repo.string(),
            "--tests-dir", (repo / "build").string(), "--ctest", ctest,
            "--output", (repo / "evidence").string(), "--timeout", "10"};
    };
    const auto rejected_before_board = [&](const fs::path& repo, const std::string& diagnostic) {
        write(repo / "calls", "");
        const auto result = invoke(arguments(repo));
        // CTest releases either omit an unbuilt command from JSON or retain
        // its unresolved path. Both must fail before board/selftest execution.
        const bool matches = diagnostic == "unbuilt" ?
            result.err.find("invalid CTest inventory: command") != std::string::npos ||
            result.err.find("CTest target not built") != std::string::npos ||
            result.err.find("cannot resolve executable") != std::string::npos :
            result.err.find(diagnostic) != std::string::npos;
        require(result.code == 2 && matches,
            "expected preflight rejection: " + diagnostic + ": " + result.err);
        require(read(repo / "calls").empty(), "preflight rejection launched board/selftest");
        require(result.out.find("REGRESSION PASS") == std::string::npos, "preflight false PASS");
        if (result.out.find("REGRESSION LOGS:") != std::string::npos) {
            const auto run = logs(result);
            require(!fs::exists(run / "01-board.argv") && !fs::exists(run / "result.txt"),
                "rejected inventory published board or success evidence");
        }
        return result;
    };
    for (const bool wrapper : {false, true}) {
        const auto repo = scratch / (wrapper ? "wrapper-build" : "direct-build");
        configure(repo, self, cmake, {}, wrapper ? "native/ci" : "native");
        const auto args = arguments(repo);
        const auto result = invoke(args);
        require(result.code == 0, "valid source root failed: " + result.err + result.out);
        require(read(repo / "calls") == "board\nselftest\n", "valid source root changed stages");
        require(read(logs(result) / "result.txt") == std::string("PASS\ncontracts=") + (wrapper ? "14\n" : "8\n"),
            "valid source root did not run every nested test");
        if (wrapper) {
            const auto xml = read(logs(result) / "ctest-results.xml");
            for (const auto& name : ci_names)
                require(xml.find("name=\"" + name + "\"") != std::string::npos, "wrapper result omitted " + name);
        }
        const auto cache_path = repo / "build/CMakeCache.txt";
        const auto cache = read(cache_path);
        for (const auto& value : std::vector<std::optional<std::string>>{
                "ON", "TRUE", "1", "YES", "OFF ", "FALSE", "0", "", "garbage", std::nullopt}) {
            write(cache_path, cache_value(cache, "SCHGEN_BUILD_PYTHON", value));
            const auto failure = rejected_before_board(repo, "SCHGEN_BUILD_PYTHON explicitly OFF");
            require(failure.out.find("REGRESSION LOGS:") == std::string::npos, "cache rejection wrote a run or spawned CTest");
        }
        for (const auto& value : std::vector<std::optional<std::string>>{"OFF", "", std::nullopt}) {
            write(cache_path, cache_value(cache, "BUILD_TESTING", value));
            rejected_before_board(repo, "enable BUILD_TESTING");
        }
        for (const auto& key : {"SCHGEN_BUILD_PYTHON", "BUILD_TESTING", "CMAKE_HOME_DIRECTORY"}) {
            write(cache_path, cache + key + ":STRING=OFF\n");
            rejected_before_board(repo, "duplicate CMake cache key");
        }
        write(cache_path, cache_value(cache, "CMAKE_HOME_DIRECTORY", std::nullopt));
        rejected_before_board(repo, "ROOT/native or ROOT/native/ci");
        write(cache_path, cache);
        // Canonical aliases must be equivalent; spelling/prefix checks are not sufficient.
        const auto alias = scratch / (wrapper ? "wrapper-alias" : "direct-alias");
        fs::create_directory_symlink(repo, alias);
        require(invoke(arguments(alias)).code == 0, "canonical repository/build alias rejected");
        const auto source_alias = scratch / (wrapper ? "wrapper-source-alias" : "direct-source-alias");
        fs::create_directory_symlink(repo / (wrapper ? "native/ci" : "native"), source_alias);
        write(cache_path, cache_value(cache, "CMAKE_HOME_DIRECTORY", source_alias.string()));
        require(invoke(args).code == 0, "canonical cache source alias rejected");
        write(cache_path, cache);
        if (!wrapper) continue;
        auto engine_args = args; engine_args[5] = (repo / "build/engine").string();
        const auto engine = invoke(engine_args);
        require(engine.code == 2 && engine.err.find("no CMakeCache.txt") != std::string::npos,
            "wrapper engine-only subdirectory bypassed top-level cache");
        for (const auto& mode : {"ci-cache-fail", "ci-environment-fail", "ctest-skip"}) {
            write(repo / "mode", mode); write(repo / "calls", "");
            const auto failed = invoke(args);
            require(failed.code == (std::string(mode) == "ctest-skip" ? 2 : 8), "wrapper failure status lost: " + failed.err);
            require(read(repo / "calls") == "board\nselftest\n", "wrapper altered documented stage order");
            require(fs::exists(logs(failed) / "03-ctest.stdout") && !fs::exists(logs(failed) / "result.txt"),
                "wrapper failure lost diagnostics or published PASS");
            if (std::string(mode) != "ctest-skip")
                require(read(logs(failed) / "03-ctest.stdout").find("extra_native_contract") == std::string::npos,
                    "CTest executed dependent engine test after failed CI fixture");
        }
    }
    for (const auto& name : ci_names) {
        const auto repo = scratch / ("missing-" + name);
        configure(repo, self, cmake, "missing:" + name, "native/ci");
        rejected_before_board(repo, "missing required native CI CTest contract: " + name);
    }
    for (const auto& variant : {"missing", "empty", "disabled", "unbuilt", "shell",
             "disabled:native_ci_environment", "unbuilt:native_ci_cli"}) {
        const auto repo = scratch / ("wrapper-negative-" + std::string(variant));
        configure(repo, self, cmake, variant, "native/ci");
        rejected_before_board(repo, variant == std::string("missing") || variant == std::string("empty") ?
            "missing required live/RC" : variant == std::string("shell") ? "not a native contract" :
            std::string(variant).find("disabled") == 0 ? "disabled CTest contract" : "unbuilt");
    }
    // These contain a full fixture test inventory: failure must be the source
    // boundary, not just absent anchors in an ordinary smoke-only build.
    for (const auto& source : {"native/ci/smoke", "native/other", "native/ci-copy", "native/ci/nested"}) {
        const auto repo = scratch / ("wrong-source-" + fs::path(source).filename().string());
        configure(repo, self, cmake, {}, source);
        rejected_before_board(repo, "ROOT/native or ROOT/native/ci");
    }
    auto wrong_repo = arguments(scratch / "wrapper-build");
    wrong_repo[3] = (scratch / "direct-build").string();
    const auto wrong = invoke(wrong_repo);
    require(wrong.code == 2 && wrong.err.find("ROOT/native or ROOT/native/ci") != std::string::npos,
        "wrapper from another repository accepted");
}
}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc > 1 && (std::string(argv[1]) == "board" || std::string(argv[1]) == "selftest")) return fixture_board(argc, argv);
        if (argc > 1 && std::string(argv[1]) == "--test-dir") return fixture_ctest(argc, argv);
        if (argc == 4 && std::string(argv[1]) == "--regression-contract-test") {
            fixture_only(argv[2]); const auto mode = read(fs::path(argv[2]) / "mode");
            std::cout << "TEST-ONLY subprocess boundary fixture: " << argv[3] << '\n';
            const std::string test = argv[3];
            if (test == "native_ci_smoke_reject_arguments") return 7; // Real CTest WILL_FAIL contract.
            if ((mode == "ci-cache-fail" && test == "native_ci_cache") ||
                (mode == "ci-environment-fail" && test == "native_ci_environment")) return 32;
            if (mode == "ctest-fail") return 31;
            if (mode == "ctest-skip" && std::string(argv[3]) == "extra_native_contract") return 77;
            if (mode == "ctest-timeout" && std::string(argv[3]) == "extra_native_contract") {
                std::this_thread::sleep_for(std::chrono::seconds{4});
                write(fs::path(argv[2]) / "CTEST_DESCENDANT_SURVIVED", "bad");
            }
            return 0;
        }
        require(argc == 1 || argc == 3, "usage: regression_cli_contracts [CMAKE CTEST]");
        const auto resolve = [](const std::string& name) {
            const auto found = find_executable(name);
            require(found.has_value(), "required executable missing: " + name);
            return fs::canonical(*found);
        };
        const auto self = resolve(argv[0]);
        const auto cmake = resolve(argc == 3 ? argv[1] : "cmake").string();
        const auto ctest = resolve(argc == 3 ? argv[2] : "ctest").string();
        auto pattern = (fs::temp_directory_path() / "schgen-regression-contracts-XXXXXX").string();
        require(::mkdtemp(pattern.data()) != nullptr, "mkdtemp failed");
        const fs::path scratch = pattern;
        std::cout << "REGRESSION CONTRACT EVIDENCE: " << scratch << '\n';
        contracts(scratch, self, cmake, ctest);
        build_roots_contracts(scratch, self, cmake, ctest);
        std::cout << "Regression CLI: " << checks << " assertions PASS (TEST-ONLY child fixtures; not board acceptance)\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << "Regression CLI contract FAIL: " << error.what() << '\n'; return 1; }
}
