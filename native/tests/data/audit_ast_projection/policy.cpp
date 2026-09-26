#include "policy.hpp"
// Global and anonymous policies must survive: no namespace allowlist.
double global_clearance=4.2;
const double derived_clearance=global_clearance+0.1;
namespace {constexpr double anonymous_gap=1.4;}
namespace other {
using Distance=double;
struct State {Distance area=0;Distance hidden=.4;const Distance frozen=0;};
enum class Physical {Gap=4,Successor};
enum class StateTag {Idle,Busy};
constexpr double Δ=1.5;
struct {double hidden=.7;} anonymous_record;
double overloaded(double v){return __builtin_round(v);}
double overloaded(int v){constexpr double bias=2.5;return v+bias;}
double shadows(double v){if(v>0){constexpr double gap=2.5;return v+gap;}else{constexpr double gap=3.5;return v+gap;}}
double lambdas(double v){
    auto f=[capture=__builtin_round(v)](double y){constexpr double eps=.2;return __builtin_floor(y+capture+eps);};
    return f(v);
}
double macros(double v){LOCAL_POLICY(buried_macro);return RAW_MACRO(v)+EXPANDED_GAP+buried_macro;}
double casts(double gap){const auto credit=gap+.05;return static_cast<int>(credit);}
extern "C" double round(double);
double pointer(double v){auto f=&round;return f(v);}
}
double included_policy::Engine::snap(double v) const {constexpr double eps=.1;return __builtin_round(v+eps);}
double included_policy::Engine::snap(int v){return v;}
constexpr double after_include=6.2;
