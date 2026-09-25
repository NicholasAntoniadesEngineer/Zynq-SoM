#include "manufacturing_assembly_internal.hpp"
#include "manufacturing_assembly_font.hpp"
#include <zlib.h>
#include <array>
#include <climits>
#include <future>
#include <thread>

namespace schgen {
using namespace assembly_detail;
namespace {
using Color=std::array<unsigned char,3>;
constexpr Color background{15,17,21},highlight{70,160,255},foreground{240,240,245};
const Glyph& glyph(int code) { for(const auto& g:glyphs)if(g.code==code)return g;return glyphs[0]; }
int nibble(char c) { return c<='9'?c-'0':c-'a'+10; }
struct Raster {
    int width,height;
    std::string pixels;
    Raster(int w,int h):width(w),height(h),pixels(static_cast<std::size_t>(w)*h*3,'\0') {
        for(std::size_t i=0;i<pixels.size();++i)pixels[i]=static_cast<char>(background[i%3]);
    }
    void pixel(int x,int y,Color color,int alpha=255) {
        if(x<0||x>=width||y<0||y>=height)return;
        auto i=(static_cast<std::size_t>(y)*width+x)*3;
        for(int c=0;c<3;++c){auto old=static_cast<unsigned char>(pixels[i+c]);int v=old*(255-alpha)+color[c]*alpha+128;pixels[i+c]=static_cast<char>((v+(v>>8))>>8);}
    }
    void rect(double x0,double y0,double x1,double y1,std::optional<Color> fill,Color outline,int thick) {
        if(!std::isfinite(x0)||!std::isfinite(y0)||!std::isfinite(x1)||!std::isfinite(y1)||x1<x0||y1<y0)throw ProjectError("invalid assembly rectangle");
        if(std::max({std::abs(x0),std::abs(x1),std::abs(y0),std::abs(y1)})>INT_MAX/2)throw ProjectError("assembly rectangle out of range");
        int a=static_cast<int>(x0),b=static_cast<int>(y0),c=static_cast<int>(x1),d=static_cast<int>(y1);
        for(int y=std::max(b,0);y<=std::min(d,height-1);++y)for(int x=std::max(a,0);x<=std::min(c,width-1);++x){
            if(x-a<thick||c-x<thick||y-b<thick||d-y<thick)pixel(x,y,outline);else if(fill)pixel(x,y,*fill);
        }
    }
    Box4 text_box(double x,double y,const std::string& text)const {
        int pen=0,left=0,right=0,top=0,bottom=0;bool first=true;
        for(const auto& [cp,bytes]:verification::utf8(text)){(void)bytes;const auto& g=glyph(static_cast<int>(cp));
            left=std::min(left,pen+g.x);right=std::max(right,pen+g.x+g.width);pen+=g.advance;right=std::max(right,pen);
            if(g.height){top=first?g.y:std::min(top,g.y);bottom=std::max(bottom,g.y+g.height);first=false;}
        }return {x+left,y+top,x+right,y+bottom};
    }
    void text(double x,double y,const std::string& text,Color color) {
        // FreeType quantizes the fractional start to 26.6 coordinates, then
        // rounds the transformed origin (y is inverted in font coordinates).
        const auto fx=std::floor(x),fy=std::floor(y);
        const int origin=static_cast<int>(fx+std::floor((std::floor((x-fx)*64+.5)+32)/64));
        const int base=static_cast<int>(fy-std::floor((32-std::floor((y-fy)*64+.5))/64));
        const auto bounds=text_box(0,0,text);const int left=static_cast<int>(bounds.x0),top=static_cast<int>(bounds.y0),width=static_cast<int>(bounds.x1)-left,height=static_cast<int>(bounds.y1)-top;
        if(width<=0||height<=0)return;std::vector<unsigned char> mask(static_cast<std::size_t>(width)*height,0);int pen=0;
        for(const auto& [cp,bytes]:verification::utf8(text)){(void)bytes;const auto& g=glyph(static_cast<int>(cp));
            for(int yy=0;yy<g.height;++yy)for(int xx=0;xx<g.width;++xx){const auto i=2*(yy*g.width+xx);const int a=nibble(g.pixels[i])*16+nibble(g.pixels[i+1]);auto& v=mask.at(static_cast<std::size_t>(g.y+yy-top)*width+pen+g.x+xx-left);const int t=a*(255-v)+128;v=static_cast<unsigned char>(v+((t+(t>>8))>>8));}
            pen+=g.advance;
        }
        for(int yy=0;yy<height;++yy)for(int xx=0;xx<width;++xx){auto a=mask[static_cast<std::size_t>(yy)*width+xx];if(a)pixel(origin+left+xx,base+top+yy,color,a);}
    }
};
void be32(std::string& out,uint32_t n) {for(int s=24;s>=0;s-=8)out+=static_cast<char>((n>>s)&255);}
void chunk(std::string& out,const char* tag,const std::string& bytes) {
    be32(out,static_cast<uint32_t>(bytes.size()));auto start=out.size();out.append(tag,4);out+=bytes;
    auto sum=crc32(0,reinterpret_cast<const Bytef*>(out.data()+start),static_cast<uInt>(bytes.size()+4));be32(out,static_cast<uint32_t>(sum));
}
int paeth(int a,int b,int c) {int p=a+b-c,pa=std::abs(p-a),pb=std::abs(p-b),pc=std::abs(p-c);return pa<=pb&&pa<=pc?a:pb<=pc?b:c;}
std::string png(const Raster& im) {
    // PNG's adaptive filter selects the lowest sum of signed-byte magnitudes.
    // Pillow's optimize=True also tries average, preserving its tie ordering.
    const auto stride=static_cast<std::size_t>(im.width)*3;std::string filtered;filtered.reserve((stride+1)*im.height);
    for(int y=0;y<im.height;++y){std::string best;std::size_t cost=std::numeric_limits<std::size_t>::max();int best_filter=0;
        for(int filter:{0,2,1,3,4}){if(cost==0)break;std::string row(stride,'\0');std::size_t score=0;
            for(std::size_t x=0;x<stride;++x){int v=static_cast<unsigned char>(im.pixels[static_cast<std::size_t>(y)*stride+x]);int a=x>=3?static_cast<unsigned char>(im.pixels[static_cast<std::size_t>(y)*stride+x-3]):0;int b=y?static_cast<unsigned char>(im.pixels[static_cast<std::size_t>(y-1)*stride+x]):0;int c=y&&x>=3?static_cast<unsigned char>(im.pixels[static_cast<std::size_t>(y-1)*stride+x-3]):0;
                int pred=filter==1?a:filter==2?b:filter==3?(a+b)/2:filter==4?paeth(a,b,c):0;auto byte=static_cast<unsigned char>(v-pred);row[x]=static_cast<char>(byte);score+=std::min(static_cast<int>(byte),256-static_cast<int>(byte));
                // Scores only increase; ties keep the earlier filter. Avoid
                // evaluating the rest of a row that cannot improve the result.
                if(score>=cost)break;}
            if(score<cost){cost=score;best=std::move(row);best_filter=filter;}
        }filtered+=static_cast<char>(best_filter);filtered+=best;
    }
    z_stream z{};if(deflateInit2(&z,9,Z_DEFLATED,15,9,Z_FILTERED)!=Z_OK)throw ProjectError("cannot initialize assembly PNG compressor");
    std::string compressed;std::array<unsigned char,65536> buffer{};z.next_in=reinterpret_cast<Bytef*>(filtered.data());z.avail_in=static_cast<uInt>(filtered.size());
    int result=Z_OK;do{z.next_out=buffer.data();z.avail_out=buffer.size();result=deflate(&z,Z_FINISH);compressed.append(reinterpret_cast<const char*>(buffer.data()),buffer.size()-z.avail_out);}while(result==Z_OK);deflateEnd(&z);
    if(result!=Z_STREAM_END)throw ProjectError("assembly PNG compression failed");
    std::string out="\x89PNG\r\n\x1a\n",header;be32(header,im.width);be32(header,im.height);header.append("\x08\x02\0\0\0",5);chunk(out,"IHDR",header);
    for(std::size_t n=0;n<compressed.size();n+=65536)chunk(out,"IDAT",compressed.substr(n,65536));chunk(out,"IEND","");return out;
}
std::string stage(const PcbModel& m,const PcbCheckInput& geo,Indices done,Indices current,const std::string& caption,std::optional<Box4> mate) {
    constexpr double scale=5,pad=28;
    if(!std::isfinite(m.board_w)||!std::isfinite(m.board_h)||m.board_w<0||m.board_h<0||m.board_w>4000||m.board_h>4000)throw ProjectError("assembly image dimensions out of range");
    const auto w=static_cast<int>(m.board_w*scale+2*pad),h=static_cast<int>(m.board_h*scale+2*pad);
    if(static_cast<long long>(w)*h>50'000'000)throw ProjectError("assembly image exceeds 50 million pixels");
    Raster im(w,h);auto px=[&](double x){return pad+(x-m.origin_x)*scale;};auto py=[&](double y){return pad+(y-m.origin_y)*scale;};
    auto rect=[&](const Box4& b,std::optional<Color> fill,Color edge,int thick){im.rect(px(b.x0),py(b.y0),px(b.x1),py(b.y1),fill,edge,thick);};
    im.rect(pad,pad,pad+m.board_w*scale,pad+m.board_h*scale,Color{22,25,34},Color{229,231,235},2);
    if(m.som_keepout)rect(*m.som_keepout,std::nullopt,{201,148,32},1);
    sort_indices(done,m);sort_indices(current,m);
    for(auto i:done)rect(geo.courtyard_at(i),m.insts.at(i).side=="top"?Color{60,66,78}:Color{40,44,54},background,1);
    for(auto i:current){const auto b=geo.courtyard_at(i);rect(b,highlight,background,1);if(m.insts.at(i).side=="bottom")rect(b,std::nullopt,{255,230,120},2);}
    if(mate){rect(*mate,std::nullopt,highlight,3);im.text(px(mate->x0)+4,py(mate->y0)+4,"SoM module",foreground);}
    std::vector<Box4> placed;
    for(auto i:current){const auto b=geo.courtyard_at(i);for(const auto& [x,y]:std::vector<std::pair<double,double>>{{px(b.x0),py(b.y0)-11},{px(b.x0),py(b.y1)+2}}){auto t=im.text_box(x,y,m.insts.at(i).ref);
        if(t.x0>=0&&t.y0>=0&&t.x1<=w&&t.y1<=h&&std::all_of(placed.begin(),placed.end(),[&](const auto& p){return t.x1<p.x0||t.x0>p.x1||t.y1<p.y0||t.y0>p.y1;})){im.text(x,y,m.insts.at(i).ref,foreground);placed.push_back(t);break;}}
    }
    im.text(8,6,caption,{203,213,225});return png(im);
}
}
std::vector<AssemblyImage> render_assembly_images(const PcbModel& m,const AssemblyPlan& plan) {
    partition(m,plan.steps,"step");partition(m,plan.phases,"phase");PcbCheckInput geo(m);Indices done;
    struct Job { std::string filename,caption; Indices done,current; std::optional<Box4> mate; };
    std::vector<Job> jobs;
    for(const auto& s:plan.steps){jobs.push_back({step_filename(s),"step "+std::to_string(s.n)+"/"+std::to_string(plan.steps.size())+" - "+s.title+" ("+std::to_string(s.insts.size())+" parts)",done,s.insts,std::nullopt});done.insert(done.end(),s.insts.begin(),s.insts.end());}
    done.clear();for(const auto& p:plan.phases){jobs.push_back({phase_filename(p),"phase "+std::to_string(p.n)+"/"+std::to_string(plan.phases.size())+" - "+p.title+" ("+std::to_string(p.insts.size())+" parts)",done,p.insts,p.slug=="som_mate"?m.som_core:std::nullopt});done.insert(done.end(),p.insts.begin(),p.insts.end());}
    std::vector<AssemblyImage> out(jobs.size());
    // Independent immutable snapshots, bounded memory/CPU use, stable output
    // order. Futures join even on exceptions, before referenced data is freed.
    const auto workers=std::min<std::size_t>({4,jobs.size(),std::max(1u,std::thread::hardware_concurrency())});
    std::vector<std::future<void>> pending;
    for(std::size_t worker=0;worker<workers;++worker)
        pending.push_back(std::async(std::launch::async,[&,worker]{
            for(std::size_t i=worker;i<jobs.size();i+=workers){const auto& job=jobs[i];
                out[i]={job.filename,stage(m,geo,job.done,job.current,job.caption,job.mate)};
            }
        }));
    for(auto& task:pending)task.get();
    return out;
}
std::string render_assembly_stage_image(const PcbModel& model,
        const std::vector<std::size_t>& done, const std::vector<std::size_t>& current,
        const std::string& caption, const std::optional<Box4>& mate) {
    return stage(model, PcbCheckInput(model), done, current, caption, mate);
}
} // namespace schgen
