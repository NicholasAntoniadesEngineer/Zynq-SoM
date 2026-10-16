#include "courtyard_area_diagnostic.hpp"
#include <iostream>
#include <limits>
#include <random>
using schgen::Box4;
int main(){try {
    const auto check=[](bool ok){if(!ok)throw std::runtime_error("courtyard union mismatch");};
    using courtyard_diagnostic::union_area;
    check(union_area({})==0);
    check(union_area({{0,0,2,2},{1,1,3,3}})==7);
    check(union_area({{0,0,2,2},{0,0,2,2},{1,1,1,3}})==4);
    std::mt19937 rng(1771);
    for(int trial=0;trial<1000;++trial) {
        std::vector<Box4> boxes;bool cells[8][8]={};
        for(int n=0;n<12;++n) {
            int x=int(rng()%9),xx=int(rng()%9),y=int(rng()%9),yy=int(rng()%9);
            if(x>xx)std::swap(x,xx);
            if(y>yy)std::swap(y,yy);
            boxes.push_back({double(x),double(y),double(xx),double(yy)});
            for(int i=x;i<xx;++i)for(int j=y;j<yy;++j)cells[i][j]=true;
        }
        double expected=0;for(const auto& row:cells)for(bool cell:row)expected+=cell;
        check(union_area(boxes)==expected);
        std::reverse(boxes.begin(),boxes.end());
        for(auto& b:boxes){b.x0=b.x0*.5-20;b.x1=b.x1*.5-20;b.y0=b.y0*.5+5;b.y1=b.y1*.5+5;}
        check(union_area(boxes)==expected*.25);
    }
    for(const auto b:std::vector<Box4>{{1,0,0,1},{0,2,1,1},{0,0,std::numeric_limits<double>::infinity(),1}}) {
        bool rejected=false;try{(void)union_area({b});}catch(const std::invalid_argument&){rejected=true;}
        check(rejected);
    }
    std::cout<<"courtyard area: 1000 independent grid unions and transformed cases PASS\n";
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
