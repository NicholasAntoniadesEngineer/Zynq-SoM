#include "schgen/model3d.hpp"
#include "schgen/native_render.hpp"
#include "schgen/json.hpp"
#include "schgen/pcb_emit.hpp"
#include "render_models_internal.hpp"
#include <png.h>
#include <cstdlib>
#include <iostream>
#include <set>
#include <unistd.h>

namespace fs=std::filesystem;
using namespace schgen;
using namespace schgen::render_models_detail;
namespace {
std::size_t assertions=0;
void require(bool value,const std::string& message) { ++assertions; if (!value) throw std::runtime_error(message); }
template<class F> void rejects(F f,const std::string& why) { bool caught=false; try { f(); } catch (const std::exception& e) { caught=true; require(std::string(e.what()).find(why)!=std::string::npos,"unexpected error: "+std::string(e.what())); } require(caught,"expected error: "+why); }
const JsonNode& field(const JsonNode& n,const std::string& key) { const auto p=object_field(n,key); if (!p) throw std::runtime_error("missing fixture "+key); return *p; }
std::string str(const JsonNode& n,const std::string& key) { return field(n,key).string_value; }
void optional_text(const std::optional<std::string>& value,const JsonNode& expected) { require(value.has_value()==(expected.kind!=JsonKind::Null),"optional diagnostic presence"); if (value) require(*value==expected.string_value,"diagnostic differs: "+*value+" expected: "+expected.string_value); }
void check_pair(const std::optional<std::pair<double,double>>& v,const JsonNode& n) { require(v.has_value()==(n.kind!=JsonKind::Null),"pair presence"); if (v) { require(v->first==n.array_value[0].number_value,"pair x exact"); require(v->second==n.array_value[1].number_value,"pair y exact"); } }
void check_box(const std::optional<Model3dBox>& v,const JsonNode& n) { require(v.has_value()==(n.kind!=JsonKind::Null),"box presence"); if (v) for (std::size_t i=0;i<4;++i) require((*v)[i]==n.array_value[i].number_value,"box coordinate exact"); }
std::string pixels(const fs::path& path) {
    png_image im{}; im.version=PNG_IMAGE_VERSION;
    require(png_image_begin_read_from_file(&im,path.c_str())!=0,"PNG readable");
    im.format=PNG_FORMAT_RGB; std::string data(PNG_IMAGE_SIZE(im),'\0');
    const bool ok=png_image_finish_read(&im,nullptr,data.data(),0,nullptr)!=0; png_image_free(&im); require(ok,"PNG decodable"); return data;
}
void compare_tiles(const std::string& rgb,const JsonNode& expected) {
    const int w=static_cast<int>(field(expected,"width").number_value),h=static_cast<int>(field(expected,"height").number_value);
    require(rgb.size()==static_cast<std::size_t>(w*h*3),"raster dimensions match independent capture");
    double error=0,max_error=0; std::size_t index=0;
    for (int ty=0;ty<12;++ty) for (int tx=0;tx<16;++tx) for (int c=0;c<3;++c) {
        double sum=0; int n=0;
        for (int y=ty*h/12;y<(ty+1)*h/12;++y) for (int x=tx*w/16;x<(tx+1)*w/16;++x) { sum+=static_cast<unsigned char>(rgb[static_cast<std::size_t>((y*w+x)*3+c)]); ++n; }
        const double difference=std::abs(sum/n-field(expected,"tiles").array_value[index++].number_value);
        error+=difference; max_error=std::max(max_error,difference);
    }
    require(error/index<2&&max_error<20,"native raster differs structurally from independent Python render: mean="+fixed(error/index,4)+", max="+fixed(max_error,4));
}
void pure(const JsonNode& fixture,const fs::path& repo,const fs::path& scratch) {
    for (const auto& c:field(fixture,"geometry").array_value) {
        const auto g=measure_model3d(str(c,"mod"),str(c,"clause"),str(c,"model"),str(c,"suffix"));
        check_pair(g.model_xy,field(c,"xy")); check_pair(g.fab_xy,field(c,"fab")); check_box(g.model_box,field(c,"box")); check_box(g.pad_box,field(c,"pads")); optional_text(g.misfit,field(c,"fit")); optional_text(g.misplaced,field(c,"placed"));
    }
    for (const auto& c:field(fixture,"obj").array_value) optional_text(model3d_obj_to_wrl(str(c,"input")),field(c,"output"));
    rejects([]{ model3d_obj_to_wrl("v nan 1 2"); },"invalid model3d number");
    rejects([]{ model3d_obj_to_wrl("v 0 0 0\nusemtl a\nf 2"); },"index out of range");
    const auto expected=field(fixture,"repository"); const auto r=check_model3d(repo/"parts",repo/"carrier");
    require(r.ok==field(field(expected,"fields"),"ok").bool_value,"repository gate verdict: "+r.report()); require(r.line()==str(expected,"line"),"repository line exact: "+r.line()); require(r.report()==str(expected,"report"),"repository report exact: "+r.report());
    const auto published=run_model3d(repo/"parts",repo/"carrier",scratch/"reports"); require(read(scratch/"reports/model3d.txt")==published.report()+"\n","publication exact");
    for (const auto& [p,sha]:field(fixture,"assets").object_value) require(pcb_sha256(read(repo/p))==sha.string_value,"hardware asset preserved: "+p);
    require(resolve_model3d_path(" ${KIPRJMOD}/body.wrl ","/md","/project")==fs::path("/project/body.wrl"),"project path resolution");
    require(resolve_model3d_path("${KISYS3DMOD}/body.wrl","/md","/project")==fs::path("/md/body.wrl"),"legacy variable resolution");
    require(!resolve_model3d_path("${UNKNOWN}/body.wrl","/md","/project"),"unresolved variable rejected"); require(!resolve_model3d_path("relative.wrl","/md","/project"),"relative path rejected");
    rejects([&]{check_model3d(scratch/"absent",repo);},"directory not found"); fs::create_directories(scratch/"empty"); rejects([&]{check_model3d(scratch/"empty",repo);},"inventory is empty");
    const auto part=scratch/"parts/P",mod=part/"P.kicad_mod",model=part/"body.wrl";
    const auto& c=field(fixture,"geometry").array_value.front(); const auto base=str(c,"mod");
    auto footprint=[&](const std::string& clause) { write(mod,base.substr(0,base.size()-1)+" (model \"${KIPRJMOD}/parts/P/body.wrl\" "+clause+"))"); };
    write(model,str(c,"model")); footprint(str(c,"clause")); require(check_model3d(scratch/"parts",scratch).ok,"valid synthetic gate");
    footprint("(offset (xyz -5.4 1.5 0))"); auto mutated=check_model3d(scratch/"parts",scratch); require(!mutated.ok&&mutated.misplaced.size()==1,"real offset mutation hard failure");
    footprint("(scale (xyz 20 20 1))"); mutated=check_model3d(scratch/"parts",scratch); require(mutated.ok&&mutated.misfit.size()==1,"fit remains soft");
    write(model,"not a model"); mutated=check_model3d(scratch/"parts",scratch); require(!mutated.ok&&mutated.invalid.size()==1,"unmeasurable geometry hard failure"); require(mutated.report().find("INVALID (1)")!=std::string::npos,"unmeasurable geometry reported");
    write(mod,base); mutated=check_model3d(scratch/"parts",scratch); require(!mutated.ok&&mutated.missing.size()==1,"missing clause hard failure");
    write(mod,"(footprint P (model \"relative.wrl\"))"); mutated=check_model3d(scratch/"parts",scratch); require(!mutated.ok&&mutated.broken.size()==1,"relative path hard failure");
    std::cout<<"288 Python geometry cases, OBJ bytes, 62 real footprints, 154 asset hashes and mutations pass\n";
}
void errors(const fs::path& scratch,const std::string& executable) {
    rejects([&]{render_pdf_to_png(scratch/"absent.pdf",scratch/"p.png");},"PDF not found"); write(scratch/"bad.pdf","not a PDF"); write(scratch/"p.png","preserve");
    rejects([&]{render_pdf_to_png(scratch/"bad.pdf",scratch/"p.png");},"cannot open"); require(read(scratch/"p.png")=="preserve","PDF failure preserves old output");
    rejects([&]{render_pdf_to_png(scratch/"bad.pdf",scratch/"p.png",0);},"DPI");
    rejects([&]{render_sheet_to_png(scratch/"absent.sch",scratch/"p.png");},"schematic not found");
    Render3dOptions o; o.kicad_cli="/no/native/kicad"; rejects([&]{render_board_3d("missing",scratch,o);},"not found");
    o.kicad_cli=executable; o.model_directory=scratch; o.width=20; o.height=20;
    write(scratch/"test.kicad_pcb","(kicad_pcb)"); write(scratch/"test.kicad_pro","project must survive");
    write(scratch/"errors/3d_top.png","stale output");
    const auto failed=render_board_3d(scratch/"test.kicad_pcb",scratch/"errors",o);
    require(!failed.ok()&&failed.written.empty()&&failed.failures.size()==8,"all failed native child processes reported"); require(read(scratch/"errors/3d_top.png")=="stale output","failed renderer cannot pass stale PNG"); require(read(scratch/"test.kicad_pro")=="project must survive","source project never mutated");
    setenv("SCHGEN_RENDER_CONTRACT_CORRUPT","1",1); const auto corrupt=render_board_3d(scratch/"test.kicad_pcb",scratch/"errors",o); unsetenv("SCHGEN_RENDER_CONTRACT_CORRUPT");
    require(!corrupt.ok()&&corrupt.failures.size()==8,"exit zero with corrupt PNG rejected");
    setenv("SCHGEN_RENDER_CONTRACT_TIMEOUT","1",1); o.timeout=std::chrono::milliseconds(250); const auto timed=render_board_3d(scratch/"test.kicad_pcb",scratch/"errors",o); unsetenv("SCHGEN_RENDER_CONTRACT_TIMEOUT");
    require(!timed.ok()&&timed.failures.size()==8,"renderer timeouts reported");
    o.timeout=std::chrono::milliseconds(5000); write(scratch/"corrupt.wrl","not geometry");
    write(scratch/"corrupt.kicad_pcb","(kicad_pcb (model \""+(scratch/"corrupt.wrl").string()+"\"))");
    rejects([&]{render_board_3d(scratch/"corrupt.kicad_pcb",scratch/"errors",o);},"no measurable coordinates");
    o.width=0; rejects([&]{render_board_3d("missing",scratch,o);},"dimensions");
}
void pdf_cases(const fs::path& repo,const fs::path& scratch) {
    const auto file=repo/"native/tests/data/render_models/pdf_reference.json";
    require(pcb_sha256(read(file))=="b9b583687e7e19e9eb25ac1afc38b1f30411ccd5163295894ceebc4362a95fe5","immutable PDF oracle bytes");
    const auto fixtures=parse_json_file(file.string()); std::size_t serial=0;
    for (const auto& c:fixtures.array_value) {
        const auto hex=str(c,"pdf_hex"); std::string pdf;
        for (std::size_t i=0;i<hex.size();i+=2) pdf.push_back(static_cast<char>(std::stoul(hex.substr(i,2),nullptr,16)));
        const auto input=scratch/("cropped démo "+std::to_string(serial++)+".pdf"); auto output=input; output.replace_extension(".png"); write(input,pdf);
        const auto p=render_pdf_to_png(input,output,static_cast<int>(field(c,"dpi").number_value));
        require(p.width_px==field(c,"width").number_value&&p.height_px==field(c,"height").number_value,"PDF rotation/crop raster dimensions");
        require(std::abs(p.page_w_mm-field(c,"page_w_mm").number_value)<1e-9&&std::abs(p.page_h_mm-field(c,"page_h_mm").number_value)<1e-9,"PDF rotation/crop physical dimensions");
        const auto rgb=pixels(output); std::array<int,4> red{p.width_px,p.height_px,-1,-1};
        for (int y=0;y<p.height_px;++y) for (int x=0;x<p.width_px;++x) {
            const auto i=static_cast<std::size_t>((y*p.width_px+x)*3);
            if (static_cast<unsigned char>(rgb[i])>240&&static_cast<unsigned char>(rgb[i+1])<20&&static_cast<unsigned char>(rgb[i+2])<20) { red[0]=std::min(red[0],x); red[1]=std::min(red[1],y); red[2]=std::max(red[2],x); red[3]=std::max(red[3],y); }
        }
        for (std::size_t i=0;i<4;++i) require(std::abs(red[i]-field(c,"red_bounds").array_value[i].number_value)<=1,"actual PDF artwork position vs MuPDF");
    }
    std::cout<<"8 independent rotated/cropped multi-page PDF cases pass\n";
}
void live(const JsonNode& fixture,const fs::path& repo,const fs::path& scratch) {
    const auto ref=parse_json_file((repo/"native/tests/data/render_models/render_reference.json").string());
    const auto tiles_path=repo/"native/tests/data/render_models/raster_tiles.json";
    require(pcb_sha256(read(tiles_path))=="93b0bd80feb38dc6d6d5218832cba80270d9e852a161c25102c260a94751971e","immutable independent raster tiles"); const auto tiles=parse_json_file(tiles_path.string());
    require(pcb_sha256(read(repo/"native/tests/data/render_models/render_reference.json"))=="92c8f067a7937462b4235ee2dcb88c5ceaa7eda4b22caf2f5932f29b393c6ff8","immutable render baseline");
    for (const auto& b:field(ref,"boards").array_value) {
        const auto source=repo/str(b,"source");
        auto original=read(source);
        if(str(b,"name")=="carrier"){
            // Preserve the original independent board hash: the only approved
            // migration is a real local model plus its package orientation.
            const std::string old_model="(model\n\t\t\t\"${KICAD10_3DMODEL_DIR}/Package_DFN_QFN.3dshapes/WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm.step\"\n\t\t\t(offset\n\t\t\t\t(xyz 0 0 0)\n\t\t\t)\n\t\t\t(scale\n\t\t\t\t(xyz 1 1 1)\n\t\t\t)\n\t\t\t(rotate\n\t\t\t\t(xyz 0 0 0)\n\t\t\t)\n\t\t)";
            auto repaired=old_model;
            replace(repaired,"${KICAD10_3DMODEL_DIR}/Package_DFN_QFN.3dshapes/WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm.step","${KIPRJMOD}/../parts/FUSB302BMPX/FUSB302BMPX.wrl");
            replace(repaired,"(rotate\n\t\t\t\t(xyz 0 0 0)","(rotate\n\t\t\t\t(xyz 0 0 90)");
            const auto pos=original.find(repaired);
            require(pos!=std::string::npos&&original.find(repaired,pos+1)==std::string::npos,"exactly one approved FUSB302 model repair");
            original.replace(pos,repaired.size(),old_model);
        }
        require(pcb_sha256(original)==str(b,"input_sha256"),"all PCB bytes outside approved model repair unchanged");
        const auto input=scratch/str(b,"name")/source.filename(); auto text=read(source); replace(text,"${KIPRJMOD}",source.parent_path().string()); write(input,text);
        auto source_pro=source; source_pro.replace_extension(".kicad_pro"); auto input_pro=input; input_pro.replace_extension(".kicad_pro"); if (fs::exists(source_pro)) write(input_pro,read(source_pro));
        const auto before=fs::exists(input_pro)?read(input_pro):std::string{};
        Render3dOptions o; o.width=240; o.height=180; o.quality="basic";
        const auto r=render_board_3d(input,input.parent_path()/"renders",o);
        for (const auto& e:r.failures) std::cerr<<e.view<<": "<<e.diagnostic<<'\n';
        require(r.ok(),"actual native KiCad must render all eight views"); require(read(input_pro)==before,"live source project immutable");
        for (std::size_t i=0;i<r.written.size();++i) {
            const auto& expected=field(b,"images").array_value[i]; require(r.written[i].filename()==str(expected,"name"),"view order");
            const auto rgb=pixels(r.written[i]); std::set<unsigned char> distinct(rgb.begin(),rgb.end()); require(distinct.size()>20,"actual rendered scene not blank");
            compare_tiles(rgb,field(field(tiles,str(b,"name")),str(expected,"name")));
            // Ray-tracer RNG/sampling may vary across executions. Log equality,
            // never claim a MuPDF/KiCad image byte contract when it is not one.
            std::cout<<str(b,"name")<<"/"<<str(expected,"name")<<" RGB Python-equal="<<(pcb_sha256(rgb)==str(expected,"rgb_sha256"))<<'\n';
        }
    }
    const auto complete_path=repo/"native/tests/data/render_models/asset_complete_reference.json";
    require(pcb_sha256(read(complete_path))=="2e4b5c6b812687c49f1d35d9d5104bfd38286252c0a78c5d92dd0ef8ee008830","immutable asset-complete capture"); const auto complete=parse_json_file(complete_path.string());
    const auto template_path=repo/"native/tests/data/render_models/asset_complete.kicad_pcb";
    auto board_text=read(template_path); require(pcb_sha256(board_text)==str(complete,"input_sha256"),"asset-complete independent template hash");
    replace(board_text,"@MODEL@",(repo/"parts/AO3400A/AO3400A.wrl").string());
    const auto mini=scratch/"asset-complete/fixture.kicad_pcb"; write(mini,board_text);
    Render3dOptions options; options.width=240; options.height=180; options.quality="basic";
    const auto rendered=render_board_3d(mini,mini.parent_path()/"renders",options);
    for (const auto& e:rendered.failures) std::cerr<<e.view<<": "<<e.diagnostic<<'\n';
    require(rendered.ok(),"asset-complete board must actually render all eight views");
    require(!fs::exists(mini.parent_path()/"fixture.kicad_pro"),"render must not create project beside caller PCB");
    std::set<std::string> view_hashes;
    for (std::size_t i=0;i<rendered.written.size();++i) {
        const auto& im=field(complete,"images").array_value[i]; require(rendered.written[i].filename()==str(im,"name"),"complete view order");
        require(rendered.views[i].width==field(im,"width").number_value&&rendered.views[i].height==field(im,"height").number_value,"actual KiCad raster dimensions equal Python");
        const auto rgb=pixels(rendered.written[i]); view_hashes.insert(pcb_sha256(rgb));
        compare_tiles(rgb,field(field(tiles,"asset-complete"),str(im,"name")));
        if (i==0) rejects([&]{compare_tiles(std::string(rgb.size(),'\0'),field(field(tiles,"asset-complete"),str(im,"name")));},"differs structurally");
        std::set<unsigned char> colors(rgb.begin(),rgb.end()); require(colors.size()>20,"real hardware render nonblank");
        std::cout<<"asset-complete/"<<str(im,"name")<<" RGB Python-equal="<<(pcb_sha256(rgb)==str(im,"rgb_sha256"))<<'\n';
    }
    require(view_hashes.size()>=5,"native camera views change actual raster");
    export_board_step(mini,mini.parent_path()/"fixture.step",options);
    const auto step=read(mini.parent_path()/"fixture.step"); require(step.size()>10000&&step.find("AO3400A")!=std::string::npos,"actual OpenCascade board STEP includes hardware model");
    require(!fs::exists(mini.parent_path()/"fixture.kicad_pro"),"STEP export must not create caller project");
    std::cout<<"native KiCad/OpenCascade STEP export includes AO3400A: "<<step.size()<<" bytes\n";
    const auto& sheet=field(ref,"sheet"); const auto source=repo/str(sheet,"source"); require(pcb_sha256(read(source))==str(sheet,"input_sha256"),"schematic baseline unchanged");
    const auto p=render_sheet_to_png(source,scratch/"schematic.png",72); require(std::abs(p.page_w_mm-field(sheet,"page_w_mm").number_value)<0.00002&&std::abs(p.page_h_mm-field(sheet,"page_h_mm").number_value)<0.00002,"native PDF physical geometry vs MuPDF");
    require(std::abs(p.width_px-field(sheet,"width_px").number_value)<=1&&std::abs(p.height_px-field(sheet,"height_px").number_value)<=1,"native PDF raster dimensions within rounding pixel");
    const auto corner=p.mm_to_px(p.page_w_mm,p.page_h_mm); require(std::abs(corner.first-p.width_px)<1e-9&&std::abs(corner.second-p.height_px)<1e-9,"mm-to-pixel mapping");
    const auto rgb=pixels(p.png_path); std::size_t dark=0; for (unsigned char c:rgb) if (c<180) ++dark; require(dark>1000&&dark<rgb.size()/2,"native schematic includes visible artwork on white page");
    std::cout<<"Poppler schematic "<<p.width_px<<'x'<<p.height_px<<", dark channels="<<dark<<", physical page matches MuPDF\n";
    for (const auto& [asset,sha]:field(fixture,"assets").object_value) require(pcb_sha256(read(repo/asset))==sha.string_value,"assets unchanged after live renders");
}
}
int main(int argc,char** argv) {
    // Native-only adversarial child, used solely by error contracts. Success
    // path coverage always invokes the real KiCad binary with --live.
    if (argc==2&&std::string(argv[1])=="version") { std::cout<<"10.0.2\n"; return 0; }
    if (argc>2&&std::string(argv[1])=="pcb") {
        if (std::getenv("SCHGEN_RENDER_CONTRACT_TIMEOUT")) ::usleep(1000000);
        if (std::getenv("SCHGEN_RENDER_CONTRACT_CORRUPT")) { for (int i=0;i+1<argc;++i) if (std::string(argv[i])=="-o") write(argv[i+1],"not PNG"); return 0; }
        std::cerr<<"intentional native failure contract\n"; return 17;
    }
    try {
        if (argc<3) throw std::runtime_error("usage: contracts REPO SCRATCH [--live]");
        const fs::path repo=argv[1],scratch=argv[2]; fs::create_directories(scratch);
        const auto fixture=parse_json_file((repo/"native/tests/data/render_models/reference.json").string());
        require(pcb_sha256(read(repo/"native/tests/data/render_models/reference.json"))=="c233558629102d5885d7dd3ad845e2894ee9107794b3ab57fa08b8fac6968a2c","immutable Python capture");
        pure(fixture,repo,scratch); errors(scratch,fs::absolute(argv[0]).string()); pdf_cases(repo,scratch); if (argc>3&&std::string(argv[3])=="--live") live(fixture,repo,scratch);
        std::cout<<assertions<<" render/model contracts PASS\n"; return 0;
    } catch (const std::exception& e) { std::cerr<<"FAIL: "<<e.what()<<'\n'; return 1; }
}
