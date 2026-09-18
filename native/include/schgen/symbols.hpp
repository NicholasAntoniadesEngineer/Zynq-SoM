#pragma once

#include "schgen/sexpr.hpp"

#include <array>
#include <filesystem>
#include <map>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace schgen {

inline constexpr double symbol_grid = 1.27;

class SymbolError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

struct SymbolPin {
    std::string number, name, etype;
    double x = 0.0, y = 0.0;
    int rotation = 0;
    double length = 2.54;
    bool hidden = false;
};

struct SymbolDef {
    std::string lib_id;
    Sexpr raw;  // Standalone symbol; extends resolved, suitable for embedding.
    std::vector<SymbolPin> pins;  // Python traversal order, including all units/styles.
    std::array<double, 4> body{};  // xmin, ymin, xmax, ymax in symbol coordinates.
    bool pin_names_hidden = false;
    bool pin_numbers_hidden = false;
};

// Extra paths win. KiCad install paths precede repository schgen/lib and parts,
// matching Python on macOS and supporting the usual Linux installs as well.
std::vector<std::filesystem::path> symbol_search_paths(
    const std::filesystem::path& repository_root,
    const std::vector<std::filesystem::path>& extra_paths = {});

// Immutable shared parse cache keyed by canonical path, nanosecond mtime, size.
// Existing Library instances remain snapshots, as in Python. New instances see
// edited files. Clear a Library to reload its definitions; clearing the shared
// file cache does not invalidate live Library definitions or returned pointers.
std::shared_ptr<const Sexpr> load_symbol_library_file(const std::filesystem::path& path);
void clear_symbol_file_cache();

class SymbolLibrary {
public:
    explicit SymbolLibrary(const std::filesystem::path& repository_root,
                           const std::vector<std::filesystem::path>& extra_paths = {});
    // Exact ordered paths, for callers with their own KiCad installation/config.
    explicit SymbolLibrary(std::vector<std::filesystem::path> search_paths);
    const std::vector<std::filesystem::path>& paths() const { return paths_; }
    const SymbolDef& get(const std::string& lib_id);
    std::set<std::string> pin_numbers(const std::string& lib_id);
    void clear();  // Invalidates references returned by get().

private:
    const Sexpr& library(const std::string& libname);
    Sexpr resolve(const std::string& libname, const std::string& name,
                  std::vector<std::string>& ancestry);
    std::vector<std::filesystem::path> paths_;
    std::map<std::string, std::shared_ptr<const Sexpr>> files_;
    std::map<std::string, SymbolDef> defs_;
};

// Parse an already standalone/flattened symbol. Rejects unresolved extends.
// Library::get additionally checks all pin positions against symbol_grid.
SymbolDef parse_symbol(const std::string& lib_id, const Sexpr& block);
bool symbol_on_grid(double value);
// Four decimal places, Python expression grouping (including noncardinal input).
std::pair<double, double> pin_page_position(const SymbolPin& pin, double anchor_x,
                                          double anchor_y, int rotation);
std::array<double, 4> symbol_body_box_page(const SymbolDef& symbol, double anchor_x,
                                          double anchor_y, int rotation);

}  // namespace schgen
