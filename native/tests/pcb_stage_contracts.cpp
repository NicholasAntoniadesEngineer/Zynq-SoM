#include "schgen/pcb_stage_templates.hpp"
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {
using namespace schgen;
int checks = 0;
void require(bool p, const std::string &message) {
    ++checks;
    if (!p)
        throw std::runtime_error(message);
}
const JsonNode &field(const JsonNode &n, const std::string &k) {
    auto p = object_field(n, k);
    if (!p)
        throw std::runtime_error("missing fixture " + k);
    return *p;
}
Box4 box(const JsonNode &n) {
    const auto &a = n.array_value;
    return {a.at(0).number_value, a.at(1).number_value, a.at(2).number_value, a.at(3).number_value};
}
std::vector<std::string> strings(const JsonNode &n) {
    std::vector<std::string> out;
    for (const auto &x : n.array_value)
        out.push_back(x.string_value);
    return out;
}
PcbCheckFootprintPtr footprint(const PcbFootprintPool &pool, const std::string &path) {
    auto p = pool.find(path);
    if (p != pool.end())
        return p->second;
    for (const auto &[key, fp] : pool)
        if (path.size() >= key.size() &&
            path.compare(path.size() - key.size(), key.size(), key) == 0)
            return fp;
    // Frozen pool represents installed KiCad libraries by library/stem, while
    // the independent call trace retains the exact original absolute path.
    for (const auto &[key, fp] : pool)
        if (std::filesystem::path(key).filename() == std::filesystem::path(path).filename() &&
            std::filesystem::path(key).parent_path().filename() ==
                std::filesystem::path(path).parent_path().filename())
            return fp;
    throw std::runtime_error("missing immutable footprint source " + path);
}
PcbStageInput input(const JsonNode &fixture, const JsonNode &row, const PcbFootprintPool &pool) {
    PcbStageInput in;
    in.sheet = field(row, "sheet").string_value;
    in.contract = field(row, "contract");
    in.refs = strings(field(row, "refs"));
    for (const auto &[r, s] : field(row, "side_of").object_value)
        in.side_of[r] = s.string_value;
    for (const auto &[r, s] : field(row, "board_refs").object_value)
        in.board_refs[r] = s.string_value;
    for (const auto &[r, b] : field(row, "bbox_of").object_value)
        in.bbox_of[r] = box(b);
    for (const auto &[r, s] : field(row, "resolvable").object_value)
        in.footprints[r] = footprint(pool, s.string_value);
    for (const auto &r : field(row, "pad_nets").array_value)
        in.pad_nets[{r.array_value[0].string_value, r.array_value[1].string_value}] =
            r.array_value[2].string_value;
    for (const auto &[r, nets] : field(row, "inter_nets").object_value)
        for (const auto &[n, pins] : nets.object_value)
            in.inter_nets[r][n] = strings(pins);
    for (const auto &[name, r] : field(fixture, "partners").object_value) {
        PcbStagePartner p;
        p.footprint = footprint(pool, r.array_value.at(0).string_value);
        p.rotation = r.array_value.at(1).number_value;
        for (const auto &[n, pins] : r.array_value.at(2).object_value)
            p.nets[n] = strings(pins);
        in.partners[name] = std::move(p);
    }
    auto pilots = strings(field(fixture, "pilot_sheets"));
    in.pilot = std::find(pilots.begin(), pilots.end(), in.sheet) != pilots.end();
    in.facing = field(row, "facing").string_value;
    in.outer_dir = field(row, "outer_dir").string_value;
    return in;
}
void offsets(const FloorplanOffsets &actual, const JsonNode &expected, const std::string &context) {
    require(actual.size() == expected.object_value.size(), context + " member count");
    for (const auto &[r, p] : expected.object_value) {
        auto a = actual.find(r);
        require(a != actual.end(), context + " missing " + r);
        require(a->second.first == p.array_value[0].number_value &&
                    a->second.second == p.array_value[1].number_value,
                context + " " + r + " actual " + std::to_string(a->second.first) + "," +
                    std::to_string(a->second.second) + " expected " +
                    std::to_string(p.array_value[0].number_value) + "," +
                    std::to_string(p.array_value[1].number_value));
    }
}
JsonNode &edit(JsonNode &node, const std::string &key) {
    for (auto &[k, value] : node.object_value)
        if (k == key)
            return value;
    throw std::runtime_error("missing mutable fixture field " + key);
}
void result_equal(const PcbStageResult &result, const JsonNode &row, const std::string &context) {
    const auto &expected = field(row, "expected").array_value;
    offsets(result.top, expected[0], context + "/top");
    offsets(result.bottom, expected[1], context + "/bottom");
    require(result.w == expected[2].number_value && result.h == expected[3].number_value,
            context + " extent " + std::to_string(result.w) + "," + std::to_string(result.h));
    const auto &er = field(row, "rotations");
    require(result.rotations.size() == er.object_value.size(), context + " rotations count");
    for (const auto &[r, v] : er.object_value)
        require(result.rotations.at(r) == v.number_value, context + " rotation " + r);
}
void input_guards(const PcbStageInput &original) {
    auto reject = [](const PcbStageInput &in, const std::string &reason) {
        bool rejected = false;
        try {
            build_pcb_stage_zone(in);
        } catch (const PcbZoneInfeasible &error) {
            rejected = true;
            require(std::string(error.what()).find(reason) != std::string::npos,
                    "typed input guard reason");
        }
        require(rejected, "invalid typed stage input rejected: " + reason);
    };
    auto in = original;
    in.contract = JsonNode{};
    reject(in, "without a contract");
    for (double clearance : {0., -1., std::numeric_limits<double>::infinity(),
                             std::numeric_limits<double>::quiet_NaN()}) {
        in = original;
        in.place_clear = clearance;
        reject(in, "clearance");
    }
    require(!original.bbox_of.empty(), "stage guard bounds available");
    in = original;
    in.bbox_of.begin()->second.x0 = in.bbox_of.begin()->second.x1 + 1;
    reject(in, "invalid stage bounds");
    in = original;
    in.bbox_of.begin()->second.y0 = std::numeric_limits<double>::quiet_NaN();
    reject(in, "invalid stage bounds");
}
void mutations(const std::filesystem::path &root, const JsonNode &fixture,
               const PcbFootprintPool &pool) {
    const auto mutants =
        parse_json_file((root / "native/tests/data/pcb_placement/stage_mutations.json").string());
    for (const auto &test : field(mutants, "cases").array_value) {
        auto sheet = field(test, "sheet").string_value, id = field(test, "mutation").string_value;
        const auto &cases = field(fixture, "cases").array_value;
        auto row = std::find_if(cases.begin(), cases.end(), [&](const auto &r) {
            return field(r, "sheet").string_value == sheet;
        });
        require(row != cases.end(), "mutation baseline exists");
        auto in = input(fixture, *row, pool);
        if (id == "no_structures")
            edit(in.contract, "structures").array_value.clear();
        else if (id == "missing_member" || id == "cycle" || id == "impossible_bound") {
            auto &structures = edit(in.contract, "structures").array_value;
            auto first = std::find_if(structures.begin(), structures.end(), [](const auto &s) {
                return field(s, "type").string_value == "proximity";
            });
            require(first != structures.end(), "proximity mutation target");
            if (id == "missing_member") {
                JsonNode lib;
                lib.kind = JsonKind::String;
                lib.string_value = "MISSING";
                edit(*first, "members").array_value.push_back(lib);
            } else if (id == "cycle") {
                JsonNode reversed = *first;
                edit(reversed, "anchor") = field(*first, "members").array_value[0];
                edit(reversed, "members").array_value = {field(*first, "anchor")};
                edit(reversed, "max_mm").number_value = 4;
                reversed.object_value.erase(
                    std::remove_if(reversed.object_value.begin(), reversed.object_value.end(),
                                   [](const auto &p) { return p.first == "anchor_pins"; }),
                    reversed.object_value.end());
                structures.push_back(reversed);
            } else
                for (auto &s : structures)
                    if (field(s, "type").string_value == "proximity")
                        edit(s, "max_mm").number_value = .001;
        } else if (id == "no_external")
            in.contract.object_value.erase(
                std::remove_if(in.contract.object_value.begin(), in.contract.object_value.end(),
                               [](const auto &p) { return p.first == "external"; }),
                in.contract.object_value.end());
        else if (id == "pilot_star")
            in.pilot = true;
        else if (id == "no_partner")
            in.partners.clear();
        else if (id != "facing" && id != "connector_face" && id != "larger_cap")
            throw std::runtime_error("unknown mutation " + id);
        if (auto p = object_field(test, "facing"))
            in.facing = p->string_value;
        if (auto p = object_field(test, "outer_dir"))
            in.outer_dir = p->string_value;
        if (auto p = object_field(test, "footprint_override")) {
            auto r = p->array_value[0].string_value;
            in.footprints[r] = footprint(pool, p->array_value[1].string_value);
            in.bbox_of[r] = box(p->array_value[2]);
        }
        auto context = "mutation/" + sheet + "/" + id + "/" + in.facing + in.outer_dir;
        if (object_field(test, "error")) {
            const std::string fragment = id == "no_structures"    ? "no hot_loop/proximity"
                                         : id == "missing_member" ? "MISSING"
                                         : id == "cycle"          ? "cyclic constraint graph"
                                                                  : "24-scale widen";
            // Compare the same independently observed policy rejection, not
            // exception-class spelling or the language-specific list repr.
            require(field(test, "error").string_value.find(fragment) != std::string::npos,
                    context + " Python reason");
            bool rejected = false;
            try {
                build_pcb_stage_zone(in);
            } catch (const PcbZoneInfeasible &e) {
                rejected = true;
                require(std::string(e.what()).find(fragment) != std::string::npos,
                        context + " wrong reason: " + e.what());
            }
            require(rejected, context + " must reject");
        } else {
            auto result = build_pcb_stage_zone(in);
            result_equal(result, test, context);
            require(result.fallback_events == strings(field(test, "fallback_events")),
                    context + " ordered diagnostics");
            const auto &expected = field(test, "quantization");
            require(result.quantization_engagements.size() == expected.object_value.size(),
                    context + " diagnostic count size");
            for (const auto &[name, n] : expected.object_value)
                require(result.quantization_engagements.at(name) == n.number_value,
                        context + " diagnostic count " + name);
        }
    }
    std::cout << "29 independent Python stage mutations passed\n";
}
void baseline(const std::filesystem::path &root, const std::string &name) {
    const auto fixture = parse_json_file(
        (root / "native/tests/data/pcb_placement" / (name + "_stages.json")).string());
    const auto emit =
        parse_json_file((root / "native/tests/data/pcb_emit" / (name + ".json")).string());
    PcbFootprintPool pool;
    for (const auto &[path, bytes] : field(emit, "footprints").object_value)
        pool[path] = pcb_check_footprint(path, bytes.string_value);
    const auto floorplan =
        parse_json_file((root / "native/tests/data/floorplan" / (name + ".json")).string());
    for (const auto &[key, doc] : field(field(floorplan, "input"), "footprints").object_value) {
        (void)key;
        auto source = field(doc, "source").string_value;
        pool[source] = pcb_check_footprint(source, field(doc, "text").string_value);
    }
    for (const auto &row : field(fixture, "cases").array_value) {
        auto in = input(fixture, row, pool);
        auto result = build_pcb_stage_zone(in);
        auto context = name + "/" + in.sheet;
        const auto &expected = field(row, "expected").array_value;
        offsets(result.top, expected[0], context + "/top");
        offsets(result.bottom, expected[1], context + "/bottom");
        require(result.w == expected[2].number_value && result.h == expected[3].number_value,
                context + " extent " + std::to_string(result.w) + "," + std::to_string(result.h) +
                    " wanted " + std::to_string(expected[2].number_value) + "," +
                    std::to_string(expected[3].number_value));
        const auto &er = field(row, "rotations");
        require(result.rotations.size() == er.object_value.size(), context + " rotations count");
        for (const auto &[r, v] : er.object_value)
            require(result.rotations.at(r) == v.number_value, context + " rotation " + r);
        std::cout << context << ": complete Python zone parity\n";
    }
    if (name == "carrier") {
        mutations(root, fixture, pool);
        input_guards(input(fixture, field(fixture, "cases").array_value.front(), pool));
    }
}
} // namespace
int main(int argc, char **argv) {
    try {
        if (argc != 2)
            throw std::runtime_error("repo root required");
        for (const auto &name : {"carrier", "devkit_mini"})
            baseline(argv[1], name);
        std::cout << "PCB stage templates: " << checks << " assertions passed\n";
    } catch (const std::exception &e) {
        std::cerr << e.what() << "\n";
        return 1;
    }
}
