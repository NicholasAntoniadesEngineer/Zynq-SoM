#pragma once
#include "schgen/spice.hpp"
#include <stdexcept>

// Test-only transport for retained historical fixtures. Never use these
// quantization scales for current calculations, verdicts or published output.
inline double historical_spice_scale(const schgen::SpiceCheck& check){
    if(check.kind=="iset")return 10;
    if(check.kind=="rc"||check.kind=="en_clamp"||check.name=="BOOT0 strap VIH")return 1000;
    if(check.kind=="divider"||check.kind=="fb_divider")return 10000;
    throw std::runtime_error("unreviewed historical SPICE precision: "+check.kind);
}
