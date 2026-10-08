#pragma once
#include <charconv>
#include <cmath>
#include <string>

namespace schgen::test {
// Workflow transport is frozen, but an improved optimiser need not repeat the
// historical prediction. Permit only finite, non-regressing margin/area for
// the SAME single ranked edit; everything else remains byte-exact. Independent
// model/ledger checks in the callers remain the acceptance authority.
inline bool compose_workflow_output(const std::string& actual,const std::string& historical) {
    const std::string marker=": predicted agg-hard-margin ",separator=", area ";
    const auto parse=[&](const std::string& text,std::size_t& begin,std::size_t& end,double& margin,double& area) {
        const auto m=text.find(marker);
        if(m==std::string::npos||text.find(marker,m+marker.size())!=std::string::npos)return false;
        begin=text.rfind('\n',m);begin=begin==std::string::npos?0:begin+1;
        end=text.find('\n',m);
        const auto a=text.find(separator,m+marker.size());
        if(end==std::string::npos||a==std::string::npos||a>=end)return false;
        const auto number=[&](std::size_t first,std::size_t last,double& value) {
            const auto result=std::from_chars(text.data()+first,text.data()+last,value);
            return result.ec==std::errc{}&&result.ptr==text.data()+last&&std::isfinite(value);
        };
        return number(m+marker.size(),a,margin)&&number(a+separator.size(),end,area)&&area>0;
    };
    std::size_t ab=0,ae=0,hb=0,he=0;double am=0,aa=0,hm=0,ha=0;
    if(!parse(actual,ab,ae,am,aa)||!parse(historical,hb,he,hm,ha)||am<hm||aa>ha)return false;
    const auto ap=actual.find(marker),hp=historical.find(marker);
    if(actual.substr(ab,ap-ab)!=historical.substr(hb,hp-hb))return false;
    auto normalized=actual;normalized.replace(ab,ae-ab,historical.substr(hb,he-hb));
    return normalized==historical;
}
}
