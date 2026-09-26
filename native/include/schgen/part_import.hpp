#pragma once

#include "schgen/catalog.hpp"
#include "schgen/json.hpp"
#include "schgen/process.hpp"
#include "schgen/sexpr.hpp"
#include <chrono>
#include <filesystem>
#include <functional>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace schgen {

// Returns nullopt for a different command; parse errors never publish files.
std::optional<int> run_part_import_command(int argc, char** argv);

class PartImportError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

struct PartImportInfo {
    CatalogPart part;
    std::vector<std::string> tags;
};
struct PartPinGroups {
    std::vector<CatalogPin> left, right, top, bottom;
};
struct PartModelTransform {
    std::string uuid, title;
    double tx = 0, ty = 0, tz = 0, rx = 0, ry = 0, rz = 0;
};
struct PartFootprint {
    Sexpr tree;
    std::optional<PartModelTransform> model;
    std::vector<std::string> diagnostics;
    std::size_t pad_count = 0;
};
struct PartImportFile {
    std::string name, bytes;
};
struct PartImportPlan {
    CatalogPart part;
    std::vector<PartImportFile> files;
    std::vector<std::string> diagnostics;
    std::size_t pad_count = 0;
};

// Pure conversion. No filesystem access, catalog mutation or network activity.
PartImportInfo part_import_info(const JsonNode& result);
std::vector<CatalogPin> part_import_pins(const JsonNode& result);
std::vector<CatalogPin> part_normalize_pin_types(std::vector<CatalogPin> pins,
                                               const std::string& prefix);
PartPinGroups part_group_pins(const std::vector<CatalogPin>& pins);
std::string part_safe_name(const std::string& name);
std::optional<CatalogPin> part_synthesize_ep(const std::string& lcsc,
                                          const std::vector<CatalogPin>& pins);
Sexpr part_generate_symbol(const std::string& name, const std::vector<CatalogPin>& pins,
                          const PartImportInfo& info);
PartFootprint part_convert_footprint(const JsonNode& result, const std::string& name,
                                    const PartImportInfo& info,
                                    const std::vector<std::string>& model_files = {},
                                    const std::optional<CatalogPin>& ep = std::nullopt);
std::string part_metadata_json(const CatalogPart& part);
std::string part_model_uuid(const JsonNode& result);
PartImportPlan prepare_part_import(const std::string& response_json,
                                   const std::string& lcsc = {},
                                   const std::string& requested_name = {},
                                   const std::vector<std::string>& existing_models = {},
                                   const std::vector<PartImportFile>& downloaded_models = {});

struct PartHttpRequest {
    std::string url;
    std::chrono::milliseconds timeout{30000};
    std::size_t max_bytes = 128 * 1024 * 1024;
};
struct PartHttpResponse {
    int status = 0;
    std::string body;
    // A failed transport never masquerades as HTTP 404 or an empty success.
    std::string transport_error;
};
using PartTransport = std::function<PartHttpResponse(const PartHttpRequest&)>;
using PartProcessRunner = std::function<ProcessResult(const std::vector<std::string>&,
                                                     std::chrono::milliseconds)>;
// Explicit live transport factory; shell-free curl, HTTPS only, bounded timeout.
// Construction does not execute anything. Optional injection is for recorded tests.
PartTransport part_curl_transport(PartProcessRunner runner = {});
// HTTP status, transport failures, truncated gzip and size limits are checked here.
std::string part_http_body(const PartHttpRequest& request, const PartHttpResponse& response);
std::string fetch_part_cad(const std::string& lcsc, const PartTransport& transport);
struct PartModelDownload {
    std::vector<PartImportFile> files;
    std::vector<std::string> diagnostics;
};
PartModelDownload fetch_part_models(const std::string& uuid, const std::string& base,
                                   const PartTransport& transport);

// Read-only cache discovery. Checks only NAME.wrl / NAME.step, in that order.
std::vector<std::string> existing_part_models(const std::filesystem::path& parts_root,
                                             const std::string& base);
struct PartImportRequest {
    std::string lcsc, name;
    std::filesystem::path parts_root;
    std::optional<std::filesystem::path> from_json;
};
// Preparation may read cache files. Offline from_json NEVER calls transport.
// Online import requires caller-supplied transport (no implicit network fallback).
PartImportPlan prepare_part_import_request(const PartImportRequest& request,
                                          const PartTransport& transport = {});
// The only part-file write boundary. Validates every target before writing; each
// file is replaced atomically, but the multi-file publication is NOT transactional.
// Existing files require explicit overwrite=true; directories/symlinks are rejected.
// Does not delete unrelated files, refresh the catalog, or open the global catalog.
std::filesystem::path publish_part_import(const PartImportPlan& plan,
                                         const std::filesystem::path& parts_root,
                                         bool overwrite = false);
// Explicit, separately authorized catalog refresh after successful publication.
// Reuses compile_part_catalog; caller selects destination, no global cache mutation.
bool compile_imported_part_catalog(const std::filesystem::path& parts_root,
                                  const std::filesystem::path& catalog_path);

} // namespace schgen
