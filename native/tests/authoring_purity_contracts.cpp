#include "schgen/authoring_purity.hpp"
#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <stdexcept>

namespace {
std::size_t checks = 0;
void require(bool value, const std::string& message) {
    ++checks; if (!value) throw std::runtime_error(message);
}
bool has(const schgen::AuthoringPurityResult& r, const std::string& code) {
    return std::any_of(r.findings.begin(), r.findings.end(), [&](const auto& f) { return f.code == code; });
}
}
int main(int argc, char** argv) {
    try {
        if (argc < 3) throw std::runtime_error("usage: contracts REPOSITORY LIBCLANG [--show] [--system DIRECTORY]...");
        const auto root = std::filesystem::canonical(argv[1]) / "native/tests/data/authoring_purity";
        schgen::AuthoringPurityScope scope;
        scope.units = {"subject.cpp", "helper.cpp"}; scope.headers = {"api.hpp"}; scope.census_roots = {"."};
        scope.constructors = {"subject.cpp::schgen::circuit | schgen::CircuitSheetIr (const schgen::SubsystemMeta &, const schgen::AuthoringContext &)"};
        scope.infrastructure = {"api.hpp::schgen::net | void (schgen::CircuitSheetIr &)"};
        schgen::AuthoringPurityOptions options{argv[2], {}};
        bool show = false;
        for (int i = 3; i < argc; ++i) {
            const std::string flag = argv[i];
            if (flag == "--show") show = true;
            else if (flag == "--system" && i + 1 < argc) options.system_include_directories.push_back(argv[++i]);
            else throw std::runtime_error("unknown test argument " + flag);
        }
        const auto commands = [&](int example) {
            return std::vector<schgen::AuthoringPurityCommand>{{"subject.cpp", {"-DPURITY_CASE=" + std::to_string(example)}},
                                                             {"helper.cpp", {"-DPURITY_CASE=" + std::to_string(example)}}};
        };
        const auto run = [&](int example) {
            auto r = schgen::check_authoring_purity(root, scope, commands(example), options);
            if (show) std::cout << "CASE " << example << '\n' << r.report();
            return r;
        };
        auto good = run(0);
        require(good.ok(), "live parameterized netlist authoring rejected:\n" + good.report());
        require(good.parsed_units == 2 && good.checked_bodies >= 3 && good.checked_references > 0, "empty evidence cannot pass");
        auto expected = scope.infrastructure; expected.insert(expected.end(), scope.constructors.begin(), scope.constructors.end());
        std::sort(expected.begin(), expected.end());
        require(good.constructor_census == expected, "exact compiler constructor identity");
        auto algorithm = run(19);
        require(algorithm.ok(), "standard algorithm with visible pure callback rejected:\n" + algorithm.report());
        const std::vector<std::pair<int, std::string>> cases = {
            {1, "unreviewed-header"}, {2, "indirect-call"}, {3, "unreviewed-dependency"},
            {4, "unreviewed-header"}, {5, "unreviewed-dependency"}, {6, "unregistered-constructor"},
            {7, "unchecked-helper"}, {8, "indirect-call"}, {9, "virtual-call"},
            {10, "forbidden-declaration"}, {11, "forbidden-declaration"}, {12, "unreviewed-header"},
            {13, "indirect-call"}, {14, "forbidden-declaration"}, {15, "forbidden-entity"},
            {16, "unchecked-helper"}, {17, "unregistered-constructor"},
            {20, "forbidden-entity"}, {21, "opaque-operation"}, {22, "unreviewed-header"},
            {23, "forbidden-entity"}, {24, "forbidden-entity"}, {25, "unchecked-helper"},
            {26, "forbidden-declaration"}, {28, "unregistered-constructor"},
            {29, "unregistered-constructor"}, {30, "unchecked-helper"}, {32, "unresolved-call"},
            {35, "unreviewed-header"}, {36, "forbidden-entity"},
            {40, "unregistered-constructor"}, {41, "unregistered-constructor"}, {43, "unregistered-constructor"}
        };
        for (const auto& [example, code] : cases) {
            auto r = run(example);
            require(!r.ok() && has(r, code), "negative " + std::to_string(example) + " missing " + code + ":\n" + r.report());
            require(!has(r, "compiler-error") && !has(r, "incomplete-evidence"), "negative must be valid C++, not a parse failure:\n" + r.report());
        }
        // A user-defined std:: function is not accepted as an opaque external:
        // its actual body must be available in the audited source.
        require(run(18).ok(), "visible innocuous user function is checked by source, not trusted by namespace");
        require(run(31).ok(), "known cross-unit initializer must have checked compiler evidence");
        require(run(42).ok(), "read-only IR parameter is not a constructor result/output parameter");
        require(run(33).ok(), "ordinary standard-library IO is not a forbidden geometry API");
        require(run(34).ok(), "ordinary data-pointer conversion is not a geometry call");
        require(has(run(27), "compiler-error"), "compiler errors cannot pass");
        auto missing = commands(0); missing.pop_back();
        require(has(schgen::check_authoring_purity(root, scope, missing, options), "missing-command"), "new/unlisted source fails census completeness");
        auto unreviewed = scope; unreviewed.units.pop_back();
        require(has(schgen::check_authoring_purity(root, unreviewed, commands(5), options), "unchecked-helper"), "transitive helper in census-only file is not blessed");
        require(has(schgen::check_authoring_purity(root, unreviewed, commands(29), options), "unregistered-constructor"), "auto-return constructor in an unrelated existing source cannot escape census");
        auto provider = scope; provider.units = {"subject.cpp"}; provider.providers = {"helper.cpp"};
        require(schgen::check_authoring_purity(root, provider, commands(44), options).ok(),
                "reachable shared-provider bodies are checked without importing unrelated pipeline operations");
        require(has(schgen::check_authoring_purity(root, provider, commands(45), options), "unreviewed-dependency"),
                "provider role cannot waive a reachable geometric helper");
        require(has(schgen::check_authoring_purity(root, scope, commands(44), options), "unreviewed-header"),
                "authored modules still forbid geometry imports even when unused");
        auto stale = scope; stale.constructors[0] += " const";
        require(has(schgen::check_authoring_purity(root, stale, commands(0), options), "stale-constructor"), "stale registration fails");
        require(!schgen::check_authoring_purity(root, scope, commands(0), {"/nonexistent/libclang", {}}).ok(), "missing compiler cannot pass");
        auto malicious = commands(0); malicious[0].arguments.push_back("@hidden-flags");
        require(!schgen::check_authoring_purity(root, scope, malicious, options).ok(), "opaque response flags fail");
        auto broken = commands(0); broken[0].arguments.push_back("-include-not-supported");
        require(!schgen::check_authoring_purity(root, scope, broken, options).ok(), "injected front-end operations fail");
        auto delayed = commands(0); delayed[0].arguments.push_back("-fdelayed-template-parsing");
        require(!schgen::check_authoring_purity(root, scope, delayed, options).ok(), "delayed parsing cannot hide template bodies");
        auto mutable_scope = scope;
        mutable_scope.infrastructure.push_back("helper.cpp::new_factory_in_existing_non_authoring_file | schgen::CircuitSheetIr ()");
        auto classified = schgen::check_authoring_purity(root, mutable_scope, commands(29), options);
        require(classified.ok(), "explicit non-authoring IR classification is observed, not auto-inferred");
        // Classifications never suppress errors in their implementation/header closure.
        mutable_scope.infrastructure = scope.infrastructure;
        mutable_scope.infrastructure.push_back("subject.cpp::schgen::unregistered | schgen::CircuitSheetIr ()");
        require(has(schgen::check_authoring_purity(root, mutable_scope, commands(39), options), "forbidden-entity"),
                "infrastructure classification does not bless a geometric constructor implementation");
        auto disguised = scope; disguised.headers.push_back("system_disguise.hpp");
        require(has(schgen::check_authoring_purity(root, disguised, commands(22), options), "forbidden-declaration"), "pragma system_header cannot hide project code");
        auto capability=provider;
        capability.capabilities={{"api.hpp::schgen::AuthoringContext::part | std::function<int (int)>",
            scope.constructors[0],"helper.cpp::schgen::native_lookup | int (int)",
            "helper.cpp::schgen::require_context | void (const schgen::AuthoringContext &)"}};
        const auto cap=[&](int example) { return schgen::check_authoring_purity(root,capability,commands(example),options); };
        const auto named=cap(46);
        require(named.ok(),"named exact callback target and guard rejected:\n"+named.report());
        for (const auto& [example,code]:std::vector<std::pair<int,std::string>>{
            {47,"indirect-call"},{48,"indirect-call"},{49,"unreviewed-dependency"},
            {50,"unchecked-capability"},{51,"unchecked-capability"},{52,"capability-escape"},{55,"capability-escape"}}) {
            const auto r=cap(example);
            require(!r.ok() && has(r,code),"capability negative "+std::to_string(example)+" missing "+code+":\n"+r.report());
            require(!has(r,"compiler-error"),"capability negative must compile");
        }
        auto wrong_target=capability; wrong_target.capabilities[0].target+=" const";
        require(has(schgen::check_authoring_purity(root,wrong_target,commands(46),options),"unchecked-capability"),"changed named target cannot be accepted");
        require(has(schgen::check_authoring_purity(root,capability,commands(0),options),"stale-capability"),"missing field/site cannot be accepted");
        auto private_header=scope; private_header.provider_headers={"geometry.hpp"};
        require(has(schgen::check_authoring_purity(root,private_header,commands(1),options),"private-provider-api"),"constructor cannot directly consume private provider headers");
        std::cout << "authoring purity: " << checks << " contracts PASS\n";
        return EXIT_SUCCESS;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return EXIT_FAILURE; }
}
