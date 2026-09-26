#include "floorplan_internal.hpp"
#include "schgen/board_decision_policy.hpp"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <limits>

namespace schgen {
using namespace floorplan_detail;
namespace {
std::string esc(const std::string& s) {
    std::string out;
    for (char c:s) { if (c=='&') out+="&amp;"; else if (c=='<') out+="&lt;"; else if (c=='>') out+="&gt;"; else out+=c; }
    return out;
}
std::string f(double v) {
    if(!std::isfinite(v))throw FloorplanError("floorplan SVG: non-finite coordinate");
    char buf[64]; const auto r=std::to_chars(buf,buf+sizeof(buf),v);
    if (r.ec!=std::errc{}) throw FloorplanError("floorplan SVG: invalid coordinate");
    std::string s(buf,r.ptr); if (s.find_first_of(".eE")==std::string::npos) s+=".0"; return s;
}
using namespace board_decision_policy::svg;
double px(double x) { return svg_map(x,ox,scale); }
double py(double y) { return svg_map(y,oy,scale); }
std::string gx(double x) { return f(px(x)); }
std::string gy(double y) { return f(py(y)); }
std::size_t text_length(const std::string& s) {
    return static_cast<std::size_t>(std::count_if(s.begin(),s.end(),[](unsigned char c){return (c&0xc0)!=0x80;}));
}
}  // namespace

std::string render_floorplan_svg(const FloorplanPlan& plan,const std::vector<FloorplanNote>& notes) {
    std::map<std::string,std::vector<int>> note_of;
    std::vector<const FloorplanNote*> legend;
    for (const auto& n:notes) { if (!n.block.empty()) note_of[n.block].push_back(n.n); if (n.n) legend.push_back(&n); }
    const double view_w=ox+plan.board_w*scale+30+400;
    const double view_h=std::max(oy+plan.board_h*scale+56,130.0+legend.size()*22+20);
    if(!std::isfinite(view_w)||!std::isfinite(view_h)||plan.board_w<=0||plan.board_h<=0||
       view_w>std::numeric_limits<int>::max()||view_h>std::numeric_limits<int>::max())
        throw FloorplanError("floorplan SVG: invalid or unrepresentable board dimensions");
    const int width=static_cast<int>(view_w),height=static_cast<int>(view_h);
    std::string out;
    auto emit=[&](const std::string& s){out+=s+"\n";};
    emit("<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 "+std::to_string(width)+" "+std::to_string(height)+"\" font-family=\"ui-monospace, SFMono-Regular, Menlo, monospace\" font-size=\"11\">");
    emit("<defs><pattern id=\"keepout\" width=\"6\" height=\"6\" patternUnits=\"userSpaceOnUse\" patternTransform=\"rotate(45)\"><line x1=\"0\" y1=\"0\" x2=\"0\" y2=\"6\" stroke=\"#dc2626\" stroke-width=\"1.2\"/></pattern></defs>");
    emit("<rect width=\""+std::to_string(width)+"\" height=\""+std::to_string(height)+"\" fill=\"white\"/>");
    emit("<text x=\"46.0\" y=\"26\" font-size=\"16\" font-weight=\"bold\">carrier floorplan — SUGGESTION, not constraint</text>");
    emit("<text x=\"46.0\" y=\"44\" fill=\"#6b7280\">to scale; derived from the netlists + "+esc(plan.som_source)+" — regenerate with `schgen floorplan`; the user owns the outline (PLAN.md round 2)</text>");
    const double bx=px(0),by=py(0),bw=plan.board_w*scale,bh=plan.board_h*scale;
    emit("<rect x=\""+f(bx)+"\" y=\""+f(by)+"\" width=\""+number(bw)+"\" height=\""+number(bh)+"\" fill=\"#fcfcfd\" stroke=\"#111827\" stroke-width=\"2\" stroke-dasharray=\"9,5\"/>");
    for (int x=10;x<static_cast<int>(plan.board_w);x+=10) {
        emit("<line x1=\""+gx(x)+"\" y1=\""+f(by)+"\" x2=\""+gx(x)+"\" y2=\""+gy(plan.board_h)+"\" stroke=\"#eceef1\" stroke-width=\"1\"/>");
        emit("<text x=\""+gx(x)+"\" y=\""+f(by-4)+"\" fill=\"#9ca3af\" font-size=\"8\" text-anchor=\"middle\">"+std::to_string(x)+"</text>");
    }
    for (int y=10;y<static_cast<int>(plan.board_h);y+=10) {
        emit("<line x1=\""+f(bx)+"\" y1=\""+gy(y)+"\" x2=\""+gx(plan.board_w)+"\" y2=\""+gy(y)+"\" stroke=\"#eceef1\" stroke-width=\"1\"/>");
        emit("<text x=\""+f(bx-6)+"\" y=\""+f(py(y)+3)+"\" fill=\"#9ca3af\" font-size=\"8\" text-anchor=\"end\">"+std::to_string(y)+"</text>");
    }
    emit("<text x=\""+f(bx)+"\" y=\""+f(py(plan.board_h)+16)+"\" fill=\"#6b7280\">derived outline "+number(plan.board_w)+" x "+number(plan.board_h)+" mm (SoM + connector bands + component area + perimeter keepout)</text>");
    std::vector<const FloorplanBlock*> blocks;
    for (const auto& b:plan.edge_blocks) blocks.push_back(&b);
    for (const auto& b:plan.interior_blocks) blocks.push_back(&b);
    std::sort(blocks.begin(),blocks.end(),[](const auto* a,const auto* b){return a->name<b->name;});
    for (const auto* bp:blocks) {
        const auto& b=*bp; const double x=px(b.x),y=py(b.y),w=b.w*scale,h=b.h*scale;
        const auto colors=b.kind=="edge" ? std::make_pair("#eff6ff","#1e3a8a") :
            (starts(b.name,"power") || starts(b.name,"bringup") ? std::make_pair("#ecfdf5","#047857") : std::make_pair("#f9fafb","#374151"));
        const auto dash=!b.reserved.empty() && b.conns.empty() ? " stroke-dasharray=\"5,4\"":"";
        emit("<rect x=\""+f(x)+"\" y=\""+f(y)+"\" width=\""+number(w)+"\" height=\""+number(h)+"\" rx=\"3\" fill=\""+colors.first+"\" stroke=\""+colors.second+"\" stroke-width=\"1.4\""+dash+"/>");
        double run=0,prior=0; for (const auto& c:b.conns) run+=c.w;
        for (std::size_t k=0;k<b.conns.size();++k) {
            const auto& c=b.conns[k]; double cx0,cy0,cw,ch;
            if (b.edge=="N" || b.edge=="S" || b.edge.empty()) {
                const double gap=(b.w-run)/(b.conns.size()+1);
                cx0=b.x+gap*(k+1)+prior; cy0=b.edge=="S" ? b.y+b.h-c.h : b.y; cw=c.w; ch=c.h;
            } else {
                const double gap=(b.h-run)/(b.conns.size()+1);
                cy0=b.y+gap*(k+1)+prior; cx0=b.edge=="W" ? b.x:b.x+b.w-c.h; cw=c.h;ch=c.w;
            }
            prior+=c.w;
            emit("<rect x=\""+gx(cx0)+"\" y=\""+gy(cy0)+"\" width=\""+number(cw*scale)+"\" height=\""+number(ch*scale)+"\" fill=\"#bfdbfe\" stroke=\"#1e3a8a\" stroke-width=\"1.2\"/>");
        }
        if (b.name=="ethernet") {
            double kx=x,ky=y,kw=w,kh=h/2;
            if (b.edge=="S") ky=y+h/2;
            else if (b.edge=="E") { kx=x+w/2;kw=w/2;kh=h; }
            else if (b.edge=="W") { kw=w/2;kh=h; }
            emit("<rect x=\""+number(kx)+"\" y=\""+number(ky)+"\" width=\""+number(kw)+"\" height=\""+number(kh)+"\" fill=\"url(#keepout)\" opacity=\"0.5\"/>");
        }
        const double cx=px(b.cx()),cy=py(b.cy());
        const bool vertical=(b.edge=="W" || b.edge=="E") && h>w;
        const double fs=std::min(11.0,std::max(7.0,((vertical ? h:w)-6)/(.62*std::max<std::size_t>(1,text_length(b.name)))));
        if (vertical) {
            emit("<text x=\""+number(cx-3)+"\" y=\""+f(cy)+"\" text-anchor=\"middle\" font-size=\""+number(fs,1)+"\" font-weight=\"bold\" transform=\"rotate(-90 "+number(cx-3)+" "+f(cy)+")\">"+esc(b.name)+"</text>");
            emit("<text x=\""+number(cx+8)+"\" y=\""+f(cy)+"\" text-anchor=\"middle\" font-size=\"7.5\" fill=\"#6b7280\" transform=\"rotate(-90 "+number(cx+8)+" "+f(cy)+")\">"+std::to_string(b.n_parts)+"p</text>");
        } else {
            emit("<text x=\""+f(cx)+"\" y=\""+f(cy)+"\" text-anchor=\"middle\" font-size=\""+number(fs,1)+"\" font-weight=\"bold\">"+esc(b.name)+"</text>");
            emit("<text x=\""+f(cx)+"\" y=\""+f(cy+10)+"\" text-anchor=\"middle\" font-size=\"7.5\" fill=\"#6b7280\">"+std::to_string(b.n_parts)+"p</text>");
        }
        for (std::size_t k=0;k<note_of[b.name].size();++k) {
            const double bcx=x+16*k;
            emit("<circle cx=\""+number(bcx)+"\" cy=\""+number(y)+"\" r=\"7\" fill=\"white\" stroke=\"#111827\" stroke-width=\"1.2\"/>");
            emit("<text x=\""+number(bcx)+"\" y=\""+number(y+3)+"\" text-anchor=\"middle\" font-size=\"9\" font-weight=\"bold\">"+std::to_string(note_of[b.name][k])+"</text>");
        }
    }
    const double sx=px(plan.som_x),sy=py(plan.som_y),sw=plan.som.w*scale,sh=plan.som.h*scale;
    emit("<rect x=\""+f(sx)+"\" y=\""+f(sy)+"\" width=\""+number(sw)+"\" height=\""+number(sh)+"\" rx=\"8\" fill=\"#fef3c7\" stroke=\"#92400e\" stroke-width=\"2\" opacity=\"0.95\"/>");
    emit("<text x=\""+number(sx+sw/2)+"\" y=\""+number(sy+sh/2-6)+"\" text-anchor=\"middle\" font-size=\"13\" font-weight=\"bold\" fill=\"#92400e\">Zynq SoM "+number(plan.som.w)+" x "+number(plan.som.h)+"</text>");
    emit("<text x=\""+number(sx+sw/2)+"\" y=\""+number(sy+sh/2+10)+"\" text-anchor=\"middle\" font-size=\"8.5\" fill=\"#92400e\">(bottom view: DF40 positions mirrored from the SoM PCB)</text>");
    for (const auto& j:plan.som.js) {
        const auto jx=gx(plan.som_x+j.x-j.w/2),jy=gy(plan.som_y+j.y-j.h/2);
        emit("<rect x=\""+jx+"\" y=\""+jy+"\" width=\""+number(j.w*scale)+"\" height=\""+number(j.h*scale)+"\" fill=\"#92400e\"/>");
        const double lx=px(plan.som_x+j.x),ly=py(plan.som_y+j.y);
        const auto rot=j.w<j.h ? " transform=\"rotate(-90 "+f(lx)+" "+number(ly+3.5)+")\"":"";
        emit("<text x=\""+f(lx)+"\" y=\""+number(ly+3.5)+"\" text-anchor=\"middle\" font-size=\"10\" font-weight=\"bold\" fill=\"white\""+rot+">"+j.ref+"</text>");
    }
    const double sby=py(plan.board_h)+30;
    emit("<line x1=\""+f(bx)+"\" y1=\""+f(sby)+"\" x2=\""+gx(20)+"\" y2=\""+f(sby)+"\" stroke=\"#111827\" stroke-width=\"3\"/>");
    emit("<text x=\""+gx(10)+"\" y=\""+f(sby+14)+"\" text-anchor=\"middle\" fill=\"#6b7280\">20 mm</text>");
    const double lx=ox+plan.board_w*scale+30;
    emit("<text x=\""+number(lx)+"\" y=\"68\" font-size=\"13\" font-weight=\"bold\">placement notes (derived)</text>");
    for (std::size_t k=0;k<legend.size();++k) {
        const double yy=oy+26+k*22;
        emit("<circle cx=\""+number(lx+8)+"\" cy=\""+number(yy-4)+"\" r=\"8\" fill=\"white\" stroke=\"#111827\" stroke-width=\"1.2\"/>");
        emit("<text x=\""+number(lx+8)+"\" y=\""+number(yy-1)+"\" text-anchor=\"middle\" font-size=\"9\" font-weight=\"bold\">"+std::to_string(legend[k]->n)+"</text>");
        emit("<text x=\""+number(lx+24)+"\" y=\""+number(yy)+"\">"+esc(legend[k]->short_text)+"</text>");
    }
    emit("<text x=\""+number(lx)+"\" y=\""+number(oy+26+legend.size()*22+12)+"\" fill=\"#6b7280\" font-size=\"10\">block area = courtyards (big parts raw, small x"+number(plan.factor)+") — see FLOORPLAN.md</text>");
    emit("</svg>");
    return out;
}
}  // namespace schgen
