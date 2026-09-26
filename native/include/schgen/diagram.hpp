#pragma once
#include "schgen/link.hpp"
#include <filesystem>

namespace schgen {
// Entire graph layout, routing, labels and SVG serialization run natively.
// Consume the existing native linker result; no catalog/interpreter/global state.
std::string render_block_diagram(const LinkResult &, const LinkSomNets &);
std::filesystem::path write_block_diagram(const LinkResult &, const LinkSomNets &,
                                          const std::filesystem::path &out);
} // namespace schgen
