#include "schgen/firmware_docs.hpp"
#include "bringup_internal.hpp"

namespace schgen {
using namespace bringup_detail;
namespace {
std::string esc(const std::string& s) {
    std::string o;for(char c:s)o+=c=='&'?"&amp;":c=='<'?"&lt;":c=='>'?"&gt;":std::string(1,c);return o;
}
std::optional<std::string> enable_port(const std::vector<ProjectCircuit>& sheets,const PowerReg& reg) {
    const CircuitSheetIr* circuit=nullptr;for(const auto& s:sheets)if(s.name==reg.sheet)circuit=&s.circuit;
    if(!circuit)return std::nullopt;std::set<std::string> ports;
    for(const auto& n:circuit->nets)if(n.net_class=="port"&&starts(n.name,"EN_"))
        for(const auto& p:n.pins)if(p.ref==reg.ref)ports.insert(n.name);
    return ports.empty()?std::nullopt:std::optional<std::string>(*ports.begin());
}
void rail_box(std::ostream& o,int x,int y,const PowerSequenceRow& r,const std::string& fill,const std::string& stroke) {
    o<<"<rect x=\""<<x<<"\" y=\""<<y<<"\" width=\"250\" height=\"46\" rx=\"8\" fill=\""<<fill<<"\" stroke=\""<<stroke<<"\" stroke-width=\"1.5\"/>\n";
    const auto head=esc(r.vout)+(r.volts&&*r.volts?"  ("+general(*r.volts)+" V)":"");
    o<<"<text x=\""<<x+10<<"\" y=\""<<y+17<<"\" font-weight=\"bold\" font-size=\"12\">"<<head<<"</text>\n";
    auto sub="load "+fixed(r.load,3)+" A / lim "+fixed(r.limit,2)+" A";
    if(r.enable&&!r.enable->empty())sub+="  ·  "+esc(*r.enable);
    o<<"<text x=\""<<x+10<<"\" y=\""<<y+34<<"\" fill=\"#374151\" font-size=\"10\">"<<esc(sub)<<"</text>\n";
}
}
PowerSequence build_power_sequence(const std::vector<ProjectCircuit>& sheets,const PowerCheckResult& result,const PowerPolicy& policy) {
    std::map<std::string,int> depth;
    for(const auto& [r,source]:policy.sources){(void)source;depth[r]=0;}
    // The legacy relaxation loops forever on a reachable positive-length cycle.
    // Bound iterations by graph vertices and report it instead of hanging.
    std::set<std::string> vertices;for(const auto& [r,d]:depth){(void)d;vertices.insert(r);}
    for(const auto& r:result.regs){vertices.insert(r.vin);vertices.insert(r.vout);}
    for(const auto& b:result.bridges){vertices.insert(b.from);vertices.insert(b.to);}
    bool changed=true;std::size_t passes=0;
    while(changed) {
        if(passes++>vertices.size())throw FirmwareDocsError("power-sequence depth: reachable regulator cycle");
        changed=false;
        for(const auto& r:result.regs)if(depth.count(r.vin)) {
            const int d=depth.at(r.vin)+1;
            if(!depth.count(r.vout)||depth.at(r.vout)<d){depth[r.vout]=d;changed=true;}
        }
        for(const auto& b:result.bridges)if(depth.count(b.from)&&(!depth.count(b.to)||depth.at(b.to)<depth.at(b.from))){depth[b.to]=depth.at(b.from);changed=true;}
    }
    std::set<std::string> always{"+3V3_SC","+5V_SOM"},sources;
    for(const auto& [r,source]:policy.sources){(void)source;always.insert(r);sources.insert(r);}
    std::vector<PowerSequenceRow> rows;
    for(const auto& r:result.regs) {
        auto en=enable_port(sheets,r);
        rows.push_back({r.vout,r.vin,rail_volts(r.vout,policy),decimal_round(r.i_out,3),decimal_round(r.limit_a,3),r.kind,r.ref,r.sheet,en});
        if(!en&&r.kind!="load_switch"&&depth.count(r.vout))always.insert(r.vout);
    }
    PowerSequence out;
    for(const auto& r:rows) {
        if(r.kind=="load_switch")out.modules.push_back(r);
        else if(!always.count(r.vout))out.chain.push_back(r);
    }
    std::stable_sort(out.chain.begin(),out.chain.end(),[&](const auto& a,const auto& b){return std::make_pair(depth.count(a.vout)?depth.at(a.vout):99,a.vout)<std::make_pair(depth.count(b.vout)?depth.at(b.vout):99,b.vout);});
    std::stable_sort(out.modules.begin(),out.modules.end(),[](const auto& a,const auto& b){return std::tie(a.vin,a.vout)<std::tie(b.vin,b.vout);});
    for(const auto& r:always)if(depth.count(r)||sources.count(r))out.stage0.push_back(r);
    return out;
}
std::string render_power_sequence_svg(const PowerSequence& seq,bool ok,const PowerPolicy& policy) {
    constexpr int x=40,col2=410,row=46,gap=26;int y=84;
    std::map<std::string,int> ypos,modpos;
    for(const auto& r:seq.stage0){ypos[r]=y;y+=row+gap;}
    const int chain_top=y+14;y=chain_top;
    for(const auto& r:seq.chain){ypos[r.vout]=y;y+=row+gap;}
    const int mod_top=std::max(chain_top,84);int my=mod_top;
    for(const auto& r:seq.modules){modpos[r.vout]=my;my+=row+14;}
    const int height=std::max(y,my)+70,width=720;
    std::ostringstream o;o.imbue(std::locale::classic());
    o<<"<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 "<<width<<' '<<height<<"\" font-family=\"ui-monospace, SFMono-Regular, Menlo, monospace\" font-size=\"11\">\n";
    o<<"<rect width=\""<<width<<"\" height=\""<<height<<"\" fill=\"white\"/>\n";
    o<<"<text x=\"40\" y=\"30\" font-size=\"15\" font-weight=\"bold\">carrier power-up sequence — staged bring-up ("<<(ok?"PASS":"FAIL")<<")</text>\n";
    o<<"<text x=\"40\" y=\"52\" font-size=\"11\" fill=\"#6b7280\">derived from the power-tree netlist; matches carrier/docs/BRINGUP.md staging. Arrows = rail dependency (parent -&gt; child).</text>\n";
    o<<"<text x=\"40\" y=\"76\" font-size=\"12\" font-weight=\"bold\" fill=\"#92400e\">stage 0 — always-on (pre-DIP / pre-PD)</text>\n";
    o<<"<text x=\"40\" y=\""<<chain_top-8<<"\" font-size=\"12\" font-weight=\"bold\" fill=\"#1e3a8a\">stages 1-3 — rail chain (close one DIP at a time)</text>\n";
    if(!seq.modules.empty())o<<"<text x=\"410\" y=\""<<mod_top-22<<"\" font-size=\"12\" font-weight=\"bold\" fill=\"#065f46\">stage 4 — gated module rails (SY6280 load switches)</text>\n";
    for(const auto& r:seq.chain)if(ypos.count(r.vin)&&ypos.count(r.vout)) {
        const int py=ypos.at(r.vin)+23,ch=ypos.at(r.vout)+23;
        o<<"<path d=\"M165,"<<py+22<<" C165,"<<py+30<<" 165,"<<ch-30<<" 165,"<<ch-22<<"\" fill=\"none\" stroke=\""<<(r.load>r.limit?"#dc2626":"#1e3a8a")<<"\" stroke-width=\"1.6\"/>\n";
    }
    for(const auto& r:seq.modules)if(ypos.count(r.vin)&&modpos.count(r.vout)) {
        const int py=ypos.at(r.vin)+23,ch=modpos.at(r.vout)+23;
        o<<"<path d=\"M290,"<<py+23<<" C350,"<<py+23<<" 350,"<<ch+23<<" 410,"<<ch+23<<"\" fill=\"none\" stroke=\""<<(r.load>r.limit?"#dc2626":"#059669")<<"\" stroke-width=\"1.2\" stroke-opacity=\"0.6\"/>\n";
    }
    for(const auto& r:seq.stage0) {
        PowerSequenceRow box;box.vout=r;box.volts=rail_volts(r,policy);
        for(const auto& [name,source]:policy.sources)if(name==r)box.limit=source.amps;
        rail_box(o,x,ypos.at(r),box,"#fef3c7","#92400e");
    }
    for(const auto& r:seq.chain)rail_box(o,x,ypos.at(r.vout),r,"#eff6ff","#1e3a8a");
    for(const auto& r:seq.modules)rail_box(o,col2,modpos.at(r.vout),r,"#ecfdf5","#065f46");
    o<<"</svg>\n";return o.str();
}
} // namespace schgen
