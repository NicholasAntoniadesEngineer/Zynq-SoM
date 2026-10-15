#pragma once
#include <cstdint>
#include <map>
#include <string>
struct Result { double seconds;std::uint64_t digest;std::map<std::string,std::size_t> counts; };
Result baseline_run(int,bool);
Result candidate_run(int,bool);
