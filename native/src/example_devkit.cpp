#include "schgen/example_devkit.hpp"
#include "schgen/project_outputs.hpp"
#include "schgen/native_render.hpp"
#include <algorithm>

namespace schgen {
namespace {
JsonNode strings(std::initializer_list<std::pair<std::string,std::string>> fields) {
    JsonNode out;out.kind=JsonKind::Object;
    for(const auto& [key,value]:fields){JsonNode s;s.kind=JsonKind::String;s.string_value=value;out.object_value.emplace_back(key,std::move(s));}
    return out;
}
JsonNode metadata(std::initializer_list<std::pair<std::string,JsonNode>> fields) {
    JsonNode out;out.kind=JsonKind::Object;out.object_value=fields;return out;
}
constexpr const char* connector="devkit_conn (mini header J5 GPIO map)";
constexpr const char* uart="devkit_uart_header (FPGA UART0 pin map)";
constexpr const char* usb="devkit_usb_receptacles (USB2 connector sheet)";
}

const std::vector<ExampleDevkitDefinition>& example_devkit_definitions() {
    static const std::vector<ExampleDevkitDefinition> definitions{
        {"usb_pd",metadata({
            {"bind",strings({{"+VDD_LOGIC","+3V3_MINI"},{"+VBUS_SENSE","+VBUS_RAW"},{"GND","GND"},
                {"CC1","PD_CC1"},{"CC2","PD_CC2"},{"I2C_SDA","MINI_I2C0_SDA"},{"I2C_SCL","MINI_I2C0_SCL"},{"INT_N","MINI_PD_INT_N"}})},
            {"expects",strings({{"I2C_SDA",connector},{"I2C_SCL",connector},{"INT_N",connector}})},
            {"buses",strings({{"i2c","MINI_I2C0"}})},
            {"notes",strings({{"draws","FUSB302B VDD (<1 mA) on the shared +3V3_MINI logic rail; MINI_I2C0 + INT pull-ups are board-shared, off-subsystem"}})}
        })},
        {"usbc_otg",metadata({
            {"bind",strings({{"+VBUS_SUPPLY","+5V_DEV"},{"+VDD_LOGIC","+3V3_MINI"},{"GND","GND"},{"CHASSIS_GND","CHASSIS_GND"},
                {"USB_DP","USB2_HOST_DP"},{"USB_DM","USB2_HOST_DM"},{"VBUS","USB2_HOST_VBUS"},
                {"VBUS_EN","USB2_HOST_EN"},{"FLT_N","USB2_HOST_FLT_N"},{"USB_ID","USB2_HOST_ID"}})},
            {"expects",strings({{"VBUS_EN",connector},{"USB_ID",connector},{"FLT_N",connector}})},
            {"notes",strings({{"draws_vbus","downstream USB device budget (TPS2051C limited) from +5V_DEV"},
                {"draws_flt","USB2_HOST_FLT# 100k pull-up on the shared +3V3_MINI logic rail"}})}
        })},
        {"microsd",metadata({
            {"bind",strings({{"+VDD_HOST","+1V8_FPGA"},{"+VDD_CARD","+3V3_MINI"},{"GND","GND"},{"SD_CLK","SD0_CLK"},
                {"SD_CMD","SD0_CMD"},{"SD_D0","SD0_DAT0"},{"SD_D1","SD0_DAT1"},{"SD_D2","SD0_DAT2"},{"SD_D3","SD0_DAT3"},{"CD_N","SD0_DETECT_N"}})},
            {"expects",strings({{"CD_N",connector}})},
            {"notes",strings({{"draws_card","SD card write burst ~200 mA + pulls + TXS02612 VCCB on +3V3_MINI"},
                {"draws_host","TXS02612 VCCA (FPGA 1.8 V SDIO level)"}})}
        })},
        {"uart_bridge",metadata({
            {"bind",strings({{"+VDD_IO","+3V3_MINI"},{"GND","GND"},{"USB_VBUS","USB2_UART_VBUS"},{"USB_DP","USB2_UART_DP"},{"USB_DM","USB2_UART_DM"},
                {"UART_TXD","FPGA_UART0_RXD"},{"UART_RXD","FPGA_UART0_TXD"},{"UART_RTS_N","FPGA_UART0_CTS_N"},{"UART_CTS_N","FPGA_UART0_RTS_N"}})},
            {"expects",strings({{"USB_VBUS",usb},{"USB_DP",usb},{"UART_TXD",uart},{"UART_RXD",uart},{"UART_RTS_N",uart},{"UART_CTS_N",uart}})},
            {"notes",strings({{"draws","CP2102N active ~14 mA typ + RST 1k pull-up on +3V3_MINI"}})}
        })}
    };
    return definitions;
}

const std::vector<std::string>& example_devkit_shared_rails() {
    static const std::vector<std::string> rails{"+3V3_MINI","GND"};return rails;
}

CircuitSheetIr author_example_devkit_subsystem(const std::string& name,const AuthoringContext& context,
                                               const std::optional<JsonNode>& override) {
    const auto& defs=example_devkit_definitions();
    const auto at=std::find_if(defs.begin(),defs.end(),[&](const auto& d){return d.name==name;});
    if(at==defs.end())throw CircuitAuthoringError("unknown four-sheet example subsystem: "+name);
    return author_subsystem(name,SubsystemMeta(override?*override:at->metadata),context);
}

std::vector<CircuitSheetIr> author_example_devkit(const AuthoringContext& context,const std::map<std::string,JsonNode>& overrides) {
    const auto& defs=example_devkit_definitions();
    for(const auto& entry:overrides) {
        const auto& name=entry.first;
        if(std::none_of(defs.begin(),defs.end(),[&](const auto& d){return d.name==name;}))
            throw CircuitAuthoringError("unknown four-sheet example override: "+name);
    }
    std::vector<CircuitSheetIr> out;
    for(const auto& d:defs){const auto it=overrides.find(d.name);
        out.push_back(author_example_devkit_subsystem(d.name,context,it==overrides.end()?std::nullopt:std::optional<JsonNode>{it->second}));}
    return out;
}

bool ExampleDevkitResult::ok() const {
    return standalone.size()==4 && hierarchy.per_sheet.size()==4 && !hierarchy.root_path.empty() &&
        std::all_of(standalone.begin(),standalone.end(),[](const auto& sheet){return sheet.ok();}) && hierarchy.ok();
}

ExampleDevkitResult build_example_devkit(const std::vector<CircuitSheetIr>& sheets,SymbolLibrary& library,
                                        const std::filesystem::path& output,const ExampleDevkitOptions& options) {
    if(output.empty())throw ProjectError("example devkit output directory must be explicit");
    const auto& defs=example_devkit_definitions();
    if(sheets.size()!=defs.size())throw ProjectError("example devkit requires exactly four sheets (not the twelve-sheet project)");
    for(std::size_t i=0;i<defs.size();++i)if(sheets[i].name!=defs[i].name)
        throw ProjectError("example devkit sheet order must be usb_pd, usbc_otg, microsd, uart_bridge");
    ExampleDevkitResult result;
    const auto schematic=output/"schematic",reports=output/"reports";
    // Match the legacy example: render the final uniquified hierarchy children,
    // not the temporary standalone sheets that the hierarchy is about to replace.
    SubsystemBuildOptions standalone;standalone.extraction=options.extraction;standalone.no_render=true;
    std::vector<BoardSheetInput> board;
    std::string cc_report="Four-sheet example connectivity checks\n";
    for(std::size_t i=0;i<sheets.size();++i) {
        auto checked=build_subsystem_sheet(sheets[i],library,schematic,standalone);
        result.report+=checked.report;
        cc_report+=sheets[i].name+": "+(checked.cc_ok?"PASS":"FAIL")+"\n";
        result.standalone.push_back(std::move(checked));
        board.push_back({sheets[i],static_cast<std::int64_t>(i+1),std::nullopt});
    }
    BoardSchematicOptions hierarchy;hierarchy.root_name="devkit_mini";hierarchy.sheet_subdir="schematic";
    hierarchy.reports_dir=reports;hierarchy.extraction=options.extraction;hierarchy.netlist_workers=options.netlist_workers;
    result.hierarchy=build_board_schematic(board,library,output,hierarchy);
    result.report+=result.hierarchy.report+"\n";
    if(!options.no_render) {
        const auto renders=output/"renders";std::filesystem::create_directories(renders);
        NativeRenderOptions render;render.kicad_cli=options.extraction.kicad_cli;
        for(std::size_t i=0;i<sheets.size();++i)try {
            render_sheet_to_png(schematic/(sheets[i].name+".kicad_sch"),renders/(sheets[i].name+".png"),300,render);
            result.standalone[i].rendered=true;
        }catch(const std::bad_alloc&){throw;}catch(const std::exception& error){
            result.report+="render "+sheets[i].name+" FAILED (advisory): "+error.what()+"\n";
        }
    }
    result.report+="DEVKIT: "+std::string(result.ok()?"PASS":"FAIL")+" (4 library sheets)\n";
    std::filesystem::create_directories(reports);
    publish_text(reports/"cc_gate.txt",cc_report);
    publish_text(reports/"example_devkit.txt",result.report);
    return result;
}
} // namespace schgen
