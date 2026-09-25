#include "floorplan_internal.hpp"

#include <algorithm>
#include <cmath>
#include <filesystem>

namespace schgen::floorplan_detail {
namespace {
double rotation(double value) {
    const double r = std::fmod(value, 360.0);
    return r < 0 ? r + 360 : r;
}
template<class Map> const typename Map::mapped_type& get(const Map& map, const typename Map::key_type& key) {
    const auto it = map.find(key);
    static const typename Map::mapped_type empty{};
    return it == map.end() ? empty : it->second;
}
bool tagged(const SexprList& node, const std::string& tag) {
    return !node.empty() && std::holds_alternative<Sexpr::Sym>(node.front().v) &&
        std::get<Sexpr::Sym>(node.front().v).name == tag;
}
}  // namespace

Engine::Engine(const FloorplanInput& input) : in(input) {
    plan.som = in.som;
    plan.som_source = in.som_source;
    plan.accounting = in.accounting;
    offset = in.module_offset.value_or(FloorplanPoint{in.project.module_offset[0], in.project.module_offset[1]});
    if (!std::isfinite(in.som.w) || !std::isfinite(in.som.h) || in.som.w <= 0 || in.som.h <= 0)
        throw FloorplanError("floorplan: SoM dimensions must be finite and > 0");
    for (double v : {offset.first, offset.second, in.origin.first, in.origin.second, in.cross_budget_k, in.place_clear})
        if (!std::isfinite(v)) throw FloorplanError("floorplan: non-finite configuration value");
    if (in.cross_budget_k <= 0 || in.place_clear < 0) throw FloorplanError("floorplan: invalid cross budget/placement clearance");
    if (in.spec && in.spec->outline) {
        const auto [w,h]=*in.spec->outline;
        if (!std::isfinite(w) || !std::isfinite(h) || w<=0 || h<=0)
            throw FloorplanSpecError("floorplan: fixed outline dimensions must be finite and > 0");
    }
    auto finite_point=[](FloorplanPoint p,const std::string& where) {
        if (!std::isfinite(p.first) || !std::isfinite(p.second))
            throw FloorplanError("floorplan: non-finite geometry at "+where);
    };
    auto finite_offsets=[&](const FloorplanOffsets& rows,const std::string& where) {
        for (const auto& [ref,p]:rows) finite_point(p,where+"/"+ref);
    };
    auto finite_rotations=[](const FloorplanRotations& rows) {
        for (const auto& [ref,r]:rows) if (!std::isfinite(r))
            throw FloorplanError("floorplan: non-finite rotation for "+ref);
    };
    for (const auto& j:in.som.js) {
        for(double v:{j.pcb_x,j.pcb_y,j.rot,j.x,j.y,j.w,j.h})
            if(!std::isfinite(v))throw FloorplanError("floorplan: non-finite SoM connector "+j.ref);
        if(j.w<0 || j.h<0)throw FloorplanError("floorplan: negative SoM connector size "+j.ref);
    }
    for (const auto* rows:{&in.geometry.top_off,&in.geometry.bot_off})
        for(const auto& [name,offsets]:*rows)finite_offsets(offsets,name);
    finite_rotations(in.geometry.conn_rot);finite_rotations(in.geometry.zone_extra_rot);
    for(const auto& [ref,b]:in.geometry.bbox_of) {
        finite_point({b.x0,b.y0},ref);finite_point({b.x1,b.y1},ref);
        if(b.x0>b.x1 || b.y0>b.y1)throw FloorplanError("floorplan: inverted courtyard for "+ref);
    }
    for (const auto& sheet : in.sheets)
        if (!sheets.emplace(sheet.name, &sheet).second) throw FloorplanError("floorplan: duplicate subsystem " + repr(sheet.name));
    for (const auto& [key, fp] : in.footprints) {
        CachedFootprint cached;
        cached.bbox = footprint_bbox(fp.document, 3);
        cached.pads = scan_pad_nodes(fp.document);
        if (!std::holds_alternative<SexprList>(fp.document.v))
            throw FloorplanError("floorplan: footprint " + repr(key) + " is not a document");
        // Match the legacy pad-name count (including duplicate numbered pads),
        // independently from geometric pads, which require an (at ...) node.
        for (const auto& node : std::get<SexprList>(fp.document.v)) {
            if (!std::holds_alternative<SexprList>(node.v)) continue;
            const auto& row = std::get<SexprList>(node.v);
            if (!tagged(row, "pad")) continue;
            if (row.size() > 1 && std::holds_alternative<std::string>(row[1].v) &&
                !std::get<std::string>(row[1].v).empty()) ++cached.pins;
            if (row.size() > 2 && std::holds_alternative<Sexpr::Sym>(row[2].v)) {
                const auto& type = std::get<Sexpr::Sym>(row[2].v).name;
                cached.has_thru |= type == "thru_hole" || type == "np_thru_hole";
            }
        }
        footprint_cache.emplace(key, std::move(cached));
    }
    for (const auto& [ref, key] : in.geometry.resolvable) {
        (void)ref; (void)footprint(key);
    }
    for (const auto& [name, shapes] : in.geometry.shapes) {
        for (const auto& shape : shapes) {
            if (!std::isfinite(shape.w) || !std::isfinite(shape.h) || shape.w < 0 || shape.h < 0)
                throw FloorplanError("floorplan: invalid shape dimensions for " + repr(name));
            if (shape.side != "top" && shape.side != "bottom") throw FloorplanError("floorplan: invalid shape side for " + repr(name));
            finite_offsets(shape.top_off,name);finite_offsets(shape.bot_off,name);finite_rotations(shape.extra_rot);
            for (const auto& [ref, key] : shape.mirror) { (void)ref; (void)footprint(key); }
        }
    }
}
std::vector<FloorplanBlock*> Engine::blocks() {
    std::vector<FloorplanBlock*> out;
    for (auto& b : plan.edge_blocks) out.push_back(&b);
    for (auto& b : plan.interior_blocks) out.push_back(&b);
    return out;
}
const CachedFootprint& Engine::footprint(const std::string& key) const {
    auto it = footprint_cache.find(key);
    if (it == footprint_cache.end()) throw FloorplanError("floorplan: missing resolved footprint " + repr(key));
    return it->second;
}
std::optional<std::string> Engine::resolved(const CircuitPartIr& part) const {
    const auto it = in.footprint_of.find(part.footprint);
    if (it == in.footprint_of.end()) return std::nullopt;
    (void)footprint(it->second);
    return it->second;
}
FloorplanPoint Engine::part_dims(const std::string& fp) const {
    const auto colon = fp.find(':');
    const auto lib = fp.substr(0, colon);
    const auto dim = in.courtyard_dims.find(lib);
    if (!lib.empty() && dim != in.courtyard_dims.end()) return dim->second;
    static const std::vector<std::tuple<std::string, double, double>> fixed = {
        {"MountingHole_3.2mm_M3_Pad",6.4,6.4}, {"TestPoint_Pad_D1.5mm",1.5,1.5},
        {"TSOT-23-6",2.9,2.8}, {"SOT-23-5",2.9,2.8}, {"SOT-23",2.9,2.4},
        {"D_SMA",4.3,2.6}, {"D_SMB",5.4,3.6}};
    return part_dims_from_name(colon == std::string::npos ? "" : fp.substr(colon + 1), fixed, 1.6, .8);
}
double Engine::sheet_area(const CircuitSheetIr& sheet, double factor) const {
    double total = 0;
    for (const auto& part : sheet.parts) {
        const auto wh = part_dims(part.footprint);
        const double a = wh.first * wh.second;
        total += a >= 40 ? a : a * factor;
    }
    return total;
}
std::vector<const CircuitPartIr*> Engine::zone_parts(const CircuitSheetIr& sheet) const {
    std::vector<const CircuitPartIr*> out;
    if (sheet.name == "som_decoupling") return out;
    for (const auto& part : sheet.parts)
        if (!(starts(sheet.name, "som_j") && starts(part.ref, "J"))) out.push_back(&part);
    return out;
}
std::vector<Box4> Engine::pad_boxes(const std::string& key, double rot, bool thru_only) const {
    std::vector<std::tuple<std::string, double, double, double, double, double>> rows;
    for (const auto& [name, type, x, y, angle, w, h] : footprint(key).pads) {
        (void)name;
        if (!thru_only || type == "thru_hole" || type == "np_thru_hole") rows.emplace_back(type, x, y, angle, w, h);
    }
    std::vector<Box4> boxes;
    for (const auto& [type, x0, y0, x1, y1] : pad_boxes_local(rows, rot)) {
        (void)type; boxes.push_back({x0,y0,x1,y1});
    }
    return boxes;
}

std::pair<Halo, Halo> Engine::fanout(const FloorplanZoneShape& shape, bool base) const {
    auto rotations = in.geometry.conn_rot;
    // Legacy base-zone path overwrites extra rotations; variants add them.
    // This asymmetry is intentional for byte-exact migration.
    for (const auto& [ref, extra] : shape.extra_rot)
        rotations[ref] = base ? extra : rotation(rotations[ref] + extra);
    std::vector<std::tuple<double,double,double,double,double,double,double,int>> rows;
    for (const auto* offsets : {&shape.top_off, &shape.bot_off}) {
        for (const auto& [ref, offset_xy] : *offsets) {
            auto key = get(in.geometry.resolvable, ref);
            std::optional<Box4> box;
            if (in.geometry.bbox_of.count(ref)) box = in.geometry.bbox_of.at(ref);
            if (shape.mirror.count(ref)) { key = shape.mirror.at(ref); box = footprint(key).bbox; }
            if (key.empty() || !box) continue;
            if (std::filesystem::path(in.footprints.at(key).source).stem().string().find("Fiducial") != std::string::npos || is_testpoint_ref(ref)) continue;
            rows.emplace_back(offset_xy.first, offset_xy.second, box->x0, box->y0, box->x1, box->y1,
                              get(rotations, ref), footprint(key).pins);
        }
    }
    return zone_fanout_reach(shape.w, shape.h,
        zone_fanout_members_rows(rows, min_subject_pins, {{2,.20},{8,1.50}},2.0), min_subject_pins);
}
std::vector<Comp> Engine::zone_components(const FloorplanZoneShape& shape, bool pad_punch) const {
    auto rotations = in.geometry.conn_rot;
    for (const auto& [r, extra] : shape.extra_rot) rotations[r] = rotation(rotations[r] + extra);
    auto courtyard = [&](const std::string& r, FloorplanPoint xy) -> std::optional<Box4> {
        std::optional<Box4> box;
        if (shape.mirror.count(r)) box = footprint(shape.mirror.at(r)).bbox;
        else if (in.geometry.bbox_of.count(r)) box = in.geometry.bbox_of.at(r);
        if (box) return offset_turned_box(*box, get(rotations, r), xy.first, xy.second);
        return std::nullopt;
    };
    std::vector<Box4> minor, punches;
    for (const auto& [r, xy] : shape.bot_off) if (auto box = courtyard(r, xy)) minor.push_back(*box);
    for (const auto* offsets : {&shape.top_off, &shape.bot_off}) {
        for (const auto& [r, xy] : *offsets) {
            auto key = get(shape.mirror, r);
            if (key.empty()) key = get(in.geometry.resolvable, r);
            if (key.empty() || !footprint(key).has_thru) continue;
            if (!pad_punch) {
                if (auto box = courtyard(r, xy)) punches.push_back(*box);
            } else {
                const auto boxes = pad_boxes(key, get(rotations, r), true);
                if (boxes.empty()) throw FloorplanError("floorplan: " + r + " (" + key + ") declares through-hole pads but the pad kernel found none — the punch set would silently lose the geometry that pierces both copper faces");
                const auto shifted = offset_boxes(boxes, xy.first, xy.second);
                punches.insert(punches.end(), shifted.begin(), shifted.end());
            }
        }
    }
    return zone_components_assemble(minor, punches, shape.side == "bottom" ? occ_top : occ_bottom, occ_punch);
}

void Engine::prepare_geometry() {
    const auto& zg = in.geometry;
    zbox = zg.zone_box;
    for (const auto& [name, wh] : zbox)
        if (!std::isfinite(wh.first) || !std::isfinite(wh.second) || wh.first < 0 || wh.second < 0)
            throw FloorplanError("floorplan: invalid zone dimensions for " + repr(name));
    for (auto* b : blocks()) {
        if (!zbox.count(b->name)) {
            const double root = std::sqrt(sheet_area(*sheets.at(b->name), 3.5));
            zbox[b->name] = {quantize("placeholder_zone_half_mm", std::max(12.0,root)),
                             quantize("placeholder_zone_half_mm", std::max(8.0,root))};
        }
        FloorplanZoneShape base;
        base.w = zbox.at(b->name).first; base.h = zbox.at(b->name).second;
        base.top_off = get(zg.top_off, b->name); base.bot_off = get(zg.bot_off, b->name);
        base.extra_rot = zg.zone_extra_rot;
        if (zg.zone_box.count(b->name)) std::tie(b->fanout_reach,b->fanout_inset) = fanout(base, true);
        for (int policy : {1,0}) {
            auto& co = components[policy];
            if (zg.zone_box.count(b->name)) co[{b->name,0}] = zone_components(base, policy != 0);
            const auto variants = zg.shapes.find(b->name);
            if (variants == zg.shapes.end()) continue;
            for (std::size_t k=1; k<variants->second.size(); ++k)
                co[{b->name,static_cast<int>(k)}] = zone_components(variants->second[k], policy != 0);
            if (b->kind == "edge" || variants->second.size() < 2) continue;
            auto& sets = shape_sets[policy][b->name];
            sets.push_back({base.w,base.h,b->fanout_reach,b->fanout_inset,"top",get(co,{b->name,0})});
            for (std::size_t k=1; k<variants->second.size(); ++k) {
                const auto& s = variants->second[k];
                const auto ri = fanout(s, false);
                sets.push_back({s.w,s.h,ri.first,ri.second,s.side,get(co,{b->name,static_cast<int>(k)})});
            }
        }
    }
    auto bound = [&](Halo r, Halo i) { max_reach = std::max({max_reach,r.w,r.e,r.n,r.s,-i.w,-i.e,-i.n,-i.s}); };
    for (const auto* b : blocks()) bound(b->fanout_reach,b->fanout_inset);
    for (const auto& [name, variants] : shape_sets[1]) {
        (void)name; for (const auto& s : variants) bound(s.reach,s.inset);
    }
    const auto dec = sheets.find("som_decoupling");
    if (dec != sheets.end()) {
        for (const auto& p : dec->second->parts) if (const auto key = resolved(p)) {
            const auto box = footprint(*key).bbox;
            ++plan.dec_count;
            plan.dec_radius = std::max({plan.dec_radius,std::hypot(box.x0,box.y0),std::hypot(box.x1,box.y0),
                                        std::hypot(box.x0,box.y1),std::hypot(box.x1,box.y1)});
        }
    }
    for (const auto* terms : {&in.compose.index.hard,&in.compose.index.soft})
        for (const auto& t : *terms) if (t.kind == "far_min") far_ceil = std::max(far_ceil,t.bound.value_or(0));
}
void Engine::board_size(double w, double h) {
    if(!std::isfinite(w)||!std::isfinite(h)||w<=0||h<=0)
        throw FloorplanError("floorplan: computed board dimensions must be finite and > 0");
    plan.board_w = w; plan.board_h = h;
    plan.som_x = quantize("som_pose_half_mm", (w-plan.som.w)/2+offset.first);
    plan.som_y = quantize("som_pose_half_mm", (h-plan.som.h)/2+offset.second);
}
std::vector<Box4> Engine::som_keepouts() const {
    std::vector<std::tuple<double,double,double,double>> jacks;
    for (const auto& j : plan.som.js) jacks.emplace_back(j.x,j.y,j.w,j.h);
    return som_keepout_rects(plan.som_x,plan.som_y,plan.som.w,plan.som.h,som_pad,jacks,som_seat_band);
}
void Engine::fallback(const std::string& name) {
    static const std::set<std::string> allowed{"legalize_only_compaction","punch_free_plan_rejected","interior_reseat_retry"};
    if (!allowed.count(name)) throw std::logic_error("floorplan: unregistered fallback " + repr(name));
    plan.accounting.fallback_events.push_back(name);
}
double Engine::quantize(const std::string& name, double value) {
    ++plan.accounting.quantization_engagements[name];
    if (name == "som_pose_half_mm") return som_pose_half_mm(value);
    if (name == "placeholder_zone_half_mm") return placeholder_zone_half_mm(value);
    if (name == "fixed_part_grid") return fixed_part_grid(value);
    if (name == "outline_snap_up") return outline_snap_up(value);
    throw std::logic_error("floorplan: unregistered quantization " + repr(name));
}
}  // namespace schgen::floorplan_detail
