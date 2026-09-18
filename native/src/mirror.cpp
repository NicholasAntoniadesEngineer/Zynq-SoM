#include "schgen/mirror.hpp"
#include "schgen/atomic_file.hpp"

#include <fstream>
#include <iterator>
#include <set>

namespace schgen {
namespace {
std::string head(const Sexpr& node) {
    const auto* list = std::get_if<SexprList>(&node.v);
    if (!list || list->empty()) return {};
    const auto* sym = std::get_if<Sexpr::Sym>(&list->front().v);
    return sym ? sym->name : std::string{};
}
std::string atom(const Sexpr& node) {
    if (const auto* s = std::get_if<std::string>(&node.v)) return *s;
    if (const auto* s = std::get_if<Sexpr::Sym>(&node.v)) return s->name;
    return sexpr_dumps(node);
}
std::string repr(const std::string& value) {
    const char q = value.find('\'') != std::string::npos && value.find('"') == std::string::npos ? '"' : '\'';
    std::string out(1, q);
    for (char c : value) {
        if (c == q || c == '\\') out += '\\';
        if (c == '\n') out += "\\n";
        else if (c == '\r') out += "\\r";
        else if (c == '\t') out += "\\t";
        else out += c;
    }
    return out + q;
}
Sexpr* find(Sexpr& node, const std::string& tag) {
    auto* list = std::get_if<SexprList>(&node.v);
    if (list) for (auto& item : *list) if (head(item) == tag) return &item;
    return nullptr;
}
void negate(Sexpr& node, std::size_t index, bool required = false) {
    auto& list = std::get<SexprList>(node.v);
    if (index >= list.size()) return;
    if (auto* value = std::get_if<double>(&list[index].v)) *value = 0.0 - *value;
    else if (auto* value = std::get_if<bool>(&list[index].v)) list[index].v = *value ? -1.0 : 0.0;
    else if (required) throw MirrorUnsupported("mirror coordinate must be numeric");
}
void points(Sexpr& node) {
    for (auto& item : std::get<SexprList>(node.v)) if (head(item) == "xy") negate(item, 2, true);
}
void fields(Sexpr& node, bool at) {
    const auto h = head(node);
    if (at ? h == "at" : h == "start" || h == "end" || h == "mid" || h == "center") {
        negate(node, 2);
        if (at) negate(node, 3);
    }
}
void primitive(Sexpr& node, const std::string& context) {
    const auto h = head(node);
    if (h == "gr_line" || h == "gr_rect" || h == "gr_circle" || h == "gr_arc") {
        for (auto& item : std::get<SexprList>(node.v)) fields(item, false);
    } else if (h == "gr_poly") {
        if (auto* pts = find(node, "pts")) points(*pts);
    } else throw MirrorUnsupported(context + ": custom-pad primitive " + repr(h) + " has no proven mirror rule");
}
void pad(Sexpr& node, const std::string& context) {
    static const std::set<std::string> plain{
        "size", "layers", "roundrect_rratio", "net", "uuid", "pinfunction", "pintype",
        "solder_mask_margin", "solder_paste_margin", "solder_paste_margin_ratio", "clearance",
        "zone_connect", "thermal_bridge_width", "thermal_bridge_angle", "thermal_gap", "die_length",
        "remove_unused_layers", "keep_end_layers", "property", "zone_layer_connections"};
    for (auto& item : std::get<SexprList>(node.v)) {
        const auto h = head(item);
        if (h.empty()) continue;
        if (h == "at") fields(item, true);
        else if (h == "drill") {
            if (find(item, "offset")) throw MirrorUnsupported(context + ": pad drill (offset ...) has no proven mirror rule — pin it against a pcbnew flip before allowing it");
        } else if (h == "options") continue;
        else if (h == "primitives") {
            for (auto& p : std::get<SexprList>(item.v)) if (!head(p).empty()) primitive(p, context);
        } else if (h == "chamfer" || h == "chamfer_ratio" || h == "rect_delta")
            throw MirrorUnsupported(context + ": pad " + repr(h) + " has no proven mirror rule (corner remap unproven) — pin it against a pcbnew flip first");
        else if (!plain.count(h)) throw MirrorUnsupported(context + ": pad child " + repr(h) + " is not in the proven mirror set");
    }
}
void transform(Sexpr& doc) {
    if (head(doc) != "footprint") throw MirrorUnsupported("mirror_fp_doc wants a parsed (footprint ...) document");
    auto& list = std::get<SexprList>(doc.v);
    const auto name = list.size() > 1 ? atom(list[1]) : "?";
    static const std::set<std::string> plain{
        "version", "generator", "generator_version", "layer", "descr", "tags", "attr", "model",
        "solder_mask_margin", "solder_paste_margin", "solder_paste_ratio", "solder_paste_margin_ratio",
        "clearance", "autoplace_cost90", "autoplace_cost180", "net_tie_pad_groups", "private_layers",
        "embedded_fonts", "uuid", "path", "sheetname", "sheetfile", "zone_connect",
        "thermal_bridge_width", "thermal_gap", "duplicate_pad_numbers_are_jumpers", "jumper_pad_groups"};
    for (auto& node : list) {
        const auto h = head(node);
        if (h.empty()) continue;
        if (h == "pad") {
            const auto& p = std::get<SexprList>(node.v);
            pad(node, name + " pad " + (p.size() > 1 ? atom(p[1]) : "?"));
        } else if (h == "fp_text" || h == "property") {
            for (auto& item : std::get<SexprList>(node.v)) fields(item, true);
        } else if (h == "fp_line" || h == "fp_rect" || h == "fp_circle" || h == "fp_arc") {
            if (h == "fp_arc" && find(node, "angle")) throw MirrorUnsupported(name + ": legacy fp_arc (angle) form has no proven mirror rule");
            for (auto& item : std::get<SexprList>(node.v)) fields(item, false);
        } else if (h == "fp_poly") {
            if (auto* pts = find(node, "pts")) points(*pts);
        } else if (!plain.count(h)) throw MirrorUnsupported(name + ": footprint child " + repr(h) + " is not in the proven mirror set — pin its transform against a pcbnew flip before allowing it");
    }
}
std::string read(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) throw MirrorUnsupported("cannot read footprint: " + path.string());
    std::string text{std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
    if (stream.bad()) throw MirrorUnsupported("cannot read footprint: " + path.string());
    return text;
}
}
Sexpr mirrored_footprint(const Sexpr& document) { auto copy = document; transform(copy); return copy; }
void mirror_footprint(Sexpr& document) { document = mirrored_footprint(document); }
std::filesystem::path write_mirrored_footprint(const std::filesystem::path& source,
                                             const std::filesystem::path& directory) {
    auto document = sexpr_loads(read(source));
    mirror_footprint(document);
    auto library = source.parent_path().filename().string();
    if (library.size() >= 7 && library.compare(library.size() - 7, 7, ".pretty") == 0) library.resize(library.size() - 7);
    const auto output = directory / (library + "__" + source.stem().string() + ".kicad_mod");
    const auto text = sexpr_dumps(document) + "\n";
    if (!std::filesystem::exists(output) || read(output) != text)
        write_atomic_file(output.string(), {text.begin(), text.end()});
    return output;
}
}  // namespace schgen
