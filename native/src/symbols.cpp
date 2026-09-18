#include "schgen/symbols.hpp"

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

#include "schgen/occupancy.hpp"
#include "schgen/turn.hpp"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <fstream>
#include <iterator>
#include <mutex>
#include <sstream>
#include <tuple>

namespace schgen {
namespace {
namespace fs = std::filesystem;
using FileKey = std::tuple<std::string, fs::file_time_type, std::uintmax_t>;
std::map<FileKey, std::shared_ptr<const Sexpr>> file_cache;
std::mutex file_cache_mutex;

const SexprList& items(const Sexpr& node, const std::string& where) {
    const auto* result = std::get_if<SexprList>(&node.v);
    if (!result) throw SymbolError(where + ": expected s-expression list");
    return *result;
}

std::string tag(const Sexpr& node) {
    const auto* list = std::get_if<SexprList>(&node.v);
    if (!list || list->empty()) return {};
    const auto* value = std::get_if<Sexpr::Sym>(&list->front().v);
    return value ? value->name : std::string{};
}

const Sexpr* find(const Sexpr& node, const std::string& name) {
    for (const auto& child : items(node, name)) {
        if (tag(child) == name) return &child;
    }
    return nullptr;
}

std::string atom(const Sexpr& node, const std::string& where) {
    if (const auto* value = std::get_if<std::string>(&node.v)) return *value;
    if (const auto* value = std::get_if<Sexpr::Sym>(&node.v)) return value->name;
    if (const auto* value = std::get_if<double>(&node.v)) {
        if (*value == std::trunc(*value)) return sexpr_fmt_num(*value);
        // Numeric pin/name atoms use Python str(), not the geometry serializer's
        // lossy six-decimal formatting. Keep their shortest round-trip spelling.
        char buffer[128];
        const auto converted = std::to_chars(std::begin(buffer), std::end(buffer), *value);
        if (converted.ec != std::errc{}) throw SymbolError(where + ": numeric atom conversion failed");
        return {buffer, converted.ptr};
    }
    if (const auto* value = std::get_if<bool>(&node.v)) return *value ? "True" : "False";
    throw SymbolError(where + ": expected atom");
}

double number(const Sexpr& node, const std::string& where) {
    double result;
    if (const auto* value = std::get_if<double>(&node.v)) {
        // sexpr._from_tagged converts integral numeric atoms to Python ints,
        // including -0.0. Quoted "-0.0" below retains its floating sign.
        result = *value == 0.0 ? 0.0 : *value;
    } else {
        const auto text = atom(node, where);
        try {
            std::size_t count = 0;
            result = std::stod(text, &count);
            if (count != text.size()) throw SymbolError(where + ": expected number");
        } catch (const std::invalid_argument&) {
            throw SymbolError(where + ": expected number");
        } catch (const std::out_of_range&) {
            throw SymbolError(where + ": number out of range");
        }
    }
    if (!std::isfinite(result)) throw SymbolError(where + ": number must be finite");
    return result;
}

const Sexpr& at(const Sexpr& node, std::size_t index, const std::string& where) {
    const auto& list = items(node, where);
    if (index >= list.size()) throw SymbolError(where + ": missing coordinate or value");
    return list[index];
}

bool has_hide_atom(const Sexpr& node) {
    for (const auto& child : items(node, "hide")) {
        if (const auto* value = std::get_if<Sexpr::Sym>(&child.v)) {
            if (value->name == "hide") return true;
        }
        // Python Sym derives from str, so membership also matches "hide".
        if (const auto* value = std::get_if<std::string>(&child.v)) {
            if (*value == "hide") return true;
        }
    }
    return false;
}

bool display_hidden(const Sexpr* node) {
    // Python treats any (hide ...) list as true at symbol level, even (hide no).
    return node && (find(*node, "hide") || has_hide_atom(*node));
}

void replace_strings(Sexpr& node, const std::string& old, const std::string& replacement) {
    if (auto* list = std::get_if<SexprList>(&node.v)) {
        for (auto& child : *list) replace_strings(child, old, replacement);
    } else if (auto* value = std::get_if<std::string>(&node.v)) {
        std::size_t offset = 0;
        while ((offset = value->find(old, offset)) != std::string::npos) {
            value->replace(offset, old.size(), replacement);
            offset += replacement.size();
        }
    }
    // Bare Sym atoms are deliberately never replaced (same as _clone_replace).
}

void rename_units(Sexpr& node, const std::string& parent, const std::string& child) {
    for (auto& entry : std::get<SexprList>(node.v)) {
        if (tag(entry) != "symbol") continue;
        auto& unit = std::get<SexprList>(entry.v);
        if (unit.size() < 2 || !std::holds_alternative<std::string>(unit[1].v)) {
            throw SymbolError(child + ": malformed inherited unit name");
        }
        auto& name = std::get<std::string>(unit[1].v);
        if (name.compare(0, parent.size() + 1, parent + "_") == 0) {
            name.replace(0, parent.size(), child);
        }
        rename_units(entry, parent, child);
    }
}

Sexpr flatten(Sexpr parent, const Sexpr& child, const std::string& name) {
    auto& output = std::get<SexprList>(parent.v);
    const auto parent_name = atom(at(parent, 1, name), name);
    output[1] = Sexpr{name};
    rename_units(parent, parent_name, name);
    // KiCad derived symbols share the root's drawings and pins. Properties are
    // overridden by key, retaining inherited property order and extra fields.
    // https://dev-docs.kicad.org/en/file-formats/sexpr-intro/index.html#_symbols
    const std::set<std::string> drawing_tags{
        "symbol", "pin", "rectangle", "polyline", "circle", "arc", "curve", "bezier",
        "text", "text_box"};
    for (std::size_t i = 2; i < items(child, name).size(); ++i) {
        const auto& value = items(child, name)[i];
        const auto key = tag(value);
        if (key == "extends") continue;
        if (drawing_tags.count(key)) {
            throw SymbolError(name + ": derived symbol cannot override pins or graphics");
        }
        if (key.empty()) throw SymbolError(name + ": malformed derived symbol entry");
        const auto property = key == "property" ? atom(at(value, 1, name), name) : "";
        auto found = std::find_if(output.begin() + 2, output.end(), [&](const Sexpr& item) {
            return tag(item) == key && (key != "property"
                || atom(at(item, 1, name), name) == property);
        });
        if (found != output.end()) *found = value;
        else output.push_back(value);
    }
    return parent;
}

struct SymbolParser {
    SymbolDef result;
    std::vector<double> xs, ys;

    void point(double x, double y) {
        if (!std::isfinite(x) || !std::isfinite(y)) {
            throw SymbolError(result.lib_id + ": geometry must be finite");
        }
        xs.push_back(x);
        ys.push_back(y);
    }

    void coordinate(const Sexpr* value) {
        if (value) point(number(at(*value, 1, result.lib_id), result.lib_id),
                         number(at(*value, 2, result.lib_id), result.lib_id));
    }

    void pin(const Sexpr& value) {
        const auto& list = items(value, result.lib_id);
        const auto* position = find(value, "at");
        const auto* length = find(value, "length");
        const auto* name = find(value, "name");
        const auto* num = find(value, "number");
        const auto* hidden = find(value, "hide");
        SymbolPin out;
        out.number = num && items(*num, result.lib_id).size() > 1
            ? atom(at(*num, 1, result.lib_id), result.lib_id) : "";
        out.name = name && items(*name, result.lib_id).size() > 1
            ? atom(at(*name, 1, result.lib_id), result.lib_id) : "";
        out.etype = list.size() > 1 ? atom(list[1], result.lib_id) : "passive";
        if (position) {
            out.x = number(at(*position, 1, result.lib_id), result.lib_id);
            out.y = number(at(*position, 2, result.lib_id), result.lib_id);
            if (items(*position, result.lib_id).size() > 3) {
                const auto angle = number(at(*position, 3, result.lib_id), result.lib_id);
                const int wrapped = static_cast<int>(std::fmod(std::trunc(angle), 360.0));
                out.rotation = wrapped < 0 ? wrapped + 360 : wrapped;
            }
        }
        if (length && items(*length, result.lib_id).size() > 1) {
            out.length = number(at(*length, 1, result.lib_id), result.lib_id);
        }
        out.hidden = has_hide_atom(value) || (hidden && items(*hidden, result.lib_id).size() > 1
            && atom(at(*hidden, 1, result.lib_id), result.lib_id) == "yes");
        result.pins.push_back(std::move(out));
    }

    void walk(const Sexpr& node) {
        // Match Python's children-first traversal, followed by local pins and
        // drawing types. Do not deduplicate pins from common/alternate units.
        for (const auto& value : items(node, result.lib_id)) {
            if (tag(value) == "symbol") walk(value);
        }
        for (const auto& value : items(node, result.lib_id)) {
            if (tag(value) == "pin") pin(value);
        }
        for (const auto* drawing : {"rectangle", "polyline", "circle", "arc"}) {
            for (const auto& value : items(node, result.lib_id)) {
                const auto kind = tag(value);
                if (kind != drawing) continue;
                if (kind == "rectangle") {
                    coordinate(find(value, "start"));
                    coordinate(find(value, "end"));
                } else if (kind == "polyline") {
                    if (const auto* points = find(value, "pts")) {
                        for (const auto& xy : items(*points, result.lib_id)) {
                            if (tag(xy) == "xy") coordinate(&xy);
                        }
                    }
                } else if (kind == "circle") {
                    const auto* center = find(value, "center");
                    const auto* radius = find(value, "radius");
                    if (center && radius) {
                        const double x = number(at(*center, 1, result.lib_id), result.lib_id);
                        const double y = number(at(*center, 2, result.lib_id), result.lib_id);
                        const double r = number(at(*radius, 1, result.lib_id), result.lib_id);
                        point(x - r, y - r);
                        point(x + r, y + r);
                    }
                } else if (kind == "arc") {
                    // The authoring baseline uses these three points, not analytical
                    // arc extrema. Expanding that box would change placement.
                    for (const auto* key : {"start", "mid", "end"}) coordinate(find(value, key));
                }
            }
        }
    }
};
}  // namespace

std::vector<fs::path> symbol_search_paths(const fs::path& repo,
                                         const std::vector<fs::path>& extra) {
    auto result = extra;
    result.emplace_back("/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols");
    result.emplace_back("/usr/share/kicad/symbols");
    result.emplace_back("/usr/local/share/kicad/symbols");
    result.push_back(repo / "schgen/lib");
    result.push_back(repo / "parts");
    return result;
}

std::shared_ptr<const Sexpr> load_symbol_library_file(const fs::path& path) {
    try {
        const auto real_path = fs::canonical(path);
        const FileKey key{real_path.string(), fs::last_write_time(real_path), fs::file_size(real_path)};
        std::lock_guard<std::mutex> lock(file_cache_mutex);
        if (const auto found = file_cache.find(key); found != file_cache.end()) return found->second;
        std::ifstream stream(real_path, std::ios::binary);
        if (!stream) throw SymbolError("cannot read symbol library " + path.string());
        const std::string text{std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
        if (stream.bad()) throw SymbolError("cannot read symbol library " + path.string());
        auto root = std::make_shared<const Sexpr>(sexpr_loads(text));
        if (tag(*root) != "kicad_symbol_lib") {
            throw SymbolError("expected kicad_symbol_lib: " + path.string());
        }
        if (fs::last_write_time(real_path) != std::get<1>(key)
            || fs::file_size(real_path) != std::get<2>(key)) {
            throw SymbolError("symbol library changed while reading: " + path.string());
        }
        // Bound cache history to one version per path; existing readers retain
        // their immutable shared snapshots until they clear or are destroyed.
        for (auto it = file_cache.begin(); it != file_cache.end();) {
            if (std::get<0>(it->first) == real_path.string()) it = file_cache.erase(it);
            else ++it;
        }
        file_cache.emplace(key, root);
        return root;
    } catch (const SymbolError&) { throw; }
    catch (const std::exception& error) {
        throw SymbolError("symbol library " + path.string() + ": " + error.what());
    }
}

void clear_symbol_file_cache() {
    std::lock_guard<std::mutex> lock(file_cache_mutex);
    file_cache.clear();
}

SymbolLibrary::SymbolLibrary(const fs::path& repo, const std::vector<fs::path>& extra)
    : paths_(symbol_search_paths(repo, extra)) {}

SymbolLibrary::SymbolLibrary(std::vector<fs::path> paths) : paths_(std::move(paths)) {}

const Sexpr& SymbolLibrary::library(const std::string& name) {
    if (const auto found = files_.find(name); found != files_.end()) return *found->second;
    for (const auto& base : paths_) {
        for (const auto& path : {base / (name + ".kicad_sym"), base / name / (name + ".kicad_sym")}) {
            if (fs::exists(path)) {
                auto root = load_symbol_library_file(path);
                return *files_.emplace(name, std::move(root)).first->second;
            }
        }
    }
    std::ostringstream message;
    message << "library '" << name << "' not found in [";
    for (std::size_t i = 0; i < paths_.size(); ++i) {
        message << (i ? ", " : "") << paths_[i].string();
    }
    throw SymbolError(message.str() + "]");
}

Sexpr SymbolLibrary::resolve(const std::string& lib, const std::string& name,
                             std::vector<std::string>& ancestry) {
    if (std::find(ancestry.begin(), ancestry.end(), name) != ancestry.end()
        || ancestry.size() >= 256) {
        std::string chain;
        for (const auto& entry : ancestry) chain += entry + " -> ";
        throw SymbolError(lib + ": inheritance cycle or excessive depth: " + chain + name);
    }
    const auto& root = library(lib);
    const Sexpr* block = nullptr;
    for (const auto& value : items(root, lib)) {
        if (tag(value) == "symbol" && items(value, lib).size() > 1
            && atom(at(value, 1, lib), lib) == name) {
            block = &value;
            break;
        }
    }
    if (!block && lib == "schgen" && !name.empty() && name.front() == '+') {
        for (const auto& value : items(root, lib)) {
            if (tag(value) == "symbol" && items(value, lib).size() > 1
                && atom(at(value, 1, lib), lib) == "+5V_USB") {
                ancestry.push_back(name);
                auto out = resolve(lib, "+5V_USB", ancestry);
                ancestry.pop_back();
                replace_strings(out, "+5V_USB", name);
                return out;
            }
        }
        throw SymbolError("rail template '+5V_USB' missing from schgen lib");
    }
    if (!block) throw SymbolError("symbol '" + name + "' not in " + lib);
    const auto* base = find(*block, "extends");
    if (!base) return *block;
    const auto parent = atom(at(*base, 1, lib + ":" + name), lib + ":" + name);
    ancestry.push_back(name);
    auto resolved = resolve(lib, parent, ancestry);
    ancestry.pop_back();
    return flatten(std::move(resolved), *block, name);
}

const SymbolDef& SymbolLibrary::get(const std::string& lib_id) {
    if (const auto found = defs_.find(lib_id); found != defs_.end()) return found->second;
    const auto colon = lib_id.find(':');
    const auto lib = lib_id.substr(0, colon);
    const auto name = colon == std::string::npos ? "" : lib_id.substr(colon + 1);
    try {
        std::vector<std::string> ancestry;
        auto result = parse_symbol(lib_id, resolve(lib, name, ancestry));
        for (const auto& pin : result.pins) {
            if (!symbol_on_grid(pin.x) || !symbol_on_grid(pin.y)) {
                throw SymbolError(lib_id + " pin " + pin.number + " at ("
                    + sexpr_fmt_num(pin.x) + "," + sexpr_fmt_num(pin.y)
                    + ") is OFF-GRID — fix the symbol; schgen never lands wires off-grid");
            }
        }
        return defs_.emplace(lib_id, std::move(result)).first->second;
    } catch (const SymbolError&) { throw; }
    catch (const std::exception& error) {
        throw SymbolError(lib_id + ": " + error.what());
    }
}

std::set<std::string> SymbolLibrary::pin_numbers(const std::string& lib_id) {
    std::set<std::string> result;
    for (const auto& pin : get(lib_id).pins) result.insert(pin.number);
    return result;
}

void SymbolLibrary::clear() {
    defs_.clear();
    files_.clear();
}

SymbolDef parse_symbol(const std::string& lib_id, const Sexpr& block) {
    if (tag(block) != "symbol") throw SymbolError(lib_id + ": expected symbol block");
    if (find(block, "extends")) throw SymbolError(lib_id + ": unresolved extends; use SymbolLibrary");
    SymbolParser parser;
    parser.result.lib_id = lib_id;
    parser.result.raw = block;
    parser.result.pin_names_hidden = display_hidden(find(block, "pin_names"));
    parser.result.pin_numbers_hidden = display_hidden(find(block, "pin_numbers"));
    parser.walk(block);
    if (parser.xs.empty()) {
        for (const auto& pin : parser.result.pins) parser.point(pin.x, pin.y);
        if (parser.xs.empty()) parser.point(0.0, 0.0);
    }
    parser.result.body = {*std::min_element(parser.xs.begin(), parser.xs.end()),
                          *std::min_element(parser.ys.begin(), parser.ys.end()),
                          *std::max_element(parser.xs.begin(), parser.xs.end()),
                          *std::max_element(parser.ys.begin(), parser.ys.end())};
    return std::move(parser.result);
}

bool symbol_on_grid(double value) {
    if (!std::isfinite(value)) return false;
    return std::fabs(value / symbol_grid - py_round(value / symbol_grid, 0)) < 1e-4;
}

std::pair<double, double> pin_page_position(const SymbolPin& pin, double ax, double ay, int rot) {
    int angle = rot % 360;
    if (angle < 0) angle += 360;
    const double rad = static_cast<double>(angle) * (3.141592653589793 / 180.0);
    const double c = py_round(std::cos(rad), 0);
    const double s = py_round(std::sin(rad), 0);
    // Keep the authoring transform's parentheses. Adding the anchor before
    // subtracting the rotated y term changes half-way rounding for e.g. -30°.
    const double local_x = pin.x * c - pin.y * s;
    const double local_y = -pin.x * s - pin.y * c;
    return {py_round(ax + local_x, 4), py_round(ay + local_y, 4)};
}

std::array<double, 4> symbol_body_box_page(const SymbolDef& symbol, double ax, double ay, int rot) {
    std::array<double, 4> out{};
    bool first = true;
    for (const double x : {symbol.body[0], symbol.body[2]}) {
        for (const double y : {symbol.body[1], symbol.body[3]}) {
            const auto point = sch_xform(x, y, ax, ay, rot);
            if (first) {
                out = {point.first, point.second, point.first, point.second};
                first = false;
            } else {
                out[0] = std::min(out[0], point.first);
                out[1] = std::min(out[1], point.second);
                out[2] = std::max(out[2], point.first);
                out[3] = std::max(out[3], point.second);
            }
        }
    }
    return out;
}

}  // namespace schgen
