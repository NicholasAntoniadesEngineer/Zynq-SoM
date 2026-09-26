#include "schgen/authoring_purity.hpp"

namespace schgen {
AuthoringPurityScope native_authoring_purity_scope() {
    AuthoringPurityScope s;
    const std::string signature = " | schgen::CircuitSheetIr (const schgen::SubsystemMeta &, const schgen::AuthoringContext &)";
    // Reviewed named constructors; never inferred from whatever files happen to
    // exist. New files and overloads require explicit review plus live checking.
    for (const auto* name : {"camera", "ethernet", "hdmi_rx", "hdmi_tx", "lcd", "microsd", "pd_input",
            "pmod", "pmod_expansion", "power", "rj45_connector", "uart_bridge", "usb_jtag",
            "usb_jtag_connector", "usb_pd", "usb_uart_connector", "usbc_otg"}) {
        const auto file = std::string("native/src/subsystem_authoring_") + name + ".cpp";
        s.units.push_back(file);
        s.constructors.push_back(file + "::schgen::subsystem_builders::" + name + signature);
    }
    for (const auto* name : {"carrier_board_aux", "carrier_board_qwiic", "carrier_board_services",
            "carrier_bringup_en", "carrier_bringup_en_modules", "carrier_bringup_modules", "carrier_bringup_rails",
            "carrier_debug_boot", "carrier_fmc", "carrier_hdmi_rx_term", "carrier_mechanical", "carrier_motor_pwm",
            "carrier_motor_sense", "carrier_power_mon", "carrier_power_som", "carrier_som_decoupling", "carrier_user_io",
            "devkit_mini_debug_boot", "devkit_mini_mechanical", "devkit_mini_power_mon", "devkit_mini_power_som",
            "devkit_mini_som_decoupling"}) {
        const auto file = std::string("native/src/project_authoring_") + name + ".cpp";
        s.units.push_back(file);
        s.constructors.push_back(file + "::schgen::project_builders::" + name + signature);
    }
    for (const auto* name : {"authoring", "authoring_ir", "circuit_helpers", "subsystem_authoring",
            "subsystem_registration", "project_authoring", "project_authoring_registry", "example_devkit"})
        s.units.push_back(std::string("native/src/") + name + ".cpp");
    for (const auto* name : {"json", "circuit", "catalog", "link", "som_interface", "authoring_context", "symbols", "sexpr", "occupancy"})
        s.providers.push_back(std::string("native/src/") + name + ".cpp");
    for (const auto* name : {"authoring_context", "symbols", "sexpr", "occupancy", "turn", "seat", "quantize", "execution_accounting"})
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
    for (const auto* name : {"authoring", "circuit_helpers", "catalog", "circuit", "json", "subsystem_authoring",
            "subsystem_registration", "project_authoring", "authoring_gates", "link", "som_interface", "xdc", "example_devkit_authoring"})
        s.headers.push_back(std::string("native/include/schgen/") + name + ".hpp");
    s.headers.push_back("native/src/authoring_values.hpp");
    s.constructors.push_back("native/src/subsystem_authoring.cpp::schgen::author_subsystem | schgen::CircuitSheetIr (const std::string &, const schgen::SubsystemMeta &, const schgen::AuthoringContext &)");
    s.constructors.push_back("native/src/project_authoring.cpp::schgen::author_project_subsystem | schgen::CircuitSheetIr (const std::string &, const std::string &, const schgen::ProjectAuthoringInput &)");
    s.constructors.push_back("native/src/project_authoring_registry.cpp::schgen::author_registered_project_definition | schgen::CircuitSheetIr (const schgen::ProjectSubsystemDefinition &, const schgen::SubsystemMeta &, const schgen::AuthoringContext &)");
    s.constructors.push_back("native/src/project_authoring.cpp::schgen::author_som_connector | schgen::CircuitSheetIr (const std::string &, const std::string &, const std::string &, const schgen::SomInterface &, const schgen::LinkMapping &, const schgen::ConnectorAuthoringPolicy &, const schgen::AuthoringContext &)");
    s.constructors.push_back("native/src/example_devkit.cpp::schgen::author_example_devkit | std::vector<schgen::CircuitSheetIr> (const schgen::AuthoringContext &, const std::map<std::string, schgen::JsonNode> &)");
    s.constructors.push_back("native/src/example_devkit.cpp::schgen::author_example_devkit_subsystem | schgen::CircuitSheetIr (const std::string &, const schgen::AuthoringContext &, const std::optional<schgen::JsonNode> &)");
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
        "native/src/bringup_internal.hpp::schgen::bringup_detail::sheet | const schgen::CircuitSheetIr *(const schgen::FirmwareDocsInput &, const std::string &)",
        "native/src/bringup_internal.hpp::schgen::bringup_detail::required | const schgen::CircuitSheetIr &(const schgen::FirmwareDocsInput &, const std::string &)",
        "native/src/bringup_internal.hpp::schgen::bringup_detail::sheets | std::map<std::string, const schgen::CircuitSheetIr *> (const schgen::FirmwareDocsInput &)",
        "native/src/copper_debt.cpp::schgen::sheet | const schgen::CircuitSheetIr &(const schgen::CopperDebtSources &, const std::string &, const std::string &)",
        "native/src/schematic_place_pages.cpp::schgen::schematic_place::split_auxiliary | std::pair<schgen::CircuitSheetIr, std::vector<std::string>> (const schgen::CircuitSheetIr &)",
        "native/src/schematic_place_pages.cpp::schgen::schematic_place::subset_page | schgen::CircuitSheetIr (const schgen::CircuitSheetIr &, const std::set<std::string> &, int)",
        "native/src/schematic_place_pages.cpp::schgen::schematic_place::partition_pages_with_fit | std::vector<schgen::CircuitSheetIr> (const schgen::CircuitSheetIr &, schgen::SymbolLibrary &, const std::function<bool (const schgen::CircuitSheetIr &)> &)",
        "native/src/schematic_place_pages.cpp::schgen::schematic_place::partition_pages | std::vector<schgen::CircuitSheetIr> (const schgen::CircuitSheetIr &, schgen::SymbolLibrary &)",
        "native/src/schematic_place_pages.cpp::schgen::partition_schematic_pages | std::vector<schgen::CircuitSheetIr> (const schgen::CircuitSheetIr &, schgen::SymbolLibrary &)",
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
