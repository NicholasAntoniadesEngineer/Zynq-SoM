// Standalone electrical IR contracts. No interpreter, extension, symbol library
// or precompiled catalog is used. An optional argument checks the carrier JSONs.
#include "schgen/circuit.hpp"
#include "schgen/json.hpp"

#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
#include <unistd.h>

namespace {
namespace fs = std::filesystem;
using schgen::CircuitSheetIr;

void require(bool value, const std::string& message) {
    // These checks deliberately remain active with NDEBUG/Release builds.
    if (!value) throw std::runtime_error(message);
}

struct TempDir {
    fs::path path;
    TempDir() {
        auto pattern = (fs::temp_directory_path() / "schgen-ir-XXXXXX").string();
        require(::mkdtemp(pattern.data()) != nullptr, "mkdtemp failed");
        path = pattern;
    }
    TempDir(const TempDir&) = delete;
    TempDir& operator=(const TempDir&) = delete;
    ~TempDir() {
        std::error_code error;
        fs::remove_all(path, error);
    }
};

struct CatalogGuard {
    ~CatalogGuard() {
        try { schgen::close_circuit_catalog(); }
        catch (...) { std::abort(); }
    }
};

void write(const fs::path& path, const std::string& text) {
    fs::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary);
    require(bool(out), "cannot create fixture: " + path.string());
    out.write(text.data(), static_cast<std::streamsize>(text.size()));
    out.close();
    require(bool(out), "cannot write fixture: " + path.string());
}

std::string read(const fs::path& path) {
    std::ifstream in(path, std::ios::binary);
    require(bool(in), "cannot read fixture: " + path.string());
    return {std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};
}

// Guard every mutation against no-op or ambiguous replacements: otherwise a
// fixture refactor could quietly stop exercising the intended validation rule.
std::string changed(std::string text, const std::string& before,
                    const std::string& after) {
    const auto pos = text.find(before);
    require(!before.empty() && pos != std::string::npos,
            "fixture mutation target missing: " + before);
    require(text.find(before, pos + before.size()) == std::string::npos,
            "fixture mutation target ambiguous: " + before);
    text.replace(pos, before.size(), after);
    return text;
}

const std::string kNet1 = R"({"name":"N1","net_class":"port","pins":["U1.1","R1.1"]})";
const std::string kNet2 = R"({"name":"N2","net_class":"port","pins":["U1.2","R1.2"]})";
const std::string kNc = R"("nc":["U1.3","U1.A4"])";

std::string fixture() {
    return R"({"schema":"schgen.circuit/1","name":"fixture","title":"Fixture",
"parts":[
 {"ref":"U1","lib_id":"missing:IC","value":"IC","footprint":"",
  "fields":{},"pin_names":{"DATA":["1"],"GND":["3","A4"]},
  "pin_numbers":["1","2","3","A4"]},
 {"ref":"R1","lib_id":"missing:R","value":"R","footprint":"",
  "fields":{},"pin_names":{},"pin_numbers":[]}],
"nets":[)" + kNet1 + "," + kNet2 + "]," + kNc + R"(,
"port_types":{},"hints":{},"loads":{},"tp_waivers":{},"decap_waivers":{},
"pull_waivers":{},"reset_waivers":{},"strap_waivers":{},"ep_waivers":{},
"thermal_waivers":{},"part_rule_waivers":{}})";
}

std::string port(const std::string& kind = "single") {
    return R"({"kind":")" + kind + R"(","pair_with":null,"impedance":null,
"role":null,"bus":null,"speed_hz":null,"level_v":null,"expect":null})";
}

std::string with_ports(const std::string& text, const std::string& first,
                       const std::string& second = "") {
    return changed(text, R"("port_types":{})", R"("port_types":{"N1":)"
        + first + (second.empty() ? "" : R"(,"N2":)" + second) + "}");
}

std::string pair_port(const std::string& kind, const std::string& other,
                      int impedance = 100) {
    return changed(changed(port(kind), R"("pair_with":null)",
                           R"("pair_with":")" + other + "\""),
                   R"("impedance":null)", "\"impedance\":" + std::to_string(impedance));
}

std::string add_nc(const std::string& text, const std::string& spec) {
    return changed(text, kNc, R"("nc":["U1.3","U1.A4",")" + spec + "\"]");
}

std::string add_pin(const std::string& net, const std::string& spec) {
    return changed(net, "]}", ",\"" + spec + "\"]}");
}

void compile(const fs::path& source, const fs::path& output) {
    require(schgen::compile_circuit_catalog(source.string(), output.string()),
            "compile returned false");
}

void reject_compile(const fs::path& source, const fs::path& output,
                     const std::string& expected) {
    try {
        compile(source, output);
    } catch (const std::runtime_error& error) {
        const std::string actual(error.what());
        require(actual.find("circuit compile failed:") != std::string::npos
                && actual.find(expected) != std::string::npos,
                "wrong rejection; expected '" + expected + "', got: " + actual);
        return;
    }
    throw std::runtime_error("invalid IR accepted; expected: " + expected);
}

struct Suite {
    std::size_t passed = 0;

    template <typename F>
    void run(const std::string& label, F test) {
        try {
            test();
            ++passed;
        } catch (const std::exception& error) {
            throw std::runtime_error(label + ": " + error.what());
        }
    }

    void rejects(const std::string& label, const std::string& text,
                 const std::string& expected) {
        run(label, [&] {
            TempDir tmp;
            const auto source = tmp.path / "source";
            const auto input = source / "circuit.json";
            const auto output = tmp.path / "circuits.bin";
            write(input, text);
            // Negative semantic cases must be syntactically valid JSON.
            schgen::parse_json_file(input.string());
            reject_compile(source, output, expected);
            require(!fs::exists(output), "invalid catalog was published");
            require(read(input) == text, "rejection changed source IR");
        });
    }

    void accepts(const std::string& label, const std::string& text,
                 const std::function<void(const CircuitSheetIr&)>& inspect = {}) {
        run(label, [&] {
            TempDir tmp;
            CatalogGuard catalog;
            const auto source = tmp.path / "source";
            const auto input = source / "circuit.json";
            const auto output = tmp.path / "circuits.bin";
            write(input, text);
            compile(source, output);
            require(schgen::open_circuit_catalog(output.string()), "open returned false");
            require(schgen::circuit_catalog_count() == 1, "wrong catalog count");
            const auto sheet = schgen::lookup_circuit_catalog("fixture");
            require(sheet.name == "fixture" && sheet.schema == "schgen.circuit/1",
                    "catalog changed circuit identity");
            require(sheet.parts.size() == 2, "catalog lost parts");
            if (inspect) inspect(sheet);
            require(read(input) == text, "compile changed source IR");
        });
    }
};

void pin_contracts(Suite& suite) {
    const auto base = fixture();
    suite.accepts("expanded metadata and inline symbol", base, [](const auto& sheet) {
        require(sheet.parts[0].pin_numbers == std::vector<std::string>{"1", "2", "3", "A4"},
                "pin table changed");
        require(sheet.parts[0].pin_names.size() == 2, "aliases lost");
        require(sheet.parts[1].pin_numbers.empty(), "inline pin table invented");
        require(sheet.nets.size() == 2 && sheet.nc.size() == 2, "connectivity lost");
    });
    const std::vector<std::pair<std::string, std::string>> bad_pins = {
        {"UNKNOWN.1", "unknown part 'UNKNOWN'"},
        {"U1.99", "pin does not exist on U1"},
        {"U1.DATA", "pin does not exist on U1"},
        {"U1", "bad pin spec"}, {".1", "bad pin spec"}, {"U1.", "bad pin spec"}};
    for (const auto& [spec, error] : bad_pins) {
        suite.rejects("invalid net pin " + spec, changed(base, kNet1, add_pin(kNet1, spec)), error);
        suite.rejects("invalid NC pin " + spec, add_nc(base, spec), error);
    }
    for (const std::string targets : {R"(["99"])", R"(["1","99"])", R"(["DATA"])", "[]"}) {
        suite.rejects("unused alias targets " + targets,
            changed(base, R"("DATA":["1"])", R"("BAD":)" + targets), "pin alias 'BAD'");
    }
    suite.rejects("alias without pin table",
        changed(base, R"("pin_numbers":["1","2","3","A4"])", R"("pin_numbers":[])"),
        "targets undeclared pin");
    for (const std::string ref : {"U1", "R1"}) {
        const auto conflicting = add_pin(kNet2, ref + ".1");
        for (const bool reverse : {false, true}) {
            suite.rejects("conflicting owner " + ref + (reverse ? " reversed" : ""),
                changed(base, kNet1 + "," + kNet2,
                        reverse ? conflicting + "," + kNet1 : kNet1 + "," + conflicting),
                "already on net");
        }
    }
    for (const std::string spec : {"U1.1", "U1.2", "R1.1", "R1.2"}) {
        suite.rejects("NC with owner " + spec, add_nc(base, spec), "carries a net, cannot be NC");
    }
    auto stacked = changed(base, R"("DATA":["1"])", R"("DATA":["1"],"ALSO_GND":["3","A4"])");
    stacked = changed(stacked, kNet2,
        kNet2 + R"(,{"name":"GND","net_class":"ground","pins":["U1.3","U1.A4"]})");
    stacked = changed(changed(stacked, kNet1, add_pin(kNet1, "U1.1")), kNc, R"("nc":[])");
    suite.accepts("stacked aliases and repeated same-net pin", stacked, [](const auto& sheet) {
        require(sheet.nc.empty() && sheet.nets.size() == 3, "stacked connectivity lost");
        require(sheet.nets[0].pins.size() == 3, "same-net repeated pin changed");
        require(sheet.parts[0].pin_names.size() == 3, "shared aliases lost");
    });
    suite.accepts("inline pin validity deferred to symbol gate", add_nc(base, "R1.A99"),
        [](const auto& sheet) {
            require(sheet.nc.back().ref == "R1" && sheet.nc.back().pin == "A99",
                    "inline NC pin lost");
        });
}

void port_contracts(Suite& suite) {
    const auto base = fixture();
    suite.accepts("single port", with_ports(base, port()));
    for (const std::string role : {"scl", "sda"}) {
        suite.accepts("i2c role " + role, with_ports(base,
            changed(port("i2c"), R"("role":null)", R"("role":")" + role + "\"")));
    }
    suite.accepts("sd bus level", with_ports(base,
        changed(port("sd_bus"), R"("level_v":null)", R"("level_v":1.8)")));
    suite.rejects("typed unknown net",
        changed(with_ports(base, port()), R"("port_types":{"N1":)",
                R"("port_types":{"UNKNOWN":)"), "not a declared PORT net");
    for (const std::string cls : {"signal", "power", "ground"}) {
        suite.rejects("typed non-port " + cls,
            with_ports(changed(base, kNet1,
                changed(kNet1, R"("net_class":"port")", R"("net_class":")" + cls + "\"")),
                port()), "not a declared PORT net");
    }
    const std::vector<std::pair<std::string, std::string>> invalid = {
        {port("unknown"), "unknown kind"},
        {changed(port(), R"("pair_with":null)", R"("pair_with":"N2")"),
         "pair_with only valid for pair kinds"},
        {changed(port(), R"("role":null)", R"("role":"scl")"), "role only valid for i2c"},
        {port("i2c"), "i2c needs role"},
        {changed(port("i2c"), R"("role":null)", R"("role":"clock")"), "i2c needs role"},
        {port("sd_bus"), "sd_bus needs level_v"}};
    for (const auto& [record, error] : invalid) {
        suite.rejects("port: " + error, with_ports(base, record), error);
    }
}

void pair_contracts(Suite& suite) {
    const auto base = fixture();
    for (const std::string kind : {"diff_pair", "usb_hs_pair", "tmds_pair"}) {
        const int impedance = kind == "usb_hs_pair" ? 90 : 100;
        const auto first = pair_port(kind, "N2", impedance);
        const auto second = pair_port(kind, "N1", impedance);
        const std::vector<std::pair<std::string, std::string>> changes = {
            {changed(first, R"("pair_with":"N2")", R"("pair_with":null)"), "needs pair_with"},
            {changed(first, R"("pair_with":"N2")", R"("pair_with":"UNKNOWN")"),
             "not a declared PORT net"},
            {changed(first, R"("pair_with":"N2")", R"("pair_with":"N1")"), "cannot pair with itself"},
            {changed(first, "\"impedance\":" + std::to_string(impedance),
                     R"("impedance":null)"), "expanded pair needs impedance"}};
        for (const auto& [record, error] : changes) {
            suite.rejects(kind + ": " + error, with_ports(base, record, second), error);
        }
        auto shared = [](std::string record) {
            record = changed(record, R"("bus":null)", R"("bus":"data")");
            return changed(record, R"("expect":null)", R"("expect":"peer")");
        };
        auto one_sided = changed(shared(first), R"("speed_hz":null)", R"("speed_hz":480000000)");
        one_sided = changed(one_sided, R"("level_v":null)", R"("level_v":1.8)");
        suite.accepts(kind + " reciprocal with one-sided speed/level",
            with_ports(base, one_sided, shared(second)), [impedance](const auto& sheet) {
                require(sheet.port_types.size() == 2, "pair record lost");
                const auto& first_port = sheet.port_types[0];
                const auto& second_port = sheet.port_types[1];
                require(first_port.impedance == impedance && second_port.impedance == impedance,
                        "pair impedance changed");
                require(first_port.has_speed_hz && first_port.speed_hz == 480000000
                        && first_port.has_level_v && first_port.level_v == 1.8
                        && !second_port.has_speed_hz && !second_port.has_level_v,
                        "legitimate one-sided metadata changed");
            });
    }
    const auto first = pair_port("diff_pair", "N2");
    const auto second = pair_port("diff_pair", "N1");
    suite.rejects("pair with internal complement", with_ports(changed(base, kNet2,
        changed(kNet2, R"("net_class":"port")", R"("net_class":"signal")")), first, second),
        "not a declared PORT net");
    const auto three_nets = changed(base, kNet2,
        kNet2 + R"(,{"name":"N3","net_class":"port","pins":[]})");
    const std::vector<std::string> conflicts = {
        changed(second, R"("pair_with":"N1")", R"("pair_with":"N3")"),
        changed(second, R"("kind":"diff_pair")", R"("kind":"usb_hs_pair")"),
        changed(second, R"("impedance":100)", R"("impedance":90)"),
        changed(second, R"("bus":null)", R"("bus":"other")"),
        changed(second, R"("expect":null)", R"("expect":"other")"), port()};
    for (std::size_t i = 0; i < conflicts.size(); ++i) {
        suite.rejects("reciprocal metadata conflict " + std::to_string(i),
            with_ports(three_nets, first, conflicts[i]), "conflicting reciprocal pair metadata");
    }
    suite.rejects("missing reciprocal type", with_ports(base, first),
                  "expanded pair needs reciprocal port_type");
    suite.run("intermediate page retains reciprocal metadata without weakening ingestion", [&] {
        TempDir tmp;
        const auto path = tmp.path / "page.json";
        write(path, with_ports(base, first));
        const auto raw = schgen::parse_json_file(path.string());
        const auto page = schgen::decode_intermediate_circuit_ir(raw);
        require(page.port_types.size() == 1 && page.port_types.front().pair_with == "N2",
                "intermediate transport dropped mate metadata");
        bool rejected = false;
        try { (void)schgen::parse_circuit_ir(raw); }
        catch (const std::runtime_error&) { rejected = true; }
        require(rejected, "canonical ingestion no longer enforces reciprocal metadata");
    });
}

void atomic_contracts(Suite& suite) {
    for (const bool existing : {false, true}) {
        suite.run(existing ? "failed compile preserves live catalog" : "failed compile publishes nothing", [&] {
            TempDir tmp;
            CatalogGuard catalog;
            const auto source = tmp.path / "source";
            const auto output = tmp.path / "circuits.bin";
            write(source / "a_valid/circuit.json", fixture());
            std::string before;
            if (existing) {
                compile(source, output);
                before = read(output);
                schgen::open_circuit_catalog(output.string());
            }
            // Fail after a valid sheet so partial catalog publication is caught.
            const auto other = changed(fixture(), R"("name":"fixture")", R"("name":"second")");
            write(source / "z_invalid/circuit.json", add_nc(other, "U1.1"));
            reject_compile(source, output, "carries a net, cannot be NC");
            if (existing) {
                require(read(output) == before, "failed compile replaced existing bytes");
                require(schgen::circuit_catalog_count() == 1
                        && schgen::lookup_circuit_catalog("fixture").nc.size() == 2,
                        "failed compile damaged active reader");
            } else {
                require(!fs::exists(output), "failed compile published new catalog");
            }
            for (const auto& entry : fs::directory_iterator(tmp.path)) {
                require(entry.path().filename().string().find(".tmp.") == std::string::npos,
                        "failed compile leaked temporary publication file");
            }
            // Repairing the input must recover, without poisoning the reader.
            write(source / "z_invalid/circuit.json", other);
            compile(source, output);
            if (existing) {
                require(schgen::circuit_catalog_count() == 1, "publication changed mapped reader");
                schgen::close_circuit_catalog();
            }
            schgen::open_circuit_catalog(output.string());
            require(schgen::circuit_catalog_count() == 2, "valid retry failed");
            require(schgen::lookup_circuit_catalog("fixture").parts.size() == 2
                    && schgen::lookup_circuit_catalog("second").parts.size() == 2,
                    "valid retry lost sheets");
        });
    }
}

void carrier_contract(Suite& suite, const fs::path& source) {
    suite.run("all 37 carrier sheets and deterministic catalog", [&] {
        TempDir tmp;
        CatalogGuard catalog;
        const auto output = tmp.path / "carrier.bin";
        std::vector<fs::path> paths;
        for (const auto& entry : fs::recursive_directory_iterator(source)) {
            if (entry.is_regular_file() && entry.path().filename() == "circuit.json") {
                paths.push_back(entry.path());
            }
        }
        require(paths.size() == 37, "expected exactly 37 carrier JSON sheets");
        std::sort(paths.begin(), paths.end());
        std::vector<std::string> originals;
        for (const auto& path : paths) originals.push_back(read(path));
        compile(source, output);
        schgen::open_circuit_catalog(output.string());
        require(schgen::circuit_catalog_count() == 37, "carrier sheet disappeared");
        for (std::size_t i = 0; i < paths.size(); ++i) {
            const auto ir = schgen::parse_json_file(paths[i].string());
            const auto name = schgen::require_string(ir, "name", false, "carrier");
            const auto sheet = schgen::lookup_circuit_catalog(name);
            const auto* parts = schgen::object_field(ir, "parts");
            const auto* nets = schgen::object_field(ir, "nets");
            const auto* nc = schgen::object_field(ir, "nc");
            require(parts && nets && nc, "carrier fixture missing electrical fields");
            require(sheet.parts.size() == parts->array_value.size()
                    && sheet.nets.size() == nets->array_value.size()
                    && sheet.nc.size() == nc->array_value.size(), name + ": records lost");
            for (std::size_t n = 0; n < sheet.nets.size(); ++n) {
                const auto& expected = nets->array_value[n];
                const auto& net = sheet.nets[n];
                const auto* pins = schgen::object_field(expected, "pins");
                require(net.name == schgen::require_string(expected, "name", false, name)
                        && net.net_class == schgen::require_string(expected, "net_class", false, name)
                        && pins && net.pins.size() == pins->array_value.size(), name + ": net changed");
                for (std::size_t p = 0; p < net.pins.size(); ++p) {
                    require(net.pins[p].ref + "." + net.pins[p].pin == pins->array_value[p].string_value,
                            name + ": net pin changed");
                }
            }
            for (std::size_t n = 0; n < sheet.nc.size(); ++n) {
                require(sheet.nc[n].ref + "." + sheet.nc[n].pin == nc->array_value[n].string_value,
                        name + ": NC pin changed");
            }
            require(read(paths[i]) == originals[i], name + ": source IR changed");
        }
        const auto again = tmp.path / "carrier-again.bin";
        compile(source, again);
        require(read(output) == read(again), "carrier catalog is nondeterministic");
    });
}
}  // namespace

int main(int argc, char** argv) {
    try {
        require(argc <= 2, "usage: circuit_semantic_contracts [CARRIER_SUBSYSTEMS_DIR]");
        Suite suite;
        pin_contracts(suite);
        port_contracts(suite);
        pair_contracts(suite);
        atomic_contracts(suite);
        if (argc == 2) carrier_contract(suite, argv[1]);
        std::cout << suite.passed << " native circuit semantic contracts passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
