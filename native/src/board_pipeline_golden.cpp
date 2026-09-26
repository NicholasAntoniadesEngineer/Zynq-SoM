#include "board_pipeline_internal.hpp"
#include "gallery_diagram_internal.hpp"
#include "bringup_unicode.hpp"
#include <png.h>
#include <cmath>
#include <numeric>
#include <climits>

namespace schgen {
namespace {
// Independent separable implementation of the legacy bicubic filter (-0.5),
// with Pillow-compatible 22-bit coefficient/byte-pass rounding. Algorithm
// reference: https://github.com/python-pillow/Pillow/blob/main/src/libImaging/Resample.c
struct Tap {int first;std::vector<std::int64_t> weights;};
std::vector<Tap> taps(int size){
    std::vector<Tap> out;const double ratio=static_cast<double>(size)/16,stretch=std::max(1.0,ratio);
    for(int destination=0;destination<16;++destination){
        const double center=(destination+.5)*ratio;
        const int first=std::max(0,static_cast<int>(center-2*stretch+.5)),last=std::min(size,static_cast<int>(center+2*stretch+.5));
        std::vector<double> weights;double total=0;
        for(int source=first;source<last;++source){const double d=std::abs((source-center+.5)/stretch);
            const double w=d<1?((1.5*d-2.5)*d*d+1):d<2?(-.5*(((d-5)*d+8)*d-4)):0;weights.push_back(w);total+=w;}
        Tap t{first,{}};for(double w:weights){const double scaled=(w/total)*4194304;t.weights.push_back(static_cast<std::int64_t>(scaled+(scaled<0?-.5:.5)));}out.push_back(std::move(t));
    }
    return out;
}
unsigned char byte(std::int64_t sum){return static_cast<unsigned char>(std::clamp<std::int64_t>(sum/4194304,0,255));}
bool duplicate(const std::string& name){auto cp=document_detail::codepoints(name);if(!cp.empty()&&cp.back()=='\n')cp.pop_back();std::size_t k=cp.size();while(k&&bringup_detail::decimal_digit(cp[k-1])>=0)--k;return k<cp.size()&&k&&cp[k-1]==' ';}
}
std::string board_png_average_hash(const std::filesystem::path& path){
    png_image image{};image.version=PNG_IMAGE_VERSION;
    struct Cleanup{png_image& p;~Cleanup(){png_image_free(&p);}} cleanup{image};
    if(!png_image_begin_read_from_file(&image,path.c_str()))throw ProjectError("golden PNG read: "+std::string(image.message));
    if(!image.width||!image.height||image.width>INT_MAX/4||image.height>INT_MAX/4||static_cast<std::uint64_t>(image.width)*image.height>536870912)
        throw ProjectError("golden PNG dimensions out of range");
    image.format=PNG_FORMAT_RGBA;std::vector<unsigned char> rgba(PNG_IMAGE_SIZE(image));
    if(!png_image_finish_read(&image,nullptr,rgba.data(),0,nullptr))throw ProjectError("golden PNG decode: "+std::string(image.message));
    const int width=static_cast<int>(image.width),height=static_cast<int>(image.height);
    std::vector<unsigned char> gray(static_cast<std::size_t>(width)*height);
    for(std::size_t i=0;i<gray.size();++i)gray[i]=static_cast<unsigned char>((19595*rgba[i*4]+38470*rgba[i*4+1]+7471*rgba[i*4+2]+32768)/65536);
    const auto horizontal=taps(width),vertical=taps(height);std::vector<unsigned char> intermediate(static_cast<std::size_t>(height)*16);
    for(int y=0;y<height;++y)for(int x=0;x<16;++x){const auto& t=horizontal[x];std::int64_t sum=2097152;
        for(std::size_t j=0;j<t.weights.size();++j)sum+=t.weights[j]*gray[static_cast<std::size_t>(y)*width+t.first+j];intermediate[static_cast<std::size_t>(y)*16+x]=byte(sum);}
    std::array<unsigned char,256> output{};
    for(int y=0;y<16;++y)for(int x=0;x<16;++x){const auto& t=vertical[y];std::int64_t sum=2097152;
        for(std::size_t j=0;j<t.weights.size();++j)sum+=t.weights[j]*intermediate[(t.first+j)*16+x];output[y*16+x]=byte(sum);}
    const auto sum=std::accumulate(output.begin(),output.end(),std::uint64_t{});std::string hash;for(auto v:output)hash+=static_cast<std::uint64_t>(v)*256>sum?'1':'0';return hash;
}
BoardGoldenResult check_board_golden(const std::filesystem::path& renders,bool bless){
    using namespace board_pipeline_detail;BoardGoldenResult out;
    if(fs::is_directory(renders))for(const auto& entry:fs::directory_iterator(renders)){
        const auto name=entry.path().filename().string(),stem=entry.path().stem().string();
        if(!entry.is_regular_file()||name.size()<4||name.substr(name.size()-4)!=".png"||stem.rfind("ratsnest",0)==0||duplicate(stem))continue;
        out.current.emplace(stem,board_png_average_hash(entry.path()));}
    const auto path=renders/"golden.json";out.have_baseline=fs::exists(path);
    if(bless){JsonNode value;value.kind=JsonKind::Object;for(const auto& [name,hash]:out.current)value.object_value.emplace_back(name,text(hash));
        publish_text(path,json(value)+"\n");out.match=true;out.blessed=true;return out;}
    if(!out.have_baseline){out.drift.push_back("no golden baseline; explicit --bless required");return out;}
    const auto baseline=parse_json_file(path.string());if(baseline.kind!=JsonKind::Object)throw ProjectError("golden baseline must be an object");
    std::map<std::string,std::string> old;for(const auto& [name,value]:baseline.object_value){if(value.kind!=JsonKind::String||value.string_value.size()!=256||value.string_value.find_first_not_of("01")!=std::string::npos)throw ProjectError("invalid golden hash: "+name);if(!old.emplace(name,value.string_value).second)throw ProjectError("duplicate golden sheet: "+name);}
    for(const auto& [name,hash]:out.current){const auto it=old.find(name);if(it==old.end())out.drift.push_back(name+": NEW sheet (no golden)");else{int distance=0;for(std::size_t i=0;i<hash.size();++i)distance+=hash[i]!=it->second[i];if(distance>12)out.drift.push_back(name+": drift "+std::to_string(distance)+"/256 bits");}}
    for(const auto& [name,hash]:old){(void)hash;if(!out.current.count(name))out.drift.push_back(name+": golden exists but no render");}
    out.match=out.drift.empty();return out;
}
std::string BoardGoldenResult::summary()const{return blessed?"golden renders: BLESSED "+std::to_string(current.size())+" sheets":match?"golden renders: "+std::to_string(current.size())+" sheets match":"golden renders: DRIFT (explicit --bless to accept):\n"+board_pipeline_detail::join(drift,"\n");}
}
