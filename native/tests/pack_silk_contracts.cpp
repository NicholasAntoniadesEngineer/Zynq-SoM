#include "schgen/json.hpp"
#include "schgen/pack.hpp"

#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>

using namespace schgen;
namespace {
template<class F> void must_reject(F action) {
    bool rejected = false;
    try { action(); } catch (const std::exception&) { rejected = true; }
    if (!rejected) throw std::runtime_error("invalid silk index input accepted");
}
void index_boundaries() {
    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double inf = std::numeric_limits<double>::infinity();
    for (double cell : {0.0, -0.0, -1.0, nan, inf, -inf})
        must_reject([&] { SilkBoxIndex index(cell); });
    SilkBoxIndex index(1.0);
    const Box4 valid{0.0, 0.0, 1.0, 1.0};
    index.add(valid);
    for (const auto& invalid : std::vector<Box4>{
        {nan, 0, 1, 1}, {0, 0, inf, 1}, {-inf, 0, 1, 1},
        {2, 0, 1, 1}, {0, 2, 1, 1},
        {1e100, 0, 1e100, 1}, {-1e100, 0, -1e100, 1}}) {
        must_reject([&] { index.add(invalid); });
        must_reject([&] { (void)index.hits(invalid); });
        must_reject([&] { (void)index.pen(invalid); });
        if (index.boxes().size() != 1 || index.pen(valid) != 1.0)
            throw std::runtime_error("rejected box mutated silk index");
    }
    for (double cell : {static_cast<double>(std::numeric_limits<int>::min()),
                        static_cast<double>(std::numeric_limits<int>::max())}) {
        SilkBoxIndex boundary(1.0);
        const Box4 box{cell, cell, cell + 0.5, cell + 0.5};
        boundary.add(box);
        if (!boundary.hits(box) || boundary.pen(box) != 0.25)
            throw std::runtime_error("representable extreme silk cell lost");
    }
    SilkBoxIndex upper(1.0);
    const double maximum = std::numeric_limits<int>::max();
    const Box4 wide{maximum - 1, maximum - 1, maximum + 0.5, maximum + 0.5};
    upper.add(wide);
    if (upper.pen(wide) != 2.25)
        throw std::runtime_error("multi-cell extreme query lost or duplicated box");
    SilkBoxIndex tiny(std::numeric_limits<double>::denorm_min());
    must_reject([&] { tiny.add(valid); });
    if (!tiny.boxes().empty()) throw std::runtime_error("overflowed division inserted box");
}
const JsonNode &field(const JsonNode &n, const std::string &key) {
    const auto *v = object_field(n, key);
    if (!v)
        throw std::runtime_error("missing field " + key);
    return *v;
}
double number(const JsonNode &n, const std::string &key) {
    const auto &v = field(n, key);
    if (v.kind != JsonKind::Number || !std::isfinite(v.number_value))
        throw std::runtime_error("expected finite number " + key);
    return v.number_value;
}
Box4 box(const JsonNode &n) {
    const auto &a = n.array_value;
    if (a.size() != 4)
        throw std::runtime_error("box must contain four coordinates");
    return {a[0].number_value, a[1].number_value, a[2].number_value, a[3].number_value};
}
SilkBoxIndex index(const JsonNode &rows) {
    SilkBoxIndex result(8.0);
    for (const auto &row : rows.array_value)
        result.add(box(row));
    return result;
}
std::vector<double> values(Box4 b) { return {b.x0, b.y0, b.x1, b.y1}; }
std::vector<double> run(const JsonNode &row) {
    const auto kind = field(row, "kind").string_value;
    const auto label = field(row, "label").string_value;
    const auto size = number(row, "size");
    if (kind == "text")
        return values(text_box(label, number(row, "x"), number(row, "y"), size, .15));
    const auto court = box(field(row, "court"));
    auto occupied = index(field(row, "occupied"));
    std::optional<SilkBoxIndex> placed;
    if (field(row, "placed").kind != JsonKind::Null)
        placed = index(field(row, "placed"));
    std::optional<Box4> bounds;
    if (field(row, "bounds").kind != JsonKind::Null)
        bounds = box(field(row, "bounds"));
    if (kind == "label") {
        const auto v = place_clear_label(court.x0, court.y0, court.x1, court.y1, label, size,
                                         occupied, placed ? &*placed : nullptr, bounds);
        return {v.x, v.y, v.box.x0, v.box.y0, v.box.x1, v.box.y1, v.extra};
    }
    if (kind == "refdes" && placed && bounds) {
        const auto v =
            place_refdes(court, label, size, box(field(row, "box")), occupied, *placed, *bounds,
                         number(row, "fx"), number(row, "fy"), number(row, "ca"), number(row, "sa"),
                         .8, .02, 8., 1e-9, .5, {.78, .62});
        return {v.moved ? 1. : 0., v.local_x,    v.local_y,    v.size,
                v.add_box.x0,      v.add_box.y0, v.add_box.x1, v.add_box.y1};
    }
    throw std::runtime_error("unsupported contract kind " + kind);
}
} // namespace
int main(int argc, char **argv) {
    try {
        if (argc != 2)
            throw std::runtime_error("usage: pack_silk_contracts CASES_JSON");
        index_boundaries();
        const auto data = parse_json_file(argv[1]);
        if (field(data, "schema").string_value != "schgen.pack_silk.python/1" ||
            field(data, "cases").array_value.size() != 34)
            throw std::runtime_error("wrong fixture schema or case count");
        int checks = 0, failures = 0;
        for (const auto &row : field(data, "cases").array_value) {
            const auto got = run(row);
            const auto &want = field(row, "expected").array_value;
            if (got.size() != want.size())
                throw std::runtime_error("wrong result size");
            for (std::size_t i = 0; i < got.size(); ++i) {
                ++checks;
                if (want[i].kind != JsonKind::Number || !std::isfinite(want[i].number_value))
                    throw std::runtime_error("expected finite Python result");
                const auto expected = want[i].number_value;
                if (got[i] != expected ||
                    (got[i] == 0 && std::signbit(got[i]) != std::signbit(expected))) {
                    ++failures;
                    std::cerr << field(row, "name").string_value << " field " << i << ": "
                              << std::setprecision(17) << got[i] << " != Python " << expected
                              << '\n';
                }
            }
        }
        if (checks != 181)
            throw std::runtime_error("incomplete contract coverage");
        std::cout << "silk kernel: " << checks << " exact fields; " << failures << " mismatches\n";
        return failures ? 1 : 0;
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
