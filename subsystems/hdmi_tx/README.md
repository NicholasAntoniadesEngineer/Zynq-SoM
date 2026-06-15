# hdmi_tx — TPD12S016 HDMI source port (reusable subsystem)

A project-agnostic, self-contained schgen subsystem: the TI **TPD12S016**
level-shift / ESD-clamp / +5V load-switch front-end driving a **HDMI Type-A
receptacle** (SOFNG HDMI-019S) as an HDMI **source**. It declares its interface
as **abstract** port + rail names and knows nothing about any board; a consuming
project supplies a **bind map** (`abstract -> real net`) to drop it onto real
nets. Reference circuit: TI TPD12S016 (SLLSE96F) **Figure 15**, "HDMI source
using one GPIO", with `CT_HPD` and `LS_OE` strapped HIGH so the level shifters
and the on-chip 55 mA +5V load switch are always on.

## Package contents

| file | role |
|------|------|
| `hdmi_tx.py`      | the NETLIST — `circuit(meta=None)`, abstract ports/rails |
| `hdmi_tx.cir`     | SPICE subckt — the passive network with the abstract rails as subckt pins |
| `test_hdmi_tx.py` | LOCAL electrical-correctness test (offline, runs the board gate slices on just this subsystem) |
| `README.md`      | this file |

Active parts are **referenced, never vendored**: the TPD12S016PWR and HDMI-019S
symbol/footprint/LCSC come from the global `parts/TPD12S016PWR/` and
`parts/HDMI-019S/`. The faithful dossier symbols are used directly (no `lib_id`
override — the "0 hand-built symbols" law); their pin **numbers** match the
datasheet, so the by-number netting is unchanged.

## The abstract interface (the reuse contract)

A consuming project binds these names. Rails classify as POWER/GROUND by name
(the `+` prefix → POWER; `GND`/`CHASSIS_GND` → GROUND), exactly as real board
rails do, so a standalone build and a bound build share net classes.

### Rails (POWER / GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VDD_IO`     | POWER  | TPD12S016 **V_CCA** (controller side, 3.3 V class). Decoupled 100n + 10u bulk (DS Fig 15). A consuming board may gate it upstream. |
| `+5V`         | POWER  | TPD12S016 **V_CC5V** (cable side) — the load-switch INPUT. The integrated 55 mA current-limited switch drives the cable's +5V from it (DS 7.3.10). Decoupled 100n. |
| `GND`         | GROUND | ground (TPD GND pins + receptacle TMDS shields / DDC ground). |
| `CHASSIS_GND` | GROUND | the four HDMI shell legs; star-bonded to `GND` by the consuming board. |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `TMDS_D2/D1/D0/CLK_P/N` | tmds_pair (100 Ω) | the 4 host-side TMDS differential pairs (V_CCA domain). Each flows **through** the TPD clamp pad to the receptacle — one net per lane, source → clamp → connector. |
| `CEC`               | single | host-side (V_CCA) CEC line; level-shifted to the cable inside the TPD. |
| `DDC_SCL`, `DDC_SDA`| i2c (bus `HDMI_TX_DDC`, 100 kHz) | host-side HDMI DDC bus. DDC pull-ups are **integrated** in the TPD12S016 (DS 7.3.9/7.3.15) — none on-board (the subsystem **waives** the pull-up rule). |
| `HPD`               | single | host-side hot-plug-detect; level-shifted from the cable's 5 V inside the TPD. |

Connector-side (B-side) lanes are **private SIGNAL wiring** (`HDMI_TX_CON_*`,
`HDMI_TX_CON_5V0`) and the always-on straps (`HDMI_TX_LS_OE`,
`HDMI_TX_CT_HPD`) are private too — they are **never** part of the contract and
are never bound. HDMI pin 14 (HEC/Utility) is reserved → an author no-connect on
the receptacle (HDMI 1.4: N.C. on non-HEAC devices). No EDID EEPROM (a SOURCE
reads the sink's EDID).

### Parts (from the global `parts/` lib + inline passives)

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| U1 | TPD12S016PWR | `parts/TPD12S016PWR/` | C201665 |
| J1 | HDMI-019S | `parts/HDMI-019S/` | C111617 |
| C1 | 100n | `Device:C` (V_CCA decoupling) | C14663 |
| C2 | 100n | `Device:C` (V_CC5V decoupling) | C14663 |
| C3 | 100n | `Device:C` (cable +5V HF bypass) | C14663 |
| C4 | 1u   | `Device:C` (cable +5V bulk) | C15849 |
| C5 | 10u  | `Device:C` (V_CCA bulk, 0805) | C15850 |
| R1 | 10k  | `Device:R` (LS_OE strap) | C25804 |
| R2 | 10k  | `Device:R` (CT_HPD strap) | C25804 |

## Consuming it from a project

A project supplies a thin adapter declaring ONE standard `META` dict (the
adapter contract, `schgen.core.subsystem.Meta`) and forwards it:

```python
from subsystems.hdmi_tx import hdmi_tx

META = {
    # abstract subsystem net -> your real board net
    "bind": {
        "+VDD_IO": "+3V3_HDMI_TX", "+5V": "+5V_HDMI_TX",
        "GND": "GND", "CHASSIS_GND": "CHASSIS_GND",
        "TMDS_D2_P": "MY_TMDS_2_P", "TMDS_D2_N": "MY_TMDS_2_N",
        # ... D1 / D0 / CLK ...
        "CEC": "MY_CEC", "DDC_SCL": "MY_SCL", "DDC_SDA": "MY_SDA",
        "HPD": "MY_HPD",
    },
    # optional: tell the linker which of your sheets binds a deferred port
    # (the P line of each TMDS pair carries the pair's deferral)
    "expects": {"TMDS_D2_P": "my_connector", "DDC_SCL": "my_connector", ...},
    # optional house-style overrides (keep your derived artifacts byte-stable)
    "buses": {"ddc": "MY_DDC_BUS"},          # the DDC bus-group name
    "notes": {"draws_vcca": "...", "draws_5v": "..."},  # power-tree draw notes
}

def circuit():
    return hdmi_tx.circuit(META)
```

The four standard `META` keys (`bind` / `expects` / `buses` / `notes`) are
universal across every reusable subsystem — a typo'd top-level key is a hard
`CircuitError`, never silently dropped. `bind` renames every external **in
place, order-preserving** (POWER/GROUND/PORT only — a SIGNAL net is private
wiring and is never rebound; a SIGNAL key or a collision is a hard
`CircuitError`). Because the rename preserves net insertion order, parts, refs,
NCs and port-type payloads, **binding to the exact names a hand-written sheet
used yields a byte-identical emitted sheet.** The carrier adapter is
`carrier/subsystems/hdmi_tx.py`.

## Design notes (datasheet + HDMI 1.4)

- **Flow-through TMDS (LAW 0).** Each of the 8 TMDS lines is **one net** that
  runs source → TPD clamp pad → receptacle. The faithful TPD symbol carries each
  clamp as its own A/B pin number (DS pin map 15..23); the port joins the A pin
  and the receptacle pin so there is one net per lane (proven against the
  kicad-cli netlist export and re-proven by the board netlist gate).
- **Level-shifted control (CEC/DDC/HPD).** These pass through the TPD's level
  shifters: the **A-side** nets are the abstract V_CCA-domain ports above; the
  **B-side** nets (`HDMI_TX_CON_*`) run at the cable's 5 V to the receptacle and
  are private SIGNAL wiring.
- **Integrated DDC pull-ups.** DDC/CEC/HPD pull-ups are **integrated** in the
  TPD12S016 (DS 7.3.9/7.3.15) — no external resistors. The subsystem **waives**
  the I2C-pull-up design rule on `DDC_SCL`/`DDC_SDA` for this reason.
- **Always-on straps.** `LS_OE` + `CT_HPD` are 10k to V_CCA (DS Fig 15 / 8.2.1)
  so the level shifters and the +5V load switch are always on.
- **Cable +5V.** The integrated current-limited switch (55 mA, DS 7.3.10) drives
  receptacle pin 18 from `+5V`; 100n HF + 1u bulk at the connector per HDMI 1.4
  Sec 4.2.7.

## Local test vs board gates

`test_hdmi_tx.py` runs the **subsystem-local** slices offline: declared abstract
interface + port types, model completeness (every pin netted-or-NC), decoupling
completeness (design_rules DECAP/EP/STRAP), part-rating coverage, the SPICE-subckt
↔ netlist passive match, and the bind contract. **Cross-board** gates stay
aggregated at board level and are *not* duplicated here: the link / port-driver
graph, the full power-tree headroom, board ERC, and the board netlist merge — all
run by `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/hdmi_tx/test_hdmi_tx.py -q
```
