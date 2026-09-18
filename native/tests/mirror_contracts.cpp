#include "schgen/mirror.hpp"
#include "schgen/json.hpp"
#include "schgen/atomic_file.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <unistd.h>

namespace {
std::size_t checks = 0;
void require(bool value, const std::string& message) {
    ++checks;
    if (!value) throw std::runtime_error(message);
}
std::string field(const schgen::JsonNode& row, const std::string& key) {
    const auto* value = schgen::object_field(row, key);
    require(value && value->kind == schgen::JsonKind::String, "missing fixture field " + key);
    return value->string_value;
}
std::string read(const std::filesystem::path& path) {
    std::ifstream input(path);
    require(bool(input), "cannot read " + path.string());
    return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}
void write(const std::filesystem::path& path, const std::string& text) {
    schgen::write_atomic_file(path.string(), {text.begin(), text.end()});
}
struct Temp {
    std::filesystem::path path;
    Temp() {
        auto pattern = (std::filesystem::temp_directory_path() / "schgen_mirror_XXXXXX").string();
        if (!mkdtemp(pattern.data())) throw std::runtime_error("mkdtemp failed");
        path = pattern;
    }
    ~Temp() { std::error_code error; std::filesystem::remove_all(path, error); }
};
}
int main(int argc, char** argv) {
    using namespace schgen;
    try {
        require(argc == 2, "usage: mirror_contracts FIXTURE_DIRECTORY");
        const auto rows = parse_json_file((std::filesystem::path(argv[1]) / "real_parts.json").string());
        for (const auto& row : rows.array_value) {
            auto doc = sexpr_loads(field(row, "source"));
            const auto name = field(row, "name"), original = sexpr_dumps(doc);
            const auto mirrored = mirrored_footprint(doc);
            require(sexpr_dumps(doc) == original, "pure mirror mutated input " + name);
            require(sexpr_dumps(mirrored) == field(row, "expected"), "frozen Python mirror differs " + name);
            mirror_footprint(doc);
            require(sexpr_dumps(doc) == sexpr_dumps(mirrored), "in-place mirror differs " + name);
            mirror_footprint(doc);
            require(sexpr_dumps(doc) == field(row, "normalized"), "mirror involution differs " + name);
        }
        const std::string input = R"((footprint "asym" (layer "F.Cu")
          (property "Reference" "X" (at 1.5 -2 45) (layer "F.SilkS"))
          (fp_line (start -2 -1) (end 3 4))
          (fp_arc (start 1 2) (mid 3 4) (end 5 6))
          (fp_poly (pts (xy 1 2) (xy 3 -4)))
          (pad "1" smd custom (at 2 -3 90) (size 1 2) (layers "F.Cu")
            (options (clearance outline))
            (primitives (gr_line (start 1 2) (end 3 4))
                        (gr_rect (start 1 2) (end 3 4))
                        (gr_circle (center 1 2) (end 3 4))
                        (gr_arc (start 1 2) (mid 3 4) (end 5 6))
                        (gr_poly (pts (xy 1 2) (xy 3 -4)))))
          (model "keep.step" (offset (xyz 1 2 3)) (rotate (xyz 0 0 90)))))";
        const std::string expected = R"((footprint "asym" (layer "F.Cu")
          (property "Reference" "X" (at 1.5 2 -45) (layer "F.SilkS"))
          (fp_line (start -2 1) (end 3 -4))
          (fp_arc (start 1 -2) (mid 3 -4) (end 5 -6))
          (fp_poly (pts (xy 1 -2) (xy 3 4)))
          (pad "1" smd custom (at 2 3 -90) (size 1 2) (layers "F.Cu")
            (options (clearance outline))
            (primitives (gr_line (start 1 -2) (end 3 -4))
                        (gr_rect (start 1 -2) (end 3 -4))
                        (gr_circle (center 1 -2) (end 3 -4))
                        (gr_arc (start 1 -2) (mid 3 -4) (end 5 -6))
                        (gr_poly (pts (xy 1 -2) (xy 3 4)))))
          (model "keep.step" (offset (xyz 1 2 3)) (rotate (xyz 0 0 90)))))";
        require(sexpr_dumps(mirrored_footprint(sexpr_loads(input))) == sexpr_dumps(sexpr_loads(expected)),
                "pinned primitives/angles/layers/model transform differs");
        for (const auto& tail : std::vector<std::string>{
                 "(fp_text_box \"unknown\")", "(fp_arc (angle 45))",
                 "(pad \"1\" smd custom (primitives (gr_curve (pts (xy 0 0)))))",
                 "(pad \"1\" smd rect (chamfer top_left))", "(pad \"1\" smd rect (chamfer_ratio 0.2))",
                 "(pad \"1\" smd rect (rect_delta 1 2))", "(pad \"1\" smd rect (unknown 1))",
                 "(pad \"1\" thru_hole circle (drill 1 (offset 0.3 0)))"}) {
            auto doc = sexpr_loads("(footprint \"failure\" (fp_line (start 1 2) (end 3 4)) " + tail + ")");
            const auto original = sexpr_dumps(doc);
            bool failed = false;
            try { mirror_footprint(doc); } catch (const MirrorUnsupported&) { failed = true; }
            require(failed, "unsupported geometry accepted: " + tail);
            require(sexpr_dumps(doc) == original, "failed transform partly mutated caller input");
        }
        Temp temporary;
        const auto source = temporary.path / "test.pretty/asym.kicad_mod";
        write(source, input);
        const auto output = write_mirrored_footprint(source, temporary.path / ".mirrored_fp");
        require(output.filename() == "test__asym.kicad_mod", "mirror output naming changed");
        require(read(output) == sexpr_dumps(sexpr_loads(expected)) + "\n", "published bytes differ");
        const auto modified = std::filesystem::last_write_time(output);
        require(write_mirrored_footprint(source, output.parent_path()) == output, "repeat output path changed");
        require(std::filesystem::last_write_time(output) == modified, "identical bytes republished");
        write(source, "(footprint \"new\" (pad \"1\" smd circle (at 3 4) (size 1 1) (layers \"F.Cu\")))");
        write_mirrored_footprint(source, output.parent_path());
        require(read(output).find("(at 3 -4)") != std::string::npos, "source edit returned stale cached geometry");
        const auto prior = read(output);
        write(source, "(footprint \"bad\" (fp_text_box \"unsupported\"))");
        bool failed = false;
        try { write_mirrored_footprint(source, output.parent_path()); } catch (const MirrorUnsupported&) { failed = true; }
        require(failed && read(output) == prior, "failed transform replaced previous valid output");
        std::cout << "mirror contracts: " << checks << " checks passed\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
