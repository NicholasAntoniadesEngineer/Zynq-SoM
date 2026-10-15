// Frozen projection of the independently SHA-matched 8212 archive. No board,
// catalog, circuit, current footprint, shape constructor or search is loaded.
#include "floorplan_internal.hpp"
#include "pcb_placement_internal.hpp"
#include "schgen/pcb_checks.hpp"
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>

namespace {
using namespace schgen;
using floorplan_detail::Engine;
std::size_t checks=0;
void require(bool ok,const char* why){++checks;if(!ok)throw std::runtime_error(why);}
bool near(double a,double b){return std::abs(a-b)<.00011;}
bool same(Halo a,Halo b){return near(a.w,b.w)&&near(a.e,b.e)&&near(a.n,b.n)&&near(a.s,b.s);}
struct Frozen {
    FloorplanInput input;
    std::map<std::string,FloorplanZoneShape> shapes;
    std::map<std::string,std::tuple<Box4,int,bool>> footprint_expected;
};
Frozen read_fixture(const std::string& path) {
    std::ifstream f(path,std::ios::binary);
    require(bool(f),"missing frozen geometry fixture");
    const std::string bytes{std::istreambuf_iterator<char>(f),{}};
    require(pcb_sha256(bytes)=="3feda34442f1ce747668443cdc56f4261df7f37ab06d1a05036004fae2d3d296",
            "frozen geometry changed: investigate; do not refresh from current hardware");
    Frozen out;
    // Engine's required positive SoM dimensions are inert here: neither
    // initialize/prepare_geometry nor any whole-board path is called.
    out.input.som.w=1;out.input.som.h=1;out.input.compact_search=true;
    std::istringstream in(bytes);std::string tag;
    while(in>>tag) {
        if(tag=="SHAPE") {
            std::string name;int index;FloorplanZoneShape shape;
            in>>name>>index>>shape.w>>shape.h>>shape.side>>std::quoted(shape.tag);
            require((name=="bringup_rails"&&index==56)||(name=="ethernet"&&index==0),"wrong archived shape");
            while(in>>tag&&tag=="PART") {
                std::string ref;bool primary,mirror;double x,y,extra,conn;int id;Box4 b;
                in>>ref>>primary>>x>>y>>extra>>conn>>id>>mirror>>b.x0>>b.y0>>b.x1>>b.y1;
                const auto key=std::to_string(id);
                (primary?shape.top_off:shape.bot_off)[ref]={x,y};
                shape.extra_rot[ref]=extra;out.input.geometry.conn_rot[ref]=conn;
                out.input.geometry.resolvable[ref]=key;out.input.geometry.bbox_of[ref]=b;
                if(mirror)shape.mirror[ref]=key;
            }
            require(tag=="ENDSHAPE"&&bool(in),"truncated shape fixture");
            require(out.shapes.emplace(name,std::move(shape)).second,"duplicate shape");
        } else if(tag=="FP") {
            int id,pins;bool thru;std::string source,source_hash;Box4 b;
            in>>id>>std::quoted(source)>>source_hash>>b.x0>>b.y0>>b.x1>>b.y1>>pins>>thru;
            require(source_hash.size()==64,"missing original footprint document digest");
            // Exact parsed courtyard bounds plus original pad nodes are the
            // complete footprint projection consumed by this production path.
            std::ostringstream doc;doc<<std::setprecision(17)<<"(footprint \"archived\" (fp_rect (start "
                <<b.x0<<' '<<b.y0<<") (end "<<b.x1<<' '<<b.y1<<") (layer \"F.CrtYd\"))";
            while(in>>tag&&tag=="PAD") {std::string node;in>>std::quoted(node);doc<<node;}
            doc<<')';require(tag=="ENDFP"&&bool(in),"truncated footprint fixture");
            const auto key=std::to_string(id);
            require(out.input.footprints.emplace(key,FloorplanFootprint{source,sexpr_loads(doc.str())}).second,"duplicate footprint");
            out.footprint_expected[key]={b,pins,thru};
        } else throw std::runtime_error("unknown frozen fixture tag "+tag);
    }
    require(out.shapes.size()==2&&out.input.footprints.size()==10&&out.input.geometry.bbox_of.size()==33,
            "incomplete archived geometry");
    return out;
}
void contracts(const Frozen& frozen) {
    Engine engine(frozen.input);
    for(const auto& [key,expected]:frozen.footprint_expected) {
        const auto& c=engine.footprint(key);const auto& [b,pins,thru]=expected;
        require(c.bbox.x0==b.x0&&c.bbox.y0==b.y0&&c.bbox.x1==b.x1&&c.bbox.y1==b.y1&&
                c.pins==pins&&c.has_thru==thru,"frozen footprint projection drift");
    }
    const auto& sw=frozen.shapes.at("bringup_rails");const auto& eth=frozen.shapes.at("ethernet");
    const auto courtyard=[&](const FloorplanZoneShape& shape,const std::string& ref,double x,double y) {
        const auto& b=frozen.input.geometry.bbox_of.at(ref);
        const auto xy=shape.top_off.count(ref)?shape.top_off.at(ref):shape.bot_off.at(ref);
        return offset_turned_box(b,shape.extra_rot.at(ref)+frozen.input.geometry.conn_rot.at(ref),x+xy.first,y+xy.second);
    };
    // Board-local block seeds (3,16), (29,36); page origin is exactly (25,25).
    const auto sb=courtyard(sw,"SW7002",28,41),eb=courtyard(eth,"C10005",54,61);
    require(near(sb.x0,53.044)&&near(sb.y0,47.99)&&near(sb.x1,62.274)&&near(sb.y1,59.73),"archived SW7002 pose drift");
    require(near(eb.x0,61.05)&&near(eb.y0,61.05)&&near(eb.x1,65.65)&&near(eb.y1,63.35),"archived C10005 pose drift");
    require(sb.x1>eb.x0&&near(eb.y0-sb.y1,1.32)&&eb.y0-sb.y1<2,"missing real bad-seed witness");
    const auto sr=engine.fanout(sw),er=engine.fanout(eth);
    require(same(sr.first,{1,1.5,0,1.5}),"archived primary halo drift");
    for(bool pad_punch:{false,true}) {
        QuantizationCounts counts;
        const auto children=engine.zone_components(sw,pad_punch,&counts);
        const auto ec=engine.zone_components(eth,pad_punch,&counts);
        require(children.size()==1&&ec.empty(),"archived child decomposition drift");
        const auto& child=children.front();
        require(child.mask==1&&near(child.dx,.55)&&near(child.dy,.99)&&near(child.w,33.724)&&near(child.h,17.74),"minority courtyard union drift");
        require(same(child.reach,{1.55,2.05,0,2.05}),"minority halo production regressed");
        require(counts.count("pack_fanout_reach_precision4dp")&&counts.count("quant_credit"),"missing actual producer accounting");
        Occupancy occupancy(170,165,.3,12,4,1,.05);
        occupancy.add(29,36,eth.w,eth.h,er.first,er.second,1,ec,&counts);
        const auto fits=[&](double y,const std::vector<Comp>& cs) {
            const bool hashed=occupancy.fits_hashed(3,y,sw.w,sw.h,sr.first,sr.second,2,cs,&counts);
            require(hashed==occupancy.fits_exhaustive(3,y,sw.w,sw.h,sr.first,sr.second,2,cs),"frozen hash/exhaustive disagreement");
            return hashed;
        };
        require(!fits(16,children),"unsafe archived seat admitted");
        auto mutant=children;for(auto& c:mutant){c.reach={};c.inset={};}
        require(fits(16,mutant),"zero-halo mutant must reproduce old admission");
        require(fits(14,children),"safe translated control rejected");
        auto rotated=sw;auto previous=child;
        for(int turn=0;turn<4;++turn) {
            rotated=pcb_placement::turned(rotated,&counts);
            const auto next=engine.zone_components(rotated,pad_punch,&counts).front();
            const auto rotated_halo=[](Halo a){return Halo{a.n,a.s,a.e,a.w};};
            require(same(next.reach,rotated_halo(previous.reach))&&same(next.inset,rotated_halo(previous.inset)),"directional child halo lost on real shape rotation");
            require(near(next.w,previous.h)&&near(next.h,previous.w)&&next.mask==previous.mask,"rotated child geometry or face drift");
            previous=next;
        }
        auto defaults=frozen.input;defaults.compact_search=false;Engine legacy(defaults);
        QuantizationCounts default_counts;
        const auto dc=legacy.zone_components(sw,pad_punch,&default_counts);
        require(dc.size()==children.size()&&same(dc.front().reach,child.reach)&&same(dc.front().inset,child.inset),"search strategy changed physical child clearance");
        require(default_counts.count("pack_fanout_reach_precision4dp")&&default_counts.count("quant_credit"),"default child producer is unaccounted");
        require(!fits(16,dc)&&fits(14,dc),"default mode admits unsafe child or rejects safe control");
    }
}
}
int main(int argc,char** argv){try{
    require(argc==2,"usage: pcb_child_halo_frozen_contracts frozen-geometry-fixture");
    contracts(read_fixture(argv[1]));
    std::cout<<"PASS frozen actual child geometry checks="<<checks<<" (no current board inputs)\n";
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
