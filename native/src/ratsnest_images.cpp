#include "ratsnest_documents_internal.hpp"
#include <functional>
#include <future>
#include <thread>

namespace schgen {
using namespace ratsnest_detail;
namespace {
std::vector<std::size_t> ordered(const PcbModel& m){std::vector<std::size_t> out;for(std::size_t i=0;i<m.insts.size();++i)out.push_back(i);
    std::stable_sort(out.begin(),out.end(),[&](auto a,auto b){return m.insts[a].ref<m.insts[b].ref;});return out;}
RatsnestImage board(const PcbModel& m,const PcbCheckInput& geo,const RatsnestPalette& palette,
        const RatsnestNets& nets,const RatsnestEdges& edges,const std::string& side) {
    Raster im(m.board_w*4+56,m.board_h*4+56);
    auto px=[&](double x){return 28+(x-m.origin_x)*4;};auto py=[&](double y){return 28+(y-m.origin_y)*4;};
    auto rect=[&](Box4 b,const std::optional<Rgba>& fill,Rgba edge,int thick){im.rectangle({px(b.x0),py(b.y0),px(b.x1),py(b.y1)},fill,edge,thick);};
    im.rectangle({28,28,28+m.board_w*4,28+m.board_h*4},Rgba{22,25,34,255},{229,231,235,255},2);
    if(m.som_keepout)rect(*m.som_keepout,std::nullopt,{201,148,32,255},1);
    for(const auto& a:ratsnest_airwires(m,nets,edges,side))im.line(px(a.x0),py(a.y0),px(a.x1),py(a.y1),a.cross?Rgba{255,59,48,230}:Rgba{120,132,150,130},a.cross?2:1);
    // The legacy mounting-hole exception is followed by an unconditional side
    // check: holes, like other instances, are drawn only on their actual side.
    for(auto i:ordered(m))if(m.insts[i].side==side)rect(geo.courtyard_at(i),rgba(color(palette,m.insts[i].sheet),235),outline,1);
    return image("ratsnest_"+side+".png",im);
}
RatsnestImage sheet(const PcbModel& m,const PcbCheckInput& geo,const std::string& name,
        const std::set<std::string>& refs,const std::set<std::string>& som,const RatsnestNets& nets,const RatsnestEdges& edges) {
    std::map<std::string,std::size_t> indices;for(std::size_t i=0;i<m.insts.size();++i)indices[m.insts[i].ref]=i;
    std::optional<Box4> bounds;auto add=[&](Box4 b){bounds=bounds?united(*bounds,b):b;};
    for(const auto& r:refs)add(geo.courtyard_at(indices.at(r)));for(const auto& r:som)add(geo.courtyard_at(indices.at(r)));
    if(!som.empty()&&m.som_keepout)add(*m.som_keepout);
    if(!bounds)throw ProjectError("ratsnest: empty sheet bounds");
    Box4 view{bounds->x0-10,bounds->y0-10,bounds->x1+10,bounds->y1+10};Raster im((view.x1-view.x0)*12,(view.y1-view.y0)*12);
    auto px=[&](double x){return (x-view.x0)*12;};auto py=[&](double y){return (y-view.y0)*12;};
    auto rect=[&](Box4 b,const std::optional<Rgba>& fill,Rgba edge,int thick){im.rectangle({px(b.x0),py(b.y0),px(b.x1),py(b.y1)},fill,edge,thick);};
    if(m.som_keepout)rect(*m.som_keepout,std::nullopt,{201,148,32,255},2);
    for(const auto& [ref,i]:indices){const auto b=geo.courtyard_at(i);if(b.x1<view.x0||b.x0>view.x1||b.y1<view.y0||b.y0>view.y1)continue;
        const bool own=refs.count(ref),top=m.insts[i].side=="top";Rgba fill;
        if(own)fill=top?Rgba{70,160,255,235}:Rgba{255,170,60,235};
        else if(som.count(ref))fill=top?Rgba{110,150,190,235}:Rgba{80,105,135,235};
        else fill=top?Rgba{60,66,78,200}:Rgba{40,44,54,200};
        rect(b,fill,outline,1);if(own&&!top)rect(b,std::nullopt,{255,230,120,255},2);
    }
    for(const auto& [name_,pts]:nets){if(std::none_of(pts.begin(),pts.end(),[&](const auto& p){return refs.count(std::get<2>(p));}))continue;
        for(const auto& [a,b]:edges.at(name_)){const auto& [xa,ya,ra,sa]=pts[a];const auto& [xb,yb,rb,sb]=pts[b];(void)sa;(void)sb;
            const bool own=refs.count(ra)&&refs.count(rb),to_som=(refs.count(ra)&&som.count(rb))||(refs.count(rb)&&som.count(ra)),leaves=refs.count(ra)!=refs.count(rb);
            const double distance=std::abs(xb-xa)+std::abs(yb-ya);const auto c=own?Rgba{120,220,160,220}:to_som?Rgba{255,59,48,235}:leaves?Rgba{255,110,100,130}:Rgba{110,118,132,70};
            im.line(px(xa),py(ya),px(xb),py(yb),c,to_som||(own&&distance>12)?2:1);
        }
    }
    for(const auto& ref:refs){const auto b=geo.courtyard_at(indices.at(ref));im.text(px(b.x0),py(b.y0)-11,ref,{240,240,245,255});}
    return image("ratsnest/"+name+".png",im);
}
}
RatsnestImage render_ratsnest_board_image(const PcbModel& m,const RatsnestPalette& palette,const std::string& side,const RatsnestNets& nets,const RatsnestEdges& edges) {
    validate(m,nets,edges);if(side!="top"&&side!="bottom")throw ProjectError("ratsnest: invalid requested side");
    return board(m,PcbCheckInput(m),palette,nets,edges,side);
}
RatsnestImage render_ratsnest_sheet_image(const PcbModel& m,const std::string& name,const std::set<std::string>& refs,const RatsnestNets& nets,const RatsnestEdges& edges,const std::set<std::string>& som) {
    validate(m,nets,edges);safe_sheet(name);std::set<std::string> known;for(const auto& i:m.insts)known.insert(i.ref);
    for(const auto* group:{&refs,&som})for(const auto& ref:*group)if(!known.count(ref))throw ProjectError("ratsnest: unknown sheet reference "+ref);
    return sheet(m,PcbCheckInput(m),name,refs,som,nets,edges);
}
namespace {
std::vector<RatsnestImage> images(const PcbModel& m,const RatsnestPalette* palette,const RatsnestNets& nets,const RatsnestEdges& edges) {
    validate(m,nets,edges);PcbCheckInput geo(m);
    std::vector<std::function<RatsnestImage()>> jobs;
    if(palette){
        jobs.emplace_back([&]{return board(m,geo,*palette,nets,edges,"top");});
        jobs.emplace_back([&]{return board(m,geo,*palette,nets,edges,"bottom");});
    }
    std::map<std::string,std::set<std::string>> sheets;std::set<std::string> som;
    for(const auto& inst:m.insts){sheets[inst.sheet].insert(inst.ref);if(starts(inst.sheet,"som_"))som.insert(inst.ref);}
    for(const auto& [name,refs]:sheets)if(!starts(name,"som_"))jobs.emplace_back([&,name=name,refs=refs]{return sheet(m,geo,name,refs,som,nets,edges);});
    if(!som.empty())jobs.emplace_back([&]{return sheet(m,geo,"som",som,{},nets,edges);});
    std::vector<RatsnestImage> out(jobs.size());
    const auto workers=std::min<std::size_t>({4,jobs.size(),std::max(1u,std::thread::hardware_concurrency())});
    std::vector<std::future<void>> pending;
    for(std::size_t worker=0;worker<workers;++worker)
        pending.push_back(std::async(std::launch::async,[&,worker]{
            for(std::size_t index=worker;index<jobs.size();index+=workers)out[index]=jobs[index]();
        }));
    for(auto& task:pending)task.get();
    return out;
}
}
std::vector<RatsnestImage> render_ratsnest_subsystem_images(const PcbModel& m,const RatsnestNets& nets,const RatsnestEdges& edges) {
    return images(m,nullptr,nets,edges);
}
std::vector<RatsnestImage> render_ratsnest_images(const PcbModel& m,const RatsnestPalette& palette,const RatsnestNets& nets,const RatsnestEdges& edges) {
    return images(m,&palette,nets,edges);
}
} // namespace schgen
