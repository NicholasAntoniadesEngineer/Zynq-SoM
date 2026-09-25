#include "pcb_checks_internal.hpp"
#include <array>
#include <cstdint>

namespace schgen {
using namespace pcb_checks;
std::string pcb_sha256(std::string_view text){
    // FIPS 180-4 SHA-256. Local state only; no subprocess/crypto provider I/O.
    constexpr std::array<std::uint32_t,64> k={0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
    std::array<std::uint32_t,8> h={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    std::vector<unsigned char> bytes(text.begin(),text.end());std::uint64_t bits=static_cast<std::uint64_t>(bytes.size())*8;bytes.push_back(0x80);while(bytes.size()%64!=56)bytes.push_back(0);for(int i=7;i>=0;--i)bytes.push_back(static_cast<unsigned char>(bits>>(i*8)));
    auto rotr=[](std::uint32_t x,int n){return (x>>n)|(x<<(32-n));};
    for(std::size_t p=0;p<bytes.size();p+=64){std::array<std::uint32_t,64> w{};for(int i=0;i<16;++i)for(int j=0;j<4;++j)w[i]=(w[i]<<8)|bytes[p+4*i+j];for(int i=16;i<64;++i){auto a=w[i-15],b=w[i-2];w[i]=w[i-16]+(rotr(a,7)^rotr(a,18)^(a>>3))+w[i-7]+(rotr(b,17)^rotr(b,19)^(b>>10));}
        auto a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f_=h[5],g_=h[6],h_=h[7];for(int i=0;i<64;++i){auto t1=h_+(rotr(e,6)^rotr(e,11)^rotr(e,25))+((e&f_)^(~e&g_))+k[i]+w[i];auto t2=(rotr(a,2)^rotr(a,13)^rotr(a,22))+((a&b)^(a&c)^(b&c));h_=g_;g_=f_;f_=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;}h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f_;h[6]+=g_;h[7]+=h_;
    }
    std::string out;const char* hex="0123456789abcdef";for(auto v:h)for(int i=7;i>=0;--i)out+=hex[(v>>(4*i))&15];return out;
}
std::string pcb_escape_content_key(const PcbCheckModel& model,std::string_view interface_bytes){
    std::string bytes(interface_bytes);for(const auto& [ref,index]:connectors(model)){const auto& i=model.insts[index];if(!i.mod)throw std::runtime_error(ref+": escape footprint unresolved");bytes+=i.mod->bytes;bytes+=ref+":"+pyfloat(py_round(i.x,3))+":"+pyfloat(py_round(i.y,3))+":"+pyfloat(py_round(i.rotation==0?0.0:i.rotation,1));}
    bytes+="{\"LANE_HANDLE\": 1.0, \"R_CONSTRUCT\": 1.8, \"VIA_LADDER\": [[0.45, 0.3], [0.4, 0.25], [0.35, 0.2]]}";return pcb_sha256(bytes);
}
EscapeLaneResult check_escape_lanes(const PcbCheckModel& m,const PcbEscapePopulation& population,std::string_view interface_bytes){
    EscapeLaneResult res;auto fail=[&](std::string s){res.ok=false;res.violations.push_back(std::move(s));};
    if(!m.escape_plan){fail("model.escape_plan is None — build_escape_plan did not run (this IS the red-on-before state)");return res;}const auto& plan=*m.escape_plan;
    for(const auto& [ref,lanes]:plan.lanes){(void)ref;res.n_lanes+=static_cast<int>(lanes.size());}
    if(!population.netted_contacts||!population.genuine_pairs)fail("project.json declares no escape.netted_contacts / escape.genuine_pairs — pin the project's measured population (the drift alarm has no basis without it)");
    if(population.netted_contacts)for(const auto& [ref,n]:*population.netted_contacts){auto live=plan.netted_counts.find(ref);if(live==plan.netted_counts.end()||live->second!=n)fail(ref+": netted contacts "+(live==plan.netted_counts.end()?"None":std::to_string(live->second))+" != pinned "+std::to_string(n)+" — SoM interface drift; re-derive the plan deliberately");}
    for(const auto& [ref,lanes]:plan.lanes){
        for(int row:{-1,1}){std::vector<const PcbEscapeLane*> out;for(const auto& ln:lanes)if(ln.row==row&&ln.direction=="outward")out.push_back(&ln);
            if(!std::is_sorted(out.begin(),out.end(),[](auto a,auto b){return a->lane<b->lane;}))fail(ref+" row "+std::to_string(row)+": lane order not monotonic");
            if(out.size()>=2){double xmin=out[0]->port_x,xmax=xmin,ymin=out[0]->port_y,ymax=ymin;for(auto p:out){xmin=std::min(xmin,p->port_x);xmax=std::max(xmax,p->port_x);ymin=std::min(ymin,p->port_y);ymax=std::max(ymax,p->port_y);}bool x=xmax-xmin>=ymax-ymin;std::vector<double> v;for(auto p:out)v.push_back(x?p->port_x:p->port_y);if(!std::is_sorted(v.begin(),v.end())&&!std::is_sorted(v.rbegin(),v.rend()))fail(ref+" row "+std::to_string(row)+": ports not monotonic along the escape line");}
            for(std::size_t i=1;i<out.size();++i){auto a=out[i-1],b=out[i];if(b->lane-a->lane!=1||a->net==b->net)continue;double gap=0.4*(b->lane-a->lane)-(a->width+b->width)/2;if(gap<0.15)fail(ref+" "+a->net+"|"+b->net+": adjacent-lane gap "+f(gap,4)+" < 0.15");}
        }
        std::vector<const PcbEscapeLane*> planes;for(const auto& ln:lanes)if(ln.direction=="plane")planes.push_back(&ln);std::stable_sort(planes.begin(),planes.end(),[](auto a,auto b){return std::tie(a->row,a->lane)<std::tie(b->row,b->lane);});
        for(std::size_t i=1;i<planes.size();++i){auto a=planes[i-1],b=planes[i];if(a->row==b->row&&a->net==b->net&&b->lane-a->lane==1&&(!a->bus_group||a->bus_group!=b->bus_group))fail(ref+" "+a->net+": contiguous POWER contacts "+std::to_string(a->lane)+"/"+std::to_string(b->lane)+" not bus-grouped");}
    }
    res.n_pairs=static_cast<int>(plan.pairs.size());std::set<std::string> genuine;for(const auto& p:plan.pairs)if(p.si_class=="GENUINE"){++res.n_genuine;genuine.insert(p.base);}auto expected=plan.genuine_pairs;std::sort(expected.begin(),expected.end());if(std::vector<std::string>(genuine.begin(),genuine.end())!=expected)fail("genuine_pairs list inconsistent with PairRecs");
    if(population.genuine_pairs&&res.n_genuine!=*population.genuine_pairs)fail("GENUINE pair count "+std::to_string(res.n_genuine)+" != pinned "+std::to_string(*population.genuine_pairs)+" — pinout drift, re-verify the hard terms");
    for(const auto& p:plan.pairs)if(p.si_class=="GENUINE"&&(!p.same_row||p.delta_lane>2))fail("GENUINE pair "+p.base+" ("+p.conn+"): same_row="+(p.same_row?"True":"False")+" delta_lane="+std::to_string(p.delta_lane)+" violates the hard terms (<= 2, same row)");
    if(plan.content_key!=pcb_escape_content_key(m,interface_bytes))fail("content_key STALE — the plan does not match the live interface/footprint/poses");return res;
}
std::string EscapeLaneResult::summary()const{std::vector<std::string> l={"ESCAPE-LANE GATE (Tier-2 plan): "+verdict(ok),"  lanes: "+std::to_string(n_lanes)+"  pair records: "+std::to_string(n_pairs)+"  GENUINE pairs: "+std::to_string(n_genuine),"  lane copper lands with the routing phase (D13 contract); this gate proves the PLAN"};for(const auto& v:violations)l.push_back("  VIOLATION: "+v);return join(l);}
PcbEscapePlan pcb_escape_plan_from_json(const JsonNode& raw){
    kind(raw,JsonKind::Object);PcbEscapePlan plan;if(auto all=object_field(raw,"lanes"))for(const auto& [ref,values]:kind(*all,JsonKind::Object).object_value){auto& lanes=plan.lanes[ref];for(const auto& v:kind(values,JsonKind::Array).array_value){PcbEscapeLane l;l.row=integer(required(v,"row"));l.lane=integer(required(v,"lane"));l.direction=jstr(required(v,"dir"));l.net=jstr(required(v,"net"));auto p=object_field(v,"port");if(p&&p->kind!=JsonKind::Null){auto& a=kind(*p,JsonKind::Array).array_value;if(a.size()!=2)throw std::runtime_error("PCB escape port must have two coordinates");l.port_x=jnum(a[0]);l.port_y=jnum(a[1]);}else if(l.direction=="outward")throw std::runtime_error("PCB outward lane missing port");if(auto w=object_field(v,"width"))l.width=jnum(*w);else if(l.direction=="outward")throw std::runtime_error("PCB outward lane missing width");if(auto b=object_field(v,"bus_group"))if(b->kind!=JsonKind::Null)l.bus_group=jstr(*b);lanes.push_back(std::move(l));}}
    if(auto counts=object_field(raw,"netted_counts"))for(const auto& [ref,n]:kind(*counts,JsonKind::Object).object_value)plan.netted_counts[ref]=integer(n);
    if(auto pairs=object_field(raw,"pairs"))for(const auto& p:kind(*pairs,JsonKind::Array).array_value)plan.pairs.push_back({jstr(required(p,"base")),jstr(required(p,"conn")),jstr(required(p,"si_class")),kind(required(p,"same_row"),JsonKind::Bool).bool_value,integer(required(p,"delta_lane"))});
    if(auto genuine=object_field(raw,"genuine_pairs"))for(const auto& s:kind(*genuine,JsonKind::Array).array_value)plan.genuine_pairs.push_back(jstr(s));if(auto key=object_field(raw,"content_key"))plan.content_key=jstr(*key);return plan;
}
PcbEscapePopulation pcb_escape_population_from_json(const JsonNode& raw){PcbEscapePopulation out;kind(raw,JsonKind::Object);if(auto n=object_field(raw,"netted_contacts"))if(n->kind==JsonKind::Object){out.netted_contacts.emplace();for(const auto& [ref,v]:n->object_value)(*out.netted_contacts)[ref]=integer(v);}if(auto n=object_field(raw,"genuine_pairs"))if(n->kind!=JsonKind::Null)out.genuine_pairs=integer(*n);return out;}
} // namespace schgen
