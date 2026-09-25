#include "floorplan_internal.hpp"

namespace schgen {
using namespace floorplan_detail;
namespace {
JsonNode strings(const std::vector<std::string>& values) {
    std::vector<JsonNode> out;
    for (const auto& value:values) out.push_back(jvalue(value));
    return jarray(std::move(out));
}
JsonNode block_json(const FloorplanBlock& b) {
    std::vector<JsonNode> conns,notes;
    for (const auto& c:b.conns) conns.push_back(jarray({jvalue(c.ref),jvalue(c.value),jvalue(c.w),jvalue(c.h)}));
    for (int n:b.notes) notes.push_back(jvalue(n));
    auto affinity=jobject({});
    for (const auto& [j,n]:b.j_aff) affinity.object_value.emplace_back(j,jvalue(n));
    JsonNode pull;
    if (b.pull) {
        const auto& p=*b.pull;
        pull=jobject({{"to",jvalue(p.to)},{"weight",jvalue(p.weight)},{"basis",jvalue(p.basis)}});
        if (p.face_present) pull.object_value.emplace_back("face",jvalue(p.face));
        if (p.exclusive_present) pull.object_value.emplace_back("exclusive",jvalue(p.exclusive));
    }
    return jobject({{"name",jvalue(b.name)},{"kind",jvalue(b.kind)},{"x",jvalue(b.x)},{"y",jvalue(b.y)},
        {"w",jvalue(b.w)},{"h",jvalue(b.h)},{"edge",jvalue(b.edge)},{"conns",jarray(std::move(conns))},
        {"reserved",strings(b.reserved)},{"n_parts",jvalue(b.n_parts)},{"area",jvalue(b.area)},
        {"j_aff",std::move(affinity)},{"zone",jvalue(b.zone)},{"notes",jarray(std::move(notes))},
        {"order_hint",b.order_hint ? jvalue(*b.order_hint):JsonNode{}},{"pinned",jvalue(b.pinned)},{"pull",std::move(pull)},
        {"shape_idx",jvalue(b.shape_idx)},{"side",jvalue(b.side)},{"layer_pref",jvalue(b.layer_pref)},
        {"fanout_reach",halo_json(b.fanout_reach)},{"fanout_inset",halo_json(b.fanout_inset)}});
}
}  // namespace
JsonNode floorplan_plan_json(const FloorplanPlan& p) {
    std::vector<JsonNode> js,edges,interior,decisions;
    for (const auto& j:p.som.js) js.push_back(jobject({{"ref",jvalue(j.ref)},{"pcb_x",jvalue(j.pcb_x)},
        {"pcb_y",jvalue(j.pcb_y)},{"rot",jvalue(j.rot)},{"x",jvalue(j.x)},{"y",jvalue(j.y)},{"w",jvalue(j.w)},{"h",jvalue(j.h)}}));
    for (const auto& b:p.edge_blocks) edges.push_back(block_json(b));
    for (const auto& b:p.interior_blocks) interior.push_back(block_json(b));
    for (const auto& d:p.accounting.decisions) decisions.push_back(jobject({{"step",jvalue(d.step)},{"kind",jvalue(d.kind)},
        {"name",jvalue(d.name)},{"value",d.value},{"inputs",jobject(d.inputs)},{"depth",jvalue(d.depth)},{"text",jvalue(d.text)}}));
    auto engagements=jobject({});
    for (const auto& [name,count]:p.accounting.quantization_engagements) engagements.object_value.emplace_back(name,jvalue(static_cast<double>(count)));
    return jobject({{"som",jobject({{"w",jvalue(p.som.w)},{"h",jvalue(p.som.h)},{"js",jarray(std::move(js))},{"source",jvalue(p.som_source)}})},
        {"som_x",jvalue(p.som_x)},{"som_y",jvalue(p.som_y)},{"edge_blocks",jarray(std::move(edges))},
        {"interior_blocks",jarray(std::move(interior))},{"factor",jvalue(p.factor)},{"spilled",strings(p.spilled)},
        {"composition",strings(p.composition)},{"dec_bank",jarray({jvalue(p.dec_count),jvalue(p.dec_radius)})},{"punch_free",jvalue(p.punch_free)},
        {"board_w",jvalue(p.board_w)},{"board_h",jvalue(p.board_h)},{"outline_note",jvalue(p.outline_note)},
        {"accounting",jobject({{"decisions",jarray(std::move(decisions))},{"fallback_events",strings(p.accounting.fallback_events)},
            {"quantization_engagements",std::move(engagements)}})}});
}
}  // namespace schgen
