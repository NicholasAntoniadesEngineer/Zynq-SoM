#include "schgen/component_basis.hpp"
#include <algorithm>
#include <iostream>
#include <stdexcept>

namespace {
using namespace schgen;
std::size_t checks = 0;
void require(bool b, const std::string& why) { ++checks; if(!b) throw std::runtime_error(why); }
const JsonNode& at(const JsonNode& n, const std::string& key) {
    const auto* v = object_field(n,key); if(!v) throw std::runtime_error(key); return *v;
}
}
int main(int argc, char** argv) {
    try {
        require(argc == 2,"usage: component_basis_contracts REPOSITORY");
        const std::filesystem::path root = argv[1];
        require(open_part_catalog((root/"native/catalog.bin").string()),"catalog");
        const auto live = author_component_basis_inputs(root);
        const auto& policy = default_component_basis_policy();
        const auto fixture = parse_json_file((root/"native/tests/data/component_basis/python_basis.json").string());
        require(live.size() == 66 && policy.sheets.size() == 66,"complete live coverage");
        require(policy.declarations.size() == 216 && policy.uses.size() == 685,"expectation coverage");
        std::size_t reviewed_basis_corrections = 0;
        for(const auto& row : at(fixture,"declarations").array_value) {
            const auto& a = row.array_value;
            const auto it = std::find_if(policy.declarations.begin(),policy.declarations.end(),
                [&](const auto& d) { return d.name == a[0].string_value; });
            require(it != policy.declarations.end(),"missing independently captured declaration");
            const auto value = a[1].kind == JsonKind::Number ? std::to_string(static_cast<int>(a[1].number_value)) : a[1].string_value;
            if(it->name == "carrier.board_aux.iso_en_pullup") {
                ++reviewed_basis_corrections;
                require(a[3].string_value == "Ties the PCA9306 EN to +3V3_AUX so the switch OPENS whenever the gated rail is down — that isolation is what stops the powered-down peripherals back-powering the always-on trunk through their ESD diodes (LAW 0). LCSC C25803." &&
                    a[4].string_value == "datasheet", "original unsupported isolation claim changed");
                require(it->value == value && it->unit == a[2].string_value && !it->numeric &&
                    it->klass == "policy" && it->basis ==
                    "R4 limits the PCA9306 VREF2 reference current from +3V3_AUX; EN directly follows AUX in switch mode. TI SCPS113O 8.1.5/8.1.8 permits separate enable control and lower reference resistance than 200k with increased bias current. Retained 100k C25803. Startup, shutdown and reverse rail isolation remain unqualified.",
                    "reviewed isolation uncertainty must not become a datasheet approval");
                continue;
            }
            require(it->value == value && it->unit == a[2].string_value &&
                it->basis == a[3].string_value && it->klass == a[4].string_value &&
                it->numeric == (a[1].kind == JsonKind::Number),"declaration differs from original Python");
        }
        require(reviewed_basis_corrections == 1, "exactly one reviewed basis correction");
        auto result = audit_component_basis(live);
        std::size_t reviewed_migrations = 0;
        for(const auto& row : at(fixture,"components").array_value) {
            const auto& a=row.array_value;
            if(a[5].string_value.empty()) continue; // numeric catalog identity, not a magnitude
            // Preserve the historical trace: only this independently reviewed
            // hardware correction may differ from its original binding.
            const bool c1 = a[0].string_value == "carrier" &&
                a[1].string_value == "board_aux" && a[2].string_value == "C1";
            const bool c5 = a[0].string_value == "carrier" &&
                a[1].string_value == "board_aux" && a[2].string_value == "C5";
            if(c1) {
                ++reviewed_migrations;
                require(a[3].string_value == "Device:C" && a[4].string_value == "100n" &&
                    a[5].string_value == "carrier.board_aux.decap", "original C1 trace changed");
            }
            if(c5) {
                ++reviewed_migrations;
                require(a[3].string_value=="Device:C"&&a[4].string_value=="100n"&&
                    a[5].string_value=="carrier.board_aux.decap","original C5 trace changed");
            }
            const auto match=std::find_if(policy.uses.begin(),policy.uses.end(),[&](const auto& u) {
                return u.scope==a[0].string_value && u.sheet==a[1].string_value &&
                    u.target==a[2].string_value && u.attribute=="value" &&
                    u.declaration==(c1 ? "carrier.board_aux.in_reservoir" : c5 ? "carrier.board_aux.reference_filter" : a[5].string_value) &&
                    u.type==a[3].string_value;
            });
            require(match!=policy.uses.end(),"obligation differs from independent Python trace");
        }
        require(reviewed_migrations == 2, "exactly two reviewed capacitor migrations");
        const auto filter=std::find_if(policy.declarations.begin(),policy.declarations.end(),
            [](const auto& d){return d.name=="carrier.board_aux.reference_filter";});
        require(filter!=policy.declarations.end()&&filter->value=="100p"&&filter->unit=="F"&&
            filter->klass=="datasheet"&&!filter->numeric&&filter->basis==
            "TI SCPS113O 11.1 specifies a 100pF filter near VREF2. Samsung CL10C101JB8NNNC, 0603 50 V C0G +/-5%, LCSC C14858. This filter and its reference-current limiter do not qualify power-transition isolation.","reviewed reference-filter basis");
        const auto reservoir = std::find_if(policy.declarations.begin(),policy.declarations.end(),
            [](const auto& d) { return d.name == "carrier.board_aux.in_reservoir"; });
        require(reservoir != policy.declarations.end(), "missing input reservoir declaration");
        require(reservoir->value == "10u" && reservoir->unit == "F" &&
            reservoir->klass == "datasheet" && !reservoir->numeric &&
            reservoir->basis == "SY6280 Rev.1.0E p.7 strongly recommends a 10uF ceramic VIN-to-GND supply filter for hot-plug droop and ringing. Nominal 10uF, 0805 25 V X5R, LCSC C15850; effective capacitance under DC bias is not established here.",
            "reviewed input reservoir specification changed");
        for(const auto& row : at(fixture,"policies").array_value) {
            const auto& a=row.array_value;
            require(std::any_of(policy.uses.begin(),policy.uses.end(),[&](const auto& u) {
                return u.scope==a[0].string_value && u.sheet==a[1].string_value &&
                    u.target==a[2].string_value && u.attribute==a[3].string_value &&
                    u.declaration==a[4].string_value && u.type==a[5].string_value;
            }),"port obligation differs from independent Python trace");
        }
        require(result.ok(), component_basis_report(result));
        require(result.n_files == 66 && result.n_registered == 216 && result.n_sites == 685,"audit counts");
        {
            auto old_c1 = live;
            auto& aux = std::find_if(old_c1.begin(),old_c1.end(),[](const auto& x) {
                return x.scope == "carrier" && x.sheet == "board_aux"; })->circuit;
            auto& c1 = *std::find_if(aux.parts.begin(),aux.parts.end(),[](const auto& x) { return x.ref == "C1"; });
            require(c1.value == "10u", "live C1 nominal value");
            c1.value = "100n";
            require(!audit_component_basis(old_c1).ok(), "accepted obsolete C1 value");
            auto old_binding = policy;
            auto& use = *std::find_if(old_binding.uses.begin(),old_binding.uses.end(),[](const auto& u) {
                return u.scope == "carrier" && u.sheet == "board_aux" && u.target == "C1"; });
            use.declaration = "carrier.board_aux.decap";
            require(!audit_component_basis(live,{"library","carrier","devkit_mini"},old_binding).ok(),
                "accepted obsolete C1 binding");
            auto missing = policy;
            missing.declarations.erase(std::remove_if(missing.declarations.begin(),missing.declarations.end(),
                [](const auto& d) { return d.name == "carrier.board_aux.in_reservoir"; }),missing.declarations.end());
            require(!audit_component_basis(live,{"library","carrier","devkit_mini"},missing).ok(),
                "accepted missing reservoir declaration");
        }
        // Mutate EVERY real obligation, not synthetic-only facsimiles. The
        // independently captured registry must detect each live construction drift.
        for(const auto& use : policy.uses) {
            auto changed = live;
            auto& c = std::find_if(changed.begin(),changed.end(),[&](const auto& x) {
                return x.scope == use.scope && x.sheet == use.sheet; })->circuit;
            if(use.attribute == "value") {
                auto p = std::find_if(c.parts.begin(),c.parts.end(),[&](const auto& x) { return x.ref == use.target; });
                p->value = "999Q";
            } else {
                auto p = std::find_if(c.port_types.begin(),c.port_types.end(),[&](const auto& x) { return x.net == use.target; });
                if(use.attribute == "speed_hz") ++p->speed_hz; else ++p->impedance;
            }
            require(!audit_component_basis(changed).ok(),"accepted live drift " + use.scope + "/" + use.sheet + "/" + use.target);
        }
        for(std::size_t i = 0; i < live.size(); ++i) {
            auto changed = live; changed.erase(changed.begin()+static_cast<std::ptrdiff_t>(i));
            require(!audit_component_basis(changed).ok(),"accepted missing sheet");
            changed = live;
            CircuitPartIr added; added.ref = "R9999"; added.lib_id = "Device:R"; added.value = "1k";
            changed[i].circuit.parts.push_back(added);
            require(!audit_component_basis(changed).ok(),"accepted undeclared passive");
        }
        auto changed = live; changed.push_back(live.front());
        require(!audit_component_basis(changed).ok(),"accepted duplicate sheet");
        changed = live;
        auto& parts = changed[0].circuit.parts;
        parts.erase(std::find_if(parts.begin(),parts.end(),[](const auto& x) { return x.ref == "R1"; }));
        require(!audit_component_basis(changed).ok(),"accepted missing expected part");
        changed = live;
        const auto& use = policy.uses.front();
        auto& c = std::find_if(changed.begin(),changed.end(),[&](const auto& x) { return x.scope == use.scope && x.sheet == use.sheet; })->circuit;
        auto part = std::find_if(c.parts.begin(),c.parts.end(),[&](const auto& x) { return x.ref == use.target; });
        part->lib_id = "Device:C";
        require(!audit_component_basis(changed).ok(),"accepted wrong component type");
        for(std::size_t i = 0; i < policy.declarations.size(); ++i) {
            auto p = policy; p.declarations[i].value += "?";
            require(!audit_component_basis(live,{"library","carrier","devkit_mini"},p).ok(),"accepted registration drift");
        }
        auto p = policy; p.declarations.push_back({"dead","1k","ohm","a reason for a resistor","policy",false,"contract"});
        require(!audit_component_basis(live,{"library","carrier","devkit_mini"},p).ok(),"dead registration");
        p = policy; p.uses.push_back(p.uses.front());
        require(!audit_component_basis(live,{"library","carrier","devkit_mini"},p).ok(),"duplicate obligation");
        p = policy; p.declarations[0].unit = "furlong";
        require(!audit_component_basis(live,{"library","carrier","devkit_mini"},p).ok(),"invalid unit");
        p = policy; p.declarations[0].basis = " ";
        require(!audit_component_basis(live,{"library","carrier","devkit_mini"},p).ok(),"empty rationale");
        p = policy; p.declarations[0].klass = "vibes";
        require(!audit_component_basis(live,{"library","carrier","devkit_mini"},p).ok(),"invalid source class");
        require(!audit_component_basis({},{}).ok(),"empty gate");
        std::cout << component_basis_report(result) << "\n" << checks << " component-basis contracts PASS\n";
        return 0;
    } catch(const std::exception& e) { std::cerr << e.what() << "\n"; return 1; }
}
