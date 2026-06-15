"""pin_completeness — every IC pin is netted or EXPLICITLY NC (LAW 0).

The unfakeable hole this closes: a "missing connection" defect most often
hides not as a wrong net, but as a pin that is SILENTLY left out — neither
wired to a net nor declared a no-connect. The author meant to connect it,
forgot, and nothing complains: ERC sees a sheet that builds, the netlist gate
only proves the nets that WERE declared, and the connected-components detector
only reasons about pins that appear in a net. A pin that is in NEITHER set is
invisible to all of them.

INVARIANT: for every multi-pin IC, each symbol pin NUMBER is either NETTED
(appears in some net of that ref) or NC (appears in circuit.nc_pins). A pin in
neither is a SILENT FLOAT — flagged.

Note Circuit.validate() already enforces full coverage at board-build time, so
a board that builds has zero floats. This gate is the STANDALONE, regression-
locking witness of that property: it runs on the model alone (no geometry, no
kicad-cli), reports any float, and — crucially — EMITS THE CURATED NC ALLOWLIST
(every author-declared no-connect, by ref/pin, with the symbol pin name). That
allowlist is the artifact that lets the gate PROMOTE to hard-fail: once the set
of legitimate NCs is blessed, a NEW unexpected NC (or a float) can be made to
fail the board.

The committed seed allowlist (schgen/verify/data/nc_allowlist.json) is the
datasheet-verified set of intentional NCs — seeded from the overnight audit
(/tmp/morning_stageA.json): e.g. usb_jtag:U1 (CH347T) NCs 2/9/11/12/15 are all
optional mode-3 pins (finding usb_jtag-3); board_services:U2 (RV-3028) CLKOUT
pin 1 is a push-pull output safe to leave open (finding io_misc-4). The report
marks each NC as ``[seed]`` (in the blessed allowlist) or ``[new]`` (present in
the design but not yet blessed) so the backlog to bless is always visible.

REPORT-FIRST (TODO: promote to HARD-FAIL). Lands report-first: it prints the
float count + NC count and writes carrier/reports/pin_completeness.txt but does
NOT fail the board build yet. Once the NC allowlist is fully blessed the
orchestrator flips it to HARD-FAIL by ANDing res.ok into ok_all in cmd_board.

LAW 4: strict. A genuine float is fixed (net it or declare nc()) and a genuine
intentional NC is added to the allowlist with its datasheet justification —
never suppressed or relaxed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core.symbols import Library

_DATA = Path(__file__).resolve().parent / "data" / "nc_allowlist.json"


@dataclass
class PinCompletenessResult:
    ok: bool = True
    parts_checked: int = 0
    nc_total: int = 0
    floats: list[str] = field(default_factory=list)        # silent float pins
    nc_seeded: list[str] = field(default_factory=list)      # NC in allowlist
    nc_new: list[str] = field(default_factory=list)         # NC not yet blessed

    def report(self) -> str:
        lines = ["pin completeness gate "
                 "(every multi-pin IC pin is NETTED or explicit NC)",
                 "=" * 64,
                 "STATUS: REPORT-FIRST (does NOT fail the board yet; promotes "
                 "to HARD-FAIL once the NC allowlist is fully blessed)",
                 f"{self.parts_checked} multi-pin parts checked; "
                 f"{self.nc_total} author-declared NC pins"]
        if self.floats:
            lines.append("")
            lines.append(f"SILENT FLOATS ({len(self.floats)}) — pin neither "
                         f"netted nor NC (probable missing connection):")
            lines += [f"  {f}" for f in self.floats]
        else:
            lines.append("silent floats: none")
        lines.append("")
        lines.append(f"NC ALLOWLIST — {len(self.nc_seeded)} blessed [seed], "
                     f"{len(self.nc_new)} to bless [new]:")
        for n in self.nc_seeded:
            lines.append(f"  [seed] {n}")
        for n in self.nc_new:
            lines.append(f"  [new]  {n}")
        return "\n".join(lines)


def load_allowlist() -> dict:
    if _DATA.exists():
        return json.loads(_DATA.read_text())
    return {}


def run(sheets, rep_dir: Path | None = None,
        lib: Library | None = None,
        allowlist: dict | None = None) -> PinCompletenessResult:
    lib = lib if lib is not None else Library()
    allow = allowlist if allowlist is not None else load_allowlist()
    res = PinCompletenessResult()
    seeded: list[str] = []
    new: list[str] = []
    for sc in sheets:
        c = sc.circuit
        # netted pins per ref, NC pins per ref (model-only; no geometry)
        netted: dict[str, set[str]] = {}
        for net in c.nets.values():
            for pr in net.pins:
                netted.setdefault(pr.ref, set()).add(pr.pin)
        nc: dict[str, set[str]] = {}
        for pr in c.nc_pins:
            nc.setdefault(pr.ref, set()).add(pr.pin)
        sheet_allow = allow.get(sc.name, {})
        for ref, part in sorted(c.parts.items()):
            pins = lib.pin_numbers(part.lib_id)
            if len(pins) < 2:
                continue                       # single-pin part: nothing to float
            res.parts_checked += 1
            names = {p.number: p.name for p in lib.get(part.lib_id).pins}
            nn = netted.get(ref, set())
            cc = nc.get(ref, set())
            floats = sorted(pins - nn - cc, key=lambda s: (len(s), s))
            if floats:
                res.ok = False
                fdesc = ", ".join(f"{n}({names.get(n, '')})" for n in floats)
                res.floats.append(
                    f"{sc.name}:{ref} ({part.value}) silent float pin(s): "
                    f"{fdesc}")
            blessed = set(sheet_allow.get(ref, []))
            for pin in sorted(cc, key=lambda s: (len(s), s)):
                tag = f"{sc.name}:{ref}.{pin} ({part.value} {names.get(pin, '')})"
                (seeded if pin in blessed else new).append(tag)
                res.nc_total += 1
    res.nc_seeded = seeded
    res.nc_new = new
    if rep_dir is not None:
        (Path(rep_dir) / "pin_completeness.txt").write_text(res.report() + "\n")
    return res
