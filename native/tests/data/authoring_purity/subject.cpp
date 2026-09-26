#include "api.hpp"
#if PURITY_CASE == 1 || PURITY_CASE == 2 || PURITY_CASE == 3 || PURITY_CASE == 12
#include "geometry.hpp"
#endif
#if PURITY_CASE == 4
#include "indirection.hpp"
#endif
#if PURITY_CASE == 5 || PURITY_CASE == 44 || PURITY_CASE == 45
int transitive_helper();
#endif
#if PURITY_CASE == 6
namespace schgen { CircuitSheetIr unregistered() { return {}; } }
#endif
#if PURITY_CASE == 39
int route() { return 1; }
namespace schgen { CircuitSheetIr unregistered() { return {route()}; } }
#endif
#if PURITY_CASE == 40
void hidden_factory(schgen::CircuitSheetIr& output) { output.parts = 1; }
#endif
#if PURITY_CASE == 41
void hidden_factory(schgen::CircuitAuthor* output) { output->data.parts = 1; }
#endif
#if PURITY_CASE == 42
int readonly_helper(const schgen::CircuitSheetIr& input) { return input.parts; }
#endif
#if PURITY_CASE == 43
schgen::CircuitAuthor factory_before_finish() { return {}; }
#endif
#if PURITY_CASE == 7
int unknown_helper();
#endif
#if PURITY_CASE == 8
int (*function_pointer)();
#endif
#if PURITY_CASE == 9
struct RuntimeProvider { virtual int get() = 0; };
extern RuntimeProvider& runtime_provider;
#endif
#if PURITY_CASE == 10
template <class T> int template_helper(T x) { return x(); }
int route() { return 2; }
#endif
#if PURITY_CASE == 11
int placer = 0;
#endif
#if PURITY_CASE == 13
#include <functional>
extern std::function<int()> erased;
#endif
#if PURITY_CASE == 14
int emit() { return 2; }
struct DestructorHelper { ~DestructorHelper() { emit(); } };
#endif
#if PURITY_CASE == 15
int route() { return 0; }
int global_initializer = route();
#endif
#if PURITY_CASE == 16
int forward_only();
#endif
#if PURITY_CASE == 17
using Alias = schgen::CircuitSheetIr;
Alias extra_aliased_constructor() { return {}; }
#endif
#if PURITY_CASE == 18
namespace std { inline int forged_trust() { return 7; } }
#endif
#if PURITY_CASE == 19
#include <algorithm>
#include <vector>
#endif
#if PURITY_CASE == 20
struct Box { int x; };
#endif
#if PURITY_CASE == 22
#include "system_disguise.hpp"
#endif
#if PURITY_CASE == 23
int place();
int default_helper(int value = place()) { return value; }
#endif
#if PURITY_CASE == 24
template<class T> int route(T x) { return x; }
#endif
#if PURITY_CASE == 25
int overload_helper(int x) { return x; }
int overload_helper(double);
#endif
#if PURITY_CASE == 26
#define DISGUISED_NAME pla ## cer
int DISGUISED_NAME() { return 0; }
#endif
#if PURITY_CASE == 30 || PURITY_CASE == 31
extern int external_counter;
#endif
#if PURITY_CASE == 32
struct MemberProvider { int value() { return 1; } };
#endif
#if PURITY_CASE == 33
#include <fstream>
#endif
#if PURITY_CASE == 35
#define CHOSEN_HEADER "geometry.hpp"
#include CHOSEN_HEADER
#endif
#if PURITY_CASE == 36
namespace std { int route() { return 7; } }
#endif
#if PURITY_CASE >= 46 && PURITY_CASE <= 56
extern std::function<int(int)> foreign;
#if PURITY_CASE == 48
int other_site(const schgen::AuthoringContext& context) { return context.part(1); }
#endif
#endif
namespace schgen {
CircuitSheetIr circuit(const SubsystemMeta& meta, const AuthoringContext& context) {
    (void)context;
    CircuitSheetIr c;
    for (int i = 0; i < meta.count; ++i) net(c);
#if PURITY_CASE == 1
    c.parts += geometry::innocent_name();
#elif PURITY_CASE == 2
    namespace alias = geometry;
    const auto callable = &alias::innocent_name;
    c.parts += callable();
#elif PURITY_CASE == 3
#define GEOMETRIC_CALL geometry::innocent_name
    c.parts += GEOMETRIC_CALL();
#elif PURITY_CASE == 4
    c.parts += innocent_bridge();
#elif PURITY_CASE == 5 || PURITY_CASE == 44 || PURITY_CASE == 45
    c.parts += transitive_helper();
#elif PURITY_CASE == 7
    c.parts += unknown_helper();
#elif PURITY_CASE == 8
    c.parts += function_pointer();
#elif PURITY_CASE == 9
    c.parts += runtime_provider.get();
#elif PURITY_CASE == 10
    c.parts += template_helper([] { return route(); });
#elif PURITY_CASE == 13
    c.parts += erased();
#elif PURITY_CASE == 14
    DestructorHelper helper;
#elif PURITY_CASE == 16
    c.parts += forward_only();
#elif PURITY_CASE == 18
    c.parts += std::forged_trust();
#elif PURITY_CASE == 19
    std::vector<int> values{3, 2, 1};
    std::sort(values.begin(), values.end(), [](int a, int b) { return a < b; });
    c.parts += values.front();
#elif PURITY_CASE == 20
    using Innocent = Box;
    Innocent b{1}; c.parts += b.x;
#elif PURITY_CASE == 21
    asm("");
#elif PURITY_CASE == 23
    c.parts += default_helper();
#elif PURITY_CASE == 24
    c.parts += route(1);
#elif PURITY_CASE == 25
    c.parts += overload_helper(1.5);
#elif PURITY_CASE == 27
    c.parts += this_identifier_does_not_compile;
#elif PURITY_CASE == 30 || PURITY_CASE == 31
    c.parts += external_counter;
#elif PURITY_CASE == 32
    MemberProvider provider;
    auto member = &MemberProvider::value;
    c.parts += (provider.*member)();
#elif PURITY_CASE == 33
    std::ofstream output("must-not-be-created");
    output << c.parts;
#elif PURITY_CASE == 34
    auto* pointer = reinterpret_cast<int*>(&c);
    (void)pointer;
#elif PURITY_CASE == 36
    c.parts += std::route();
#elif PURITY_CASE >= 46 && PURITY_CASE <= 56
#if PURITY_CASE == 52
    const_cast<AuthoringContext&>(context).part = foreign;
#elif PURITY_CASE == 55
    auto escaped = context.part;
    c.parts += escaped(1);
#elif PURITY_CASE == 47
    c.parts += foreign(context.part(1));
#elif PURITY_CASE == 48
    c.parts += other_site(context);
#endif
    if (context.part) c.parts += context.part(meta.count);
#endif
    return c;
}
}
