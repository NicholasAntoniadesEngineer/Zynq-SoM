#include "schgen/json.hpp"
#include "schgen/legalize.hpp"
#include "../src/accurate_norm.hpp"
#include <cmath>
#include <filesystem>
#include <iostream>
#include <stdexcept>

namespace {
using namespace schgen;
const JsonNode &field(const JsonNode &n,const std::string &k) {
    const auto p=object_field(n,k);if(!p)throw std::runtime_error("missing "+k);return *p;
}
double number(const JsonNode &n,const std::string &k){return field(n,k).number_value;}
Box4 box(const JsonNode &n){const auto &v=n.array_value;return {v.at(0).number_value,v.at(1).number_value,v.at(2).number_value,v.at(3).number_value};}
std::size_t checks=0,failures=0;
void equal(double actual,double expected,const std::string &label) {
    ++checks;if(actual==expected)return;
    ++failures;std::cerr<<label<<" actual="<<std::hexfloat<<actual<<" expected="<<expected<<std::defaultfloat<<'\n';
}
}
int main(int argc,char **argv) {
    try {
        if(argc!=2)throw std::runtime_error("usage: compose_kernel_contracts REPO_ROOT");
        const auto base=std::filesystem::path(argv[1])/"native/tests/data/compose_repair";
        const auto roots=parse_json_file((base/"kernel_regressions.json").string());
        for(const auto &r:field(roots,"channel").array_value) {
            const auto n=static_cast<int>(number(r,"n"));
            equal(channel_demand_mm(n,6,2.,.2),number(r,"expected"),"channel "+std::to_string(n));
        }
        std::size_t i=0;
        for(const auto &r:field(roots,"facing").array_value) {
            const auto &a=field(r,"zone").array_value,&b=field(r,"output").array_value,&c=field(r,"down").array_value,&expected=field(r,"expected").array_value;
            const auto actual=accurate_facing_dot(a.at(0).number_value,a.at(1).number_value,b.at(0).number_value,b.at(1).number_value,c.at(0).number_value,c.at(1).number_value);
            equal(actual.first,expected.at(0).number_value,"facing dot "+std::to_string(i));
            equal(actual.second,expected.at(1).number_value,"facing angle "+std::to_string(i++));
        }
        const auto boxes=parse_json_file((base/"bbox_regressions.json").string());i=0;
        for(const auto &r:field(boxes,"cases").array_value)equal(bbox_gap(box(field(r,"a")),box(field(r,"b"))),number(r,"expected"),"bbox "+std::to_string(i++));
        std::cout<<"compose kernel contracts: "<<checks<<" checked, "<<failures<<" failed\n";
        return failures?1:0;
    }catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}
}
