#include "schgen/subsystem_scaffold.hpp"

#include <atomic>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <stdexcept>
#include <sys/stat.h>
#include <unistd.h>

#if defined(__APPLE__)
#include <stdio.h>
#elif defined(__linux__)
#include <sys/syscall.h>
#include <linux/fs.h>
#endif

namespace schgen {
namespace {
class Fd {
public:
    explicit Fd(int fd) : fd_(fd) {}
    ~Fd() { if (fd_ >= 0) ::close(fd_); }
    Fd(const Fd&) = delete;
    Fd& operator=(const Fd&) = delete;
    int get() const { return fd_; }
private:
    int fd_;
};
[[noreturn]] void fail(const std::string& message, int error = errno) {
    throw std::runtime_error(message + ": " + std::strerror(error));
}
struct Stage {
    int root;
    std::string name;
    Fd directory;
    std::vector<std::string> files;
    bool published = false;
    ~Stage() {
        if (published) return;
        for (const auto& file : files) ::unlinkat(directory.get(), file.c_str(), 0);
        struct stat owned{}, current{};
        if (::fstat(directory.get(), &owned) == 0 &&
            ::fstatat(root, name.c_str(), &current, AT_SYMLINK_NOFOLLOW) == 0 &&
            owned.st_dev == current.st_dev && owned.st_ino == current.st_ino)
            ::unlinkat(root, name.c_str(), AT_REMOVEDIR);
    }
};
int rename_exclusive(int root, const std::string& source, const std::string& destination) {
#if defined(__APPLE__)
    return ::renameatx_np(root, source.c_str(), root, destination.c_str(), RENAME_EXCL);
#elif defined(__linux__) && defined(SYS_renameat2)
    return static_cast<int>(::syscall(SYS_renameat2, root, source.c_str(), root,
                                      destination.c_str(), RENAME_NOREPLACE));
#else
    (void)root; (void)source; (void)destination;
    errno = ENOTSUP;
    return -1;
#endif
}
} // namespace

PublishedSubsystemScaffold scaffold_subsystem(const std::filesystem::path& library_root,
                                              const std::string& name) {
    const auto rendered = render_subsystem_scaffold(name); // validate before any I/O
    const auto root_path = library_root.lexically_normal();
    if (root_path.empty() || root_path.string().find('\0') != std::string::npos)
        throw std::invalid_argument("invalid subsystem library root");
    // Remove a trailing slash: open(.../link/, O_NOFOLLOW) could follow link.
    auto root_name = root_path;
    while (root_name != root_name.root_path() && root_name.filename().empty())
        root_name = root_name.parent_path();
    Fd root(::open(root_name.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC));
    if (root.get() < 0) fail("open existing subsystem library " + root_name.string());
    struct stat existing{};
    if (::fstatat(root.get(), name.c_str(), &existing, AT_SYMLINK_NOFOLLOW) == 0)
        throw std::runtime_error("subsystem " + name + " already exists; edit it explicitly in place");
    if (errno != ENOENT) fail("inspect subsystem destination " + name);

    static std::atomic<unsigned long long> sequence{0};
    std::string staging;
    for (unsigned attempt = 0; attempt != 1024; ++attempt) {
        staging = ".schgen-scaffold." + std::to_string(::getpid()) + "." +
                  std::to_string(sequence.fetch_add(1));
        if (::mkdirat(root.get(), staging.c_str(), 0700) == 0) break;
        if (errno != EEXIST) fail("create private subsystem staging directory");
        staging.clear();
    }
    if (staging.empty()) throw std::runtime_error("cannot allocate subsystem staging directory");
    const int stage_fd = ::openat(root.get(), staging.c_str(),
                                  O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (stage_fd < 0) {
        const int error = errno;
        ::unlinkat(root.get(), staging.c_str(), AT_REMOVEDIR);
        fail("open private subsystem staging directory", error);
    }
    Stage stage{root.get(), staging, Fd(stage_fd), {}, false};
    PublishedSubsystemScaffold result{root_name / name, {}, false};
    stage.files.reserve(rendered.files.size());
    result.files.reserve(rendered.files.size());
    for (const auto& file : rendered.files) {
        // Reserve cleanup ownership before file creation, including exceptions.
        stage.files.push_back(file.name);
        Fd output(::openat(stage.directory.get(), file.name.c_str(),
                          O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0644));
        if (output.get() < 0) fail("create scaffold file " + file.name);
        std::size_t written = 0;
        while (written < file.contents.size()) {
            const auto n = ::write(output.get(), file.contents.data() + written,
                                   file.contents.size() - written);
            if (n < 0 && errno == EINTR) continue;
            if (n <= 0) fail("write scaffold file " + file.name, n == 0 ? EIO : errno);
            written += static_cast<std::size_t>(n);
        }
        if (::fsync(output.get()) != 0) fail("sync scaffold file " + file.name);
        result.files.push_back(file.name);
    }
    if (::fchmod(stage.directory.get(), 0755) != 0 || ::fsync(stage.directory.get()) != 0)
        fail("sync scaffold directory");
    if (rename_exclusive(root.get(), staging, name) != 0) {
        const int error = errno;
        if (error == EEXIST || error == ENOTEMPTY)
            throw std::runtime_error("subsystem " + name + " already exists; no files replaced");
        fail("publish subsystem without replacement", error);
    }
    stage.published = true;
    // Publication already committed: never report an apparent rollback if
    // directory durability is unavailable on this filesystem.
    result.directory_synced = ::fsync(root.get()) == 0;
    return result;
}

std::string subsystem_scaffold_summary(const PublishedSubsystemScaffold& result) {
    const auto name = result.package.filename().string();
    std::string out = "scaffolded " + result.package.string() + " (";
    for (std::size_t i = 0; i < result.files.size(); ++i) {
        if (i) out += ", ";
        out += result.files[i];
    }
    out += ")\nnext: implement " + name + ".cpp; configure native with "
           "-DSCHGEN_SUBSYSTEM_PACKAGES=" + name +
           "; build schgen_subsystem_" + name + "_test and run native_subsystem_" + name +
           ". See the package README for metadata, registration, and catalog inputs.\n";
    if (!result.directory_synced)
        out += "warning: package published, but the parent directory could not be fsynced\n";
    return out;
}
} // namespace schgen
