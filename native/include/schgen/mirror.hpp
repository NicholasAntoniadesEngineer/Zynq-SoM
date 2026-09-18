#pragma once

#include "schgen/sexpr.hpp"
#include <filesystem>
#include <stdexcept>

namespace schgen {
class MirrorUnsupported : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};
// Reflect footprint-local Y and local angles; do not swap copper layers.
// Unknown geometry fails closed. Failure leaves the caller's document intact.
void mirror_footprint(Sexpr& document);
Sexpr mirrored_footprint(const Sexpr& document);
// Re-read the explicit source on every invocation; never return stale geometry
// from a process-global path cache. Skip publication when bytes are unchanged.
std::filesystem::path write_mirrored_footprint(const std::filesystem::path& source,
                                             const std::filesystem::path& output_directory);
}  // namespace schgen
