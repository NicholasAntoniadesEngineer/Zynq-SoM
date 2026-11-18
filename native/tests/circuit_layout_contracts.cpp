#include "schgen/authoring.hpp"

#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

using namespace schgen;

void require(bool condition, const std::string& what) {
    if (!condition) throw std::runtime_error("circuit layout contract failed: " + what);
}

AuthoringContext bare() {
    AuthoringContext context;
    context.part = [](const std::string& name) -> CatalogPart {
        throw std::runtime_error("no catalog in this contract: " + name);
    };
    return context;
}

CircuitAuthor regulator() {
    CircuitAuthor c("rail", "rail under test", bare());
    c.part("U1", "Regulator_Linear:AP2112K-3.3", "AP2112K-3.3", "Package_TO_SOT_SMD:SOT-23-5");
    c.part("J1", "Connector_Generic:Conn_01x02", "header", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical");
    c.net("VIN", {"U1.1", "J1.1"}, "power");
    c.net("GND", {"U1.2", "J1.2"}, "ground");
    c.net("EN", {"U1.3"}, "signal");
    c.net("VOUT", {"U1.5"}, "power");
    c.nc({"U1.4"});
    return c;
}

bool rejected(const std::function<void(CircuitAuthor&)>& mistake, const std::string& expected) {
    CircuitAuthor c = regulator();
    try {
        mistake(c);
        (void)c.finish();
    } catch (const std::exception& error) {
        if (std::string(error.what()).find(expected) != std::string::npos) return true;
        std::cout << "  unexpected message: " << error.what() << "\n";
        return false;
    }
    return false;
}

void helpers_record_their_owner() {
    CircuitAuthor c = regulator();
    const auto caps = c.decouple("U1.1", {"100n", "10u"});
    const auto pull = c.pullup("U1.3", "10k", "VIN");
    const CircuitSheetIr sheet = c.finish();
    require(sheet.layout.serves.size() == caps.size() + 1, "each helper part is recorded once");
    for (std::size_t index = 0; index < caps.size(); ++index) {
        const auto& service = sheet.layout.serves[index];
        require(service.part == caps[index] && service.owner.ref == "U1" && service.owner.pin == "1" && service.net.empty(),
                "a decoupling capacitor serves the pin it was declared for");
    }
    require(sheet.layout.serves[0].role == "bypass" && sheet.layout.serves[1].role == "reservoir",
            "a small decoupling value is a bypass and a bulk value is a reservoir");
    const auto filter = c.decouple("U1.5", {"100p"}, std::nullopt, "GND", "Device:C", {}, "filter");
    require(c.finish().layout.serves.back().part == filter.front() && c.finish().layout.serves.back().role == "filter",
            "a declared role overrides the value rule");
    const auto& last = sheet.layout.serves.back();
    require(last.part == pull && last.role == "pull" && last.owner.ref == "U1" && last.owner.pin == "3",
            "a pull resistor serves the pin it was declared for");
}

void declarations_survive_transport() {
    CircuitAuthor c = regulator();
    c.part("C9", "Device:C", "1u");
    c.net("VOUT", {"C9.1"});
    c.net("GND", {"C9.2"});
    c.part("R9", "Device:R", "0R");
    c.net("VOUT", {"R9.1"});
    c.net("GND", {"R9.2"});
    c.part("C8", "Device:C", "10u");
    c.net("VIN", {"C8.1"});
    c.net("GND", {"C8.2"});
    c.serves("C9", "U1.5", "reservoir");
    c.serves_net("C8", "VIN", "reservoir");
    c.free("R9", "bleed resistor with no single owner");
    c.bind({{"VIN", "+5V0"}});
    const CircuitSheetIr sheet = c.finish();
    require(sheet.layout.serves.size() == 2 && sheet.layout.free.size() == 1, "declarations are kept by finish");
    require(sheet.layout.serves[1].net == "+5V0", "binding a net renames the net a part serves");
    const JsonNode document = circuit_layout_json(sheet);
    const CircuitLayoutIr restored = parse_circuit_layout(document, sheet);
    CircuitSheetIr copy = sheet;
    copy.layout = restored;
    require(authoring_json_equal(circuit_layout_json(copy), document), "layout intent round trips through its document");
    require(authoring_json_equal(authored_circuit_json(copy), authored_circuit_json(sheet)),
            "the electrical document does not carry layout intent");
    require(object_field(authored_circuit_json(sheet), "serves") == nullptr, "the electrical document is unchanged");
    CircuitAuthor reopened(sheet, bare());
    require(reopened.finish().layout.serves.size() == 2, "reopening a sheet keeps its declarations");
}

void mistakes_are_rejected() {
    const auto cap = [](CircuitAuthor& c, const std::string& ref, const std::string& net) {
        c.part(ref, "Device:C", "100n");
        c.net(net, {ref + ".1"});
        c.net("GND", {ref + ".2"});
    };
    require(rejected([&](CircuitAuthor& c) { cap(c, "C9", "VOUT"); c.serves("C9", "U1.5", "decoration"); }, "unknown role"),
            "an unknown role is rejected");
    require(rejected([&](CircuitAuthor& c) { c.serves("C9", "U1.5", "bypass"); }, "unknown part"),
            "an unknown part is rejected");
    require(rejected([&](CircuitAuthor& c) { cap(c, "C9", "VOUT"); c.serves("C9", "U1.3", "bypass"); }, "shares no net"),
            "an owner pin on another net is rejected");
    require(rejected([&](CircuitAuthor& c) {
                cap(c, "C9", "VOUT");
                c.serves("C9", "U1.5", "bypass");
                c.free("C9", "second thoughts");
            }, "already has a declaration"),
            "a second declaration for one part is rejected");
    require(rejected([&](CircuitAuthor& c) { cap(c, "C9", "VOUT"); c.serves("C9", "C9.1", "bypass"); }, "cannot serve itself"),
            "a part serving itself is rejected");
    require(rejected([&](CircuitAuthor& c) {
                cap(c, "C8", "VOUT");
                cap(c, "C9", "VOUT");
                c.serves("C8", "C9.1", "bypass");
                c.serves("C9", "C8.1", "bypass");
            }, "forms a cycle"),
            "circular ownership is rejected");
    require(rejected([&](CircuitAuthor& c) { cap(c, "C9", "VOUT"); c.free("C9", "  "); }, "a reason is required"),
            "releasing a part without a reason is rejected");
    require(rejected([&](CircuitAuthor& c) { cap(c, "C9", "VOUT"); c.serves_net("C9", "VIN", "bypass"); }, "no pin on net"),
            "serving a net the part does not touch is rejected");
    require(rejected([&](CircuitAuthor& c) { cap(c, "C9", "VOUT"); c.serves_net("C9", "NOWHERE", "bypass"); }, "not a declared net"),
            "serving an undeclared net is rejected");
}

void documents_are_strict() {
    CircuitAuthor c = regulator();
    c.decouple("U1.1", {"100n"});
    const CircuitSheetIr sheet = c.finish();
    const auto broken = [&](const std::function<void(JsonNode&)>& damage) {
        JsonNode document = circuit_layout_json(sheet);
        damage(document);
        try {
            (void)parse_circuit_layout(document, sheet);
        } catch (const std::exception&) {
            return true;
        }
        return false;
    };
    const auto field = [](JsonNode& node, const std::string& key) -> JsonNode& {
        for (auto& [name, value] : node.object_value)
            if (name == key) return value;
        throw std::runtime_error("fixture field missing: " + key);
    };
    require(!broken([](JsonNode&) {}), "an untouched document is accepted");
    require(broken([&](JsonNode& d) { field(d, "schema").string_value = "schgen.subsystem-layout/0"; }),
            "another schema is rejected");
    require(broken([&](JsonNode& d) { field(d, "name").string_value = "elsewhere"; }),
            "a document for another sheet is rejected");
    require(broken([&](JsonNode& d) { field(field(d, "serves").array_value.front(), "pin").string_value = "U1"; }),
            "an owner that is not REF.PIN is rejected");
    require(broken([&](JsonNode& d) { d.object_value.emplace_back("extra", JsonNode{}); }), "an unknown field is rejected");
    require(circuit_service_roles().size() == std::size_t{13}, "the role vocabulary is the documented one");
}

}

int main() {
    try {
        helpers_record_their_owner();
        declarations_survive_transport();
        mistakes_are_rejected();
        documents_are_strict();
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 1;
    }
    std::cout << "circuit layout contracts ok\n";
    return 0;
}
