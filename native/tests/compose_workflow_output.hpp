#pragma once
#include <charconv>
#include <cmath>
#include <string>

namespace schgen::test {
// Workflow transport is frozen, but an improved optimiser need not repeat the
// historical prediction. Permit only finite, non-regressing margin/area for
// the SAME single ranked edit; everything else remains byte-exact. Independent
// model/ledger checks in the callers remain the acceptance authority.
inline bool compose_workflow_output(const std::string& raw_actual,const std::string& historical) {
    auto actual=raw_actual;
    // This frozen workflow has one spatial term and no facing term. Only in
    // that case is its old aggregate comparable to the new spatial minimum.
    const std::string unit_marker=": predicted min margin ";
    if(const auto at=actual.find(unit_marker);at!=std::string::npos) {
        const auto split=actual.find(" mm / unavailable degrees, area ",at);
        const auto end=actual.find(" mm^2\n",at);
        if(split==std::string::npos||end==std::string::npos||split>=end)return false;
        actual.erase(end,5);
        actual.replace(split,std::string(" mm / unavailable degrees, area ").size(),", area ");
        actual.replace(at,unit_marker.size(),": predicted agg-hard-margin ");
        const std::string policy="compose: ranked candidates (soft RED, area, minimum mm margin, minimum degree margin, edit; replica ORDER only";
        if(const auto p=actual.find(policy);p!=std::string::npos)
            actual.replace(p,policy.size(),"compose: ranked candidates (replica ORDER only");
    }
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
