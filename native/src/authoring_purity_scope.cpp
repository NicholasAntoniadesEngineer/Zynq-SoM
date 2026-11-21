#include "schgen/authoring_purity.hpp"

namespace schgen {
AuthoringPurityScope native_authoring_purity_scope() {
    AuthoringPurityScope s;
    const std::string signature = " | schgen::CircuitSheetIr (const schgen::SubsystemMeta &, const schgen::AuthoringContext &)";
    // Reviewed named constructors; never inferred from whatever files happen to
    // exist. New files and overloads require explicit review plus live checking.
    for (const auto* name : {"authoring", "authoring_ir", "circuit_helpers", "subsystem_authoring", "subsystem_authoring_data",
            "subsystem_registration", "project_authoring"})
        s.units.push_back(std::string("native/src/") + name + ".cpp");
    for (const auto* name : {"json", "circuit", "circuit_layout", "roles", "catalog", "link", "som_interface", "authoring_context", "symbols", "sexpr",
            "occupancy", "board_definition"})
        s.providers.push_back(std::string("native/src/") + name + ".cpp");
    for (const auto* name : {"authoring_context", "symbols", "sexpr", "occupancy", "turn", "seat", "quantize", "execution_accounting", "roles",
            "named_constant"})
        s.provider_headers.push_back(std::string("native/include/schgen/") + name + ".hpp");
    const std::string guard="native/src/authoring_context.cpp::schgen::require_native_authoring_context | void (const schgen::AuthoringContext &)";
    s.capabilities = {
        {"native/include/schgen/authoring.hpp::schgen::AuthoringContext::part | std::function<schgen::CatalogPart (const std::string &)>",
         "native/src/authoring.cpp::schgen::CircuitAuthor::use_part | std::string (const std::string &, const schgen::AuthoringPartSelection &)",
         "native/src/catalog.cpp::schgen::lookup_part_catalog | schgen::CatalogPart (const std::string &)",guard},
        {"native/include/schgen/authoring.hpp::schgen::AuthoringContext::pins | std::function<std::optional<std::set<std::string>> (const std::string &)>",
         "native/src/authoring.cpp::schgen::CircuitAuthor::expand_pin | std::vector<schgen::CircuitPinRefIr> (const std::string &) const",
         "native/src/authoring_context.cpp::schgen::NativeAuthoringPinResolver::operator() | std::optional<std::set<std::string>> (const std::string &) const",guard}
    };
    // Constructor include closure excludes geometry, model_checks_internal,
    // subsystem_build, and the mixed example build umbrella. Provider-only
    // headers above are not imported or directly callable by constructor units.
    for (const auto* name : {"authoring", "circuit_helpers", "catalog", "circuit", "json", "subsystem_authoring", "subsystem_data",
            "subsystem_registration", "project_authoring", "board_definition", "authoring_gates", "link", "som_interface", "xdc"})
        s.headers.push_back(std::string("native/include/schgen/") + name + ".hpp");
    s.headers.push_back("native/src/authoring_values.hpp");
    s.constructors.push_back("native/src/subsystem_authoring.cpp::schgen::author_subsystem | schgen::CircuitSheetIr (const std::string &, const schgen::SubsystemMeta &, const schgen::AuthoringContext &)");
    s.constructors.push_back("native/src/subsystem_authoring_data.cpp::schgen::extend_subsystem_data | schgen::CircuitSheetIr (schgen::CircuitSheetIr, const schgen::JsonNode &, const schgen::AuthoringContext &)");
    s.constructors.push_back("native/src/subsystem_authoring_data.cpp::schgen::author_subsystem_data | schgen::CircuitSheetIr (const schgen::JsonNode &, const schgen::SubsystemMeta &, const schgen::AuthoringContext &)");
    s.constructors.push_back("native/src/project_authoring.cpp::schgen::author_project_subsystem | schgen::CircuitSheetIr (const std::string &, const std::string &, const schgen::ProjectAuthoringInput &)");
    s.constructors.push_back("native/src/project_authoring.cpp::schgen::author_som_connector | schgen::CircuitSheetIr (const std::string &, const std::string &, const std::string &, const schgen::SomInterface &, const schgen::LinkMapping &, const schgen::ConnectorAuthoringPolicy &, const schgen::AuthoringContext &)");
    // Canonical type strings depend on the configured standard library. The
    // initial catalog below is validated on Apple Clang/libc++; other toolchains
    // must supply a separately reviewed manifest, not normalize away overloads.
    s.infrastructure = {
        "native/include/schgen/authoring.hpp::schgen::CircuitAuthor::view | const schgen::CircuitSheetIr &() const",
        "native/include/schgen/circuit.hpp::schgen::CircuitSheetIr::operator= | schgen::CircuitSheetIr &(schgen::CircuitSheetIr &&) noexcept",
        "native/src/authoring.cpp::schgen::CircuitAuthor::finish | schgen::CircuitSheetIr () const",
        "native/src/authoring.cpp::schgen::CircuitAuthor::subset | schgen::CircuitSheetIr (const std::set<std::string> &, int) const",
        "native/src/authoring.cpp::schgen::SubsystemMeta::finish | schgen::CircuitSheetIr (schgen::CircuitAuthor &) const",
        "native/src/circuit_helpers.cpp::schgen::add_mounting_hole | schgen::CircuitPartIr (schgen::CircuitSheetIr &, const std::string &, const std::optional<std::string> &)",
        "native/src/circuit.cpp::schgen::parse_circuit_ir | schgen::CircuitSheetIr (const schgen::JsonNode &)",
        "native/src/subsystem_authoring_data.cpp::schgen::add_part | void (schgen::CircuitAuthor &, const schgen::JsonNode &, const std::string &)",
        "native/src/subsystem_authoring_data.cpp::schgen::add_port | void (schgen::CircuitAuthor &, const schgen::JsonNode &, const schgen::SubsystemMeta &, const std::string &)",
        "native/src/subsystem_authoring_data.cpp::schgen::add_purpose | void (schgen::CircuitAuthor &, const schgen::JsonNode &, const std::string &)",
        "native/src/subsystem_authoring_data.cpp::schgen::apply_sections | void (schgen::CircuitAuthor &, const schgen::JsonNode &, const schgen::SubsystemMeta &, const std::string &, bool)",
        "native/src/circuit.cpp::schgen::parse_sheet_ir | schgen::CircuitSheetIr (const schgen::JsonNode &)",
        "native/src/circuit.cpp::schgen::decode_intermediate_circuit_ir | schgen::CircuitSheetIr (const schgen::JsonNode &)"
    };
    // Reviewed census roles, NOT allowed constructor dependencies. These are
    // parsers/catalog transports, read-only document indexes, post-authoring
    // page partitioners, and deliberately invalid selftest fixtures/mutations.
    // Their sources/headers are not added to the constructor helper closure.
    for (const auto* identity : {
        "native/src/circuit.cpp::schgen::load_circuit_json | schgen::CircuitSheetIr (const std::filesystem::path &)",
        "native/src/circuit.cpp::schgen::lookup_circuit_catalog | schgen::CircuitSheetIr (const std::string &)",
        "native/src/copper_debt.cpp::schgen::sheet | const schgen::CircuitSheetIr &(const schgen::CopperDebtSources &, const std::string &, const std::string &)",
        "native/src/schematic_place_pages.cpp::schgen::schematic_place::split_auxiliary | std::pair<schgen::CircuitSheetIr, std::vector<std::string>> (const schgen::CircuitSheetIr &)",
        "native/src/schematic_place_pages.cpp::schgen::schematic_place::subset_page | schgen::CircuitSheetIr (const schgen::CircuitSheetIr &, const std::set<std::string> &, int)",
        "native/src/schematic_place_pages.cpp::schgen::schematic_place::partition_pages_with_fit | std::vector<schgen::CircuitSheetIr> (const schgen::CircuitSheetIr &, schgen::SymbolLibrary &, const std::function<bool (const schgen::CircuitSheetIr &)> &)",
        "native/src/schematic_place_pages.cpp::schgen::schematic_place::partition_pages | std::vector<schgen::CircuitSheetIr> (const schgen::CircuitSheetIr &, schgen::SymbolLibrary &, std::map<std::string, unsigned long> *)",
        "native/src/schematic_place_pages.cpp::schgen::partition_schematic_pages | std::vector<schgen::CircuitSheetIr> (const schgen::CircuitSheetIr &, schgen::SymbolLibrary &, std::map<std::string, unsigned long> *)",
        "native/src/selftest.cpp::schgen::selftest_rail_decoupling_fixture | schgen::CircuitSheetIr ()",
        "native/src/selftest.cpp::schgen::selftest_esd_clamp_fixture | schgen::CircuitSheetIr ()",
        "native/src/selftest_full_models.cpp::schgen::delete_part | void (schgen::CircuitSheetIr &, const std::string &)",
        "native/src/selftest_full_models.cpp::schgen::erase_pin | void (schgen::CircuitSheetIr &, const schgen::CircuitPinRefIr &)",
        "native/src/selftest_full_models.cpp::schgen::load | void (schgen::CircuitSheetIr &, double, const std::string &)"
    }) s.infrastructure.push_back(identity);
    for (const auto* name : {"fixture_design_rules", "fixture_ep", "fixture_buck", "fixture_testpoints",
            "fixture_mounting_hole", "fixture_board_0", "fixture_board_1", "selftest_rc_fixture"})
        s.infrastructure.push_back(std::string("native/src/selftest_full_fixtures.cpp::schgen::") + name + " | schgen::CircuitSheetIr ()");
    // Includes non-authoring sources in the CENSUS, not in the allowed helper
    // closure. Parent must supply their real front-end arguments. Any additional
    // IR-returning transport/parser definitions require explicit classification.
    s.census_roots = {"native/src"};
    return s;
}
} // namespace schgen
