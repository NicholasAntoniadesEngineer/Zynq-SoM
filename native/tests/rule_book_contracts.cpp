#include "schgen/roles.hpp"
#include "schgen/placement_integrity.hpp"
#include "schgen/rules.hpp"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <set>
#include <sstream>

namespace {

using namespace schgen;
using namespace schgen::rules;

namespace fixture {
constexpr double chip_half = 2, chip_pad_x = 1.5, chip_pad_y = 1, small_half_x = 1, small_half_y = 0.5;
constexpr double small_pad_x = 0.5, pad_size = 0.4;
constexpr double regulator_x = 20, regulator_y = 20, input_capacitor_x = 16.5, upper_row = 19, lower_row = 21;
constexpr double inductor_x = 24, output_capacitor_x = 27, logic_x = 40, sense_x = 36.5, crystal_x = 44, load_y = 17;
constexpr double connector_y = 40, clamp_y = 42, bystander_y = 50, intruder_x = 21, intruder_y = 41;
constexpr double spare_x = 60, spare_y = 60, module_low = 100, module_high = 130, module_centre = 115;
constexpr double module_capacitor_x = 112, module_capacitor_y = 96, crowding_x = 98.5, crowding_y = 110;
constexpr double far_x = 10, far_termination_x = 26, low_height = 1, tall_height = 5;
const char* const height_source = "fixture";
constexpr int pair_impedance = 90;
const char* const module_footprint = "parts/DF40C-100DS-0.4V_51/DF40C-100DS-0.4V_51.kicad_mod";
const std::set<std::string> areas{"mechanical", "high_speed", "power", "protection", "decoupling", "sensing", "timing"};
const std::set<std::string> confidences{"primary vendor document", "expert consensus", "owner decision", "derived"};
}

void require(bool condition, const std::string& what) {
    if (!condition) throw std::runtime_error("rule book contract failed: " + what);
}

std::string file_text(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) throw std::runtime_error("rule book contract cannot read " + path.string());
    return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}

struct PadSite {
    std::string name;
    double x = 0, y = 0;
};

PcbCheckFootprintPtr footprint(const std::string& name, double half_x, double half_y, const std::vector<PadSite>& pads) {
    std::ostringstream text;
    text << "(footprint \"" << name << "\" (fp_rect (start " << -half_x << " " << -half_y << ") (end " << half_x << " "
         << half_y << ") (layer \"F.CrtYd\"))";
    for (const auto& pad : pads)
        text << " (pad \"" << pad.name << "\" smd rect (at " << pad.x << " " << pad.y << ") (size " << fixture::pad_size
             << " " << fixture::pad_size << ") (layers \"F.Cu\"))";
    text << ")";
    return pcb_check_footprint(name + ".kicad_mod", text.str());
}

PcbCheckFootprintPtr chip() {
    static const PcbCheckFootprintPtr shared = footprint("chip", fixture::chip_half, fixture::chip_half,
        {{"1", -fixture::chip_pad_x, -fixture::chip_pad_y}, {"2", fixture::chip_pad_x, -fixture::chip_pad_y},
         {"3", -fixture::chip_pad_x, fixture::chip_pad_y}, {"4", fixture::chip_pad_x, fixture::chip_pad_y}});
    return shared;
}

PcbCheckFootprintPtr small() {
    static const PcbCheckFootprintPtr shared = footprint("small", fixture::small_half_x, fixture::small_half_y,
        {{"1", -fixture::small_pad_x, 0}, {"2", fixture::small_pad_x, 0}});
    return shared;
}

struct Scene {
    PcbModel model;
    layout::AuthoredIntent intent;
    Stackup stackup;

    PcbCheckInstance& part(const std::string& reference) {
        const auto found = std::find_if(model.insts.begin(), model.insts.end(),
                                        [&](const PcbCheckInstance& instance) { return instance.ref == reference; });
        require(found != model.insts.end(), "fixture holds " + reference);
        return *found;
    }
    void add(const std::string& reference, const std::string& sheet, PartClass part_class, double x, double y,
             PcbCheckFootprintPtr mod, const std::vector<std::pair<std::string, std::string>>& nets) {
        PcbCheckInstance instance;
        instance.ref = reference;
        instance.sheet = sheet;
        instance.part_class = part_class;
        instance.height = PartHeight{fixture::low_height, fixture::height_source};
        instance.footprint = "fixture";
        instance.x = x;
        instance.y = y;
        instance.mod = std::move(mod);
        for (const auto& [pad, net] : nets) instance.pad_nets[pad] = {1, net};
        model.insts.push_back(std::move(instance));
    }
    void serve(const std::string& part, const std::string& role, const std::string& owner, const std::string& pin) {
        intent.services.push_back({part, role, owner, pin, {}, "fixture", false});
    }
    void move(const std::string& reference, double x, double y) {
        part(reference).x = x;
        part(reference).y = y;
    }
    void sink(const std::string& reference) { part(reference).side = "bottom"; }
    RuleResult judge(const std::string& id) const {
        const PcbCheckInput input(model);
        const RuleContext context(input, model, stackup, intent);
        for (const auto& entry : rule_book())
            if (entry.rule.id == id) return entry.check(context);
        throw std::runtime_error("rule book contract failed: no rule named " + id);
    }
    std::size_t findings(const std::string& id) const { return judge(id).findings.size(); }
};

Stackup stack(std::initializer_list<CopperRole> roles) {
    Stackup stackup;
    for (const CopperRole role : roles) {
        const int ordinal = static_cast<int>(stackup.copper.size()) + 1;
        stackup.copper.push_back({ordinal, "L" + std::to_string(ordinal), role, 0, {}});
    }
    return stackup;
}

Stackup grounded() {
    return stack({CopperRole::signal, CopperRole::ground, CopperRole::signal, CopperRole::power, CopperRole::ground,
                  CopperRole::signal});
}

Stackup rear_over_power() {
    return stack({CopperRole::signal, CopperRole::ground, CopperRole::power, CopperRole::signal});
}

Scene baseline(const std::filesystem::path& repository) {
    Scene scene;
    scene.stackup = grounded();
    scene.model.som_keepout = Box4{fixture::module_low, fixture::module_low, fixture::module_high, fixture::module_high};
    scene.model.netclass_of["DP"] = "USB";
    scene.model.classes["USB"] = DifferentialGeometry{fixture::pair_impedance, 0, 0, "fixture"};
    scene.add("U1", "power", PartClass::integrated_circuit, fixture::regulator_x, fixture::regulator_y, chip(),
              {{"1", "VIN"}, {"2", "SW"}, {"3", "FB"}, {"4", "GND"}});
    scene.add("C1", "power", PartClass::capacitor, fixture::input_capacitor_x, fixture::upper_row, small(), {{"1", "GND"}, {"2", "VIN"}});
    scene.add("L1", "power", PartClass::inductor, fixture::inductor_x, fixture::upper_row, small(), {{"1", "SW"}, {"2", "VOUT"}});
    scene.add("C2", "power", PartClass::capacitor, fixture::output_capacitor_x, fixture::upper_row, small(), {{"1", "VOUT"}, {"2", "GND"}});
    scene.add("R1", "power", PartClass::resistor, fixture::input_capacitor_x, fixture::lower_row, small(), {{"1", "GND"}, {"2", "FB"}});
    scene.add("U2", "logic", PartClass::integrated_circuit, fixture::logic_x, fixture::regulator_y, chip(),
              {{"1", "SENSE"}, {"2", "XI"}, {"3", "LINE"}, {"4", "GND"}});
    scene.add("RS1", "logic", PartClass::resistor, fixture::sense_x, fixture::upper_row, small(), {{"1", "LOAD"}, {"2", "SENSE"}});
    scene.add("Y1", "logic", PartClass::crystal, fixture::crystal_x, fixture::upper_row, small(), {{"1", "XI"}, {"2", "GND"}});
    scene.add("C3", "logic", PartClass::capacitor, fixture::crystal_x, fixture::load_y, small(), {{"1", "XI"}, {"2", "GND"}});
    scene.add("R2", "logic", PartClass::resistor, fixture::sense_x, fixture::lower_row, small(), {{"1", "RAIL"}, {"2", "LINE"}});
    scene.add("J1", "usb", PartClass::connector, fixture::regulator_x, fixture::connector_y, small(), {{"1", "DP"}, {"2", "GND"}});
    scene.add("U3", "usb", PartClass::diode, fixture::regulator_x, fixture::clamp_y, small(), {{"1", "DP"}, {"2", "GND"}});
    scene.add("U4", "usb", PartClass::integrated_circuit, fixture::regulator_x, fixture::bystander_y, chip(), {{"1", "DP"}, {"4", "GND"}});
    scene.add("C9", "spare", PartClass::capacitor, fixture::spare_x, fixture::spare_y, small(), {});
    scene.sink("C9");
    const std::string bytes = file_text(repository / fixture::module_footprint);
    const PcbCheckFootprintPtr module = pcb_check_footprint(fixture::module_footprint, bytes);
    std::vector<std::pair<std::string, std::string>> module_nets;
    for (const auto& pad : module->pads) module_nets.emplace_back(std::get<0>(pad), "M" + std::get<0>(pad));
    scene.add("J9", "som_j1", PartClass::module_connector, fixture::module_centre, fixture::module_centre, module, module_nets);
    ModuleMate mate;
    mate.connector = "J1";
    mate.ref = "J9";
    mate.receptacle = mate.mate = posed_footprint_pads(*module, fixture::module_centre, fixture::module_centre, 0);
    scene.model.module_mates = {mate};
    scene.model.module_origin = std::make_pair(0.0, 0.0);
    scene.add("C7", "module_power", PartClass::capacitor, fixture::module_capacitor_x, fixture::module_capacitor_y, small(),
              {{"1", module_nets.front().second}, {"2", "GND"}});
    scene.serve("C1", "bypass", "U1", "1");
    scene.serve("L1", "switching", "U1", "2");
    scene.serve("C2", "reservoir", "L1", "2");
    scene.serve("R1", "feedback", "U1", "3");
    scene.serve("RS1", "sense", "U2", "1");
    scene.serve("Y1", "timing", "U2", "2");
    scene.serve("C3", "timing", "Y1", "1");
    scene.serve("R2", "terminate", "U2", "3");
    scene.serve("U3", "protect", "J1", "1");
    scene.intent.services.push_back({"C7", "bypass", {}, {}, "1", "module_power", true});
    scene.intent.pin_names["U1"] = {{"1", "VIN"}, {"2", "SW"}, {"3", "FB"}, {"4", "GND"}};
    return scene;
}

void book_is_indexed(const std::filesystem::path& repository) {
    const auto& book = rule_book();
    std::set<std::string> ids, files;
    for (const auto& entry : book) {
        const std::string id(entry.rule.id), area(entry.rule.area);
        require(ids.insert(id).second, "rule id " + id + " is unique");
        require(!id.empty() && std::all_of(id.begin(), id.end(), [](char letter) {
                    return (letter >= 'a' && letter <= 'z') || letter == '-';
                }), "rule id " + id + " is kebab-case");
        require(fixture::areas.count(area) != 0, "rule " + id + " names a known area");
        require(fixture::confidences.count(std::string(entry.rule.confidence)) != 0, "rule " + id + " states a known confidence");
        require(!entry.rule.statement.empty() && !entry.rule.why.empty() && !entry.rule.source.empty() && entry.check,
                "rule " + id + " states what it is, why, its source and has a check");
        std::string stem = id;
        std::replace(stem.begin(), stem.end(), '-', '_');
        const auto file = std::filesystem::path("native/src/rules") / area / (stem + ".cpp");
        require(std::filesystem::is_regular_file(repository / file), "rule " + id + " lives in " + file.string());
        files.insert(file.string());
    }
    std::size_t found = 0;
    for (const auto& area : fixture::areas)
        if (std::filesystem::is_directory(repository / "native/src/rules" / area))
            for (const auto& entry : std::filesystem::directory_iterator(repository / "native/src/rules" / area)) {
                ++found;
                require(files.count((std::filesystem::path("native/src/rules") / area / entry.path().filename()).string()) != 0,
                        entry.path().string() + " is a rule file the book lists");
            }
    require(found == book.size(), "every rule file is in the book");
    require(file_text(repository / "native/rules/README.md") == rule_book_markdown(),
            "native/rules/README.md equals the output of schgen rules");
}

void rules_judge(const std::filesystem::path& repository) {
    const Scene good = baseline(repository);
    for (const auto& entry : rule_book()) {
        const RuleResult judged = good.judge(std::string(entry.rule.id));
        require(judged.findings.empty(), std::string(entry.rule.id) + " passes the sound board" +
                                             (judged.findings.empty() ? "" : ": " + judged.findings.front().subject + " " +
                                                                                 judged.findings.front().detail));
        require(judged.checked > 0, std::string(entry.rule.id) + " judges something on the sound board");
    }
    {
        Scene scene = good;
        scene.move("R1", fixture::crowding_x, fixture::crowding_y);
        require(scene.findings("module-clearance") == 1, "a top part inside the module clearance is found");
        scene.sink("R1");
        require(scene.findings("module-clearance") == 0, "a rear part is not judged against the module clearance");
    }
    {
        Scene scene = good;
        require(good.judge("tall-part-beside-module").measurements.empty(), "a board of low parts lists no tall part");
        scene.part("U1").height = PartHeight{fixture::tall_height, fixture::height_source};
        scene.part("C7").height = PartHeight{fixture::tall_height, fixture::height_source};
        const RuleResult listed = scene.judge("tall-part-beside-module");
        require(listed.findings.empty() && listed.measurements.size() == 2 &&
                listed.measurements.front().rfind("C7", 0) == 0,
                "tall top parts are listed with the one nearest the module first");
        scene.sink("U1");
        require(scene.judge("tall-part-beside-module").measurements.size() == 1, "a tall rear part is not listed");
        scene.part("C7").height.reset();
        require(scene.findings("tall-part-beside-module") == 1, "a top part with no height is a finding, never a skip");
    }
    {
        Scene scene = good;
        scene.part("C1").part_class.reset();
        bool refused = false;
        try {
            scene.judge("regulator-loop-one-face");
        } catch (const std::runtime_error& error) {
            refused = std::string(error.what()).find("C1") != std::string::npos;
        }
        require(refused, "a part with no class stops the rule book and is named");
    }
    {
        Scene scene = good;
        scene.move("C9", fixture::module_centre, fixture::module_centre);
        require(scene.findings("module-escape-corridor") == 1, "a rear part inside an escape corridor is found");
        scene.part("C9").mod = nullptr;
        require(scene.findings("module-escape-corridor") == 1, "a part with no footprint is a corridor finding");
    }
    {
        Scene scene = good;
        scene.sink("U3");
        require(scene.findings("controlled-net-needs-ground") == 0, "a controlled part over a rear ground plane passes");
        scene.stackup = rear_over_power();
        require(scene.findings("controlled-net-needs-ground") == 1, "a controlled part over a power layer is found");
    }
    {
        Scene scene = good;
        scene.move("R2", fixture::far_termination_x, fixture::lower_row);
        require(scene.findings("termination-distance-report") == 1, "a termination beyond its reach is found");
        require(good.judge("termination-distance-report").measurements.size() == 1, "every termination distance is reported");
    }
    {
        Scene scene = good;
        scene.sink("L1");
        require(scene.findings("regulator-loop-one-face") == 1, "an inductor on the other face is found");
        scene = good;
        scene.sink("C1");
        scene.sink("C2");
        require(scene.findings("regulator-loop-one-face") == 2, "input and output capacitors on the other face are found");
        scene = good;
        scene.intent.pin_names.clear();
        require(scene.findings("regulator-loop-one-face") == 1 && scene.findings("input-capacitor-nearest") == 1,
                "a regulator with no identifiable input pin is a finding, never a skip");
    }
    {
        Scene scene = good;
        scene.sink("L1");
        require(scene.findings("regulator-over-ground") == 0, "an inductor over a rear ground plane passes");
        scene.stackup = rear_over_power();
        require(scene.findings("regulator-over-ground") == 1, "an inductor over a power layer is found");
    }
    {
        Scene scene = good;
        scene.move("C1", fixture::far_x, fixture::upper_row);
        require(scene.findings("input-capacitor-nearest") == 1, "an input capacitor that is not nearest its pin is found");
        require(good.judge("input-capacitor-nearest").measurements.size() == 1, "every input capacitor distance is reported");
    }
    {
        Scene scene = good;
        scene.move("R1", fixture::inductor_x, fixture::upper_row);
        scene.sink("R1");
        require(scene.findings("nothing-sensitive-under-inductor") == 1, "a feedback part under an inductor is found");
        require(good.judge("nothing-sensitive-under-inductor").measurements.size() == 1,
                "the nearest sense or timing part is reported for every inductor");
    }
    {
        Scene scene = good;
        scene.move("U4", fixture::intruder_x, fixture::intruder_y);
        require(scene.findings("protect-first-after-connector") == 1, "a part ahead of the clamp is found");
        scene = good;
        scene.sink("U3");
        require(scene.findings("protect-first-after-connector") == 1, "a clamp on the other face is found");
        scene = good;
        for (auto& service : scene.intent.services)
            if (service.role == "protect") service.owner = "R2";
        const RuleResult judged = scene.judge("protect-first-after-connector");
        require(judged.checked == 0 && judged.findings.empty() && judged.measurements.size() == 1,
                "a clamp that serves no connector pin is reported as not judged");
    }
    {
        Scene scene = good;
        scene.sink("C1");
        require(scene.findings("bypass-on-pin-face-or-under") == 1, "a bypass capacitor on the other face and not under is found");
        scene.move("C1", fixture::regulator_x, fixture::regulator_y);
        require(scene.findings("bypass-on-pin-face-or-under") == 0, "a bypass capacitor directly under over ground passes");
        scene.stackup = rear_over_power();
        require(scene.findings("bypass-on-pin-face-or-under") == 1, "a bypass capacitor directly under over power is found");
        require(good.judge("bypass-on-pin-face-or-under").checked == 2 &&
                good.judge("bypass-on-pin-face-or-under").measurements.size() == 1,
                "pin and module bypass capacitors are judged and their distances summarised");
    }
    {
        Scene scene = good;
        scene.sink("C3");
        require(scene.findings("timing-parts-on-crystal-face") == 1, "a load capacitor on the other face is found");
    }
    {
        Scene scene = good;
        require(scene.judge("sense-distance-report").measurements.size() == 1, "every sense distance is reported");
        scene.serve("RS9", "sense", "U2", "1");
        scene.serve("RS1", "sense", "U2", "9");
        require(scene.findings("sense-distance-report") == 2, "a sense part or pin that cannot be found is a finding, never a skip");
    }
}

void runner_gates(const std::filesystem::path& repository) {
    select_stackup(grounded());
    Scene scene = baseline(repository);
    const auto judged = [&] { return check_placement_integrity(PcbCheckInput(scene.model), scene.model, scene.intent); };
    const PlacementIntegrityResult sound = judged();
    require(sound.ok && sound.rules.size() == rule_book().size(), "the gate runs every rule and passes the sound board");
    const std::string summary = sound.summary(rules::Stage::layout);
    for (const auto& entry : rule_book())
        require(summary.find(std::string(entry.rule.area) + "/" + std::string(entry.rule.id) + ": checked ") != std::string::npos,
                "the summary has a line for " + std::string(entry.rule.id));
    scene.move("C9", fixture::module_centre, fixture::module_centre);
    const PlacementIntegrityResult broken = judged();
    require(!broken.ok && broken.summary(rules::Stage::layout).find("FAIL module-escape-corridor: C9") != std::string::npos,
            "a gate rule with findings fails the board and names them");
    for (const auto& result : broken.rules)
        if (result.rule->enforcement == Enforcement::measured)
            require(result.findings.empty(), "the corridor mutation leaves measured rules clean");
    Scene measured = baseline(repository);
    measured.move("R2", fixture::far_termination_x, fixture::lower_row);
    const PlacementIntegrityResult reported =
        check_placement_integrity(PcbCheckInput(measured.model), measured.model, measured.intent);
    require(reported.of("termination-distance-report").rule->enforcement == Enforcement::measured && reported.ok &&
            reported.of("termination-distance-report").findings.size() == 1 &&
            reported.summary(rules::Stage::layout).find("FOUND termination-distance-report: R2") != std::string::npos,
            "a measured rule reports its findings without failing the board");
}

}

void roles_live_in_one_place(const std::filesystem::path& repository) {
    const std::filesystem::path sources = repository / "native/src";
    std::vector<std::filesystem::path> files;
    for (const auto& entry : std::filesystem::recursive_directory_iterator(sources / "rules"))
        if (entry.path().extension() == ".cpp") files.push_back(entry.path());
    for (const auto& entry : std::filesystem::directory_iterator(sources)) {
        const std::string name = entry.path().filename().string();
        if (name.rfind("layout_", 0) == 0 && name != "layout_json.cpp") files.push_back(entry.path());
    }
    files.push_back(sources / "circuit_layout.cpp");
    files.push_back(sources / "placement_integrity.cpp");
    for (const auto& file : files) {
        std::ifstream stream(file);
        const std::string text((std::istreambuf_iterator<char>(stream)), std::istreambuf_iterator<char>());
        for (const schgen::rules::RoleRule& role : schgen::rules::role_catalogue()) {
            const std::string quoted = "\"" + std::string(role.name) + "\"";
            std::size_t at = text.find(quoted);
            while (at != std::string::npos) {
                const std::size_t line = text.rfind('\n', at);
                const std::string before = text.substr(line == std::string::npos ? 0 : line, at - (line == std::string::npos ? 0 : line));
                if (before.find("constexpr Rule") == std::string::npos && text.compare(at + quoted.size(), 1, ",") != 0)
                    throw std::runtime_error(file.filename().string() + " names the role " + quoted +
                                             " itself; role knowledge belongs in roles.cpp");
                at = text.find(quoted, at + quoted.size());
            }
        }
    }
}

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: rule_book_contracts REPOSITORY");
        const auto repository = std::filesystem::absolute(argv[1]);
        book_is_indexed(repository);
        roles_live_in_one_place(repository);
        rules_judge(repository);
        runner_gates(repository);
        std::cout << "rule book contracts ok\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 1;
    }
}
