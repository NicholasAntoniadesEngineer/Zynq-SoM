#pragma once
namespace included_policy {
constexpr double header_gap=9.1;
struct Engine {double snap(double) const;double snap(int);};
inline double header_round(double v){return __builtin_round(v);}
}
#define EXPANDED_GAP 2.75
#define RAW_MACRO(value) __builtin_round(value)
#define LOCAL_POLICY(name) constexpr double name=3.2
