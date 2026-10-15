#include "schgen/board_pipeline.hpp"
#include "schgen/process.hpp"
#include <fstream>
#include <iostream>
#include <iterator>
#include <set>
#include <unistd.h>

namespace {
using namespace schgen;
namespace fs=std::filesystem;
std::size_t checks=0;
void require(bool ok,const std::string& why){++checks;if(!ok)throw std::runtime_error(why);}
struct Scratch {
    fs::path path;
    Scratch(){auto pattern=(fs::temp_directory_path()/"schgen-render-baseline-XXXXXX").string();require(::mkdtemp(pattern.data())!=nullptr,"create private baseline scratch");path=pattern;}
    ~Scratch(){std::error_code ec;fs::remove_all(path,ec);}
};
void write(const fs::path& path,const std::string& bytes){
    std::ofstream out(path,std::ios::binary);out.write(bytes.data(),static_cast<std::streamsize>(bytes.size()));out.close();
    require(bool(out),"write private historical image");
}
std::string read(const fs::path& path){
    std::ifstream in(path,std::ios::binary);if(!in)throw std::runtime_error("missing baseline artifact: "+path.string());
    std::string out{std::istreambuf_iterator<char>(in),{}};
    if(in.bad())throw std::runtime_error("incomplete baseline artifact: "+path.string());return out;
}
std::string git(const fs::path& root,std::vector<std::string> args){
    args.insert(args.begin(),{"git","-C",root.string()});
    const auto result=run_process_bytes(args);
    if(result.exit_code)throw std::runtime_error("baseline Git evidence unavailable: "+result.stderr_text);
    return result.stdout_text;
}
const std::string old_model="(model\n\t\t\t\"${KICAD10_3DMODEL_DIR}/Package_DFN_QFN.3dshapes/WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm.step\"\n\t\t\t(offset\n\t\t\t\t(xyz 0 0 0)\n\t\t\t)\n\t\t\t(scale\n\t\t\t\t(xyz 1 1 1)\n\t\t\t)\n\t\t\t(rotate\n\t\t\t\t(xyz 0 0 0)\n\t\t\t)\n\t\t)";
const std::string repaired_model="(model\n\t\t\t\"${KIPRJMOD}/../parts/FUSB302BMPX/FUSB302BMPX.wrl\"\n\t\t\t(offset\n\t\t\t\t(xyz 0 0 0)\n\t\t\t)\n\t\t\t(scale\n\t\t\t\t(xyz 1 1 1)\n\t\t\t)\n\t\t\t(rotate\n\t\t\t\t(xyz 0 0 90)\n\t\t\t)\n\t\t)";
std::string before_repair(std::string bytes){
    const auto pos=bytes.find(repaired_model);
    require(pos!=bytes.npos&&bytes.find(repaired_model,pos+repaired_model.size())==bytes.npos,"exactly one approved physical-model repair required");
    require(bytes.find(old_model)==bytes.npos,"obsolete missing model must not remain");
    bytes.replace(pos,repaired_model.size(),old_model);return bytes;
}
void run(const fs::path& root){
    const std::string pcb="carrier/Zynq_Carrier.kicad_pcb";
    const std::string historical="c3a627a0f4fd21f7084264395bde3d8da033a4d0";
    const auto baseline=git(root,{"show",historical+":"+pcb});
    // Same approved bytes as historical MD5 06308484dd95ffb65b09ef456bd64547.
    // Pin immutable history: origin/master legitimately advances after merges.
    // Independently verified with both digests at retirement;
    // SHA-256 strengthens the pin, it does not bless a new board.
    const std::string approved="4b45325d224e6376dc43b871484357fad50b1705b37b0389e2c746683c4022f7";
    require(pcb_sha256(baseline)==approved,"historical approved board baseline changed");
    const auto model_repair=git(root,{"show","374c42acc50138ea609d85dfe4d2c503fb0c538c:"+pcb});
    require(pcb_sha256(before_repair(model_repair))==approved,"historical physical-model repair changed other bytes");
    // 226bfb83 subsequently removed exactly three degenerate RV-3028
    // courtyard lines and resequenced that footprint's generated UUIDs.
    // The full diff was reviewed; no pad, placement, valid edge or model moved.
    // Pin its entire artifact rather than normalize arbitrary geometry away.
    const auto corrected=git(root,{"show","226bfb8346eadf0d59e59d4e6b1f3ef99fec279d:"+pcb});
    require(pcb_sha256(corrected)=="8437ddd4fbcf012c800bed70a1b6968c0d09444b00c9e816390dfc5946360633","reviewed courtyard correction artifact changed");
    const auto current=read(root/pcb);
    // Current placement may improve. Keep the model-specific invariant, not
    // byte equality with a retired board. Hardware qualification lives in the
    // independent PCB checks and full board pipeline.
    before_repair(current);
    bool rejected=false;try{before_repair(current+repaired_model);}catch(const std::exception&){rejected=true;}
    require(rejected,"duplicate repair must not be normalized away");
    rejected=false;try{before_repair(current+old_model);}catch(const std::exception&){rejected=true;}
    require(rejected,"old model must not be normalized away");
    std::set<std::string> paths;
    const auto collect=[&](const std::string& bytes){
        std::size_t start=0;while(start<bytes.size()){
            const auto end=bytes.find('\0',start);require(end!=bytes.npos,"Git inventory must be NUL terminated");
            const fs::path path=bytes.substr(start,end-start);start=end+1;
            const auto parent=path.parent_path().generic_string();
            if(path.extension()==".png"&&(parent=="carrier/renders"||parent=="carrier/renders/ratsnest"||parent=="carrier/renders/assembly"))paths.insert(path.generic_string());
        }
    };
    collect(git(root,{"ls-tree","-r","--name-only","-z",historical,"--","carrier/renders"}));
    require(paths.size()>=10,"official baseline population cannot shrink");
    require(read(root/"carrier/renders/golden.json")==git(root,{"show",historical+":carrier/renders/golden.json"}),"historical golden must not be silently blessed");
    const auto golden=parse_json_file((root/"carrier/renders/golden.json").string());
    require(golden.kind==JsonKind::Object&&!golden.object_value.empty(),"golden map must not be empty");
    Scratch scratch;
    const auto historical_image=scratch.path/"historical.png";
    for(const auto& path:paths){
        write(historical_image,git(root,{"show",historical+":"+path}));
        require(board_png_average_hash(historical_image).size()==256,"historical image decodes: "+path);
        const auto current_hash=board_png_average_hash(root/path);
        require(current_hash.size()==256&&current_hash.find('0')!=current_hash.npos&&current_hash.find('1')!=current_hash.npos,"current image exists, decodes and is nonuniform: "+path);
    }
    for(const auto& [name,expected]:golden.object_value){
        require(!name.empty()&&fs::path(name).filename()==name&&name!="."&&name!="..","safe golden image name");
        require(expected.kind==JsonKind::String&&expected.string_value.size()==256&&expected.string_value.find_first_not_of("01")==std::string::npos,"valid exact golden hash");
        const auto path="carrier/renders/"+name+".png";
        require(paths.count(path)==1,"golden image belongs to pinned historical inventory");
        write(historical_image,git(root,{"show",historical+":"+path}));
        require(board_png_average_hash(historical_image)==expected.string_value,"zero-distance historical golden hash drift: "+name);
    }
    write(historical_image,"not a PNG");
    rejected=false;try{board_png_average_hash(historical_image);}catch(const std::exception&){rejected=true;}
    require(rejected,"corrupt image must not pass current-image decode checks");
}
}
int main(int argc,char** argv){try{if(argc!=2)throw std::runtime_error("usage: render_baseline_contracts REPOSITORY");run(fs::canonical(argv[1]));std::cout<<checks<<" exact committed render-baseline contracts passed\n";return 0;}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
