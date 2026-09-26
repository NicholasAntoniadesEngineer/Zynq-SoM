#include "schgen/native_render.hpp"
#include "schgen/model3d.hpp"
#include "schgen/process.hpp"
#include "render_models_internal.hpp"
#include <poppler/cpp/poppler-document.h>
#include <poppler/cpp/poppler-page.h>
#include <poppler/cpp/poppler-page-renderer.h>
#include <png.h>
#include <array>
#include <cerrno>
#include <cstring>
#include <cstdlib>
#include <memory>
#include <regex>
#include <set>
#include <unistd.h>

namespace schgen {
namespace fs=std::filesystem;
namespace {
using namespace render_models_detail;
struct Temp {
    fs::path path;
    Temp() {
        std::string pattern=(fs::temp_directory_path()/"schgen-native-render-XXXXXX").string();
        std::vector<char> b(pattern.begin(),pattern.end()); b.push_back('\0');
        const auto p=::mkdtemp(b.data()); if (!p) throw RenderError("cannot create render staging: "+std::string(std::strerror(errno))); path=p;
    }
    Temp(const Temp&)=delete; Temp& operator=(const Temp&)=delete;
    ~Temp() { std::error_code ec; fs::remove_all(path,ec); }
};
void dimensions(int w,int h) {
    if (w<=0||h<=0||w>32768||h>32768||static_cast<std::uint64_t>(w)*static_cast<std::uint64_t>(h)>100000000)
        throw RenderError("render dimensions exceed safe pixel limit");
}
std::pair<int,int> validate_png(const fs::path& path,int width,int height,bool exact=true) {
    png_image im{}; im.version=PNG_IMAGE_VERSION;
    if (!png_image_begin_read_from_file(&im,path.c_str())) { const std::string error=im.message; png_image_free(&im); throw RenderError("invalid rendered PNG: "+error); }
    struct Free { png_image& im; ~Free(){png_image_free(&im);} } guard{im};
    if (im.width==0||im.height==0||im.width>static_cast<unsigned>(width)||im.height>static_cast<unsigned>(height)||
        (exact&&(im.width!=static_cast<unsigned>(width)||im.height!=static_cast<unsigned>(height)))) throw RenderError("rendered PNG dimensions exceed request");
    im.format=PNG_FORMAT_RGBA; std::vector<png_byte> pixels(PNG_IMAGE_SIZE(im));
    if (!png_image_finish_read(&im,nullptr,pixels.data(),0,nullptr)) throw RenderError("invalid rendered PNG pixels: "+std::string(im.message));
    return {static_cast<int>(im.width),static_cast<int>(im.height)};
}
std::string cli(const NativeRenderOptions& o) {
    if (o.timeout.count()<=0) throw RenderError("render timeout must be positive");
    const auto exe=find_executable(o.kicad_cli); if (!exe) throw RenderError("kicad-cli not found; native KiCad 9+ is required"); return exe->string();
}
int major(const std::string& exe,const NativeRenderOptions& o) {
    const auto r=run_process({exe,"version"},std::min(o.timeout,std::chrono::milliseconds(20000))); std::smatch m;
    if (r.exit_code!=0||!std::regex_search(r.stdout_text,m,std::regex(R"((\d+)\.)"))) throw RenderError("cannot determine native KiCad version: "+r.stderr_text);
    const int v=std::stoi(m[1]); if (v<9) throw RenderError("native KiCad 9+ is required"); return v;
}
std::string diagnostic(const ProcessResult& r) {
    const auto& s=r.stderr_text.empty()?r.stdout_text:r.stderr_text;
    return "exit="+std::to_string(r.exit_code)+": "+s.substr(s.size()>200?s.size()-200:0);
}
fs::path stage_board(const fs::path& input,const fs::path& dir) {
    if (!fs::is_regular_file(input)) throw RenderError("PCB not found: "+input.string());
    const auto source=fs::absolute(input); const auto copy=dir/source.filename();
    auto text=read(source);
    // Plain relative model names also resolve against the original project,
    // not against staging. Variable-bearing paths are resolved by KiCad -D.
    static const std::regex model(R"rx(\(model\s+"([^"]*)")rx");
    std::string rewritten; std::size_t last=0;
    for (std::sregex_iterator it(text.begin(),text.end(),model),end;it!=end;++it) {
        const auto& m=*it; const auto raw=m[1].str(); const auto pos=static_cast<std::size_t>(m.position(1));
        rewritten+=text.substr(last,pos-last);
        if (!raw.empty()&&raw.find('$')==raw.npos&&!fs::path(raw).is_absolute()) {
            auto absolute=(source.parent_path()/raw).lexically_normal().string(); replace(absolute,"\\","\\\\"); replace(absolute,"\"","\\\""); rewritten+=absolute;
        } else rewritten+=raw;
        last=pos+raw.size();
    }
    rewritten+=text.substr(last); write(copy,rewritten);
    auto pro=source; pro.replace_extension(".kicad_pro");
    if (fs::is_regular_file(pro)) write(dir/pro.filename(),read(pro));
    return copy;
}
fs::path model_directory(const Render3dOptions& o) {
    const auto md=o.model_directory?o.model_directory:find_render_model_directory();
    if (!md || !fs::is_directory(*md)) throw RenderError("KiCad 3D-model library not found; supply an installed model_directory");
    return fs::absolute(*md);
}
void required_models(const fs::path& pcb,const fs::path& md,int version,bool step) {
    const auto text=read(pcb); static const std::regex model(R"rx(\(model\s+"([^"]*)")rx");
    std::vector<std::string> problems; std::set<fs::path> checked;
    for (std::sregex_iterator it(text.begin(),text.end(),model),end;it!=end;++it) {
        auto raw=(*it)[1].str(); replace(raw,"${KIPRJMOD}",fs::canonical(pcb).parent_path().string());
        replace(raw,"${KICAD"+std::to_string(version)+"_3DMODEL_DIR}",md.string()); replace(raw,"${KISYS3DMOD}",md.string());
        if (raw.find('$')!=raw.npos) { problems.push_back("unresolved required 3D asset variable: "+raw); continue; }
        auto p=fs::path(raw); if (!p.is_absolute()) p=fs::absolute(pcb).parent_path()/p;
        if (!checked.insert(p.lexically_normal()).second) continue;
        if (!fs::is_regular_file(p)||fs::file_size(p)==0) { problems.push_back("required 3D asset missing or empty: "+p.string()); continue; }
        auto ext=p.extension().string(); std::transform(ext.begin(),ext.end(),ext.begin(),[](unsigned char c){return static_cast<char>(std::tolower(c));});
        if (ext==".wrl"||ext==".step"||ext==".stp") {
            try {
                const auto contents=read(p);
                if (!measure_model3d("","",contents,ext).model_xy) problems.push_back("required 3D asset has no measurable coordinates: "+p.string());
            } catch (const std::exception& e) { problems.push_back("required 3D asset cannot be measured: "+p.string()+": "+e.what()); }
        }
        if (step&&ext==".wrl") {
            auto substitute=p; substitute.replace_extension(".step");
            if (!fs::is_regular_file(substitute)) { substitute=p; substitute.replace_extension(".stp"); }
            if (!fs::is_regular_file(substitute)||fs::file_size(substitute)==0) problems.push_back("required STEP substitute missing: "+p.string());
        }
    }
    std::sort(problems.begin(),problems.end()); problems.erase(std::unique(problems.begin(),problems.end()),problems.end());
    if (!problems.empty()) throw RenderError(join(problems,"\n"));
}
std::vector<std::string> variables(const fs::path& pcb,const fs::path& md,int version) {
    return {"-D","KICAD"+std::to_string(version)+"_3DMODEL_DIR="+md.string(),"-D","KIPRJMOD="+fs::canonical(pcb).parent_path().string()};
}
}
std::pair<double,double> PageRaster::mm_to_px(double x,double y) const {
    if (!(page_w_mm>0&&page_h_mm>0)) throw RenderError("page physical dimensions must be positive");
    return {x*(width_px/page_w_mm),y*(height_px/page_h_mm)};
}
PageRaster render_pdf_to_png(const fs::path& pdf,const fs::path& png,int dpi) {
    if (dpi<1||dpi>2400) throw RenderError("render DPI must be in [1,2400]");
    if (!fs::is_regular_file(pdf)) throw RenderError("PDF not found: "+pdf.string());
    if (!poppler::page_renderer::can_render()) throw RenderError("installed Poppler has no native raster backend");
    const std::unique_ptr<poppler::document> doc(poppler::document::load_from_file(pdf.string()));
    if (!doc||doc->is_locked()||doc->pages()<1) throw RenderError("cannot open first PDF page: "+pdf.string());
    const std::unique_ptr<poppler::page> page(doc->create_page(0)); if (!page) throw RenderError("cannot load first PDF page");
    const auto rect=page->page_rect(); double w=rect.width(),h=rect.height();
    if (page->orientation()==poppler::page::landscape||page->orientation()==poppler::page::seascape) std::swap(w,h);
    if (!std::isfinite(w)||!std::isfinite(h)||w<=0||h<=0||w*dpi/72>32768||h*dpi/72>32768) throw RenderError("invalid PDF page dimensions");
    const int width=static_cast<int>(std::ceil(w*dpi/72)),height=static_cast<int>(std::ceil(h*dpi/72)); dimensions(width,height);
    poppler::page_renderer renderer; renderer.set_image_format(poppler::image::format_rgb24); renderer.set_paper_color(0xffffffff);
    renderer.set_render_hints(poppler::page_renderer::antialiasing|poppler::page_renderer::text_antialiasing);
    const auto im=renderer.render_page(page.get(),dpi,dpi,0,0,width,height);
    if (!im.is_valid()||im.width()!=width||im.height()!=height) throw RenderError("Poppler native page rendering failed");
    Temp temp; const auto output=temp.path/"page.png";
    if (!im.save(output.string(),"png",dpi)) throw RenderError("Poppler PNG encoding failed");
    validate_png(output,width,height); write(png,read(output));
    return {png,width,height,w/72*25.4,h/72*25.4,static_cast<double>(dpi)};
}
PageRaster render_sheet_to_png(const fs::path& schematic,const fs::path& png,int dpi,const NativeRenderOptions& o) {
    if (dpi<1||dpi>2400) throw RenderError("render DPI must be in [1,2400]");
    if (!fs::is_regular_file(schematic)) throw RenderError("schematic not found: "+schematic.string());
    const auto exe=cli(o); Temp temp; const auto pdf=temp.path/(schematic.stem().string()+".pdf");
    const auto r=run_process({exe,"sch","export","pdf","--output",pdf.string(),fs::absolute(schematic).string()},o.timeout);
    if (r.exit_code!=0||!fs::is_regular_file(pdf)) throw RenderError("kicad-cli sch export pdf failed: "+diagnostic(r));
    return render_pdf_to_png(pdf,png,dpi);
}
std::optional<fs::path> find_render_model_directory() {
    for (const auto* p:{"/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels","/usr/share/kicad/3dmodels","/usr/local/share/kicad/3dmodels"}) if (fs::is_directory(p)) return fs::path(p);
    return std::nullopt;
}
std::string Render3dResult::summary() const {
    std::vector<std::string> paths; for (const auto& p:written) paths.push_back(p.string());
    return written.empty()?std::string{}:"3D RENDERS: "+std::to_string(written.size())+" view(s) -> "+render_models_detail::join(paths,", ")+" (VISUAL-verify: LAW 1)";
}
Render3dResult render_board_3d(const fs::path& pcb,const fs::path& output,const Render3dOptions& o) {
    dimensions(o.width,o.height);
    if (o.quality!="high"&&o.quality!="basic"&&o.quality!="user"&&o.quality!="job_settings") throw RenderError("invalid KiCad render quality");
    const auto exe=cli(o); const auto md=model_directory(o); const int version=major(exe,o); required_models(pcb,md,version,false);
    Temp temp; const auto input=stage_board(pcb,temp.path); const auto vars=variables(pcb,md,version);
    Render3dResult result;
    const std::vector<std::pair<std::string,std::vector<std::string>>> views{
        {"top",{"--side","top"}},{"bottom",{"--side","bottom"}},{"left",{"--side","left"}},{"right",{"--side","right"}},
        {"front",{"--side","front"}},{"back",{"--side","back"}},{"persp",{"--perspective"}},{"persp_rear",{"--perspective","--rotate","0,0,180"}}};
    for (const auto& [name,args]:views) {
        const auto png=temp.path/("3d_"+name+".png"); std::vector<std::string> command{exe,"pcb","render"}; command.insert(command.end(),vars.begin(),vars.end());
        const std::vector<std::string> common{"--quality",o.quality,"--background","opaque","-w",std::to_string(o.width),"-h",std::to_string(o.height)};
        command.insert(command.end(),common.begin(),common.end()); command.insert(command.end(),args.begin(),args.end()); command.insert(command.end(),{"-o",png.string(),input.string()});
        try {
            const auto r=run_process(command,o.timeout);
            if (r.exit_code!=0||!fs::is_regular_file(png)) throw RenderError(diagnostic(r));
            const auto size=validate_png(png,o.width,o.height,false); const auto dest=output/png.filename(); write(dest,read(png)); result.written.push_back(dest); result.views.push_back({name,dest,size.first,size.second});
        } catch (const std::exception& e) { result.failures.push_back({name,e.what()}); }
    }
    return result;
}
void export_board_step(const fs::path& pcb,const fs::path& output,const Render3dOptions& o) {
    const auto exe=cli(o); const auto md=model_directory(o); const int version=major(exe,o); required_models(pcb,md,version,true); Temp temp;
    const auto input=stage_board(pcb,temp.path),step=temp.path/"board.step"; const auto vars=variables(pcb,md,version);
    std::vector<std::string> command{exe,"pcb","export","step"}; command.insert(command.end(),vars.begin(),vars.end());
    // KiCad's macOS writer attempts to retain output attributes. Provide the
    // private destination first so a new export does not emit an OS error.
    write(step,"");
    command.insert(command.end(),{"--force","--subst-models","-o",step.string(),input.string()}); const auto r=run_process(command,o.timeout);
    if (r.exit_code!=0||!fs::is_regular_file(step)) throw RenderError("KiCad STEP export failed: "+diagnostic(r));
    const auto text=read(step);
    if (text.find("ISO-10303-21;")==text.npos||text.find("END-ISO-10303-21;")==text.npos||text.find("CARTESIAN_POINT")==text.npos) throw RenderError("KiCad STEP output is incomplete");
    // KiCad can produce a board while reporting missing component models.
    std::string log=r.stdout_text+r.stderr_text; std::transform(log.begin(),log.end(),log.begin(),[](unsigned char c){return static_cast<char>(std::tolower(c));});
    if (log.find("error")!=log.npos||log.find("could not")!=log.npos||log.find("unable to")!=log.npos||log.find("not found")!=log.npos) throw RenderError("KiCad STEP model diagnostic: "+log);
    write(output,text);
}
}
