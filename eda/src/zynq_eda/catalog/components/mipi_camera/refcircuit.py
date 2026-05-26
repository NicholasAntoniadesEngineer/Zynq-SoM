"""Generic 15-pin 1.0 mm pitch FPC connector for MIPI CSI-2 cameras.

Datasheet: BOOMELE 1.0-15P mechanical drawing (compatible with the
Raspberry Pi-camera FFC pitch), distributed locally as
``components/mipi_camera/datasheet.pdf``. URL:
https://datasheet.lcsc.com/lcsc/BOOMELE-1-0-15P_C66660.pdf

Right-angle SMT FPC receptacle with 15 contacts on a 1.0 mm pitch -
mechanically compatible with the Raspberry Pi camera (V1/V2/V3) and HQ
camera FFC. The carrier exposes a 2-lane CSI-2 receive interface
matching Pi-camera pin order.

Mechanical highlights (catalog page 1):
    - Voltage rating: 50 V AC(rms)/DC
    - Current rating: 0.5 A AC(rms)/DC per contact
    - Contact resistance: 40 mOhm max
    - Operating temperature: -25 to +85 deg C

Pin map (Raspberry Pi camera-compatible):
    1   GND
    2   CSI_D0-
    3   CSI_D0+
    4   GND
    5   CSI_D1-
    6   CSI_D1+
    7   GND
    8   CSI_CLK-
    9   CSI_CLK+
    10  GND
    11  CAM_GPIO0   (camera shutter / reset)
    12  CAM_GPIO1   (LED enable / strobe)
    13  CAM_SCL
    14  CAM_SDA
    15  +3V3        (camera VANA + VDIG supply)

MIPI D-PHY termination (100 ohm differential, 50 ohm common-mode) is
*internal* to the receiving SerDes / FPGA (or in the case of slow CSI-2,
to the Zynq PL bank programmed in LVDS_25 mode with internal DCI 100 ohm
termination enabled). The carrier therefore does NOT add external
termination resistors.
"""

from __future__ import annotations

from zynq_eda.core.model.refcircuit import ExternalPart, LayoutNote, ReferenceCircuit


MIPI_CAMERA_REFCIRCUIT = ReferenceCircuit(
    part_mpn="1.0-15P",
    lcsc="C66660",
    datasheet_url="https://datasheet.lcsc.com/lcsc/BOOMELE-1-0-15P_C66660.pdf",
    datasheet_revision="BOOMELE 1.0-15P mechanical drawing, 2011-06",
    app_circuit_figure="MIPI CSI-2 D-PHY connector + Raspberry Pi camera-FFC pinout",
    local_datasheet_path="components/mipi_camera/datasheet.pdf",
    app_circuit_page="FFC mechanical p. 1 + MIPI D-PHY v1.2 Sec 8 (termination internal)",
    minimum_circuit_verified=True,
    symbol_token="FFC_15P_1mm",
    footprint="Connector_FFC-FPC:FFC_15P_1mm",
    description="15-pin 1.0 mm pitch FPC receptacle for MIPI CSI-2 camera (Pi-camera compatible)",
    supply_rail="+3V3",
    external_parts=(
        # +3V3 supply decoupling at the FFC. The Pi camera draws short
        # bursts of ~250 mA during sensor readout, so a bulk + HF stack
        # local to the connector keeps droop within the sensor's tolerance.
        # ``+3V3`` is the symbol's pin-15 name (see
        # shared/symbols/zynq_eda.kicad_sym FFC_15P), which the carrier's
        # pin_to_net wires to the global +3V3 rail.
        ExternalPart(
            from_pin="+3V3",
            to_net="GND",
            part_token="10u_0603_X7R",
            justification="Bulk decoupling for sensor supply at FFC (~250 mA readout bursts)",
        ),
        ExternalPart(
            from_pin="+3V3",
            to_net="GND",
            part_token="100n_0402_X7R",
            justification="HF bypass for sensor supply at FFC",
        ),
        # Camera I2C pull-ups - carrier owns these (sensor side is open-drain).
        ExternalPart(
            from_pin="CAM_SCL",
            to_net="+3V3",
            part_token="4k7_0402_1%",
            justification="Camera I2C SCL pull-up (carrier-owned, sensor is open-drain)",
        ),
        ExternalPart(
            from_pin="CAM_SDA",
            to_net="+3V3",
            part_token="4k7_0402_1%",
            justification="Camera I2C SDA pull-up (carrier-owned, sensor is open-drain)",
        ),
        # GPIO0 (camera reset) default-low pull-down so the camera stays in
        # reset during boot - matches Pi camera firmware behaviour.
        ExternalPart(
            from_pin="CAM_GPIO0",
            to_net="GND",
            part_token="100k_0402_1%",
            justification="Default-reset pull-down: camera held in reset until host releases",
        ),
    ),
    strap_pins=(),
    no_external_required=frozenset({
        # MIPI D-PHY termination is internal to the receiver (Zynq PL DCI
        # or external MIPI PHY). No external resistors here.
        "CSI_D0+", "CSI_D0-",
        "CSI_D1+", "CSI_D1-",
        "CSI_CLK+", "CSI_CLK-",
        # CAM_GPIO1 has no specific bias requirement (strobe output).
        "CAM_GPIO1",
    }),
    layout_notes=(
        LayoutNote(
            text="Route CSI-2 data and clock pairs as 100 ohm differential "
                 "controlled impedance, intra-pair skew under 0.05 mm",
            severity="rule",
            justification="MIPI D-PHY v1.2 Sec 8: signal-integrity requirement at 800 Mbps/lane",
        ),
        LayoutNote(
            text="Keep CSI-2 trace length under 100 mm; reference to unbroken "
                 "GND plane; no via stitching transitions",
            severity="rule",
            justification="MIPI D-PHY v1.2 Sec 9: maximum line length and return path",
        ),
        LayoutNote(
            text="Place I2C pull-ups within 10 mm of the connector",
            severity="guideline",
        ),
        LayoutNote(
            text="Route CAM_GPIO0/1 away from the high-speed lanes; treat as "
                 "low-speed digital outputs",
            severity="info",
        ),
    ),
)
