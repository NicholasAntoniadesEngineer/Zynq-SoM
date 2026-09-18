#include "schgen/design_rules.hpp"

#include <algorithm>
#include <cstdint>
#include <map>
#include <new>
#include <set>
#include <system_error>
#include <unordered_map>
#include <unordered_set>

namespace schgen {
namespace {
using Strings = std::vector<std::string>;
using PinKey = std::pair<std::string, std::string>;

std::string join(const Strings& values, const std::string& separator) {
    std::string out;
    for (std::size_t i = 0; i < values.size(); ++i) {
        if (i) out += separator;
        out += values[i];
    }
    return out;
}
bool starts(const std::string& text, const std::string& prefix) {
    return text.compare(0, prefix.size(), prefix) == 0;
}
bool ends(const std::string& text, const std::string& suffix) {
    return text.size() >= suffix.size()
        && text.compare(text.size() - suffix.size(), suffix.size(), suffix) == 0;
}

// UTF-8 transport is also used by the circuit/symbol loaders. Keeping codepoint
// widths here is necessary for Python's report alignment (not byte widths).
std::uint32_t next_codepoint(const std::string& s, std::size_t& pos) {
    const auto lead = static_cast<unsigned char>(s[pos++]);
    if (lead < 0x80) return lead;
    const unsigned count = lead < 0xe0 ? 1 : lead < 0xf0 ? 2 : 3;
    std::uint32_t cp = lead & (count == 1 ? 0x1f : count == 2 ? 0xf : 0x7);
    for (unsigned i = 0; i < count && pos < s.size(); ++i)
        cp = (cp << 6) | (static_cast<unsigned char>(s[pos++]) & 0x3f);
    return cp;
}

// Unicode character properties are defined below, frozen to the Python
// reference's Unicode database. No locale-dependent ctype/regex behavior.
// Frozen Unicode 16.0.0 properties from the Python reference. Binary
// search keeps Unicode parity independent of C/C++ locale and installed ICU.
struct UnicodeRange { std::uint32_t first, last; };
template<std::size_t N>
bool in_ranges(std::uint32_t cp, const UnicodeRange (&ranges)[N]) {
    const auto* it = std::lower_bound(ranges, ranges + N, cp,
        [](const UnicodeRange& range, std::uint32_t value) { return range.last < value; });
    return it != ranges + N && cp >= it->first;
}
bool decimal_digit(std::uint32_t cp) {
    static constexpr UnicodeRange ranges[] = {
        {0x30, 0x39}, {0x660, 0x669}, {0x6f0, 0x6f9}, {0x7c0, 0x7c9},
        {0x966, 0x96f}, {0x9e6, 0x9ef}, {0xa66, 0xa6f}, {0xae6, 0xaef},
        {0xb66, 0xb6f}, {0xbe6, 0xbef}, {0xc66, 0xc6f}, {0xce6, 0xcef},
        {0xd66, 0xd6f}, {0xde6, 0xdef}, {0xe50, 0xe59}, {0xed0, 0xed9},
        {0xf20, 0xf29}, {0x1040, 0x1049}, {0x1090, 0x1099}, {0x17e0, 0x17e9},
        {0x1810, 0x1819}, {0x1946, 0x194f}, {0x19d0, 0x19d9}, {0x1a80, 0x1a89},
        {0x1a90, 0x1a99}, {0x1b50, 0x1b59}, {0x1bb0, 0x1bb9}, {0x1c40, 0x1c49},
        {0x1c50, 0x1c59}, {0xa620, 0xa629}, {0xa8d0, 0xa8d9}, {0xa900, 0xa909},
        {0xa9d0, 0xa9d9}, {0xa9f0, 0xa9f9}, {0xaa50, 0xaa59}, {0xabf0, 0xabf9},
        {0xff10, 0xff19}, {0x104a0, 0x104a9}, {0x10d30, 0x10d39}, {0x10d40, 0x10d49},
        {0x11066, 0x1106f}, {0x110f0, 0x110f9}, {0x11136, 0x1113f}, {0x111d0, 0x111d9},
        {0x112f0, 0x112f9}, {0x11450, 0x11459}, {0x114d0, 0x114d9}, {0x11650, 0x11659},
        {0x116c0, 0x116c9}, {0x116d0, 0x116e3}, {0x11730, 0x11739}, {0x118e0, 0x118e9},
        {0x11950, 0x11959}, {0x11bf0, 0x11bf9}, {0x11c50, 0x11c59}, {0x11d50, 0x11d59},
        {0x11da0, 0x11da9}, {0x11f50, 0x11f59}, {0x16130, 0x16139}, {0x16a60, 0x16a69},
        {0x16ac0, 0x16ac9}, {0x16b50, 0x16b59}, {0x16d70, 0x16d79}, {0x1ccf0, 0x1ccf9},
        {0x1d7ce, 0x1d7ff}, {0x1e140, 0x1e149}, {0x1e2f0, 0x1e2f9}, {0x1e4f0, 0x1e4f9},
        {0x1e5f1, 0x1e5fa}, {0x1e950, 0x1e959}, {0x1fbf0, 0x1fbf9},
    };
    return in_ranges(cp, ranges);
}
bool python_digit(std::uint32_t cp) {
    static constexpr UnicodeRange ranges[] = {
        {0x30, 0x39}, {0xb2, 0xb3}, {0xb9, 0xb9}, {0x660, 0x669},
        {0x6f0, 0x6f9}, {0x7c0, 0x7c9}, {0x966, 0x96f}, {0x9e6, 0x9ef},
        {0xa66, 0xa6f}, {0xae6, 0xaef}, {0xb66, 0xb6f}, {0xbe6, 0xbef},
        {0xc66, 0xc6f}, {0xce6, 0xcef}, {0xd66, 0xd6f}, {0xde6, 0xdef},
        {0xe50, 0xe59}, {0xed0, 0xed9}, {0xf20, 0xf29}, {0x1040, 0x1049},
        {0x1090, 0x1099}, {0x1369, 0x1371}, {0x17e0, 0x17e9}, {0x1810, 0x1819},
        {0x1946, 0x194f}, {0x19d0, 0x19da}, {0x1a80, 0x1a89}, {0x1a90, 0x1a99},
        {0x1b50, 0x1b59}, {0x1bb0, 0x1bb9}, {0x1c40, 0x1c49}, {0x1c50, 0x1c59},
        {0x2070, 0x2070}, {0x2074, 0x2079}, {0x2080, 0x2089}, {0x2460, 0x2468},
        {0x2474, 0x247c}, {0x2488, 0x2490}, {0x24ea, 0x24ea}, {0x24f5, 0x24fd},
        {0x24ff, 0x24ff}, {0x2776, 0x277e}, {0x2780, 0x2788}, {0x278a, 0x2792},
        {0xa620, 0xa629}, {0xa8d0, 0xa8d9}, {0xa900, 0xa909}, {0xa9d0, 0xa9d9},
        {0xa9f0, 0xa9f9}, {0xaa50, 0xaa59}, {0xabf0, 0xabf9}, {0xff10, 0xff19},
        {0x104a0, 0x104a9}, {0x10a40, 0x10a43}, {0x10d30, 0x10d39}, {0x10d40, 0x10d49},
        {0x10e60, 0x10e68}, {0x11052, 0x1105a}, {0x11066, 0x1106f}, {0x110f0, 0x110f9},
        {0x11136, 0x1113f}, {0x111d0, 0x111d9}, {0x112f0, 0x112f9}, {0x11450, 0x11459},
        {0x114d0, 0x114d9}, {0x11650, 0x11659}, {0x116c0, 0x116c9}, {0x116d0, 0x116e3},
        {0x11730, 0x11739}, {0x118e0, 0x118e9}, {0x11950, 0x11959}, {0x11bf0, 0x11bf9},
        {0x11c50, 0x11c59}, {0x11d50, 0x11d59}, {0x11da0, 0x11da9}, {0x11f50, 0x11f59},
        {0x16130, 0x16139}, {0x16a60, 0x16a69}, {0x16ac0, 0x16ac9}, {0x16b50, 0x16b59},
        {0x16d70, 0x16d79}, {0x1ccf0, 0x1ccf9}, {0x1d7ce, 0x1d7ff}, {0x1e140, 0x1e149},
        {0x1e2f0, 0x1e2f9}, {0x1e4f0, 0x1e4f9}, {0x1e5f1, 0x1e5fa}, {0x1e950, 0x1e959},
        {0x1f100, 0x1f10a}, {0x1fbf0, 0x1fbf9},
    };
    return in_ranges(cp, ranges);
}
bool printable(std::uint32_t cp) {
    static constexpr UnicodeRange ranges[] = {
        {0x0, 0x1f}, {0x7f, 0xa0}, {0xad, 0xad}, {0x378, 0x379},
        {0x380, 0x383}, {0x38b, 0x38b}, {0x38d, 0x38d}, {0x3a2, 0x3a2},
        {0x530, 0x530}, {0x557, 0x558}, {0x58b, 0x58c}, {0x590, 0x590},
        {0x5c8, 0x5cf}, {0x5eb, 0x5ee}, {0x5f5, 0x605}, {0x61c, 0x61c},
        {0x6dd, 0x6dd}, {0x70e, 0x70f}, {0x74b, 0x74c}, {0x7b2, 0x7bf},
        {0x7fb, 0x7fc}, {0x82e, 0x82f}, {0x83f, 0x83f}, {0x85c, 0x85d},
        {0x85f, 0x85f}, {0x86b, 0x86f}, {0x88f, 0x896}, {0x8e2, 0x8e2},
        {0x984, 0x984}, {0x98d, 0x98e}, {0x991, 0x992}, {0x9a9, 0x9a9},
        {0x9b1, 0x9b1}, {0x9b3, 0x9b5}, {0x9ba, 0x9bb}, {0x9c5, 0x9c6},
        {0x9c9, 0x9ca}, {0x9cf, 0x9d6}, {0x9d8, 0x9db}, {0x9de, 0x9de},
        {0x9e4, 0x9e5}, {0x9ff, 0xa00}, {0xa04, 0xa04}, {0xa0b, 0xa0e},
        {0xa11, 0xa12}, {0xa29, 0xa29}, {0xa31, 0xa31}, {0xa34, 0xa34},
        {0xa37, 0xa37}, {0xa3a, 0xa3b}, {0xa3d, 0xa3d}, {0xa43, 0xa46},
        {0xa49, 0xa4a}, {0xa4e, 0xa50}, {0xa52, 0xa58}, {0xa5d, 0xa5d},
        {0xa5f, 0xa65}, {0xa77, 0xa80}, {0xa84, 0xa84}, {0xa8e, 0xa8e},
        {0xa92, 0xa92}, {0xaa9, 0xaa9}, {0xab1, 0xab1}, {0xab4, 0xab4},
        {0xaba, 0xabb}, {0xac6, 0xac6}, {0xaca, 0xaca}, {0xace, 0xacf},
        {0xad1, 0xadf}, {0xae4, 0xae5}, {0xaf2, 0xaf8}, {0xb00, 0xb00},
        {0xb04, 0xb04}, {0xb0d, 0xb0e}, {0xb11, 0xb12}, {0xb29, 0xb29},
        {0xb31, 0xb31}, {0xb34, 0xb34}, {0xb3a, 0xb3b}, {0xb45, 0xb46},
        {0xb49, 0xb4a}, {0xb4e, 0xb54}, {0xb58, 0xb5b}, {0xb5e, 0xb5e},
        {0xb64, 0xb65}, {0xb78, 0xb81}, {0xb84, 0xb84}, {0xb8b, 0xb8d},
        {0xb91, 0xb91}, {0xb96, 0xb98}, {0xb9b, 0xb9b}, {0xb9d, 0xb9d},
        {0xba0, 0xba2}, {0xba5, 0xba7}, {0xbab, 0xbad}, {0xbba, 0xbbd},
        {0xbc3, 0xbc5}, {0xbc9, 0xbc9}, {0xbce, 0xbcf}, {0xbd1, 0xbd6},
        {0xbd8, 0xbe5}, {0xbfb, 0xbff}, {0xc0d, 0xc0d}, {0xc11, 0xc11},
        {0xc29, 0xc29}, {0xc3a, 0xc3b}, {0xc45, 0xc45}, {0xc49, 0xc49},
        {0xc4e, 0xc54}, {0xc57, 0xc57}, {0xc5b, 0xc5c}, {0xc5e, 0xc5f},
        {0xc64, 0xc65}, {0xc70, 0xc76}, {0xc8d, 0xc8d}, {0xc91, 0xc91},
        {0xca9, 0xca9}, {0xcb4, 0xcb4}, {0xcba, 0xcbb}, {0xcc5, 0xcc5},
        {0xcc9, 0xcc9}, {0xcce, 0xcd4}, {0xcd7, 0xcdc}, {0xcdf, 0xcdf},
        {0xce4, 0xce5}, {0xcf0, 0xcf0}, {0xcf4, 0xcff}, {0xd0d, 0xd0d},
        {0xd11, 0xd11}, {0xd45, 0xd45}, {0xd49, 0xd49}, {0xd50, 0xd53},
        {0xd64, 0xd65}, {0xd80, 0xd80}, {0xd84, 0xd84}, {0xd97, 0xd99},
        {0xdb2, 0xdb2}, {0xdbc, 0xdbc}, {0xdbe, 0xdbf}, {0xdc7, 0xdc9},
        {0xdcb, 0xdce}, {0xdd5, 0xdd5}, {0xdd7, 0xdd7}, {0xde0, 0xde5},
        {0xdf0, 0xdf1}, {0xdf5, 0xe00}, {0xe3b, 0xe3e}, {0xe5c, 0xe80},
        {0xe83, 0xe83}, {0xe85, 0xe85}, {0xe8b, 0xe8b}, {0xea4, 0xea4},
        {0xea6, 0xea6}, {0xebe, 0xebf}, {0xec5, 0xec5}, {0xec7, 0xec7},
        {0xecf, 0xecf}, {0xeda, 0xedb}, {0xee0, 0xeff}, {0xf48, 0xf48},
        {0xf6d, 0xf70}, {0xf98, 0xf98}, {0xfbd, 0xfbd}, {0xfcd, 0xfcd},
        {0xfdb, 0xfff}, {0x10c6, 0x10c6}, {0x10c8, 0x10cc}, {0x10ce, 0x10cf},
        {0x1249, 0x1249}, {0x124e, 0x124f}, {0x1257, 0x1257}, {0x1259, 0x1259},
        {0x125e, 0x125f}, {0x1289, 0x1289}, {0x128e, 0x128f}, {0x12b1, 0x12b1},
        {0x12b6, 0x12b7}, {0x12bf, 0x12bf}, {0x12c1, 0x12c1}, {0x12c6, 0x12c7},
        {0x12d7, 0x12d7}, {0x1311, 0x1311}, {0x1316, 0x1317}, {0x135b, 0x135c},
        {0x137d, 0x137f}, {0x139a, 0x139f}, {0x13f6, 0x13f7}, {0x13fe, 0x13ff},
        {0x1680, 0x1680}, {0x169d, 0x169f}, {0x16f9, 0x16ff}, {0x1716, 0x171e},
        {0x1737, 0x173f}, {0x1754, 0x175f}, {0x176d, 0x176d}, {0x1771, 0x1771},
        {0x1774, 0x177f}, {0x17de, 0x17df}, {0x17ea, 0x17ef}, {0x17fa, 0x17ff},
        {0x180e, 0x180e}, {0x181a, 0x181f}, {0x1879, 0x187f}, {0x18ab, 0x18af},
        {0x18f6, 0x18ff}, {0x191f, 0x191f}, {0x192c, 0x192f}, {0x193c, 0x193f},
        {0x1941, 0x1943}, {0x196e, 0x196f}, {0x1975, 0x197f}, {0x19ac, 0x19af},
        {0x19ca, 0x19cf}, {0x19db, 0x19dd}, {0x1a1c, 0x1a1d}, {0x1a5f, 0x1a5f},
        {0x1a7d, 0x1a7e}, {0x1a8a, 0x1a8f}, {0x1a9a, 0x1a9f}, {0x1aae, 0x1aaf},
        {0x1acf, 0x1aff}, {0x1b4d, 0x1b4d}, {0x1bf4, 0x1bfb}, {0x1c38, 0x1c3a},
        {0x1c4a, 0x1c4c}, {0x1c8b, 0x1c8f}, {0x1cbb, 0x1cbc}, {0x1cc8, 0x1ccf},
        {0x1cfb, 0x1cff}, {0x1f16, 0x1f17}, {0x1f1e, 0x1f1f}, {0x1f46, 0x1f47},
        {0x1f4e, 0x1f4f}, {0x1f58, 0x1f58}, {0x1f5a, 0x1f5a}, {0x1f5c, 0x1f5c},
        {0x1f5e, 0x1f5e}, {0x1f7e, 0x1f7f}, {0x1fb5, 0x1fb5}, {0x1fc5, 0x1fc5},
        {0x1fd4, 0x1fd5}, {0x1fdc, 0x1fdc}, {0x1ff0, 0x1ff1}, {0x1ff5, 0x1ff5},
        {0x1fff, 0x200f}, {0x2028, 0x202f}, {0x205f, 0x206f}, {0x2072, 0x2073},
        {0x208f, 0x208f}, {0x209d, 0x209f}, {0x20c1, 0x20cf}, {0x20f1, 0x20ff},
        {0x218c, 0x218f}, {0x242a, 0x243f}, {0x244b, 0x245f}, {0x2b74, 0x2b75},
        {0x2b96, 0x2b96}, {0x2cf4, 0x2cf8}, {0x2d26, 0x2d26}, {0x2d28, 0x2d2c},
        {0x2d2e, 0x2d2f}, {0x2d68, 0x2d6e}, {0x2d71, 0x2d7e}, {0x2d97, 0x2d9f},
        {0x2da7, 0x2da7}, {0x2daf, 0x2daf}, {0x2db7, 0x2db7}, {0x2dbf, 0x2dbf},
        {0x2dc7, 0x2dc7}, {0x2dcf, 0x2dcf}, {0x2dd7, 0x2dd7}, {0x2ddf, 0x2ddf},
        {0x2e5e, 0x2e7f}, {0x2e9a, 0x2e9a}, {0x2ef4, 0x2eff}, {0x2fd6, 0x2fef},
        {0x3000, 0x3000}, {0x3040, 0x3040}, {0x3097, 0x3098}, {0x3100, 0x3104},
        {0x3130, 0x3130}, {0x318f, 0x318f}, {0x31e6, 0x31ee}, {0x321f, 0x321f},
        {0xa48d, 0xa48f}, {0xa4c7, 0xa4cf}, {0xa62c, 0xa63f}, {0xa6f8, 0xa6ff},
        {0xa7ce, 0xa7cf}, {0xa7d2, 0xa7d2}, {0xa7d4, 0xa7d4}, {0xa7dd, 0xa7f1},
        {0xa82d, 0xa82f}, {0xa83a, 0xa83f}, {0xa878, 0xa87f}, {0xa8c6, 0xa8cd},
        {0xa8da, 0xa8df}, {0xa954, 0xa95e}, {0xa97d, 0xa97f}, {0xa9ce, 0xa9ce},
        {0xa9da, 0xa9dd}, {0xa9ff, 0xa9ff}, {0xaa37, 0xaa3f}, {0xaa4e, 0xaa4f},
        {0xaa5a, 0xaa5b}, {0xaac3, 0xaada}, {0xaaf7, 0xab00}, {0xab07, 0xab08},
        {0xab0f, 0xab10}, {0xab17, 0xab1f}, {0xab27, 0xab27}, {0xab2f, 0xab2f},
        {0xab6c, 0xab6f}, {0xabee, 0xabef}, {0xabfa, 0xabff}, {0xd7a4, 0xd7af},
        {0xd7c7, 0xd7ca}, {0xd7fc, 0xf8ff}, {0xfa6e, 0xfa6f}, {0xfada, 0xfaff},
        {0xfb07, 0xfb12}, {0xfb18, 0xfb1c}, {0xfb37, 0xfb37}, {0xfb3d, 0xfb3d},
        {0xfb3f, 0xfb3f}, {0xfb42, 0xfb42}, {0xfb45, 0xfb45}, {0xfbc3, 0xfbd2},
        {0xfd90, 0xfd91}, {0xfdc8, 0xfdce}, {0xfdd0, 0xfdef}, {0xfe1a, 0xfe1f},
        {0xfe53, 0xfe53}, {0xfe67, 0xfe67}, {0xfe6c, 0xfe6f}, {0xfe75, 0xfe75},
        {0xfefd, 0xff00}, {0xffbf, 0xffc1}, {0xffc8, 0xffc9}, {0xffd0, 0xffd1},
        {0xffd8, 0xffd9}, {0xffdd, 0xffdf}, {0xffe7, 0xffe7}, {0xffef, 0xfffb},
        {0xfffe, 0xffff}, {0x1000c, 0x1000c}, {0x10027, 0x10027}, {0x1003b, 0x1003b},
        {0x1003e, 0x1003e}, {0x1004e, 0x1004f}, {0x1005e, 0x1007f}, {0x100fb, 0x100ff},
        {0x10103, 0x10106}, {0x10134, 0x10136}, {0x1018f, 0x1018f}, {0x1019d, 0x1019f},
        {0x101a1, 0x101cf}, {0x101fe, 0x1027f}, {0x1029d, 0x1029f}, {0x102d1, 0x102df},
        {0x102fc, 0x102ff}, {0x10324, 0x1032c}, {0x1034b, 0x1034f}, {0x1037b, 0x1037f},
        {0x1039e, 0x1039e}, {0x103c4, 0x103c7}, {0x103d6, 0x103ff}, {0x1049e, 0x1049f},
        {0x104aa, 0x104af}, {0x104d4, 0x104d7}, {0x104fc, 0x104ff}, {0x10528, 0x1052f},
        {0x10564, 0x1056e}, {0x1057b, 0x1057b}, {0x1058b, 0x1058b}, {0x10593, 0x10593},
        {0x10596, 0x10596}, {0x105a2, 0x105a2}, {0x105b2, 0x105b2}, {0x105ba, 0x105ba},
        {0x105bd, 0x105bf}, {0x105f4, 0x105ff}, {0x10737, 0x1073f}, {0x10756, 0x1075f},
        {0x10768, 0x1077f}, {0x10786, 0x10786}, {0x107b1, 0x107b1}, {0x107bb, 0x107ff},
        {0x10806, 0x10807}, {0x10809, 0x10809}, {0x10836, 0x10836}, {0x10839, 0x1083b},
        {0x1083d, 0x1083e}, {0x10856, 0x10856}, {0x1089f, 0x108a6}, {0x108b0, 0x108df},
        {0x108f3, 0x108f3}, {0x108f6, 0x108fa}, {0x1091c, 0x1091e}, {0x1093a, 0x1093e},
        {0x10940, 0x1097f}, {0x109b8, 0x109bb}, {0x109d0, 0x109d1}, {0x10a04, 0x10a04},
        {0x10a07, 0x10a0b}, {0x10a14, 0x10a14}, {0x10a18, 0x10a18}, {0x10a36, 0x10a37},
        {0x10a3b, 0x10a3e}, {0x10a49, 0x10a4f}, {0x10a59, 0x10a5f}, {0x10aa0, 0x10abf},
        {0x10ae7, 0x10aea}, {0x10af7, 0x10aff}, {0x10b36, 0x10b38}, {0x10b56, 0x10b57},
        {0x10b73, 0x10b77}, {0x10b92, 0x10b98}, {0x10b9d, 0x10ba8}, {0x10bb0, 0x10bff},
        {0x10c49, 0x10c7f}, {0x10cb3, 0x10cbf}, {0x10cf3, 0x10cf9}, {0x10d28, 0x10d2f},
        {0x10d3a, 0x10d3f}, {0x10d66, 0x10d68}, {0x10d86, 0x10d8d}, {0x10d90, 0x10e5f},
        {0x10e7f, 0x10e7f}, {0x10eaa, 0x10eaa}, {0x10eae, 0x10eaf}, {0x10eb2, 0x10ec1},
        {0x10ec5, 0x10efb}, {0x10f28, 0x10f2f}, {0x10f5a, 0x10f6f}, {0x10f8a, 0x10faf},
        {0x10fcc, 0x10fdf}, {0x10ff7, 0x10fff}, {0x1104e, 0x11051}, {0x11076, 0x1107e},
        {0x110bd, 0x110bd}, {0x110c3, 0x110cf}, {0x110e9, 0x110ef}, {0x110fa, 0x110ff},
        {0x11135, 0x11135}, {0x11148, 0x1114f}, {0x11177, 0x1117f}, {0x111e0, 0x111e0},
        {0x111f5, 0x111ff}, {0x11212, 0x11212}, {0x11242, 0x1127f}, {0x11287, 0x11287},
        {0x11289, 0x11289}, {0x1128e, 0x1128e}, {0x1129e, 0x1129e}, {0x112aa, 0x112af},
        {0x112eb, 0x112ef}, {0x112fa, 0x112ff}, {0x11304, 0x11304}, {0x1130d, 0x1130e},
        {0x11311, 0x11312}, {0x11329, 0x11329}, {0x11331, 0x11331}, {0x11334, 0x11334},
        {0x1133a, 0x1133a}, {0x11345, 0x11346}, {0x11349, 0x1134a}, {0x1134e, 0x1134f},
        {0x11351, 0x11356}, {0x11358, 0x1135c}, {0x11364, 0x11365}, {0x1136d, 0x1136f},
        {0x11375, 0x1137f}, {0x1138a, 0x1138a}, {0x1138c, 0x1138d}, {0x1138f, 0x1138f},
        {0x113b6, 0x113b6}, {0x113c1, 0x113c1}, {0x113c3, 0x113c4}, {0x113c6, 0x113c6},
        {0x113cb, 0x113cb}, {0x113d6, 0x113d6}, {0x113d9, 0x113e0}, {0x113e3, 0x113ff},
        {0x1145c, 0x1145c}, {0x11462, 0x1147f}, {0x114c8, 0x114cf}, {0x114da, 0x1157f},
        {0x115b6, 0x115b7}, {0x115de, 0x115ff}, {0x11645, 0x1164f}, {0x1165a, 0x1165f},
        {0x1166d, 0x1167f}, {0x116ba, 0x116bf}, {0x116ca, 0x116cf}, {0x116e4, 0x116ff},
        {0x1171b, 0x1171c}, {0x1172c, 0x1172f}, {0x11747, 0x117ff}, {0x1183c, 0x1189f},
        {0x118f3, 0x118fe}, {0x11907, 0x11908}, {0x1190a, 0x1190b}, {0x11914, 0x11914},
        {0x11917, 0x11917}, {0x11936, 0x11936}, {0x11939, 0x1193a}, {0x11947, 0x1194f},
        {0x1195a, 0x1199f}, {0x119a8, 0x119a9}, {0x119d8, 0x119d9}, {0x119e5, 0x119ff},
        {0x11a48, 0x11a4f}, {0x11aa3, 0x11aaf}, {0x11af9, 0x11aff}, {0x11b0a, 0x11bbf},
        {0x11be2, 0x11bef}, {0x11bfa, 0x11bff}, {0x11c09, 0x11c09}, {0x11c37, 0x11c37},
        {0x11c46, 0x11c4f}, {0x11c6d, 0x11c6f}, {0x11c90, 0x11c91}, {0x11ca8, 0x11ca8},
        {0x11cb7, 0x11cff}, {0x11d07, 0x11d07}, {0x11d0a, 0x11d0a}, {0x11d37, 0x11d39},
        {0x11d3b, 0x11d3b}, {0x11d3e, 0x11d3e}, {0x11d48, 0x11d4f}, {0x11d5a, 0x11d5f},
        {0x11d66, 0x11d66}, {0x11d69, 0x11d69}, {0x11d8f, 0x11d8f}, {0x11d92, 0x11d92},
        {0x11d99, 0x11d9f}, {0x11daa, 0x11edf}, {0x11ef9, 0x11eff}, {0x11f11, 0x11f11},
        {0x11f3b, 0x11f3d}, {0x11f5b, 0x11faf}, {0x11fb1, 0x11fbf}, {0x11ff2, 0x11ffe},
        {0x1239a, 0x123ff}, {0x1246f, 0x1246f}, {0x12475, 0x1247f}, {0x12544, 0x12f8f},
        {0x12ff3, 0x12fff}, {0x13430, 0x1343f}, {0x13456, 0x1345f}, {0x143fb, 0x143ff},
        {0x14647, 0x160ff}, {0x1613a, 0x167ff}, {0x16a39, 0x16a3f}, {0x16a5f, 0x16a5f},
        {0x16a6a, 0x16a6d}, {0x16abf, 0x16abf}, {0x16aca, 0x16acf}, {0x16aee, 0x16aef},
        {0x16af6, 0x16aff}, {0x16b46, 0x16b4f}, {0x16b5a, 0x16b5a}, {0x16b62, 0x16b62},
        {0x16b78, 0x16b7c}, {0x16b90, 0x16d3f}, {0x16d7a, 0x16e3f}, {0x16e9b, 0x16eff},
        {0x16f4b, 0x16f4e}, {0x16f88, 0x16f8e}, {0x16fa0, 0x16fdf}, {0x16fe5, 0x16fef},
        {0x16ff2, 0x16fff}, {0x187f8, 0x187ff}, {0x18cd6, 0x18cfe}, {0x18d09, 0x1afef},
        {0x1aff4, 0x1aff4}, {0x1affc, 0x1affc}, {0x1afff, 0x1afff}, {0x1b123, 0x1b131},
        {0x1b133, 0x1b14f}, {0x1b153, 0x1b154}, {0x1b156, 0x1b163}, {0x1b168, 0x1b16f},
        {0x1b2fc, 0x1bbff}, {0x1bc6b, 0x1bc6f}, {0x1bc7d, 0x1bc7f}, {0x1bc89, 0x1bc8f},
        {0x1bc9a, 0x1bc9b}, {0x1bca0, 0x1cbff}, {0x1ccfa, 0x1ccff}, {0x1ceb4, 0x1ceff},
        {0x1cf2e, 0x1cf2f}, {0x1cf47, 0x1cf4f}, {0x1cfc4, 0x1cfff}, {0x1d0f6, 0x1d0ff},
        {0x1d127, 0x1d128}, {0x1d173, 0x1d17a}, {0x1d1eb, 0x1d1ff}, {0x1d246, 0x1d2bf},
        {0x1d2d4, 0x1d2df}, {0x1d2f4, 0x1d2ff}, {0x1d357, 0x1d35f}, {0x1d379, 0x1d3ff},
        {0x1d455, 0x1d455}, {0x1d49d, 0x1d49d}, {0x1d4a0, 0x1d4a1}, {0x1d4a3, 0x1d4a4},
        {0x1d4a7, 0x1d4a8}, {0x1d4ad, 0x1d4ad}, {0x1d4ba, 0x1d4ba}, {0x1d4bc, 0x1d4bc},
        {0x1d4c4, 0x1d4c4}, {0x1d506, 0x1d506}, {0x1d50b, 0x1d50c}, {0x1d515, 0x1d515},
        {0x1d51d, 0x1d51d}, {0x1d53a, 0x1d53a}, {0x1d53f, 0x1d53f}, {0x1d545, 0x1d545},
        {0x1d547, 0x1d549}, {0x1d551, 0x1d551}, {0x1d6a6, 0x1d6a7}, {0x1d7cc, 0x1d7cd},
        {0x1da8c, 0x1da9a}, {0x1daa0, 0x1daa0}, {0x1dab0, 0x1deff}, {0x1df1f, 0x1df24},
        {0x1df2b, 0x1dfff}, {0x1e007, 0x1e007}, {0x1e019, 0x1e01a}, {0x1e022, 0x1e022},
        {0x1e025, 0x1e025}, {0x1e02b, 0x1e02f}, {0x1e06e, 0x1e08e}, {0x1e090, 0x1e0ff},
        {0x1e12d, 0x1e12f}, {0x1e13e, 0x1e13f}, {0x1e14a, 0x1e14d}, {0x1e150, 0x1e28f},
        {0x1e2af, 0x1e2bf}, {0x1e2fa, 0x1e2fe}, {0x1e300, 0x1e4cf}, {0x1e4fa, 0x1e5cf},
        {0x1e5fb, 0x1e5fe}, {0x1e600, 0x1e7df}, {0x1e7e7, 0x1e7e7}, {0x1e7ec, 0x1e7ec},
        {0x1e7ef, 0x1e7ef}, {0x1e7ff, 0x1e7ff}, {0x1e8c5, 0x1e8c6}, {0x1e8d7, 0x1e8ff},
        {0x1e94c, 0x1e94f}, {0x1e95a, 0x1e95d}, {0x1e960, 0x1ec70}, {0x1ecb5, 0x1ed00},
        {0x1ed3e, 0x1edff}, {0x1ee04, 0x1ee04}, {0x1ee20, 0x1ee20}, {0x1ee23, 0x1ee23},
        {0x1ee25, 0x1ee26}, {0x1ee28, 0x1ee28}, {0x1ee33, 0x1ee33}, {0x1ee38, 0x1ee38},
        {0x1ee3a, 0x1ee3a}, {0x1ee3c, 0x1ee41}, {0x1ee43, 0x1ee46}, {0x1ee48, 0x1ee48},
        {0x1ee4a, 0x1ee4a}, {0x1ee4c, 0x1ee4c}, {0x1ee50, 0x1ee50}, {0x1ee53, 0x1ee53},
        {0x1ee55, 0x1ee56}, {0x1ee58, 0x1ee58}, {0x1ee5a, 0x1ee5a}, {0x1ee5c, 0x1ee5c},
        {0x1ee5e, 0x1ee5e}, {0x1ee60, 0x1ee60}, {0x1ee63, 0x1ee63}, {0x1ee65, 0x1ee66},
        {0x1ee6b, 0x1ee6b}, {0x1ee73, 0x1ee73}, {0x1ee78, 0x1ee78}, {0x1ee7d, 0x1ee7d},
        {0x1ee7f, 0x1ee7f}, {0x1ee8a, 0x1ee8a}, {0x1ee9c, 0x1eea0}, {0x1eea4, 0x1eea4},
        {0x1eeaa, 0x1eeaa}, {0x1eebc, 0x1eeef}, {0x1eef2, 0x1efff}, {0x1f02c, 0x1f02f},
        {0x1f094, 0x1f09f}, {0x1f0af, 0x1f0b0}, {0x1f0c0, 0x1f0c0}, {0x1f0d0, 0x1f0d0},
        {0x1f0f6, 0x1f0ff}, {0x1f1ae, 0x1f1e5}, {0x1f203, 0x1f20f}, {0x1f23c, 0x1f23f},
        {0x1f249, 0x1f24f}, {0x1f252, 0x1f25f}, {0x1f266, 0x1f2ff}, {0x1f6d8, 0x1f6db},
        {0x1f6ed, 0x1f6ef}, {0x1f6fd, 0x1f6ff}, {0x1f777, 0x1f77a}, {0x1f7da, 0x1f7df},
        {0x1f7ec, 0x1f7ef}, {0x1f7f1, 0x1f7ff}, {0x1f80c, 0x1f80f}, {0x1f848, 0x1f84f},
        {0x1f85a, 0x1f85f}, {0x1f888, 0x1f88f}, {0x1f8ae, 0x1f8af}, {0x1f8bc, 0x1f8bf},
        {0x1f8c2, 0x1f8ff}, {0x1fa54, 0x1fa5f}, {0x1fa6e, 0x1fa6f}, {0x1fa7d, 0x1fa7f},
        {0x1fa8a, 0x1fa8e}, {0x1fac7, 0x1facd}, {0x1fadd, 0x1fade}, {0x1faea, 0x1faef},
        {0x1faf9, 0x1faff}, {0x1fb93, 0x1fb93}, {0x1fbfa, 0x1ffff}, {0x2a6e0, 0x2a6ff},
        {0x2b73a, 0x2b73f}, {0x2b81e, 0x2b81f}, {0x2cea2, 0x2ceaf}, {0x2ebe1, 0x2ebef},
        {0x2ee5e, 0x2f7ff}, {0x2fa1e, 0x2ffff}, {0x3134b, 0x3134f}, {0x323b0, 0xe00ff},
        {0xe01f0, 0x10ffff},
    };
    return !in_ranges(cp, ranges);
}

std::string normalized(const std::string& s, bool regex_case = true) {
    std::string out;
    for (std::size_t pos = 0; pos < s.size();) {
        const auto first = pos;
        auto cp = next_codepoint(s, pos);
        if (cp >= 'a' && cp <= 'z') cp -= 'a' - 'A';
        if (cp == 0x131 || (regex_case && cp == 0x130)) cp = 'I';
        if (cp == 0x17f) cp = 'S';
        if (regex_case && cp == 0x212a) cp = 'K';
        if (!regex_case && cp == 0xdf) { out += "SS"; continue; }
        if (cp > 127 && decimal_digit(cp)) cp = '0';
        if (cp < 0x80) out += static_cast<char>(cp);
        else out.append(s, first, pos - first);
    }
    return out;
}
bool ground(const std::string& name) {
    const auto up = normalized(name);
    for (const auto* p : {"GND", "GNDA", "GNDD", "GNDPWR", "AGND", "DGND", "PGND",
                          "VSS", "VSSA", "VSSIO", "CHASSIS_GND"})
        if (starts(up, p)) return true;
    return false;
}

// Python's $ also matches immediately before a final newline. Do not trim any
// other whitespace; names and author reasons are otherwise passed verbatim.
std::string dollar_name(std::string name) {
    if (!name.empty() && name.back() == '\n') name.pop_back();
    return name;
}
bool config_pin(const std::string& name) {
    const auto up = dollar_name(normalized(name));
    for (const auto* exact : {"NOE", "OE", "NCS", "CS", "NCE", "CE", "SET", "POL"})
        if (up == exact) return true;
    for (const auto* pre : {"MODE", "ADDR", "A", "SEL", "CFG", "STRAP", "CONFIG", "S"}) {
        const std::string prefix(pre);
        if (!starts(up, prefix)) continue;
        const auto count = up.size() - prefix.size();
        if (prefix == "A" && (count < 1 || count > 2)) continue;
        if (prefix == "S" && count != 1) continue;
        if (std::all_of(up.begin() + static_cast<std::ptrdiff_t>(prefix.size()), up.end(),
                        [](char c) { return c >= '0' && c <= '9'; })) return true;
    }
    return false;
}
bool ep_pin(const std::string& name) {
    const auto up = dollar_name(normalized(name));
    for (const auto* exact : {"PPAD", "GNDPAD", "GND_PAD", "DAP"}) if (up == exact) return true;
    if (starts(up, "THERMAL") && up.find('\n') == std::string::npos) return true;
    for (const auto* pre : {"EP", "PAD", "EPAD"}) {
        const std::string prefix(pre);
        if (starts(up, prefix) && std::all_of(up.begin() + static_cast<std::ptrdiff_t>(prefix.size()), up.end(),
                                            [](char c) { return c >= '0' && c <= '9'; })) return true;
    }
    return false;
}
bool reset_net(const std::string& name) {
    const auto up = dollar_name(normalized(name));
    for (std::size_t at = 0; at < up.size(); ++at) {
        if (at != 0 && up[at - 1] != '_') continue;
        for (const auto* token : {"RST", "NRST", "RESET", "NRESET", "SRST", "POR"}) {
            const std::string word(token);
            if (up.compare(at, word.size(), word) != 0) continue;
            const auto end = at + word.size();
            if (end == up.size() || up[end] == '_' || up[end] == 'N' || up[end] == 'B') return true;
        }
    }
    return false;
}
bool internal_pull(const std::string& name) {
    const auto up = normalized(name);
    for (auto at = up.find("STM32"); at != std::string::npos; at = up.find("STM32", at + 5)) {
        const auto target = up.find("NRST", at + 5);
        if (target != std::string::npos && target < up.find('\n', at + 5)) return true;
    }
    return false;
}
bool driver_type(const std::string& etype) {
    return etype == "output" || etype == "bidirectional" || etype == "tri_state"
        || etype == "power_out" || etype == "open_collector" || etype == "open_emitter";
}
std::string repr(const std::string& s) {
    const char quote = s.find('\'') != std::string::npos && s.find('"') == std::string::npos ? '"' : '\'';
    std::string out(1, quote);
    constexpr char hex[] = "0123456789abcdef";
    for (std::size_t pos = 0; pos < s.size();) {
        const auto first = pos;
        const auto cp = next_codepoint(s, pos);
        if (cp == static_cast<unsigned char>(quote) || cp == '\\') { out += '\\'; out += static_cast<char>(cp); }
        else if (cp == '\n') out += "\\n";
        else if (cp == '\r') out += "\\r";
        else if (cp == '\t') out += "\\t";
        else if (!printable(cp)) {
            const int width = cp <= 0xff ? 2 : cp <= 0xffff ? 4 : 8;
            out += width == 2 ? "\\x" : width == 4 ? "\\u" : "\\U";
            for (int i = width - 1; i >= 0; --i) out += hex[(cp >> (4 * i)) & 15];
        } else out.append(s, first, pos - first);
    }
    return out + quote;
}
std::string list_repr(Strings values) {
    if (values.empty()) return "none";
    std::sort(values.begin(), values.end());
    for (auto& value : values) value = repr(value);
    return "[" + join(values, ", ") + "]";
}
std::string padded(const std::string& s, std::size_t width) {
    std::size_t count = 0;
    for (std::size_t pos = 0; pos < s.size(); ++count) next_codepoint(s, pos);
    return s + std::string(count < width ? width - count : 0, ' ');
}

template<class T>
const T* lookup(const std::vector<std::pair<std::string, T>>& values, const std::string& key) {
    for (const auto& entry : values) if (entry.first == key) return &entry.second;
    return nullptr;
}
template<class T>
std::vector<std::pair<std::string, T>> sorted(const std::vector<std::pair<std::string, T>>& values) {
    auto out = values;
    std::sort(out.begin(), out.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
    return out;
}
template<class T>
T& ordered_slot(std::vector<std::pair<std::string, T>>& values,
                std::unordered_map<std::string, std::size_t>& index, const std::string& key) {
    const auto item = index.emplace(key, values.size());
    if (item.second) values.emplace_back(key, T{});
    return values[item.first->second].second;
}
std::size_t count(const DesignRuleResult& result, const std::string& key) {
    const auto* value = lookup(result.checked, key);
    return value ? *value : 0;
}

struct Pins {
    std::vector<SymbolPin> all;
    bool multipin = false;
    std::map<std::string, Strings> supplies;
    std::vector<std::size_t> config, ep;
    std::unordered_set<std::string> drivers;
};
struct PinKeyHash {
    std::size_t operator()(const PinKey& key) const {
        const auto a = std::hash<std::string>{}(key.first), b = std::hash<std::string>{}(key.second);
        return a ^ (b + 0x9e3779b9U + (a << 6) + (a >> 2));
    }
};
struct SheetIndex {
    std::vector<const CircuitPartIr*> parts;  // lexical ref order
    std::unordered_map<std::string, const CircuitPartIr*> part_by_ref;
    std::unordered_map<PinKey, const CircuitNetIr*, PinKeyHash> net_by_pin;
    std::unordered_map<const CircuitNetIr*, std::set<PinKey>> drivers;
    std::unordered_set<std::string> bypassed;
    std::unordered_map<std::string, std::unordered_map<std::string, std::string>> waivers;

    const CircuitNetIr* net(const std::string& ref, const std::string& number) const {
        const auto it = net_by_pin.find({ref, number});
        return it == net_by_pin.end() ? nullptr : it->second;
    }
    const std::string* waiver(const std::string& kind, const Strings& keys) const {
        const auto it = waivers.find(kind);
        if (it == waivers.end()) return nullptr;
        for (const auto& key : keys) {
            const auto w = it->second.find(key);
            if (w != it->second.end()) return &w->second;
        }
        return nullptr;
    }
};
using NetLocations = std::unordered_map<std::string, std::set<std::string>>;
Strings locations(const NetLocations& values, const std::string& net) {
    const auto it = values.find(net);
    return it == values.end() ? Strings{} : Strings(it->second.begin(), it->second.end());
}

JsonNode js(const std::string& value) { JsonNode n; n.kind = JsonKind::String; n.string_value = value; return n; }
JsonNode jb(bool value) { JsonNode n; n.kind = JsonKind::Bool; n.bool_value = value; return n; }
JsonNode jn(std::size_t value) { JsonNode n; n.kind = JsonKind::Number; n.number_value = static_cast<double>(value); return n; }
JsonNode ja(const Strings& values) {
    JsonNode n; n.kind = JsonKind::Array;
    for (const auto& value : values) n.array_value.push_back(js(value));
    return n;
}
template<class T, class F>
JsonNode jo(const std::vector<std::pair<std::string, T>>& values, F convert) {
    JsonNode n; n.kind = JsonKind::Object;
    for (const auto& value : values) n.object_value.emplace_back(value.first, convert(value.second));
    return n;
}
}  // namespace

struct DesignRuleIndex::Impl {
    std::vector<CircuitSheetIr> sheets;
    std::vector<SheetIndex> indices;
    std::unordered_map<std::string, Pins> symbols;
    std::unordered_map<std::string, std::vector<std::size_t>> net_sheets;
    std::map<std::string, std::string> i2c_nets, reset_nets;
    NetLocations pulls, resistors, capacitors;
    TestpointCoverage coverage;
    std::string unnetted_testpoint;

    Impl(std::vector<CircuitSheetIr> input, const DesignRuleSymbolResolver& resolve)
        : sheets(std::move(input)), indices(sheets.size()) {
        // Coverage has no symbol dependency. Defer its legacy StopIteration
        // failure until that check is requested, so it cannot change the
        // behavior of callers running only the electrical completeness gate.
        try { coverage = check_testpoint_coverage(sheets); }
        catch (const UnnettedTestpoint& error) { unnetted_testpoint = error.what(); }
        // Resolve/classify once per library ID, independent of part quantity.
        for (const auto& sc : sheets) for (const auto& part : sc.parts) {
            if (symbols.count(part.lib_id)) continue;
            Pins pins;
            const SymbolDef* definition = nullptr;
            try { definition = &resolve(part.lib_id); }
            catch (const std::bad_alloc&) { throw; }
            catch (const std::system_error&) { throw; }
            catch (const std::exception&) { /* Python unresolved-symbol skip. */ }
            if (definition) pins.all = definition->pins;
            std::unordered_set<std::string> numbers;
            for (std::size_t i = 0; i < pins.all.size(); ++i) {
                const auto& p = pins.all[i];
                numbers.insert(p.number);
                if (is_power_pin_name(p.name) || (p.etype == "power_in" && !ground(p.name)))
                    pins.supplies[p.name].push_back(p.number);
                if (config_pin(p.name)) pins.config.push_back(i);
                if (ep_pin(p.name)) pins.ep.push_back(i);
                if (driver_type(p.etype)) pins.drivers.insert(p.number);
            }
            pins.multipin = numbers.size() > 2 && !ends(part.lib_id, ":R")
                && !ends(part.lib_id, ":C") && !ends(part.lib_id, ":L");
            for (auto& supply : pins.supplies) std::sort(supply.second.begin(), supply.second.end());
            symbols.emplace(part.lib_id, std::move(pins));
        }
        for (std::size_t i = 0; i < sheets.size(); ++i) {
            const auto& sc = sheets[i];
            auto& idx = indices[i];
            for (const auto& part : sc.parts) {
                idx.parts.push_back(&part);
                idx.part_by_ref.emplace(part.ref, &part);
            }
            std::sort(idx.parts.begin(), idx.parts.end(), [](const auto* a, const auto* b) { return a->ref < b->ref; });
            for (const auto& w : sc.waivers) idx.waivers[w.kind][w.key] = w.reason;
            for (const auto& pt : sc.port_types) if (pt.kind == "i2c") i2c_nets.emplace(pt.net, sc.name);
            for (const auto& net : sc.nets) {
                net_sheets[net.name].push_back(i);
                if (reset_net(net.name)) reset_nets.emplace(net.name, sc.name);
                for (const auto& pr : net.pins) {
                    // net_of() returns the first occurrence, even for unchecked
                    // mutation inputs with multiply connected pins.
                    idx.net_by_pin.emplace(PinKey{pr.ref, pr.pin}, &net);
                    const auto op = idx.part_by_ref.find(pr.ref);
                    if (op != idx.part_by_ref.end()
                        && symbols.at(op->second->lib_id).drivers.count(pr.pin))
                        idx.drivers[&net].emplace(pr.ref, pr.pin);
                }
            }
            for (const auto* part : idx.parts) {
                const bool cap = ends(part->lib_id, ":C"), res = ends(part->lib_id, ":R");
                if (!cap && !res) continue;
                std::map<std::string, bool> names; // name -> any POWER occurrence
                bool grounded = false;
                for (const auto& pin : symbols.at(part->lib_id).all) {
                    const auto* net = idx.net(part->ref, pin.number);
                    if (!net) continue;
                    names[net->name] = names[net->name] || net->net_class == "power";
                    grounded = grounded || ground(net->name);
                }
                const auto loc = sc.name + ":" + part->ref;
                for (const auto& name : names) {
                    if (cap && grounded) {
                        capacitors[name.first].insert(loc);
                        if (!name.first.empty() && !ground(name.first)) idx.bypassed.insert(name.first);
                    }
                    if (res) {
                        resistors[name.first].insert(loc);
                        for (const auto& other : names)
                            if (other.first != name.first && other.second)
                                pulls[name.first].insert(loc + "->" + other.first);
                    }
                }
            }
        }
    }

    const std::string* board_waiver(const std::string& kind, const std::string& net) const {
        const auto it = net_sheets.find(net);
        if (it != net_sheets.end()) for (const auto i : it->second)
            if (const auto* value = indices[i].waiver(kind, {net})) return value;
        return nullptr;
    }

    DesignRuleResult check() const {
        DesignRuleResult out;
        std::size_t decap_count = 0, strap_count = 0, ep_count = 0;
        for (std::size_t i = 0; i < sheets.size(); ++i) {
            const auto& sc = sheets[i]; const auto& idx = indices[i];
            for (const auto* part : idx.parts) {
                const auto& pins = symbols.at(part->lib_id);
                if (!pins.multipin) continue;
                for (const auto& supply : pins.supplies) {
                    std::map<std::string, Strings> rails;
                    for (const auto& pn : supply.second) {
                        const auto* n = idx.net(part->ref, pn);
                        rails[n && !n->name.empty() ? n->name : "<unconnected>"].push_back(pn);
                    }
                    for (const auto& rail : rails) {
                        if (rail.first == "<unconnected>" || ground(rail.first)) continue;
                        ++decap_count;
                        if (const auto* w = idx.waiver("decap_waivers", {part->ref + "." + rail.second.front(), part->ref, rail.first})) {
                            out.waived.push_back("DECAP " + sc.name + ":" + part->ref + "." + supply.first + " (" + rail.first + "): " + *w);
                        } else if (!idx.bypassed.count(rail.first)) {
                            out.decap.push_back(sc.name + ":" + part->ref + "." + supply.first + " (pin "
                                + join(rail.second, ",") + ") on rail " + repr(rail.first)
                                + " has no decoupling cap to GND on this sheet (" + part->value
                                + ") — add a bypass cap or c.waive_decap(" + repr(part->ref) + ", reason)");
                        }
                    }
                }
            }
        }
        for (const auto& net : i2c_nets) {
            if (const auto* w = board_waiver("pull_waivers", net.first))
                out.waived.push_back("I2C " + net.first + " (typed on " + net.second + "): " + *w);
            else if (!pulls.count(net.first))
                out.i2c.push_back(net.first + " (i2c, typed on " + net.second
                    + ") has NO pull-up resistor to any power rail anywhere on the board — an open-drain I2C bus is dead without pull-ups; add a pull-up or c.waive_pull("
                    + repr(net.first) + ", reason)");
        }
        for (const auto& net : reset_nets) {
            const auto prefix = "RESET " + net.first + " (on " + net.second + "): ";
            if (internal_pull(net.first)) {
                out.waived.push_back(prefix + "internal-pull whitelist (part provides its own pull; external RC optional)");
                continue;
            }
            if (const auto* w = board_waiver("reset_waivers", net.first)) {
                out.waived.push_back(prefix + *w); continue;
            }
            const auto caps = locations(capacitors, net.first), rs = locations(resistors, net.first);
            if (!caps.empty() && !rs.empty()) continue;
            Strings miss, have;
            if (caps.empty()) miss.push_back("no cap-to-GND"); else have.push_back("cap @ " + join(caps, ", "));
            if (rs.empty()) miss.push_back("no pull resistor"); else have.push_back("pull @ " + join(rs, ", "));
            out.reset.push_back(net.first + " (reset, on " + net.second + ") lacks a complete RC: "
                + join(miss, "; ") + (have.empty() ? "" : " (has " + join(have, "; ") + ")")
                + " — add the missing element or c.waive_reset(" + repr(net.first) + ", reason)");
        }
        for (std::size_t i = 0; i < sheets.size(); ++i) {
            const auto& sc = sheets[i]; const auto& idx = indices[i];
            for (const auto* part : idx.parts) {
                const auto& pins = symbols.at(part->lib_id);
                if (!pins.multipin) continue;
                for (const auto pin_index : pins.config) {
                    const auto& p = pins.all[pin_index];
                    const auto* n = idx.net(part->ref, p.number);
                    if (!n || n->net_class == "port" || n->net_class == "power" || n->net_class == "ground") continue;
                    ++strap_count;
                    const auto drivers = idx.drivers.find(n);
                    const PinKey own{part->ref, p.number};
                    if (drivers != idx.drivers.end() && (drivers->second.size() > 1 || !drivers->second.count(own))) continue;
                    if (const auto* w = idx.waiver("strap_waivers", {part->ref + "." + p.number, part->ref + "." + p.name, part->ref, n->name})) {
                        out.waived.push_back("STRAP " + sc.name + ":" + part->ref + "." + p.name + " (" + n->name + "): " + *w);
                        continue;
                    }
                    Strings others;
                    for (const auto& pr : n->pins)
                        if (PinKey{pr.ref, pr.pin} != own) others.push_back(pr.ref + "." + pr.pin);
                    out.strap.push_back(sc.name + ":" + part->ref + "." + p.name + " (pin " + p.number + ", " + part->value
                        + ") is a config input on passive-only undriven net " + repr(n->name)
                        + " (other pins: " + list_repr(others) + ") — strap it to a rail/GND or drive it, or c.waive_strap("
                        + repr(part->ref) + ", reason)");
                }
            }
        }
        for (std::size_t i = 0; i < sheets.size(); ++i) {
            const auto& sc = sheets[i]; const auto& idx = indices[i];
            for (const auto* part : idx.parts) {
                const auto& pins = symbols.at(part->lib_id);
                for (const auto pin_index : pins.ep) {
                    const auto& p = pins.all[pin_index]; ++ep_count;
                    const auto* n = idx.net(part->ref, p.number);
                    if (n && ground(n->name)) continue;
                    Strings keys{part->ref + "." + p.number, part->ref + "." + p.name, part->ref};
                    if (n && !n->name.empty()) keys.push_back(n->name);
                    if (const auto* w = idx.waiver("ep_waivers", keys)) {
                        out.waived.push_back("EP " + sc.name + ":" + part->ref + "." + p.name + " ("
                            + (n ? n->name : "unconnected") + "): " + *w); continue;
                    }
                    out.ep.push_back(sc.name + ":" + part->ref + "." + p.name + " (pin " + p.number + ", " + part->value
                        + ") exposed pad is " + (n ? "on non-GROUND net " + repr(n->name) : "UNCONNECTED (nc/floating)")
                        + " — net it to GND, or c.waive_ep(" + repr(part->ref) + ", reason)");
                }
            }
        }
        out.checked = {{"decap", decap_count}, {"i2c", i2c_nets.size()}, {"reset", reset_nets.size()},
                       {"strap", strap_count}, {"ep", ep_count}};
        return out;
    }
};

DesignRuleIndex::DesignRuleIndex(std::vector<CircuitSheetIr> sheets, const DesignRuleSymbolResolver& resolve)
    : impl_(std::make_shared<Impl>(std::move(sheets), resolve)) {}
DesignRuleIndex::DesignRuleIndex(std::vector<CircuitSheetIr> sheets, const std::vector<SymbolDef>& symbols) {
    std::unordered_map<std::string, const SymbolDef*> defs;
    for (const auto& def : symbols) defs.emplace(def.lib_id, &def);
    impl_ = std::make_shared<Impl>(std::move(sheets), [&](const std::string& id) -> const SymbolDef& {
        return *defs.at(id);
    });
}
DesignRuleResult DesignRuleIndex::check() const { return impl_->check(); }
TestpointCoverage DesignRuleIndex::check_testpoints() const {
    if (!impl_->unnetted_testpoint.empty()) throw UnnettedTestpoint(impl_->unnetted_testpoint);
    return impl_->coverage;
}
DesignRuleResult check_design_rules(const std::vector<CircuitSheetIr>& sheets, const DesignRuleSymbolResolver& resolve) {
    return DesignRuleIndex(sheets, resolve).check();
}
DesignRuleResult check_design_rules(const std::vector<CircuitSheetIr>& sheets, const std::vector<SymbolDef>& symbols) {
    return DesignRuleIndex(sheets, symbols).check();
}

bool is_power_pin_name(const std::string& name) {
    // upper(), not IGNORECASE: dotted capital I is not interchangeable here.
    const auto up = normalized(name, false);
    if (up.empty() || ground(up) || starts(up, "VOUT") || starts(up, "VO_")) return false;
    for (const auto* pre : {"VDDIO", "VDDA", "VDDD", "VDDQ", "VDD", "VCCIO", "VCCA", "VCCB", "VCC5V", "VCC3V3", "VCC",
                            "AVDD", "AVCC", "DVDD", "PVDD", "VBAT", "VBACKUP", "VSYS", "VIN", "VPP", "VREF", "VPU",
                            "VANA", "VCORE", "VDRV", "VAUX", "VL", "VS"}) {
        const std::string prefix(pre);
        if (up == prefix) return true;
        if (!starts(up, prefix)) continue;
        auto pos = prefix.size();
        const auto next = next_codepoint(up, pos);
        if (next == '_' || python_digit(next)) return true;
    }
    return false;
}

TestpointCoverage check_testpoint_coverage(const std::vector<CircuitSheetIr>& sheets) {
    TestpointCoverage out;
    std::unordered_map<std::string, std::size_t> required, have, waived;
    for (const auto& sc : sheets) {
        std::unordered_map<std::string, std::string> port_types, first_net;
        for (const auto& pt : sc.port_types) port_types[pt.net] = pt.kind;
        for (const auto& net : sc.nets) {
            for (const auto& pr : net.pins) first_net.emplace(pr.ref, net.name);
            std::string kind;
            if (net.net_class == "power" || net.net_class == "ground") kind = "rail";
            else if (net.net_class == "port") {
                const auto type = port_types.find(net.name);
                if (type != port_types.end() && type->second == "i2c") kind = "i2c";
                else if (type != port_types.end() && type->second == "sd_bus" && (ends(net.name, "CMD") || ends(net.name, "CLK"))) kind = "sd_bus";
                else {
                    // \d is Unicode-aware in Python; UART and suffix are case-sensitive.
                    std::string digits;
                    for (std::size_t p = 0; p < net.name.size();) {
                        const auto first = p; const auto cp = next_codepoint(net.name, p);
                        if (decimal_digit(cp)) digits += '0'; else digits.append(net.name, first, p - first);
                    }
                    digits = dollar_name(std::move(digits));
                    bool uart = false;
                    if (ends(digits, "_TXD") || ends(digits, "_RXD")) {
                        auto at = digits.size() - 4;
                        while (at > 0 && digits[at - 1] >= '0' && digits[at - 1] <= '9') --at;
                        uart = at >= 4 && digits.compare(at - 4, 4, "UART") == 0;
                    }
                    if (uart) kind = "uart";
                    else if (starts(net.name, "EN_") || ends(dollar_name(net.name), "_EN")) kind = "enable";
                }
            }
            if (!kind.empty() && !required.count(net.name)) ordered_slot(out.required, required, net.name) = kind;
        }
        std::vector<const CircuitPartIr*> parts;
        for (const auto& p : sc.parts) if (p.lib_id == "Connector:TestPoint") parts.push_back(&p);
        std::sort(parts.begin(), parts.end(), [](const auto* a, const auto* b) { return a->ref < b->ref; });
        for (const auto* p : parts) {
            const auto net = first_net.find(p->ref);
            if (net == first_net.end()) throw UnnettedTestpoint(sc.name + ":" + p->ref + ": test point carries no net");
            ordered_slot(out.have, have, net->second).push_back(sc.name + ":" + p->ref);
        }
        for (const auto& w : sc.waivers) if (w.kind == "tp_waivers")
            ordered_slot(out.waived, waived, w.key) = {sc.name, w.reason};
    }
    for (const auto& net : sorted(out.required)) if (!have.count(net.first) && !waived.count(net.first))
        out.errors.push_back(net.first + " [" + net.second + "] has no test point and no waiver — add c.testpoint("
            + repr(net.first) + ") or c.waive_tp(" + repr(net.first) + ", reason)");
    return out;
}

bool DesignRuleResult::ok() const { return decap.empty() && i2c.empty() && reset.empty() && strap.empty() && ep.empty(); }
Strings DesignRuleResult::findings() const {
    Strings out;
    for (const auto* group : {&decap, &i2c, &reset, &strap, &ep}) out.insert(out.end(), group->begin(), group->end());
    return out;
}
std::string DesignRuleResult::summary() const {
    if (ok()) return "DESIGN RULES: PASS (netlist electrically complete — " + std::to_string(count(*this, "decap"))
        + " IC supply pins, " + std::to_string(count(*this, "i2c")) + " I2C nets, " + std::to_string(count(*this, "reset"))
        + " reset nets, " + std::to_string(count(*this, "strap")) + " strap pins, " + std::to_string(count(*this, "ep"))
        + " exposed pads checked; " + std::to_string(waived.size()) + " waived)";
    Strings lines{"DESIGN RULES: FAIL"};
    for (const auto& group : std::vector<std::pair<std::string, const Strings*>>{{"DECAP", &decap}, {"I2C", &i2c}, {"RESET", &reset}, {"STRAP", &strap}, {"EP", &ep}})
        for (const auto& item : *group.second) lines.push_back("  " + group.first + ": " + item);
    return join(lines, "\n");
}
std::string DesignRuleResult::report() const {
    Strings lines{"schgen design-rule completeness gate", std::string(64, '='), "",
        "rules (model-only, pin FUNCTION inferred by NAME):",
        "  DECAP every multi-pin IC supply pin has a cap to GND on its sheet",
        "  I2C   every i2c-typed bus net has a pull-up to a rail (board-wide)",
        "  RESET every reset net carries an RC (cap-to-GND + pull resistor)",
        "  STRAP no config-input pin floats on a passive-only undriven net",
        "  EP    every exposed/thermal pad is netted to a GROUND net (never nc/floating, never a non-GND net)", "",
        "checked: " + std::to_string(count(*this, "decap")) + " IC supply pins, " + std::to_string(count(*this, "i2c"))
        + " i2c nets, " + std::to_string(count(*this, "reset")) + " reset nets, " + std::to_string(count(*this, "strap"))
        + " config pins, " + std::to_string(count(*this, "ep")) + " exposed pads", ""};
    struct Group { const char* tag; const char* label; const Strings* items; };
    for (const auto& g : std::vector<Group>{{"DECAP", "missing decoupling", &decap}, {"I2C", "i2c bus with no pull-up", &i2c},
         {"RESET", "reset without a full RC", &reset}, {"STRAP", "floating control input", &strap}, {"EP", "exposed pad not on GND", &ep}}) {
        lines.push_back(std::string(g.tag) + " — " + g.label + " (" + std::to_string(g.items->size()) + "):");
        for (const auto& item : *g.items) lines.push_back("  * " + item);
        if (g.items->empty()) lines.push_back("  (none)");
        lines.emplace_back();
    }
    lines.push_back("waivers — author-declared, verbatim (" + std::to_string(waived.size()) + "):");
    for (const auto& w : waived) lines.push_back("  " + w);
    if (waived.empty()) lines.push_back("  (none)");
    lines.emplace_back();
    lines.push_back(std::string("DESIGN RULES: ") + (ok() ? "PASS" : "FAIL") + " (" + std::to_string(findings().size())
        + " findings, " + std::to_string(waived.size()) + " waived)");
    return join(lines, "\n");
}
bool TestpointCoverage::ok() const { return errors.empty(); }
std::size_t TestpointCoverage::covered() const {
    std::size_t count = 0;
    for (const auto& net : required) if (lookup(have, net.first)) ++count;
    return count;
}
std::string TestpointCoverage::report() const {
    Strings lines{"schgen test-point coverage gate", std::string(64, '='), "",
        "rule: every POWER/GROUND rail + key single-ended bus (i2c ports, sd_bus CMD/CLK, UART RXD/TXD, EN lines) owns a probe point or an explicit waiver.", "",
        "required nets (" + std::to_string(required.size()) + "):"};
    for (const auto& net : sorted(required)) {
        std::string state = "UNCOVERED";
        if (const auto* loc = lookup(have, net.first)) state = "TP @ " + join(*loc, ", ");
        else if (const auto* w = lookup(waived, net.first)) state = "WAIVED (" + w->first + "): " + w->second;
        lines.push_back("  " + padded(net.first, 22) + " [" + padded(net.second, 9) + "] " + state);
    }
    std::vector<std::pair<std::string, Strings>> extra;
    for (const auto& net : have) if (!lookup(required, net.first)) extra.push_back(net);
    if (!extra.empty()) {
        lines.emplace_back(); lines.push_back("additional probe points (" + std::to_string(extra.size()) + "):");
        for (const auto& net : sorted(extra)) lines.push_back("  " + padded(net.first, 22) + " TP @ " + join(net.second, ", "));
    }
    if (!waived.empty()) {
        lines.emplace_back(); lines.push_back("waivers — author-declared, verbatim (" + std::to_string(waived.size()) + "):");
        for (const auto& w : sorted(waived)) lines.push_back("  " + padded(w.first, 22) + " (" + w.second.first + ") " + w.second.second);
    }
    lines.emplace_back();
    if (!errors.empty()) {
        lines.push_back("ERRORS (" + std::to_string(errors.size()) + "):");
        for (const auto& e : errors) lines.push_back("  ERROR: " + e);
    } else lines.push_back("errors: none");
    lines.emplace_back();
    lines.push_back(std::string("TESTPOINTS: ") + (ok() ? "PASS" : "FAIL") + " (" + std::to_string(covered()) + "/"
        + std::to_string(required.size()) + " required nets covered, " + std::to_string(waived.size()) + " waived)");
    return join(lines, "\n");
}

JsonNode design_rule_result_json(const DesignRuleResult& r) {
    JsonNode out; out.kind = JsonKind::Object;
    out.object_value = {{"decap", ja(r.decap)}, {"i2c", ja(r.i2c)}, {"reset", ja(r.reset)}, {"strap", ja(r.strap)},
        {"ep", ja(r.ep)}, {"waived", ja(r.waived)}, {"checked", jo(r.checked, jn)}, {"ok", jb(r.ok())},
        {"findings", ja(r.findings())}, {"summary", js(r.summary())}, {"report", js(r.report())}};
    return out;
}
JsonNode testpoint_coverage_json(const TestpointCoverage& r) {
    JsonNode out; out.kind = JsonKind::Object;
    out.object_value = {{"required", jo(r.required, js)}, {"have", jo(r.have, ja)},
        {"waived", jo(r.waived, [](const auto& w) { return ja({w.first, w.second}); })},
        {"errors", ja(r.errors)}, {"extras", jo(r.extras, ja)}, {"ok", jb(r.ok())}, {"covered", jn(r.covered())}, {"report", js(r.report())}};
    return out;
}

}  // namespace schgen
