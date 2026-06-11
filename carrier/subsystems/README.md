# carrier/subsystems — authoring a subsystem

A subsystem is ONE Python file: the NETLIST, nothing else. No coordinates,
no wire plans, no text positions — the placement engine derives every piece
of geometry from the netlist's topology, and the build FAILS if a subsystem
defines `placer` or imports geometry APIs (the purity gate).

## Compose from parts

```python
from schgen.model import Circuit

def circuit() -> Circuit:
    c = Circuit("my_sheet", "one-line description")

    # actives come from parts/<MPN>/ — lib_id/footprint/LCSC/pins all from
    # the generated folder; a missing folder fails the build with the exact
    # `schgen part add C… --name <MPN>` fix to run.
    u1 = c.use_part("TPS2051CDBVR", ref="U1")

    # connect by pin NAME (validated against the part's pin table; a name
    # carried by stacked duplicate pads nets ALL of them) — bare numbers
    # stay first-class for connectors:
    c.net("+5V_USB", "U1.IN")
    c.port("USB_VBUS", "U1.OUT", "J2.VBUS")

    # passives use the KiCad device libs inline (value + footprint):
    c.part("R1", "Device:R", "56k", "Resistor_SMD:R_0603_1608Metric",
           LCSC="C…")
    c.decouple("U1.IN", "100n")        # macros expand to explicit parts+nets
    c.pullup("U1.FLT#", "100k", "+5V_USB")
    return c
```

## The net contract

Cross-sheet names are the contract. `carrier/nets.py` (regenerate with
`schgen nets`) exposes every SoM connector net and every board rail as a
Python attribute — `from carrier.nets import SOM, RAILS;
c.port(SOM.SDIO_CLK, …)` — so a typo is an AttributeError, not a silent
open. Conventions:

- `c.port(...)` = the sheet's external interface (hier label). Type it where
  it matters: `kind="usb_hs_pair"/"tmds_pair"/"i2c"/"sd_bus"` + `pair_with=`
  / `role=` / `level_v=`. Ports that bind to a later-wave sheet carry an
  explicit `expect="..."` deferral — never a silent skip.
- Gated module rails (+5V_USB, +3V3_SD, …) are POWER nets (`c.net`), not
  ports: schgen synthesizes their power symbols and the linker merges them
  board-wide by name; the bringup sheets source them.
- `c.nc(...)` for intentionally unused pins; `c.hint(net, "trunk")` is the
  only declarative layout extra.

## Build, read the gates, review

```bash
PYTHONPATH=. python -m schgen build my_sheet     # one sheet, all gates
PYTHONPATH=. python -m schgen board              # whole board + project
```

A build prints four verdicts: PURITY (netlist-only source), model
completeness (every input driven), then the three immutable gates —
NETLIST (KiCad's own extraction == your declaration, pin for pin), ERC
(zero errors), VISUAL (zero overlap / zero crossings / fits the page).
Then OPEN the PNG under `carrier/renders/` and read it like a reviewer:
the render is the deliverable.
