#include "schgen/ratsnest_documents.hpp"
#include "schgen/ratsnest_gate.hpp"
#include "schgen/pcb_emit.hpp"
#include "schgen/atomic_file.hpp"
#include "ratsnest_documents_internal.hpp"
#include <fstream>
#include <iostream>
#include <cstdlib>
#include <zlib.h>

namespace fs=std::filesystem;
using namespace schgen;
namespace {
std::size_t assertions=0;
void require(bool p,const std::string& why){++assertions;if(!p)throw std::runtime_error(why);}
const JsonNode& field(const JsonNode& n,const std::string& k){auto p=object_field(n,k);if(!p)throw std::runtime_error("missing "+k);return *p;}
std::string str(const JsonNode& n,const std::string& k){return field(n,k).string_value;}
double num(const JsonNode& n,const std::string& k){return field(n,k).number_value;}
std::string read(const fs::path& p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("cannot read "+p.string());return {std::istreambuf_iterator<char>(f),{}};}
void write(const fs::path& p,const std::string& s){write_atomic_file(p.string(),{s.begin(),s.end()});}
template<class F>void rejects(F f,const std::string& message){bool caught=false;try{f();}catch(const std::exception& e){caught=true;require(std::string(e.what()).find(message)!=std::string::npos,"unexpected error: "+std::string(e.what()));}require(caught,"expected rejection: "+message);}
PcbFootprintPool pool(const JsonNode& n){PcbFootprintPool out;for(const auto& [k,v]:n.object_value)out[k]=pcb_check_footprint(k,v.string_value);return out;}
std::uint32_t be32(const std::string& s,std::size_t i){std::uint32_t out=0;for(int n=0;n<4;++n)out=(out<<8)|static_cast<unsigned char>(s.at(i+n));return out;}
std::string rgb(const std::string& png,int width,int height){
    require(png.substr(0,8)==std::string("\x89PNG\r\n\x1a\n",8),"PNG signature");require(be32(png,16)==static_cast<unsigned>(width)&&be32(png,20)==static_cast<unsigned>(height),"PNG size");
    std::string compressed;for(std::size_t p=8;p<png.size();){auto n=be32(png,p);require(p+n+12<=png.size(),"PNG chunk bound");const auto crc=crc32(0,reinterpret_cast<const Bytef*>(png.data()+p+4),n+4);require(crc==be32(png,p+8+n),"PNG CRC");if(png.substr(p+4,4)=="IDAT")compressed+=png.substr(p+8,n);p+=n+12;}
    const auto stride=static_cast<std::size_t>(width)*3;std::string filtered((stride+1)*height,'\0');uLongf size=filtered.size();
    require(uncompress(reinterpret_cast<Bytef*>(filtered.data()),&size,reinterpret_cast<const Bytef*>(compressed.data()),compressed.size())==Z_OK&&size==filtered.size(),"PNG decode");
    std::string out(stride*height,'\0');for(int y=0;y<height;++y){auto filter=static_cast<unsigned char>(filtered[y*(stride+1)]);require(filter<=4,"PNG filter");for(std::size_t x=0;x<stride;++x){const auto offset=y*stride+x;
        const int a=x>=3?static_cast<unsigned char>(out[offset-3]):0,b=y?static_cast<unsigned char>(out[offset-stride]):0,c=y&&x>=3?static_cast<unsigned char>(out[offset-stride-3]):0,p=a+b-c,aa=std::abs(p-a),bb=std::abs(p-b),cc=std::abs(p-c);
        const int predictor=filter==1?a:filter==2?b:filter==3?(a+b)/2:filter==4?(aa<=bb&&aa<=cc?a:bb<=cc?b:c):0;out[offset]=static_cast<char>(static_cast<unsigned char>(filtered[y*(stride+1)+x+1])+predictor);}}
    return out;
}
void check_image(const RatsnestImage& im,const JsonNode& expected,const fs::path& output){
    require(im.filename==str(expected,"filename"),"image filename");require(im.width==num(expected,"width")&&im.height==num(expected,"height"),"image dimensions "+im.filename);
    write(output/im.filename,im.png);const auto pixels=rgb(im.png,im.width,im.height);write(output/(im.filename+".rgb"),pixels);
    require(pcb_sha256(pixels)==str(expected,"rgb_sha256"),"RGB differs: "+(output/im.filename).string());
    require(pcb_sha256(im.png)==str(expected,"png_sha256"),"PNG bytes differ: "+im.filename);
}
void test_case(const PcbModel& model,const JsonNode& expected,const fs::path& output){
    std::set<std::string> names;for(const auto& inst:model.insts)names.insert(inst.sheet);const auto colors=ratsnest_palette({names.begin(),names.end()});
    require(colors.size()==field(expected,"palette").object_value.size(),"palette count");for(const auto& [name,c]:field(expected,"palette").object_value)for(std::size_t i=0;i<3;++i)require(colors.at(name)[i]==c.array_value[i].number_value,"palette color");
    const auto result=render_ratsnest_documents(model);write(output/"RATSNEST.svg",result.svg);
    require(pcb_sha256(result.svg)==str(expected,"svg_sha256"),"SVG bytes differ: "+(output/"RATSNEST.svg").string());
    require(result.cross_mm==num(expected,"cross_mm")&&result.total_mm==num(expected,"total_mm")&&result.n_cross==num(expected,"n_cross"),"lengths exact");
    const auto& images=field(expected,"images").array_value;require(result.images.size()==images.size(),"image count");
    for(std::size_t i=0;i<images.size();++i)check_image(result.images[i],images[i],output);
    std::cout<<str(expected,"name")<<": SVG and "<<images.size()<<" PNGs byte exact\n";
}
void boundaries(PcbModel m,const fs::path& scratch){
    const auto original=render_ratsnest_documents(m);const auto nets=ratsnest_net_pad_positions(m);const auto edges=ratsnest_mst(nets);
    const auto supplied=render_ratsnest_documents(m,&nets,&edges);require(supplied.svg==original.svg&&supplied.images[0].png==original.images[0].png,"supplied nets and edges preserved");
    std::set<std::string> names;std::map<std::string,std::set<std::string>> by_sheet;std::set<std::string> som;
    for(const auto& inst:m.insts){names.insert(inst.sheet);by_sheet[inst.sheet].insert(inst.ref);if(inst.sheet.compare(0,4,"som_")==0)som.insert(inst.ref);}
    const auto palette=ratsnest_palette({names.begin(),names.end()});require(render_ratsnest_board_image(m,palette,"top",nets,edges).png==original.images[0].png,"individual board image exact");
    const auto subsystems=render_ratsnest_subsystem_images(m,nets,edges);require(subsystems.size()+2==original.images.size(),"subsystem API inventory");
    for(std::size_t i=0;i<subsystems.size();++i){const auto& im=subsystems[i];require(im.png==original.images[i+2].png,"subsystem API image exact");const auto name=fs::path(im.filename).stem().string();
        require(render_ratsnest_sheet_image(m,name,name=="som"?som:by_sheet.at(name),nets,edges,name=="som"?std::set<std::string>{}:som).png==im.png,"individual sheet image exact");}
    rejects([&]{render_ratsnest_sheet_image(m,"unknown",{"missing"},nets,edges);},"unknown sheet reference");
    rejects([&]{render_ratsnest_sheet_image(m,"empty",{},nets,edges);},"empty sheet bounds");
    rejects([&]{render_ratsnest_board_image(m,palette,"middle",nets,edges);},"invalid requested side");
    auto changed=m;changed.insts.front().x+=1;auto moved=render_ratsnest_documents(changed);require(moved.svg!=original.svg&&moved.images.front().png!=original.images.front().png,"fresh poses affect both outputs");
    auto altered=edges;for(auto& [name,es]:altered){(void)name;if(!es.empty()){es.pop_back();break;}}
    const auto fewer=render_ratsnest_documents(m,&nets,&altered);require(fewer.svg!=original.svg&&fewer.total_mm<original.total_mm,"caller graph used instead of recomputed MST");
    changed=m;changed.origin_x+=10;changed.origin_y+=10;for(auto& i:changed.insts){i.x+=10;i.y+=10;}
    if(changed.som_keepout){changed.som_keepout->x0+=10;changed.som_keepout->x1+=10;changed.som_keepout->y0+=10;changed.som_keepout->y1+=10;}
    const auto translated=render_ratsnest_documents(changed);require(translated.svg==original.svg,"explicit model origin respected");for(std::size_t i=0;i<original.images.size();++i)require(translated.images[i].png==original.images[i].png,"translated image exact");
    const auto root=scratch/"publication";write(root/"renders/ratsnest/stale.png","stale");write(root/"renders/ratsnest/keep.txt","keep");write(root/"renders/untouched.png","outside");
    const auto published=run_ratsnest_documents(m,root);require(read(published.svg)==original.svg,"live SVG published");require(read(published.png_top)==original.images[0].png&&read(published.png_bottom)==original.images[1].png,"live PNGs published");
    rejects([&]{ratsnest_document_summary(published,root/"unrelated");},"outside repository");
    require(!fs::exists(root/"renders/ratsnest/stale.png")&&read(root/"renders/ratsnest/keep.txt")=="keep"&&read(root/"renders/untouched.png")=="outside","stale cleanup scoped");
    require(published.sheets.size()+2==original.images.size(),"published sheet inventory");for(const auto& im:original.images)require(read(root/"renders"/im.filename)==im.png,"publication content");
    write(root/"renders/ratsnest/retained-on-failure.png","retain");changed=m;changed.insts.front().mod.reset();rejects([&]{run_ratsnest_documents(changed,root);},"unresolved");
    require(read(published.svg)==original.svg&&read(root/"renders/ratsnest/retained-on-failure.png")=="retain","failed render writes and prunes nothing");
    const auto blocked=scratch/"blocked";write(blocked/"docs","file");write(blocked/"renders/ratsnest_top.png","previous");rejects([&]{run_ratsnest_documents(m,blocked);},"docs");require(read(blocked/"renders/ratsnest_top.png")=="previous","publication preflight failure preserves previous image");
    changed=m;changed.insts.push_back(changed.insts.front());rejects([&]{render_ratsnest_documents(changed);},"duplicate reference");
    changed=m;changed.insts.front().ref="R\n1";rejects([&]{render_ratsnest_documents(changed);},"invalid reference label");
    changed=m;changed.insts.front().sheet="../escape";rejects([&]{run_ratsnest_documents(changed,root);},"unsafe sheet");
    changed=m;changed.insts.front().sheet="som";changed.insts.back().sheet="som_custom";rejects([&]{render_ratsnest_documents(changed);},"colliding som.png");
    changed=m;changed.insts.front().side="internal";rejects([&]{render_ratsnest_documents(changed);},"invalid side");
    changed=m;changed.board_w=-1;rejects([&]{render_ratsnest_documents(changed);},"dimensions out of range");
    changed=m;changed.board_h=std::numeric_limits<double>::quiet_NaN();rejects([&]{render_ratsnest_documents(changed);},"nonfinite");
    changed=m;changed.insts.front().x=std::numeric_limits<double>::infinity();rejects([&]{render_ratsnest_documents(changed);},"nonfinite");
    changed=m;changed.som_keepout=Box4{2,2,1,1};rejects([&]{render_ratsnest_documents(changed);},"invalid keepout");
    RatsnestEdges missing;rejects([&]{render_ratsnest_documents(m,&nets,&missing);},"missing net");
    auto invalid=edges;invalid.begin()->second.push_back({-1,0});rejects([&]{render_ratsnest_documents(m,&nets,&invalid);},"invalid edge");
    invalid=edges;invalid.begin()->second.push_back({0,100000});rejects([&]{render_ratsnest_documents(m,&nets,&invalid);},"invalid edge");
    auto bad_nets=nets;std::get<0>(bad_nets.begin()->second.front())=std::numeric_limits<double>::quiet_NaN();rejects([&]{render_ratsnest_documents(m,&bad_nets);},"coordinate out of range");
    bad_nets=nets;std::get<1>(bad_nets.begin()->second.front())=1e20;rejects([&]{render_ratsnest_documents(m,&bad_nets);},"coordinate out of range");
    rejects([&]{ratsnest_airwires(m,nets,edges,"inside");},"invalid requested side");
    changed=m;changed.insts.front().sheet="logic & <control>";const auto escaped=render_ratsnest_documents(changed);
    require(escaped.svg.find("logic &amp; &lt;control&gt;")!=std::string::npos&&escaped.svg.find("logic & <control>")==std::string::npos,"SVG escapes text markup");
    ratsnest_detail::Raster raster(10,10);rejects([&]{raster.line(0,0,1,1,{0,0,0,255},3);},"only line widths");
    rejects([&]{raster.line(0,0,1e20,1,{0,0,0,255},1);},"coordinate out of range");
    rejects([&]{raster.text(0,0,std::string(100001,'R'),{0,0,0,255});},"text too long");
    rejects([&]{ratsnest_detail::Raster huge(10000,10000);},"50 million");
    rejects([&]{ratsnest_detail::Raster empty(0,5);},"dimension out of range");
    std::cout<<"live mutation, publication and error contracts passed\n";
}
}
int main(int argc,char** argv){try{
    if(argc!=3)throw std::runtime_error("usage: ratsnest_documents_contracts REPOSITORY SCRATCH_PARENT");
    const fs::path root=argv[1];fs::create_directories(argv[2]);auto pattern=(fs::path(argv[2])/"run-XXXXXX").string();std::vector<char> path(pattern.begin(),pattern.end());path.push_back(0);if(!mkdtemp(path.data()))throw std::runtime_error("mkdtemp failed");const fs::path scratch=path.data();std::cout<<"scratch: "<<scratch<<"\n";
    const auto fixture_path=root/"native/tests/data/ratsnest_documents/reference.json";
    require(pcb_sha256(read(fixture_path))=="21c1e68c4ea12e4cadce261dcbd122be88a045e29af873de8a538dd4763d7569","immutable reference fixture");
    const auto fixture=parse_json_file(fixture_path.string());
    const auto& raster=field(fixture,"raster");ratsnest_detail::Raster im(91,79);
    for(const auto& line:field(raster,"lines").array_value){const auto& p=field(line,"points").array_value;const auto& c=field(line,"color").array_value;
        im.line(p[0].number_value,p[1].number_value,p[2].number_value,p[3].number_value,{static_cast<unsigned char>(c[0].number_value),static_cast<unsigned char>(c[1].number_value),static_cast<unsigned char>(c[2].number_value),static_cast<unsigned char>(c[3].number_value)},static_cast<int>(num(line,"width")));}
    check_image({"raster.png",im.png(),im.width,im.height},field(raster,"image"),scratch);std::cout<<"raster octants and clipping exact\n";
    const auto summary_path=root/"native/tests/data/ratsnest_documents/summary.json";
    require(pcb_sha256(read(summary_path))=="6e9db9806c3b38e0c6199e90ec0129882ddb2eb668bcf2e83e0240406d802907","immutable summary fixture");
    const auto summaries=parse_json_file(summary_path.string());
    const auto fps=pool(field(fixture,"footprints"));for(const auto& row:field(fixture,"mutations").array_value){auto m=pcb_model_from_json(field(row,"model"),fps);test_case(m,row,scratch/str(row,"name"));
        RatsnestPublication r;r.png_top="/repo/board/renders/ratsnest_top.png";r.png_bottom="/repo/board/renders/ratsnest_bottom.png";r.svg="/repo/board/docs/RATSNEST.svg";r.board_w=m.board_w;r.board_h=m.board_h;r.n_top=m.n_top;r.n_bottom=m.n_bottom;r.cross_mm=num(row,"cross_mm");r.total_mm=num(row,"total_mm");r.n_cross=static_cast<int>(num(row,"n_cross"));require(ratsnest_document_summary(r,"/repo")==str(summaries,str(row,"name")),"summary exact");}
    for(const auto& expected:field(fixture,"projects").array_value){const auto name=str(expected,"name");const auto raw=parse_json_file((root/"native/tests/data/pcb_emit"/(name+".json")).string());test_case(pcb_model_from_json(field(raw,"model"),pool(field(raw,"footprints"))),expected,scratch/name);}
    boundaries(pcb_model_from_json(field(field(fixture,"mutations").array_value.front(),"model"),fps),scratch);
    std::cout<<assertions<<" ratsnest document assertions passed\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
