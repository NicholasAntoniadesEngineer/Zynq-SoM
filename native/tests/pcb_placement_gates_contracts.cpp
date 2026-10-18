#include "pcb_placement_fixture.hpp"
#include "schgen/pcb_placement_gates.hpp"
#include "schgen/ratsnest_gate.hpp"
#include <cmath>
#include <iostream>
#include <limits>
#include <sstream>

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
bool same_flow(const PcbPlacementFlowResult& got,J expected,const std::string& where) {
    // Retain frozen measurements and every non-flow requirement. Only finite
    // heuristic-distance failures change classification; unresolved endpoints
    // must retain the original failure. Historical report prose is not policy.
    auto mutable_field=[&](const std::string& key)->J& {
        for(auto& [k,v]:expected.object_value)if(k==key)return v;
        throw std::runtime_error("missing expected flow field "+key);
    };
    std::vector<std::string> distance_failures;
    for(const auto& term:field(expected,"terms").array_value)
        if(string(term,"kind")=="flow"&&field(term,"measured").kind==JsonKind::Number&&!field(term,"ok").bool_value)
            distance_failures.push_back("flow "+string(term,"subject")+"->"+string(term,"target")+": ");
    auto& violations=mutable_field("violations").array_value;
    const auto before=violations.size();
    violations.erase(std::remove_if(violations.begin(),violations.end(),[&](const auto& v){
        return v.string_value.find("mm budget (FLOW_K=")!=std::string::npos&&
            std::any_of(distance_failures.begin(),distance_failures.end(),[&](const auto& prefix){return v.string_value.rfind(prefix,0)==0;});
    }),violations.end());
    require(before-violations.size()==distance_failures.size(),where+" independently classified distance failures");
    mutable_field("flow_fail").number_value-=distance_failures.size();
    const bool ok=violations.empty()&&field(expected,"unresolved").array_value.empty();
    mutable_field("ok")=boolean(ok);
    auto actual=flow_json(got);
    for(auto* row:{&expected,&actual})row->object_value.erase(std::remove_if(row->object_value.begin(),row->object_value.end(),
        [](const auto& entry){return entry.first=="summary";}),row->object_value.end());
    same(actual,expected,where);
    for(const auto& term:got.terms)if(term.kind=="flow") {
        require(term.advisory==std::isfinite(term.measured),where+" heuristic distance marked advisory only when resolved");
        if(std::isfinite(term.measured))require(got.summary().find("not a trace-length or hardware limit")!=std::string::npos,
            where+" advisory provenance visible");
    }
    return ok;
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
            same_flow(check_pcb_placement_flow(in, p, &p.contracts), field(c, "expected"),
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
    // Preserve every historical term/verdict/report byte except the invalid
    // mixed-unit summary. Frozen expectations are not rewritten from production.
    const auto without_summary=[&](const std::string& report,const std::string& prefix,int expected){
        std::istringstream input(report);std::string line,out;int removed=0;
        while(std::getline(input,line)) {
            if(line.rfind(prefix,0)==0)++removed;else out+=line+'\n';
        }
        require(removed==expected,name+" exact summary replacement boundary");return out;
    };
    require(without_summary(got.text(),"  hard margins (",2)==
            without_summary(field(row,"report").string_value,"  aggregate hard margin:",1),name+" unchanged non-summary report");
    for(bool angular:{false,true}) {
        std::size_t measured=0,unresolved=0;double sum=0;std::optional<double> minimum;
        for(const auto& e:got.evaluations)if(e.term.enforced&&(e.term.kind=="facing")==angular) {
            if(e.note=="UNRESOLVED"||!std::isfinite(e.margin)){++unresolved;continue;}
            ++measured;sum+=e.margin;if(!minimum||e.margin<*minimum)minimum=e.margin;
        }
        const auto& actual=angular?got.hard_margins.facing_degrees:got.hard_margins.distance_mm;
        require(actual.measured==measured&&actual.unresolved==unresolved&&
                actual.minimum.has_value()==minimum.has_value()&&std::abs(actual.sum-sum)<=.00500001&&
                (!minimum||std::abs(*actual.minimum-*minimum)<=.00500001),name+" unit-separated oracle evaluations");
    }
    same(array({strings_json(got.unmanaged), strings_json(got.managed)}), field(row, "intrusions"),
         name + "/intrusions");
    std::vector<J> cross;
    for (const auto &[p, v] : got.cross_airwires)
        cross.push_back(
            array({array({text(p.first), text(p.second)}), array({num(v.first), num(v.second)})}));
    same(array(cross), field(row, "cross"), name + "/cross");
}
void generated_compose_equal(const PcbComposeReport& current,const PcbComposeReport& historical,const std::string& where) {
    require(current.evaluations.size()==historical.evaluations.size(),where+" retains every evaluated term");
    auto expected_na=historical.index.na;
    for(auto& term:expected_na)if(term.kind=="flow_hop") {
        term.prefer_short_flow=term.enforced;term.enforced=false;
        require(term.basis.rfind("flow chain",0)==0,where+" unexpected historical flow provenance");
        term.basis.replace(0,std::string("flow chain").size(),"ADVISORY board-size-derived flow preference");
    }
    same(index_json(FloorplanTermIndex{{},{},current.index.na}),index_json(FloorplanTermIndex{{},{},expected_na}),where+" retains project scope");
    for(std::size_t i=0;i<expected_na.size();++i)
        require(current.index.na[i].prefer_short_flow==expected_na[i].prefer_short_flow,where+" NA intent provenance");
    int hard_red=0,soft_red=0;
    for(const auto& old:historical.evaluations) {
        const auto found=std::find_if(current.evaluations.begin(),current.evaluations.end(),[&](const auto& e){
            return e.term.kind==old.term.kind&&e.term.subject==old.term.subject&&e.term.target()==old.term.target();
        });
        require(found!=current.evaluations.end(),where+" lost term");
        if(old.term.kind=="flow_hop") {
            require(!found->term.enforced&&found->term.prefer_short_flow==old.term.enforced,where+" preference differs from wired scope");
            require(found->measured==old.measured&&found->bound==old.bound&&found->margin==old.margin&&found->ok==old.ok,
                    where+" changed measured geometry or hid negative preference");
        }else same(evals_json({*found}),evals_json({old}),where+" non-flow requirement");
        if(!old.ok)++((old.term.kind!="flow_hop"&&old.term.enforced)?hard_red:soft_red);
    }
    require(current.hard_red==hard_red&&current.soft_red==soft_red,where+" red classification");
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
        const bool expected_flow_ok=same_flow(gates.placement_flow, field(row, "flow"), name + "/flow");
        auto &report = gates.coverage_report;
        same(array({text(report.text), num(report.wired), num(report.met), num(report.violated)}),
             field(row, "coverage_report"), name + "/coverage report");
        compose_equal(gates.composition, field(row, "compose"), name + "/compose");
        require(gates.ok() == (field(field(row, "wired_result"), "ok").bool_value &&
                               expected_flow_ok),
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
    same_flow(check_pcb_placement_flow(input, policy), field(raw, "flow"), project + "/flow");
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
            same_flow(full.placement_flow, field(raw, "flow"), project + "/complete flow");
            require(full.ok() == (full.placement_contract.ok && full.placement_flow.ok),
                    "original verdict policy");
            require(report_pcb_composition(input, index, policy, current).text() == got.text(),
                    project + " current model matches just-emitted sidecar evidence");
            auto production = check_pcb_placement_gates(f.input, model);
            generated_compose_equal(production.composition,got,project+"/production");
            same(contract_json(production.placement_contract), field(raw, "wired_result"),
                 project + "/production wired");
            same_flow(production.placement_flow, field(raw, "flow"),
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
        const auto historical=report_pcb_composition(PcbCheckInput(m),index_from(field(row,"index")),policy,evidence);
        compose_equal(historical,row,project+"/frozen scoped measurements/"+name);
        generated_compose_equal(report_pcb_composition(PcbCheckInput(m),index,policy,evidence),historical,
                                project+"/scoped report/"+name);
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
    const auto margin=[](const std::string& kind,double value,bool enforced=true,const std::string& note="") {
        FloorplanTerm term;term.kind=kind;term.enforced=enforced;
        return FloorplanTermEval{term,0,0,value,value>=0,note};
    };
    const auto grouped=pcb_compose_hard_margins({margin("near_max",3.25),margin("far_min",-1.25),
        margin("facing",.5),margin("facing",-90,true,"UNRESOLVED"),margin("facing",999,false),
        margin("flow_hop",INFINITY),margin("near_max",NAN)});
    require(grouped.distance_mm.measured==2&&grouped.distance_mm.unresolved==2&&
            grouped.distance_mm.sum==2&&grouped.distance_mm.minimum== -1.25,
            "linear margins retain actual failures without angles or unresolved sentinels");
    require(grouped.facing_degrees.measured==1&&grouped.facing_degrees.unresolved==1&&
            grouped.facing_degrees.sum==.5&&grouped.facing_degrees.minimum==.5,
            "finite unresolved facing sentinel and advisory terms are not measurements");
    const auto empty=pcb_compose_hard_margins({});
    require(!empty.distance_mm.minimum&&!empty.facing_degrees.minimum&&
            empty.distance_mm.measured==0&&empty.facing_degrees.measured==0,"absent margin is not zero clearance");
    require(pcb_compose_hard_margins({margin("near_max",0)}).distance_mm.minimum==0,
            "measured zero slack remains distinct from absent margin");
    reject([&]{pcb_compose_hard_margins({margin("unknown",1)});},"unknown margin unit rejected");
    reject([&]{pcb_compose_hard_margins({margin("far_min",std::numeric_limits<double>::max()),
        margin("far_min",std::numeric_limits<double>::max())});},"unrepresentable summary rejected");
    PcbComposeReport unit_report;unit_report.hard_margins=grouped;
    const auto unit_text=unit_report.text();
    require(unit_text.find("hard margins (mm): measured 2, unresolved 2, sum 2.0, min -1.25")!=std::string::npos&&
            unit_text.find("hard margins (degrees): measured 1, unresolved 1, sum 0.5, min 0.5")!=std::string::npos,
            "report labels measured populations and actual units");
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
void flow_outline_sensitivity_witness() {
    // Diagnostic for the existing global heuristic, not a hardware requirement
    // or a qualified board. Shrinking empty outline area changes its verdict
    // even though every component and pad stays in exactly the same place.
    PcbPlacementGatePolicy policy;policy.wired_sheets={"source"};
    policy.project_zones={"source","load"};
    policy.contracts["source"]=parse_json_text(
        R"({"contract":"placement/v2","external":{"flow":["source","load"]}})");
    PcbCheckModel model;model.board_w=model.board_h=120;
    for(const auto& row:std::vector<std::pair<std::string,double>>{{"source",10},{"load",50}}) {
        PcbCheckInstance i;i.ref=row.first;i.sheet=row.first;i.x=row.second;i.y=10;
        i.mod=pcb_check_footprint("outline-witness","(footprint x (pad 1 smd rect (at 0 0) (size 1 1)))");
        i.pad_nets={{"1",{1,"SUPPLY"}}};model.insts.push_back(i);
    }
    const PcbCheckInput large_input(model);
    const auto large=check_pcb_placement_flow(large_input,policy);
    model.board_w=model.board_h=60;
    const PcbCheckInput small_input(model);
    const auto small=check_pcb_placement_flow(small_input,policy);
    require(large.ok&&small.ok&&small.flow_fail==0,"empty outline area must not reject unchanged physical geometry");
    require(large.terms[0].ok&&!small.terms[0].ok&&large.terms[0].advisory&&small.terms[0].advisory,
            "negative heuristic comparison must remain visible, not a fabricated PASS");
    require(large.terms.size()==1&&small.terms.size()==1&&large.terms[0].measured==40&&small.terms[0].measured==40,
            "outline witness changed component distance");
    require(large.flow_budget_mm==42&&small.flow_budget_mm==21,"outline witness budget calculation incorrect");
    for(std::size_t i=0;i<model.insts.size();++i) {
        const auto a=large_input.geometry_at(i).pad_boxes.at("1"),b=small_input.geometry_at(i).pad_boxes.at("1");
        require(a.x0==b.x0&&a.x1==b.x1&&a.y0==b.y0&&a.y1==b.y1&&b.x0>=0&&b.y0>=0&&b.x1<=60&&b.y1<=60,
                "outline witness moved pads or violated the smaller outline");
    }
    model.insts.pop_back();
    const auto missing=check_pcb_placement_flow(PcbCheckInput(model),policy);
    require(!missing.ok&&!missing.unresolved.empty(),"missing flow endpoint must remain an independent rejection");
    std::cout<<"flow outline policy: identical 40mm endpoints accepted on both outlines; 21mm heuristic preference remains unsatisfied\n";
}
void advisory_facing_policy() {
    PcbPlacementGatePolicy policy;policy.wired_sheets={"source"};policy.project_zones={"source","load"};
    const auto contract=[](const std::string& extra){return parse_json_text(
        "{\"contract\":\"placement/v2\",\"roles\":{\"C1\":\"cout_bulk\"},\"external\":{"
        "\"downstream\":\"load\",\"output_roles\":[\"cout_bulk\"]"+extra+"}}");};
    policy.ref_maps["source"]={{"C1","C1"}};
    PcbCheckModel model;model.board_w=model.board_h=60;
    for(const auto& row:std::vector<std::tuple<std::string,std::string,double,double>>{
        {"U1","source",10,10},{"C1","source",12,10},{"TP1","source",10,30},{"LOAD","load",20,20}}) {
        PcbCheckInstance i;i.ref=std::get<0>(row);i.sheet=std::get<1>(row);
        i.x=std::get<2>(row);i.y=std::get<3>(row);
        i.mod=pcb_check_footprint("synthetic","(footprint x (pad 1 smd rect (at 0 0) (size 1 1)))");
        model.insts.push_back(i);
    }
    policy.contracts["source"]=contract("");
    const auto hard=check_pcb_placement_flow(PcbCheckInput(model),policy);
    require(!hard.ok&&hard.facing_fail==1&&hard.advisories.empty(),"unreviewed facing silently relaxed");
    const std::string advisory=",\"facing_advisory_basis\":\"reviewed centroid sensitivity witness\"";
    policy.contracts["source"]=contract(advisory);
    const auto soft=check_pcb_placement_flow(PcbCheckInput(model),policy);
    require(soft.ok&&soft.facing_fail==0&&soft.advisories.size()==1&&soft.terms.size()==1&&
            !soft.terms[0].ok&&soft.terms[0].advisory,"negative preference lost or reported as satisfied");
    require(soft.summary().find("preference NOT satisfied")!=std::string::npos&&
            soft.summary().find("not hardware qualification")!=std::string::npos,"advisory not visibly reported");
    auto missing=model;missing.insts.erase(missing.insts.begin()+1);
    const auto unresolved=check_pcb_placement_flow(PcbCheckInput(missing),policy);
    require(!unresolved.ok&&!unresolved.unresolved.empty(),"missing advisory geometry was waived");
    policy.contracts["source"]=contract(advisory+",\"far\":[{\"what\":\"load\",\"min_mm\":100}]");
    const auto separated=check_pcb_placement_flow(PcbCheckInput(model),policy);
    require(!separated.ok&&separated.far_fail==1,"advisory facing relaxed another hard constraint");
    for(const std::string bad:{"\"\"","\"   \"","false","12","[]"}) {
        policy.contracts["source"]=contract(",\"facing_advisory_basis\":"+bad);
        bool rejected=false;try{(void)check_pcb_placement_flow(PcbCheckInput(model),policy);}
        catch(const std::invalid_argument&){rejected=true;}
        require(rejected,"invalid advisory provenance accepted");
    }
}
void power_som_centroid_policy(const std::filesystem::path& root) {
    const auto contract=parse_json_file((root/"carrier/subsystems/power_som/placement_contract.json").string());
    require(pcb_facing_advisory_basis(contract).has_value(),"reviewed SoM centroid policy needs explicit provenance");
    auto strict=contract;
    for(auto& [key,value]:strict.object_value)if(key=="external")
        value.object_value.erase(std::remove_if(value.object_value.begin(),value.object_value.end(),
            [](const auto& p){return p.first=="facing_advisory_basis";}),value.object_value.end());
    for(bool flip_x:{false,true})for(bool flip_y:{false,true})for(bool moved:{false,true}) {
        const auto point=[&](double x,double y){return std::make_pair(flip_x?60-x:x,flip_y?60-y:y);};
        PcbPlacementGatePolicy policy;policy.wired_sheets={"power_som"};policy.project_zones={"power_som"};
        policy.ref_maps["power_som"]={{"U4","U4"},{"C18","C18"},{"C19","C19"}};
        PcbCheckModel model;model.board_w=model.board_h=60;
        const auto load=point(20,20);model.som_core=Box4{load.first-1,load.second-1,load.first+1,load.second+1};
        for(const auto& [ref,x,y]:std::vector<std::tuple<std::string,double,double>>{
            {"U4",10,10},{"C18",12,10},{"C19",12,10},{"TP1",10,moved?30.:11.}}) {
            const auto p=point(x,y);PcbCheckInstance i;i.ref=ref;i.sheet="power_som";i.x=p.first;i.y=p.second;
            model.insts.push_back(i);
        }
        // Deliberately isolated centroid diagnostic, not physical board qualification.
        policy.contracts["power_som"]=strict;
        const auto hard=check_pcb_placement_flow(PcbCheckInput(model),policy);
        require(hard.facing_checked==1&&hard.facing_fail==(moved?1:0)&&hard.ok!=moved,
            "actual SoM centroid rule must expose sensitivity to unrelated testpoint movement");
        policy.contracts["power_som"]=contract;
        const auto soft=check_pcb_placement_flow(PcbCheckInput(model),policy);
        require(soft.ok&&soft.facing_fail==0&&soft.advisories.size()==1&&soft.terms.size()==1&&
            soft.terms[0].advisory&&soft.terms[0].ok!=moved,
            "reviewed SoM preference must retain negative evidence without hardware PASS claim");
        for(int mode=0;mode<5;++mode)for(bool advisory:{false,true}) {
            auto broken=model;auto partial=policy;
            partial.contracts["power_som"]=advisory?contract:strict;
            if(mode==0)partial.ref_maps["power_som"].erase("C19");
            if(mode==1)broken.insts.erase(broken.insts.begin()+2);
            if(mode==2)broken.insts[2].sheet="unrelated";
            if(mode==3)partial.ref_maps["power_som"]["C19"]="C18";
            if(mode==4)broken.insts.push_back(broken.insts[2]);
            const auto bad=check_pcb_placement_flow(PcbCheckInput(broken),partial);
            require(!bad.ok&&bad.facing_fail==1&&!bad.unresolved.empty()&&bad.advisories.empty(),
                "partial or ambiguous output centroid must remain unresolved, mode="+std::to_string(mode));
            FloorplanTerm term;term.kind="facing";term.subject="power_som";term.target_raw="@som";
            term.output_roles={"C18","C19"};term.enforced=!advisory;
            FloorplanTermIndex index;(advisory?index.soft:index.hard).push_back(term);
            const auto measured=measure_pcb_compose_terms(PcbCheckInput(broken),index,partial);
            require(measured.size()==1&&!measured[0].ok&&measured[0].note=="UNRESOLVED",
                "composition must not report a partial output centroid as measured");
            if(mode==1||mode==2||mode==4) {
                auto& direct=(advisory?index.soft:index.hard).front();
                direct.out_refs={"C18","C19"};direct.output_roles.clear();
                const auto explicit_refs=measure_pcb_compose_terms(PcbCheckInput(broken),index,partial);
                require(explicit_refs.size()==1&&!explicit_refs[0].ok&&explicit_refs[0].note=="UNRESOLVED",
                    "explicit output refs must also require complete unique model members");
            }
        }
        for(const auto& refs:std::vector<std::vector<std::string>>{
            {"C18","C18"},{"C18",""},{"C18","absent"}}) {
            FloorplanTerm term;term.kind="facing";term.subject="power_som";term.target_raw="@som";term.out_refs=refs;
            FloorplanTermIndex index;index.soft.push_back(term);
            const auto measured=measure_pcb_compose_terms(PcbCheckInput(model),index,policy);
            require(measured.size()==1&&!measured[0].ok&&measured[0].note=="UNRESOLVED",
                "malformed explicit output membership must not become a partial centroid");
        }
        model.som_core.reset();
        const auto unresolved=check_pcb_placement_flow(PcbCheckInput(model),policy);
        require(!unresolved.ok&&!unresolved.unresolved.empty(),"missing SoM geometry must remain a failure");
    }
}
} // namespace
int main(int argc, char **argv) {
    try {
        if (argc != 2)
            throw std::runtime_error("repo root required");
        synthetic(argv[1]);
        adversarial(argv[1]);
        typed_guards();
        flow_outline_sensitivity_witness();
        advisory_facing_policy();
        power_som_centroid_policy(argv[1]);
        baseline(argv[1], "carrier");
        baseline(argv[1], "devkit_mini");
        std::cout << "PCB independent placement gates: " << checks << " assertions passed\n";
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
