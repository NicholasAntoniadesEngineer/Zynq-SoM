#include "schgen/model3d.hpp"
#include "render_models_internal.hpp"
#include <cstdlib>
#include <limits>
#include <regex>

namespace schgen {
namespace fs=std::filesystem;
namespace {
using namespace render_models_detail;
using Pair=std::pair<double,double>;
std::optional<Model3dBox> bounds(const std::vector<Pair>& pts) {
    if (pts.empty()) return std::nullopt;
    Model3dBox b{pts.front().first,pts.front().second,pts.front().first,pts.front().second};
    for (const auto& [x,y]:pts) { if (!std::isfinite(x)||!std::isfinite(y)) throw std::runtime_error("non-finite model3d bounds"); b[0]=std::min(b[0],x); b[1]=std::min(b[1],y); b[2]=std::max(b[2],x); b[3]=std::max(b[3],y); }
    return b;
}
std::optional<Model3dBox> model_bounds(const std::string& text,bool wrl) {
    std::vector<Pair> pts;
    if (wrl) {
        static const std::regex point(R"(point\s*\[)"), num(R"(-?\d+\.?\d*(?:e-?\d+)?)");
        std::size_t start=0; std::smatch match;
        while (start<text.size() && std::regex_search(text.begin()+static_cast<std::ptrdiff_t>(start),text.end(),match,point)) {
            start+=static_cast<std::size_t>(match.position()+match.length());
            const auto end=text.find(']',start); if (end==text.npos) break;
            const auto block=text.substr(start,end-start); std::vector<double> numbers;
            for (std::sregex_iterator i(block.begin(),block.end(),num),last;i!=last;++i) numbers.push_back(number(i->str()));
            for (std::size_t i=0;i+2<numbers.size();i+=3) pts.emplace_back(numbers[i],numbers[i+1]);
            start=end+1;
        }
    } else {
        static const std::regex cart(R"(CARTESIAN_POINT\('[^']*',\(([-\d.E+]+),([-\d.E+]+),([-\d.E+]+)\)\))");
        for (std::sregex_iterator i(text.begin(),text.end(),cart),last;i!=last;++i) pts.emplace_back(number((*i)[1]),number((*i)[2]));
    }
    return bounds(pts);
}
constexpr double pin_depth=0.2,hole_slack=0.3;
using Triple=std::array<double,3>;
std::vector<Triple> model_points(const std::string& text,bool wrl) {
    std::vector<Triple> pts;
    if (wrl) {
        static const std::regex point(R"(point\s*\[)"), num(R"(-?\d+\.?\d*(?:e-?\d+)?)");
        std::size_t start=0; std::smatch match;
        while (start<text.size() && std::regex_search(text.begin()+static_cast<std::ptrdiff_t>(start),text.end(),match,point)) {
            start+=static_cast<std::size_t>(match.position()+match.length());
            const auto end=text.find(']',start); if (end==text.npos) break;
            const auto block=text.substr(start,end-start); std::vector<double> numbers;
            for (std::sregex_iterator i(block.begin(),block.end(),num),last;i!=last;++i) numbers.push_back(number(i->str()));
            for (std::size_t i=0;i+2<numbers.size();i+=3) pts.push_back({numbers[i],numbers[i+1],numbers[i+2]});
            start=end+1;
        }
    } else {
        static const std::regex cart(R"(CARTESIAN_POINT\('[^']*',\(([-\d.E+]+),([-\d.E+]+),([-\d.E+]+)\)\))");
        for (std::sregex_iterator i(text.begin(),text.end(),cart),last;i!=last;++i) pts.push_back({number((*i)[1]),number((*i)[2]),number((*i)[3])});
    }
    return pts;
}
struct Hole { std::string name; double x,y,drill; };
std::vector<Hole> holes(const std::string& text) {
    static const std::regex pad(R"rx(\(pad\s+"([^"]*)"\s+thru_hole\s+\S+\s+\(at\s+(-?[\d.]+)\s+(-?[\d.]+)(?:\s+[-\d.]+)?\)\s+\(size\s+[-\d.]+\s+[-\d.]+\)\s+\(drill\s+(?:oval\s+)?([\d.]+)(?:\s+([\d.]+))?)rx");
    std::vector<Hole> out;
    for (std::sregex_iterator i(text.begin(),text.end(),pad),last;i!=last;++i)
        out.push_back({(*i)[1].str(),number((*i)[2]),number((*i)[3]),std::max(number((*i)[4]),(*i)[5].matched?number((*i)[5]):0.0)});
    return out;
}
std::optional<Pair> fab_xy(const std::string& text) {
    static const std::regex element(R"(\(fp_(?:line|rect|poly|circle)\b)"), xy(R"(\((?:start|end|center|mid|xy)\s+(-?[\d.]+)\s+(-?[\d.]+)\))");
    std::vector<Pair> pts; std::size_t start=0; std::smatch m;
    while (start<text.size() && std::regex_search(text.begin()+static_cast<std::ptrdiff_t>(start),text.end(),m,element)) {
        start+=static_cast<std::size_t>(m.position()); auto end=start; int depth=0;
        for (;end<text.size();++end) { if (text[end]=='(') ++depth; else if (text[end]==')' && --depth==0) break; }
        const auto block=text.substr(start,end-start+1); start=std::min(end+1,text.size());
        if (block.find("\"F.Fab\"")==block.npos) continue;
        for (std::sregex_iterator i(block.begin(),block.end(),xy),last;i!=last;++i) pts.emplace_back(number((*i)[1]),number((*i)[2]));
    }
    const auto b=bounds(pts); if (!b) return std::nullopt;
    return Pair{(*b)[2]-(*b)[0],(*b)[3]-(*b)[1]};
}
std::optional<Model3dBox> pads(const std::string& text) {
    static const std::regex pad(R"rx(\(pad\s+"[^"]*"\s+\S+\s+\S+\s+\(at\s+(-?[\d.]+)\s+(-?[\d.]+)(?:\s+[-\d.]+)?\)\s+\(size\s+(-?[\d.]+)\s+(-?[\d.]+)\))rx");
    std::vector<Pair> pts;
    for (std::sregex_iterator i(text.begin(),text.end(),pad),last;i!=last;++i) {
        const double x=number((*i)[1]),y=number((*i)[2]),w=number((*i)[3]),h=number((*i)[4]);
        pts.emplace_back(x-w/2,y-h/2); pts.emplace_back(x+w/2,y+h/2);
    }
    return bounds(pts);
}
std::array<double,3> xyz(const std::string& text,const std::string& tag,std::array<double,3> fallback) {
    const std::regex re("\\("+tag+R"(\s*\(xyz\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\))"); std::smatch m;
    return std::regex_search(text,m,re)?std::array<double,3>{number(m[1]),number(m[2]),number(m[3])}:fallback;
}
std::string keys(const std::map<std::string,std::string>& m) {
    std::vector<std::string> v; for (const auto& kv:m) v.push_back(kv.first); return join(v,", ");
}
void judge(Model3dGeometry& g,const std::string& footprint,const std::array<double,3>& off) {
    using namespace render_models_detail;
    if (!g.model_box) return;
    const double w=(*g.model_box)[2]-(*g.model_box)[0],h=(*g.model_box)[3]-(*g.model_box)[1];
    if (g.fab_xy && g.fab_xy->first>0 && g.fab_xy->second>0) {
        const double rw=w/g.fab_xy->first,rh=h/g.fab_xy->second;
        if (!(rw>=0.5&&rw<=2&&rh>=0.5&&rh<=2)) g.misfit="model "+fixed(w,1)+"x"+fixed(h,1)+" mm vs footprint body "+fixed(g.fab_xy->first,1)+"x"+fixed(g.fab_xy->second,1)+" mm (ratio "+fixed(rw,2)+","+fixed(rh,2)+" outside [0.5,2.0])";
    }
    if (g.pad_box) {
        const auto& p=*g.pad_box; const auto& m=*g.model_box;
        const double pa=(p[2]-p[0])*(p[3]-p[1]);
        if (pa>0) {
            const double frac=std::max(0.0,std::min(m[2],p[2])-std::max(m[0],p[0]))*std::max(0.0,std::min(m[3],p[3])-std::max(m[1],p[1]))/pa;
            if (frac<0.2) g.misplaced="body ("+fixed(m[0],1)+","+fixed(m[1],1)+")..("+fixed(m[2],1)+","+fixed(m[3],1)+") mm overlaps the pad area only "+fixed(frac*100,0)+"% (needs >=20%); model offset ("+fixed(off[0],2)+","+fixed(off[1],2)+") plants the body off its pads";
        }
    }
    const auto drilled=holes(footprint);
    if (drilled.empty()||g.tilted||g.pins.empty()) return;
    std::vector<std::string> empty;
    for (const auto& hole:drilled) {
        double nearest=std::numeric_limits<double>::infinity();
        for (const auto& [x,y]:g.pins) nearest=std::min(nearest,std::hypot(hole.x-x,hole.y-y));
        if (nearest>hole.drill/2+hole_slack) empty.push_back(hole.name+" ("+fixed(nearest,2)+" mm from the nearest pin)");
    }
    if (!empty.empty()) g.unseated=std::to_string(empty.size())+" of "+std::to_string(drilled.size())+" drilled pads have no model pin through them: "+join(empty,", ")+"; the model is turned or offset against its footprint";
}
Model3dGeometry place(const std::string& footprint,const std::string& clause,const std::string& model_text,const std::string& extension,std::array<double,3>& off) {
    using namespace render_models_detail;
    Model3dGeometry g; g.fab_xy=fab_xy(footprint); g.pad_box=pads(footprint);
    std::string ext=extension; std::transform(ext.begin(),ext.end(),ext.begin(),[](unsigned char c){return static_cast<char>(std::tolower(c));});
    const bool wrl=ext==".wrl"; const auto b=model_bounds(model_text,wrl); if (!b) return g;
    auto scale=xyz(clause,"scale",{1,1,1}); for (auto& s:scale) if (s==0) s=1;
    auto rz=std::fmod(xyz(clause,"rotate",{0,0,0})[2],360); if (rz<0) rz+=360;
    off=xyz(clause,"offset",{0,0,0}); const double unit=wrl?2.54:1;
    double w=((*b)[2]-(*b)[0])*unit*std::abs(scale[0]),h=((*b)[3]-(*b)[1])*unit*std::abs(scale[1]);
    // Extents use absolute scale, but the center must retain reflection signs.
    const double cx=((*b)[0]+(*b)[2])/2*unit*scale[0],cy=((*b)[1]+(*b)[3])/2*unit*scale[1];
    const double th=rz*(std::acos(-1.0)/180),rcx=cx*std::cos(th)+cy*std::sin(th),rcy=-cx*std::sin(th)+cy*std::cos(th);
    if (std::fmod(rz,180)==90) std::swap(w,h);
    else if(std::fmod(rz,90)!=0) {
        // Axis-aligned envelope of all four transformed rectangle corners.
        // Keep exact quarter-turn extents rather than introducing trig noise.
        const double cosine=std::abs(std::cos(th)),sine=std::abs(std::sin(th));
        const double rotated_w=w*cosine+h*sine;
        h=w*sine+h*cosine;w=rotated_w;
    }
    g.model_xy=Pair{w,h}; g.model_box=Model3dBox{off[0]+rcx-w/2,off[1]+rcy-h/2,off[0]+rcx+w/2,off[1]+rcy+h/2};
    for (const auto v:*g.model_box) if (!std::isfinite(v)) throw std::runtime_error("non-finite transformed model geometry");
    const auto turn=xyz(clause,"rotate",{0,0,0});
    if (turn[0]!=0||turn[1]!=0) g.tilted=true;
    else for (const auto& p:model_points(model_text,wrl)) {
        if (p[2]*unit*scale[2]+off[2]>=-pin_depth) continue;
        const double x=p[0]*unit*scale[0],y=p[1]*unit*scale[1];
        g.pins.emplace_back(off[0]+x*std::cos(th)+y*std::sin(th),-(off[1]-x*std::sin(th)+y*std::cos(th)));
    }
    return g;
}
}
Model3dGeometry measure_model3d(const std::string& footprint,const std::string& clause,const std::string& model_text,const std::string& extension) {
    std::array<double,3> off{};
    Model3dGeometry g=place(footprint,clause,model_text,extension,off);
    judge(g,footprint,off);
    return g;
}
Model3dGeometry measure_models3d(const std::string& footprint,const std::vector<Model3dSource>& models) {
    if (models.empty()) throw std::invalid_argument("model3d: no model to measure");
    std::array<double,3> first{};
    Model3dGeometry g=place(footprint,models.front().clause,models.front().text,models.front().extension,first);
    for (std::size_t i=1;i<models.size();++i) {
        std::array<double,3> off{};
        const Model3dGeometry next=place(footprint,models[i].clause,models[i].text,models[i].extension,off);
        if (!next.model_box) { g.model_xy.reset(); g.model_box.reset(); break; }
        if (!g.model_box) break;
        auto& box=*g.model_box; const auto& more=*next.model_box;
        box={std::min(box[0],more[0]),std::min(box[1],more[1]),std::max(box[2],more[2]),std::max(box[3],more[3])};
        g.model_xy=Pair{box[2]-box[0],box[3]-box[1]};
        g.tilted=g.tilted||next.tilted;
        g.pins.insert(g.pins.end(),next.pins.begin(),next.pins.end());
    }
    judge(g,footprint,first);
    return g;
}
std::string Model3dResult::line() const {
    std::string s="3D MODELS: "+std::to_string(covered)+"/"+std::to_string(total)+" footprints";
    if (!unmatched.empty()) s+="; "+std::to_string(unmatched.size())+" unmatched: ["+keys(unmatched)+"]";
    for (const auto& entry:std::vector<std::pair<std::string,const std::map<std::string,std::string>*>>{{"MISFIT",&misfit},{"MISPLACED",&misplaced},{"UNSEATED",&unseated},{"INVALID",&invalid}})
        if (!entry.second->empty()) s+="; "+std::to_string(entry.second->size())+" "+entry.first+": ["+keys(*entry.second)+"]";
    return s;
}
std::string Model3dResult::report() const {
    std::string out="3D model coverage gate (custom footprints reference a stock KiCad 3D model that EXISTS on disk)\n"+std::string(72,'=')+"\nSTATUS: SOFT — gaps are reported, never fail the board (some bespoke parts have no faithful stock body)\n"+std::to_string(covered)+"/"+std::to_string(total)+" custom footprints have a resolving 3D model";
    auto section=[&](const auto& m,const std::string& name,const std::string& suffix) {
        if (m.empty()) return;
        out+="\n\n"+name+" ("+std::to_string(m.size())+")"+suffix;
        for (const auto& [k,v]:m) out+="\n  "+k+": "+v;
    };
    section(unmatched,"UNMATCHED"," — no model (a wrong body is worse than none):");
    if (unmatched.empty()) out+="\nunmatched: none — every custom footprint has a model";
    section(misfit,"MISFIT"," — model resolves but does NOT match the footprint body (LAW):");
    section(misplaced,"MISPLACED"," — HARD: model body planted off its pads (offset bug, LAW 5/6):");
    section(unseated,"UNSEATED"," — HARD: model pins do not pass through the footprint's drilled pads:");
    if (!tilted.empty()) { out+="\n\nPINS NOT CHECKED, model tilted about X or Y ("+std::to_string(tilted.size())+"):"; for (const auto& m:tilted) out+="\n  "+m; }
    section(broken,"BROKEN"," — (model ...) path does not resolve to a file on disk:");
    if (!missing.empty()) { out+="\n\nMISSING (model ...) clause ("+std::to_string(missing.size())+"):"; auto v=missing; std::sort(v.begin(),v.end()); for (const auto& m:v) out+="\n  "+m; }
    section(invalid,"INVALID"," — HARD: model geometry cannot be measured:");
    return out;
}
fs::path default_model3d_directory() {
    for (const char* name:{"KICAD10_3DMODEL_DIR","KISYS3DMOD"}) if (const auto v=std::getenv(name);v&&*v) return v;
    return "/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels";
}
std::optional<fs::path> resolve_model3d_path(const std::string& raw,const fs::path& md,const fs::path& root) {
    using namespace render_models_detail;
    auto s=trim(raw); replace(s,"${KICAD10_3DMODEL_DIR}",md.string()); replace(s,"${KISYS3DMOD}",md.string()); replace(s,"${KIPRJMOD}",root.string());
    if (s.find('$')!=s.npos || !fs::path(s).is_absolute()) return std::nullopt;
    return fs::path(s);
}
Model3dResult check_model3d(const fs::path& parts,const fs::path& root,const fs::path& md) {
    using namespace render_models_detail;
    if (!fs::is_directory(parts)) throw std::runtime_error("model3d parts directory not found: "+parts.string());
    std::vector<fs::path> mods;
    for (const auto& dir:fs::directory_iterator(parts)) if (dir.is_directory())
        for (const auto& file:fs::directory_iterator(dir.path())) if (file.path().extension()==".kicad_mod"&&file.is_regular_file()) mods.push_back(file.path());
    if (mods.empty()) throw std::runtime_error("model3d footprint inventory is empty: "+parts.string());
    std::sort(mods.begin(),mods.end()); Model3dResult r;
    static const std::regex model(R"rx(\(model\s+"([^"]*)")rx");
    for (const auto& mod:mods) {
        const auto mpn=mod.parent_path().filename().string(),text=read(mod); ++r.total; std::smatch m;
        if (!std::regex_search(text,m,model)) { r.missing.push_back(mpn); r.unmatched[mpn]="no (model ...) clause"; continue; }
        const auto raw=m[1].str(); const auto path=resolve_model3d_path(raw,md,root);
        if (!path || !fs::is_regular_file(*path)) { r.broken[mpn]=raw; r.unmatched[mpn]="model path does not resolve: "+raw; continue; }
        ++r.covered;
        std::vector<Model3dSource> sources{{text.substr(static_cast<std::size_t>(m.position()+m.length()),500),{},{}}};
        std::vector<fs::path> files{*path};
        for (auto rest=m.suffix().first;std::regex_search(rest,text.cend(),m,model);rest=m.suffix().first) {
            const auto more=resolve_model3d_path(m[1].str(),md,root);
            if (!more || !fs::is_regular_file(*more)) { r.broken[mpn]=m[1].str(); continue; }
            sources.push_back({std::string(m.suffix().first,std::min(m.suffix().first+500,text.cend())),{},{}});
            files.push_back(*more);
        }
        try {
            for (std::size_t i=0;i<sources.size();++i) { sources[i].text=read(files[i]); sources[i].extension=files[i].extension().string(); }
            const auto g=measure_models3d(text,sources);
            if (!g.model_xy) r.invalid[mpn]="no finite STEP/WRL coordinate envelope";
            if (g.misfit) r.misfit[mpn]=*g.misfit;
            if (g.misplaced) r.misplaced[mpn]=*g.misplaced;
            if (g.unseated) r.unseated[mpn]=*g.unseated;
            if (g.tilted) r.tilted.push_back(mpn);
        } catch (const std::exception& e) { r.invalid[mpn]=e.what(); }
    }
    r.ok=r.broken.empty()&&r.missing.empty()&&r.misplaced.empty()&&r.unseated.empty()&&r.invalid.empty(); return r;
}
Model3dResult run_model3d(const fs::path& parts,const fs::path& root,const fs::path& reports,const fs::path& md) {
    auto r=check_model3d(parts,root,md); render_models_detail::write(reports/"model3d.txt",r.report()+"\n"); return r;
}
}
