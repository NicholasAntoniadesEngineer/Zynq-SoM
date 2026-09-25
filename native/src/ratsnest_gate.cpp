#include "schgen/ratsnest_gate.hpp"
#include "pcb_checks_internal.hpp"
#include "schgen/turn.hpp"

namespace schgen {
using namespace pcb_checks;
RatsnestNets ratsnest_net_pad_positions(const PcbCheckModel& model) {
    RatsnestNets out;
    for (const auto& inst : model.insts) {
        if (!inst.mod) throw std::runtime_error(inst.ref + ": footprint geometry unresolved");
        for (const auto& [name,type,x,y,rotation,w,h] : inst.mod->pads) {
            (void)type; (void)rotation; (void)w; (void)h;
            auto net = inst.pad_nets.find(name);
            if (net == inst.pad_nets.end() || net->second.second.empty() || starts(net->second.second,"unconnected-")) continue;
            auto p = turn_point(x, y, inst.rotation);
            out[net->second.second].emplace_back(py_round(inst.x+p.first,3), py_round(inst.y+p.second,3),inst.ref,inst.sheet);
        }
    }
    return out;
}
RatsnestGateResult check_ratsnest(const PcbCheckInput& input, const RatsnestNets* supplied_nets,
        const RatsnestEdges* supplied_edges, double cross_k) {
    const auto& m=input.model(); RatsnestGateResult res;
    if(!std::isfinite(m.board_w)||!std::isfinite(m.board_h)||m.board_w<=0||m.board_h<=0||
       !std::isfinite(m.origin_x)||!std::isfinite(m.origin_y)||!std::isfinite(cross_k)||cross_k<0)
        throw std::invalid_argument("ratsnest: finite positive board dimensions and nonnegative cross budget required");
    res.board_w=m.board_w; res.board_h=m.board_h;
    const double x0=m.origin_x,y0=m.origin_y,x1=x0+m.board_w,y1=y0+m.board_h;
    std::map<std::string,std::vector<Box4>> by_sheet;
    for (std::size_t i=0;i<m.insts.size();++i) {
        const auto& inst=m.insts[i]; const auto p=input.pad_bbox_at(i),c=input.courtyard_at(i);
        if(p.x0<x0-1e-6||p.y0<y0-1e-6||p.x1>x1+1e-6||p.y1>y1+1e-6)
            res.off_board.push_back(inst.ref+" ("+inst.sheet+"): copper ("+f(p.x0,1)+","+f(p.y0,1)+")..("+
                f(p.x1,1)+","+f(p.y1,1)+") outside Edge.Cuts ("+f(x0,0)+","+f(y0,0)+")..("+f(x1,0)+","+f(y1,0)+")");
        const auto file=std::filesystem::path(inst.mod->source).filename().string();
        if(starts(file,"MountingHole")||starts(file,"Fiducial"))continue;
        by_sheet[inst.sheet].push_back(c);
    }
    for(const auto& [name,boxes]:by_sheet) {
        if(starts(name,"som_j"))continue;
        ++res.n_subsystems;auto hull=boxes.front();double total=0;
        for(auto b:boxes){hull=united(hull,b);total+=(b.x1-b.x0)*(b.y1-b.y0);}
        const double area=(hull.x1-hull.x0)*(hull.y1-hull.y0),disp=area/(total?total:1);
        res.clusters.emplace_back(name,static_cast<int>(boxes.size()),py_round(area,1),py_round(disp,2));
        if(boxes.size()>ratsnest_small_n&&disp>ratsnest_dispersion_max)
            res.dispersed.push_back(name+": dispersion "+f(disp,1)+"x > "+g(ratsnest_dispersion_max)+"x (bbox "+
                f(hull.x1-hull.x0,0)+"x"+f(hull.y1-hull.y0,0)+" mm for "+std::to_string(boxes.size())+" parts)");
    }
    std::stable_sort(res.clusters.begin(),res.clusters.end(),[](const auto& a,const auto& b){return std::get<3>(a)>std::get<3>(b);});
    auto nets=supplied_nets?RatsnestNets{}:ratsnest_net_pad_positions(m);const auto& np=supplied_nets?*supplied_nets:nets;
    auto edges=supplied_edges?RatsnestEdges{}:ratsnest_mst(np);
    std::tie(res.cross_mm,res.total_mm,res.n_cross)=ratsnest_lengths(np,supplied_edges?*supplied_edges:edges);
    res.cross_budget_mm=py_round(cross_k*std::sqrt(m.board_w*m.board_h)*res.n_subsystems,1);
    res.ok=res.off_board.empty()&&res.dispersed.empty()&&res.cross_ok();return res;
}
std::map<std::string,double> ratsnest_dispersion_by_sheet(const RatsnestGateResult& r){
    std::map<std::string,double> out;for(const auto& [name,n,a,d]:r.clusters){(void)n;(void)a;out[name]=d;}return out;
}
std::string RatsnestGateResult::summary() const {
    std::vector<std::string> lines={"LAW-5 RATSNEST GATE: "+verdict(ok)+" (board "+g(board_w)+" x "+g(board_h)+" mm)",
        "  off-board parts: "+std::to_string(off_board.size())};
    for(const auto& r:off_board)lines.push_back("    OFF-BOARD "+r);
    lines.push_back("  dispersed subsystems: "+std::to_string(dispersed.size())+" (threshold "+g(ratsnest_dispersion_max)+"x)");
    for(const auto& d:dispersed)lines.push_back("    DISPERSED "+d);
    lines.push_back("  cross-subsystem airwire: "+g(cross_mm)+" mm (budget "+f(cross_budget_mm,0)+" mm, "+
        (cross_ok()?"OK":"OVER")+"; "+std::to_string(n_cross)+" edges; "+g(cross_mm)+"/"+g(total_mm)+" mm = "+f(100*cross_ratio(),1)+"% of total)");
    lines.push_back("  per-subsystem clusters (n, bbox mm, dispersion):");
    for(const auto& [name,n,a,d]:clusters)lines.push_back("    "+pad(name,22)+" n="+pad(std::to_string(n),3)+" bbox_area="+pad(f(a,0),8,true)+" disp="+pad(f(d,1),5,true));
    return join(lines);
}
} // namespace schgen
