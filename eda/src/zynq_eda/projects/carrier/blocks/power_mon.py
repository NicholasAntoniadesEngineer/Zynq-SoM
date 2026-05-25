"""Carrier Power Monitoring block: INA226 high-side current/power monitor on +VIN.

Single INA226AIDGSR monitors the carrier's +VIN rail by sensing the voltage
across a shunt resistor placed in series with +VIN (typically a 10 mOhm 2010
1% shunt — DS Sec 9.3 Eq 7, full-scale at 8.192 A). The STM32 co-processor
reads bus voltage / shunt voltage / current / power over I2C2 and gets an
asynchronous over-/under-limit notification on the ALERT_N open-drain output.

Block boundaries:
    +VIN  ─┬─[R_sense shunt]──→ +VIN_LOAD (downstream load)
           │                  │
        IN+ │                  │ IN-
            └──────[INA226]────┘
                    │ VS = +3V3, GND
                    │ SDA / SCL → STM32_I2C2
                    │ ALERT_N → STM32_INA226_ALERT_N

The R_sense and the differential filter (10R + 100nF between IN+/IN-) are
declared in INA226_REFCIRCUIT.external_parts so the layout engine places
them around the IC automatically. I2C pull-ups live on the shared +3V3_SC bus
provided elsewhere (see fusb302 refcircuit).
"""

from __future__ import annotations

from zynq_eda.catalog.refcircuits import REFCIRCUITS
from zynq_eda.core.model.block import (
    Block,
    GroundNet,
    IcInstance,
    PowerInputNet,
    SignalNet,
)
from zynq_eda.core.model.interface import SheetEdge


def build_power_mon() -> Block:
    """Return the carrier Power Monitor block (single INA226 on +VIN)."""
    return Block(
        name="power_mon",
        title="Power Monitoring (INA226 on +VIN)",
        paper_size="A4",
        description=(
            "INA226 high-side bidirectional current/power monitor on the +VIN "
            "rail. Sensed across a series shunt (10 mOhm 2010 1%), read by "
            "the STM32 over I2C2 with an open-drain ALERT_N output for "
            "over-/under-limit notification. VS supply = +3V3."
        ),
        ics=(
            IcInstance(
                reference="U1",
                refcircuit=REFCIRCUITS["INA226AIDGSR"],
                lib_id="Sensor_Energy:INA226",
                # INA226 VS (Pin 5) is the chip's logic supply, not a converter
                # output. Tie it to +3V3 so the cluster algorithm labels the
                # VS-decoupling cap correctly.
                power_input_net="+3V3",
            ),
        ),
        external_nets=(
            # Power & ground references.
            PowerInputNet("+VIN", edge=SheetEdge.LEFT),
            PowerInputNet("+3V3", edge=SheetEdge.LEFT),
            GroundNet("GND", edge=SheetEdge.LEFT),
            # I2C2 from the STM32 co-processor (host writes config / reads
            # measurements; bidirectional SDA, input-only SCL).
            SignalNet("STM32_I2C2_SDA",        direction="bidirectional", edge=SheetEdge.LEFT),
            SignalNet("STM32_I2C2_SCL",        direction="input",         edge=SheetEdge.LEFT),
            # Open-drain alert flag back to the STM32 (output from the block).
            SignalNet("STM32_INA226_ALERT_N",  direction="output",        edge=SheetEdge.LEFT),
        ),
    )
