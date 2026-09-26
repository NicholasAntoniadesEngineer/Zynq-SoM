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
               const std::string& variant = {}) {
    fs::create_directories(repo / "native");
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
    write(repo / "native/CMakeLists.txt", file);
    const auto result = run_process({cmake, "-S", (repo / "native").string(), "-B", (repo / "build").string(), "-DBUILD_TESTING=ON"});
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
}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc > 1 && (std::string(argv[1]) == "board" || std::string(argv[1]) == "selftest")) return fixture_board(argc, argv);
        if (argc > 1 && std::string(argv[1]) == "--test-dir") return fixture_ctest(argc, argv);
        if (argc == 4 && std::string(argv[1]) == "--regression-contract-test") {
            fixture_only(argv[2]); const auto mode = read(fs::path(argv[2]) / "mode");
            std::cout << "TEST-ONLY subprocess boundary fixture: " << argv[3] << '\n';
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
        std::cout << "Regression CLI: " << checks << " assertions PASS (TEST-ONLY child fixtures; not board acceptance)\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << "Regression CLI contract FAIL: " << error.what() << '\n'; return 1; }
}
