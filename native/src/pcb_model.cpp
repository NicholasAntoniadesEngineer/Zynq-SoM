#include "pcb_emit_internal.hpp"

namespace schgen {
using namespace pcb_emission;
PcbModel pcb_model_from_json(const JsonNode &root, const PcbFootprintPool &pool) {
    kind(root, JsonKind::Object);
    PcbModel m;
    m.board_w = jnum(required(root, "board_w"));
    m.board_h = jnum(required(root, "board_h"));
    if (auto v = object_field(root, "origin_x"))
        m.origin_x = jnum(*v);
    if (auto v = object_field(root, "origin_y"))
        m.origin_y = jnum(*v);
    for (const auto &raw : kind(required(root, "insts"), JsonKind::Array).array_value) {
        PcbFootprintInst i;
        i.ref = jstr(required(raw, "ref"));
        i.value = jstr(required(raw, "value"));
        i.footprint = jstr(required(raw, "footprint"));
        i.sheet = jstr(required(raw, "sheet"));
        i.x = jnum(required(raw, "x"));
        i.y = jnum(required(raw, "y"));
        i.rotation = jnum(required(raw, "rotation"));
        if (auto v = object_field(raw, "side"))
            i.side = jstr(*v);
        if (auto v = object_field(raw, "mirror"))
            i.mirror = jbool(*v);
        if (i.side != "top" && i.side != "bottom")
            throw PcbEmissionError(i.ref + ": invalid footprint side " + i.side);
        auto source = jstr(required(raw, "mod_path"));
        auto fp = pool.find(source);
        if (fp == pool.end() || !fp->second)
            throw PcbEmissionError(i.ref + ": unresolved footprint snapshot " + source);
        i.mod = fp->second;
        for (const auto &[pad, net] :
             kind(required(raw, "pad_nets"), JsonKind::Object).object_value) {
            const auto &a = kind(net, JsonKind::Array).array_value;
            if (a.size() != 2)
                throw PcbEmissionError(i.ref + ": pad net requires number and name");
            i.pad_nets[pad] = {jint(a[0]), jstr(a[1])};
        }
        m.insts.push_back(std::move(i));
    }
    for (const auto &[name, n] : kind(required(root, "net_numbers"), JsonKind::Object).object_value)
        m.net_numbers[name] = jint(n);
    for (const auto &[name, c] : kind(required(root, "netclass_of"), JsonKind::Object).object_value)
        m.netclass_of[name] = jstr(c);
    for (const auto &[name, g] : kind(required(root, "classes"), JsonKind::Object).object_value) {
        if (g.kind == JsonKind::Null)
            m.classes[name] = std::nullopt;
        else
            m.classes[name] =
                DifferentialGeometry{jint(required(g, "impedance")), jnum(required(g, "width_mm")),
                                     jnum(required(g, "gap_mm")), jstr(required(g, "source"))};
    }
    m.placed = jint(required(root, "placed"));
    for (const auto &s : kind(required(root, "deferred"), JsonKind::Array).array_value)
        m.deferred.push_back(jstr(s));
    if (auto n = object_field(root, "n_top"))
        m.n_top = jint(*n);
    if (auto n = object_field(root, "n_bottom"))
        m.n_bottom = jint(*n);
    if (auto n = object_field(root, "two_side"))
        m.two_side = jbool(*n);
    if (auto n = object_field(root, "som_keepout"))
        if (n->kind != JsonKind::Null)
            m.som_keepout = box(*n);
    if (auto n = object_field(root, "som_core"))
        if (n->kind != JsonKind::Null)
            m.som_core = box(*n);
    if (auto rows = object_field(root, "copper"))
        for (const auto &row : kind(*rows, JsonKind::Array).array_value) {
            PcbCheckCopper c;
            c.kind = jstr(required(row, "kind"));
            c.net = jint(required(row, "net"));
            if (c.kind == "via") {
                c.x = jnum(required(row, "x"));
                c.y = jnum(required(row, "y"));
                c.size = jnum(required(row, "size"));
                c.drill = jnum(required(row, "drill"));
                if (auto v = object_field(row, "locked"))
                    m.copper_locks[m.copper.size()] = jbool(*v);
            } else if (c.kind == "segment") {
                c.x1 = jnum(required(row, "x1"));
                c.y1 = jnum(required(row, "y1"));
                c.x2 = jnum(required(row, "x2"));
                c.y2 = jnum(required(row, "y2"));
                c.width = jnum(required(row, "width"));
                c.layer = jstr(required(row, "layer"));
            } else
                throw PcbEmissionError("unknown escape copper kind '" + c.kind + "'");
            for (auto entry : {std::pair{"group", &c.group},
                               {"conn", &c.conn},
                               {"role", &c.role},
                               {"net_name", &c.net_name}})
                if (auto v = object_field(row, entry.first))
                    *entry.second = jstr(*v);
            m.copper.push_back(std::move(c));
        }
    m.escape_meta = jo();
    if (auto n = object_field(root, "escape_meta")) {
        kind(*n, JsonKind::Object);
        m.escape_meta = *n;
        if (auto h = object_field(*n, "som_interface_sha256"))
            m.escape_interface_sha256 = jstr(*h);
        else if (!n->object_value.empty())
            m.escape_interface_sha256 = "";
    }
    if (auto n = object_field(root, "escape_plan"))
        if (n->kind != JsonKind::Null) {
            m.escape_plan = pcb_escape_plan_from_json(*n);
            m.escape_plan_record = *n;
        }
    if (auto n = object_field(root, "stage_moves"))
        for (const auto &[k, v] : kind(*n, JsonKind::Object).object_value)
            m.stage_moves[k] = jint(v);
    return m;
}
JsonNode pcb_model_json(const PcbModel &m) {
    JsonNode insts = ja(), nets = jo(), classes = jo(), netclasses = jo(), deferred = ja(),
             copper = ja(), moves = jo();
    for (const auto &i : m.insts) {
        if (!i.mod)
            throw PcbEmissionError(i.ref + ": unresolved footprint snapshot");
        JsonNode pn = jo();
        for (const auto &[pad, n] : i.pad_nets)
            set(pn, pad, ja({j(n.first), j(n.second)}));
        insts.array_value.push_back(jo({{"ref", j(i.ref)},
                                        {"value", j(i.value)},
                                        {"footprint", j(i.footprint)},
                                        {"x", j(i.x)},
                                        {"y", j(i.y)},
                                        {"rotation", j(i.rotation)},
                                        {"pad_nets", std::move(pn)},
                                        {"mod_path", j(i.mod->source)},
                                        {"sheet", j(i.sheet)},
                                        {"side", j(i.side)},
                                        {"mirror", jb(i.mirror)}}));
    }
    for (const auto &[s, n] : m.net_numbers)
        set(nets, s, j(n));
    for (const auto &[s, n] : m.netclass_of)
        set(netclasses, s, j(n));
    for (const auto &s : m.deferred)
        deferred.array_value.push_back(j(s));
    for (const auto &[s, n] : m.stage_moves)
        set(moves, s, j(n));
    for (const auto &[s, g] : m.classes)
        set(classes, s,
            g ? jo({{"impedance", j(g->impedance)},
                    {"width_mm", j(g->width_mm)},
                    {"gap_mm", j(g->gap_mm)},
                    {"source", j(g->source)}})
              : JsonNode{});
    for (std::size_t index = 0; index < m.copper.size(); ++index) {
        const auto &c = m.copper[index];
        JsonNode n = jo({{"kind", j(c.kind)}});
        if (c.kind == "via") {
            set(n, "x", j(c.x));
            set(n, "y", j(c.y));
            set(n, "size", j(c.size));
            set(n, "drill", j(c.drill));
            auto lock = m.copper_locks.find(index);
            if (lock != m.copper_locks.end())
                set(n, "locked", jb(lock->second));
        } else if (c.kind == "segment") {
            set(n, "x1", j(c.x1));
            set(n, "y1", j(c.y1));
            set(n, "x2", j(c.x2));
            set(n, "y2", j(c.y2));
            set(n, "width", j(c.width));
            set(n, "layer", j(c.layer));
        } else
            throw PcbEmissionError("unknown escape copper kind '" + c.kind + "'");
        set(n, "net", j(c.net));
        for (auto [key, value] : {std::pair{"group", c.group},
                                  {"conn", c.conn},
                                  {"role", c.role},
                                  {"net_name", c.net_name}})
            if (!value.empty())
                set(n, key, j(value));
        copper.array_value.push_back(std::move(n));
    }
    auto meta = m.escape_meta.kind == JsonKind::Null ? jo() : m.escape_meta;
    if (m.escape_interface_sha256 &&
        (!m.escape_interface_sha256->empty() || object_field(meta, "som_interface_sha256") ||
         meta.object_value.empty()))
        set(meta, "som_interface_sha256", j(*m.escape_interface_sha256));
    JsonNode plan;
    if (m.escape_plan) {
        plan = m.escape_plan_record.value_or(jo());
        JsonNode lanes = jo(), counts = jo(), pairs = ja(), genuine = ja();
        const auto *previous_lanes = object_field(plan, "lanes");
        for (const auto &[ref, rows] : m.escape_plan->lanes) {
            JsonNode a = ja();
            const auto *previous = previous_lanes ? object_field(*previous_lanes, ref) : nullptr;
            for (std::size_t index = 0; index < rows.size(); ++index) {
                const auto &l = rows[index];
                JsonNode row = jo();
                if (previous && previous->kind == JsonKind::Array &&
                    index < previous->array_value.size())
                    row = previous->array_value[index];
                set(row, "row", j(l.row));
                set(row, "lane", j(l.lane));
                set(row, "dir", j(l.direction));
                set(row, "net", j(l.net));
                const auto *port = object_field(row, "port");
                if (l.direction == "outward" || l.port_x != 0 || l.port_y != 0 ||
                    (port && port->kind != JsonKind::Null))
                    set(row, "port", ja({j(l.port_x), j(l.port_y)}));
                if (l.direction == "outward" || l.width != 0 || object_field(row, "width"))
                    set(row, "width", j(l.width));
                if (l.bus_group || object_field(row, "bus_group"))
                    set(row, "bus_group", l.bus_group ? j(*l.bus_group) : JsonNode{});
                a.array_value.push_back(std::move(row));
            }
            set(lanes, ref, std::move(a));
        }
        for (const auto &[ref, n] : m.escape_plan->netted_counts)
            set(counts, ref, j(n));
        const auto *old_pairs = object_field(plan, "pairs");
        for (std::size_t index = 0; index < m.escape_plan->pairs.size(); ++index) {
            const auto &pair = m.escape_plan->pairs[index];
            JsonNode row = jo();
            if (old_pairs && old_pairs->kind == JsonKind::Array &&
                index < old_pairs->array_value.size())
                row = old_pairs->array_value[index];
            set(row, "base", j(pair.base));
            set(row, "conn", j(pair.conn));
            set(row, "si_class", j(pair.si_class));
            set(row, "same_row", jb(pair.same_row));
            set(row, "delta_lane", j(pair.delta_lane));
            pairs.array_value.push_back(std::move(row));
        }
        for (const auto &s : m.escape_plan->genuine_pairs)
            genuine.array_value.push_back(j(s));
        if (object_field(plan, "lanes") || !lanes.object_value.empty())
            set(plan, "lanes", std::move(lanes));
        if (object_field(plan, "netted_counts") || !counts.object_value.empty())
            set(plan, "netted_counts", std::move(counts));
        if (object_field(plan, "pairs") || !pairs.array_value.empty())
            set(plan, "pairs", std::move(pairs));
        if (object_field(plan, "genuine_pairs") || !genuine.array_value.empty())
            set(plan, "genuine_pairs", std::move(genuine));
        if (object_field(plan, "content_key") || !m.escape_plan->content_key.empty())
            set(plan, "content_key", j(m.escape_plan->content_key));
    }
    return jo({{"board_w", j(m.board_w)},
               {"board_h", j(m.board_h)},
               {"origin_x", j(m.origin_x)},
               {"origin_y", j(m.origin_y)},
               {"insts", std::move(insts)},
               {"net_numbers", std::move(nets)},
               {"netclass_of", std::move(netclasses)},
               {"classes", std::move(classes)},
               {"placed", j(m.placed)},
               {"deferred", std::move(deferred)},
               {"som_keepout", m.som_keepout ? box_json(*m.som_keepout) : JsonNode{}},
               {"n_top", j(m.n_top)},
               {"n_bottom", j(m.n_bottom)},
               {"two_side", jb(m.two_side)},
               {"som_core", m.som_core ? box_json(*m.som_core) : JsonNode{}},
               {"copper", std::move(copper)},
               {"escape_meta", std::move(meta)},
               {"escape_plan", std::move(plan)},
               {"stage_moves", std::move(moves)}});
}
} // namespace schgen
