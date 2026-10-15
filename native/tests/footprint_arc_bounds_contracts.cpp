#include "schgen/pcb_scan.hpp"
#include "schgen/sexpr.hpp"
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <utility>

using namespace schgen;
void require(bool value,const char* why){if(!value)throw std::runtime_error(why);}
int main(){try{
    const auto known=footprint_bbox(sexpr_loads("(footprint arc (fp_arc (start 3 4) (mid -3 4) (end -4 -3) (layer F.CrtYd)))"),6);
    require(known.x0==-5&&known.y0==-3&&known.x1==3&&known.y1==5,"arc extrema outside start/mid/end were omitted");
    const auto translated=footprint_bbox(sexpr_loads("(footprint arc (fp_arc (start 1000000003 -999999996) (mid 999999997 -999999996) (end 999999996 -1000000003) (layer F.CrtYd)))"),6);
    require(translated.x0==999999995&&translated.y0==-1000000003&&translated.x1==1000000003&&translated.y1==-999999995,"circumcenter calculation depends on coordinate origin");
    for(const auto* points:{"(start 0 0) (mid 1 1) (end 2 2)","(start 0 0) (mid 0 0) (end 1 1)","(start 0 0) (mid 1 1)"}){
        bool rejected=false;try{(void)footprint_bbox(sexpr_loads(std::string("(footprint arc (fp_arc ")+points+" (layer F.CrtYd)))"),6);}
        catch(const std::runtime_error&){rejected=true;}require(rejected,"invalid modern arc silently reduced to endpoint bounds");
    }
    const double pi=std::acos(-1.);std::size_t cases=0;
    for(double start:{10.,70.,170.,250.,350.})for(double sweep:{20.,100.,200.,340.,-20.,-100.,-200.,-340.})
    for(double radius:{.1,5.,100.}){
        std::ostringstream text;text<<std::setprecision(17)<<"(footprint arc (fp_arc";
        for(const auto& p:{std::pair<const char*,double>{"start",0.},{"mid",.5},{"end",1.}}){const double a=(start+sweep*p.second)*pi/180.;
            text<<" ("<<p.first<<' '<<-7+radius*std::cos(a)<<' '<<11+radius*std::sin(a)<<')';}
        text<<" (layer B.CrtYd)))";const auto box=footprint_bbox(sexpr_loads(text.str()),6);
        for(int i=0;i<=4000;++i){const double a=(start+sweep*i/4000.)*pi/180.;const double x=-7+radius*std::cos(a),y=11+radius*std::sin(a);
            require(x>=box.x0-.00000051&&x<=box.x1+.00000051&&y>=box.y0-.00000051&&y<=box.y1+.00000051,"sampled arc escapes quantized bounds");}
        // Every reported extreme must belong to the swept arc, not just its
        // containing circle. A dense independent sample bounds excess tightly.
        double x0=INFINITY,y0=INFINITY,x1=-INFINITY,y1=-INFINITY;
        for(int i=0;i<=4000;++i){const double a=(start+sweep*i/4000.)*pi/180.;
            const double x=-7+radius*std::cos(a),y=11+radius*std::sin(a);
            x0=std::min(x0,x);x1=std::max(x1,x);y0=std::min(y0,y);y1=std::max(y1,y);}
        const double tolerance=radius*(1-std::cos(std::abs(sweep)*pi/180./4000.))+.00000051;
        require(std::abs(box.x0-x0)<=tolerance&&std::abs(box.x1-x1)<=tolerance&&
            std::abs(box.y0-y0)<=tolerance&&std::abs(box.y1-y1)<=tolerance,"arc bounds include an unswept quadrant");++cases;
    }
    std::cout<<"PASS exact arc and "<<cases<<" independent sampled sweep bounds\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
