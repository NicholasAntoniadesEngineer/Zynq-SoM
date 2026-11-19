#pragma once

#include "schgen/roles.hpp"
#include "schgen/layout_adapter.hpp"
#include "schgen/named_constant.hpp"
#include "schgen/pcb_model.hpp"
#include "schgen/stackup.hpp"

#include <array>
#include <cstdint>
#include <initializer_list>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace schgen::rules {

namespace constants {
inline constexpr NamedConstant judging_resolution{"judging_resolution", 1e-3, "mm", "policy",
    "a distance or overlap smaller than this is below fabrication resolution and is not judged"};
inline constexpr std::array rule_registry{judging_resolution};
}

enum class Enforcement : std::uint8_t { gate, measured };

enum class Stage : std::uint8_t { placement, layout };

struct Rule {
    std::string_view id, area, statement, why, source, confidence;
    Enforcement enforcement = Enforcement::measured;
    Stage met_by = Stage::placement;
};

struct Finding {
    std::string subject, detail;
};

struct RuleResult {
    const Rule* rule = nullptr;
    std::size_t checked = 0;
    std::vector<Finding> findings;
    std::vector<std::string> measurements;
};

struct Service {
    std::size_t part = 0, owner = 0;
    std::string role, pin;
    std::vector<std::string> pads;
};

struct RegulatorInput {
    std::string pad, name;
    std::vector<std::size_t> capacitors;
};

struct RegulatorOutput {
    std::size_t member = 0;
    std::string pad;
    std::vector<std::size_t> capacitors;
};

struct Regulator {
    std::size_t part = 0;
    std::vector<std::size_t> inductors, supports;
    std::vector<RegulatorInput> inputs;
    std::vector<RegulatorOutput> outputs;
};

class RuleContext {
public:
    RuleContext(const PcbCheckInput& input, const PcbModel& model, const Stackup& stackup,
                const layout::AuthoredIntent& intent);
    const PcbModel& model() const { return model_; }
    const Stackup& stackup() const { return stackup_; }
    const std::vector<PcbCheckInstance>& parts() const { return input_.model().insts; }
    const std::vector<Service>& services() const { return services_; }
    const std::vector<Regulator>& regulators() const { return regulators_; }
    std::vector<const Service*> serving(const std::vector<std::string_view>& roles) const;
    std::vector<Finding> unresolved(const std::vector<std::string_view>& roles) const;
    bool placed(std::size_t part) const;
    bool rear(std::size_t part) const;
    bool ground_beneath(std::size_t part) const;
    PartClass part_class(std::size_t part) const;
    bool module_connector(std::size_t part) const;
    bool capacitor(std::size_t part) const;
    bool inductor(std::size_t part) const;
    bool connector(std::size_t part) const;
    std::string label(std::size_t part) const;
    std::string face(std::size_t part) const;
    std::string neighbour(std::size_t part) const;
    std::string pin_name(std::size_t part, const std::string& pad) const;
    std::string net_at(std::size_t part, const std::string& pad) const;
    Box4 courtyard(std::size_t part) const;
    Box4 body(std::size_t part) const;
    double overlap(std::size_t first, std::size_t second) const;
    static double overlap(const Box4& a, const Box4& b);
    double centre_distance(std::size_t first, std::size_t second) const;
    std::optional<double> pad_gap(std::size_t owner, const std::vector<std::string>& pads, std::size_t member) const;
    std::optional<double> net_gap(std::size_t owner, const std::vector<std::string>& pads, std::size_t member,
                                  const std::string& net) const;

private:
    const PcbCheckInput& input_;
    const PcbModel& model_;
    const Stackup& stackup_;
    std::vector<Service> services_;
    std::vector<std::pair<std::string, Finding>> unresolved_;
    std::vector<Regulator> regulators_;
    std::map<std::string, std::map<std::string, std::string>> pin_names_;
};

using Check = RuleResult (*)(const RuleContext&);

struct RuleEntry {
    Rule rule;
    Check check = nullptr;
};

const std::vector<RuleEntry>& rule_book();
const char* enforcement_name(Enforcement enforcement);
std::string rule_book_markdown();
std::optional<int> run_rules_command(int argc, char** argv);

}
