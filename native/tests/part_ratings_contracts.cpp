#include "schgen/json.hpp"
#include "schgen/part_checks.hpp"

#include <iostream>
#include <stdexcept>

namespace {

using namespace schgen;

constexpr std::size_t expected_rows = 100;
const char* const expected_first = "C14663";
const char* const expected_last = "C124014";
const char* const inline_name = "inline.json";

std::size_t checks = 0;

void require(bool condition, const std::string& detail) {
    ++checks;
    if (!condition) throw std::runtime_error("part ratings contract failed: " + detail);
}

PartRatingsTable parsed(const std::string& text) {
    return parse_part_ratings(parse_json_text(text, inline_name), inline_name);
}

void rejects(const std::string& text, const std::string& needle) {
    bool thrown = false;
    try {
        parsed(text);
    } catch (const std::runtime_error& error) {
        const std::string message = error.what();
        thrown = message.find(needle) != std::string::npos;
        if (!thrown) throw std::runtime_error("expected '" + needle + "', got: " + message);
        require(message.find(inline_name) != std::string::npos, "the message names the file: " + message);
    }
    require(thrown, "accepted: expected '" + needle + "'");
}

std::string document(const std::string& schema, const std::string& rows) {
    return "{\"schema\": \"" + schema + "\", \"ratings\": [" + rows + "]}";
}

std::string with_rows(const std::string& rows) { return document("schgen.part_ratings/1", rows); }

const std::string minimal_row = "{\"lcsc\": \"C1\", \"kind\": \"mlcc\", \"source\": \"fixture\"}";

void real_file_loads() {
    const auto table = load_part_ratings(part_ratings_file());
    require(table.size() == expected_rows, "the real file holds the expected row count");
    require(table.front().first == expected_first, "the first code is the one the table began with");
    require(table.back().first == expected_last, "the last code is the one the table ended with");
    require(default_part_ratings().size() == expected_rows, "default_part_ratings returns the loaded file");
}

void shape_is_enforced() {
    rejects(document("schgen.part_ratings/2", minimal_row), "schema must be");
    rejects("{\"ratings\": []}", "schema");
    rejects("{\"schema\": \"schgen.part_ratings/1\"}", "ratings");
    rejects(with_rows(""), "non-empty");
    rejects("{\"schema\": \"schgen.part_ratings/1\", \"ratings\": [], \"extra\": 1}", "unknown key 'extra'");
    rejects(with_rows("{\"lcsc\": \"C1\", \"kind\": \"mlcc\", \"source\": \"s\", \"colour\": \"red\"}"),
            "unknown key 'colour'");
    rejects(with_rows("{\"kind\": \"mlcc\", \"source\": \"s\"}"), "lcsc");
    rejects(with_rows("{\"lcsc\": \"\", \"kind\": \"mlcc\", \"source\": \"s\"}"), "lcsc");
    rejects(with_rows("{\"lcsc\": \"C1\", \"source\": \"s\"}"), "kind");
    rejects(with_rows("{\"lcsc\": \"C1\", \"kind\": \"\", \"source\": \"s\"}"), "kind");
    rejects(with_rows("{\"lcsc\": \"C1\", \"kind\": \"mlcc\"}"), "source");
    rejects(with_rows("{\"lcsc\": \"C1\", \"kind\": \"mlcc\", \"source\": \"\"}"), "source");
    rejects(with_rows(minimal_row + ", " + minimal_row), "listed twice");
}

void numbers_are_numbers() {
    for (const char* key : {"v_max", "i_max", "p_max", "temp_max", "vin_max"}) {
        const std::string head = "{\"lcsc\": \"C1\", \"kind\": \"mlcc\", \"source\": \"s\", \"" + std::string(key) + "\": ";
        rejects(with_rows(head + "\"50\"}"), key);
        rejects(with_rows(head + "null}"), key);
    }
    rejects(with_rows("{\"lcsc\": \"C1\", \"kind\": \"mlcc\", \"source\": \"s\", \"tol\": 5}"), "tol");
}

void absent_optionals_stay_absent() {
    const auto table = parsed(with_rows(minimal_row));
    require(table.size() == 1, "one row loaded");
    const PartRatings& row = table.front().second;
    require(!row.v_max && !row.i_max && !row.p_max && !row.temp_max && !row.vin_max, "absent numbers are nullopt");
    require(!row.tol && !row.dielectric, "absent strings are nullopt");
    require(row.kind == "mlcc" && row.source == "fixture", "required fields are carried");
}

}

int main() {
    try {
        real_file_loads();
        shape_is_enforced();
        numbers_are_numbers();
        absent_optionals_stay_absent();
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 1;
    }
    std::cout << "part ratings contracts: " << checks << " checks passed\n";
    return 0;
}
