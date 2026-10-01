// Correctness regressions, separate from immutable historical geometry goldens.
#include "../src/schematic_place_internal.hpp"
#include "schgen/native_render.hpp"
#include <fstream>
#include <iostream>
#include <sstream>
#include <png.h>

using namespace schgen;
namespace fs = std::filesystem;
static void require(bool v, const std::string& why) { if (!v) throw std::runtime_error(why); }
static const JsonNode& field(const JsonNode& n,const std::string& k) {
    const auto* p=object_field(n,k); require(p!=nullptr,"missing "+k); return *p;
}
static double number(const JsonNode& n,const std::string& k) {return field(n,k).number_value;}
static const SexprList& children(const Sexpr& n) {return std::get<SexprList>(n.v);}
static const Sexpr& child(const Sexpr& n,const std::string& k) {
    for(const auto& v:children(n)) if(const auto* a=std::get_if<SexprList>(&v.v))
        if(!a->empty()) if(const auto* s=std::get_if<Sexpr::Sym>(&a->front().v)) if(s->name==k)return v;
    throw std::runtime_error("missing sexpr "+k);
}
static std::string letters(std::string s) {
    s.erase(std::remove(s.begin(),s.end(),' '),s.end()); return s;
}
static void margin_clear(const PageRaster& raster) {
    png_image png{};png.version=PNG_IMAGE_VERSION;
    require(png_image_begin_read_from_file(&png,raster.png_path.c_str())!=0,"PNG read");
    png.format=PNG_FORMAT_RGB;std::vector<unsigned char> pixels(PNG_IMAGE_SIZE(png));
    require(png_image_finish_read(&png,nullptr,pixels.data(),0,nullptr)!=0,"PNG decode");
    const auto start=raster.mm_to_px(raster.page_w_mm-9,raster.page_h_mm-40);
    const auto end=raster.mm_to_px(raster.page_w_mm,raster.page_h_mm-18);
    bool ink=false;
    for(int y=static_cast<int>(start.second);y<static_cast<int>(end.second);++y)
        for(int x=static_cast<int>(start.first);x<static_cast<int>(png.width);++x) {
            const auto k=(static_cast<std::size_t>(y)*png.width+x)*3;
            ink|=pixels[k]>70 && pixels[k+1]<pixels[k]/2 && pixels[k+2]<pixels[k]/2;
        }
    png_image_free(&png);require(!ink,"title/comment ink beyond worksheet right frame");
}
static void project_titles() {
    SchematicDesign d; d.circuit.name="same_sheet";
    d.circuit.title="Long project-independent sheet title that must retain its existing wrapping exactly";
    const auto before=emit_schematic(d,SchematicSymbolResolver{}).text;
    for (const auto& [name,label] : std::vector<std::pair<std::string,std::string>>{
            {"carrier","Zynq SoM Carrier"},{"devkit_mini","Zynq SoM Devkit Mini"},
            {"unrelated_test_board","Zynq SoM Unrelated Test Board"}}) {
        const auto emitted=emit_schematic(d,SchematicSymbolResolver{},{"","","",name}).text;
        auto expected=before;
        const std::string old_company="(company \"Zynq SoM Carrier\")";
        const auto position=expected.find(old_company);
        require(position!=std::string::npos,"company field absent");
        expected.replace(position,old_company.size(),"(company \""+label+"\")");
        require(emitted==expected,"project title changed wrapping/geometry/UUIDs or ignored metadata");
    }
}
static void titles(const fs::path& renders) {
    project_titles();
    const std::vector<std::string> cases={"", "Short title", std::string(40,'W'), std::string(41,'W'),
        "SoM bank-35 IO breakout (2x20 2.54mm header, VADJ 2.5V)",
        "Mechanical: M3 mounts + chassis-GND bond (fiducials are PCB-only)",
        "Repeated unicode — μ Ω 中文 title repeated unicode — μ Ω 中文 title"};
    for(std::size_t i=0;i<cases.size();++i) {
        SchematicDesign d;d.circuit.name="title_regression";d.circuit.title=cases[i];
        const auto a=emit_schematic(d,SchematicSymbolResolver{});
        require(a.text==emit_schematic(d,SchematicSymbolResolver{}).text,"title nondeterminism");
        const auto& block=child(a.document,"title_block");
        std::string joined=std::get<std::string>(children(child(block,"title"))[1].v);
        if(i<3) require(joined==cases[i],"short title changed");
        else require(joined!=cases[i],"overlong title not wrapped");
        for(const auto& row:children(block)) if(const auto* fields=std::get_if<SexprList>(&row.v))
            if(fields->size()==3) if(const auto* s=std::get_if<Sexpr::Sym>(&(*fields)[0].v))
                if(s->name=="comment" && std::get<double>((*fields)[1].v)>1)
                    joined+=std::get<std::string>((*fields)[2].v);
        require(letters(joined)==letters(cases[i]),"title content lost");
        require(d.circuit.title==cases[i],"title IR mutated");
        if(!renders.empty()) {
            fs::create_directories(renders);
            const auto path=renders/("title_"+std::to_string(i)+".kicad_sch");
            {std::ofstream out(path);out<<a.text;require(out.good(),"title write");}
            margin_clear(render_sheet_to_png(path,renders/("title_"+std::to_string(i)+".png")));
        }
    }
    SchematicDesign huge;huge.circuit.title=std::string(1000,'W');
    bool rejected=false;try{emit_schematic(huge,SchematicSymbolResolver{});}catch(const std::runtime_error&){rejected=true;}
    require(rejected,"unbounded worksheet title accepted");
    std::cout<<"title regressions: 7 deterministic/content-preserving cases + capacity rejection PASS\n";
}
static void clusters(const fs::path& fixtures) {
    using namespace schgen::schematic_place;
    SymbolLibrary lib(std::vector<fs::path>{fixtures/"symbols"});
    std::size_t count=0,wrapped=0;
    for(const auto& entry:fs::directory_iterator(fixtures)) {
        if(entry.path().extension()!=".json")continue;
        std::ifstream in(entry.path());std::ostringstream buffer;buffer<<in.rdbuf();
        const auto f=parse_json_text(buffer.str());const auto* method=object_field(f,"method");
        if(!method||method->string_value!="cluster")continue;
        auto c=parse_circuit_ir(field(f,"circuit"));
        const auto& s=field(f,"spacing");
        SchematicSpacing spacing{number(s,"port_run"),number(s,"label_tap_gap"),number(s,"hang_stub"),
            number(s,"stagger_extra"),number(s,"cap_pitch"),number(s,"cluster_dx"),number(s,"cluster_dy"),
            number(s,"flags_dy"),number(s,"flag_pitch")};
        Engine e(c,lib,spacing);const auto& init=field(f,"initial");
        e._n_box_bucks=static_cast<std::size_t>(number(init,"n_box_bucks"));
        for(const auto& b:field(field(init,"placement"),"boxes").array_value)
            e.pl.boxes.push_back({number(b,"x0"),number(b,"y0"),number(b,"x1"),number(b,"y1"),
                field(b,"kind").string_value,field(b,"owner").string_value});
        const auto& args=field(f,"args");const auto& b=field(args,"body");
        e._decoupling_cluster(number(args,"ax"),number(args,"ay"),
            {number(b,"x0"),number(b,"y0"),number(b,"x1"),number(b,"y1"),"body","U0"});
        require(e.pl.parts.size()==c.parts.size(),"cluster dropped a capacitor");
        std::set<double> rows;for(const auto& p:e.pl.parts)rows.insert(p.y);
        if(rows.size()>1)++wrapped;
        for(const auto& power:e.pl.powers) if(power.net_name()=="GND")
            for(const auto& box:e.pl.boxes) if(box.owner==power.ref)
                for(const auto& [net,paths]:e.pl.plans) if(net!="GND")
                    for(const auto& path:paths) for(std::size_t j=1;j<path.size();++j) {
                        const auto a=path[j-1],z=path[j];if(a.second!=z.second||a.first==z.first)continue;
                        const bool intersects=a.second>=box.y0 && a.second<=box.y1 &&
                            std::max(a.first,z.first)>=box.x0 && std::min(a.first,z.first)<=box.x1;
                        require(!intersects,entry.path().filename().string()+": foreign bus touches ground artwork/text");
                    }
        ++count;
    }
    require(count>=6 && wrapped>=1,"cluster regression coverage missing");
    std::cout<<"cluster regressions: "<<count<<" immutable inputs, "<<wrapped<<" wrapped PASS\n";
}
int main(int argc,char** argv) {try {
    require(argc==2||argc==3,"usage: schematic_visual_corrections FIXTURE_DIR [PRIVATE_RENDER_DIR]");
    int failures=0;
    try{titles(argc==3?fs::path(argv[2]):fs::path{});}catch(const std::exception& e){std::cerr<<e.what()<<'\n';++failures;}
    try{clusters(argv[1]);}catch(const std::exception& e){std::cerr<<e.what()<<'\n';++failures;}
    return failures?1:0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
