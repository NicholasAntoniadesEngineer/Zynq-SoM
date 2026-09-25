#include "schgen/selftest_full.hpp"

namespace schgen {
namespace {
CircuitSheetIr fixture_design_rules() {
    CircuitSheetIr c;
    c.schema="schgen.circuit/1";c.name="selftest_dr";c.title="selftest design-rule fixture";
    c.parts={{"U1","CP2102N-A02-GQFN24R:CP2102N-A02-GQFN24R","CP2102N","CP2102N-A02-GQFN24R:CP2102N-A02-GQFN24R",{{"LCSC","C969151"}},{{"RI/CLK",{"1"}},{"GND",{"2","25"}},{"D+",{"3"}},{"D-",{"4"}},{"VIO",{"5"}},{"VDD",{"6"}},{"VREGIN",{"7"}},{"VBUS",{"8"}},{"RSTb",{"9"}},{"NC",{"10","16"}},{"GPIO.3/WAKEUP",{"11"}},{"GPIO.2/RS485",{"12"}},{"GPIO.1/RXT",{"13"}},{"GPIO.0/TXT",{"14"}},{"SUSPENDb",{"15"}},{"SUSPEND",{"17"}},{"CTS",{"18"}},{"RTS",{"19"}},{"RXD",{"20"}},{"TXD",{"21"}},{"DSR",{"22"}},{"DTR",{"23"}},{"DCD",{"24"}}},{"1","10","11","12","13","14","15","16","17","18","19","2","20","21","22","23","24","25","3","4","5","6","7","8","9"}},{"C1","Device:C","100n","Capacitor_SMD:C_0603_1608Metric",{},{},{}},{"C2","Device:C","100n","Capacitor_SMD:C_0603_1608Metric",{},{},{}},{"C3","Device:C","100n","Capacitor_SMD:C_0603_1608Metric",{},{},{}},{"R1","Device:R","4k7","Resistor_SMD:R_0603_1608Metric",{},{},{}},{"C4","Device:C","100n","Capacitor_SMD:C_0603_1608Metric",{},{},{}},{"R2","Device:R","10k","Resistor_SMD:R_0603_1608Metric",{},{},{}}};
    c.nets={{"+3V3","power",{{"U1","5"},{"U1","7"},{"C1","1"},{"C2","1"},{"R1","1"},{"R2","1"}}},{"+VDD_CORE","power",{{"U1","6"},{"C3","1"}}},{"GND","ground",{{"U1","2"},{"U1","25"},{"C1","2"},{"C2","2"},{"C3","2"},{"C4","2"}}},{"SC_I2C_SCL","port",{{"U1","20"},{"R1","2"}}},{"SYS_RST_N","signal",{{"U1","9"},{"C4","1"},{"R2","2"}}}};
    {CircuitPortIr p;p.net="SC_I2C_SCL";p.kind="i2c";
    p.role="scl";p.has_role=true;
    c.port_types.push_back(p);}
    return c;
}
CircuitSheetIr fixture_ep() {
    CircuitSheetIr c;
    c.schema="schgen.circuit/1";c.name="selftest_ep";c.title="selftest exposed-pad fixture";
    c.parts={{"U1","TLV75725PDYDR:TLV75725PDYDR","TLV75725PDYDR","TLV75725PDYDR:TLV75725PDYDR",{{"LCSC","C35209004"}},{{"IN",{"1"}},{"GND",{"2"}},{"EN",{"3"}},{"NC",{"4"}},{"OUT",{"5"}},{"EP",{"6"}}},{"1","2","3","4","5","6"}}};
    c.nets={{"+3V3","power",{{"U1","1"},{"U1","3"}}},{"+2V5","power",{{"U1","5"}}},{"GND","ground",{{"U1","2"},{"U1","6"}}}};
    c.nc={{"U1","4"}};
    return c;
}
CircuitSheetIr fixture_buck() {
    CircuitSheetIr c;
    c.schema="schgen.circuit/1";c.name="selftest_buck";c.title="selftest power/thermal/spice fixture";
    c.parts={{"U1","Regulator_Switching:TPS54302","TPS54302DDCR","Package_TO_SOT_SMD:SOT-23-6",{},{},{}},{"L1","Device:L","2.2uH","",{},{},{}},{"R1","Device:R","45k3","Resistor_SMD:R_0603_1608Metric",{},{},{}},{"R2","Device:R","10k","Resistor_SMD:R_0603_1608Metric",{},{},{}}};
    c.nets={{"+VIN","power",{{"U1","3"}}},{"SW","signal",{{"U1","2"},{"L1","1"}}},{"+3V3","power",{{"L1","2"},{"R1","1"}}},{"GND","ground",{{"U1","1"},{"R2","2"}}},{"+5V_EN","power",{{"U1","5"}}},{"FB","signal",{{"U1","4"},{"R1","2"},{"R2","1"}}}};
    c.loads.push_back({"+3V3",0.5,"selftest declared load"});
    return c;
}
CircuitSheetIr fixture_testpoints() {
    CircuitSheetIr c;
    c.schema="schgen.circuit/1";c.name="selftest_tp";c.title="selftest test-point fixture";
    c.parts={{"R1","Device:R","10k","Resistor_SMD:R_0603_1608Metric",{},{},{}},{"TP1","Connector:TestPoint","+3V3","TestPoint:TestPoint_Pad_D1.5mm",{{"BOM","exclude"}},{},{}},{"TP2","Connector:TestPoint","GND","TestPoint:TestPoint_Pad_D1.5mm",{{"BOM","exclude"}},{},{}}};
    c.nets={{"+3V3","power",{{"R1","1"},{"TP1","1"}}},{"GND","ground",{{"R1","2"},{"TP2","1"}}}};
    return c;
}
CircuitSheetIr fixture_mounting_hole() {
    CircuitSheetIr c;
    c.schema="schgen.circuit/1";c.name="selftest_mh";c.title="selftest mounting-hole fixture";
    c.parts={{"R1","Device:R","10k","Resistor_SMD:R_0603_1608Metric",{},{},{}}};
    c.nets={{"CHASSIS_GND","ground",{{"R1","1"}}},{"+3V3","power",{{"R1","2"}}}};
    return c;
}
CircuitSheetIr fixture_board_0() {
    CircuitSheetIr c;
    c.schema="schgen.circuit/1";c.name="selftest_brd_a";c.title="selftest board fixture A";
    c.parts={{"R1","Device:R","10k","Resistor_SMD:R_0603_1608Metric",{},{},{}}};
    c.nets={{"+3V3","power",{{"R1","1"}}},{"SELFTEST_LINK","port",{{"R1","2"}}}};
    return c;
}
CircuitSheetIr fixture_board_1() {
    CircuitSheetIr c;
    c.schema="schgen.circuit/1";c.name="selftest_brd_b";c.title="selftest board fixture B";
    c.parts={{"R2","Device:R","10k","Resistor_SMD:R_0603_1608Metric",{},{},{}}};
    c.nets={{"SELFTEST_LINK","port",{{"R2","1"}}},{"GND","ground",{{"R2","2"}}}};
    return c;
}
} // namespace

SelftestModelFixtures selftest_model_fixtures(PcbCheckFootprintPtr footprint) {
    if(!footprint)throw std::invalid_argument("selftest requires the real resistor footprint");
    SelftestModelFixtures f;
    f.design_rules=fixture_design_rules();f.ep=fixture_ep();f.buck=fixture_buck();
    f.testpoints=fixture_testpoints();f.mounting_hole=fixture_mounting_hole();
    f.rail_cap=selftest_rail_decoupling_fixture();f.esd_clamp=selftest_esd_clamp_fixture();
    f.board={fixture_board_0(),fixture_board_1()};
    f.cap_voltage.schema="schgen.circuit/1";f.cap_voltage.name="selftest_capv";f.cap_voltage.title="selftest cap-voltage fixture";
    f.cap_voltage.parts={{"C1","Device:C","10u","Capacitor_SMD:C_0805_2012Metric",{{"LCSC","C15850"}},{},{}}};
    f.cap_voltage.nets={{"HDMI_RX_5V","power",{{"C1","1"}}},{"GND","ground",{{"C1","2"}}}};
    f.symbol_law.schema="schgen.circuit/1";f.symbol_law.name="selftest_symlaw";f.symbol_law.title="selftest symbol-law fixture";
    f.symbol_law.parts={{"R1","Device:R","10k","Resistor_SMD:R_0603_1608Metric",{},{},{}}};
    f.symbol_law.nets={{"+3V3","power",{{"R1","1"}}},{"GND","ground",{{"R1","2"}}}};
    auto& m=f.ratsnest;m.board_w=60;m.board_h=40;m.origin_x=25;m.origin_y=25;
    m.net_numbers={{"",0},{"A_SIG",1},{"B_SIG",2},{"GND",3}};
    auto inst=[&](std::string ref,std::string sheet,double x,double y,std::string net) {
        PcbCheckInstance p;p.ref=ref;p.sheet=sheet;p.value="10k";p.footprint="Resistor_SMD:R_0603_1608Metric";
        p.x=25+x;p.y=25+y;p.mod=footprint;p.pad_nets={{"1",{1,net}},{"2",{2,"GND"}}};m.insts.push_back(p);
    };
    inst("R1","subsys_a",8,8,"A_SIG");inst("R2","subsys_a",12,8,"A_SIG");
    inst("R3","subsys_a",10,12,"A_SIG");inst("R7","subsys_a",8,12,"A_SIG");
    inst("R4","subsys_b",48,8,"A_SIG");inst("R5","subsys_b",52,8,"B_SIG");inst("R6","subsys_b",50,12,"B_SIG");
    return f;
}
CircuitSheetIr selftest_rc_fixture() {
    CircuitSheetIr c;c.schema="schgen.circuit/1";c.name="m1_rc";c.title="M1 RC divider (engine-placed smoke test)";
    c.parts={{"R1","Device:R","10k","Resistor_SMD:R_0603_1608Metric",{},{},{}},
        {"R2","Device:R","10k","Resistor_SMD:R_0603_1608Metric",{},{},{}},
        {"C1","Device:C","100n","Capacitor_SMD:C_0603_1608Metric",{},{},{}}};
    c.nets={{"+3V3","power",{{"R1","1"}}},{"MID","port",{{"R1","2"},{"R2","1"},{"C1","1"}}},{"GND","ground",{{"R2","2"},{"C1","2"}}}};
    CircuitPortIr p;p.net="MID";p.kind="single";p.has_expect=true;
    p.expect="schgen smoke sheet — divider mid-point has no board consumer by design";c.port_types.push_back(p);
    return c;
}
} // namespace schgen
