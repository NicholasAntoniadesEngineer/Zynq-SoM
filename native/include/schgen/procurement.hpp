#pragma once
#include "schgen/project.hpp"
#include <functional>
#include <optional>

namespace schgen {
struct ProcurementInfo {
    std::string mpn, brand, package, library;
    long long stock = 0, min_qty = 1;
    std::vector<std::pair<long long, double>> prices;
};
struct ProcurementItem {
    std::string lcsc, value;
    std::vector<std::string> refs, alternatives;
};
struct ProcurementInventory {
    std::vector<ProcurementItem> items;
    std::vector<std::string> missing;
};
struct ProcurementResult {
    bool ok = false;
    double cost = 0;
    std::size_t extended_reels = 0;
    std::vector<std::string> failures, warnings;
    std::string report;
};
struct ProcurementProvider {
    std::function<std::optional<ProcurementInfo>(const std::string&)> assembly;
    std::function<bool(const std::string&)> catalog;
};
ProcurementInventory procurement_inventory(const std::vector<ProjectCircuit>&);
std::pair<std::string, std::string> assess_procurement_stock(long long stock,
    long long need, long long floor = 50);
double procurement_unit_price(const std::vector<std::pair<long long, double>>&, long long);
// Provider errors are distinct from absent catalog entries and propagate. A
// network outage must never be reported as evidence that a part does not exist.
ProcurementResult assess_procurement(const ProcurementInventory&,
    const ProcurementProvider&, long long boards = 1, long long floor = 50,
    bool allow_missing = false);
std::optional<ProcurementInfo> procurement_jlc_response(const JsonNode&, const std::string&);
bool procurement_lcsc_response(const JsonNode&);
// HTTPS-only shell-free curl transport; no Python, credentials or purchases.
ProcurementProvider live_procurement_provider(int timeout_seconds = 20,
    const std::string& curl_executable = "curl");
}
