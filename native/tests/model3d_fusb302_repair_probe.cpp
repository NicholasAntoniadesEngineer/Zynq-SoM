// Read-only hardware provenance and isolated native-render probe. This does not
// repair the repo PCB, its authoring footprint, or the installed KiCad library.
#include "schgen/model3d.hpp"
#include "schgen/native_render.hpp"
#include "schgen/process.hpp"
#include "schgen/sexpr.hpp"
#include "schgen/pcb_emit.hpp"
#include "render_models_internal.hpp"
#include <iostream>
#include <regex>
#include <png.h>

namespace fs=std::filesystem;
using namespace schgen;
using namespace schgen::render_models_detail;
namespace {
std::string atom(const Sexpr& n) {
    if (const auto p=std::get_if<std::string>(&n.v)) return *p;
    if (const auto p=std::get_if<Sexpr::Sym>(&n.v)) return p->name;
    return {};
}
bool tag(const Sexpr& n,const std::string& s) { const auto p=std::get_if<SexprList>(&n.v); return p&&!p->empty()&&atom(p->front())==s; }
void require(bool condition,const std::string& why) { if (!condition) throw std::runtime_error(why); }
std::map<int,std::pair<double,double>> pad_positions(const Sexpr& n) {
    std::map<int,std::pair<double,double>> pads;
    for (const auto& item:std::get<SexprList>(n.v)) if (tag(item,"pad")) {
        const auto& row=std::get<SexprList>(item.v); const auto name=atom(row.at(1)); if (name.empty()) continue;
        for (const auto& child:row) if (tag(child,"at")) { const auto& xy=std::get<SexprList>(child.v); pads[std::stoi(name)]={std::get<double>(xy.at(1).v),std::get<double>(xy.at(2).v)}; }
    }
    return pads;
}
Sexpr with_model(Sexpr doc,const fs::path& model,int rotation) {
    auto& root=std::get<SexprList>(doc.v);
    for (auto& item:root) if (tag(item,"model")) {
        auto& row=std::get<SexprList>(item.v); row.at(1).v=model.string();
        for (auto& child:row) if (tag(child,"rotate")) {
            auto& values=std::get<SexprList>(std::get<SexprList>(child.v).at(1).v); values.at(3).v=static_cast<double>(rotation);
        }
    }
    root.push_back(sexpr_loads("(at 3 3)")); return doc;
}
std::pair<double,double> pin1_marker(const fs::path& image) {
    png_image im{}; im.version=PNG_IMAGE_VERSION;
    require(png_image_begin_read_from_file(&im,image.c_str())!=0,"orientation PNG readable");
    im.format=PNG_FORMAT_RGB; const auto width=im.width,height=im.height; std::vector<png_byte> rgb(PNG_IMAGE_SIZE(im));
    const bool decoded=png_image_finish_read(&im,nullptr,rgb.data(),0,nullptr)!=0; png_image_free(&im); require(decoded,"orientation PNG decoded");
    double sx=0,sy=0; std::size_t count=0;
    for (unsigned y=height*26/100;y<height*74/100;++y) for (unsigned x=width*26/100;x<width*74/100;++x) {
        const auto i=static_cast<std::size_t>((y*width+x)*3);
        if (rgb[i]>240&&rgb[i+1]>240&&rgb[i+2]>240) { sx+=x; sy+=y; ++count; }
    }
    require(count>100,"actual pin-1 body marker detected"); return {sx/count/width,sy/count/height};
}
}
int main(int argc,char** argv) {
    try {
        if (argc!=3) throw std::runtime_error("usage: probe REPO ISOLATED_OUTPUT");
        const fs::path repo=argv[1],output=argv[2]; fs::create_directories(output);
        const auto part=repo/"parts/FUSB302BMPX",wrl=part/"FUSB302BMPX.wrl",step=part/"FUSB302BMPX.step";
        const auto stock_path=fs::path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/Package_DFN_QFN.pretty/WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm.kicad_mod");
        const auto stock=sexpr_loads(read(stock_path)),custom=sexpr_loads(read(part/"FUSB302BMPX.kicad_mod"));
        const auto stock_pads=pad_positions(stock),custom_pads=pad_positions(custom);
        require(stock_pads.size()==15&&custom_pads.size()==15,"actual 14 leads plus EP");
        for (int n=1;n<=14;++n) {
            const auto a=custom_pads.at(n),b=stock_pads.at(n);
            const double dx=-a.second-b.first,dy=a.first-b.second;
            require(std::hypot(dx,dy)<0.086,"numbered pad rotation mismatch");
        }
        require(stock_pads.at(15)==std::make_pair(0.0,0.0),"stock EP centered");
        const auto geometry=measure_model3d(read(stock_path),"",read(wrl),".wrl");
        require(geometry.model_xy&&!geometry.misfit&&!geometry.misplaced,"genuine WRL envelope fits actual stock footprint");
        std::cout<<"FUSB302BMPX WRL envelope "<<geometry.model_xy->first<<'x'<<geometry.model_xy->second<<" mm; 15 numbered pads verified\n";
        // Read genuine SolidWorks STEP coordinates with their legal whitespace;
        // this is inspection only, not a replacement STEP parser in production.
        const auto step_bytes=read(step); static const std::regex point(R"(CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*([-+\d.eE]+)\s*,\s*([-+\d.eE]+)\s*,\s*([-+\d.eE]+)\s*\))");
        std::array<double,3> lo{1e100,1e100,1e100},hi{-1e100,-1e100,-1e100}; std::size_t count=0;
        for (std::sregex_iterator i(step_bytes.begin(),step_bytes.end(),point),end;i!=end;++i) { ++count; for (int n=0;n<3;++n) { const double value=number((*i)[n+1]); lo[n]=std::min(lo[n],value); hi[n]=std::max(hi[n],value); } }
        require(count>100,"STEP has genuine coordinate geometry");
        std::cout<<"STEP coordinate envelope (includes control points): ["<<lo[0]<<','<<lo[1]<<','<<lo[2]<<"]..["<<hi[0]<<','<<hi[1]<<','<<hi[2]<<"], "<<count<<" points\n";
        for (int rotation:{0,90,270}) {
            const auto directory=output/std::to_string(rotation); fs::create_directories(directory);
            const std::string board="(kicad_pcb (version 20241229) (generator \"schgen-native-probe\") (general (thickness 1.6)) (paper \"A4\") (layers (0 \"F.Cu\" signal) (31 \"B.Cu\" signal) (44 \"Edge.Cuts\" user)) (setup (pad_to_mask_clearance 0)) (gr_rect (start 0 0) (end 6 6) (stroke (width 0.05) (type default)) (fill none) (layer \"Edge.Cuts\")) "+sexpr_dumps(with_model(stock,wrl,rotation))+"\n)\n";
            const auto pcb=directory/"FUSB302B.kicad_pcb"; write(pcb,board);
            const auto r=run_process({"kicad-cli","pcb","render","--quality","basic","--background","opaque","--width","800","--height","800","--side","top","--zoom","1.3","-o",(directory/"top.png").string(),pcb.string()},std::chrono::minutes(2));
            require(r.exit_code==0&&fs::is_regular_file(directory/"top.png"),"native orientation render failed: "+r.stderr_text);
            const auto marker=pin1_marker(directory/"top.png");
            std::cout<<"Native KiCad model Z="<<rotation<<" pin-1 marker normalized XY "<<marker.first<<','<<marker.second<<'\n';
            require((marker.first<0.4&&marker.second<0.4)==(rotation==90),"only Z=90 aligns marker with stock pad 1 at upper-left");
            if (rotation==90) {
                export_board_step(pcb,directory/"FUSB302B.step"); const auto generated=read(directory/"FUSB302B.step"); require(generated.find("MLP-14_L2.5-W2.5-H0.8-P0.50")!=generated.npos,"real STEP substitute product retained"); std::cout<<"Real STEP import/export with repository substitute: "<<generated.size()<<" bytes\n";
                auto step_board=board; replace(step_board,wrl.string(),step.string()); const auto step_pcb=directory/"direct-step.kicad_pcb"; write(step_pcb,step_board);
                const auto sr=run_process({"kicad-cli","pcb","render","--quality","basic","--background","opaque","--width","800","--height","800","--side","top","--zoom","1.3","-o",(directory/"direct-step.png").string(),step_pcb.string()},std::chrono::minutes(2));
                require(sr.exit_code==0&&fs::is_regular_file(directory/"direct-step.png"),"genuine STEP native importer renders directly");
            }
        }
        const auto carrier=repo/"carrier/Zynq_Carrier.kicad_pcb"; const auto original=read(carrier); auto repaired=original;
        const std::string missing="${KICAD10_3DMODEL_DIR}/Package_DFN_QFN.3dshapes/WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm.step";
        const auto position=repaired.find(missing); require(position!=repaired.npos&&repaired.find(missing,position+1)==repaired.npos,"one precise Carrier model target");
        repaired.replace(position,missing.size(),wrl.string());
        const auto rotate=repaired.find("(rotate",position),xyz=repaired.find("(xyz 0 0 0)",rotate);
        require(rotate!=repaired.npos&&xyz!=repaired.npos&&xyz-rotate<100,"existing zero model rotation resolved");
        repaired.replace(xyz,std::string("(xyz 0 0 0)").size(),"(xyz 0 0 90)");
        // Only for the isolated input's location: keep every other genuine
        // relative repository model resolving to its original source directory.
        replace(repaired,"${KIPRJMOD}",carrier.parent_path().string());
        const auto scratch_board=output/"carrier-repair/Zynq_Carrier.kicad_pcb"; write(scratch_board,repaired);
        write(output/"carrier-repair/Zynq_Carrier.kicad_pro",read(repo/"carrier/Zynq_Carrier.kicad_pro"));
        Render3dOptions settings; settings.quality="basic"; settings.width=320; settings.height=240;
        const auto result=render_board_3d(scratch_board,output/"carrier-repair/renders",settings);
        for (const auto& failure:result.failures) std::cerr<<failure.view<<": "<<failure.diagnostic<<'\n';
        require(result.ok(),"Carrier scratch repair must render all eight actual native views");
        require(read(carrier)==original,"original Carrier PCB unchanged");
        std::cout<<"Carrier scratch model-only repair: "<<result.written.size()<<"/8 genuine native views complete; source PCB unchanged\n";
        std::cout<<"WRL sha256 "<<pcb_sha256(read(wrl))<<"\nSTEP sha256 "<<pcb_sha256(read(step))<<'\n';
        std::cout<<"Read-only FUSB302B provenance/orientation probe PASS: stock footprint requires model Z=90 degrees\n";
    } catch (const std::exception& e) { std::cerr<<"FAIL: "<<e.what()<<'\n'; return 1; }
}
