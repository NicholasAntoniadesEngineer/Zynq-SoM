// Native-only, frozen schematic/IR/XML contracts. Run DATA_DIR [--kicad CLI].
// --kicad is explicit and mandatory when requested: no success-by-skip path.
#include "schgen/netlist_gate.hpp"

#include <algorithm>
#include <csignal>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <iterator>
#include <map>
#include <stdexcept>
#include <unistd.h>

namespace {
namespace fs = std::filesystem;
using namespace schgen;

void require(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);  // Active under NDEBUG.
}
std::string read(const fs::path& path) {
    std::ifstream in(path, std::ios::binary);
    require(bool(in), "cannot read " + path.string());
    std::string text{std::istreambuf_iterator<char>(in), {}};
    require(!in.bad(), "failed reading " + path.string());
    return text;
}
void write(const fs::path& path, const std::string& text) {
    std::ofstream out(path, std::ios::binary);
    out << text; out.close();
    require(bool(out), "failed writing " + path.string());
}
const JsonNode& field(const JsonNode& node, const std::string& name) {
    const auto* value = object_field(node, name);
    require(value != nullptr, "missing fixture key " + name);
    return *value;
}
std::string str(const JsonNode& node, const std::string& name) { return field(node, name).string_value; }
std::vector<std::string> strings(const JsonNode& node) {
    std::vector<std::string> out;
    for (const auto& item : node.array_value) out.push_back(item.string_value);
    return out;
}
ExtractedNetlist netlist(const JsonNode& node) {
    ExtractedNetlist out;
    for (const auto& row : node.array_value) {
        require(row.array_value.size() == 2, "bad extracted row");
        std::vector<KicadNetlistPin> pins;
        for (const auto& pin : row.array_value[1].array_value) {
            require(pin.array_value.size() == 2, "bad extracted pin");
            pins.push_back({pin.array_value[0].string_value, pin.array_value[1].string_value});
        }
        out.emplace_back(row.array_value[0].string_value, std::move(pins));
    }
    return out;
}
void compare(const ExtractedNetlist& actual, const ExtractedNetlist& expected) {
    require(actual.size() == expected.size(), "extracted net count differs");
    for (std::size_t i = 0; i < actual.size(); ++i) {
        require(actual[i].first == expected[i].first, "extracted names/order differ");
        require(actual[i].second.size() == expected[i].second.size(), "pin count differs for " + actual[i].first);
        for (std::size_t j = 0; j < actual[i].second.size(); ++j)
            require(actual[i].second[j].ref == expected[i].second[j].ref && actual[i].second[j].pin == expected[i].second[j].pin,
                    "pin value/order differs for " + actual[i].first);
    }
}
void compare(const NetlistGateResult& actual, const JsonNode& expected) {
    require(actual.ok == field(expected, "ok").bool_value, "pass/fail differs: " + actual.summary());
    for (const auto& [name, values] : std::vector<std::pair<std::string, const std::vector<std::string>*>>{
        {"shorts",&actual.shorts}, {"opens",&actual.opens}, {"nc_cheats",&actual.nc_cheats},
        {"part_mismatches",&actual.part_mismatches}, {"name_mismatches",&actual.name_mismatches}})
        require(*values == strings(field(expected,name)), name + " differ: " + actual.summary());
    require(actual.summary() == str(expected, "summary"), "summary bytes/order differ: " + actual.summary());
}
struct Suite {
    int passed = 0, failed = 0;
    void run(const std::string& label, const std::function<void()>& action) {
        try { action(); ++passed; }
        catch (const std::exception& e) { ++failed; std::cerr << label << ": " << e.what() << '\n'; }
    }
    void rejects(const std::string& label, const std::function<void()>& action, const std::string& wanted) {
        run(label, [&] {
            try { action(); }
            catch (const NetlistGateError& e) {
                require(std::string(e.what()).find(wanted) != std::string::npos, "unexpected error: " + std::string(e.what()));
                return;
            }
            throw std::runtime_error("invalid input accepted");
        });
    }
};
struct TempDir {
    fs::path path;
    TempDir() {
        auto pattern = (fs::temp_directory_path() / "netlist-contracts-XXXXXX").string();
        require(::mkdtemp(pattern.data()) != nullptr, "mkdtemp failed");
        path = pattern;
    }
    ~TempDir() { std::error_code ec; fs::remove_all(path, ec); }
};

// Process transport probe only; connectivity goldens and live mutation tests
// come from real KiCad. No shell scripts, Python, or substitute gate oracle.
int transport_probe(int argc, char** argv) {
    require(argc == 9, "wrong argv count");
    for (const auto& [i, value] : std::vector<std::pair<int, std::string>>{
            {1,"sch"},{2,"export"},{3,"netlist"},{4,"--format"},{5,"kicadxml"},{6,"-o"}})
        require(argv[i] == value, "argv changed");
    const fs::path input = argv[8], output = argv[7];
    write(input.string() + ".scratch", output.parent_path().string());
    if (input.filename() == "failure") { std::cerr << "deliberate export error"; return 7; }
    if (input.filename() == "signal") { ::raise(SIGTERM); return 1; }
    if (input.filename() == "no-output") return 0;
    std::cout << std::string(180000, 'o'); std::cerr << std::string(180000, 'e');
    write(output, read(input.string() + ".xml"));
    return 0;
}
std::string insert_before_end(std::string text, const std::string& insertion) {
    const auto end = text.rfind(')');
    require(end != std::string::npos, "missing document end");
    text.insert(end, insertion);
    return text;
}
std::string m1_mutation(std::string text, bool shorted) {
    if (shorted) return insert_before_end(text, "(wire (pts (xy 101.6 77.47) (xy 101.6 85.09)) "
        "(stroke (width 0) (type default)) (uuid \"22222222-2222-4222-8222-222222222222\"))\n");
    const auto begin = text.find("\t(wire\n\t\t(pts\n\t\t\t(xy 101.6 91.44)\n\t\t\t(xy 101.6 97.79)");
    require(begin != std::string::npos, "missing M1 open mutation target");
    const auto end = text.find("\n\t)", begin);
    require(end != std::string::npos, "unterminated M1 wire");
    text.erase(begin, end + 4 - begin);
    return text;
}

void contracts(Suite& suite, const fs::path& fixtures, const fs::path& self, const std::string& cli) {
    const auto corpus = parse_json_file((fixtures / "cases.json").string());
    std::map<std::string, CircuitSheetIr> circuits;
    for (const auto& [name, spec] : field(corpus, "circuits").object_value) {
        if (const auto* path = object_field(spec, "file")) circuits[name] = load_circuit_json(fixtures / path->string_value);
        else circuits[name] = parse_circuit_ir(field(spec, "ir"));
    }
    for (const auto& spec : field(corpus, "xml_cases").array_value) {
        const auto* path = object_field(spec, "file");
        const auto source = path ? path->string_value : "synthetic XML";
        suite.run("ordered extraction " + source, [&] {
            compare(parse_netlist_xml(path ? read(fixtures / source) : str(spec,"text"), source), netlist(field(spec,"expected")));
        });
    }
    std::map<std::string, JsonNode> expected;
    for (const auto& spec : field(corpus, "cases").array_value) {
        const auto name = str(spec, "name");
        expected.emplace(name, field(spec, "expected"));
        suite.run("frozen report " + name, [&] {
            const auto* path = object_field(spec, "schematic_file");
            auto text = path ? read(fixtures / path->string_value) : str(spec, "schematic_text");
            if (const auto* suffix = object_field(spec, "append_nc"))
                text = text.substr(0, text.rfind(')')) + "(no_connect" + suffix->string_value;
            compare(check_netlist(circuits.at(str(spec,"circuit")), netlist(field(spec,"extracted")), text), field(spec,"expected"));
        });
    }
    suite.run("normalization", [&] {
        require(normalize_netlist_name("/MID") == "MID" && normalize_netlist_name("+3V3") == "+3V3"
                && normalize_netlist_name("//x") == "x" && normalize_netlist_name("///").empty()
                && normalize_netlist_name("/sheet/MID") == "sheet/MID", "normalization changed");
    });
    suite.run("direct duplicate dictionary semantics", [&] {
        const ExtractedNetlist rows{{"Z",{{"U1","bad"}}},{"Z",{{"U1","1"}}}};
        require(check_netlist(circuits.at("simple"), rows, "").ok, "duplicate net was treated as multimap");
    });
    suite.run("dead device prefixes and part ordering", [&] {
        const auto messages = dead_two_terminal(circuits.at("dead"));
        require(messages == strings(field(expected.at("dead_two_terminal"),"shorts")) && messages.size() == 3,
                "cap/resistor/inductor detection changed");
    });
    suite.run("single internal signal pin retains reference semantics", [&] {
        auto c = circuits.at("simple"); c.nets[0].net_class = "signal";
        require(check_netlist(c, ExtractedNetlist{}, "").ok, "netlist gate substituted for electrical completeness");
    });
    for (const auto& text : std::vector<std::string>{"", "<export>", "<export/><export/>", "<export a='&undefined;'/>",
            "<!DOCTYPE export [<!ENTITY e SYSTEM 'file:///etc/passwd'>]><export><nets>&e;</nets></export>",
            "<!DOCTYPE export SYSTEM 'https://invalid.example/external.dtd'><export/>"})
        suite.rejects("secure XML rejection", [&] { parse_netlist_xml(text); }, "XML");
    for (const auto& text : std::vector<std::string>{"(kicad_sch (no_connect))", "(kicad_sch (no_connect (at 1)))",
            "(kicad_sch (no_connect (at nan 0)))", "(kicad_sch (no_connect (at 0 infinity)))",
            "(kicad_sch (no_connect (at 0 0))", "(kicad_sch (no_connect (at 0 0)) (symbol (lib_id U) (at 0 0 \"nan\")))"})
        suite.rejects("malformed NC geometry", [&] { check_netlist(circuits.at("simple"), {}, text); }, "NC geometry");
    suite.run("immutable caller records", [&] {
        const auto c = circuits.at("m1_rc");
        const auto nets = parse_netlist_xml(read(fixtures / "m1_rc.xml"));
        const auto again = nets;
        require(check_netlist(c, nets, read(fixtures / "m1_rc.kicad_sch")).ok, "clean M1 failed");
        compare(nets, again);
    });

    TempDir tmp;
    const auto spaced_cli = tmp.path / "cli ; literal ' argument";
    fs::create_symlink(self, spaced_cli);
    const NetlistExtractOptions options{spaced_cli.string()};
    const auto source = tmp.path / "sheet ; $(touch SHOULD_NOT_EXIST) ' name.kicad_sch";
    write(source, read(fixtures / "m1_rc.kicad_sch"));
    write(source.string() + ".xml", read(fixtures / "m1_rc.xml"));
    suite.run("shared shell-free process transport and live gate", [&] {
        compare(extract_netlist(source, options), parse_netlist_xml(read(fixtures / "m1_rc.xml")));
        compare(check_netlist(circuits.at("m1_rc"), source, options), expected.at("m1_rc_clean"));
        require(!fs::exists(read(source.string() + ".scratch")), "private scratch directory leaked");
    });
    for (const auto& [name, diagnostic] : std::vector<std::pair<std::string,std::string>>{
            {"failure","deliberate export error"},{"signal","kicad-cli failed"},{"no-output","cannot read"}}) {
        const auto path = tmp.path / name;
        suite.rejects("process failure " + name, [&] { extract_netlist(path,options); }, diagnostic);
        suite.run("process failure cleanup " + name, [&] {
            require(!fs::exists(read(path.string()+".scratch")), "failed process leaked scratch directory");
        });
    }
    suite.rejects("no executable fallback", [&] { extract_netlist(source,{(tmp.path/"absent").string()}); }, "cannot execute");
    suite.rejects("empty executable", [&] { extract_netlist(source,{""}); }, "executable is empty");
    suite.rejects("embedded NUL executable", [&] { extract_netlist(source,{std::string("cli\0tail",8)}); }, "embedded null");
    suite.rejects("embedded NUL source", [&] { extract_netlist(fs::path(std::string("sch\0tail",8)),options); }, "embedded null");
    const auto bad = tmp.path / "bad-xml";
    write(bad.string()+".xml","<!DOCTYPE export><export/>");
    suite.rejects("live XML remains hardened", [&] { extract_netlist(bad,options); }, "DTD");

    if (!cli.empty()) {
        for (const std::string key : {"carrier_board_services","devkit_uart_bridge","m1_rc"})
            suite.run("real KiCad frozen " + key, [&] {
                const auto path = fixtures / (key+".kicad_sch");
                compare(extract_netlist(path,{cli}),parse_netlist_xml(read(fixtures/(key+".xml"))));
                compare(check_netlist(circuits.at(key),path,{cli}),expected.at(key+"_clean"));
            });
        for (const bool shorted : {true,false}) {
            const std::string key = shorted ? "m1_short" : "m1_open";
            suite.run("real KiCad physical mutation " + key, [&] {
                const auto path = tmp.path/(key+".kicad_sch");
                write(path,m1_mutation(read(fixtures/"m1_rc.kicad_sch"),shorted));
                compare(extract_netlist(path,{cli}),parse_netlist_xml(read(fixtures/(key+".xml"))));
                compare(check_netlist(circuits.at("m1_rc"),path,{cli}),expected.at(key+"_physical_wire_mutation"));
            });
        }
        suite.run("real KiCad NC cannot replace a declared net", [&] {
            const auto path = tmp.path / "m1_nc.kicad_sch";
            write(path,insert_before_end(read(fixtures/"m1_rc.kicad_sch"),
                "(no_connect (at 101.6 77.47) (uuid \"33333333-3333-4333-8333-333333333333\"))\n"));
            const auto result = check_netlist(circuits.at("m1_rc"),path,{cli});
            require(!result.ok && result.nc_cheats == strings(field(expected.at("m1_rc_nc_on_live_pin"),"nc_cheats")),
                    "KiCad pass hid the NC cheat: " + result.summary());
        });
    }
}
}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc > 1 && std::string(argv[1]) == "sch") return transport_probe(argc,argv);
        require(argc == 2 || (argc == 4 && std::string(argv[2]) == "--kicad"),
                "usage: netlist_gate_contracts DATA_DIR [--kicad CLI]");
        Suite suite;
        contracts(suite,fs::absolute(argv[1]),fs::canonical(argv[0]),argc == 4 ? argv[3] : "");
        std::cout << "netlist gate contracts: " << suite.passed << " passed, " << suite.failed << " failed\n";
        return suite.failed ? 1 : 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
