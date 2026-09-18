// Build against som_interface.cpp, json.cpp, atomic_file.cpp, xdc.cpp and
// LibXml2::LibXml2. Run: som_interface_contracts DATA_DIR [REPO_ROOT].
// The optional real-source test runs KiCad; all other tests are hermetic C++.
// JSON baselines came from executing the unchanged Python extractor on the
// synthetic XML and KiCad 10.0.2's real SoM export on 2026-09-18.
#include "schgen/som_interface.hpp"
#include "schgen/json.hpp"

#include <algorithm>
#include <cstdlib>
#include <csignal>
#include <filesystem>
#include <fstream>
#include <functional>
#include <future>
#include <iostream>
#include <iterator>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>
#include <unistd.h>

namespace {
namespace fs = std::filesystem;
using namespace schgen;
const std::string source = "som/Zynq_SoM.kicad_sch";

void require(bool value, const std::string& message) {
    if (!value) throw std::runtime_error(message);
}
std::string read(const fs::path& path) {
    std::ifstream in(path, std::ios::binary);
    require(bool(in), "cannot read " + path.string());
    return {std::istreambuf_iterator<char>(in), {}};
}
void write(const fs::path& path, const std::string& text) {
    std::ofstream out(path, std::ios::binary);
    out << text;
    out.close();
    require(bool(out), "cannot write " + path.string());
}
struct TempDir {
    fs::path path;
    TempDir() {
        auto pattern = (fs::temp_directory_path() / "som-contracts-XXXXXX").string();
        require(::mkdtemp(pattern.data()) != nullptr, "mkdtemp failed");
        path = pattern;
    }
    ~TempDir() { std::error_code ec; fs::remove_all(path, ec); }
};
std::string changed(std::string text, const std::string& before, const std::string& after) {
    const auto p = text.find(before);
    require(p != std::string::npos && text.find(before, p + before.size()) == std::string::npos,
            "mutation target missing or repeated: " + before);
    text.replace(p, before.size(), after);
    return text;
}
const JsonNode& field(const JsonNode& n, const std::string& key) {
    const auto* value = object_field(n, key);
    require(value != nullptr, "baseline missing " + key);
    return *value;
}
XdcStrings pairs(const JsonNode& n) {
    XdcStrings result;
    for (const auto& [k, v] : n.object_value) result.emplace_back(k, v.string_value);
    return result;
}
void compare(const SomZynq& live, const JsonNode& baseline) {
    require(live.zynq_ref == field(baseline, "zynq_ref").string_value, "reference changed");
    require(live.value == field(baseline, "value").string_value, "device changed");
    require(live.source == field(baseline, "source").string_value, "source changed");
    require(live.pin_names == pairs(field(baseline, "pin_names")), "pin names/order changed");
    require(live.ball_net == pairs(field(baseline, "ball_net")), "ball nets/order changed");
    require(live.jpin_net == pairs(field(baseline, "jpin_net")), "connector nets/order changed");
}
void compare(const SomInterface& live, const JsonNode& baseline) {
    const auto& connectors = field(baseline, "connectors").object_value;
    require(live.source == field(baseline, "source").string_value, "interface source changed");
    require(live.connectors.size() == connectors.size(), "connector population changed");
    for (std::size_t i = 0; i < connectors.size(); ++i) {
        require(live.connectors[i].first == connectors[i].first, "connector ordering changed");
        require(live.connectors[i].second.pins == pairs(field(connectors[i].second, "pins")),
                "connector pin nets/order changed");
    }
}
struct Suite {
    int count = 0;
    void run(const std::string& label, const std::function<void()>& action) {
        try { action(); ++count; }
        catch (const std::exception& e) { throw std::runtime_error(label + ": " + e.what()); }
    }
    void rejects(const std::string& label, const std::function<void()>& action, const std::string& expected,
                 bool exact = true) {
        run(label, [&] {
            try { action(); }
            catch (const SomInterfaceError& e) {
                const std::string actual = e.what();
                require(exact ? actual == expected : actual.find(expected) != std::string::npos,
                        "wrong error: " + actual + "; expected " + expected);
                return;
            }
            throw std::runtime_error("invalid input accepted");
        });
    }
};

// The test binary doubles as a deterministic KiCad executable. It verifies
// argv boundaries, writes a netlist and records its scratch path for cleanup
// checks. No shell or Python helper is involved in process tests.
int fake_cli(int argc, char** argv) {
    require(argc == 9, "wrong KiCad argument count");
    for (const auto& [index, expected] : std::vector<std::pair<int, std::string>>{
            {1,"sch"},{2,"export"},{3,"netlist"},{4,"--format"},{5,"kicadxml"},{6,"-o"}})
        require(argv[index] == expected, "wrong KiCad argument");
    const fs::path input = argv[8], output = argv[7];
    write(input.string() + ".scratch", output.parent_path().string());
    if (input.filename() == "failure") {
        for (int i = 0; i < 500; ++i) std::cerr << "Ω";
        std::cerr << "\r\nlast\rline";
        return 7;
    }
    if (input.filename() == "no-output") return 0;
    if (input.filename() == "signal") { ::raise(SIGTERM); return 1; }
    // Large stdout/stderr cannot deadlock the file-based capture.
    std::cout << std::string(150000, 'o');
    std::cerr << std::string(150000, 'e');
    write(output, read(input));
    return 0;
}

void check_cleanup(const fs::path& input) {
    require(!fs::exists(read(input.string() + ".scratch")), "KiCad scratch directory leaked");
}

void contracts(const fs::path& fixtures, const fs::path& self, const std::optional<fs::path>& repo) {
    Suite s;
    const auto xml = read(fixtures / "som_interface.xml");
    const auto baseline = parse_json_file((fixtures / "som_synthetic_baseline.json").string());
    const auto live = parse_som_zynq_xml(xml, source);
    const auto interface = parse_som_interface_xml(xml, source, {"J3", "J1", "J2", "J1"});
    s.run("Python ordered extraction", [&] {
        compare(live, field(baseline,"zynq"));
        compare(interface, field(baseline,"interface"));
        require(interface.connectors[0].second.value == "Final value", "duplicate component lost last value");
        require(!interface.connectors[0].second.footprint, "empty footprint must be null");
        require(!interface.connectors[2].second.value && interface.connectors[2].second.footprint == "",
                "empty vs absent metadata distinction changed");
    });
    s.run("Python JSON bytes and load roundtrip", [&] {
        require(som_interface_json(interface) == read(fixtures / "som_interface_golden.json"), "interface JSON bytes differ");
        require(som_zynq_json(live) == read(fixtures / "som_zynq_golden.json"), "zynq JSON bytes differ");
        const auto loaded = load_som_interface(fixtures / "som_interface_golden.json");
        require(som_interface_json(loaded) == som_interface_json(interface), "contract JSON roundtrip changed");
        require(loaded.connectors.front().second.footprint == "Conn:𐀀", "non-BMP JSON did not decode");
    });
    s.run("empty selections and missing sections", [&] {
        require(parse_som_interface_xml("<export/>", "relative", {}).connectors.empty(), "empty selection failed");
        require(parse_som_zynq_xml(xml, source, "U2", {}).jpin_net.empty(), "empty jrefs not honored");
        const auto doc = xml.substr(0, xml.find("  <nets>")) + "</export>";
        require(parse_som_zynq_xml(doc, source).ball_net.empty(), "absent nets are not empty");
        require(parse_som_interface_xml(doc, source, {"J1"}).connectors[0].second.pins.empty(), "absent nets failed");
    });
    s.run("custom device and connector refs", [&] {
        const auto micro = parse_som_zynq_xml(xml, source, "U9", {"J3", "U9", "J9"});
        require(micro.pin_names == XdcStrings{{"1","PA0"}} && micro.value == "", "custom device failed");
        require(micro.ball_net.size() == 1 && micro.jpin_net.size() == 4, "custom selection failed");
        require(parse_som_zynq_xml(changed(xml,"<value>XC7Z020-CLG484</value>","<value/>"),source).value == std::nullopt,
                "empty device value failed");
    });
    s.rejects("missing refs retain request order and duplicates", [&] {
        parse_som_interface_xml(xml, source, {"missing", "J9", "missing", "x'y"});
    }, "connector refs not found in SoM netlist: ['missing', 'J9', 'missing', \"x'y\"]");
    s.rejects("missing components", [&] { parse_som_zynq_xml("<export/>",source); },
              "U2 not found in SoM netlist " + source);
    s.rejects("missing libsource", [&] {
        parse_som_zynq_xml(changed(xml,"<libsource lib=\"FPGA\" part=\"Zynq\"/>",""),source);
    }, "U2 not found in SoM netlist " + source);
    s.rejects("libsource requires both lib and part", [&] {
        parse_som_zynq_xml(changed(xml,"<libsource lib=\"FPGA\" part=\"Zynq\"/>",
                                 "<libsource lib=\"wrong\" part=\"Zynq\"/>"),source);
    }, "libpart pin table for U2 (('wrong', 'Zynq')) missing from SoM netlist");
    s.rejects("empty libpart", [&] {
        parse_som_zynq_xml("<export><components><comp ref='U2'><libsource/></comp></components></export>", source);
    }, "libpart pin table for U2 (('', '')) missing from SoM netlist");
    s.run("missing/empty pin numbers preserve Python semantics", [&] {
        require(live.ball_net.back() == std::make_pair(std::string{}, std::string{}), "missing ball pin changed");
        require(live.jpin_net[live.jpin_net.size()-2].first == "J3.None" && live.jpin_net.back().first == "J3.",
                "missing connector pin became empty");
        const auto tiny = parse_som_zynq_xml("<export><components><comp ref='U2'><libsource/></comp></components>"
            "<libparts><libpart><pins><pin/></pins></libpart></libparts></export>",source);
        require(tiny.pin_names == XdcStrings{{"", ""}}, "empty-number pin table was rejected");
    });
    for (const std::string bad : {"", "<export>", "<export/><export/>", "<export a='&undefined;'/>"})
        s.rejects("XML syntax failure", [&] { parse_som_interface_xml(bad,source,{}); }, "invalid SoM netlist XML", false);
    s.rejects("DTD and external entities disabled", [&] {
        parse_som_interface_xml("<!DOCTYPE export [<!ENTITY ext SYSTEM 'file:///etc/passwd'>]>"
            "<export><components><comp ref='J1'><value>&ext;</value></comp></components></export>",source,{"J1"});
    }, "DTD is not allowed in SoM netlist XML for " + source);
    s.run("XDC consumes live maps without rail or policy rewriting", [&] {
        XdcInput input;
        input.refs = {"J2"};
        input.connectors = {{"J2",interface.connectors[0].second.pins}};
        input.function_map = {{"ZYNQ_PL_P","DATA_P"},{"ZYNQ_PL_N_FINAL","DATA_N"}};
        input.bank_rails = input.vcco_rails = {{"34","+2V5"}};
        input.ports = {{"DATA_P","consumer","single",{},{},0},{"DATA_N","consumer","single",{},{},1}};
        apply_som_to_xdc(input,live);
        require(input.pin_names == live.pin_names && input.ball_net == live.ball_net && input.jpin_net == live.jpin_net,
                "adapter changed ordered maps");
        require(input.bank_rails == XdcStrings{{"34","+2V5"}}, "live adapter overwrote rail policy");
        const auto xdc = generate_xdc(input);
        require(xdc.entries.size()==2 && xdc.entries[0].ball=="B1" && xdc.entries[1].ball=="B2",
                "XDC pin mapping failed");
        require(xdc.entries[0].bank=="34" && xdc.entries[0].iostd=="LVCMOS25", "XDC bank/rail mapping changed");
    });

    TempDir temp;
    const SomExtractOptions options{self.string()};
    const auto input = temp.path / "source space ' ;$(ignored).kicad_sch";
    write(input, xml);
    s.run("live argv, large captured output and scratch cleanup", [&] {
        const auto extracted = extract_som_zynq(input,"U2",{"J1","J2","J3"},options);
        require(extracted.source==input.string() && extracted.pin_names==live.pin_names && extracted.jpin_net==live.jpin_net,
                "subprocess extraction changed fields");
        check_cleanup(input);
    });
    s.run("concurrent exports have isolated scratch paths", [&] {
        const auto second = temp.path / "second";
        write(second,xml);
        auto a = std::async(std::launch::async,[&] { return extract_som_zynq(input,"U2",{},options); });
        auto b = std::async(std::launch::async,[&] { return extract_som_zynq(second,"U2",{},options); });
        require(a.get().ball_net==b.get().ball_net, "concurrent extraction differs");
        require(read(input.string()+".scratch")!=read(second.string()+".scratch"), "scratch directories collided");
        check_cleanup(input); check_cleanup(second);
    });
    s.run("CLI JSON publication and report", [&] {
        const auto output = temp.path / "nested/interface.json";
        const auto report=write_som_interface(input," J3, J1,,J2,J1 \t",output,options);
        auto expected=interface; expected.source=input.string();
        require(read(output)==som_interface_json(expected), "published JSON differs");
        require(report=="SoM interface: 4 connectors, 9 pins -> "+output.string()+"\n"
            "  J1 (Mezz & \"quoted\" Ω): 3 pins, 3 netted\n"
            "  J2 (Final value): 3 pins, 3 netted\n"
            "  J3 (None): 3 pins, 2 netted\n", "CLI report differs: " + report);
    });
    s.run("CLI Unicode whitespace stripping matches str.strip", [&] {
        const auto output = temp.path / "unicode-refs.json";
        const auto report = write_som_interface(input,"\u00a0J3\u2003,\x1cJ1, J2,\u3000",output,options);
        auto expected=interface; expected.source=input.string();
        require(read(output)==som_interface_json(expected),"Unicode whitespace changed connector selection");
        require(report.find("SoM interface: 3 connectors, 9 pins -> ")==0,"Unicode whitespace changed ref count");
    });
    const auto failure=temp.path/"failure";
    std::string tail;
    for(int i=0;i<390;++i)tail+="Ω";
    s.rejects("nonzero exit preserves last 400 Unicode characters", [&] {
        extract_som_zynq(failure,"U2",{},options);
    }, "kicad-cli failed on "+failure.string()+": "+tail+"\nlast\nline");
    s.run("failure scratch cleanup",[&] {check_cleanup(failure);});
    s.rejects("killed CLI is a failed export", [&] { extract_som_zynq(temp.path/"signal","U2",{},options); },
              "kicad-cli failed on "+(temp.path/"signal").string()+": ");
    s.rejects("zero exit without a netlist is not success", [&] {
        extract_som_zynq(temp.path/"no-output","U2",{},options);
    }, "cannot read SoM netlist file:", false);
    s.rejects("missing executable", [&] {extract_som_zynq(input,"U2",{},{(temp.path/"absent executable").string()});},
              "cannot execute ",false);
    s.run("failed publication preserves existing destination", [&] {
        const auto output=temp.path/"protected.json";
        write(output,"previous\n");
        try {write_som_interface(failure,"J1",output,options);} catch(const SomInterfaceError&) {}
        require(read(output)=="previous\n","failed extraction changed destination");
    });
    s.run("real snapshot invariants", [&] {
        const auto real=parse_json_file((fixtures/"som_real_baseline.json").string());
        require(field(field(real,"zynq"),"pin_names").object_value.size()==483, "real pin population changed");
        require(field(field(real,"zynq"),"jpin_net").object_value.size()==300, "real connector population changed");
    });
    if(repo) s.run("real SoM live against Python baseline and committed contracts",[&] {
        const auto real=parse_json_file((fixtures/"som_real_baseline.json").string());
        auto device=extract_som_zynq(*repo/source);
        auto contract=extract_som_interface(*repo/source,{"J3","J1","J2","J1"});
        device.source=contract.source=source;
        compare(device,field(real,"zynq")); compare(contract,field(real,"interface"));
        for(const auto* project:{"carrier","devkit_mini"}) {
            const auto saved=load_som_interface(*repo/project/"som_interface.json");
            for(const auto& [ref,conn]:saved.connectors) {
                const auto found=std::find_if(contract.connectors.begin(),contract.connectors.end(),
                    [target_ref = ref](const auto& item){return item.first==target_ref;});
                require(found!=contract.connectors.end(),"saved connector missing live");
                auto a=conn.pins,b=found->second.pins;
                std::sort(a.begin(),a.end());std::sort(b.begin(),b.end());
                require(a==b,"saved contract pin drift: "+std::string(project)+" "+ref);
            }
        }
    });
    std::cout << s.count << " SoM interface contracts passed\n";
}
}  // namespace

int main(int argc,char** argv) {
    try {
        if(argc>1 && std::string(argv[1])=="sch")return fake_cli(argc,argv);
        require(argc==2 || argc==3,"usage: som_interface_contracts DATA_DIR [REPO_ROOT]");
        contracts(argv[1],fs::absolute(argv[0]),argc==3 ? std::optional<fs::path>{argv[2]} : std::nullopt);
        return 0;
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
