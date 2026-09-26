#include "ratsnest_documents_internal.hpp"
#include "manufacturing_assembly_font.hpp"
#include "verification_internal.hpp"
#include <zlib.h>

// The scan-conversion rules below are adapted from Pillow 12.2.0 Draw.c;
// storage, bounds checking and C++ ownership are specific to this implementation.
// https://github.com/python-pillow/Pillow/blob/12.2.0/src/libImaging/Draw.c
// Copyright (c) 1996-2006 Fredrik Lundh; 1997-2006 Secret Labs AB.
// PIL: Copyright 1997-2011 Secret Labs AB; 1995-2011 Fredrik Lundh and contributors.
// Pillow: Copyright 2010 Jeffrey 'Alex' Clark and contributors.
// MIT-CMU License:
// By obtaining, using, and/or copying this software and/or its associated
// documentation, you agree that you have read, understood, and will comply
// with the following terms and conditions:
// Permission to use, copy, modify and distribute this software and its
// documentation for any purpose and without fee is hereby granted,
// provided that the above copyright notice appears in all copies, and that
// both that copyright notice and this permission notice appear in supporting
// documentation, and that the name of Secret Labs AB or the author not be
// used in advertising or publicity pertaining to distribution of the software
// without specific, written prior permission.
// SECRET LABS AB AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS
// SOFTWARE, INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS.
// IN NO EVENT SHALL SECRET LABS AB OR THE AUTHOR BE LIABLE FOR ANY SPECIAL,
// INDIRECT OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
// LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE
// OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
// PERFORMANCE OF THIS SOFTWARE.

namespace schgen::ratsnest_detail {
int raster_size(double n) {
    if(!std::isfinite(n)||n<1||n>50000)throw ProjectError("ratsnest: image dimension out of range");
    return static_cast<int>(n);
}
namespace {
int coordinate(double v) {
    if(!std::isfinite(v)||std::abs(v)>50'000'000)throw ProjectError("ratsnest: raster coordinate out of range");
    return static_cast<int>(v);
}
int down(double v){return static_cast<int>(std::copysign(std::ceil(std::abs(v)-.5),v));}
// Pillow performs the positive scan-line half-pixel addition/subtraction in
// float, before promotion into floor/ceil. Preserve that rounding boundary.
int up(float v){return v>=0?static_cast<int>(std::floor(v+.5F)):-static_cast<int>(std::floor(std::abs(static_cast<double>(v))+.5));}
int down(float v){return v>=0?static_cast<int>(std::ceil(v-.5F)):-static_cast<int>(std::ceil(std::abs(static_cast<double>(v))-.5));}
struct Edge {
    int x0,y0,xmin,xmax,ymin,ymax;
    float slope;
    Edge(int x,int y,int xx,int yy):x0(x),y0(y),xmin(std::min(x,xx)),xmax(std::max(x,xx)),
        ymin(std::min(y,yy)),ymax(std::max(y,yy)),slope(y==yy?0:static_cast<float>(xx-x)/(yy-y)){}
    // The captured arm64 Pillow build fuses this single-precision operation.
    // Model it explicitly so -ffp-contract=off remains valid everywhere else.
    float at(int y)const{return std::fma(static_cast<float>(y-y0),slope,static_cast<float>(x0));}
};
void polygon(Raster& im,const std::array<std::pair<int,int>,4>& vertices,Rgba color) {
    std::vector<Edge> edges;int ymin=im.height-1,ymax=0;
    for(std::size_t i=0;i<vertices.size();++i){auto a=vertices[i],b=vertices[(i+1)%vertices.size()];
        edges.emplace_back(a.first,a.second,b.first,b.second);ymin=std::min(ymin,edges.back().ymin);ymax=std::max(ymax,edges.back().ymax);}
    std::vector<const Edge*> active;for(const auto& e:edges)if(e.ymin!=e.ymax)active.push_back(&e);
    ymin=std::max(ymin,0);ymax=std::min(ymax,im.height);
    for(int y=ymin;y<=ymax;++y){std::vector<float> intersections;
        for(std::size_t i=0;i<active.size();++i){const auto& e=*active[i];if(y<e.ymin||y>e.ymax)continue;
            intersections.push_back(e.at(y));
            if(y==e.ymax&&y<ymax)intersections.push_back(intersections.back());
            else if((y==e.ymin||y==e.ymax)&&e.slope!=0){
                for(std::size_t j=0;j<i;++j){const auto& other=*active[j];
                    if((y!=other.ymin&&y!=other.ymax)||other.slope==0||std::round(intersections.back())!=std::round(other.at(y)))continue;
                    const int adjacent=y+(y==e.ymax?-1:1);
                    if(adjacent<other.ymin||adjacent>other.ymax)continue;
                    const auto a=e.at(adjacent),b=other.at(adjacent);
                    if(intersections.back()>a+1&&intersections.back()>b+1)intersections.back()=std::round(std::max(a,b))+1;
                    else if(intersections.back()<a-1&&intersections.back()<b-1)intersections.back()=std::round(std::min(a,b))-1;
                    break;
                }
            }
        }
        std::sort(intersections.begin(),intersections.end());int pos=intersections.empty()?-1:0;
        auto horizontal=[&]{for(const auto& e:edges)if(e.ymin==y&&e.ymax==y){
            if(pos!=-1&&pos<e.xmin)continue;
            const int start=std::max(pos,e.xmin);if(e.xmax<start)continue;
            im.hline(start,y,e.xmax,color);pos=e.xmax+1;
        }};
        for(std::size_t i=1;i<intersections.size();i+=2){const int end=down(intersections[i]);if(end<pos)continue;
            horizontal();if(end<pos)continue;const int start=std::max(pos,up(intersections[i-1]));if(end<start)continue;
            im.hline(start,y,end,color);pos=end+1;
        }horizontal();
    }
}
const assembly_detail::Glyph& glyph(int cp){for(const auto& g:assembly_detail::glyphs)if(g.code==cp)return g;return assembly_detail::glyphs[0];}
int nibble(char c){return c<='9'?c-'0':c-'a'+10;}
void be32(std::string& out,std::uint32_t n){for(int shift=24;shift>=0;shift-=8)out+=static_cast<char>((n>>shift)&255);}
void chunk(std::string& out,const char* tag,const std::string& data){be32(out,static_cast<std::uint32_t>(data.size()));const auto start=out.size();out.append(tag,4);out+=data;
    be32(out,static_cast<std::uint32_t>(crc32(0,reinterpret_cast<const Bytef*>(out.data()+start),static_cast<uInt>(data.size()+4))));}
int paeth(int a,int b,int c){const int p=a+b-c,aa=std::abs(p-a),bb=std::abs(p-b),cc=std::abs(p-c);return aa<=bb&&aa<=cc?a:bb<=cc?b:c;}
}
Raster::Raster(double w,double h):width(raster_size(w)),height(raster_size(h)){
    if(static_cast<long long>(width)*height>50'000'000)throw ProjectError("ratsnest: image exceeds 50 million pixels");
    pixels.resize(static_cast<std::size_t>(width)*height*3);for(std::size_t i=0;i<pixels.size();++i)pixels[i]=static_cast<char>(background[i%3]);
}
void Raster::pixel(int x,int y,Rgba c){if(x<0||y<0||x>=width||y>=height)return;const auto i=(static_cast<std::size_t>(y)*width+x)*3;
    for(int k=0;k<3;++k){const int value=static_cast<unsigned char>(pixels[i+k])*(255-c[3])+c[k]*c[3]+128;pixels[i+k]=static_cast<char>((value+(value>>8))>>8);}}
void Raster::hline(int x0,int y,int x1,Rgba c){if(y<0||y>=height)return;for(int x=std::max(0,x0);x<=std::min(width-1,x1);++x)pixel(x,y,c);}
void Raster::rectangle(Box4 b,const std::optional<Rgba>& fill,Rgba edge,int thick){
    if(b.x1<b.x0||b.y1<b.y0||thick<1)throw ProjectError("ratsnest: invalid raster rectangle");
    const int x0=coordinate(b.x0),y0=coordinate(b.y0),x1=coordinate(b.x1),y1=coordinate(b.y1);
    for(int y=std::max(0,y0);y<=std::min(height-1,y1);++y)for(int x=std::max(0,x0);x<=std::min(width-1,x1);++x){
        if(fill)pixel(x,y,*fill);if(x-x0<thick||x1-x<thick||y-y0<thick||y1-y<thick)pixel(x,y,edge);}
}
void Raster::line(double xa,double ya,double xb,double yb,Rgba c,int width_){
    int x=coordinate(xa),y=coordinate(ya);const int end_x=coordinate(xb),end_y=coordinate(yb);
    const int dx=end_x-x,dy=end_y-y;
    if(width_==2){if(!dx&&!dy){pixel(x,y,c);return;}
        const double length=std::hypot(dx,dy);const int ox=down(dy/length),oy=down(dx/length);
        polygon(*this,{{{x,y+oy},{end_x,end_y+oy},{end_x+ox,end_y},{x+ox,y}}},c);return;}
    if(width_!=1)throw ProjectError("ratsnest: only line widths one and two are supported");
    const int ax=std::abs(dx),ay=std::abs(dy),sx=dx<0?-1:1,sy=dy<0?-1:1;
    if(ax>ay){int error=2*ay-ax;for(int i=0;i<ax;++i){pixel(x,y,c);if(error>=0){y+=sy;error-=2*ax;}error+=2*ay;x+=sx;}}
    else{int error=2*ax-ay;for(int i=0;i<ay;++i){pixel(x,y,c);if(error>=0){x+=sx;error-=2*ay;}error+=2*ax;y+=sy;}}
    pixel(end_x,end_y,c);
}
void Raster::text(double x,double y,const std::string& text,Rgba c){
    if(text.size()>100'000)throw ProjectError("ratsnest: text too long");
    const auto fx=std::floor(x),fy=std::floor(y);
    const int origin=coordinate(fx+std::floor((std::floor((x-fx)*64+.5)+32)/64));
    const int base=coordinate(fy-std::floor((32-std::floor((y-fy)*64+.5))/64));
    int pen=0,left=0,right=0,top=0,bottom=0;bool first=true;
    for(const auto& [cp,bytes]:verification::utf8(text)){(void)bytes;const auto& g=glyph(static_cast<int>(cp));
        left=std::min(left,pen+g.x);right=std::max(right,pen+g.x+g.width);pen+=g.advance;right=std::max(right,pen);
        if(g.height){top=first?g.y:std::min(top,g.y);bottom=std::max(bottom,g.y+g.height);first=false;}}
    const int w=right-left,h=bottom-top;if(w<=0||h<=0)return;
    if(static_cast<long long>(w)*h>1'000'000)throw ProjectError("ratsnest: text mask too large");
    std::vector<unsigned char> mask(static_cast<std::size_t>(w)*h);pen=0;
    for(const auto& [cp,bytes]:verification::utf8(text)){(void)bytes;const auto& g=glyph(static_cast<int>(cp));
        for(int yy=0;yy<g.height;++yy)for(int xx=0;xx<g.width;++xx){const auto i=2*(yy*g.width+xx);const int alpha=nibble(g.pixels[i])*16+nibble(g.pixels[i+1]);auto& v=mask.at(static_cast<std::size_t>(g.y+yy-top)*w+pen+g.x+xx-left);const int t=alpha*(255-v)+128;v=static_cast<unsigned char>(v+((t+(t>>8))>>8));}pen+=g.advance;}
    for(int yy=0;yy<h;++yy)for(int xx=0;xx<w;++xx){auto a=mask[static_cast<std::size_t>(yy)*w+xx];if(a){auto ink=c;ink[3]=static_cast<unsigned char>((a*c[3]+127)/255);pixel(origin+left+xx,base+top+yy,ink);}}
}
std::string Raster::png()const{
    // Same independent PNG encoder contract as assembly, kept local while its
    // parent-owned implementation is being integrated. No board-output assets.
    const auto stride=static_cast<std::size_t>(width)*3;std::string filtered;filtered.reserve((stride+1)*height);
    for(int y=0;y<height;++y){std::string best;auto cost=std::numeric_limits<std::size_t>::max();int best_filter=0;
        for(int filter:{0,2,1,3,4}){if(cost==0)break;std::string row(stride,'\0');std::size_t score=0;
            for(std::size_t x=0;x<stride;++x){const auto offset=static_cast<std::size_t>(y)*stride+x;
                const int v=static_cast<unsigned char>(pixels[offset]),a=x>=3?static_cast<unsigned char>(pixels[offset-3]):0,b=y?static_cast<unsigned char>(pixels[offset-stride]):0,cc=y&&x>=3?static_cast<unsigned char>(pixels[offset-stride-3]):0;
                const int predictor=filter==1?a:filter==2?b:filter==3?(a+b)/2:filter==4?paeth(a,b,cc):0;const auto byte=static_cast<unsigned char>(v-predictor);row[x]=static_cast<char>(byte);score+=std::min(static_cast<int>(byte),256-static_cast<int>(byte));
                if(score>=cost)break;}
            if(score<cost){cost=score;best=std::move(row);best_filter=filter;}}
        filtered+=static_cast<char>(best_filter);filtered+=best;}
    z_stream z{};if(deflateInit2(&z,9,Z_DEFLATED,15,9,Z_FILTERED)!=Z_OK)throw ProjectError("ratsnest: cannot initialize compressor");
    struct End{z_stream* stream;~End(){deflateEnd(stream);}} end{&z};
    std::string compressed;std::array<unsigned char,65536> buffer{};z.next_in=reinterpret_cast<Bytef*>(filtered.data());z.avail_in=static_cast<uInt>(filtered.size());
    int result;do{z.next_out=buffer.data();z.avail_out=buffer.size();result=deflate(&z,Z_FINISH);compressed.append(reinterpret_cast<const char*>(buffer.data()),buffer.size()-z.avail_out);}while(result==Z_OK);
    if(result!=Z_STREAM_END)throw ProjectError("ratsnest: PNG compression failed");
    std::string out="\x89PNG\r\n\x1a\n",header;be32(header,width);be32(header,height);header.append("\x08\x02\0\0\0",5);chunk(out,"IHDR",header);
    for(std::size_t i=0;i<compressed.size();i+=65536)chunk(out,"IDAT",compressed.substr(i,65536));chunk(out,"IEND","");return out;
}
} // namespace schgen::ratsnest_detail
