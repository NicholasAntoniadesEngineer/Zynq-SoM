#include "floorplan_internal.hpp"

#include <algorithm>

namespace schgen {
using namespace floorplan_detail;
namespace {
bool has_value(const CircuitSheetIr& c,const std::string& prefix) {
    return std::any_of(c.parts.begin(),c.parts.end(),[&](const auto& p){return starts(p.value,prefix);});
}
std::string first_value(const CircuitSheetIr& c,const std::vector<std::string>& prefixes,const std::string& fallback={}) {
    for (const auto& p:c.parts) for (const auto& prefix:prefixes) if (starts(p.value,prefix)) return p.value;
    return fallback;
}
int pairs(const CircuitSheetIr& c,const std::string& kind) {
    int n=0; for (const auto& p:c.port_types) if (p.kind==kind) ++n; return n/2;
}
}  // namespace

std::vector<FloorplanNote> build_floorplan_notes(const FloorplanPlan& plan,const FloorplanInput& input) {
    std::map<std::string,const CircuitSheetIr*> sheets;
    for (const auto& c:input.sheets) sheets[c.name]=&c;
    std::vector<const FloorplanBlock*> ordered;
    for (const auto& b:plan.edge_blocks) ordered.push_back(&b);
    const std::map<std::string,int> edge_order{{"N",0},{"W",1},{"E",2},{"S",3}};
    std::stable_sort(ordered.begin(),ordered.end(),[&](const auto* a,const auto* b){
        return std::make_tuple(edge_order.at(a->edge),a->x,a->y)<std::make_tuple(edge_order.at(b->edge),b->x,b->y);
    });
    std::vector<const FloorplanBlock*> interior;
    for (const auto& b:plan.interior_blocks) interior.push_back(&b);
    std::sort(interior.begin(),interior.end(),[](const auto* a,const auto* b){return a->name<b->name;});
    ordered.insert(ordered.end(),interior.begin(),interior.end());
    std::vector<FloorplanNote> notes;
    auto add=[&](const std::string& block,const std::string& short_text,const std::string& long_text) {
        notes.push_back({static_cast<int>(notes.size()+1),block,short_text,long_text.empty() ? short_text:long_text});
    };
    for (const auto* bp:ordered) {
        const auto& b=*bp;
        if (!sheets.count(b.name)) throw FloorplanError("floorplan notes: unknown subsystem "+repr(b.name));
        const auto& c=*sheets.at(b.name);
        std::set<std::string> nets,values;
        for (const auto& n:c.nets) nets.insert(n.name);
        for (const auto& conn:b.conns) values.insert(conn.value);
        if (values.count("TYPE-C-31-M-12") && nets.count("+VIN")) {
            const bool efuse=has_value(c,"TPS2594");
            add(b.name,"power inlet: VBUS->TVS->bulk->+VIN; CC pair to FUSB302",
                std::string("PD power inlet: keep the VBUS path (receptacle -> ")+(efuse ? "eFuse soft-start -> ":"")+
                "TVS -> bulk -> +VIN) in one corner so the +VIN plane spreads from a single point; CC1/CC2 route to the FUSB302 (usb_pd block, anchored next to this inlet)."+
                (efuse ? "":" PLAN.md round 5: a TPS25940-class eFuse lands between receptacle and bulk — reserve space for it here."));
        } else if (values.count("TYPE-C-31-M-12")) {
            const auto esd=first_value(c,{"USBLC","TPD"});
            add(b.name,"USB-C OTG: 90R HS pair short + matched; ESD at conn",
                "USB-C OTG: the 90R D+/D- pair wants the shortest matched run to its SoM pins; "+
                (esd.empty() ? "":esd+" ESD array within ~10 mm of the receptacle; ")+"VBUS source switch beside the connector.");
        }
        if (values.count("HDMI-019S")) {
            const auto n=std::to_string(pairs(c,"tmds_pair"));
            add(b.name,n+" TMDS pairs 100R; companion IC at connector",
                n+" TMDS pairs at 100R differential, intra-pair skew <= 0.15 mm (constraints.py); place "+
                first_value(c,{"TPD12S","M24C"},"the companion IC")+" directly behind the receptacle so all pairs pass straight through.");
        }
        if (b.name=="ethernet" || has_value(c,"HX5008"))
            add(b.name,"magnetics keep-out: no planes line-side; 100R MDI",
                "Magnetics isolation: void ALL planes under the HX5008 line side + Bob-Smith network (CHASSIS_GND moat to the RJ45); MDI pairs are 100R differential. RJ45 itself is an author-declared deferral (expect rj45_connector) — the dashed reservation is its landing zone.");
        if (values.count("TF-01A"))
            add(b.name,"SDIO 1.8V island: TXS02612 splits 1.8V / 3.3V sides",
                "microSD: SDIO runs at 1.8 V on the SoM side (typed sd_bus level in the netlist) — keep the TXS02612 translator mid-block: 1.8V side faces the SoM, 3.3V card side faces the slot; bus length match <= 2.5 mm to CLK.");
        if (values.count("AFC07-S40FCA-00")) {
            const auto boost=first_value(c,{"SY7201"});
            add(b.name,"LCD FFC exit; backlight boost loop tight",
                std::string("40-pin LCD FFC: cable exits over the board edge; ")+
                (boost.empty() ? "":"keep the "+boost+" backlight boost loop (L/D/C) tight and away from the FFC signal rows; ")+
                "RGB888 bus is single-ended bank-34 3V3 — bus-route together.");
        }
        if (values.count("SFW15R-1STE1LF")) {
            const auto n=std::to_string(pairs(c,"diff_pair"));
            add(b.name,"camera FFC: "+n+" CSI-2 pairs 100R to J3 side",
                "RPi camera FFC: "+n+" MIPI CSI-2 pairs at 100R differential to the J3 side of the SoM (bank 35, 2.5 V VCCO per the expect= notes) — keep the run to the J3 strip short.");
        }
        if (values.count("DS1024-2x6R2"))
            add(b.name,"PMOD pair on gated +3V3_PMOD rail",
                "Two PMOD sockets side by side; both fed from the gated +3V3_PMOD rail (SY6280 cell in bringup_modules) — route the gated rail once, star at the sockets.");
        bool vadj=values.count("TLV75725PDYDR")!=0;
        const FloorplanRegulator* ldo=nullptr;
        for (const auto& r:input.regulators) if (r.sheet==b.name) { if (!ldo) ldo=&r; vadj |= r.value.find("TLV75725")!=std::string::npos; }
        if (vadj && ldo) {
            const double vi=rail_volts(ldo->vin).value_or(0),vo=rail_volts(ldo->vout).value_or(0);
            add(b.name,"bank-35 IO header: VADJ LDO copper",ldo->value+" VADJ LDO dissipates ~"+
                number((vi-vo)*ldo->i_out,2)+" W at the declared "+number(ldo->i_out)+" A — give its EP pad a ground pour.");
        }
        if (std::find(b.reserved.begin(),b.reserved.end(),"usb_uart_connector")!=b.reserved.end())
            add(b.name,"USB-UART conn deferred; TPs on TX/RX",
                "CP2102N UART bridge: its USB connector is an author-declared deferral (expect usb_uart_connector) — the block reserves edge space for it; TX/RX test points stay probe-able.");
        if (b.name=="power") {
            std::string diss;
            for (const auto& r:input.regulators) if (r.sheet==b.name && r.kind=="buck") {
                if (r.eff==0) throw FloorplanError("floorplan notes: zero regulator efficiency for "+r.ref);
                if (!diss.empty()) diss+="; ";
                diss+=r.value+" "+r.vout+" ~"+number((1/r.eff-1)*rail_volts(r.vout).value_or(0)*r.i_out,2)+" W";
            }
            add(b.name,"2 bucks: thermal copper + vias; keep SW loops tight",
                "Buck thermal (worst-case declared draws): "+diss+". Pour copper on the SW/PGND side, stitch vias under the packages, keep each SW node loop minimal.");
        }
        if (b.name=="bringup_modules") {
            std::vector<std::string> gated;
            for (const auto& r:input.regulators) if (r.sheet==b.name) gated.push_back(r.vout);
            std::sort(gated.begin(),gated.end()); std::string rails;
            for (const auto& r:gated) { if (!rails.empty()) rails+=", "; rails+=r; }
            const auto n=std::to_string(gated.size());
            add(b.name,n+" load switches: gated-rail star points",n+" SY6280 load-switch cells; each gated rail ("+rails+") stars from its switch — place this block centrally so every gated rail leaves toward its module without crossing the others.");
        }
        if (b.name=="bringup_rails") add(b.name,"rail-EN DIPs + PG LEDs: human access",
            "Rail-enable DIP switches + power-good LEDs: face them where fingers and eyes reach them with the mezzanine mounted — keep clear of the SoM shadow.");
        if (b.name=="power_mon") add(b.name,"INA3221 shunts sit IN the rail path",
            "Power monitor: the shunt resistors are in series with the rails — the rails must physically route through this block; place it between the regulators and the loads, Kelvin-connect the sense pairs.");
        if (b.name=="debug_boot") add(b.name,"JTAG/SWD headers vertical: probe clearance",
            "JTAG (2x7 2 mm) + SWD (2x5 1.27 mm) headers mate vertically — any top-side spot works; keep cable/probe clearance and the boot DIP reachable.");
        if (b.name=="usb_pd") add(b.name,"FUSB302 beside inlet: short CC stubs",
            "FUSB302 PD controller: anchored beside the pd_input receptacle so CC1/CC2 stay short stubs; I2C runs to the SoM J1 side.");
        if (b.name=="user_io") add(b.name,"LEDs + buttons human-facing",
            "User LEDs + buttons: human-facing — keep at the accessible S side, clear of the PMOD cable shadow.");
    }
    int ntp=0;
    for (const auto& sc:input.sheets) for (const auto& p:sc.parts) if (starts(p.ref,"TP")) ++ntp;
    notes.push_back({0,"",std::to_string(ntp)+" test points board-wide",std::to_string(ntp)+
        " test points board-wide (test-point gate): spread them with probe clearance as the blocks settle; none may end up under the SoM."});
    return notes;
}
}  // namespace schgen
