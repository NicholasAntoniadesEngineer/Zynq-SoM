#pragma once

#include "schgen/project_authoring.hpp"

namespace schgen {
// Expectations are reviewed engineering metadata, independent of construction.
// The audit consumes the caller's actual IR, never a snapshot or source search.
struct ComponentBasisDeclaration {
    std::string name, value, unit, basis, klass;
    bool numeric = false;
    std::string site;
};
struct ComponentBasisUse {
    std::string scope, sheet, target, attribute, declaration, type;
};
struct ComponentBasisSheet {
    std::string scope, name;
};
struct ComponentBasisPolicy {
    std::vector<ComponentBasisDeclaration> declarations;
    std::vector<ComponentBasisUse> uses;
    std::vector<ComponentBasisSheet> sheets;
    std::vector<std::string> board_scope_only;
};
struct ComponentBasisInput {
    std::string scope, sheet;
    CircuitSheetIr circuit;
};
struct ComponentBasisResult {
    std::size_t n_registered = 0, n_files = 0, n_sites = 0;
    std::vector<std::string> raw, undeclared, unused, broken;
    bool ok() const { return raw.empty() && undeclared.empty() && unused.empty() && broken.empty(); }
};
ComponentBasisPolicy load_component_basis_policy(const std::filesystem::path& repository);
std::set<std::string> component_basis_scopes(const std::filesystem::path& repository);
// Scopes are explicit and required; omitted/extra/duplicate sheets fail closed.
ComponentBasisResult audit_component_basis(const std::vector<ComponentBasisInput>&,
    const std::set<std::string>& scopes, const ComponentBasisPolicy&);
std::vector<ComponentBasisInput> author_component_basis_inputs(const std::filesystem::path& repository,
    const ComponentBasisPolicy&);
std::string component_basis_report(const ComponentBasisResult&);
JsonNode component_basis_result_json(const ComponentBasisResult&);
JsonNode component_basis_policy_json(const ComponentBasisPolicy&);
} // namespace schgen
