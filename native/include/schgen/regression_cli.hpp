#pragma once

#include <optional>

namespace schgen {
// Dispatch before run_project_command (also accepts leading --repo/--project).
// check --help describes the explicit CTest build and retained output boundary.
// Production always spawns the resolved argv[0] and real CTest, never a shell,
// interpreter, injected runner, cached verdict, or a selected subset of tests.
// nullopt: not this command; 2: invalid input/evidence; 124: child timeout;
// 126/127: launch failure; ordinary child status or 128+signal: fail-fast.
std::optional<int> run_regression_command(int argc, char** argv);
}  // namespace schgen
