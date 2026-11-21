#pragma once

#include "schgen/bom.hpp"
#include "schgen/part_checks.hpp"

#include <optional>
#include <string>
#include <vector>

namespace schgen {

inline constexpr const char* rated_bom_empty_cell = "-";

struct RatedBomWorst {
    std::string at;
    double stress = 0.0, ratio = 0.0, limit = 0.0;
    PartCheckBound bound = PartCheckBound::none;
};

struct RatedBomLine {
    std::size_t number = 0;
    BomRow bom;
    std::optional<PartRatings> rating;
    std::size_t checks = 0, fails = 0, waived = 0, advisory = 0;
    std::optional<RatedBomWorst> voltage, power;
    std::string verdict;
};

struct RatedBom {
    std::vector<RatedBomLine> lines;
    std::size_t checks() const;
    std::size_t fails() const;
    std::size_t waived() const;
    std::size_t advisory() const;
    std::size_t unrated() const;
    std::string text() const;
};

RatedBom build_rated_bom(const BomOutput& bom, const PartRatingsTable& ratings, const PartCheckResult& parts);

std::vector<std::string> verify_rated_bom(const RatedBom& report, const BomOutput& bom, const PartRatingsTable& ratings, const PartCheckResult& parts);

}
