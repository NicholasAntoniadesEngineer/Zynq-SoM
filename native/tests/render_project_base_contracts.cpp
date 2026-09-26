// Genuine KiCad rendering/STEP import from a copied PCB, without copying models.
#include "schgen/native_render.hpp"
#include "render_models_internal.hpp"
#include <iostream>
#include <png.h>
#include <unistd.h>

namespace fs=std::filesystem;
using namespace schgen;
using namespace schgen::render_models_detail;
namespace {
std::size_t checks=0;
void require(bool value,const std::string& why) {
    ++checks; if (!value) throw std::runtime_error(why);
}
template<class F> void rejects(F f,const std::string& text) {
    bool caught=false;
    try { f(); } catch (const std::exception& e) { caught=std::string(e.what()).find(text)!=std::string::npos; }
    require(caught,"expected rejection: "+text);
}
struct Scratch {
    fs::path path;
    Scratch() {
        auto pattern=(fs::temp_directory_path()/"schgen-render-project-base-XXXXXX").string();
        require(::mkdtemp(pattern.data())!=nullptr,"private scratch"); path=pattern;
    }
    ~Scratch() { std::error_code error; fs::remove_all(path,error); }
};
std::vector<double> tiles(const fs::path& path) {
    png_image image{}; image.version=PNG_IMAGE_VERSION;
    require(png_image_begin_read_from_file(&image,path.c_str())!=0,"real PNG header");
    image.format=PNG_FORMAT_RGB; const auto w=image.width,h=image.height;
    std::vector<png_byte> rgb(PNG_IMAGE_SIZE(image));
    const bool decoded=png_image_finish_read(&image,nullptr,rgb.data(),0,nullptr)!=0;
    png_image_free(&image); require(decoded&&w>0&&h>0,"real PNG pixels");
    std::vector<double> out;
    for (unsigned ty=0;ty<12;++ty) for (unsigned tx=0;tx<16;++tx) for (unsigned c=0;c<3;++c) {
        double sum=0; std::size_t count=0;
        for (unsigned y=ty*h/12;y<(ty+1)*h/12;++y) for (unsigned x=tx*w/16;x<(tx+1)*w/16;++x) {
            sum+=rgb[(static_cast<std::size_t>(y)*w+x)*3+c]; ++count;
        }
        require(count>0,"nonempty image tile"); out.push_back(sum/count);
    }
    return out;
}
void same_images(const Render3dResult& expected,const Render3dResult& actual) {
    require(expected.ok()&&actual.ok(),"all eight real KiCad views required");
    for (std::size_t i=0;i<8;++i) {
        require(expected.views[i].view==actual.views[i].view,"view order preserved");
        require(expected.views[i].width==actual.views[i].width&&expected.views[i].height==actual.views[i].height,"raster dimensions preserved");
        const auto a=tiles(expected.written[i]),b=tiles(actual.written[i]);
        double total=0,worst=0;
        for (std::size_t j=0;j<a.size();++j) { const auto delta=std::abs(a[j]-b[j]); total+=delta; worst=std::max(worst,delta); }
        require(total/a.size()<2&&worst<20,"genuine model raster changed relative to absolute-source control");
    }
}
}
int main(int argc,char** argv) {
    try {
        require(argc==2,"usage: render_project_base_contracts REPO");
        const auto repo=fs::canonical(argv[1]); Scratch scratch;
        const auto model=repo/"parts/AO3400A/AO3400A.wrl",step=repo/"parts/AO3400A/AO3400A.step";
        const auto model_before=read(model),step_before=read(step);
        const auto board_template=read(repo/"native/tests/data/render_models/asset_complete.kicad_pcb");
        auto absolute=board_template; replace(absolute,"@MODEL@",model.string());
        const auto control=scratch.path/"control/fixture.kicad_pcb"; write(control,absolute);
        Render3dOptions options; options.width=240; options.height=180; options.quality="basic";
        const auto baseline=render_board_3d(control,scratch.path/"control/renders",options);
        require(baseline.ok(),"default absolute-model control renders eight views");
        for (const auto& reference:{std::string("${KIPRJMOD}/../parts/AO3400A/AO3400A.wrl"),std::string("../parts/AO3400A/AO3400A.wrl")}) {
            const auto name=reference.front()=='$'?"variable":"relative";
            const auto pcb=scratch.path/name/"fixture.kicad_pcb";
            auto board=board_template; replace(board,"@MODEL@",reference); write(pcb,board);
            auto project=pcb; project.replace_extension(".kicad_pro"); const std::string project_bytes="{\"meta\":{\"version\":1}}\n"; write(project,project_bytes);
            const auto output=scratch.path/name/"renders",old=output/"3d_top.png"; write(old,"old output");
            rejects([&]{render_board_3d(pcb,output,options);},"required 3D asset missing");
            require(read(old)=="old output","default failure cannot credit/overwrite stale PNG");
            auto source_options=options; source_options.source_project_directory=repo/"carrier";
            const auto result=render_board_3d(pcb,output,source_options); same_images(baseline,result);
            const auto exported=scratch.path/name/"assembly.step"; export_board_step(pcb,exported,source_options);
            require(read(exported).size()>1000000,"actual AO3400A STEP component exported, not board-only geometry");
            source_options.source_project_directory=scratch.path;
            rejects([&]{render_board_3d(pcb,output,source_options);},"required 3D asset missing");
            rejects([&]{export_board_step(pcb,exported,source_options);},"required 3D asset missing");
            source_options.source_project_directory=scratch.path/"absent";
            rejects([&]{render_board_3d(pcb,output,source_options);},"source project directory not found");
            require(read(pcb)==board&&read(project)==project_bytes,"copied PCB and project bytes unchanged");
            require(!fs::exists(scratch.path/"parts"),"no model copying or fallback asset tree");
        }
        require(read(model)==model_before&&read(step)==step_before,"genuine source WRL/STEP untouched");
        std::cout<<checks<<" external-project render contracts passed; 24 real views, two full STEP exports\n";
    } catch (const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
}
