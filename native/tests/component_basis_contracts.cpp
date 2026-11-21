#include "schgen/component_basis.hpp"
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <unistd.h>

namespace {
using namespace schgen;
std::size_t checks = 0;
void require(bool b, const std::string& why) { ++checks; if(!b) throw std::runtime_error(why); }
const JsonNode& at(const JsonNode& n, const std::string& key) {
    const auto* v = object_field(n,key); if(!v) throw std::runtime_error(key); return *v;
}
const std::string schema_line = "\"schema\":\"schgen.component_basis/1\"";
const std::string declaration_row = "{\"name\":\"d.one\",\"value\":\"1k\",\"unit\":\"ohm\",\"basis\":\"reason\",\"class\":\"policy\",\"numeric\":false}";
const std::string library_use = "{\"sheet\":\"s\",\"target\":\"R1\",\"attribute\":\"value\",\"declaration\":\"d.one\",\"type\":\"Device:R\"}";
const std::string board_use = "{\"sheet\":\"b\",\"target\":\"R1\",\"attribute\":\"value\",\"declaration\":\"d.one\",\"type\":\"Device:R\"}";
const char* const loader_board = "board_x";
const char* const loader_file = "component_basis.json";
std::string library_text(const std::string& declarations, const std::string& uses, const std::string& sheets) {
    return "{" + schema_line + ",\"declarations\":" + declarations + ",\"uses\":" + uses + ",\"sheets\":" + sheets + ",\"board_scope_only\":[\"b\"]}";
}
std::string board_text(const std::string& uses, const std::string& sheets) {
    return "{" + schema_line + ",\"uses\":" + uses + ",\"sheets\":" + sheets + "}";
}
const std::string valid_library = library_text("[" + declaration_row + "]", "[" + library_use + "]", "[\"s\"]");
const std::string valid_board = board_text("[" + board_use + "]", "[\"b\"]");
void put_file(const std::filesystem::path& path, const std::string& text) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream(path, std::ios::binary) << text;
}
std::string replaced(std::string text, const std::string& from, const std::string& to) {
    const auto at_ = text.find(from);
    require(at_ != std::string::npos, "mutation target absent: " + from);
    return text.replace(at_, from.size(), to);
}
void loader_rejects(const std::filesystem::path& scratch, const std::string& library, const std::string& board,
                    const std::string& needle, const std::string& file_name, const std::string& row = "") {
    std::filesystem::remove_all(scratch);
    put_file(scratch / "subsystems" / loader_file, library);
    put_file(scratch / loader_board / "board.json", "{}");
    put_file(scratch / loader_board / loader_file, board);
    bool thrown = false;
    try { (void)load_component_basis_policy(scratch); }
    catch(const std::runtime_error& error) {
        const std::string message = error.what();
        thrown = message.find(needle) != std::string::npos;
        require(thrown, "expected '" + needle + "', got: " + message);
        require(message.find(file_name) != std::string::npos, "the message names the file: " + message);
        require(row.empty() || message.find(row) != std::string::npos, "the message names the row: " + message);
    }
    require(thrown, "loader accepted: expected '" + needle + "'");
}
}
int main(int argc, char** argv) {
    try {
        require(argc == 2,"usage: component_basis_contracts REPOSITORY");
        const std::filesystem::path root = argv[1];
        require(open_part_catalog((root/"native/catalog.bin").string()),"catalog");
        const auto policy = load_component_basis_policy(root);
        const auto scopes = component_basis_scopes(root);
        const auto live = author_component_basis_inputs(root,policy);
        for(const auto* board : {"carrier","devkit_mini"}) {
            const auto one = single_basis_board(root / board);
            const auto board_policy = load_component_basis_policy(root, one);
            const auto board_result = audit_component_basis(author_component_basis_inputs(root, one, board_policy), component_basis_scopes(one), board_policy);
            require(board_result.ok(), std::string("a single-board audit passes for ") + board + ": " + component_basis_report(board_result));
        }
        const auto fixture = parse_json_file((root/"native/tests/data/component_basis/python_basis.json").string());
        require(live.size() == 66 && policy.sheets.size() == 66,"complete live coverage");
        require(policy.declarations.size() == 212 && policy.uses.size() == 681,"expectation coverage");
        const std::vector<std::string> retired={"carrier.power_som.en_series_r","carrier.power_som.en_bypass","devkit_mini.power_som.en_series_r","devkit_mini.power_som.en_bypass"};
        std::size_t reviewed_basis_corrections = 0,retired_declarations=0,retired_uses=0;
        for(const auto& row : at(fixture,"declarations").array_value) {
            const auto& a = row.array_value;
            const auto it = std::find_if(policy.declarations.begin(),policy.declarations.end(),
                [&](const auto& d) { return d.name == a[0].string_value; });
            if(std::find(retired.begin(),retired.end(),a[0].string_value)!=retired.end()){
                require(it==policy.declarations.end(),"removed enable component kept a stale declaration");
                ++retired_declarations;continue;
            }
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
        require(retired_declarations==4,"exactly four retired enable declarations");
        auto result = audit_component_basis(live,scopes,policy);
        std::size_t reviewed_migrations = 0;
        for(const auto& row : at(fixture,"components").array_value) {
            const auto& a=row.array_value;
            if(a[5].string_value.empty()) continue; // numeric catalog identity, not a magnitude
            if(std::find(retired.begin(),retired.end(),a[5].string_value)!=retired.end()){
                require(std::none_of(policy.uses.begin(),policy.uses.end(),[&](const auto& u){return u.scope==a[0].string_value&&u.sheet==a[1].string_value&&u.target==a[2].string_value;}),
                        "removed enable part kept a stale value binding");
                ++retired_uses;continue;
            }
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
        require(retired_uses==4,"exactly four retired enable uses");
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
        require(result.n_files == 66 && result.n_registered == 212 && result.n_sites == 681,"audit counts");
        {
            auto old_c1 = live;
            auto& aux = std::find_if(old_c1.begin(),old_c1.end(),[](const auto& x) {
                return x.scope == "carrier" && x.sheet == "board_aux"; })->circuit;
            auto& c1 = *std::find_if(aux.parts.begin(),aux.parts.end(),[](const auto& x) { return x.ref == "C1"; });
            require(c1.value == "10u", "live C1 nominal value");
            c1.value = "100n";
            require(!audit_component_basis(old_c1,scopes,policy).ok(), "accepted obsolete C1 value");
            auto old_binding = policy;
            auto& use = *std::find_if(old_binding.uses.begin(),old_binding.uses.end(),[](const auto& u) {
                return u.scope == "carrier" && u.sheet == "board_aux" && u.target == "C1"; });
            use.declaration = "carrier.board_aux.decap";
            require(!audit_component_basis(live,scopes,old_binding).ok(),
                "accepted obsolete C1 binding");
            auto missing = policy;
            missing.declarations.erase(std::remove_if(missing.declarations.begin(),missing.declarations.end(),
                [](const auto& d) { return d.name == "carrier.board_aux.in_reservoir"; }),missing.declarations.end());
            require(!audit_component_basis(live,scopes,missing).ok(),
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
            require(!audit_component_basis(changed,scopes,policy).ok(),"accepted live drift " + use.scope + "/" + use.sheet + "/" + use.target);
        }
        for(std::size_t i = 0; i < live.size(); ++i) {
            auto changed = live; changed.erase(changed.begin()+static_cast<std::ptrdiff_t>(i));
            require(!audit_component_basis(changed,scopes,policy).ok(),"accepted missing sheet");
            changed = live;
            CircuitPartIr added; added.ref = "R9999"; added.lib_id = "Device:R"; added.value = "1k";
            changed[i].circuit.parts.push_back(added);
            require(!audit_component_basis(changed,scopes,policy).ok(),"accepted undeclared passive");
        }
        auto changed = live; changed.push_back(live.front());
        require(!audit_component_basis(changed,scopes,policy).ok(),"accepted duplicate sheet");
        changed = live;
        auto& parts = changed[0].circuit.parts;
        parts.erase(std::find_if(parts.begin(),parts.end(),[](const auto& x) { return x.ref == "R1"; }));
        require(!audit_component_basis(changed,scopes,policy).ok(),"accepted missing expected part");
        changed = live;
        const auto& use = policy.uses.front();
        auto& c = std::find_if(changed.begin(),changed.end(),[&](const auto& x) { return x.scope == use.scope && x.sheet == use.sheet; })->circuit;
        auto part = std::find_if(c.parts.begin(),c.parts.end(),[&](const auto& x) { return x.ref == use.target; });
        part->lib_id = "Device:C";
        require(!audit_component_basis(changed,scopes,policy).ok(),"accepted wrong component type");
        for(std::size_t i = 0; i < policy.declarations.size(); ++i) {
            auto p = policy; p.declarations[i].value += "?";
            require(!audit_component_basis(live,scopes,p).ok(),"accepted registration drift");
        }
        auto p = policy; p.declarations.push_back({"dead","1k","ohm","a reason for a resistor","policy",false,"contract"});
        require(!audit_component_basis(live,scopes,p).ok(),"dead registration");
        p = policy; p.uses.push_back(p.uses.front());
        require(!audit_component_basis(live,scopes,p).ok(),"duplicate obligation");
        p = policy; p.declarations[0].unit = "furlong";
        require(!audit_component_basis(live,scopes,p).ok(),"invalid unit");
        p = policy; p.declarations[0].basis = " ";
        require(!audit_component_basis(live,scopes,p).ok(),"empty rationale");
        p = policy; p.declarations[0].klass = "vibes";
        require(!audit_component_basis(live,scopes,p).ok(),"invalid source class");
        require(!audit_component_basis({},{},policy).ok(),"empty gate");
        {
            const auto library = subsystem_library(make_authoring_context(root));
            const auto& only = policy.board_scope_only;
            std::size_t listed = 0;
            for(const auto& d : library) {
                const bool in_sheets = std::any_of(policy.sheets.begin(),policy.sheets.end(),[&](const auto& s) { return s.scope == "library" && s.name == d.name; });
                const bool in_only = std::find(only.begin(),only.end(),d.name) != only.end();
                require(in_sheets != in_only,"library subsystem accounted for exactly once: " + d.name);
                listed += in_sheets ? 1 : 0;
            }
            require(listed + only.size() == library.size(),"every library subsystem is accounted for");
            const auto fails = [&](const ComponentBasisPolicy& changed, const std::string& needle, const std::string& why) {
                bool thrown = false;
                try { (void)author_component_basis_inputs(root,changed); }
                catch(const std::runtime_error& error) {
                    const std::string message = error.what();
                    thrown = message.find(needle) != std::string::npos && message.find("subsystems/component_basis.json") != std::string::npos;
                    require(thrown,why + ": " + message);
                }
                require(thrown,why);
            };
            const auto first_listed = std::find_if(policy.sheets.begin(),policy.sheets.end(),[](const auto& s) { return s.scope == "library"; })->name;
            auto changed = policy;
            changed.sheets.erase(std::find_if(changed.sheets.begin(),changed.sheets.end(),[&](const auto& s) { return s.scope == "library" && s.name == first_listed; }));
            fails(changed,"library subsystem " + first_listed + " is neither in sheets nor in board_scope_only of","unaccounted library subsystem");
            changed = policy; changed.board_scope_only.push_back(first_listed);
            fails(changed,"library subsystem " + first_listed + " is in both sheets and board_scope_only of","doubly accounted library subsystem");
            changed = policy; changed.board_scope_only.push_back("not_a_subsystem");
            fails(changed,"board_scope_only names not_a_subsystem","board_scope_only names no library subsystem");
            changed = policy; changed.sheets.push_back({"library","not_a_subsystem"});
            fails(changed,"sheets names not_a_subsystem","sheets names no library subsystem");
        }
        {
            const auto scratch = std::filesystem::temp_directory_path() / ("component_basis_loader_" + std::to_string(::getpid()));
            const std::string lib = "subsystems/" + std::string(loader_file), brd = std::string(loader_board) + "/" + loader_file;
            std::filesystem::remove_all(scratch);
            put_file(scratch / "subsystems" / loader_file, valid_library);
            put_file(scratch / loader_board / "board.json", "{}");
            put_file(scratch / loader_board / loader_file, valid_board);
            const auto small = load_component_basis_policy(scratch);
            require(small.declarations.size() == 1 && small.uses.size() == 2 && small.sheets.size() == 2,"loader counts");
            require(small.declarations[0].site == lib + ":d.one","loader site");
            require(small.uses[0].scope == "library" && small.uses[1].scope == loader_board && small.sheets[1].scope == loader_board,"loader scopes");
            require(component_basis_scopes(scratch) == std::set<std::string>{"library",loader_board},"scope set");
            put_file(scratch / "broken_board" / "board.json", "{}");
            put_file(scratch / "broken_board" / loader_file, "{\"schema\": \"schgen.component_basis/2\"}");
            bool every_board_fails = false;
            try { (void)load_component_basis_policy(scratch); }
            catch(const std::runtime_error& error) { every_board_fails = std::string(error.what()).find("broken_board") != std::string::npos; }
            require(every_board_fails,"the every-board audit judges every board folder");
            const auto alone = load_component_basis_policy(scratch, single_basis_board(scratch / loader_board));
            require(!alone.every_board && alone.sheets.size() == 2 && component_basis_scopes(single_basis_board(scratch / loader_board)) == std::set<std::string>{"library",loader_board},
                    "a board's audit reads only the library and that board, so another board's mistake cannot fail it");
            std::filesystem::remove_all(scratch / "broken_board");
            for(const auto& declaration : policy.declarations)
                require(declaration.site == "subsystems/component_basis.json:" + declaration.name,"production site form");
            std::filesystem::remove(scratch / "subsystems" / loader_file);
            bool missing_library = false;
            try { (void)load_component_basis_policy(scratch); }
            catch(const std::runtime_error& error) { missing_library = std::string(error.what()).find(lib) != std::string::npos; }
            require(missing_library,"missing library file");
            put_file(scratch / "subsystems" / loader_file, valid_library);
            std::filesystem::remove(scratch / loader_board / loader_file);
            bool missing_board = false;
            try { (void)load_component_basis_policy(scratch); }
            catch(const std::runtime_error& error) { missing_board = std::string(error.what()).find(brd) != std::string::npos; }
            require(missing_board,"missing board file");
            const auto lib_with = [&](const std::string& from, const std::string& to) { return replaced(valid_library, from, to); };
            const auto brd_with = [&](const std::string& from, const std::string& to) { return replaced(valid_board, from, to); };
            const std::string decl_row = "declarations row 1", use_row = "uses row 1", sheet_row = "sheets row 1";
            loader_rejects(scratch, lib_with("component_basis/1", "component_basis/2"), valid_board, "schema must be", lib);
            loader_rejects(scratch, lib_with(schema_line + ",", ""), valid_board, "missing required field 'schema'", lib);
            loader_rejects(scratch, valid_library, brd_with("component_basis/1", "component_basis/2"), "schema must be", brd);
            loader_rejects(scratch, lib_with("{\"schema\"", "{\"extra\":1,\"schema\""), valid_board, "unknown key 'extra'", lib);
            loader_rejects(scratch, valid_library, brd_with("{\"schema\"", "{\"declarations\":[],\"schema\""), "unknown key 'declarations'", brd);
            loader_rejects(scratch, valid_library, brd_with("{\"schema\"", "{\"extra\":1,\"schema\""), "unknown key 'extra'", brd);
            loader_rejects(scratch, lib_with(",\"declarations\":[" + declaration_row + "]", ""), valid_board, "missing required field 'declarations'", lib);
            loader_rejects(scratch, lib_with("\"declarations\":[" + declaration_row + "]", "\"declarations\":3"), valid_board, "must be an array", lib);
            loader_rejects(scratch, lib_with(",\"uses\":[" + library_use + "]", ""), valid_board, "missing required field 'uses'", lib);
            loader_rejects(scratch, lib_with(",\"sheets\":[\"s\"]", ""), valid_board, "missing required field 'sheets'", lib);
            loader_rejects(scratch, valid_library, brd_with(",\"sheets\":[\"b\"]", ""), "missing required field 'sheets'", brd);
            loader_rejects(scratch, valid_library, brd_with("\"sheets\":[\"b\"]", "\"sheets\":\"b\""), "must be an array", brd);
            loader_rejects(scratch, valid_library, brd_with("\"uses\":[" + board_use + "]", "\"uses\":3"), "must be an array", brd);
            loader_rejects(scratch, lib_with("\"declarations\":[" + declaration_row + "]", "\"declarations\":[3]"), valid_board, "must be an object", lib, decl_row);
            loader_rejects(scratch, lib_with("\"unit\":\"ohm\",", ""), valid_board, "missing required field 'unit'", lib, decl_row);
            loader_rejects(scratch, lib_with("\"name\":\"d.one\"", "\"name\":\"\""), valid_board, "must not be empty", lib, decl_row);
            loader_rejects(scratch, lib_with("\"value\":\"1k\"", "\"value\":3"), valid_board, "must be a string", lib, decl_row);
            loader_rejects(scratch, lib_with("\"basis\":\"reason\"", "\"basis\":\"\""), valid_board, "must not be empty", lib, decl_row);
            loader_rejects(scratch, lib_with("\"class\":\"policy\"", "\"klass\":\"policy\""), valid_board, "unknown key 'klass'", lib, decl_row);
            loader_rejects(scratch, lib_with(",\"numeric\":false", ""), valid_board, "missing required field 'numeric'", lib, decl_row);
            loader_rejects(scratch, lib_with("\"numeric\":false", "\"numeric\":\"no\""), valid_board, "must be a boolean", lib, decl_row);
            loader_rejects(scratch, lib_with("[" + declaration_row + "]", "[" + declaration_row + "," + declaration_row + "]"), valid_board, "listed twice", lib, "declarations row 2");
            loader_rejects(scratch, lib_with("\"sheets\":[\"s\"]", "\"sheets\":[\"\"]"), valid_board, "must not be empty", lib, sheet_row);
            loader_rejects(scratch, lib_with("\"sheets\":[\"s\"]", "\"sheets\":[3]"), valid_board, "must be a string", lib, sheet_row);
            loader_rejects(scratch, lib_with("\"sheets\":[\"s\"]", "\"sheets\":[\"s\",\"s\"]"), valid_board, "listed twice", lib, "sheets row 2");
            loader_rejects(scratch, lib_with("\"target\":\"R1\"", "\"target\":\"\""), valid_board, "must not be empty", lib, use_row);
            loader_rejects(scratch, lib_with("\"type\":\"Device:R\"", "\"type\":4"), valid_board, "must be a string", lib, use_row);
            loader_rejects(scratch, lib_with("\"attribute\":\"value\",", ""), valid_board, "missing required field 'attribute'", lib, use_row);
            loader_rejects(scratch, lib_with("\"sheet\":\"s\"", "\"sheet\":\"t\""), valid_board, "not in this file's sheets", lib, use_row);
            loader_rejects(scratch, lib_with("\"declaration\":\"d.one\"", "\"declaration\":\"d.two\""), valid_board, "does not exist", lib, use_row);
            loader_rejects(scratch, lib_with("\"sheet\":\"s\"", "\"sheet\":\"s\",\"scope\":\"x\""), valid_board, "unknown key 'scope'", lib, use_row);
            loader_rejects(scratch, valid_library, brd_with("\"sheet\":\"b\"", "\"sheet\":\"c\""), "not in this file's sheets", brd, use_row);
            loader_rejects(scratch, valid_library, brd_with("\"declaration\":\"d.one\"", "\"declaration\":\"d.two\""), "does not exist", brd, use_row);
            loader_rejects(scratch, valid_library, brd_with("\"sheets\":[\"b\"]", "\"sheets\":[\"b\",\"b\"]"), "listed twice", brd, "sheets row 2");
            loader_rejects(scratch, lib_with(",\"board_scope_only\":[\"b\"]", ""), valid_board, "missing required field 'board_scope_only'", lib);
            loader_rejects(scratch, lib_with("\"board_scope_only\":[\"b\"]", "\"board_scope_only\":\"b\""), valid_board, "must be an array", lib);
            loader_rejects(scratch, lib_with("\"board_scope_only\":[\"b\"]", "\"board_scope_only\":[3]"), valid_board, "must be a string", lib, "board_scope_only row 1");
            loader_rejects(scratch, lib_with("\"board_scope_only\":[\"b\"]", "\"board_scope_only\":[\"\"]"), valid_board, "must not be empty", lib, "board_scope_only row 1");
            loader_rejects(scratch, lib_with("\"board_scope_only\":[\"b\"]", "\"board_scope_only\":[\"b\",\"b\"]"), valid_board, "listed twice", lib, "board_scope_only row 2");
            loader_rejects(scratch, lib_with("\"board_scope_only\":[\"b\"]", "\"board_scope_only\":[\"b\",\"nowhere\"]"), valid_board, "nowhere is in the sheets of no board", lib);
            loader_rejects(scratch, valid_library, brd_with("{\"schema\"", "{\"board_scope_only\":[],\"schema\""), "unknown key 'board_scope_only'", brd);
            std::filesystem::remove_all(scratch);
        }
        std::cout << component_basis_report(result) << "\n" << checks << " component-basis contracts PASS\n";
        return 0;
    } catch(const std::exception& e) { std::cerr << e.what() << "\n"; return 1; }
}
