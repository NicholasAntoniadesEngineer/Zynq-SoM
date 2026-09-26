#include "part_import_internal.hpp"
#include <array>
#include <set>

namespace schgen {
namespace {
using namespace part_import_detail;
constexpr double pi=3.14159265358979323846;
using Point=std::pair<double,double>;
struct Context {
    double ox,oy;
    Point pt(double x,double y) const { return {rounded((x-ox)*0.254),rounded((y-oy)*0.254)}; }
    Point pt(const std::string& x,const std::string& y) const { return pt(number(x),number(y)); }
};
S xy(const std::string& tag,Point p) { return list({sym(tag),num(p.first),num(p.second)}); }
const std::map<int,std::string> layers{{1,"F.Cu"},{2,"B.Cu"},{3,"F.SilkS"},{4,"B.SilkS"},{5,"F.Paste"},{6,"B.Paste"},
    {7,"F.Mask"},{8,"B.Mask"},{10,"Edge.Cuts"},{12,"Cmts.User"},{13,"F.Fab"},{14,"B.Fab"},{15,"Dwgs.User"},
    {99,"F.CrtYd"},{100,"F.Fab"},{101,"F.SilkS"}};
std::string layer(double id) { const auto it=layers.find(integer(id));return it==layers.end()?"F.Fab":it->second; }
S fp_line(Point start,Point end,double width,const std::string& layer) {
    return list({sym("fp_line"),xy("start",start),xy("end",end),stroke(width),list({sym("layer"),str(layer)})});
}
void extend(std::vector<S>& out,std::vector<S> values) { for(auto& v:values)out.push_back(std::move(v)); }
struct Command { char kind; std::vector<double> args; };
std::vector<Command> path_commands(const std::string& path) {
    const std::string commands="MLHVAZmlhvaz";
    std::vector<Command> out;
    const auto source=trim(path);
    for(std::size_t start=0;start<source.size();) {
        auto end=source.find_first_of(commands,start+1);if(end==source.npos)end=source.size();
        const auto token=trim(source.substr(start,end-start));start=end;
        if(token.empty())continue;
        auto rest=token.substr(1);std::replace(rest.begin(),rest.end(),',',' ');
        Command cmd{upper(token.substr(0,1))[0],{}};
        for(const auto& arg:words(rest)) {
            // Unknown/malformed path operands must not silently become geometry at 0.
            const double value=number(arg,std::numeric_limits<double>::quiet_NaN());
            if(!std::isfinite(value))throw PartImportError("invalid EasyEDA SVG operand: "+arg);
            cmd.args.push_back(value);
        }
        out.push_back(std::move(cmd));
    }
    return out;
}
std::vector<Point> path_points(const std::string& path,const Context& ctx) {
    double x=0,y=0;std::vector<Point> out;
    for(const auto& cmd:path_commands(path)) {
        const auto& a=cmd.args;
        if(cmd.kind=='M' || cmd.kind=='L') {
            for(std::size_t i=0;i+1<a.size();i+=2) {x=a[i];y=a[i+1];out.push_back(ctx.pt(x,y));}
        } else if(cmd.kind=='H' && !a.empty()) {x=a.back();out.push_back(ctx.pt(x,y));}
        else if(cmd.kind=='V' && !a.empty()) {y=a.back();out.push_back(ctx.pt(x,y));}
        else if(cmd.kind=='A' && a.size()>=7) {x=a[5];y=a[6];out.push_back(ctx.pt(x,y));}
        else if(cmd.kind=='Z' && !out.empty() && out.front()!=out.back())out.push_back(out.front());
    }
    return out;
}
std::optional<Point> arc_center(Point p,Point q,double rx,double ry,double phi,bool large,bool sweep) {
    rx=std::abs(rx);ry=std::abs(ry);if(rx<1e-9 || ry<1e-9)return std::nullopt;
    const double angle=rotation(phi)*pi/180,cp=std::cos(angle),sp=std::sin(angle);
    const double dx=(p.first-q.first)/2,dy=(p.second-q.second)/2;
    const double xp=cp*dx+sp*dy,yp=-sp*dx+cp*dy;
    const double lam=xp*xp/(rx*rx)+yp*yp/(ry*ry);
    if(lam>1){const double scale=std::sqrt(lam);rx*=scale;ry*=scale;}
    const double numerator=rx*rx*ry*ry-rx*rx*yp*yp-ry*ry*xp*xp;
    const double denominator=rx*rx*yp*yp+ry*ry*xp*xp;
    double coefficient=denominator?std::sqrt(std::max(numerator/denominator,0.0)):0;
    if(large==sweep)coefficient=-coefficient;
    const double cxp=coefficient*rx*yp/ry,cyp=-coefficient*ry*xp/rx;
    return Point{cp*cxp-sp*cyp+(p.first+q.first)/2,sp*cxp+cp*cyp+(p.second+q.second)/2};
}
std::vector<std::array<Point,3>> arc_points(const std::string& path,const Context& ctx) {
    std::vector<std::array<Point,3>> out;std::optional<Point> cur;
    for(const auto& cmd:path_commands(path)) {
        const auto& a=cmd.args;
        if(cmd.kind=='M' && a.size()>=2)cur=Point{a[0],a[1]};
        else if(cmd.kind=='A' && a.size()>=7 && cur) {
            const Point end{a[5],a[6]};const bool large=integer(a[3])!=0,sweep=integer(a[4])!=0;
            const auto c=arc_center(*cur,end,a[0],a[1],a[2],large,sweep);
            if(c) {
                const double a0=std::atan2(cur->second-c->second,cur->first-c->first);
                const double a1=std::atan2(end.second-c->second,end.first-c->first);
                double delta=std::fmod(a1-a0,2*pi);if(delta<0)delta+=2*pi;if(!sweep)delta-=2*pi;
                const double mid=a0+delta/2;
                const double radius=std::hypot(cur->first-c->first,cur->second-c->second);
                out.push_back({ctx.pt(cur->first,cur->second),ctx.pt(c->first+radius*std::cos(mid),c->second+radius*std::sin(mid)),ctx.pt(end.first,end.second)});
            }
            cur=end;
        }
    }
    return out;
}
std::vector<S> pad_nodes(const std::vector<std::string>& f,const Context& ctx) {
    if(f.size()<11)throw PartImportError("truncated EasyEDA PAD");
    const std::map<std::string,std::string> shapes{{"ELLIPSE","circle"},{"RECT","rect"},{"OVAL","oval"},{"POLYGON","custom"}};
    auto pn=f[7];const auto left=pn.find('('),right=pn.find(')');if(left!=pn.npos && right!=pn.npos)pn=pn.substr(left+1,right>left?right-left-1:0);
    const double hole_len=f.size()>12?mm(f[12]):0;
    const bool plated=f.size()>14 && !f[14].empty()?upper(f[14])=="Y":true;
    const auto [x,y]=ctx.pt(f[1],f[2]);const double w=std::max(mm(f[3]),0.01),h=std::max(mm(f[4]),0.01),hole=2*mm(f[8]);
    const int layer_id=integer(number(f[5],1));const double rot=rotation(number(f[10]));
    auto it=shapes.find(f[0]);std::string shape=it==shapes.end()?"custom":it->second;
    const bool through=hole>0;
    std::vector<std::string> ls;
    if(through)ls=layer_id==1?std::vector<std::string>{"F.Cu","F.Mask"}:layer_id==2?std::vector<std::string>{"B.Cu","B.Mask"}:std::vector<std::string>{"*.Cu","*.Mask"};
    else ls=layer_id==2?std::vector<std::string>{"B.Cu","B.Paste","B.Mask"}:layer_id==11?std::vector<std::string>{"*.Cu","*.Paste","*.Mask"}:std::vector<std::string>{"F.Cu","F.Paste","F.Mask"};
    if(f[0]=="ELLIPSE" && std::abs(w-h)>1e-6)shape="oval";
    auto at=list({sym("at"),num(x),num(y)});if(shape!="custom" && rot)append(at,num(rounded(rot,2)));
    auto pad=list({sym("pad"),str(pn),sym(through?(!plated?"np_thru_hole":"thru_hole"):"smd"),sym(shape),std::move(at)});
    auto layer_node=[&] {S out=list({sym("layers")});for(const auto& l:ls)append(out,str(l));return out;};
    if(shape=="custom") {
        const auto coords=words(f[9]);auto pts=list({sym("pts")});
        for(std::size_t i=0;i+1<coords.size();i+=2) {
            const auto p=ctx.pt(coords[i],coords[i+1]);append(pts,xy("xy",{rounded(p.first-x),rounded(p.second-y)}));
        }
        if(items(pts).size()<4)return {};
        append(pad,list({sym("size"),num(0.1),num(0.1)}));append(pad,layer_node());
        append(pad,list({sym("options"),list({sym("clearance"),sym("outline")}),list({sym("anchor"),sym("rect")})}));
        append(pad,list({sym("primitives"),list({sym("gr_poly"),std::move(pts),list({sym("width"),num(0)}),list({sym("fill"),sym("yes")})})}));
    } else {
        append(pad,list({sym("size"),num(w),num(h)}));
        if(through) {
            if(hole_len) {
                const double longest=std::max(hole,hole_len);
                append(pad,h-longest>=w-longest?list({sym("drill"),sym("oval"),num(hole),num(hole_len)}):list({sym("drill"),sym("oval"),num(hole_len),num(hole)}));
            } else append(pad,list({sym("drill"),num(hole)}));
        }
        if(!through && (shape=="rect" || shape=="roundrect") && std::find(ls.begin(),ls.end(),"F.Paste")!=ls.end() && std::min(w,h)>=2) {
            ls.erase(std::remove(ls.begin(),ls.end(),"F.Paste"),ls.end());append(pad,layer_node());
            std::vector<S> out{std::move(pad)};extend(out,paste_grid(pn,x,y,w,h,rot));return out;
        }
        append(pad,layer_node());
    }
    return {std::move(pad)};
}
S fp_property(const std::string& key,const std::string& value,double y,const std::string& layer,bool hide) {
    auto p=list({sym("property"),str(key),str(value),list({sym("at"),num(0),num(y),num(0)}),list({sym("layer"),str(layer)})});
    if(hide)append(p,list({sym("hide"),sym("yes")}));
    append(p,list({sym("effects"),list({sym("font"),list({sym("size"),num(1),num(1)}),list({sym("thickness"),num(0.15)})})}));return p;
}
}

namespace part_import_detail {
std::vector<S> paste_grid(const std::string& pn,double x,double y,double w,double h,double rot) {
    const int nx=std::max(2,integer(std::ceil(w/1.5))),ny=std::max(2,integer(std::ceil(h/1.5)));
    if(static_cast<long long>(nx)*ny>1000000)throw PartImportError("EasyEDA paste grid exceeds one million apertures");
    const double px=w/nx,py=h/ny,aw=rounded(px*std::sqrt(0.60)),ah=rounded(py*std::sqrt(0.60));
    const double a=rot*pi/180,c=std::cos(a),s=std::sin(a);std::vector<S> out;
    for(int i=0;i<nx;++i)for(int j=0;j<ny;++j) {
        const double dx=-w/2+px*(i+0.5),dy=-h/2+py*(j+0.5);
        auto at=list({sym("at"),num(rounded(x+dx*c-dy*s)),num(rounded(y+dx*s+dy*c))});
        if(rot)append(at,num(rounded(rot,2)));
        out.push_back(list({sym("pad"),str(pn),sym("smd"),sym("rect"),std::move(at),
            list({sym("size"),num(aw),num(ah)}),list({sym("layers"),str("F.Paste")})}));
    }
    return out;
}
}

std::vector<Sexpr> part_ep_pad_nodes(const std::string& number,const std::string& lcsc) {
    if(lcsc!="C3192119")throw PartImportError("no exposed-pad specification for "+lcsc);
    // MPS MPQ4423H Rev1.11 QFN-8 bottom D2xE2 nominal, 1.0 x 1.1 mm.
    return {list({sym("pad"),str(number),sym("smd"),sym("rect"),list({sym("at"),num(0),num(0)}),
        list({sym("size"),num(1),num(1.1)}),list({sym("layers"),str("F.Cu"),str("F.Paste"),str("F.Mask")})})};
}

std::vector<Sexpr> part_silk_plus_nodes(const std::string& lcsc) {
    if(lcsc!="C5365933")return {};
    // EasyEDA layer-12 SOLIDREGION cross at pad 1, V_RTC_BAT; pad 2 is ground.
    return {fp_line({rounded(-5.6-0.6),0},{rounded(-5.6+0.6),0},0.15,"F.SilkS"),
            fp_line({-5.6,-0.6},{-5.6,0.6},0.15,"F.SilkS")};
}

PartFootprint part_convert_footprint(const JsonNode& result,const std::string& name,const PartImportInfo& info,
                                    const std::vector<std::string>& model_files,const std::optional<CatalogPin>& ep) {
    const auto& pkg=field(result,"packageDetail");const auto& data=field(pkg,"dataStr");
    const auto& shapes=field(data,"shape").array_value;
    if(shapes.empty())throw PartImportError("EasyEDA payload has no footprint (packageDetail)");
    const auto& head=field(data,"head");const auto& cp=field(head,"c_para");
    const Context ctx{number(field(head,"x")),number(field(head,"y"))};
    const bool smd=truth(field(result,"SMT")) && get(pkg,"title").find("-TH_")==std::string::npos;
    PartFootprint out;const auto& p=info.part;
    auto fp=list({sym("footprint"),str(name),list({sym("version"),num(20260206)}),list({sym("generator"),str("schgen_part_gen")}),
        list({sym("generator_version"),str("1.0")}),list({sym("layer"),str("F.Cu")}),
        list({sym("descr"),str(get(cp,"package")+" — "+p.description+" (EasyEDA/LCSC "+p.lcsc+", faithful conversion)")}),
        list({sym("tags"),str(join(info.tags," "))})});
    std::vector<S> pads,graphics;
    for(const auto& entry:shapes) {
        const auto line=string(entry);const auto tilde=line.find('~');
        const auto kind=line.substr(0,tilde);const auto f=split(tilde==line.npos?"":line.substr(tilde+1),"~");
        const auto need=[&](std::size_t n) {if(f.size()<n)throw PartImportError("truncated EasyEDA "+kind);};
        if(kind=="PAD")extend(pads,pad_nodes(f,ctx));
        else if(kind=="TRACK") {
            need(4);const auto pts=words(f[3]);const auto ly=layer(number(f[1],3));
            for(std::size_t i=0;i+3<pts.size();i+=2)graphics.push_back(fp_line(ctx.pt(pts[i],pts[i+1]),ctx.pt(pts[i+2],pts[i+3]),mm(f[0]),ly));
        } else if(kind=="CIRCLE") {
            need(5);const auto q=ctx.pt(f[0],f[1]);graphics.push_back(list({sym("fp_circle"),xy("center",q),
                xy("end",{rounded(q.first+mm(f[2])),q.second}),stroke(mm(f[3])),list({sym("fill"),sym("none")}),list({sym("layer"),str(layer(number(f[4],3)))})}));
        } else if(kind=="RECT") {
            need(5);const auto q=ctx.pt(f[0],f[1]);graphics.push_back(list({sym("fp_rect"),xy("start",q),
                xy("end",{rounded(q.first+mm(f[2])),rounded(q.second+mm(f[3]))}),stroke(f.size()>7?mm(f[7]):0.1),
                list({sym("fill"),sym("none")}),list({sym("layer"),str(layer(number(f[4],3)))})}));
        } else if(kind=="ARC") {
            need(4);for(const auto& a:arc_points(f[3],ctx))graphics.push_back(list({sym("fp_arc"),xy("start",a[0]),xy("mid",a[1]),xy("end",a[2]),
                stroke(mm(f[0])),list({sym("layer"),str(layer(number(f[1],3)))})}));
        } else if(kind=="HOLE" || kind=="VIA") {
            need(kind=="VIA"?5:3);const auto q=ctx.pt(f[0],f[1]);const double d=kind=="VIA"?mm(f[2]):2*mm(f[2]);
            const double drill=kind=="VIA"?2*mm(f[4]):d;
            pads.push_back(list({sym("pad"),str(""),sym(kind=="VIA"?"thru_hole":"np_thru_hole"),sym("circle"),xy("at",q),
                list({sym("size"),num(d),num(d)}),list({sym("drill"),num(drill)}),list({sym("layers"),str("*.Cu"),str("*.Mask")})}));
        } else if(kind=="TEXT") {
            if(f.size()<10 || f[9].empty())continue;
            const auto q=ctx.pt(f[1],f[2]);auto ly=layer(number(f[6],3));
            if(f[0]=="N") {const auto i=ly.find(".SilkS");if(i!=ly.npos)ly.replace(i,6,".Fab");}
            const double size=std::max(mm(f[8]),0.5);
            graphics.push_back(list({sym("fp_text"),sym("user"),str(f[9]),list({sym("at"),num(q.first),num(q.second),num(rounded(rotation(number(f[4])),2))}),
                list({sym("layer"),str(ly)}),list({sym("effects"),list({sym("font"),list({sym("size"),num(size),num(size)}),list({sym("thickness"),num(std::max(mm(f[3]),0.1))})})})}));
        } else if(kind=="SOLIDREGION") {
            need(3);const int id=integer(number(f[0],3));const auto type=f.size()>3?f[3]:"solid";
            if(!std::set<int>{3,4,13,14,99}.count(id) || (type!="solid" && type!="npth"))continue;
            const auto points=path_points(f[2],ctx);if(points.size()<3)continue;
            if(id==99) {for(std::size_t i=0;i+1<points.size();++i)graphics.push_back(fp_line(points[i],points[i+1],0.05,"F.CrtYd"));}
            else {auto pts=list({sym("pts")});for(const auto& q:points)append(pts,xy("xy",q));
                graphics.push_back(list({sym("fp_poly"),std::move(pts),list({sym("stroke"),list({sym("width"),num(0)}),list({sym("type"),sym("solid")})}),
                    list({sym("fill"),sym("yes")}),list({sym("layer"),str(layers.at(id))})}));}
        } else if(kind=="SVGNODE") {
            JsonNode node;try {node=parse_json_text(f[0]);}catch(const std::runtime_error&){continue;}
            const auto& attrs=field(node,"attrs");const auto canvas=split(get(data,"canvas"),"~");
            const double cox=canvas.size()>17?number(canvas[16]):ctx.ox,coy=canvas.size()>17?number(canvas[17]):ctx.oy;
            const auto co=split(get(attrs,"c_origin").empty()?"0,0":get(attrs,"c_origin"),",");
            const auto rot=split(get(attrs,"c_rotation").empty()?"0,0,0":get(attrs,"c_rotation"),",");
            out.model=PartModelTransform{get(attrs,"uuid"),get(attrs,"title"),rounded((number(co[0])-cox)*0.254),
                rounded(-((co.size()>1?number(co[1]):0)-coy)*0.254),rounded(number(field(attrs,"z"))*0.254),
                rotation(360-number(rot[0])),rotation(360-(rot.size()>1?number(rot[1]):0)),rotation(360-(rot.size()>2?number(rot[2]):0))};
        }
    }
    if(ep)extend(pads,part_ep_pad_nodes(ep->number,p.lcsc));
    extend(graphics,part_silk_plus_nodes(p.lcsc));
    append(fp,list({sym("attr"),sym(smd?"smd":"through_hole")}));
    double low=0,high=0;bool first=true;
    for(const auto& pad:pads) {
        const double y=std::get<double>(items(items(pad).at(4)).at(2).v);
        if(first){low=high=y;first=false;}else {low=std::min(low,y);high=std::max(high,y);}
    }
    append(fp,fp_property("Reference","REF**",rounded(low-2,2),"F.SilkS",false));
    append(fp,fp_property("Value",name,rounded(high+2,2),"F.Fab",false));
    append(fp,fp_property("Datasheet",p.datasheet,0,"F.Fab",true));
    append(fp,fp_property("Description",p.description,0,"F.Fab",true));
    append(fp,fp_property("LCSC",p.lcsc,0,"F.Fab",true));
    append(fp,list({sym("fp_text"),sym("user"),str("${REFERENCE}"),list({sym("at"),num(0),num(0),num(0)}),list({sym("layer"),str("F.Fab")}),
        list({sym("effects"),list({sym("font"),list({sym("size"),num(1),num(1)}),list({sym("thickness"),num(0.15)})})})}));
    for(auto& g:graphics)append(fp,std::move(g));for(const auto& pad:pads)append(fp,pad);
    if(out.model && !model_files.empty()) {
        double hx=0,hy=0;
        for(const auto& pad:pads) {
            double x=0,y=0,w=0,h=0;
            for(const auto& element:items(pad)) {
                if(tag(element,"at")){x=std::get<double>(items(element)[1].v);y=std::get<double>(items(element)[2].v);}
                else if(tag(element,"size")){w=std::get<double>(items(element)[1].v);h=std::get<double>(items(element)[2].v);}
            }
            hx=std::max(hx,std::abs(x)+w/2);hy=std::max(hy,std::abs(y)+h/2);
        }
        auto& m=*out.model;
        if(std::abs(m.tx)>hx+5 || std::abs(m.ty)>hy+5) {
            out.diagnostics.push_back("implausible model offset reset to 0 (EasyEDA c_origin unit mismatch)");m.tx=m.ty=0;
        }
        append(fp,list({sym("model"),str(model_files[0]),list({sym("offset"),list({sym("xyz"),num(m.tx),num(m.ty),num(m.tz)})}),
            list({sym("scale"),list({sym("xyz"),num(1),num(1),num(1)})}),list({sym("rotate"),list({sym("xyz"),num(m.rx),num(m.ry),num(m.rz)})})}));
    }
    out.tree=std::move(fp);out.pad_count=pads.size();return out;
}
} // namespace schgen
