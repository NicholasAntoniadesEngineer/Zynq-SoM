#include "schgen/procurement.hpp"
#include "schgen/process.hpp"
#include "verification_internal.hpp"
#include <iomanip>
#include <limits>
#include <locale>

namespace schgen {
namespace {
using namespace verification;
std::string column(std::string text, std::size_t width, bool right = false) {
    const auto length = utf8(text).size();
    if (length >= width) return text;
    const std::string padding(width - length, ' ');
    return right ? padding + text : text + padding;
}
std::string money(double value) {
    std::ostringstream out; out.imbue(std::locale::classic());
    out << std::fixed << std::setprecision(4) << value; return out.str();
}
std::string first(const std::string& text, std::size_t count) {
    std::string out; for (const auto& character : utf8(text)) {
        if (!count--) break; out += character.second;
    } return out;
}
std::string string_value(const JsonNode& n, const std::string& key) {
    const auto* value = object_field(n, key);
    if (!value) return "";
    if (value->kind != JsonKind::String) throw ProjectError("procurement: expected string " + key);
    return value->string_value;
}
double number(const JsonNode& n, const std::string& key, double fallback) {
    const auto* value = object_field(n, key);
    if (!value || value->kind == JsonKind::Null) return fallback;
    double out;
    if (value->kind == JsonKind::Number) out = value->number_value == 0 ? fallback : value->number_value;
    else if (value->kind == JsonKind::String) {
        if (value->string_value.empty()) return fallback;
        const auto text = verification::trim(value->string_value);
        std::size_t used = 0; out = std::stod(text, &used);
        if (used != text.size()) throw ProjectError("invalid procurement number: " + key);
    } else throw ProjectError("invalid procurement number: " + key);
    if (!std::isfinite(out)) throw ProjectError("nonfinite procurement number: " + key);
    return out;
}
long long integer(const JsonNode& n, const std::string& key, long long fallback) {
    const double out = number(n, key, static_cast<double>(fallback));
    if (out < -9223372036854775808.0 || out >= 9223372036854775808.0 || std::trunc(out) != out)
        throw ProjectError("invalid procurement integer: " + key);
    return static_cast<long long>(out);
}
void code(const std::string& value) {
    if (value.size() < 2 || value[0] != 'C' || !std::all_of(value.begin()+1,value.end(),[](char c){return c>='0'&&c<='9';}))
        throw ProjectError("invalid LCSC component identifier: " + value);
}
}
ProcurementInventory procurement_inventory(const std::vector<ProjectCircuit>& sheets) {
    ProcurementInventory out; std::map<std::string,ProcurementItem> items;
    for (const auto& sheet : sheets) for (const auto* part : verification::ordered_parts(sheet.circuit)) {
        if (verification::field(*part,"BOM") == "exclude") continue;
        const auto id = verification::trim(verification::field(*part,"LCSC"));
        const auto label = sheet.circuit.name + ":" + part->ref;
        if (id.empty()) {out.missing.push_back(label + " (" + part->value + ")");continue;}
        auto [position,inserted] = items.emplace(id,ProcurementItem{id,part->value,{},{}});
        (void)inserted; auto& item = position->second; item.refs.push_back(label);
        const auto alternatives = verification::field(*part,"ALT_LCSC"); std::size_t start = 0;
        while (start <= alternatives.size()) {
            const auto end = alternatives.find(',',start);
            const auto alt = verification::trim(alternatives.substr(start,end==std::string::npos?end:end-start));
            if (!alt.empty() && std::find(item.alternatives.begin(),item.alternatives.end(),alt)==item.alternatives.end()) item.alternatives.push_back(alt);
            if (end==std::string::npos) break; start=end+1;
        }
    }
    for (auto& entry : items) out.items.push_back(std::move(entry.second)); return out;
}
std::pair<std::string,std::string> assess_procurement_stock(long long stock,long long need,long long floor) {
    if(stock<=0)return {"out","** OUT OF STOCK **"};
    if(stock<need)return {"insufficient","** INSUFFICIENT (stock "+std::to_string(stock)+" < need "+std::to_string(need)+") **"};
    if(stock<std::max(need,floor))return {"low","** LOW STOCK ("+std::to_string(stock)+" < floor "+std::to_string(floor)+") **"};
    return {"ok",""};
}
double procurement_unit_price(const std::vector<std::pair<long long,double>>& prices,long long qty) {
    if(prices.empty())return 0;
    auto sorted=prices;std::sort(sorted.begin(),sorted.end());double best=prices.front().second;
    for(const auto& [start,price]:sorted){if(!std::isfinite(price)||price<0)throw ProjectError("invalid procurement price");if(qty>=start)best=price;}
    return best;
}
ProcurementResult assess_procurement(const ProcurementInventory& inventory,const ProcurementProvider& provider,
        long long boards,long long floor,bool allow_missing) {
    if(boards<=0||floor<0)throw ProjectError("procurement requires positive board quantity and nonnegative stock floor");
    if(!provider.assembly||!provider.catalog)throw ProjectError("procurement providers are required");
    ProcurementResult out;std::ostringstream report;report.imbue(std::locale::classic());
    std::map<std::string,std::optional<ProcurementInfo>> queried;
    const auto query=[&](const std::string& id)->const std::optional<ProcurementInfo>& {
        auto found=queried.find(id);
        if(found==queried.end())found=queried.emplace(id,provider.assembly(id)).first;
        return found->second;
    };
    report<<"preflight: "<<inventory.items.size()<<" LCSC line item(s), "<<inventory.missing.size()<<" part(s) without an LCSC id, "<<boards<<" board(s)\n";
    const auto row=[](const std::string& id,const std::string& mpn,const std::string& lib,const std::string& stock,const std::string& need,const std::string& unit,const std::string& ext){return column(id,12)+" "+column(mpn,24)+" "+column(lib,9)+" "+column(stock,9,true)+" "+column(need,5,true)+" "+column(unit,8,true)+" "+column(ext,8,true)+"  ";};
    if(!inventory.items.empty()){const auto header=row("LCSC","MPN","lib","stock","need","unit $","ext $")+"refs";report<<header<<'\n'<<std::string(header.size(),'-')<<'\n';}
    auto items=inventory.items;std::stable_sort(items.begin(),items.end(),[](const auto&a,const auto&b){return a.lcsc<b.lcsc;});
    for(const auto& item:items){
        if(item.refs.size()>static_cast<unsigned long long>(std::numeric_limits<long long>::max()/boards))throw ProjectError("procurement quantity overflow");
        const auto need=static_cast<long long>(item.refs.size())*boards;const auto info=query(item.lcsc);
        if(!info){const auto where=provider.catalog(item.lcsc)?"LCSC catalog only (not JLC assembly)":"NOT FOUND anywhere";report<<row(item.lcsc,item.value,"?","-",std::to_string(need),"-","-")<<where<<'\n';out.failures.push_back(item.lcsc+" ("+item.value+"): "+where);continue;}
        const auto unit=procurement_unit_price(info->prices,std::max(need,info->min_qty)),extended=unit*need;
        out.cost+=extended;if(!std::isfinite(out.cost))throw ProjectError("procurement cost overflow");
        if(info->library=="Extended")++out.extended_reels;
        const auto [status,flag]=assess_procurement_stock(info->stock,need,floor);std::string flags=flag.empty()?"":"  "+flag;
        if(status!="ok"){
            std::optional<std::pair<std::string,ProcurementInfo>> chosen;
            for(const auto& alt:item.alternatives){const auto candidate=query(alt);if(candidate&&assess_procurement_stock(candidate->stock,need,floor).first=="ok"){chosen={{alt,*candidate}};break;}}
            if(chosen){flags+="  -> 2nd source "+chosen->first+" OK (stock "+std::to_string(chosen->second.stock)+")";out.warnings.push_back(item.lcsc+" ("+info->mpn+"): "+status+" but covered by alternate "+chosen->first+" (stock "+std::to_string(chosen->second.stock)+")");}
            else if(status=="out"||status=="insufficient")out.failures.push_back(item.lcsc+" ("+info->mpn+"): "+(status=="out"?"OUT":"INSUFFICIENT")+(item.alternatives.empty()?"":"; no alternate clears it (tried "+verification::join(item.alternatives,",")+")"));
            else out.warnings.push_back(item.lcsc+" ("+info->mpn+"): LOW STOCK "+std::to_string(info->stock)+" < floor "+std::to_string(floor)+(item.alternatives.empty()?"; no ALT_LCSC second source committed":"; no healthier alternate"));
        }
        report<<row(item.lcsc,first(info->mpn,24),info->library,std::to_string(info->stock),std::to_string(need),money(unit),money(extended))<<verification::join(item.refs,",")<<flags<<'\n';
    }
    report<<"\nTOTAL parts cost: $"<<money(out.cost)<<" for "<<boards<<" board(s); Extended reels: "<<out.extended_reels<<" (+ JLC feeder fee each)\n";
    if(!inventory.missing.empty()){report<<"MISSING LCSC id ("<<inventory.missing.size()<<"):\n";for(const auto& text:inventory.missing)report<<"  "<<text<<'\n';}
    if(!out.warnings.empty()){report<<"PROCUREMENT WARNINGS ("<<out.warnings.size()<<" — not fatal, review before a build):\n";for(const auto& text:out.warnings)report<<"  "<<text<<'\n';}
    if(!out.failures.empty()){report<<"PREFLIGHT: FAIL ("<<out.failures.size()<<" availability problem(s))\n";for(const auto& text:out.failures)report<<"  "<<text<<'\n';}
    else if(!inventory.missing.empty()&&!allow_missing)report<<"PREFLIGHT: FAIL (parts without LCSC ids cannot be ordered; rerun with --allow-missing to tolerate)\n";
    else {out.ok=true;report<<"PREFLIGHT: PASS\n";}
    out.report=report.str();return out;
}
std::optional<ProcurementInfo> procurement_jlc_response(const JsonNode& raw,const std::string& id) {
    const auto* data=object_field(raw,"data");const auto* page=data?object_field(*data,"componentPageInfo"):nullptr;const auto* list=page?object_field(*page,"list"):nullptr;
    if(raw.kind!=JsonKind::Object||!data||data->kind!=JsonKind::Object||!page||page->kind!=JsonKind::Object)
        throw ProjectError("malformed or unsuccessful JLC response");
    if(!list||list->kind==JsonKind::Null)return std::nullopt;
    if(list->kind!=JsonKind::Array)throw ProjectError("malformed JLC component list");
    for(const auto& item:list->array_value)if(string_value(item,"componentCode")==id){
        ProcurementInfo out;out.mpn=string_value(item,"componentModelEn");out.brand=string_value(item,"componentBrandEn");out.package=string_value(item,"componentSpecificationEn");out.stock=integer(item,"stockCount",0);out.min_qty=integer(item,"minPurchaseNum",1);out.library=string_value(item,"componentLibraryType")=="base"?"Basic":"Extended";
        const auto* prices=object_field(item,"componentPrices");if(prices&&prices->kind!=JsonKind::Null){if(prices->kind!=JsonKind::Array)throw ProjectError("malformed JLC prices");for(const auto& p:prices->array_value)out.prices.emplace_back(integer(p,"startNumber",1),number(p,"productPrice",0));}
        return out;
    }
    return std::nullopt;
}
bool procurement_lcsc_response(const JsonNode& raw) {
    const auto* status=object_field(raw,"code"),*result=object_field(raw,"result");
    if(raw.kind!=JsonKind::Object||!status||status->kind!=JsonKind::Number)
        throw ProjectError("malformed LCSC response");
    return status&&status->kind==JsonKind::Number&&status->number_value==200&&result&&
        result->kind!=JsonKind::Null&&!(result->kind==JsonKind::Bool&&!result->bool_value)&&
        !(result->kind==JsonKind::Object&&result->object_value.empty())&&!(result->kind==JsonKind::Array&&result->array_value.empty())&&
        !(result->kind==JsonKind::String&&result->string_value.empty())&&!(result->kind==JsonKind::Number&&result->number_value==0);
}
ProcurementProvider live_procurement_provider(int timeout,const std::string& executable) {
    if(timeout<=0||timeout>300)throw ProjectError("procurement timeout must be between 1 and 300 seconds");
    const auto request=[=](const std::string& url,const std::optional<std::string>& body){
        std::vector<std::string> args{executable,"--fail","--silent","--show-error","--location","--proto","=https","--proto-redir","=https","--max-time",std::to_string(timeout),"--user-agent","Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"};
        if(body)args.insert(args.end(),{"--header","Content-Type: application/json","--header","Origin: https://jlcpcb.com","--header","Referer: https://jlcpcb.com/parts","--data-binary",*body});
        args.insert(args.end(),{"--url",url});const auto response=run_process(args,std::chrono::seconds(timeout+2));
        if(response.exit_code!=0)throw ProjectError("procurement service unavailable: "+response.stderr_text);
        return parse_json_text(response.stdout_text,"procurement HTTPS response");
    };
    return {[=](const std::string& id){code(id);return procurement_jlc_response(request("https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList","{\"keyword\":\""+id+"\",\"currentPage\":1,\"pageSize\":5}"),id);},
        [=](const std::string& id){code(id);return procurement_lcsc_response(request("https://wmsc.lcsc.com/ftps/wm/product/detail?productCode="+id,std::nullopt));}};
}
}
