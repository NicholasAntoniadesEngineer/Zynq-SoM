#pragma once

#include "schgen/json.hpp"
#include "schgen/layout_problem.hpp"

namespace schgen::layout {

struct Document {
    Problem problem;
    Placement placement;
};

std::string document_json(const Problem& problem, const Placement& placement);
Document read_document(const JsonNode& root);

}
