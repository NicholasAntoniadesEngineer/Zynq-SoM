"""Generated Zynq PS device-tree fragment (downstream P3).

``schgen devicetree`` (also run by ``schgen board``) writes
``carrier/firmware/carrier_pl.dtsi`` — a COMMENTED device-tree overlay
fragment for the Zynq-7000 PS, the PS-side twin of the PL ``schgen xdc``
(``carrier/fpga/Zynq_Carrier_pins.xdc``).

The XDC constrains every carrier PORT that reaches a PL ball through
J1/J2/J3.  Everything it DROPS on the PS side (a contract net that reaches
no PL ball: the microSD bus and the bare PS MIO pins on J1) gets NOTHING
downstream — yet the firmware/U-Boot/Linux side still needs to know which
SoM MIO index each carrier signal lands on.  This fragment closes that gap:

- the ``SDIO_*`` bus (SDIO_CLK/CMD/D0-D3 on J1) -> the PS SD-host controller
  node (``sdhci``), as a commented overlay with the standard 4-bit-bus +
  card-detect properties;
- every bound ``ZYNQ_PS_MIO<n>`` contract net -> its MIO index ``<n>`` (the
  index is IN the net name), as ``pinctrl`` MIO-line comments — including
  the two function-renamed console pins (MIO10/11 -> PS UART0) and the two
  VMODE boot straps (MIO7/VM0, MIO8\\VM1, on-SoM, carrier no-connect).

Sources (all programmatic — nothing hand-typed):
- carrier net -> J pin: the committed ``carrier/som_interface.json``
  contract, the SAME walk ``schgen firmware`` / ``schgen xdc`` use;
- carrier net -> PL ball (to PROVE a net is PS-side, i.e. reaches no PL
  ball): ``schgen.som_interface.extract_zynq`` (kicad-cli on the SoM
  project at generation time) — exactly as the XDC derives its PL set;
- contract net -> carrier FUNCTION name: ``carrier/som_conn_gen`` FUNCTION_MAP
  (so a renamed MIO resolves to its function PORT, never an orphan), the
  SAME source the J-sheet generator and the linker use.

Deterministic: same inputs -> byte-identical .dtsi (sorted by MIO index /
SDIO line; no timestamps; the device string is read from the SoM netlist).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from schgen.core.som_interface import extract_zynq

REPO_ROOT = Path(__file__).resolve().parents[2]
CARRIER = REPO_ROOT / "carrier"
DEFAULT_SOM = REPO_ROOT / "som" / "Zynq_SoM.kicad_sch"
DEFAULT_CONTRACT = CARRIER / "som_interface.json"
DEFAULT_OUT = CARRIER / "firmware" / "carrier_pl.dtsi"

# Zynq-7000 PS SD host controller node the carrier microSD bus lands on.
# The SoM routes the carrier SDIO_* bus to PS SDIO0 (UG585 Tbl 2-4: SDIO0 =
# sdhci@e0100000); the on-SoM eMMC/boot device, if any, is SDIO1.  This is a
# COMMENTED template — the exact node label is the user's board .dts choice;
# the MIO/EMIO routing itself is fixed on-module and is documented here.
SDIO_NODE = "&sdhci0"            # PS SDIO0 = sdhci@e0100000 (UG585)
SDIO_NODE_ADDR = "e0100000"
# Card-detect is a PL/EMIO net (bank 13, J2.17) — the XDC constrains it as a
# get_ports pin; named here only so the SD node's cd-gpios story is complete.
SD_CARD_DETECT_PORT = "SD_CARD_DETECT"

# SDIO bus line -> its role in the SD-host node (sorted output order is the
# tuple order: CLK, CMD, then the 4 data lines).
SDIO_LINES = (
    ("SDIO_CLK", "clk"),
    ("SDIO_CMD", "cmd"),
    ("SDIO_D0", "dat0"),
    ("SDIO_D1", "dat1"),
    ("SDIO_D2", "dat2"),
    ("SDIO_D3", "dat3"),
)

_MIO_RE = re.compile(r"ZYNQ_PS_MIO(\d+)")


class DeviceTreeError(ValueError):
    pass


def _function_map() -> dict[str, str]:
    """contract-net -> carrier FUNCTION net (carrier/som_conn_gen FUNCTION_MAP
    + PUDC_STRAPS).  Loaded from the SAME source the J-sheets and the linker
    use, so this generator's renames cannot drift from theirs."""
    import importlib.util
    gen_path = CARRIER / "som_conn_gen.py"
    spec = importlib.util.spec_from_file_location("_dt_som_conn_gen", gen_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    m = dict(mod.FUNCTION_MAP)
    m.update(mod.PUDC_STRAPS)
    return m


def _pl_nets(som_sch: Path, refs: tuple[str, ...]) -> set[str]:
    """The SoM contract nets that reach a Zynq PL ball (IO_* pin names) — the
    set the XDC KEEPS.  Anything outside it on J1/J2/J3 is PS-side: exactly
    what we emit here.  Derived from the live netlist, like the XDC."""
    live = extract_zynq(som_sch, jrefs=refs)
    return {net for ball, net in live["ball_net"].items()
            if live["pin_names"].get(ball, "").startswith("IO_")}


def _device(som_sch: Path, refs: tuple[str, ...]) -> str:
    return extract_zynq(som_sch, jrefs=refs)["value"]


def generate(out: Path = DEFAULT_OUT, *,
             som_sch: Path = DEFAULT_SOM,
             contract_path: Path = DEFAULT_CONTRACT,
             refs: tuple[str, ...] = ("J1", "J2", "J3")) -> Path:
    """Build + write the PS device-tree fragment. Raises
    :class:`DeviceTreeError` if the contract carries no PS SDIO/MIO net (the
    walk would silently emit nothing) or if an SDIO line is missing."""
    contract = json.loads(contract_path.read_text())["connectors"]
    func_map = _function_map()
    pl_nets = _pl_nets(som_sch, refs)
    device = _device(som_sch, refs)

    # -- walk the contract, the SAME walk firmware.py / xdc.py use ------------
    # contract net -> sorted J-pin locations (a PS net is a single J1 pin, but
    # collect a list so a future fan-out is reported, not silently dropped).
    net_pins: dict[str, list[str]] = {}
    for jref in refs:
        if jref not in contract:
            raise DeviceTreeError(f"{jref} missing from {contract_path}")
        for pin, som_net in contract[jref]["pins"].items():
            if som_net.startswith("unconnected-"):
                continue
            net_pins.setdefault(som_net, []).append(f"{jref}.{pin}")
    for locs in net_pins.values():
        locs.sort(key=lambda s: (s.split(".")[0], int(s.split(".")[1])))

    # -- SDIO bus: every line PRESENT, PS-side (never on a PL ball) ----------
    sdio_rows: list[tuple[str, str, str]] = []   # (net, role, jpin)
    for net, role in SDIO_LINES:
        if net not in net_pins:
            raise DeviceTreeError(
                f"SDIO line {net!r} absent from the contract — the microSD "
                f"bus is incomplete (expected all of {[n for n, _ in SDIO_LINES]})")
        if net in pl_nets:
            raise DeviceTreeError(
                f"SDIO line {net!r} reaches a PL ball — it is not a PS net; "
                f"the XDC, not this fragment, owns it")
        sdio_rows.append((net, role, net_pins[net][0]))

    # -- PS MIO pins: every bound ZYNQ_PS_MIO<n>, the index from the name ----
    # (the XDC drops these — none reach a PL ball — so they get nothing
    #  downstream without this fragment).  Sort by MIO index.
    mio_rows: list[tuple[int, str, str, str]] = []  # (idx, raw, func, jpin)
    for som_net in net_pins:
        m = _MIO_RE.search(som_net)
        if not m:
            continue
        if som_net in pl_nets:
            raise DeviceTreeError(
                f"{som_net!r} carries a PS MIO index but reaches a PL ball — "
                f"contract/SoM disagree on PS vs PL")
        idx = int(m.group(1))
        func = func_map.get(som_net, som_net)
        mio_rows.append((idx, som_net, func, net_pins[som_net][0]))
    mio_rows.sort(key=lambda r: (r[0], r[1]))
    if not mio_rows:
        raise DeviceTreeError(
            "no ZYNQ_PS_MIO* net in the contract — the PS pinmux walk found "
            "nothing; the contract is stale or PS pins were renamed")
    seen_idx: dict[int, str] = {}
    for idx, raw, _func, _jp in mio_rows:
        if idx in seen_idx:
            raise DeviceTreeError(
                f"MIO{idx} claimed twice: {seen_idx[idx]!r} and {raw!r}")
        seen_idx[idx] = raw

    def rel(p: Path) -> str:
        try:
            return str(Path(p).resolve().relative_to(REPO_ROOT))
        except ValueError:
            return str(p)

    L: list[str] = []
    L.append("/*")
    L.append(" * carrier_pl.dtsi -- Zynq-7000 PS device-tree fragment for the")
    L.append(" * carrier.  GENERATED -- DO NOT EDIT.")
    L.append(" *")
    L.append(" * generated-by: schgen devicetree (schgen/devicetree.py)")
    L.append(" * regenerate:   PYTHONPATH=. python -m schgen devicetree")
    L.append(f" * PS device:    {device} (from the SoM netlist)")
    L.append(" * sources:")
    L.append(f" *   contract : {rel(contract_path)} "
             "(net <- J pin, same walk as schgen firmware/xdc)")
    L.append(f" *   ball map : {rel(som_sch)} "
             "(kicad-cli; PS = reaches no PL ball)")
    L.append(" *   renames  : carrier/som_conn_gen FUNCTION_MAP "
             "(MIO -> carrier function net)")
    L.append(" *")
    L.append(" * This is the PS-side twin of carrier/fpga/Zynq_Carrier_pins.xdc:")
    L.append(" * the XDC owns every carrier net that reaches a PL ball; THIS")
    L.append(" * fragment documents the PS-side nets the XDC drops -- the")
    L.append(" * microSD bus and the bare PS MIO pins routed out on J1.")
    L.append(" *")
    L.append(" * The overlay bodies below are COMMENTED templates: the MIO/EMIO")
    L.append(" * routing is fixed on the SoM, so paste the relevant node(s)")
    L.append(" * into your board .dts and uncomment.  The pinmux table is the")
    L.append(" * authoritative carrier-signal <-> MIO-index map.")
    L.append(" */")
    L.append("")
    L.append("/dts-v1/;")
    L.append("/plugin/;")
    L.append("")

    # -- section 1: PS pinmux table (carrier signal <-> MIO index) -----------
    L.append("/* " + "=" * 72 + " */")
    L.append("/* PS pinmux table -- carrier signal <-> Zynq PS MIO index "
             "(J1 pins).      */")
    L.append("/* (the MIO index is parsed from the contract net name; "
             "sorted by index)  */")
    L.append("/* " + "-" * 72 + " */")
    L.append(f"/* {'MIO':>5}  {'J1 pin':<7}  {'carrier net (function)':<28} "
             f"note */")
    for idx, raw, func, jp in mio_rows:
        note = ""
        if func != raw:
            note = f"renamed from {raw}"
        elif "/" in raw or "\\" in raw:
            # VMODE boot strap (MIO7/VM0, MIO8\VM1): on-SoM, carrier no-connect
            note = "VMODE boot strap (on-SoM, carrier NC)"
        else:
            note = "spare PS MIO (bare to J1)"
        L.append(f"/* MIO{idx:<2}  {jp:<7}  {func:<28} {note} */")
    L.append("/* " + "=" * 72 + " */")
    L.append("")

    # -- section 2: PS UART0 console (the renamed MIO10/11 group) ------------
    uart = {func: idx for idx, raw, func, jp in mio_rows}
    if "ZYNQ_PS_UART0_RXD" in uart and "ZYNQ_PS_UART0_TXD" in uart:
        rx, tx = uart["ZYNQ_PS_UART0_RXD"], uart["ZYNQ_PS_UART0_TXD"]
        L.append("/* ---- PS UART0 console -- MIO console group "
                 "(uart_bridge) ---------- */")
        L.append("/* The carrier brings PS UART0 out on the SoM console MIO "
                 "pair, routed   */")
        L.append("/* to the FT232 USB-UART bridge (carrier uart_bridge "
                 "sheet).            */")
        L.append("/*")
        L.append(" * &uart0 {   // PS UART0 = uart@e0000000 (UG585)")
        L.append(" *     status = \"okay\";")
        L.append(f" *     // MIO{rx} = ZYNQ_PS_UART0_RXD (Zynq RX), "
                 f"MIO{tx} = ZYNQ_PS_UART0_TXD (Zynq TX)")
        L.append(" * };")
        L.append(" */")
        L.append("")

    # -- section 3: microSD on the PS SD-host controller --------------------
    L.append("/* ---- microSD -- PS SD-host controller (sdhci) "
             "------------------------ */")
    L.append("/* The carrier SDIO_* 4-bit bus runs at 1.8 V straight into the "
             "Zynq PS    */")
    L.append("/* (carrier/PLAN.md round 2).  Card-detect is a PL/EMIO net "
             "(bank 13,        */")
    L.append("/* J2.17) the XDC constrains as a get_ports pin -- noted here "
             "for the cd     */")
    L.append("/* story but routed through the PL, not a PS MIO.            "
             "                */")
    L.append("/* " + "-" * 72 + " */")
    L.append(f"/* {'role':<5}  {'J1 pin':<7}  carrier net */")
    for net, role, jp in sdio_rows:
        L.append(f"/* {role:<5}  {jp:<7}  {net} */")
    L.append(f"/* cd     J2.17    {SD_CARD_DETECT_PORT} "
             "(PL/EMIO -- constrained by the XDC) */")
    L.append("/*")
    L.append(f" * {SDIO_NODE} {{   // PS SDIO0 = sdhci@{SDIO_NODE_ADDR} (UG585)")
    L.append(" *     status = \"okay\";")
    L.append(" *     bus-width = <4>;          // SDIO_D0..D3")
    L.append(" *     // 1.8 V signaling (carrier/PLAN.md round 2)")
    L.append(" *     no-1-8-v;                 // delete if the SoM level-shifts")
    L.append(f" *     // card-detect: {SD_CARD_DETECT_PORT} is a PL/EMIO net "
             "(bank 13, J2.17),")
    L.append(" *     // so cd is wired through the PL fabric, not a PS MIO --")
    L.append(" *     // drive it from your EMIO gpio or use broken-cd/non-removable.")
    L.append(" *     broken-cd;")
    L.append(" * };")
    L.append(" */")

    out.parent.mkdir(parents=True, exist_ok=True)
    # pure-ASCII (the contract carries a backslash in MIO8\VM1; comments use
    # plain dashes) for portable dtc toolchains.
    text = "\n".join(L).replace("—", "--").replace("→", "->")
    out.write_text(text + "\n")
    return out


def cmd_devicetree(args: argparse.Namespace) -> int:
    out = generate(getattr(args, "output", None) or DEFAULT_OUT,
                   som_sch=getattr(args, "som", None) or DEFAULT_SOM)
    n_mio = sum(1 for line in out.read_text().splitlines()
                if line.lstrip().startswith("/* MIO"))
    print(f"DEVICETREE: {out} ({n_mio} PS MIO lines mapped)")
    return 0
