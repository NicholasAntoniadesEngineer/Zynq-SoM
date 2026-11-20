#include "schgen/stackup.hpp"
#include "floorplan_internal.hpp"

#include <algorithm>

namespace schgen {
using namespace floorplan_detail;
namespace {
std::string join(const std::vector<std::string>& xs,const std::string& separator) {
    std::string out;for(const auto& s:xs){if(!out.empty())out+=separator;out+=s;}return out;
}
std::string mm_range(const std::string& label,const std::vector<double>& values) {
    const auto bounds=std::minmax_element(values.begin(),values.end());
    if(bounds.first==values.end())throw FloorplanError("floorplan: empty SI match budget");
    return label+" <= "+number(*bounds.first)+(*bounds.first==*bounds.second ? "":".."+number(*bounds.second))+" mm";
}
}  // namespace

std::string render_floorplan_md(const FloorplanPlan& plan,const FloorplanInput& input) {
    std::string out;auto line=[&](const std::string& s=""){out+=s+"\n";};
    line("# Floorplan");
    line();line("![floorplan](FLOORPLAN.svg)");line();line("## Sources (everything derived, nothing invented)");line();
    line("- SoM outline + connector positions: `"+plan.som_source+"` (Edge.Cuts bbox + connector footprints, parsed live)");
    line("- block sizes: per-part courtyards (`parts/<MPN>/<MPN>.kicad_mod` F.CrtYd; KiCad-standard footprints from the dims in their names), big parts raw + small parts x"+number(plan.factor)+" routing factor");
    line("- edge pinning + zones: connector parts in each sheet netlist + linker module-connector bindings (incl. `expect=` deferrals)");
    line("- electrical notes: `native/src/constraints.cpp` (" + board_stackup().fabricator_name + "), `native/src/power_checks.cpp` analysis, typed ports (1.8V SDIO)");
    line();line("## Extracted SoM geometry");line();
    line("SoM outline: **"+number(plan.som.w)+" x "+number(plan.som.h)+" mm**.");
    line();line("| conn | SoM PCB `(at)` | carrier-top view (SoM-rel) | pad extent |");line("|---|---|---|---|");
    for(const auto& j:plan.som.js)line("| "+j.ref+" | ("+number(j.pcb_x)+", "+number(j.pcb_y)+") rot "+number(j.rot)+" | ("+number(j.x)+", "+number(j.y)+") | "+number(j.w)+" x "+number(j.h)+" mm |");
    line();line("Derived board: **"+number(plan.board_w)+" x "+number(plan.board_h)+" mm**; SoM origin at **("+number(plan.som_x)+", "+number(plan.som_y)+")** (centered). All coordinates below are board-frame mm, origin top-left, +y down (KiCad convention).");
    line();line("Outline derivation: "+plan.outline_note+".");line();
    line("## Edge connectors (pinned to edges by their mating direction)");line();
    line("| edge | sheet | block (x, y, w x h) | connector(s) | notes |");line("|---|---|---|---|---|");
    const std::map<std::string,int> edge_order{{"N",0},{"W",1},{"E",2},{"S",3}};
    const auto described=[&](const std::string& value)->const std::string&{
        const auto& description=connector_fact_of(input.project.connectors,value).description;
        if(!description)throw FloorplanError("floorplan: "+value+" has no description in the part facts");
        return *description;
    };
    std::vector<const FloorplanBlock*> edges,interior;
    for(const auto& b:plan.edge_blocks)edges.push_back(&b);
    for(const auto& b:plan.interior_blocks)interior.push_back(&b);
    std::stable_sort(edges.begin(),edges.end(),[&](const auto* a,const auto* b){return std::make_tuple(edge_order.at(a->edge),a->x,a->y)<std::make_tuple(edge_order.at(b->edge),b->x,b->y);});
    std::sort(interior.begin(),interior.end(),[](const auto* a,const auto* b){return a->name<b->name;});
    for(const auto* p:edges){
        const auto& b=*p;std::vector<std::string> cs,rs;
        for(const auto& c:b.conns)cs.push_back(c.value+" ("+described(c.value)+")");
        for(const auto& r:b.reserved)rs.push_back("RESERVED: "+r+" (deferred)");
        std::string conns=join(cs,", ");if(!rs.empty())conns+=(conns.empty()?"":"; ")+join(rs,", ");
        line("| "+b.edge+" | "+b.name+" | ("+number(b.x)+", "+number(b.y)+", "+number(b.w)+" x "+number(b.h)+") | "+conns+" |  |");
    }
    if(!plan.spilled.empty()){line();line("Edge spills (preferred edge full — honest, not hidden):");for(const auto& s:plan.spilled)line("- "+s);}
    line();line("## Interior blocks (zone = dominant SoM connector side, or the power cluster)");line();
    line("| sheet | anchor | block (x, y, w x h) | parts | est mm2 | notes |");line("|---|---|---|---|---|---|");
    for(const auto* p:interior){const auto& b=*p;line("| "+b.name+" | "+b.zone+" | ("+number(b.x)+", "+number(b.y)+", "+number(b.w)+" x "+number(b.h)+") | "+std::to_string(b.n_parts)+" | "+number(b.area)+" |  |");}
    line();line("## Routing constraint classes (" + board_stackup().fabricator_name + " — from native/src/constraints.cpp)");line();
    struct Class{std::set<std::string> nets;std::string kind;int impedance=0;bool paired=false;};
    std::map<std::string,Class> classes;
    std::vector<const CircuitSheetIr*> sheets;
    for(const auto& s:input.sheets)sheets.push_back(&s);
    std::sort(sheets.begin(),sheets.end(),[](const auto* a,const auto* b){return a->name<b->name;});
    bool researched=false;
    for(const auto* s:sheets){
        std::vector<const CircuitPortIr*> ports;
        for(const auto& p:s->port_types)ports.push_back(&p);
        std::sort(ports.begin(),ports.end(),[](const auto* a,const auto* b){return a->net<b->net;});
        for(const auto* p:ports){
            if(!p->pair_with.empty())for(const auto& n:s->nets)if(n.name==p->net && n.net_class=="port")researched=true;
            if(p->kind=="single")continue;
            const auto nc=port_net_class(*p);
            const auto found=classes.emplace(nc,Class{{},p->kind,p->has_impedance?p->impedance:0,!p->pair_with.empty()});
            found.first->second.nets.insert(p->net);
        }
    }
    std::vector<const FloorplanSiPair*> pairs;
    if(researched)for(const auto& p:input.si_pairs)pairs.push_back(&p);
    std::stable_sort(pairs.begin(),pairs.end(),[](const auto* a,const auto* b){return std::tie(a->interface,a->net_p)<std::tie(b->interface,b->net_p);});
    std::map<std::string,const FloorplanSiPair*> by_net;
    for(const auto* p:pairs){by_net[p->net_p]=p;by_net[p->net_n]=p;}
    line("| class | nets | geometry (track/gap mm) | match budget |");line("|---|---|---|---|");
    for(const auto& [name,c]:classes){
        std::string geometry="-",match="-";
        if(const auto* g=differential_geometry(c.impedance))geometry=number(g->width_mm)+" / "+number(g->gap_mm);
        if(c.paired){
            std::vector<double> intra,inter;
            for(const auto& n:c.nets){
                const auto p=by_net.find(n);
                if(p==by_net.end())throw FloorplanError(n+": typed "+c.kind+" but has no row in "+input.si_source+" — every pair's intra-pair skew is read per net from the researched table; there is no per-kind default to fall back to. Add the pair with its standard citation.");
                intra.push_back(p->second->intra_pair_skew_mm());inter.push_back(p->second->match_tol_mm());
            }
            match=mm_range("intra-pair",intra)+"; "+mm_range("inter-pair",inter);
        }else if(c.kind=="sd_bus")match="bus to CLK <= 2.5 mm (policy)";
        line("| "+name+" | "+std::to_string(c.nets.size())+" | "+geometry+" | "+match+" |");
    }
    line();line("Full per-net table: `carrier/manufacturing/layout_constraints.csv` (+ the `.kicad_dru` rules).");
    line();line("## Power and thermal (worst-case declared draws — powertree analysis)");line();
    line("| regulator | sheet | rail | I out (A) | est dissipation |");line("|---|---|---|---|---|");
    for(const auto& r:input.regulators){
        const double vo=rail_volts(r.vout).value_or(0),vi=rail_volts(r.vin).value_or(0);double power=0;
        if(r.kind=="buck"){if(r.eff==0)throw FloorplanError("floorplan: zero regulator efficiency for "+r.ref);power=(1/r.eff-1)*vo*r.i_out;}
        else if(r.kind=="ldo")power=std::max(0.0,vi-vo)*r.i_out;
        const auto ptxt=power>=.05 ? "~"+number(power,2)+" W":"negligible";
        line("| "+r.value+" ("+r.ref+") | "+r.sheet+" | "+r.vin+" -> "+r.vout+" | "+number(r.i_out,3)+" | "+ptxt+" |");
    }
    line();line("Numbers are the power-tree gate's worst-case declared draws (`carrier/reports/power_tree.txt`); regulators above ~0.3 W want copper pours + stitching vias.");
    return out;
}
}  // namespace schgen
