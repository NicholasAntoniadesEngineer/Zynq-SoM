#include "ratsnest_documents_internal.hpp"
#include "schgen/ratsnest_gate.hpp"
#include "schgen/atomic_file.hpp"

namespace schgen {
using namespace ratsnest_detail;
namespace ratsnest_detail {
void safe_sheet(const std::string& name) {
    if(name.empty()||name=="."||name==".."||name.find_first_of("/\\")!=name.npos||
       std::any_of(name.begin(),name.end(),[](unsigned char c){return c<32||c==127;}))
        throw ProjectError("ratsnest: unsafe sheet filename");
}
void validate(const PcbModel& m,const RatsnestNets& nets,const RatsnestEdges& edges) {
    for(auto v:{m.board_w,m.board_h,m.origin_x,m.origin_y})
        if(!std::isfinite(v))throw ProjectError("ratsnest: nonfinite board geometry");
    if(m.board_w<0||m.board_h<0||m.board_w>4000||m.board_h>4000)
        throw ProjectError("ratsnest: board dimensions out of range");
    std::set<std::string> refs;bool som=false,plain_som=false;
    PcbCheckInput geometry(m);
    auto bounded=[](double v){if(!std::isfinite(v)||std::abs(v)>1e6)throw ProjectError("ratsnest: coordinate out of range");};
    for(std::size_t i=0;i<m.insts.size();++i){const auto& inst=m.insts[i];
        if(inst.ref.empty()||inst.ref.size()>100'000||std::any_of(inst.ref.begin(),inst.ref.end(),[](unsigned char c){return c<32||c==127;}))
            throw ProjectError("ratsnest: invalid reference label");
        if(!refs.insert(inst.ref).second)throw ProjectError("ratsnest: duplicate reference "+inst.ref);
        if(inst.side!="top"&&inst.side!="bottom")throw ProjectError("ratsnest: invalid side "+inst.side);
        safe_sheet(inst.sheet);som|=starts(inst.sheet,"som_");plain_som|=inst.sheet=="som";
        const auto box=geometry.courtyard_at(i);for(auto v:{box.x0,box.y0,box.x1,box.y1})bounded(v);
    }
    if(som&&plain_som)throw ProjectError("ratsnest: colliding som.png sheet names");
    if(m.som_keepout){auto b=*m.som_keepout;for(auto v:{b.x0,b.y0,b.x1,b.y1})bounded(v);
        if(b.x1<b.x0||b.y1<b.y0)throw ProjectError("ratsnest: invalid keepout rectangle");}
    for(const auto& [name,pts]:nets){auto it=edges.find(name);
        if(it==edges.end())throw ProjectError("ratsnest: missing net "+name);
        for(const auto& [x,y,ref,sheet]:pts){(void)ref;(void)sheet;bounded(x);bounded(y);}
        for(const auto& [a,b]:it->second)if(a<0||b<0||static_cast<std::size_t>(a)>=pts.size()||static_cast<std::size_t>(b)>=pts.size())
            throw ProjectError("ratsnest: invalid edge in "+name);
    }
}
}
RatsnestPalette ratsnest_palette(const std::vector<std::string>& sheets) {
    std::vector<std::string> real;for(const auto& s:sheets)if(!starts(s,"som_j"))real.push_back(s);
    std::sort(real.begin(),real.end());RatsnestPalette out;const auto n=std::max<std::size_t>(1,real.size());
    for(std::size_t i=0;i<real.size();++i){const double h=static_cast<double>(i)/n,s=i%2?.78:.55,v=i%3?.92:.74;
        const double hf=h*6;const int sector=static_cast<int>(hf);const double fraction=hf-sector;
        const double p=v*(1-s),q=v*(1-s*fraction),t=v*(1-s*(1-fraction));
        std::array<double,3> rgb{};
        switch(sector%6){case 0:rgb={v,t,p};break;case 1:rgb={q,v,p};break;case 2:rgb={p,v,t};break;
            case 3:rgb={p,q,v};break;case 4:rgb={t,p,v};break;default:rgb={v,p,q};break;}
        out[real[i]]={static_cast<unsigned char>(rgb[0]*255),static_cast<unsigned char>(rgb[1]*255),static_cast<unsigned char>(rgb[2]*255)};
    }
    for(const auto& s:sheets)if(starts(s,"som_j"))out[s]={201,148,32};return out;
}
std::vector<RatsnestAirwire> ratsnest_airwires(const PcbModel& m,const RatsnestNets& nets,
        const RatsnestEdges& edges,const std::optional<std::string>& side) {
    validate(m,nets,edges);if(side&&*side!="top"&&*side!="bottom")throw ProjectError("ratsnest: invalid requested side");
    std::map<std::string,std::string> sides;for(const auto& i:m.insts)sides[i.ref]=i.side;
    std::vector<RatsnestAirwire> out;
    for(const auto& [name,pts]:nets)for(const auto& [a,b]:edges.at(name)){
        const auto& [xa,ya,ra,sa]=pts[a];const auto& [xb,yb,rb,sb]=pts[b];
        if(side&&sides[ra]!=*side&&sides[rb]!=*side)continue;
        out.push_back({xa,ya,xb,yb,sa!=sb});
    }
    return out;
}
namespace {
std::string hex(RatsnestColor c){std::string out="#";for(auto b:c){out+="0123456789abcdef"[b>>4];out+="0123456789abcdef"[b&15];}return out;}
std::string xml(const std::string& text){std::string out;for(char c:text){if(c=='&')out+="&amp;";else if(c=='<')out+="&lt;";else if(c=='>')out+="&gt;";else out+=c;}return out;}
}
std::string render_ratsnest_svg(const PcbModel& m,const RatsnestPalette& palette,const RatsnestNets& nets,const RatsnestEdges& edges) {
    const auto aw=ratsnest_airwires(m,nets,edges);PcbCheckInput geometry(m);
    const auto width=raster_size(m.board_w*4+286),height=raster_size(m.board_h*4+96);
    auto round=[](double n){return pyfloat(py_round(n,2));};
    auto px=[&](double x){return round(28+(x-m.origin_x)*4);};auto py=[&](double y){return round(28+(y-m.origin_y)*4);};
    const auto w=std::to_string(width),h=std::to_string(height);std::vector<std::string> e;
    e.push_back("<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 "+w+" "+h+"\" font-family=\"monospace\" font-size=\"9\">");
    e.push_back("<rect width=\""+w+"\" height=\""+h+"\" fill=\"#0f1115\"/>");
    e.push_back("<rect x=\""+px(m.origin_x)+"\" y=\""+py(m.origin_y)+"\" width=\""+round(m.board_w*4)+"\" height=\""+round(m.board_h*4)+"\" fill=\"#161922\" stroke=\"#e5e7eb\" stroke-width=\"1.5\"/>");
    if(m.som_keepout){auto b=*m.som_keepout;e.push_back("<rect x=\""+px(b.x0)+"\" y=\""+py(b.y0)+"\" width=\""+round((b.x1-b.x0)*4)+"\" height=\""+round((b.y1-b.y0)*4)+"\" fill=\"none\" stroke=\"#c99420\" stroke-width=\"1\" stroke-dasharray=\"4,3\"/>");}
    for(bool cross:{true,false})for(const auto& a:aw)if(a.cross==cross)e.push_back("<line x1=\""+px(a.x0)+"\" y1=\""+py(a.y0)+"\" x2=\""+px(a.x1)+"\" y2=\""+py(a.y1)+"\" stroke=\""+(cross?"#ff3b30":"#5b6472")+"\" stroke-width=\""+(cross?"0.9":"0.35")+"\" opacity=\""+(cross?"0.85":"0.5")+"\"/>");
    std::vector<std::size_t> indices;for(std::size_t i=0;i<m.insts.size();++i)indices.push_back(i);
    std::stable_sort(indices.begin(),indices.end(),[&](auto a,auto b){return std::make_pair(m.insts[a].side!="bottom",m.insts[a].ref)<std::make_pair(m.insts[b].side!="bottom",m.insts[b].ref);});
    for(auto i:indices){const auto& inst=m.insts[i];const auto b=geometry.courtyard_at(i);
        e.push_back("<rect x=\""+px(b.x0)+"\" y=\""+py(b.y0)+"\" width=\""+round((b.x1-b.x0)*4)+"\" height=\""+round((b.y1-b.y0)*4)+"\" fill=\""+hex(color(palette,inst.sheet))+"\" opacity=\""+(inst.side=="bottom"?"0.45":"0.9")+"\" stroke=\"#0f1115\" stroke-width=\"0.3\"/>");}
    const auto lx=28+m.board_w*4+16;const double ly=32;
    e.push_back("<text x=\""+pyfloat(lx)+"\" y=\""+pyfloat(ly)+"\" fill=\"#e5e7eb\" font-size=\"11\" font-weight=\"bold\">subsystems</text>");
    int i=0;for(const auto& [name,c]:palette){const double yy=ly+16+i++*12;
        e.push_back("<rect x=\""+pyfloat(lx)+"\" y=\""+pyfloat(yy-8)+"\" width=\"9\" height=\"9\" fill=\""+hex(c)+"\"/>");
        e.push_back("<text x=\""+pyfloat(lx+14)+"\" y=\""+pyfloat(yy)+"\" fill=\"#cbd5e1\">"+xml(name)+"</text>");}
    e.push_back("<text x=\"28.0\" y=\""+std::to_string(height-10)+"\" fill=\"#94a3b8\">board "+g(m.board_w)+" x "+g(m.board_h)+" mm — boxes=footprints (top solid / bottom faint), red=cross-subsystem airwire, grey=intra, gold dash=SoM keep-out. schgen ratsnest (deterministic).</text>");
    e.push_back("</svg>");return join(e)+"\n";
}
RatsnestDocuments render_ratsnest_documents(const PcbModel& m,const RatsnestNets* supplied,const RatsnestEdges* supplied_edges) {
    validate(m,{},{});
    const auto made=supplied?RatsnestNets{}:ratsnest_net_pad_positions(m);const auto& nets=supplied?*supplied:made;
    for(const auto& [name,pts]:nets){(void)name;for(const auto& [x,y,ref,sheet]:pts){(void)ref;(void)sheet;
        if(!std::isfinite(x)||!std::isfinite(y)||std::abs(x)>1e6||std::abs(y)>1e6)throw ProjectError("ratsnest: coordinate out of range");}}
    const auto computed=supplied_edges?RatsnestEdges{}:ratsnest_mst(nets);const auto& edges=supplied_edges?*supplied_edges:computed;
    validate(m,nets,edges);std::set<std::string> sheets;for(const auto& inst:m.insts)sheets.insert(inst.sheet);
    const auto palette=ratsnest_palette({sheets.begin(),sheets.end()});RatsnestDocuments out;
    out.svg=render_ratsnest_svg(m,palette,nets,edges);out.images=render_ratsnest_images(m,palette,nets,edges);
    std::tie(out.cross_mm,out.total_mm,out.n_cross)=ratsnest_lengths(nets,edges);
    out.board_w=m.board_w;out.board_h=m.board_h;out.n_top=m.n_top;out.n_bottom=m.n_bottom;return out;
}
RatsnestPublication run_ratsnest_documents(const PcbModel& m,const std::filesystem::path& root,const RatsnestNets* nets,const RatsnestEdges* edges) {
    const auto doc=render_ratsnest_documents(m,nets,edges);RatsnestPublication out;
    out.png_top=root/"renders/ratsnest_top.png";out.png_bottom=root/"renders/ratsnest_bottom.png";out.svg=root/"docs/RATSNEST.svg";
    const auto sheets=root/"renders/ratsnest";std::filesystem::create_directories(sheets);std::filesystem::create_directories(out.svg.parent_path());
    std::set<std::filesystem::path> keep;
    for(const auto& im:doc.images){auto path=root/"renders"/im.filename;write_atomic_file(path.string(),{im.png.begin(),im.png.end()});
        if(path.parent_path()==sheets){keep.insert(path);out.sheets.push_back(path);}}
    write_atomic_file(out.svg.string(),{doc.svg.begin(),doc.svg.end()});
    for(const auto& entry:std::filesystem::directory_iterator(sheets))if(entry.path().extension()==".png"&&entry.is_regular_file()&&!keep.count(entry.path()))std::filesystem::remove(entry.path());
    out.cross_mm=doc.cross_mm;out.total_mm=doc.total_mm;out.n_cross=doc.n_cross;out.board_w=doc.board_w;out.board_h=doc.board_h;out.n_top=doc.n_top;out.n_bottom=doc.n_bottom;return out;
}
std::string ratsnest_document_summary(const RatsnestPublication& r,const std::filesystem::path& root) {
    auto relative=[&](const std::filesystem::path& p){auto rel=p.lexically_relative(root);
        if(rel.empty()||*rel.begin()=="..")throw ProjectError("ratsnest: summary path outside repository");return rel.generic_string();};
    return "ratsnest: "+relative(r.png_top)+" + "+relative(r.png_bottom)+" + "+relative(r.svg)+"\n  board "+g(r.board_w)+" x "+g(r.board_h)+" mm  (top "+std::to_string(r.n_top)+" / bottom "+std::to_string(r.n_bottom)+")\n  airwires: "+g(r.total_mm)+" mm total, "+g(r.cross_mm)+" mm cross-subsystem ("+std::to_string(r.n_cross)+" edges, "+f(r.total_mm?100*r.cross_mm/r.total_mm:0,1)+"% of length)\n";
}
} // namespace schgen
