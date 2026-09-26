#pragma once

#include <filesystem>
#include <string>
#include <vector>

namespace schgen {
struct SubsystemScaffoldFile {
    std::string name;
    std::string contents;
};
struct SubsystemScaffold {
    std::string name;
    std::vector<SubsystemScaffoldFile> files;
};
struct PublishedSubsystemScaffold {
    std::filesystem::path package;
    std::vector<std::string> files;
    bool directory_synced = false;
};

// Pure rendering. Portable package names: [a-z][a-z0-9_]*, at most 63
// characters, no double underscores or reserved DOS device names.
SubsystemScaffold render_subsystem_scaffold(const std::string& name);

// EXPLICIT source publication, never invoked by rendering, checks, or builds.
// library_root must already be a directory, not a symlink. Stage privately in
// that directory, then atomically publish with a no-replace rename. Every
// existing destination (including empty directories and dangling symlinks)
// is a collision. There is deliberately NO force/overwrite option. Concurrent
// publishers have exactly one winner. No existing source/registry is edited.
// Darwin/Linux only: unsupported no-replace platforms fail closed.
PublishedSubsystemScaffold scaffold_subsystem(const std::filesystem::path& library_root,
                                              const std::string& name);
std::string subsystem_scaffold_summary(const PublishedSubsystemScaffold& result);
} // namespace schgen
