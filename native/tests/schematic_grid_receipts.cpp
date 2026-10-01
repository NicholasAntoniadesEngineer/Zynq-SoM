#include "../src/schematic_place_internal.hpp"
#include "../src/precision_receipt.hpp"
#include "schgen/native_audit_state.hpp"

#include <cmath>
#include <filesystem>
#include <iostream>
#include <limits>

int schematic_grid_observe(const std::filesystem::path&);
void verify_schematic_grid_entries(const std::string&, const std::filesystem::path&);
namespace {
using namespace schgen;
namespace sp = schgen::schematic_place;
void require(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(message);
}
void equal(double a, double b) {
    require(a == b && (a != 0 || std::signbit(a) == std::signbit(b)), "scalar arithmetic changed");
}
}
int main(int argc, char** argv) {
    try {
        if (argc == 3 && std::string(argv[2]) == "--observe") return schematic_grid_observe(argv[1]);
        require(argc == 2, "repository argument required");
        const std::filesystem::path repo = argv[1];
        verify_schematic_grid_entries(argv[0], repo);
        SymbolLibrary lib(std::vector<std::filesystem::path>{
            repo/"native/tests/data/symbols/kicad", repo/"schgen/lib", repo/"parts"});
        CircuitSheetIr circuit; circuit.name = "grid-receipts";
        sp::Engine first(circuit, lib), second(circuit, lib);
        const double values[] = {-100.123, -1.905, -0.0, 0.0, 0.635, 1.905, 100.123};
        for (double v : values) {
            equal(first.gsnap(v), schgen::gsnap(v, symbol_grid));
            equal(first.gfloor(v), schgen::gfloor(v, symbol_grid));
            equal(first.gceil(v), schgen::gceil(v, symbol_grid));
        }
        require(first.owned_counts == QuantizationCounts{{"gsnap",7},{"gfloor",7},{"gceil",7}},
                "Engine entries missing/duplicated");
        require(second.owned_counts.empty(), "independent Engine contaminated");
        QuantizationCounts shared;
        sp::Engine attached(circuit, lib, {}, &shared);
        attached.gsnap(2.5);
        require(shared == QuantizationCounts{{"gsnap",1}} && attached.owned_counts.empty(),
                "external invocation sink not used");
        QuantizationCounts spacing;
        SchematicSpacing{}.expanded(&spacing);
        require(spacing == QuantizationCounts{{"gceil",7}}, "expanded spacing must count seven actual entries");
        SchematicPlacement centered;
        centered.boxes.push_back({0,0,20,20,"body","test"});
        QuantizationCounts centering;
        sp::center_on_sheet(centered, &centering);
        require(centering == QuantizationCounts{{"gsnap",2}}, "centering entries");
        int calls = 0;
        sp::PageOperations ops{
            [&](const auto&, auto&, const auto&) {
                if (++calls == 1) throw SchematicPlaceError("retry");
                SchematicPlacement p; p.boxes.push_back({0,0,300,200,"body","test"}); return p;
            },
            [](const auto&, const auto&, auto&) { return SchematicRoutedSheet{}; },
            [](const auto&) { return VisualResult{true,{}}; }};
        QuantizationCounts retry;
        const auto page = sp::place_and_route_with(circuit,lib,{},2,ops,&retry);
        require(page.placement.paper == "A3" && calls == 2, "retry/A3 behavior changed");
        require(retry == QuantizationCounts{{"gceil",7},{"gsnap",2}}, "retry prefix/A3 receipts");

        // Failure import must occur exactly once and retain only completed scalar entries.
        QuantizationCounts imported;
        int imports = 0;
        bool threw = false;
        try {
            board_pipeline_detail::with_precision_receipt([&](auto& counts) -> int {
                sp::Engine e(circuit,lib,{},&counts);
                e.gfloor(1.2); e.gsnap(3.4);
                throw std::runtime_error("producer failure");
            }, [&](const auto& counts) { ++imports; imported = counts; });
        } catch (const std::runtime_error&) { threw = true; }
        require(threw && imports == 1 && imported == QuantizationCounts{{"gfloor",1},{"gsnap",1}},
                "throwing invocation prefix not imported once");
        imports = 0;
        const auto result = board_pipeline_detail::with_precision_receipt([&](auto& counts) {
            return sp::gceil(3.4,&counts);
        }, [&](const auto& counts) { ++imports; imported = counts; });
        equal(result, schgen::gceil(3.4,symbol_grid));
        require(imports == 1 && imported == QuantizationCounts{{"gceil",1}}, "successful receipt import");
        imports = 0;
        threw = false;
        try {
            board_pipeline_detail::with_precision_receipt([](auto& counts) {
                return sp::gsnap(3.4,&counts);
            }, [&](const auto&) { ++imports; throw std::runtime_error("import failure"); });
        } catch (const std::runtime_error&) { threw = true; }
        require(threw && imports == 1, "failed import retried");

        NativeQuantizations registry;
        NativeFallbacks fallbacks;
        register_native_quantizations(registry);
        register_native_fallbacks(fallbacks);
        NativeAccountingInbox inbox(registry, fallbacks);
        const auto declarations = registry.declarations().size();
        const auto before = registry.engagements();
        require(inbox.merge_once("schematic/test/grid",NativeAccountingBatch{
            native_counter_batch(imported),{}}), "board receipt not imported");
        require(!inbox.merge_once("schematic/test/grid",NativeAccountingBatch{
            native_counter_batch(imported),{}}), "duplicate board receipt imported");
        const auto after = registry.engagements();
        for (const auto& [name,n] : after) {
            const auto old=before.find(name);
            const auto delta=imported.find(name);
            require(old==before.end() || !old->second.nonzero(), "registry began with unexpected work");
            require(n == AuditInteger(delta==imported.end()?0:static_cast<std::int64_t>(delta->second)),
                    "board ledger delta differs from receipt");
        }
        require(registry.declarations().size()==declarations, "receipt added operation declarations");

        QuantizationCounts overflow{{"gsnap",std::numeric_limits<std::size_t>::max()}};
        threw = false;
        try { sp::gsnap(0,&overflow); } catch (const std::overflow_error&) { threw = true; }
        require(threw && overflow.at("gsnap") == std::numeric_limits<std::size_t>::max(),
                "counter overflow corrupted state");
        std::cout << "schematic grid receipt contracts passed\n";
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n'; return 1;
    }
}
