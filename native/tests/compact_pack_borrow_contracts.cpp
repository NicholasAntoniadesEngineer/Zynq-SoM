#include "schgen/pack_refine.hpp"
#include "../src/pack_refine_internal.hpp"
#include <iostream>
#include <sstream>
#include <limits>

#include "schgen/occupancy_precision.hpp"
#include <algorithm>
#include <cmath>
#include <unordered_map>
#include <map>

// Independent prechange search from HEAD 4df6db6e, including board overrides.
namespace schgen {
static std::vector<SeatShapeHit> reference_seat_shapes(
    const Occupancy& occupancy, double anchor_x, double anchor_y,
    const std::vector<SeatShapeCand>& cands, double board_w, double board_h,
    double clear, QuantizationCounts* counts, bool keep_all) {
    Occupancy working = occupancy;
    working.set_board(board_w, board_h);
    std::vector<std::string> side_order;
    std::unordered_map<std::string, SeatShapeHit> best;
    std::vector<SeatShapeHit> all;
    for (const auto& cand : cands) {
        if (cand.w > board_w - 2.0 * clear || cand.h > board_h - 2.0 * clear) {
            continue;
        }
        auto pos = working.place_near(anchor_x, anchor_y, cand.w, cand.h,
                                      cand.reach, cand.inset, cand.mask,
                                      cand.comps, cand.win_x0, cand.win_x1,
                                      cand.win_y0, cand.win_y1, counts);
        if (!pos.has_value()) {
            continue;
        }
        const double dist = std::fabs(pos->x + cand.w / 2.0 - anchor_x)
            + std::fabs(pos->y + cand.h / 2.0 - anchor_y);
        const double dist_key = occupancy_shape_key4dp(dist, counts);
        auto found = keep_all ? best.end() : best.find(cand.side);
        if (!keep_all && found != best.end()) {
            if (dist_key > found->second.dist_key) {
                continue;
            }
            if (dist_key == found->second.dist_key
                && cand.index >= found->second.index) {
                continue;
            }
        } else if (!keep_all && found == best.end()) {
            side_order.push_back(cand.side);
        }
        SeatShapeHit hit;
        hit.side = cand.side;
        hit.index = cand.index;
        hit.x = pos->x;
        hit.y = pos->y;
        hit.w = cand.w;
        hit.h = cand.h;
        hit.reach = cand.reach;
        hit.inset = cand.inset;
        hit.comps = cand.comps;
        hit.dist_key = dist_key;
        if (keep_all) all.push_back(std::move(hit));
        else best[cand.side] = std::move(hit);
    }
    if (keep_all) return all;
    std::vector<SeatShapeHit> out;
    out.reserve(side_order.size());
    for (const auto& side : side_order) {
        out.push_back(best[side]);
    }
    return out;
}

std::vector<SeatShapeHit> reference_seat_shape_sides(const Occupancy& occupancy,
    double anchor_x, double anchor_y, const std::vector<SeatShapeCand>& cands,
    double board_w, double board_h, double clear, QuantizationCounts* counts) {
    return reference_seat_shapes(occupancy,anchor_x,anchor_y,cands,board_w,board_h,clear,counts,false);
}
std::vector<SeatShapeHit> reference_seat_shape_candidates(const Occupancy& occupancy,
    double anchor_x, double anchor_y, const std::vector<SeatShapeCand>& cands,
    double board_w, double board_h, double clear, QuantizationCounts* counts) {
    return reference_seat_shapes(occupancy,anchor_x,anchor_y,cands,board_w,board_h,clear,counts,true);
}

}

namespace {
using namespace schgen;
using floorplan_detail::seat_shape_candidates_on_current_board;
void require(bool p,const char* why) { if(!p) throw std::runtime_error(why); }
std::string signature(const std::vector<SeatShapeHit>& hits) {
    std::ostringstream s; s << std::hexfloat;
    for(const auto& h:hits) {
        s << h.side << ':' << h.index << ':' << h.x << ':' << h.y << ':' << h.w << ':' << h.h << ':' << h.dist_key;
        for(const auto& halo:{h.reach,h.inset}) s << ':' << halo.w << ':' << halo.e << ':' << halo.n << ':' << halo.s;
        for(const auto& c:h.comps) {
            s << '/' << c.dx << ':' << c.dy << ':' << c.w << ':' << c.h << ':' << c.mask;
            for(const auto& v:{c.reach,c.inset})s<<':'<<v.w<<':'<<v.e<<':'<<v.n<<':'<<v.s;
        }
        s << '\n';
    }
    return s.str();
}
SeatShapeCand shape(int i) { return {i,3,2,{},{},1,i%2 ? "label-B":"label-A",{},-30,60,-30,60}; }
// Independent oracle: serialized scalar bytes, not the production comparator.
// The grid/reservations are immutable and this table dies within one seat call.
// Cold counters here cannot overflow; seeded overflow prefixes are tested below
// and duplicate near-MAX guards are covered by compact_seat_memo_contracts.
QuantizationCounts unique_query_counts(const Occupancy& occ,
    const std::vector<SeatShapeCand>& cands,double ax,double ay) {
    QuantizationCounts counts;
    std::map<std::string,std::optional<Pose>> seen;
    for(const auto& c:cands) {
        if(c.w>19 || c.h>17) continue; // Same existing 20x18 / .5 filter.
        std::vector<double> values{ax,ay,20,18,.5,c.w,c.h,
            c.reach.w,c.reach.e,c.reach.n,c.reach.s,
            c.inset.w,c.inset.e,c.inset.n,c.inset.s,
            c.win_x0,c.win_x1,c.win_y0,c.win_y1};
        std::vector<int> masks{c.mask};
        bool eligible=c.w>0 && c.h>0 && c.mask>0
            && c.win_x0<=c.win_x1 && c.win_y0<=c.win_y1;
        for(const auto& p:c.comps) {
            values.insert(values.end(),{p.dx,p.dy,p.w,p.h});
            for(const auto& h:{p.reach,p.inset})values.insert(values.end(),{h.w,h.e,h.n,h.s});
            masks.push_back(p.mask);
            eligible=eligible && p.w>0 && p.h>0 && p.mask>0;
        }
        for(double v:values) if(!std::isfinite(v)) eligible=false;
        std::string key;
        if(eligible) {
            const auto append=[&](const auto& v) {
                key.append(reinterpret_cast<const char*>(&v),sizeof(v));
            };
            append(c.comps.size());
            for(double v:values) append(v); // Exact bits, including signed zero.
            for(int mask:masks) append(mask); // Ordered child masks, not a set.
        }
        auto prior=eligible ? seen.find(key):seen.end();
        std::optional<Pose> pos;
        if(prior!=seen.end()) pos=prior->second;
        else {
            pos=occ.place_near(ax,ay,c.w,c.h,c.reach,c.inset,c.mask,c.comps,
                c.win_x0,c.win_x1,c.win_y0,c.win_y1,&counts);
            if(eligible) seen.emplace(std::move(key),pos);
        }
        if(pos) (void)occupancy_shape_key4dp(
            std::fabs(pos->x+c.w/2.0-ax)+std::fabs(pos->y+c.h/2.0-ay),&counts);
    }
    return counts;
}
void equal(const Occupancy& occ,const std::vector<SeatShapeCand>& c,double ax=8,double ay=8) {
    const auto before=occ.rect_count();
    QuantizationCounts baseline,candidate,again;
    const auto expected=reference_seat_shape_candidates(occ,ax,ay,c,20,18,.5,&baseline);
    const auto got=seat_shape_candidates_on_current_board(occ,ax,ay,c,20,18,.5,&candidate);
    require(signature(got)==signature(expected),"complete ordered hits differ from frozen reference");
    require(occ.rect_count()==before,"occupancy mutated");
    require(signature(seat_shape_candidates_on_current_board(occ,ax,ay,c,20,18,.5,&again))==signature(got),"repeat poses changed");
    require(again==candidate,"repeat counts changed");
    require(candidate==unique_query_counts(occ,c,ax,ay),"borrowed receipts must count unique actual queries and every successful shape scalar");
    QuantizationCounts public_counts;
    require(signature(seat_shape_candidates(occ,ax,ay,c,20,18,.5,&public_counts))==signature(expected),
            "public full hits differ from frozen reference");
    require(public_counts==baseline,"public full-candidate receipts changed");
    QuantizationCounts old_sides,new_sides;
    require(signature(reference_seat_shape_sides(occ,ax,ay,c,20,18,.5,&old_sides))==
            signature(seat_shape_sides(occ,ax,ay,c,20,18,.5,&new_sides)),"legacy side output changed");
    require(old_sides==new_sides,"legacy side receipts changed");
}
void board_override() {
    Occupancy occ(20,18,.5,8,0,1,.05);
    auto c=shape(0);
    QuantizationCounts original,public_counts;
    const auto expected=reference_seat_shape_candidates(occ,16,16,{c},10,8,.5,&original);
    const auto resized=seat_shape_candidates(occ,16,16,{c},10,8,.5,&public_counts);
    require(!expected.empty() && signature(resized)==signature(expected),"public resize changed");
    require(original==public_counts,"public resize receipts changed");
    require(signature(seat_shape_candidates_on_current_board(occ,16,16,{c},20,18,.5,nullptr))!=signature(expected),
            "public resize leaked into borrowed occupancy");
    equal(occ,{c});equal(occ,{});
}
void overflow() {
    Occupancy occ(20,18,.5,8,0,1,.05);
    QuantizationCounts expected{{"occupancy_axis_count",std::numeric_limits<std::size_t>::max()-1}};
    auto actual=expected;
    bool old_threw=false,new_threw=false;
    try {(void)reference_seat_shape_candidates(occ,8,8,{shape(0)},20,18,.5,&expected);}
    catch(const std::overflow_error&) {old_threw=true;}
    try {(void)seat_shape_candidates_on_current_board(occ,8,8,{shape(0)},20,18,.5,&actual);}
    catch(const std::overflow_error&) {new_threw=true;}
    require(old_threw && new_threw && expected==actual,"failed-prefix accounting changed");
    equal(occ,{shape(0)});
}
void children() {
    Occupancy occ(20,18,.5,8,0,1,.05);
    // Main top body can overlap the bottom obstacle; child bottom reservations cannot.
    occ.add(6,6,4,4,{},{},2,{});
    auto a=shape(0),b=shape(1),c=shape(2);
    b.comps={{0,0,3,2,2}};
    c.comps={{30,30,1,1,2}};
    auto full=reference_seat_shape_candidates(occ,8,8,{a,b,c},20,18,.5,nullptr);
    require(full.size()==3 && (full[0].x!=full[1].x || full[0].y!=full[1].y),"child fallback witness inactive");
    equal(occ,{a,b,c});
    // A new occupancy state must not inherit a cached pose or miss.
    occ.add(0,0,20,18,{},{},1,{}); equal(occ,{a,b,c});
    occ.remove(0,0,20,18,{},{},1,{}); equal(occ,{a,b,c});
}
void malformed_bypass() {
    Occupancy occ(20,18,.5,8,0,1,.05);
    std::vector<SeatShapeCand> malformed;
    auto c=shape(0); c.w=-1; malformed.push_back(c);
    c=shape(0); c.comps={{0,0,0,1,2}}; malformed.push_back(c);
    c=shape(0); c.win_x0=10; c.win_x1=5; malformed.push_back(c);
    c=shape(0); c.win_x0=std::numeric_limits<double>::quiet_NaN(); malformed.push_back(c);
    c=shape(0); c.win_x1=std::numeric_limits<double>::infinity(); malformed.push_back(c);
    for(const auto& bad:malformed) {
        equal(occ,{bad,bad});
        QuantizationCounts expected,actual;
        (void)reference_seat_shape_candidates(occ,8,8,{bad,bad},20,18,.5,&expected);
        (void)seat_shape_candidates_on_current_board(occ,8,8,{bad,bad},20,18,.5,&actual);
        require(expected==actual,"malformed/nonfinite duplicate must execute both original queries");
    }
}
void halo_relaxation() {
    for(double clearance:{-.25,0.,.5}) for(int mask:{1,2,3}) {
        Occupancy occ(20,18,clearance,12,4,1,.05);
        occ.add(5,5,4,4,{2,1,3,2},{1,2,1,2},mask,{});
        auto a=shape(0),b=shape(1),c=shape(2);
        a.reach={1,2,3,4};b.reach={4,3,2,1};c.reach={2,2,2,2};
        a.inset={1,0,2,3};b.inset={3,2,0,1};c.inset={-1,2,2,0};
        for(double anchor:{2.,8.,15.}) equal(occ,{a,b,c},anchor,7);
        // Crossing the positive-reach branch must prevent unsafe grouping.
        a.reach.w=0.;b.reach.e=-1.;equal(occ,{a,b,c});
    }
}
void matrix() {
    for(int obstacle=0;obstacle<6;++obstacle) {
        Occupancy occ(20,18,.5,8,2,1,.05);
        occ.add(2+obstacle,3,4,5,{},{},obstacle%3+1,{});
        for(int changed=0;changed<19;++changed) {
            auto a=shape(0),b=shape(1),c=shape(2);
            switch(changed) {
                case 0:b.w=4;break; case 1:b.h=4;break;
                case 2:b.reach.w=1;break; case 3:b.reach.e=1;break;
                case 4:b.reach.n=1;break; case 5:b.reach.s=1;break;
                case 6:b.inset.w=-1;break; case 7:b.inset.e=-1;break;
                case 8:b.inset.n=-1;break; case 9:b.inset.s=-1;break;
                case 10:b.mask=2;break; case 11:b.win_x0=10;break;
                case 12:b.win_x1=5;break; case 13:b.win_y0=10;break;
                case 14:b.win_y1=5;break; case 15:b.comps={{-1,1,2,2,3}};break;
                case 16:b.w=40;break; case 17:b.win_x0=70;break;
                case 18:b.reach.w=-0.;break;
            }
            for(double anchor:{2.,8.,15.}) { equal(occ,{a,b,c},anchor,7);equal(occ,{b,c,a},anchor,7); }
        }
    }
}
}
int main() {
    try {
        board_override();overflow();children();malformed_bypass();halo_relaxation();matrix();
        std::cout << "compact borrowed-occupancy search contracts PASS\n";
        return 0;
    } catch(const std::exception& e) { std::cerr << e.what() << '\n';return 1; }
}
