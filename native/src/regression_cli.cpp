#if defined(__linux__) && !defined(_GNU_SOURCE)
#define _GNU_SOURCE
#endif
#include "schgen/regression_cli.hpp"

#include "schgen/json.hpp"
#include "schgen/process.hpp"

#include <libxml/parser.h>
#include <libxml/tree.h>

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <climits>
#include <cstring>
#include <fcntl.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <signal.h>
#include <spawn.h>
#include <stdexcept>
#include <string>
#include <sys/wait.h>
#include <thread>
#include <unistd.h>
#include <vector>

extern char** environ;

namespace schgen {
namespace {
namespace fs = std::filesystem;
using Seconds = std::chrono::seconds;
const std::set<std::string> required_tests{
    "native_regression_rc_smoke", "native_selftest_full_contracts",
    "native_board_live_contracts", "native_board_pipeline_live_contracts",
    "native_render_models_live_contracts", "native_example_devkit_live_contracts",
    "native_single_sheet_live"};

const char help[] =
    "usage: schgen check --tests-dir BUILD [--repo ROOT] [--project NAME_OR_PATH]\n"
    "                    [-o DIRECTORY] [--ctest PATH] [--kicad-cli PATH]\n"
    "                    [--config CONFIG] [--timeout SECONDS]\n\n"
    "Run the complete native board, native mutation/determinism selftest, then\n"
    "ALL CTest contracts, including live KiCad gates and the native RC smoke.\n"
    "Stop at the first failure. No rendering/gate skips, test filters, Python,\n"
    "shell command strings, builds, or success-by-empty/disabled/skipped tests.\n\n"
    "--tests-dir  Required configured and built native CTest directory for ROOT.\n"
    "--repo       Repository root (default: current working directory).\n"
    "--project    Forwarded unchanged to board and selftest (native default if absent).\n"
    "--output, -o Parent for a NEW regression-XXXXXX run directory (default: system temp).\n"
    "             Retains board/, selftest.txt, raw per-stage stdout/stderr, argv,\n"
    "             statuses, CTest inventory and JUnit, even on failure/timeout.\n"
    "--ctest      CTest executable (default: ctest on PATH).\n"
    "--kicad-cli  KiCad executable for board/selftest; CTest uses its build configuration.\n"
    "--config     CTest build configuration, e.g. Release.\n"
    "--timeout    Wall-clock limit per stage and default CTest test limit,\n"
    "             integer seconds 1..86400 (default 3600; inventory <=30).\n"
    "--help, -h   This command's help; no children or writes.\n";

[[noreturn]] void fail(const std::string& text) { throw std::runtime_error(text); }
std::string read(const fs::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) fail("cannot read " + path.string());
    std::string text{std::istreambuf_iterator<char>(input), {}};
    if (input.bad()) fail("cannot read " + path.string());
    return text;
}
void write(const fs::path& path, const std::string& text) {
    std::ofstream output(path, std::ios::binary);
    output.write(text.data(), static_cast<std::streamsize>(text.size()));
    output.close();
    if (!output) fail("cannot write " + path.string());
}
fs::path executable(const std::string& text) {
    const auto path = find_executable(text);
    if (!path) fail("cannot resolve executable: " + text);
    return fs::canonical(*path);
}
struct Options {
    fs::path repo = fs::current_path(), tests, output;
    std::string project, ctest = "ctest", kicad, config;
    Seconds timeout{3600};
    bool help = false;
};
bool takes_value(const std::string& key) {
    return key == "--repo" || key == "--project" || key == "--tests-dir" ||
        key == "--output" || key == "-o" || key == "--ctest" ||
        key == "--kicad-cli" || key == "--config" || key == "--timeout";
}
// Scan only tokens in command position, never an option's value named "check".
bool owns(int argc, char** argv) {
    for (int i = 1; i < argc; ++i) {
        if (!argv[i]) return false;
        const std::string token = argv[i];
        if (takes_value(token)) { ++i; continue; }
        if (token == "check") return true;
        if (token.empty() || token.front() != '-') return false;
    }
    return false;
}
Options parse(int argc, char** argv) {
    Options o; std::set<std::string> seen; bool command = false;
    for (int i = 1; i < argc; ++i) {
        if (!argv[i]) fail("null command argument");
        const std::string key = std::string(argv[i]) == "-o" ? "--output" : argv[i];
        if (key == "check" && !command) { command = true; continue; }
        if (key == "--help" || key == "-h") { o.help = true; continue; }
        if (!takes_value(key)) fail("unknown check option: " + key);
        if (!seen.insert(key).second) fail("duplicate option: " + key);
        if (++i >= argc || !argv[i] || !*argv[i]) fail("missing value for " + key);
        const std::string value = argv[i];
        if (value.rfind("--", 0) == 0) fail("missing value for " + key);
        if (key == "--repo") o.repo = value;
        else if (key == "--project") o.project = value;
        else if (key == "--tests-dir") o.tests = value;
        else if (key == "--output") o.output = value;
        else if (key == "--ctest") o.ctest = value;
        else if (key == "--kicad-cli") o.kicad = value;
        else if (key == "--config") o.config = value;
        else {
            if (value.size() > 5 || value.find_first_not_of("0123456789") != std::string::npos)
                fail("--timeout must be integer seconds 1..86400");
            const auto count = std::stol(value);
            if (count < 1 || count > 86400) fail("--timeout must be integer seconds 1..86400");
            o.timeout = Seconds{count};
        }
    }
    if (!o.help && o.tests.empty()) fail("check requires explicit --tests-dir BUILD; use check --help");
    return o;
}
void validate_build(Options& o) {
    o.repo = fs::canonical(o.repo); o.tests = fs::canonical(o.tests);
    if (!fs::is_directory(o.repo) || !fs::is_directory(o.tests) ||
        !fs::is_regular_file(o.tests / "CTestTestfile.cmake"))
        fail("--tests-dir must be a configured native CTest build directory");
    std::map<std::string, std::string> cache;
    std::ifstream input(o.tests / "CMakeCache.txt");
    if (!input) fail("--tests-dir has no CMakeCache.txt");
    for (std::string line; std::getline(input, line);) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty() || line[0] == '#' || line.rfind("//", 0) == 0) continue;
        const auto colon = line.find(':'); const auto equals = line.find('=', colon);
        if (colon != std::string::npos && equals != std::string::npos)
            cache[line.substr(0, colon)] = line.substr(equals + 1);
    }
    if (cache["CMAKE_HOME_DIRECTORY"].empty() ||
        fs::canonical(cache["CMAKE_HOME_DIRECTORY"]) != fs::canonical(o.repo / "native"))
        fail("CTest build source must be --repo ROOT/native");
    if (cache["BUILD_TESTING"] != "ON" && cache["BUILD_TESTING"] != "TRUE" && cache["BUILD_TESTING"] != "1")
        fail("CTest build must enable BUILD_TESTING");
}

struct Descriptor {
    int value = -1;
    explicit Descriptor(const fs::path& path) {
        value = ::open(path.c_str(), O_RDWR | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
        if (value < 0) fail("cannot create log " + path.string() + ": " + std::strerror(errno));
    }
    ~Descriptor() { if (value >= 0) ::close(value); }
    Descriptor(const Descriptor&) = delete;
    Descriptor& operator=(const Descriptor&) = delete;
};
void checked(int code, const char* operation) {
    if (code) fail(std::string(operation) + ": " + std::strerror(code));
}
struct SpawnActions {
    posix_spawn_file_actions_t value;
    SpawnActions() { checked(posix_spawn_file_actions_init(&value), "spawn actions"); }
    ~SpawnActions() { posix_spawn_file_actions_destroy(&value); }
};
struct SpawnAttributes {
    posix_spawnattr_t value;
    SpawnAttributes() { checked(posix_spawnattr_init(&value), "spawn attributes"); }
    ~SpawnAttributes() { posix_spawnattr_destroy(&value); }
};
struct Child {
    pid_t pid = -1;
    ~Child() {
        if (pid <= 0) return;
        ::kill(-pid, SIGKILL);
        int status = 0;
        while (::waitpid(pid, &status, 0) < 0 && errno == EINTR) {}
    }
};
// Bounded replay per polling tick; logs themselves are never truncated or
// UTF-8/newline-normalized. A prolific child cannot starve the deadline check.
void replay(int fd, off_t& offset, std::ostream& output) {
    char buffer[16384];
    for (int i = 0; i < 16; ++i) {
        const auto count = ::pread(fd, buffer, sizeof(buffer), offset);
        if (count < 0 && errno == EINTR) { --i; continue; }
        if (count < 0) fail("cannot replay child log");
        if (!count) break;
        offset += count; output.write(buffer, count);
    }
    output.flush();
}
int spawn(const std::vector<std::string>& args, const fs::path& cwd,
          const fs::path& logs, const std::string& label, Seconds timeout, bool echo) {
    std::string invocation;
    for (const auto& arg : args) {
        if (arg.find('\0') != std::string::npos) fail("NUL in process argument");
        invocation += std::to_string(arg.size()) + ':' + arg + '\n';
    }
    write(logs / (label + ".argv"), invocation);
    Descriptor out(logs / (label + ".stdout")), err(logs / (label + ".stderr"));
    SpawnActions actions; SpawnAttributes attributes;
    checked(posix_spawn_file_actions_addopen(&actions.value, STDIN_FILENO, "/dev/null", O_RDONLY, 0), "stdin");
    checked(posix_spawn_file_actions_adddup2(&actions.value, out.value, STDOUT_FILENO), "stdout");
    checked(posix_spawn_file_actions_adddup2(&actions.value, err.value, STDERR_FILENO), "stderr");
#if defined(__APPLE__) && __ENVIRONMENT_MAC_OS_X_VERSION_MIN_REQUIRED__ >= 260000
    checked(posix_spawn_file_actions_addchdir(&actions.value, cwd.c_str()), "child cwd");
#else
    checked(posix_spawn_file_actions_addchdir_np(&actions.value, cwd.c_str()), "child cwd");
#endif
#if defined(__GLIBC__) && defined(__GLIBC_PREREQ)
#if __GLIBC_PREREQ(2,34)
    checked(posix_spawn_file_actions_addclosefrom_np(&actions.value, 3), "close descriptors");
#endif
#endif
    short flags = POSIX_SPAWN_SETPGROUP;
#ifdef POSIX_SPAWN_CLOEXEC_DEFAULT
    flags |= POSIX_SPAWN_CLOEXEC_DEFAULT;
#endif
    checked(posix_spawnattr_setpgroup(&attributes.value, 0), "process group");
    checked(posix_spawnattr_setflags(&attributes.value, flags), "process flags");
    std::vector<char*> argv;
    for (const auto& arg : args) argv.push_back(const_cast<char*>(arg.c_str()));
    argv.push_back(nullptr);
    Child child;
    const int error = ::posix_spawn(&child.pid, argv.front(), &actions.value, &attributes.value, argv.data(), environ);
    if (error) {
        child.pid = -1;
        const int code = error == ENOENT ? 127 : 126;
        write(logs / (label + ".status"), "spawn_error=" + std::to_string(error) + "\nexit=" + std::to_string(code) + "\n");
        std::cerr << "cannot launch " << args.front() << ": " << std::strerror(error) << '\n';
        return code;
    }
    off_t out_at = 0, err_at = 0;
    int status = 0; bool timeout_hit = false;
    const auto deadline = std::chrono::steady_clock::now() + timeout;
    for (;;) {
        if (echo) { replay(out.value, out_at, std::cout); replay(err.value, err_at, std::cerr); }
        const auto result = ::waitpid(child.pid, &status, WNOHANG);
        if (result == child.pid) { child.pid = -1; break; }
        if (result < 0) { if (errno == EINTR) continue; fail("waitpid failed: " + std::string(std::strerror(errno))); }
        if (std::chrono::steady_clock::now() >= deadline) {
            timeout_hit = true;
            ::kill(-child.pid, SIGKILL);
            while (::waitpid(child.pid, &status, 0) < 0) {
                if (errno != EINTR) fail("cannot reap timed-out child");
            }
            child.pid = -1; break;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds{10});
    }
    if (echo) { replay(out.value, out_at, std::cout); replay(err.value, err_at, std::cerr); }
    const int code = timeout_hit ? 124 : WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
    write(logs / (label + ".status"), "exit=" + std::to_string(code) + "\ntimeout=" +
        (timeout_hit ? "true" : "false") + "\nsignal=" + std::to_string(WIFSIGNALED(status) ? WTERMSIG(status) : 0) + "\n");
    if (timeout_hit) std::cerr << label << " timed out after " << timeout.count() << " seconds\n";
    return code;
}
const JsonNode& field(const JsonNode& node, const std::string& key, JsonKind kind) {
    const auto* value = object_field(node, key);
    if (!value || value->kind != kind) fail("invalid CTest inventory: " + key);
    return *value;
}
std::set<std::string> inventory(const fs::path& path) {
    const auto root = parse_json_file(path.string());
    if (field(root, "kind", JsonKind::String).string_value != "ctestInfo") fail("not a CTest inventory");
    if (field(field(root, "version", JsonKind::Object), "major", JsonKind::Number).number_value != 1)
        fail("unsupported CTest inventory version");
    std::set<std::string> names;
    for (const auto& test : field(root, "tests", JsonKind::Array).array_value) {
        const auto name = field(test, "name", JsonKind::String).string_value;
        if (name.empty() || !names.insert(name).second) fail("empty or duplicate CTest name");
        const auto& command = field(test, "command", JsonKind::Array).array_value;
        if (command.empty() || command.front().kind != JsonKind::String) fail("CTest target not built: " + name);
        const auto program = executable(command.front().string_value);
        const auto basename = program.filename().string();
        const std::set<std::string> shells{"sh", "bash", "zsh", "dash", "csh", "fish", "cmd", "powershell", "pwsh"};
        if (shells.count(basename) || basename.rfind("python", 0) == 0 || basename.rfind("pypy", 0) == 0)
            fail("CTest entry is not a native contract: " + name);
        for (const auto& prop : field(test, "properties", JsonKind::Array).array_value) {
            if (field(prop, "name", JsonKind::String).string_value == "DISABLED") {
                const auto* value = object_field(prop, "value");
                if (!value || value->kind != JsonKind::Bool || value->bool_value)
                    fail("disabled CTest contract: " + name);
            }
        }
    }
    if (names.empty()) fail("CTest inventory is empty");
    for (const auto& name : required_tests)
        if (!names.count(name)) fail("missing required live/RC CTest contract: " + name);
    return names;
}
std::string attribute(xmlNode* node, const char* name) {
    std::unique_ptr<xmlChar, decltype(xmlFree)> value(xmlGetNoNsProp(node, BAD_CAST name), xmlFree);
    return value ? reinterpret_cast<const char*>(value.get()) : "";
}
bool named(xmlNode* node, const char* name) {
    return node && node->type == XML_ELEMENT_NODE && !node->ns && xmlStrEqual(node->name, BAD_CAST name);
}
void verify_results(const fs::path& path, const std::set<std::string>& expected) {
    const auto text = read(path);
    if (text.size() > INT_MAX) fail("CTest JUnit document too large");
    std::unique_ptr<xmlDoc, decltype(&xmlFreeDoc)> doc(xmlReadMemory(text.data(), static_cast<int>(text.size()),
        nullptr, nullptr, XML_PARSE_NONET | XML_PARSE_NOERROR | XML_PARSE_NOWARNING), xmlFreeDoc);
    if (!doc || doc->intSubset || doc->extSubset) fail("invalid/DTD CTest JUnit document");
    auto* root = xmlDocGetRootElement(doc.get());
    if (!named(root, "testsuite") || attribute(root, "tests") != std::to_string(expected.size()) ||
        attribute(root, "failures") != "0" || attribute(root, "disabled") != "0")
        fail("CTest did not report the complete passing inventory");
    for (const auto* count : {"errors", "skipped"})
        if (!attribute(root, count).empty() && attribute(root, count) != "0")
            fail("CTest reported " + std::string(count));
    std::set<std::string> actual;
    for (auto* node = root->children; node; node = node->next) {
        if (!named(node, "testcase")) continue;
        const auto name = attribute(node, "name");
        if (attribute(node, "status") != "run" || !actual.insert(name).second)
            fail("CTest skipped or duplicated contract: " + name);
        for (auto* child = node->children; child; child = child->next)
            if (named(child, "failure") || named(child, "error") || named(child, "skipped"))
                fail("CTest contract did not pass: " + name);
    }
    if (actual != expected) fail("CTest result names differ from preflight inventory");
}
}  // namespace

std::optional<int> run_regression_command(int argc, char** argv) {
    if (argc < 2 || !argv || !owns(argc, argv)) return std::nullopt;
    fs::path logs;
    try {
        auto o = parse(argc, argv);
        if (o.help) { std::cout << help; return 0; }
        validate_build(o);
        if (!argv[0] || !*argv[0]) fail("missing invoking executable argv[0]");
        const auto self = executable(argv[0]);
        const auto ctest = executable(o.ctest);
        if (!o.kicad.empty()) o.kicad = executable(o.kicad).string();
        const auto parent = o.output.empty() ? fs::temp_directory_path() : fs::absolute(o.output);
        fs::create_directories(parent);
        auto pattern = (parent / "regression-XXXXXX").string();
        if (!::mkdtemp(pattern.data())) fail("cannot create regression log directory: " + std::string(std::strerror(errno)));
        logs = pattern;
        std::cout << "REGRESSION LOGS: " << logs.string() << '\n' << std::flush;
        std::vector<std::string> ctest_args{ctest.string(), "--test-dir", o.tests.string()};
        if (!o.config.empty()) ctest_args.insert(ctest_args.end(), {"--build-config", o.config});
        auto listing = ctest_args; listing.push_back("--show-only=json-v1");
        int code = spawn(listing, o.repo, logs, "00-inventory", std::min(o.timeout, Seconds{30}), false);
        if (code) { std::cerr << "REGRESSION FAIL at CTest inventory\n"; return code; }
        const auto tests = inventory(logs / "00-inventory.stdout");
        std::vector<std::string> common{"--repo", o.repo.string()};
        if (!o.project.empty()) common.insert(common.end(), {"--project", o.project});
        if (!o.kicad.empty()) common.insert(common.end(), {"--kicad-cli", o.kicad});
        for (const auto* stage : {"board", "selftest"}) {
            const bool board = std::string(stage) == "board";
            const std::string label = board ? "01-board" : "02-selftest";
            std::vector<std::string> args{self.string(), stage};
            args.insert(args.end(), common.begin(), common.end());
            args.insert(args.end(), {"--output", (logs / (board ? "board" : "selftest.txt")).string()});
            if (!board) args.push_back("--keep");
            std::cout << "\n==== " << (board ? "1/3 board — complete native pipeline" :
                "2/3 selftest — mutations + determinism") << " ====\n" << std::flush;
            code = spawn(args, o.repo, logs, label, o.timeout, true);
            if (code) { std::cerr << "REGRESSION FAIL at " << stage << " (exit " << code << ")\n"; return code; }
        }
        std::cout << "\n==== 3/3 CTest — all " << tests.size() << " native contracts, including RC smoke ====\n" << std::flush;
        ctest_args.insert(ctest_args.end(), {"--parallel", "1", "--stop-on-failure", "--output-on-failure",
            "--no-tests=error", "--timeout", std::to_string(o.timeout.count()),
            "--output-junit", (logs / "ctest-results.xml").string()});
        code = spawn(ctest_args, o.repo, logs, "03-ctest", o.timeout, true);
        if (code) { std::cerr << "REGRESSION FAIL at CTest (exit " << code << ")\n"; return code; }
        verify_results(logs / "ctest-results.xml", tests);
        write(logs / "result.txt", "PASS\ncontracts=" + std::to_string(tests.size()) + "\n");
        std::cout << "REGRESSION PASS — native board + selftest + all " << tests.size()
                  << " CTest contracts (including RC smoke) passed.\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "REGRESSION FAIL: " << error.what();
        if (!logs.empty()) std::cerr << " (logs retained: " << logs.string() << ')';
        std::cerr << '\n'; return 2;
    }
}
}  // namespace schgen
