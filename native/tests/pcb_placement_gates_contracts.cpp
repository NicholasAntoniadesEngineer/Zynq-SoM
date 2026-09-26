#include "pcb_placement_fixture.hpp"
#include "schgen/pcb_placement_gates.hpp"
#include "schgen/ratsnest_gate.hpp"
#include <cmath>
#include <iostream>
#include <limits>

namespace {
using namespace placement_fixture;
std::size_t checks = 0;
void require(bool test, const std::string &why) {
    ++checks;
    if (!test)
        throw std::runtime_error(why);
}
J text(std::string v) {
    J n;
    n.kind = JsonKind::String;
    n.string_value = std::move(v);
    return n;
}
J num(double v) {
    if (!std::isfinite(v))
        return text(std::isnan(v) ? "NaN" : v < 0 ? "-Infinity" : "Infinity");
    J n;
    n.kind = JsonKind::Number;
    n.number_value = v;
    return n;
}
J boolean(bool v) {
    J n;
    n.kind = JsonKind::Bool;
    n.bool_value = v;
    return n;
}
J array(std::vector<J> v) {
    J n;
    n.kind = JsonKind::Array;
    n.array_value = std::move(v);
    return n;
}
J strings_json(const std::vector<std::string> &v) {
    std::vector<J> a;
    for (const auto &s : v)
        a.push_back(text(s));
    return array(std::move(a));
}
J object(std::initializer_list<std::pair<std::string, J>> v) {
    J n;
    n.kind = JsonKind::Object;
    n.object_value = v;
    return n;
}
void same(const J &a, const J &b, const std::string &where) {
    require(a.kind == b.kind, where + " type");
    if (a.kind == JsonKind::Object) {
        require(a.object_value.size() == b.object_value.size(), where + " object size");
        for (const auto &[k, v] : b.object_value)
            same(field(a, k), v, where + "/" + k);
    } else if (a.kind == JsonKind::Array) {
        require(a.array_value.size() == b.array_value.size(), where + " array size");
        for (std::size_t k = 0; k < b.array_value.size(); ++k)
            same(a.array_value[k], b.array_value[k], where + "/" + std::to_string(k));
    } else if (a.kind == JsonKind::String)
        require(a.string_value == b.string_value,
                where + " text\nactual: " + a.string_value + "\nexpected: " + b.string_value);
    else if (a.kind == JsonKind::Number)
        require(a.number_value == b.number_value,
                where + " numeric actual=" + std::to_string(a.number_value) +
                    " expected=" + std::to_string(b.number_value));
    else if (a.kind == JsonKind::Bool)
        require(a.bool_value == b.bool_value, where + " boolean");
}
J contract_json(const PcbPlacementContractResult &r) {
    return object({{"ok", boolean(r.ok)},
                   {"sheet", text(r.sheet)},
                   {"have_contract", boolean(r.have_contract)},
                   {"checked", num(r.checked)},
                   {"violations", strings_json(r.violations)},
                   {"missing_refs", strings_json(r.missing_refs)},
                   {"hot_loop_fail", num(r.hot_loop_fail)},
                   {"same_side_fail", num(r.same_side_fail)},
                   {"bulk_fail", num(r.bulk_fail)},
                   {"bulk_out_fail", num(r.bulk_out_fail)},
                   {"sw_node_fail", num(r.sw_node_fail)},
                   {"fb_fail", num(r.fb_fail)},
                   {"boot_fail", num(r.boot_fail)},
                   {"vcc_fail", num(r.vcc_fail)},
                   {"bias_fail", num(r.bias_fail)},
                   {"rt_fail", num(r.rt_fail)},
                   {"ldo_fail", num(r.ldo_fail)},
                   {"proximity_fail", num(r.proximity_fail)},
                   {"unknown_fail", num(r.unknown_fail)},
                   {"summary", text(r.summary())}});
}
J flow_json(const PcbPlacementFlowResult &r) {
    std::vector<J> terms;
    for (const auto &t : r.terms)
        terms.push_back(object({{"kind", text(t.kind)},
                                {"subject", text(t.subject)},
                                {"target", text(t.target)},
                                {"measured", num(t.measured)},
                                {"bound", num(t.bound)},
                                {"ok", boolean(t.ok)},
                                {"basis", text(t.basis)}}));
    return object({{"ok", boolean(r.ok)},
                   {"n_contracts", num(r.n_contracts)},
                   {"flow_checked", num(r.flow_checked)},
                   {"flow_fail", num(r.flow_fail)},
                   {"facing_checked", num(r.facing_checked)},
                   {"facing_fail", num(r.facing_fail)},
                   {"far_checked", num(r.far_checked)},
                   {"far_fail", num(r.far_fail)},
                   {"near_max_checked", num(r.near_max_checked)},
                   {"near_max_fail", num(r.near_max_fail)},
                   {"unresolved", strings_json(r.unresolved)},
                   {"na", strings_json(r.na)},
                   {"violations", strings_json(r.violations)},
                   {"detail", strings_json(r.detail)},
                   {"board_area", num(r.board_area)},
                   {"flow_budget_mm", num(r.flow_budget_mm)},
                   {"terms", array(terms)},
                   {"summary", text(r.summary())}});
}
J term_json(const FloorplanTerm &t) {
    return object({{"kind", text(t.kind)},
                   {"sheet", text(t.sheet)},
                   {"subject", text(t.subject)},
                   {"target_raw", text(t.target_raw)},
                   {"bound", t.bound ? num(*t.bound) : J{}},
                   {"basis", text(t.basis)},
                   {"enforced", boolean(t.enforced)},
                   {"output_roles", strings_json(t.output_roles)},
                   {"out_refs", strings_json(t.out_refs)}});
}
FloorplanTermIndex index_from(const J &index) {
    FloorplanTermIndex out;
    for (const auto &[name, rows] : index.object_value) {
        auto &dst = name == "hard" ? out.hard : name == "soft" ? out.soft : out.na;
        for (const auto &r : rows.array_value) {
            FloorplanTerm t;
            t.kind = string(r, "kind");
            t.sheet = string(r, "sheet");
            t.subject = string(r, "subject");
            t.target_raw = string(r, "target_raw");
            if (field(r, "bound").kind != JsonKind::Null)
                t.bound = number(r, "bound");
            t.basis = string(r, "basis");
            t.enforced = field(r, "enforced").bool_value;
            t.output_roles = strings(field(r, "output_roles"));
            t.out_refs = strings(field(r, "out_refs"));
            dst.push_back(t);
        }
    }
    return out;
}
J evals_json(const std::vector<FloorplanTermEval> &es) {
    std::vector<J> out;
    for (const auto &e : es)
        out.push_back(object({{"term", term_json(e.term)},
                              {"measured", num(e.measured)},
                              {"bound", num(e.bound)},
                              {"margin", num(e.margin)},
                              {"ok", boolean(e.ok)},
                              {"note", text(e.note)}}));
    return array(out);
}
J index_json(const FloorplanTermIndex &index) {
    auto terms = [](const std::vector<FloorplanTerm> &ts) {
        std::vector<J> out;
        for (const auto &t : ts)
            out.push_back(term_json(t));
        return array(out);
    };
    return object(
        {{"hard", terms(index.hard)}, {"soft", terms(index.soft)}, {"na", terms(index.na)}});
}
PcbFootprintPool footprints(const J &n) {
    PcbFootprintPool out;
    for (const auto &[k, v] : n.object_value)
        out[k] = pcb_check_footprint(k, v.string_value);
    return out;
}
std::map<std::string, std::string> mapping(const J &n) {
    std::map<std::string, std::string> out;
    for (const auto &[k, v] : n.object_value)
        out[k] = v.string_value;
    return out;
}
PcbCheckModel minimal_model(const J &m, const PcbFootprintPool &pool) {
    PcbCheckModel out;
    out.board_w = number(m, "board_w");
    out.board_h = number(m, "board_h");
    if (field(m, "som_core").kind != JsonKind::Null)
        out.som_core = box(field(m, "som_core"));
    for (const auto &r : field(m, "insts").array_value) {
        PcbCheckInstance i;
        i.ref = string(r, "ref");
        i.value = string(r, "value");
        i.footprint = string(r, "footprint");
        i.sheet = string(r, "sheet");
        i.side = string(r, "side");
        i.x = number(r, "x");
        i.y = number(r, "y");
        i.rotation = number(r, "rotation");
        i.mirror = field(r, "mirror").bool_value;
        i.mod = pool.at(string(r, "mod_path"));
        for (const auto &[pin, net] : field(r, "pad_nets").object_value)
            i.pad_nets[pin] = {static_cast<int>(net.array_value[0].number_value),
                               net.array_value[1].string_value};
        out.insts.push_back(i);
    }
    return out;
}
void synthetic(const std::filesystem::path &root) {
    auto raw =
        parse_json_file((root / "native/tests/data/pcb_placement_gates/synthetic.json").string());
    auto pool = footprints(field(raw, "footprints"));
    for (const auto &c : field(raw, "cases").array_value) {
        PcbCheckInput in(minimal_model(field(c, "model"), pool));
        auto name = string(c, "name");
        if (string(c, "kind") == "contract") {
            const auto &contract = field(c, "contract");
            auto got = check_pcb_placement_contract(
                in, string(c, "sheet"), contract.kind == JsonKind::Null ? nullptr : &contract,
                mapping(field(c, "ref_map")));
            same(contract_json(got), field(c, "expected"), name);
        } else {
            PcbPlacementGatePolicy p;
            for (const auto &[s, v] : field(c, "contracts").object_value)
                p.contracts[s] = v;
            for (const auto &[s, v] : field(c, "ref_maps").object_value)
                p.ref_maps[s] = mapping(v);
            auto names = strings(field(c, "zones"));
            p.project_zones.insert(names.begin(), names.end());
            same(flow_json(check_pcb_placement_flow(in, p, &p.contracts)), field(c, "expected"),
                 name);
        }
    }
    std::cout << "64 independent synthetic contract/flow cases passed\n";
}
J &edit(J &n, const std::string &key) {
    for (auto &[k, v] : n.object_value)
        if (k == key)
            return v;
    throw std::runtime_error("missing mutable " + key);
}
void compose_equal(const PcbComposeReport &got, const J &row, const std::string &name) {
    same(evals_json(got.evaluations), field(row, "evals"), name + "/evals");
    same(text(got.text()), field(row, "report"), name + "/report");
    same(array({strings_json(got.unmanaged), strings_json(got.managed)}), field(row, "intrusions"),
         name + "/intrusions");
    std::vector<J> cross;
    for (const auto &[p, v] : got.cross_airwires)
        cross.push_back(
            array({array({text(p.first), text(p.second)}), array({num(v.first), num(v.second)})}));
    same(array(cross), field(row, "cross"), name + "/cross");
}
void adversarial(const std::filesystem::path &root) {
    auto raw =
        parse_json_file((root / "native/tests/data/pcb_placement_gates/adversarial.json").string());
    auto pool = footprints(field(raw, "footprints"));
    for (const auto &row : field(raw, "cases").array_value) {
        auto model = minimal_model(field(row, "model"), pool);
        PcbCheckInput input(model);
        PcbPlacementGatePolicy policy;
        for (const auto &[s, c] : field(row, "contracts").object_value)
            policy.contracts[s] = c;
        for (const auto &[s, c] : field(row, "ref_maps").object_value)
            policy.ref_maps[s] = mapping(c);
        for (const auto &s : strings(field(row, "wired")))
            policy.wired_sheets.insert(s);
        for (const auto &s : strings(field(row, "zones")))
            policy.project_zones.insert(s);
        auto name = "adversarial/" + string(row, "name");
        auto cov = pcb_contract_coverage(input, policy);
        require(cov.size() == field(row, "coverage").object_value.size(), name + " coverage size");
        for (const auto &[s, r] : cov)
            same(contract_json(r), field(field(row, "coverage"), s), name + "/coverage/" + s);
        auto all = check_all_pcb_placement_contracts(input, policy);
        require(all.size() == field(row, "check_all").object_value.size(),
                name + " check_all size");
        for (const auto &[s, r] : all)
            same(contract_json(r), field(field(row, "check_all"), s), name + "/check_all/" + s);
        auto evidence = pcb_compose_evidence(field(row, "sidecar"));
        auto index = index_from(field(field(row, "compose"), "index"));
        auto gates = check_pcb_placement_gates(input, policy, index, evidence);
        same(contract_json(gates.placement_contract), field(row, "wired_result"), name + "/wired");
        same(flow_json(gates.placement_flow), field(row, "flow"), name + "/flow");
        auto &report = gates.coverage_report;
        same(array({text(report.text), num(report.wired), num(report.met), num(report.violated)}),
             field(row, "coverage_report"), name + "/coverage report");
        compose_equal(gates.composition, field(row, "compose"), name + "/compose");
        require(gates.ok() == (field(field(row, "wired_result"), "ok").bool_value &&
                               field(field(row, "flow"), "ok").bool_value),
                name + " aggregate verdict retains hard/advisory policy");
    }
    std::cout << "25 independent hard/advisory, corridor and exact-boundary mutations passed\n";
}
void baseline(const std::filesystem::path &root, const std::string &project) {
    auto raw = parse_json_file(
        (root / "native/tests/data/pcb_placement_gates" / (project + ".json")).string());
    auto f = load(root, project);
    auto model = pcb_model_from_json(f.model, f.expected_pool);
    PcbCheckInput input(model);
    auto policy = pcb_placement_gate_policy(f.input);
    require(policy.contracts.size() == field(raw, "contracts").object_value.size(),
            project + " policy contract count");
    for (const auto &[s, refs] : field(raw, "ref_maps").object_value)
        require(policy.ref_maps.at(s) == mapping(refs),
                project + " live canonical board refs " + s);
    auto names = strings(field(raw, "zones"));
    require(policy.project_zones == std::set<std::string>(names.begin(), names.end()),
            project + " live project zone scope");
    names = strings(field(raw, "wired"));
    require(policy.wired_sheets == std::set<std::string>(names.begin(), names.end()),
            project + " live wired policy");
    auto cov = pcb_contract_coverage(input, policy);
    require(cov.size() == field(raw, "coverage").object_value.size(), project + " coverage count");
    for (const auto &[s, r] : cov)
        same(contract_json(r), field(field(raw, "coverage"), s), project + "/coverage/" + s);
    auto all = check_all_pcb_placement_contracts(input, policy);
    require(all.size() == field(raw, "check_all").object_value.size(),
            project + " check_all count");
    for (const auto &[s, r] : all)
        same(contract_json(r), field(field(raw, "check_all"), s), project + "/check_all/" + s);
    auto report = render_pcb_contract_coverage(cov, policy.wired_sheets);
    same(array({text(report.text), num(report.wired), num(report.met), num(report.violated)}),
         field(raw, "coverage_report"), project + "/coverage_report");
    same(contract_json(check_pcb_wired_contracts(input, policy)), field(raw, "wired_result"),
         project + "/wired");
    same(flow_json(check_pcb_placement_flow(input, policy)), field(raw, "flow"), project + "/flow");
    validate_pcb_contract_pins(policy);
    ++checks;
    for (const auto &c : field(raw, "pin_cases").array_value) {
        auto sheet = string(c, "sheet"), key = string(c, "field");
        auto contract = policy.contracts.at(sheet);
        auto &st = edit(contract, "structures")
                       .array_value.at(static_cast<std::size_t>(number(c, "index")));
        if (key == "min_from.pin") {
            auto &mf = edit(st, "min_from").array_value.front();
            if (object_field(mf, "pin"))
                edit(mf, "pin") = field(c, "value");
            else
                mf.object_value.emplace_back("pin", field(c, "value"));
        } else
            edit(st, key) = field(c, "value");
        std::string error;
        try {
            validate_pcb_contract_pins(sheet, contract, policy.source_parts.at(sheet));
        } catch (const PcbContractPinError &e) {
            error = e.what();
        }
        if (field(c, "error").kind == JsonKind::Null)
            require(error.empty(), project + " unresolved pin soft policy");
        else
            same(text(error), field(c, "error"), project + "/pin/" + sheet + "/" + key);
    }
    auto evidence = pcb_compose_evidence(field(raw, "sidecar"));
    require(evidence.corridors.size() == 6, project + " six independently captured corridors");
    auto current = pcb_compose_evidence(model);
    require(current.corridors.size() == evidence.corridors.size(),
            project + " current-model evidence complete");
    auto nets = ratsnest_net_pad_positions(model);
    auto edges = ratsnest_mst(nets);
    for (const auto &row : field(raw, "compose").array_value) {
        auto m = model;
        auto name = string(row, "name");
        if (name == "moved_power_first") {
            auto i = std::find_if(m.insts.begin(), m.insts.end(),
                                  [](const auto &i) { return i.sheet == "power"; });
            require(i != m.insts.end(), "power mutation target");
            i->x += 100;
        } else if (name == "missing_power")
            m.insts.erase(std::remove_if(m.insts.begin(), m.insts.end(),
                                         [](const auto &i) { return i.sheet == "power"; }),
                          m.insts.end());
        auto index = index_from(field(row, "index"));
        auto got = report_pcb_composition(PcbCheckInput(m), index, policy, evidence, &nets, &edges);
        compose_equal(got, row, project + "/compose/" + name);
        if (name == "baseline") {
            auto full = check_pcb_placement_gates(input, policy, index, evidence);
            compose_equal(full.composition, row, project + "/complete composition");
            same(contract_json(full.placement_contract), field(raw, "wired_result"),
                 project + "/complete wired");
            same(flow_json(full.placement_flow), field(raw, "flow"), project + "/complete flow");
            require(full.ok() == (full.placement_contract.ok && full.placement_flow.ok),
                    "original verdict policy");
            require(report_pcb_composition(input, index, policy, current).text() == got.text(),
                    project + " current model matches just-emitted sidecar evidence");
            auto production = check_pcb_placement_gates(f.input, model);
            compose_equal(production.composition, row, project + "/production overload");
            same(contract_json(production.placement_contract), field(raw, "wired_result"),
                 project + "/production wired");
            same(flow_json(production.placement_flow), field(raw, "flow"),
                 project + "/production flow");
        }
    }
    auto scoped = parse_json_file(
        (root / "native/tests/data/pcb_placement_gates" / (project + "_scoped.json")).string());
    for (const auto &row : field(scoped, "compose").array_value) {
        auto name = string(row, "name");
        if (name == "extra_terms")
            continue;
        auto m = model;
        if (name == "moved_power_first")
            std::find_if(m.insts.begin(), m.insts.end(), [](const auto &i) {
                return i.sheet == "power";
            })->x += 100;
        else if (name == "missing_power")
            m.insts.erase(std::remove_if(m.insts.begin(), m.insts.end(),
                                         [](const auto &i) { return i.sheet == "power"; }),
                          m.insts.end());
        auto index = pcb_final_compose_index(f.input, m);
        same(index_json(index), field(row, "index"), project + "/placed scope/" + name);
        compose_equal(report_pcb_composition(PcbCheckInput(m), index, policy, evidence), row,
                      project + "/scoped report/" + name);
    }
    auto recomputed = parse_json_file(
        (root / "native/tests/data/pcb_placement_gates" / (project + "_recomputed.json")).string());
    for (const auto &row : field(recomputed, "compose").array_value) {
        auto m = model;
        auto name = string(row, "name");
        if (name == "moved_power_first")
            std::find_if(m.insts.begin(), m.insts.end(), [](const auto &i) {
                return i.sheet == "power";
            })->x += 100;
        else if (name == "missing_power")
            m.insts.erase(std::remove_if(m.insts.begin(), m.insts.end(),
                                         [](const auto &i) { return i.sheet == "power"; }),
                          m.insts.end());
        compose_equal(report_pcb_composition(PcbCheckInput(m), index_from(field(row, "index")),
                                             policy, evidence),
                      row, project + "/fresh model/" + name);
    }
    std::cout << project
              << ": full gates, reports, pin mutations and final compose mutations passed\n";
}
void typed_guards() {
    auto reject = [](auto &&fn, const std::string &why) {
        bool rejected = false;
        try {
            fn();
        } catch (const std::exception &) {
            rejected = true;
        }
        require(rejected, why);
    };
    require(pcb_compose_evidence(J{}).corridors.empty(), "missing prior sidecar stays empty");
    auto bad =
        object({{"t1_constraints",
                 object({{"corridors", object({{"x", object({{"rect", array({num(2), num(0), num(1),
                                                                             num(1)})}})}})}})}});
    reject([&] { pcb_compose_evidence(bad); }, "inverted sidecar is not silent success");
    edit(edit(edit(bad, "t1_constraints"), "corridors").object_value[0].second, "rect")
        .array_value.pop_back();
    reject([&] { pcb_compose_evidence(bad); }, "short sidecar rectangle rejected");
    PcbCheckModel model;
    model.board_w = model.board_h = 10;
    PcbCheckInput input(model);
    for (const auto *type :
         {"hot_loop", "bulk_in", "bulk_out", "sw_node", "fb_cluster", "boot", "vcc_cap", "bias_cap",
          "rt_r", "ldo_stage", "proximity", "same_side"}) {
        auto malformed = object({{"structures", array({object({{"type", text(type)}})})}});
        reject([&] { check_pcb_placement_contract(input, "power", &malformed, {}); },
               std::string("missing required policy fields reject: ") + type);
    }
    FloorplanTermIndex index;
    FloorplanTerm term;
    term.kind = "unimplemented";
    index.hard.push_back(term);
    reject([&] { measure_pcb_compose_terms(input, index, {}); },
           "unknown typed compose term rejected");
    RatsnestNets nets{{"N", {{1, 1, "A", "a"}, {2, 2, "B", "b"}}}};
    RatsnestEdges edges{{"N", {{0, 2}}}};
    reject([&] { pcb_cross_airwires_by_pair(model, &nets, &edges); },
           "out-of-range MST endpoint rejected");
    edges.clear();
    reject([&] { pcb_cross_airwires_by_pair(model, &nets, &edges); }, "missing MST net rejected");
    auto contract =
        object({{"structures", array({object({{"type", text("proximity")},
                                              {"anchor", text("U1")},
                                              {"anchor_pins", array({text("1")})}})})}});
    auto fp = pcb_check_footprint("unchanged-source.kicad_mod",
                                  "(footprint \"x\" (pad \"1\" smd rect (at 0 0) (size 1 1)))");
    std::map<std::string, PcbContractSourcePart> parts{{"U1", {"test:x", fp}}};
    validate_pcb_contract_pins("test", contract, parts);
    ++checks;
    parts.at("U1").mod = pcb_check_footprint(
        "unchanged-source.kicad_mod", "(footprint \"x\" (pad \"2\" smd rect (at 0 0) (size 1 1)))");
    reject([&] { validate_pcb_contract_pins("test", contract, parts); },
           "new immutable footprint bytes invalidate pin validation");
    parts.at("U1").mod.reset();
    validate_pcb_contract_pins("test", contract, parts);
    ++checks;
}
} // namespace
int main(int argc, char **argv) {
    try {
        if (argc != 2)
            throw std::runtime_error("repo root required");
        synthetic(argv[1]);
        adversarial(argv[1]);
        typed_guards();
        baseline(argv[1], "carrier");
        baseline(argv[1], "devkit_mini");
        std::cout << "PCB independent placement gates: " << checks << " assertions passed\n";
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
