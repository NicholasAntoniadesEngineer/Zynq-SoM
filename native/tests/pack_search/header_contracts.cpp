// Deliberately first and only include: public header supplies its dependencies.
#include "schgen/pack_search_precision.hpp"
int main(){
    int visits=0;
    schgen::pack_search_detail::for_each_index(std::numeric_limits<long>::max(),1,[&](long){++visits;});
    bool rejected=false;
    try{schgen::pack_search_detail::for_each_index(std::numeric_limits<long>::max(),2,[](long){});}
    catch(const std::overflow_error&){rejected=true;}
    return visits==1&&rejected?0:1;
}
