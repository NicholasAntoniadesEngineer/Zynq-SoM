#include "pcb_placement_gates_internal.hpp"
#include "schgen/board_schematic.hpp"

namespace schgen {
using namespace placement_gates;
PcbPlacementGatePolicy pcb_placement_gate_policy(const PcbPlacementInput &in) {
    PcbPlacementGatePolicy p;
    p.contracts = in.contracts;
    p.wired_sheets.insert(in.floorplan.project.wired_sheets.begin(),
                          in.floorplan.project.wired_sheets.end());
    const std::map<std::string, int> bands(in.floorplan.sheet_index.begin(),
                                           in.floorplan.sheet_index.end());
    for (std::size_t k = 0; k < in.floorplan.sheets.size(); ++k) {
        const auto &sheet = in.floorplan.sheets[k];
        p.project_zones.insert(sheet.name);
        int band = bands.count(sheet.name) ? bands.at(sheet.name) : static_cast<int>(k + 1);
        for (const auto &part : sheet.parts) {
            p.ref_maps[sheet.name][part.ref] = board_renamed_ref(part.ref, band, sheet.name);
            auto &src = p.source_parts[sheet.name][part.ref];
            src.footprint = part.footprint;
            auto fp = in.floorplan.footprint_of.find(part.footprint);
            if (fp != in.floorplan.footprint_of.end()) {
                auto hit = in.footprints.find(fp->second);
                if (hit != in.footprints.end())
                    src.mod = hit->second;
            }
        }
    }
    return p;
}
namespace {
void named_pins(const JsonNode &v, std::vector<std::string> &out) {
    if (v.kind == JsonKind::String)
        out.push_back(v.string_value);
    else
        for (const auto &child : array(v))
            named_pins(child, out);
}
const std::vector<std::pair<std::string, std::string>> &pin_fields(const std::string &type) {
    static const std::map<std::string, std::vector<std::pair<std::string, std::string>>> fields{
        {"hot_loop", {{"ic", "pin_pairs"}}},
        {"bulk_in", {{"ic", "vin_pins"}}},
        {"bulk_out", {{"inductor", "inductor_out_pin"}}},
        {"sw_node", {{"ic", "sw_pin"}}},
        {"fb_cluster", {{"ic", "fb_pin"}, {"ic", "own_sw_pin"}, {"foreign_ic", "foreign_sw_pin"}}},
        {"boot", {{"ic", "pins"}}},
        {"vcc_cap", {{"ic", "pin"}}},
        {"bias_cap", {{"ic", "pin"}}},
        {"rt_r", {{"ic", "pin"}}},
        {"ldo_stage", {{"ic", "cin_pin"}, {"ic", "cout_pin"}}},
        {"proximity", {{"anchor", "anchor_pins"}}}};
    static const std::vector<std::pair<std::string, std::string>> empty;
    auto i = fields.find(type);
    return i == fields.end() ? empty : i->second;
}
using Counter = int PcbPlacementContractResult::*;
const std::vector<std::pair<std::string, Counter>> &counters() {
    static const std::vector<std::pair<std::string, Counter>> c{
        {"hot_loop", &PcbPlacementContractResult::hot_loop_fail},
        {"same_side", &PcbPlacementContractResult::same_side_fail},
        {"bulk", &PcbPlacementContractResult::bulk_fail},
        {"bulk_out", &PcbPlacementContractResult::bulk_out_fail},
        {"sw_node", &PcbPlacementContractResult::sw_node_fail},
        {"fb", &PcbPlacementContractResult::fb_fail},
        {"boot", &PcbPlacementContractResult::boot_fail},
        {"vcc", &PcbPlacementContractResult::vcc_fail},
        {"bias", &PcbPlacementContractResult::bias_fail},
        {"rt", &PcbPlacementContractResult::rt_fail},
        {"ldo", &PcbPlacementContractResult::ldo_fail},
        {"proximity", &PcbPlacementContractResult::proximity_fail},
        {"unknown", &PcbPlacementContractResult::unknown_fail}};
    return c;
}
void required_structure_fields(const JsonNode &structure, const std::string &type) {
    // A missing required key must not become an empty ref and a skipped
    // measurement. Unknown types are handled by the fail-loud result branch.
    static const std::map<std::string, std::vector<std::string>> fields{
        {"hot_loop", {"ic", "max_pad_to_pin_mm", "basis", "caps", "pin_pairs"}},
        {"bulk_in", {"ic", "max_pad_to_pin_mm", "caps", "vin_pins"}},
        {"bulk_out", {"ic", "inductor", "max_pad_to_pin_mm", "inductor_out_pin", "caps"}},
        {"sw_node", {"ic", "inductor", "max_pad_to_pin_mm", "sw_pin"}},
        {"fb_cluster",
         {"ic", "own_inductor", "max_to_fb_mm", "min_to_own_sw_mm", "members", "fb_pin",
          "own_sw_pin"}},
        {"boot", {"ic", "cap", "max_pad_to_pin_mm", "pins"}},
        {"vcc_cap", {"ic", "cap", "max_pad_to_pin_mm", "pin"}},
        {"bias_cap", {"ic", "cap", "max_pad_to_pin_mm", "pin"}},
        {"rt_r", {"ic", "resistor", "max_pad_to_pin_mm", "pin"}},
        {"ldo_stage", {"ic", "max_pad_to_pin_mm", "cin", "cin_pin", "cout", "cout_pin"}},
        {"proximity", {"max_mm"}},
        {"same_side", {"ics"}}};
    auto found = fields.find(type);
    if (found != fields.end())
        for (const auto &name : found->second)
            (void)required(structure, name);
}
} // namespace
void validate_pcb_contract_pins(const std::string &sheet, const JsonNode &contract,
                                const std::map<std::string, PcbContractSourcePart> &parts) {
    kind(contract, JsonKind::Object);
    auto demand = [&](std::size_t index, const std::string &type, const std::string &ref,
                      const std::string &field, const JsonNode &value) {
        auto part = parts.find(ref);
        if (part == parts.end() || !part->second.mod)
            return;
        std::set<std::string> available;
        for (const auto &row : part->second.mod->pads)
            if (!std::get<0>(row).empty())
                available.insert(std::get<0>(row));
        std::vector<std::string> pins;
        named_pins(value, pins);
        for (const auto &pin : pins)
            if (!available.count(pin)) {
                std::vector<std::string> sorted(available.begin(), available.end());
                std::sort(sorted.begin(), sorted.end(), [](const auto &a, const auto &b) {
                    return std::make_pair(a.size(), a) < std::make_pair(b.size(), b);
                });
                throw PcbContractPinError("placement contract " + repr(sheet) + " structure #" +
                                          std::to_string(index) + " (" + type + "): " + field +
                                          " names pin " + repr(pin) + " but " + ref +
                                          " (footprint " + repr(part->second.footprint) +
                                          ") has no such pad — pin fields must be FOOTPRINT pad "
                                          "ids, not symbol pin names. Available pads: " +
                                          list_repr(sorted));
            }
    };
    const auto &ss = array(opt(contract, "structures"));
    for (std::size_t k = 0; k < ss.size(); ++k) {
        const auto &s = ss[k];
        auto type = str(s, "type", "None");
        for (const auto &[r, fld] : pin_fields(type))
            if (truth(opt(s, r)) && truth(opt(s, fld)))
                demand(k, type, str(s, r), fld, opt(s, fld));
        if (type == "proximity")
            for (const auto &mf : array(opt(s, "min_from")))
                if (truth(opt(mf, "part")) && truth(opt(mf, "pin")))
                    demand(k, type, str(mf, "part"), "min_from.pin", opt(mf, "pin"));
    }
}
void validate_pcb_contract_pins(const PcbPlacementGatePolicy &p) {
    static const std::map<std::string, PcbContractSourcePart> empty;
    for (const auto &[s, c] : p.contracts) {
        auto i = p.source_parts.find(s);
        validate_pcb_contract_pins(s, c, i == p.source_parts.end() ? empty : i->second);
    }
}
PcbPlacementContractResult
check_pcb_placement_contract(const PcbCheckInput &input, const std::string &sheet,
                             const JsonNode *contract,
                             const std::map<std::string, std::string> &ref_map) {
    PcbPlacementContractResult res;
    res.sheet = sheet;
    if (!contract)
        return res;
    kind(*contract, JsonKind::Object);
    res.have_contract = true;
    std::map<std::string, std::size_t> indices;
    const auto &m = input.model();
    for (std::size_t i = 0; i < m.insts.size(); ++i)
        if (m.insts[i].sheet == sheet)
            indices[m.insts[i].ref] = i;
    auto index = [&](const std::string &lib) -> std::optional<std::size_t> {
        auto ref = ref_map.find(lib);
        if (ref == ref_map.end() || !indices.count(ref->second)) {
            unique_add(res.missing_refs,
                       lib + "->" +
                           (ref == ref_map.end() || ref->second.empty() ? "?" : ref->second));
            return {};
        }
        return indices.at(ref->second);
    };
    auto inst = [&](const std::string &lib) -> const PcbCheckInstance * {
        auto i = index(lib);
        return i ? &m.insts[*i] : nullptr;
    };
    auto boxes = [&](const std::string &lib) -> const Boxes * {
        auto i = index(lib);
        return i ? &input.geometry_at(*i).pad_boxes : nullptr;
    };
    auto pin_gap = [&](const Boxes *a, const Boxes *b, const std::vector<std::string> &pins) {
        return gap(a, b, &pins);
    };
    auto add = [&](Counter counter, const std::string &v) {
        ++(res.*counter);
        res.violations.push_back(v);
    };
    const auto &structures = array(opt(*contract, "structures"));
    for (const auto &s : structures) {
        auto type = str(s, "type", "None"), ic = str(s, "ic"), basis = str(s, "basis");
        required_structure_fields(s, type);
        ++res.checked;
        auto lim = num(s, "max_pad_to_pin_mm");
        if (type == "hot_loop") {
            auto ii = inst(ic);
            auto ib = ii ? boxes(ic) : nullptr;
            struct Cap {
                std::string ref;
                const PcbCheckInstance *inst;
                const Boxes *boxes;
            };
            std::vector<Cap> caps;
            for (const auto &c : strings(opt(s, "caps")))
                caps.push_back({c, inst(c), boxes(c)});
            for (const auto &pair : array(opt(s, "pin_pairs"))) {
                auto pins = strings(pair);
                std::optional<double> best;
                std::string ref;
                for (const auto &c : caps) {
                    if (!ib || !c.boxes || !c.inst)
                        continue;
                    if (truth(opt(s, "same_side")) && ii && c.inst->side != ii->side)
                        continue;
                    auto d = pin_gap(ib, c.boxes, pins);
                    if (d && (!best || *d < *best)) {
                        best = d;
                        ref = c.ref;
                    }
                }
                if (over(best, lim))
                    add(&PcbPlacementContractResult::hot_loop_fail,
                        "hot_loop " + ic + " pins " + join(pins, "/") + " (VIN/PGND): " +
                            (!best ? "none within " + g(lim) + "mm same-side"
                                   : "nearest " + ref + " " + f(*best, 2) + "mm") +
                            " > " + g(lim) + "mm [" + basis + "]");
            }
        } else if (type == "bulk_in") {
            auto ib = boxes(ic);
            auto pins = strings(opt(s, "vin_pins"));
            for (const auto &c : strings(opt(s, "caps"))) {
                auto cb = boxes(c);
                if (!ib || !cb)
                    continue;
                auto d = pin_gap(ib, cb, pins);
                if (over(d, lim))
                    add(&PcbPlacementContractResult::bulk_fail,
                        "bulk_in " + ic + " " + c + ": " + dist(d) + " > " + g(lim) + "mm to VIN " +
                            list_repr(pins) + " [" + basis + "]");
            }
        } else if (type == "bulk_out") {
            auto ii = inst(ic), li = inst(str(s, "inductor"));
            auto lb = li ? boxes(str(s, "inductor")) : nullptr;
            auto pin = str(s, "inductor_out_pin");
            for (const auto &c : strings(opt(s, "caps"))) {
                auto ci = inst(c);
                auto cb = boxes(c);
                if (!lb || !cb || !ci)
                    continue;
                if (truth(opt(s, "same_side")) && ii && ci->side != ii->side) {
                    add(&PcbPlacementContractResult::bulk_out_fail,
                        "bulk_out " + ic + " " + c + ": on " + ci->side + " but IC is " + ii->side +
                            " (same_side) [" + basis + "]");
                    continue;
                }
                auto d = pin_gap(lb, cb, {pin});
                if (over(d, lim))
                    add(&PcbPlacementContractResult::bulk_out_fail,
                        "bulk_out " + ic + " " + c + ": " + dist(d) + " > " + g(lim) + "mm to L=" +
                            str(s, "inductor") + " out pad " + pin + " [" + basis + "]");
            }
        } else if (type == "sw_node") {
            auto ib = boxes(ic), lb = boxes(str(s, "inductor"));
            if (ib && lb) {
                auto d = pin_gap(ib, lb, {str(s, "sw_pin")});
                if (over(d, lim))
                    add(&PcbPlacementContractResult::sw_node_fail,
                        "sw_node " + ic + " L=" + str(s, "inductor") + ": " + dist(d) + " > " +
                            g(lim) + "mm to SW pin " + str(s, "sw_pin") + " [" + basis + "]");
            }
        } else if (type == "fb_cluster") {
            auto ib = boxes(ic), own_l = boxes(str(s, "own_inductor"));
            auto foreign = str(s, "foreign_ic"), foreign_l = str(s, "foreign_inductor"),
                 sw = str(s, "foreign_sw_pin");
            auto fb = foreign.empty() ? nullptr : boxes(foreign),
                 fl = foreign_l.empty() ? nullptr : boxes(foreign_l);
            auto to = num(s, "max_to_fb_mm"), own = num(s, "min_to_own_sw_mm"),
                 away = num(s, "min_to_foreign_sw_mm");
            for (const auto &r : strings(opt(s, "members"))) {
                auto mb = boxes(r);
                if (!mb)
                    continue;
                if (ib) {
                    auto d = pin_gap(ib, mb, {str(s, "fb_pin")});
                    if (over(d, to))
                        add(&PcbPlacementContractResult::fb_fail,
                            "fb_cluster " + ic + " " + r + ": " + dist(d) + " > " + g(to) +
                                "mm to FB pin " + str(s, "fb_pin") + " [" + basis + "]");
                }
                auto d = minimum(pin_gap(ib, mb, {str(s, "own_sw_pin")}), gap(mb, own_l));
                if (under(d, own))
                    add(&PcbPlacementContractResult::fb_fail,
                        "fb_cluster " + ic + " " + r + ": " + f(*d, 2) + "mm < " + g(own) +
                            "mm from own SW/L (too close) [" + basis + "]");
                if (opt(s, "foreign_ic").kind != JsonKind::Null) {
                    auto fd =
                        minimum(sw.empty() ? std::nullopt : pin_gap(fb, mb, {sw}), gap(mb, fl));
                    if (under(fd, away))
                        add(&PcbPlacementContractResult::fb_fail,
                            "fb_cluster " + ic + " " + r + ": " + f(*fd, 2) + "mm < " + g(away) +
                                "mm from foreign " + foreign + " SW/L [" + basis + "]");
                }
            }
        } else if (type == "boot" || type == "vcc_cap" || type == "bias_cap" || type == "rt_r") {
            auto r = str(s, type == "rt_r" ? "resistor" : "cap");
            auto ib = boxes(ic), rb = boxes(r);
            if (!ib || !rb)
                continue;
            auto pins =
                type == "boot" ? strings(opt(s, "pins")) : std::vector<std::string>{str(s, "pin")};
            auto d = pin_gap(ib, rb, pins);
            Counter counter = type == "boot"       ? &PcbPlacementContractResult::boot_fail
                              : type == "vcc_cap"  ? &PcbPlacementContractResult::vcc_fail
                              : type == "bias_cap" ? &PcbPlacementContractResult::bias_fail
                                                   : &PcbPlacementContractResult::rt_fail;
            auto desc = type == "boot" ? "pins " + list_repr(pins)
                                       : (type == "vcc_cap"    ? "VCC pin "
                                          : type == "bias_cap" ? "BIAS pin "
                                                               : "RT pin ") +
                                             str(s, "pin");
            if (over(d, lim))
                add(counter, type + " " + ic + " " + r + ": " + dist(d) + " > " + g(lim) +
                                 "mm to " + desc + " [" + basis + "]");
        } else if (type == "ldo_stage") {
            auto ib = boxes(ic);
            for (const auto &role : std::vector<std::tuple<std::string, std::string, std::string>>{
                     {"Cin", str(s, "cin"), str(s, "cin_pin")},
                     {"Cout", str(s, "cout"), str(s, "cout_pin")}}) {
                const auto &[name, r, pin] = role;
                auto cb = boxes(r);
                if (!ib || !cb)
                    continue;
                auto d = pin_gap(ib, cb, {pin});
                if (over(d, lim))
                    add(&PcbPlacementContractResult::ldo_fail,
                        "ldo_stage " + ic + " " + name + "=" + r + ": " + dist(d) + " > " + g(lim) +
                            "mm to pin " + pin + " [" + basis + "]");
            }
        } else if (type == "proximity") {
            auto anchor = str(s, "anchor");
            auto ai = anchor.empty() ? nullptr : inst(anchor);
            auto ab = anchor.empty() ? nullptr : boxes(anchor);
            auto pins = strings(opt(s, "anchor_pins"));
            auto maximum = num(s, "max_mm");
            for (const auto &r : strings(opt(s, "members"))) {
                auto mb = boxes(r);
                auto mi = inst(r);
                if (!mb || !ab)
                    continue;
                auto d = gap(ab, mb, pins.empty() ? nullptr : &pins);
                auto tgt = pins.empty() ? "any pad" : "pins " + join(pins, "/");
                if (over(d, maximum))
                    add(&PcbPlacementContractResult::proximity_fail,
                        "proximity " + anchor + " " + r + ": " + dist(d) + " > " + g(maximum) +
                            "mm to " + anchor + " " + tgt + " [" + basis + "]");
                if (truth(opt(s, "same_side")) && ai && mi && mi->side != ai->side)
                    add(&PcbPlacementContractResult::proximity_fail,
                        "proximity " + anchor + " " + r + ": on " + mi->side + " but anchor " +
                            anchor + " is " + ai->side + " (same_side) [" + basis + "]");
                for (const auto &mf : array(opt(s, "min_from"))) {
                    auto other = str(mf, "part");
                    auto ob = other.empty() ? nullptr : boxes(other);
                    if (!ob)
                        continue;
                    auto mm = num(mf, "min_mm");
                    auto pin = str(mf, "pin");
                    auto fd = pin.empty() ? gap(ob, mb) : pin_gap(ob, mb, {pin});
                    if (under(fd, mm))
                        add(&PcbPlacementContractResult::proximity_fail,
                            "proximity " + anchor + " " + r + ": " + f(*fd, 2) + "mm < " + g(mm) +
                                "mm from " + other + " " +
                                (pin.empty() ? "any pad" : "pin " + pin) + " (too close) [" +
                                basis + "]");
                }
            }
        } else if (type == "same_side") {
            for (const auto &r : strings(opt(s, "ics"))) {
                auto ii = inst(r);
                if (!ii)
                    continue;
                std::set<std::string> members;
                for (const auto &s2 : structures) {
                    if (str(s2, "type") == "same_side" ||
                        (str(s2, "ic") != r && str(s2, "anchor") != r))
                        continue;
                    for (auto key : {"cap", "inductor", "resistor", "cin", "cout"})
                        if (opt(s2, key).kind != JsonKind::Null)
                            members.insert(str(s2, key));
                    for (auto key : {"caps", "members"})
                        for (const auto &ref : strings(opt(s2, key)))
                            members.insert(ref);
                }
                for (const auto &ref : members) {
                    auto mi = inst(ref);
                    if (mi && mi->side != ii->side)
                        add(&PcbPlacementContractResult::same_side_fail,
                            "same_side " + r + " " + ref + ": on " + mi->side + " but IC is " +
                                ii->side + " [" + basis + "]");
                }
            }
        } else
            add(&PcbPlacementContractResult::unknown_fail,
                "UNKNOWN structure type " +
                    (opt(s, "type").kind == JsonKind::Null ? "None" : repr(type)) +
                    " — gate has no branch to check it (fail-loud) [" + basis + "]");
    }
    // Preserve the original missing-reference policy: listed diagnostics alone
    // do not change ok. Individual structure branches determine violations.
    res.ok = res.violations.empty();
    return res;
}
std::string PcbPlacementContractResult::summary() const {
    if (!sheet_summaries.empty())
        return join(sheet_summaries, "\n\n");
    std::vector<std::string> lines{"PLACEMENT-CONTRACT GATE (" + (sheet.empty() ? "?" : sheet) +
                                   "): " + verdict(ok) +
                                   " (contract=" + (have_contract ? "yes" : "none") + ", " +
                                   std::to_string(checked) + " structures)"};
    std::string count = "  fails:";
    for (const auto &[name, p] : counters())
        count += " " + name + "=" + std::to_string(this->*p);
    lines.push_back(count);
    auto missing = missing_refs;
    std::sort(missing.begin(), missing.end());
    lines.push_back("  unresolved refs: " + std::to_string(missing.size()));
    for (const auto &r : missing)
        lines.push_back("    MISSING " + r);
    auto vs = violations;
    std::sort(vs.begin(), vs.end());
    lines.push_back("  violations: " + std::to_string(vs.size()));
    for (const auto &v : vs)
        lines.push_back("    " + v);
    return join(lines);
}
PcbPlacementContractResult check_pcb_wired_contracts(const PcbCheckInput &in,
                                                     const PcbPlacementGatePolicy &p) {
    if (p.wired_sheets.empty())
        return check_pcb_placement_contract(in, "power", nullptr, {});
    std::vector<PcbPlacementContractResult> results;
    std::vector<std::string> names;
    for (const auto &s : p.wired_sheets) {
        auto c = p.contracts.find(s);
        results.push_back(check_pcb_placement_contract(
            in, s, c == p.contracts.end() ? nullptr : &c->second, refs(p, s)));
        names.push_back(s);
    }
    if (results.size() == 1)
        return results.front();
    PcbPlacementContractResult out;
    out.sheet = join(names, "+");
    for (const auto &r : results) {
        out.ok &= r.ok;
        out.have_contract |= r.have_contract;
        out.checked += r.checked;
        for (const auto &[name, c] : counters()) {
            (void)name;
            out.*c += r.*c;
        }
        out.violations.insert(out.violations.end(), r.violations.begin(), r.violations.end());
        out.missing_refs.insert(out.missing_refs.end(), r.missing_refs.begin(),
                                r.missing_refs.end());
        out.sheet_summaries.push_back(r.summary());
    }
    return out;
}
PcbContractResults check_all_pcb_placement_contracts(const PcbCheckInput &in,
                                                     const PcbPlacementGatePolicy &p) {
    std::set<std::string> placed;
    for (const auto &i : in.model().insts)
        placed.insert(i.sheet);
    PcbContractResults out;
    for (const auto &s : placed) {
        auto c = p.contracts.find(s);
        if (c != p.contracts.end())
            out[s] = check_pcb_placement_contract(in, s, &c->second, refs(p, s));
    }
    return out;
}
PcbContractResults pcb_contract_coverage(const PcbCheckInput &in, const PcbPlacementGatePolicy &p) {
    PcbContractResults out;
    for (const auto &[s, c] : p.contracts)
        out[s] = check_pcb_placement_contract(in, s, &c, refs(p, s));
    return out;
}
PcbContractCoverageReport render_pcb_contract_coverage(const PcbContractResults &cov,
                                                       const std::set<std::string> &wired) {
    PcbContractCoverageReport out;
    std::vector<std::string> lines;
    for (const auto &[s, r] : cov) {
        if (!r.have_contract)
            continue;
        std::string status;
        if (wired.count(s)) {
            ++out.wired;
            status = "WIRED-gated";
        } else if (r.violations.empty()) {
            ++out.met;
            status = "inert-met";
        } else {
            ++out.violated;
            status = "inert-VIOLATED";
        }
        auto worst = r.violations.empty() ? "" : r.violations.front();
        worst = worst.substr(0, worst.find(" ["));
        std::size_t end = 0, count = 0;
        for (; end < worst.size(); ++end)
            if ((static_cast<unsigned char>(worst[end]) & 0xc0) != 0x80 && ++count > 64)
                break;
        worst.resize(end);
        lines.push_back("  " + pad(s, 22) + " " + pad(status, 15) + " " +
                        pad(std::to_string(r.checked), 2, true) + " chk  " +
                        std::to_string(r.violations.size()) + " viol  " + worst);
    }
    out.text = "CONTRACT COVERAGE: " + std::to_string(out.wired) + " wired(gated) / " +
               std::to_string(out.met) + " inert-met / " + std::to_string(out.violated) +
               " inert-VIOLATED  (authored SI/PI intent not yet placer-enforced)\n" + join(lines);
    return out;
}
} // namespace schgen
