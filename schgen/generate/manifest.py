"""Machine-readable DESIGN MANIFEST (PLAN.md round 5 / P5 — the integration
spine).

``schgen board`` already computes, in memory, the whole state of the design:
the Zynq device, the rail tree + setpoints + limits + declared loads, the I2C
address map + STM32 GPIO map, the XDC pin/bank population, the BOM line-item
census, the test-point coverage. Today every one of those is printed, written
into a human report, or simply discarded. Downstream tools (CI dashboards,
release notes, an external bring-up rig) then have to SCRAPE that prose back
out — brittle, lossy, and version-coupled.

``schgen.manifest.generate`` serializes that same state ONCE, as
``carrier/manifest.json``: a stable, sorted, machine-readable contract other
tools consume instead of re-parsing text. It is a PURE FUNCTION of its inputs
(the linked sheets + the already-computed gate results) — give it the same
board and it writes byte-identical JSON. No wall-clock timestamps; the only
"time" anywhere is the content hash of each emitted artifact.

Schema (top-level keys, all sorted):

- ``device``      — Zynq part value + ref on the SoM (from the XDC walk).
- ``rails``       — list of {name, volts, limit_a, load_a, source, draws[]},
                    one per POWER/GROUND rail, with the regulator/source that
                    feeds it and every declared ``c.draws`` on it.
- ``i2c_map``     — list of {device, addr, addr_hex, bus, sheet, ref}, the
                    strapped addresses DERIVED from the netlists (TCA9535 /
                    INA3221 straps, FUSB302B fixed).
- ``gpio_map``    — list of {net, port, pin, j_pins[]}, the SoM STM32 (U9)
                    GPIO map joined to the J-connector contract.
- ``xdc``         — {pins, banks[]}: the PL pin count and the banks it spans.
- ``bom``         — {lines, parts, missing[], cost, extended}: line-item +
                    placed-part counts and the parts with no LCSC id. ``cost``
                    / ``extended`` are populated only when a preflight result
                    is supplied (live JLC data is non-deterministic), else null.
- ``testpoints``  — {covered, required, waived}: the coverage-gate tally.
- ``artifacts``   — list of {path, sha256}, one per generated file under
                    ``carrier/`` (the hash is read from the file on disk), so a
                    consumer can prove the manifest matches the tree it ships.

``generate(sheets, link_result, ...)`` accepts the already-computed gate
results (power-tree, coverage, XDC) so the board run hands over what it has
rather than recomputing; absent, they are derived from the same pure analysis
functions the gates use, so a standalone manifest is identical to the board's.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from schgen.generate import bringup_facts as bf
from schgen.verify import powertree, testpoints
from schgen.core.model import NetClass

REPO_ROOT = Path(__file__).resolve().parents[2]
CARRIER = REPO_ROOT / "carrier"
DEFAULT_OUT = CARRIER / "manifest.json"

# I2C bus the bring-up devices live on (firmware contract: STM32_I2C2, the
# DAC-pin bit-bang — see schgen/firmware.py section 5).
I2C_BUS = "STM32_I2C2"


# ---- rails ---------------------------------------------------------------------

def _rails(sheets, pt_res: powertree.Result) -> list[dict]:
    """One entry per POWER/GROUND rail: voltage (by name), the regulator/source
    feeding it, its summed load, and every declared draw. All derived from the
    same power-tree analysis the budget gate runs."""
    # rail -> the regulator whose output it is (sheet:ref value), else a source
    fed_by: dict[str, str] = {}
    for reg in pt_res.regs:
        fed_by[reg.vout] = f"{reg.sheet}:{reg.ref} {reg.value} [{reg.kind}]"
    for rail, (_v, _a, who) in powertree.SOURCES.items():
        fed_by.setdefault(rail, f"source: {who}")
    limit_by: dict[str, float] = {r.vout: r.limit_a for r in pt_res.regs}
    for rail, (_v, amps, _who) in powertree.SOURCES.items():
        limit_by.setdefault(rail, amps)

    rail_names: set[str] = set(pt_res.rails)
    for sc in sheets:
        for net in sc.circuit.nets.values():
            if net.net_class in (NetClass.POWER, NetClass.GROUND):
                rail_names.add(net.name)

    out: list[dict] = []
    for name in sorted(rail_names):
        volts = powertree.rail_volts(name)
        draws = [
            {"sheet": s, "amps": round(a, 4), "note": n}
            for s, a, n in sorted(pt_res.draws.get(name, []))
        ]
        out.append({
            "name": name,
            "volts": volts,
            "limit_a": (round(limit_by[name], 4) if name in limit_by
                        else None),
            "load_a": round(pt_res.rails.get(name, 0.0), 4),
            "source": fed_by.get(name),
            "draws": draws,
        })
    return out


# ---- I2C address map -----------------------------------------------------------

def _i2c_map(sheets) -> list[dict]:
    """The strapped I2C address map, addresses DERIVED from the netlists exactly
    as the firmware contract derives them: TCA9535 (A2/A1/A0 straps), INA3221
    (A0 strap), FUSB302B (fixed) on the always-on STM32_I2C2 trunk; the
    ID-EEPROM (A1/A0 straps) + RTC on the gated, PCA9306-isolated AUX_I2C
    segment. Silent on any device class absent from this board so the manifest
    stays a pure function of the sheets present."""
    by_name = {sc.name: sc.circuit for sc in sheets}
    rows: list[dict] = []
    for name, c in sorted(by_name.items()):
        if any("TCA9535" in p.value for p in c.parts.values()):
            exp = bf.expander(c)   # exactly-one guard lives in bringup_facts
            rows.append({"device": "TCA9535", "addr": exp.addr,
                         "sheet": name, "ref": exp.ref})
        for m in bf.ina3221_monitors(c):
            rows.append({"device": "INA3221", "addr": m.addr,
                         "sheet": name, "ref": m.ref})
        for ref in sorted(r for r, p in c.parts.items()
                          if "FUSB302" in p.value):
            rows.append({"device": "FUSB302B", "addr": bf.FUSB302B_ADDR,
                         "sheet": name, "ref": ref})
        if name == "board_services":
            from schgen.generate.firmware import RV3028_ADDR, _id_eeprom_addr
            rows.append({"device": "24AA025E48", "addr": _id_eeprom_addr(c),
                         "sheet": name, "ref": "U1", "bus": "AUX_I2C"})
            rows.append({"device": "RV-3028", "addr": RV3028_ADDR,
                         "sheet": name, "ref": "U2", "bus": "AUX_I2C"})
    rows.sort(key=lambda r: (r["addr"], r["device"], r["sheet"], r["ref"]))
    for r in rows:
        r["addr_hex"] = f"0x{r['addr']:02X}"
        r.setdefault("bus", I2C_BUS)   # AUX rows carry their own bus
    return [{"device": r["device"], "addr": r["addr"], "addr_hex": r["addr_hex"],
             "bus": r["bus"], "sheet": r["sheet"], "ref": r["ref"]}
            for r in rows]


# ---- STM32 GPIO map ------------------------------------------------------------

def _gpio_map(stm32: dict | None) -> list[dict]:
    """The SoM STM32 (U9) GPIO map joined to the J-connector contract — the same
    live extraction the firmware contract uses. ``None`` => derive it here."""
    if stm32 is None:
        stm32 = bf.stm32_pin_map()
    nets: dict[str, bf.Stm32Net] = stm32["nets"]
    out = []
    for name in sorted(nets):
        e = nets[name]
        out.append({"net": e.net, "port": e.port, "pin": e.pin,
                    "j_pins": list(e.j_pins)})
    return out


# ---- BOM census ----------------------------------------------------------------

def _bom(sheets, preflight: dict | None) -> dict:
    """Line-item census (one row per value+footprint+LCSC group, exactly as the
    JLC BOM exporter groups them) + the placed-part count + the parts with no
    LCSC id. ``cost`` / ``extended`` come from a supplied preflight result only
    (live JLC data is non-deterministic); absent, they are null."""
    groups: set[tuple[str, str, str]] = set()
    parts = 0
    missing: list[str] = []
    for sc in sheets:
        for ref, part in sorted(sc.circuit.parts.items()):
            if part.fields.get("BOM") == "exclude":
                continue       # pad-only test points: copper, no BOM line
            parts += 1
            lcsc = part.fields.get("LCSC", "")
            if not lcsc:
                missing.append(f"{sc.name}:{ref}")
            groups.add((part.value, part.footprint, lcsc))
    out = {
        "lines": len(groups),
        "parts": parts,
        "missing": sorted(missing),
        "cost": None,
        "extended": None,
    }
    if preflight is not None:
        if preflight.get("cost") is not None:
            out["cost"] = round(float(preflight["cost"]), 4)
        if preflight.get("extended") is not None:
            out["extended"] = int(preflight["extended"])
    return out


# ---- artifact hashes -----------------------------------------------------------

# Generated files under carrier/ to fingerprint. Globs are resolved + SORTED so
# the artifact list is deterministic; the manifest itself is never hashed (it
# would be hashing its own pre-write state). Directories that hold ONLY authored
# input (subsystems/, research/) or the renders (PNG byte-noise, golden-hashed
# separately) are deliberately excluded.
_ARTIFACT_GLOBS = (
    "Zynq_Carrier.kicad_sch",
    "Zynq_Carrier.kicad_pro",
    "Zynq_Carrier.kicad_pcb",          # PCB foundation (Stream D)
    "schematic/*.kicad_sch",
    "fpga/*.xdc",
    "firmware/*.h",
    "manufacturing/*.csv",
    "manufacturing/*.txt",
    "manufacturing/*.kicad_dru",       # layout + PCB-foundation design rules
    "manufacturing/SI_CONSTRAINTS.md",  # signal-integrity diff-pair/skew table
    "reports/*.txt",
    "docs/*.svg",
    "docs/BRINGUP.md",
    "docs/FLOORPLAN.md",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _artifacts(carrier: Path, out_path: Path) -> list[dict]:
    seen: dict[str, Path] = {}
    for glob in _ARTIFACT_GLOBS:
        for p in carrier.glob(glob):
            if not p.is_file() or p.resolve() == out_path.resolve():
                continue
            seen[str(p.relative_to(carrier))] = p
    return [{"path": rel, "sha256": _sha256(seen[rel])}
            for rel in sorted(seen)]


# ---- device --------------------------------------------------------------------

def _device_from_xdc(xdc_path: Path | None) -> str | None:
    """Read the Zynq device value the XDC walk stamped into its file header
    (``# Device: <value> (<ref> on the SoM)``). The XDC generator already ran
    kicad-cli on the SoM and committed the value here — reading it back is
    deterministic and avoids a second live extraction."""
    if xdc_path is None or not Path(xdc_path).exists():
        return None
    for line in Path(xdc_path).read_text().splitlines():
        if line.startswith("# Device:"):
            return line[len("# Device:"):].strip() or None
    return None


# ---- the manifest --------------------------------------------------------------

def build(sheets, link_result, *,
          pt_res: powertree.Result | None = None,
          tp_res: testpoints.Coverage | None = None,
          xdc_res=None,
          device: str | None = None,
          stm32: dict | None = None,
          preflight: dict | None = None,
          carrier: Path = CARRIER,
          out_path: Path = DEFAULT_OUT) -> dict:
    """The manifest as a plain dict — pure, no I/O except the artifact hashing
    (which reads the already-written generated files). ``generate`` wraps this
    with the JSON write; this split lets a caller inspect/diff without a file."""
    if pt_res is None:
        pt_res = powertree.analyze(sheets)
    if tp_res is None:
        tp_res = testpoints.check_coverage(sheets)

    # device + xdc pins/banks: prefer the supplied XdcResult (the board run
    # already walked the SoM); the bank set is the XDC entries' banks. The XDC
    # walk needs kicad-cli on the SoM, so we never force it here. The device
    # value is read from the XDC file header that walk wrote (deterministic,
    # already on disk) unless passed explicitly.
    xdc_block: dict = {"pins": None, "banks": []}
    if xdc_res is not None:
        xdc_block = {"pins": xdc_res.count,
                     "banks": sorted({e.bank for e in xdc_res.entries})}
        if device is None:
            device = _device_from_xdc(getattr(xdc_res, "path", None))

    return {
        "device": device,
        "rails": _rails(sheets, pt_res),
        "i2c_map": _i2c_map(sheets),
        "gpio_map": _gpio_map(stm32),
        "xdc": xdc_block,
        "bom": _bom(sheets, preflight),
        "testpoints": {
            "covered": tp_res.covered,
            "required": len(tp_res.required),
            "waived": len(tp_res.waived),
        },
        "artifacts": _artifacts(carrier, out_path),
    }


def generate(sheets, link_result, *,
             pt_res: powertree.Result | None = None,
             tp_res: testpoints.Coverage | None = None,
             xdc_res=None,
             device: str | None = None,
             stm32: dict | None = None,
             preflight: dict | None = None,
             carrier: Path = CARRIER,
             out_path: Path = DEFAULT_OUT) -> Path:
    """Serialize the design manifest to ``out_path`` (default
    ``carrier/manifest.json``). Deterministic: sorted keys, no timestamps —
    same inputs + same on-disk artifacts => byte-identical JSON."""
    data = build(sheets, link_result, pt_res=pt_res, tp_res=tp_res,
                 xdc_res=xdc_res, device=device, stm32=stm32,
                 preflight=preflight, carrier=carrier, out_path=out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return out_path


# ---- CLI -----------------------------------------------------------------------

def cmd_manifest(args: argparse.Namespace) -> int:
    from schgen.core.link import all_subsystem_paths, link, load_som_contract, load_subsystem
    names = args.subsystems or [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    res = link(sheets, load_som_contract())
    out = generate(sheets, res, out_path=args.output or DEFAULT_OUT)
    data = json.loads(out.read_text())
    print(f"MANIFEST: {out} ({len(data['rails'])} rails, "
          f"{len(data['i2c_map'])} i2c, {len(data['gpio_map'])} gpio, "
          f"{data['bom']['lines']} bom lines, "
          f"{len(data['artifacts'])} artifacts hashed)")
    return 0
