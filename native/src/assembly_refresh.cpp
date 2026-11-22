#include "schgen/assembly_refresh.hpp"

#include "schgen/process.hpp"

#include <algorithm>
#include <cctype>
#include <chrono>
#include <cmath>
#include <ctime>
#include <regex>
#include <thread>

namespace schgen {
namespace {

const char* const user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36";
const std::chrono::milliseconds request_spacing{1000};
const std::chrono::seconds request_timeout{40};
const std::chrono::seconds process_slack{2};
const char* const library_base = "base";
const char* const library_expand = "expand";
const char* const buyable_flag = "1";
const char* const assembly_label = "Assembly Type";
const char* const pcba_label = "PCBA Type";
const std::string flight_joiner = "\"])</script><script>self.__next_f.push([1,\"";
const char* const time_format = "%Y-%m-%dT%H:%M:%SZ";
const std::size_t time_capacity = 32;
const std::size_t page_search_size = 5;
const char* const comparison_key = "part";

[[noreturn]] void refuse(const std::string& code, const std::string& what) { throw std::runtime_error(code + ": " + what); }

const JsonNode* member(const JsonNode& node, const std::string& key) { return node.kind == JsonKind::Object ? object_field(node, key) : nullptr; }

std::string collapsed(const std::string& markup) {
    static const std::regex tag("<[^>]+>");
    std::string text = std::regex_replace(markup, tag, " ");
    for (const auto& [entity, plain] : std::vector<std::pair<std::string, std::string>>{{"&amp;", "&"}, {"&lt;", "<"}, {"&gt;", ">"}, {"&nbsp;", " "}, {"&#x27;", "'"}, {"&quot;", "\""}}) {
        for (std::size_t at = text.find(entity); at != std::string::npos; at = text.find(entity, at + plain.size())) text.replace(at, entity.size(), plain);
    }
    std::string out;
    bool space = false;
    for (char c : text) {
        if (std::isspace(static_cast<unsigned char>(c))) { space = !out.empty(); continue; }
        if (space) out += ' ';
        space = false;
        out += c;
    }
    return out;
}

std::optional<std::string> visible(const std::string& page, const std::string& label) {
    const std::regex pattern(">" + label + R"(</dt>\s*<dd[^>]*>([\s\S]*?)</dd>)");
    std::smatch match;
    if (!std::regex_search(page, match, pattern)) return std::nullopt;
    const std::string text = collapsed(match[1].str());
    if (text.empty()) return std::nullopt;
    return text;
}

std::optional<std::string> embedded(const std::string& page, const std::string& key) {
    const std::regex pattern(R"(\\"()" + key + R"()\\":(\\"([^\\]*)\\"|[^,}\]<\s\\]+))");
    std::smatch match;
    if (!std::regex_search(page, match, pattern)) return std::nullopt;
    return match[3].matched ? match[3].str() : match[2].str();
}

std::int64_t whole(const JsonNode& node, const std::string& key, const std::string& code) {
    const JsonNode* value = member(node, key);
    if (!value || value->kind != JsonKind::Number || value->number_value < 0 || value->number_value != std::floor(value->number_value))
        refuse(code, "'" + key + "' is missing or is not a whole number");
    return static_cast<std::int64_t>(value->number_value);
}

std::string pcba_name(const std::string& shown, const std::string& code) {
    if (shown == "Economic and Standard") return "economic_and_standard";
    if (shown == "Standard Only") return "standard_only";
    refuse(code, "PCBA type '" + shown + "' is not a type the facts file knows");
}

std::optional<std::int64_t> lcsc_stock(const std::string& code, const AssemblyTransport& transport) {
    const JsonNode detail = parse_json_text(transport({assembly_endpoint::lcsc_detail + code, std::nullopt}), "LCSC detail of " + code);
    const JsonNode* result = member(detail, "result");
    if (result && result->kind == JsonKind::Null) return std::nullopt;
    if (!result || result->kind != JsonKind::Object) refuse(code, "the LCSC detail is malformed");
    const JsonNode* product = member(*result, "productCode");
    if (!product || product->kind != JsonKind::String || product->string_value != code) refuse(code, "the LCSC detail answers for another code");
    return whole(*result, "stockNumber", code);
}

}

std::string assembly_utc_now() {
    const std::time_t now = std::time(nullptr);
    std::tm utc{};
    gmtime_r(&now, &utc);
    char text[time_capacity];
    if (!std::strftime(text, sizeof text, time_format, &utc)) throw std::runtime_error("cannot format the time");
    return text;
}

AssemblyPart read_assembly_part(const std::string& code, const AssemblyTransport& transport, const std::string& read_utc) {
    AssemblyPart part;
    part.read_utc = read_utc;
    const std::string keyword = "{\"keyword\":\"" + code + "\",\"currentPage\":1,\"pageSize\":" + std::to_string(page_search_size) + "}";
    part.source_urls = {assembly_endpoint::search, assembly_endpoint::part_page + code, assembly_endpoint::lcsc_detail + code};
    const JsonNode search = parse_json_text(transport({assembly_endpoint::search, keyword}), "JLCPCB search for " + code);
    const JsonNode* info = member(search, "data");
    info = info ? member(*info, "componentPageInfo") : nullptr;
    const JsonNode* list = info ? member(*info, "list") : nullptr;
    if (!list || (list->kind != JsonKind::Array && list->kind != JsonKind::Null)) refuse(code, "the search answer has no component list");
    const JsonNode* hit = nullptr;
    if (list->kind == JsonKind::Array)
        for (const JsonNode& item : list->array_value) {
            const JsonNode* name = member(item, "componentCode");
            if (name && name->kind == JsonKind::String && name->string_value == code) { hit = &item; break; }
        }
    part.lcsc_stock = lcsc_stock(code, transport);
    if (!hit) {
        part.source_urls = {assembly_endpoint::search, assembly_endpoint::lcsc_detail + code};
        return part;
    }
    part.in_library = true;
    const JsonNode* type = member(*hit, "componentLibraryType");
    const JsonNode* preferred = member(*hit, "preferredComponentFlag");
    if (!type || type->kind != JsonKind::String) refuse(code, "the search hit has no library type");
    if (type->string_value == library_base) part.part_class = "basic";
    else if (type->string_value == library_expand) part.part_class = preferred && preferred->kind == JsonKind::Bool && preferred->bool_value ? "preferred" : "extended";
    else refuse(code, "library type '" + type->string_value + "' is not base or expand");
    part.preferred = part.part_class == "preferred";
    part.jlc_stock = whole(*hit, "stockCount", code);
    for (const auto& [key, slot] : std::vector<std::pair<std::string, std::string*>>{{"componentModelEn", &part.mpn}, {"componentSpecificationEn", &part.jlc_package}}) {
        const JsonNode* value = member(*hit, key);
        if (!value || value->kind != JsonKind::String || value->string_value.empty()) refuse(code, "the search hit has no '" + key + "'");
        *slot = value->string_value;
    }
    const JsonNode* buy = member(*hit, "isBuyComponent");
    if (!buy) refuse(code, "the search hit has no 'isBuyComponent'");
    part.buyable = (buy->kind == JsonKind::String && buy->string_value == buyable_flag) || (buy->kind == JsonKind::Bool && buy->bool_value) || (buy->kind == JsonKind::Number && buy->number_value == 1.0);
    std::string page = transport({assembly_endpoint::part_page + code, std::nullopt});
    for (std::size_t at = page.find(flight_joiner); at != std::string::npos; at = page.find(flight_joiner, at)) page.erase(at, flight_joiner.size());
    const auto assembly_type = visible(page, assembly_label), pcba_type = visible(page, pcba_label);
    const auto mode = embedded(page, "assemblyMode"), fee = embedded(page, "specialComponentFee"), audit = embedded(page, "needAuditFlag"), level = embedded(page, "moistureSensitivityLevelEn");
    if (!assembly_type || !pcba_type || !mode || !fee || !audit) refuse(code, "the part page does not show its assembly type, PCBA type, assembly mode, special fee and audit flag");
    part.assembly_type = *assembly_type;
    part.pcba_type = pcba_name(*pcba_type, code);
    part.assembly_mode = *mode;
    std::size_t used = 0;
    try { part.special_fee = std::stod(*fee, &used); } catch (const std::exception&) { used = 0; }
    if (used != fee->size()) refuse(code, "special fee '" + *fee + "' is not a number");
    if (*audit != "true" && *audit != "false") refuse(code, "audit flag '" + *audit + "' is not true or false");
    part.audit_flag = *audit == "true";
    part.msl = level && *level != "null" ? *level : std::string();
    return part;
}

AssemblyRefreshResult refresh_assembly_facts(const AssemblyFacts& old, const std::vector<std::string>& codes,
                                             const AssemblyTransport& transport, const AssemblyClock& clock) {
    AssemblyRefreshResult out;
    out.facts = old;
    std::vector<std::string> ordered = codes;
    std::sort(ordered.begin(), ordered.end());
    ordered.erase(std::unique(ordered.begin(), ordered.end()), ordered.end());
    for (const std::string& code : ordered) {
        try {
            AssemblyPart fresh = read_assembly_part(code, transport, clock());
            const auto previous = old.parts.find(code);
            if (previous != old.parts.end()) fresh.route = previous->second.route;
            AssemblyPart comparable = fresh, before = previous == old.parts.end() ? AssemblyPart{} : previous->second;
            comparable.read_utc.clear();
            before.read_utc.clear();
            const auto same = [](const AssemblyPart& a, const AssemblyPart& b) {
                AssemblyFacts left, right;
                left.parts[comparison_key] = a;
                right.parts[comparison_key] = b;
                return assembly_facts_text(left) == assembly_facts_text(right);
            };
            if (previous == old.parts.end()) out.changes.push_back(code + ": new row");
            else if (!same(comparable, before)) out.changes.push_back(code + ": changed");
            out.facts.parts[code] = fresh;
        } catch (const std::exception& error) {
            out.failures.push_back(code + ": " + error.what() + (old.parts.count(code) ? "; the old row is kept" : "; no row exists"));
        }
    }
    return out;
}

AssemblyTransport live_assembly_transport() {
    auto spaced = std::make_shared<bool>(false);
    return [spaced](const AssemblyRequest& request) {
        if (*spaced) std::this_thread::sleep_for(request_spacing);
        *spaced = true;
        std::vector<std::string> args{"curl", "--silent", "--show-error", "--location", "--proto", "=https", "--proto-redir", "=https",
                                      "--max-time", std::to_string(request_timeout.count()), "--user-agent", user_agent};
        if (request.body) args.insert(args.end(), {"--header", "Content-Type: application/json", "--data-binary", *request.body});
        args.insert(args.end(), {"--url", request.url});
        const ProcessResult response = run_process(args, request_timeout + process_slack);
        if (response.exit_code != 0) throw std::runtime_error("transport failed for " + request.url + ": " + response.stderr_text);
        return response.stdout_text;
    };
}

}
