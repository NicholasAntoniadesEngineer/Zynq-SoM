#include "schgen/authoring_context.hpp"
#include "schgen/subsystem_authoring.hpp"
#include <iostream>
#include <type_traits>

namespace {
using namespace schgen;
std::size_t checks = 0, foreign_calls = 0;
void require(bool value, const std::string& why) {
    ++checks;
    if (!value) throw std::runtime_error(why);
}
template<class F> void rejects(F fn, const std::string& expected) {
    bool rejected = false;
    try { fn(); }
    catch (const CircuitAuthoringError& e) {
        rejected = true;
        require(std::string(e.what()) == expected, "wrong native-context diagnostic: " + std::string(e.what()));
    }
    require(rejected, "untrusted native context accepted");
}
CatalogPart foreign_catalog(const std::string& name) {
    ++foreign_calls;
    CatalogPart p; p.safe_name = name; p.mpn = name; p.prefix = "U";
    p.lib_id = "Foreign:part"; return p;
}
std::optional<std::set<std::string>> foreign_pins(const std::string&) {
    ++foreign_calls; return std::set<std::string>{"99"};
}
} // namespace

int main(int argc, char** argv) {
    try {
        require(argc == 2, "usage: authoring_context_contracts REPOSITORY");
        const std::filesystem::path root = std::filesystem::absolute(argv[1]);
        const std::string catalog_error = "native authoring context: catalog target must be lookup_part_catalog";
        const std::string pin_error = "native authoring context: pins target must own a NativeAuthoringPinResolver";
        static_assert(!std::is_default_constructible_v<NativeAuthoringPinResolver>);
        static_assert(std::is_final_v<NativeAuthoringPinResolver>);
        static_assert(std::is_copy_constructible_v<NativeAuthoringPinResolver>);
        static_assert(std::is_move_constructible_v<NativeAuthoringPinResolver>);

        // The validator inspects targets only. A closed catalog is deliberately
        // fine: validation must not call lookup_part_catalog to guess its target.
        close_part_catalog();
        auto native = make_authoring_context(root);
        require_native_authoring_context(native); ++checks;
        auto copy = native;
        require_native_authoring_context(copy); ++checks;
        require(copy.pins.target<NativeAuthoringPinResolver>() != nullptr, "named target stored directly");
        require(native.pins("Device:R") == std::optional<std::set<std::string>>{{"1", "2"}}, "real native resistor pins");
        require(!native.pins("MissingAuthoringLibrary:MissingSymbol"), "unresolved symbol remains nullopt");

        auto changed = native; changed.part = {};
        rejects([&] { require_native_authoring_context(changed); }, catalog_error);
        changed = native; changed.part = foreign_catalog;
        rejects([&] { require_native_authoring_context(changed); }, catalog_error);
        // Identical signatures and forwarding behavior are not native identity.
        changed = native; changed.part = [](const std::string& name) { ++foreign_calls; return lookup_part_catalog(name); };
        rejects([&] { require_native_authoring_context(changed); }, catalog_error);
        auto genuine_catalog = native.part;
        changed = native; changed.part = std::ref(genuine_catalog);
        rejects([&] { require_native_authoring_context(changed); }, catalog_error);
        changed = native; changed.part = std::bind(lookup_part_catalog, std::placeholders::_1);
        rejects([&] { require_native_authoring_context(changed); }, catalog_error);
        changed = native; changed.pins = {};
        rejects([&] { require_native_authoring_context(changed); }, pin_error);
        changed = native; changed.pins = foreign_pins;
        rejects([&] { require_native_authoring_context(changed); }, pin_error);
        changed = native; changed.pins = [original = native.pins](const std::string& name) {
            ++foreign_calls; return original(name);
        };
        rejects([&] { require_native_authoring_context(changed); }, pin_error);
        auto genuine_pins = native.pins;
        changed = native; changed.pins = std::ref(genuine_pins);
        rejects([&] { require_native_authoring_context(changed); }, pin_error);
        changed = native;
        auto moved = std::move(*changed.pins.target<NativeAuthoringPinResolver>());
        rejects([&] { require_native_authoring_context(changed); }, pin_error);
        rejects([&] { changed.pins("Device:R"); }, "native pin resolver: empty library owner");
        changed.pins = std::move(moved);
        require_native_authoring_context(changed); ++checks;
        require(changed.pins("Device:R") == native.pins("Device:R"), "moved owner remains usable");
        require(foreign_calls == 0, "validation executed an untrusted provider");
        rejects([&] { require_native_authoring_context(AuthoringContext{}); }, pin_error);

        // Acceptance is not cached in the context or a mutable approval flag.
        require_native_authoring_context(copy); ++checks;
        copy.part = foreign_catalog;
        rejects([&] { require_native_authoring_context(copy); }, catalog_error);
        require_native_authoring_context(native); ++checks;
        copy = native; copy.pins = foreign_pins;
        rejects([&] { require_native_authoring_context(copy); }, pin_error);
        require_native_authoring_context(native); ++checks;
        require(foreign_calls == 0, "post-validation mutation ran callback during rejection");

        // Existing public API still accepts explicit custom providers outside
        // native-policy entry points. No signature/layout/default was changed.
        AuthoringContext custom; custom.part = foreign_catalog; custom.pins = foreign_pins;
        CircuitAuthor circuit("custom-provider", {}, custom);
        const auto ref = circuit.use_part("LIVE_PART");
        circuit.port("CUSTOM_PIN", {ref + ".99"});
        require(foreign_calls == 2 && circuit.finish().nets.front().pins.front().pin == "99", "custom provider compatibility");
        require(open_part_catalog((root / "native/catalog.bin").string()), "open catalog");
        require_native_authoring_context(native); ++checks;
        const auto first = author_subsystem("usb_pd", SubsystemMeta{}, native);
        auto retained = native;
        native = {};
        require_native_authoring_context(retained); ++checks;
        const auto second = author_subsystem("usb_pd", SubsystemMeta{}, retained);
        require(authoring_json_equal(authored_circuit_json(first), authored_circuit_json(second)), "native snapshot lifetime/copy parity");
        close_part_catalog();
        std::cout << checks << " native authoring-context contracts passed; actual targets, no callback execution, mutation rejection\n";
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n'; return 1;
    }
}
