#include "pcb_checks_internal.hpp"

namespace schgen {
using namespace pcb_checks;
PcbCheckFootprintPtr pcb_check_footprint(std::string source,std::string bytes){
    auto doc=sexpr_loads(bytes);return pcb_check_footprint(std::move(source),std::move(bytes),std::move(doc));
}
PcbCheckFootprintPtr pcb_check_footprint(std::string source,std::string bytes,Sexpr document){
    if(!tag(document,"footprint")&&!tag(document,"module"))throw std::runtime_error("PCB footprint root required: "+source);
    auto fp=std::make_shared<PcbCheckFootprint>();fp->source=std::move(source);fp->bytes=std::move(bytes);fp->document=std::move(document);
    fp->pads=scan_pad_nodes(fp->document);
    // Orientation-only checks also accept a footprint containing just a model.
    try{fp->bbox=footprint_bbox(fp->document,3);}catch(const std::runtime_error& e){
        if(std::string(e.what())!="footprint_bbox: no measurable extent")throw;
    }
    return fp;
}
PcbCheckInput::PcbCheckInput(PcbCheckModel model):model_(std::move(model)){
    for(const auto& inst:model_.insts){
        if(!inst.mod){geometry_.push_back(std::nullopt);continue;}
        if(!std::isfinite(inst.x)||!std::isfinite(inst.y)||!std::isfinite(inst.rotation))throw std::runtime_error(inst.ref+": nonfinite placement");
        PcbCheckGeometry geo;if(inst.mod->bbox)geo.courtyard=inst_placed_box(*inst.mod->bbox,inst.x,inst.y,inst.rotation,4);
        std::vector<std::tuple<std::string,double,double,double,double,double>> named,typed;
        for(const auto& [name,type,x,y,r,w,h]:inst.mod->pads){named.emplace_back(name,x,y,r,w,h);typed.emplace_back(type,x,y,r,w,h);}
        auto local=pad_boxes_local(typed,inst.rotation);std::optional<Box4> hull;
        for(const auto& [type,x0,y0,x1,y1]:local){(void)type;Box4 b{x0,y0,x1,y1};hull=hull?united(*hull,b):b;}
        geo.pad_bbox=hull?std::optional<Box4>(inst_placed_box(*hull,inst.x,inst.y,0,3)):geo.courtyard;
        for(const auto& [name,x0,y0,x1,y1]:pad_boxes_named(named,inst.rotation))geo.pad_boxes[name]=translated({x0,y0,x1,y1},inst.x,inst.y);
        geometry_.push_back(std::move(geo));
    }
}
const PcbCheckGeometry& PcbCheckInput::geometry_at(std::size_t index)const{
    const auto& g=geometry_.at(index);if(!g)throw std::runtime_error(model_.insts.at(index).ref+": footprint geometry unresolved");return *g;
}
Box4 PcbCheckInput::courtyard_at(std::size_t index)const{
    const auto& g=geometry_at(index);if(!g.courtyard)throw std::runtime_error(model_.insts.at(index).ref+": footprint has no measurable extent");return *g.courtyard;
}
Box4 PcbCheckInput::pad_bbox_at(std::size_t index)const{
    const auto& g=geometry_at(index);if(!g.pad_bbox)throw std::runtime_error(model_.insts.at(index).ref+": footprint has no measurable extent");return *g.pad_bbox;
}
RefdesOverlapResult check_refdes_overlap(const Sexpr& pcb,bool enforce_bottom){
    RefdesOverlapResult res;std::vector<std::pair<std::string,Box4>> top,bot;
    // The verifier keys off the property's silk layer (not footprint Cu side).
    // collect_refdes_props has placement-specific side filtering, so reuse the
    // existing font/text/rotation primitives here on the exact document.
    if(!tag(pcb,"kicad_pcb"))throw std::runtime_error("PCB board root required");
    for(const auto& fp:*list(pcb)){
        if(!tag(fp,"footprint"))continue;auto at=child(fp,"at");if(!at)continue;
        auto [x,y]=xy(*at);double rot=at->size()>3&&std::holds_alternative<double>((*at)[3].v)?number(*at,3):0;
        for(const auto& prop:*list(fp)){
            if(!tag(prop,"property")||list(prop)->size()<3||atom((*list(prop))[1])!="Reference")continue;
            auto layer=child(prop,"layer"),hide=child(prop,"hide"),local=child(prop,"at");
            if(!layer||layer->size()<2||!local||(hide&&(hide->size()<2||atom((*hide)[1])=="yes")))continue;
            auto lay=atom((*layer)[1]);if(lay!="F.SilkS"&&lay!="B.SilkS")continue;
            const auto p=turn_point(number(*local,1),number(*local,2),rot);auto ref=atom((*list(prop))[2]);
            // text_box currently counts bytes; the gate's width is in Unicode
            // characters, as Python len(). Geometry only needs that count.
            std::size_t chars=0;for(unsigned char c:ref)if((c&0xc0)!=0x80)++chars;
            (lay=="F.SilkS"?top:bot).emplace_back(ref,text_box(std::string(chars,'x'),x+p.first,y+p.second,font_size(prop,1),0.15));
        }
    }
    res.n_top=static_cast<int>(top.size());res.n_bottom=static_cast<int>(bot.size());
    for(std::size_t i=0;i<top.size();++i)for(std::size_t j=i+1;j<top.size();++j)if(overlap_area(top[i].second,top[j].second)>0)res.top_pairs.emplace_back(top[i].first,top[j].first);
    for(std::size_t i=0;i<bot.size();++i)for(std::size_t j=i+1;j<bot.size();++j)if(overlap_area(bot[i].second,bot[j].second)>0)++res.bottom_pairs;
    res.ok=res.top_pairs.empty()&&(!enforce_bottom||res.bottom_pairs==0);return res;
}
} // namespace schgen
