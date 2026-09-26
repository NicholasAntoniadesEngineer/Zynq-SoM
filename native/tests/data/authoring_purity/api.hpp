#pragma once
#if PURITY_CASE >= 46 && PURITY_CASE <= 56
#include <functional>
#endif
namespace schgen {
struct CircuitSheetIr { int parts = 0; };
struct CircuitAuthor { CircuitSheetIr data; };
struct SubsystemMeta { int count = 2; };
#if PURITY_CASE >= 46 && PURITY_CASE <= 56
struct AuthoringContext { std::function<int(int)> part; };
int native_lookup(int);
void require_context(const AuthoringContext&);
#else
struct AuthoringContext {};
#endif
inline void net(CircuitSheetIr& circuit) { ++circuit.parts; }
#if PURITY_CASE == 28
inline auto header_constructor() { return CircuitSheetIr{}; }
#endif
}
