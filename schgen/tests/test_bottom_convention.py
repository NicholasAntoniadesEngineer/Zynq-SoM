"""BOTTOM-SIDE CONVENTION guards — model pad geometry == EMITTED pad geometry.

THE DEFECT (fixed by the hardening wave, this file is its permanent
instrument): the in-process pad-geometry convention X-MIRRORED bottom-side
footprints (placement._eff_bbox_for, mating_face._inst_pad_geom/_rot_pad_bbox/
_inst_courtyard, placement_contract_gate._pad_boxes) while EMISSION
(embed._flip_to_bottom) keeps local coordinates unchanged and KiCad stores a
B.Cu footprint's coordinates in the FINAL front-view frame, applying ONLY the
placement rotation at load.

GROUND TRUTH (pinned): verified with KiCad's own pcbnew 10.0.2 module loading
the emitted board — every pad's global position equals
``fp_at + R_cw(fp_rot)·(px, py)`` on BOTH sides (worst residual 0.7 um, pure
rounding); independently DRC-proven on C22025 by the T2 wave and by GAP1's
scan.  RED-ON-BEFORE (measured on the live board before unification): the pad
POSITION multiset happened to agree (all bottom parts are X-symmetric
passives) but the NET-at-position was wrong on 319/319 bottom parts — all 650
bottom pads — with per-pad displacement 0.79..2.96 mm (e.g. a microsd 0805's
+3V3_SD modeled 1.90 mm away at its GND pad's true spot; a 4D03 network's
ESC_SIG0 2.40 mm off).  Ratsnest airwire endpoints, contract-gate distances
and escape obstacles all consumed those wrong positions; the escape generator
carried a union-of-both-conventions workaround (now removed).

CONSEQUENCE GUARDED FOREVER (rescoped by wave-9 chirality): a bottom part
emitted from an UNCHANGED library document (inst.mirror=False — the 2-side
classifier population) lands the CHIRAL MIRROR of its top-side pattern, so
that population stays restricted to mirror-symmetric, non-polarized parts
(test_bottom_parts_achiral_nonpolarized). A part emitted from its
pcb/mirror.py MIRRORED document (inst.mirror=True — block bottom variants,
KiCad-exact pcbnew LEFT_RIGHT flip encoding, proven object-equal at 0.0 nm)
carries the physically correct flipped pattern, so ANY footprint may emit
that way; the guard instead demands the mirrored document + bottom side
(tests/test_chirality.py holds the transform pins).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from schgen.core import sexpr
from schgen.core.sexpr import Sym
from schgen.generate.pcb.constants import FootprintInst
from schgen.generate.pcb.emit import emit_pcb
from schgen.generate.pcb.mating_face import (
    _inst_pad_geom,
    _rot_pad_bbox,
)
from schgen.verify.placement_contract_gate import _pad_boxes


@pytest.fixture(scope="module")
def model(carrier_model):
    return carrier_model


@pytest.fixture(scope="module")
def board(model, tmp_path_factory):
    out = tmp_path_factory.mktemp("bottom_conv") / "Zynq_Carrier.kicad_pcb"
    emit_pcb(model, out)
    return out


# ---------------------------------------------------------------------------
# the KiCad-loader reference math (pcbnew-pinned, see module docstring):
# pad center = fp_at + R_cw(fp_rot) · (px, py), IDENTICAL for F.Cu and B.Cu.
# ---------------------------------------------------------------------------
def _emitted_pads(board_path: Path):
    """ref -> (side, [(pad_name, gx, gy, net_name), ...]) parsed from the
    emitted .kicad_pcb with the pcbnew-verified loader transform."""
    doc = sexpr.loads(board_path.read_text())
    out: dict[str, tuple[str, list[tuple[str, float, float, str]]]] = {}
    for node in doc:
        if not (isinstance(node, list) and node and node[0] == Sym("footprint")):
            continue
        lay = next(x for x in node
                   if isinstance(x, list) and x and x[0] == Sym("layer"))
        side = "bottom" if str(lay[1]) == "B.Cu" else "top"
        ref = next((str(x[2]) for x in node
                    if isinstance(x, list) and len(x) > 2
                    and x[0] == Sym("property") and x[1] == "Reference"), "?")
        at = next(x for x in node
                  if isinstance(x, list) and x and x[0] == Sym("at"))
        fx, fy = float(at[1]), float(at[2])
        frot = float(at[3]) if len(at) > 3 else 0.0
        R = math.radians(frot)
        cs, sn = math.cos(R), math.sin(R)
        pads: list[tuple[str, float, float, str]] = []
        for p in node:
            if not (isinstance(p, list) and p and p[0] == Sym("pad")):
                continue
            pat = sexpr.find(p, "at")
            pnet = sexpr.find(p, "net")
            px, py = float(pat[1]), float(pat[2])
            # KiCad CW (+y-down) rotation — NO side-dependent mirror.
            gx = fx + px * cs + py * sn
            gy = fy - px * sn + py * cs
            pads.append((str(p[1]), gx, gy,
                         str(pnet[2]) if pnet is not None else ""))
        out[ref] = (side, pads)
    return out


def test_model_pad_geometry_equals_emitted(model, board):
    """PARITY INSTRUMENT: for EVERY footprint (both sides), the in-process
    model's pad positions + nets (_inst_pad_geom) equal the emitted board's,
    read back with the pcbnew-pinned loader math. Catches anyone reintroducing
    a side-dependent mirror in EITHER the model helpers OR embed/emission.

    Net exemption (documented): pads whose MODEL net is "" may carry a net in
    the file — embed._thermal_via_nets assigns the EP net to blank thermal-via
    pads at EMBED time, downstream of the model (conservative: the model
    treats them as no-net obstacles)."""
    emitted = _emitted_pads(board)
    checked_bottom = checked = 0
    for inst in model.insts:
        side, epads = emitted[inst.ref]
        assert side == inst.side, inst.ref
        mpads = _inst_pad_geom(inst)
        assert len(mpads) == len(epads), inst.ref
        used: set[int] = set()
        for name, mx, my, mnet in mpads:
            best = min(
                ((math.hypot(mx - gx, my - gy), i, gnet)
                 for i, (pname, gx, gy, gnet) in enumerate(epads)
                 if i not in used and pname == name),
                key=lambda t: t[0])
            d, i, gnet = best
            used.add(i)
            assert d <= 0.005, (
                f"{inst.ref}.{name} [{inst.side}]: model pad "
                f"({mx},{my}) is {d:.4f} mm from the emitted position — "
                f"the model/emission convention split is BACK")
            if mnet != "":
                assert mnet == gnet, (
                    f"{inst.ref}.{name} [{inst.side}]: model net {mnet!r} but "
                    f"emitted net {gnet!r} at the same position — net-at-"
                    f"position mismatch (the bottom-mirror defect class)")
            checked += 1
            if inst.side == "bottom":
                checked_bottom += 1
    # the instrument must actually bite: a real 2-side board with a populated
    # bottom (319 parts / 650 pads at unification time).
    assert checked_bottom >= 100, "bottom side unexpectedly empty"
    assert checked >= 1000


# ---------------------------------------------------------------------------
# entry guard: only PROVEN mirror-safe parts may be classified bottom.
# ---------------------------------------------------------------------------

# multi-pad bottom parts must be individually proven mirror-safe and listed
# here WITH the basis; anything else fails the guard until a human proves it.
_MIRROR_SAFE_MULTIPAD = {
    # 4-element ISOLATED equal-value (33R) convex array; every element spans
    # straight across the two pad rows (1-8, 2-7, 3-6, 4-5), so the X-mirror
    # permutes identical elements onto identical elements — electrically
    # mirror-invariant.
    "4D03WGJ0330T5E",
}

_POLARIZED_FP_TOKENS = ("CP_", "D_", "LED", "Diode", "Polar", "Tantal")


def test_bottom_parts_achiral_nonpolarized(model):
    """ENTRY GUARD (tripwire): every NON-MIRRORED bottom part must be (a) a
    passive ref class, (b) a non-polarized footprint, (c) geometrically
    ACHIRAL — its pad (position, size) multiset invariant under the X-mirror —
    and (d) if it has >2 pads, individually proven mirror-safe above. An
    unchanged library document emitted on B.Cu lands the chiral mirror of the
    part's top-side pattern (embed._flip_to_bottom keeps local coordinates,
    KiCad applies no mirror), so any such part failing these tests would
    assemble reversed — a LAW-0 defect the netlist/DRC gates cannot see.
    inst.mirror=True parts are EXEMPT from achirality (their document IS the
    KiCad-exact mirror, any footprint legal) but must carry that mirrored
    document on the bottom side — enforced here and by the embed guard."""
    from schgen.generate.pcb.constants import _INT_DESC, CONN_MATING_FACE
    from schgen.generate.pcb.mirror import is_mirrored_path
    seen_bottom = 0
    for inst in model.insts:
        if inst.mirror:
            assert inst.side == "bottom" and is_mirrored_path(inst.mod_path), (
                f"{inst.ref}: mirror=True must pair a .mirrored_fp document "
                f"with side=bottom")
            assert (inst.ref not in _INT_DESC
                    and inst.value not in CONN_MATING_FACE), (
                f"{inst.ref}: a mating connector may never emit face-down "
                f"(user policy 2026-07-29; the JTAG/SWD-header hole)")
            continue
        if inst.side != "bottom":
            continue
        seen_bottom += 1
        prefix = "".join(ch for ch in inst.ref if ch.isalpha())
        assert prefix in ("R", "C", "L", "RN", "RS", "FB"), (
            f"{inst.ref} ({inst.footprint}): non-passive ref class on the "
            f"BOTTOM — polarized/active parts emit REVERSED (chiral-mirror "
            f"land pattern). Place it top, or prove mirror-safety here.")
        assert not any(t in inst.footprint for t in _POLARIZED_FP_TOKENS), (
            f"{inst.ref}: polarized footprint {inst.footprint} on the BOTTOM")
        # chirality: pad (x, y, w, h) multiset must equal its own X-mirror.
        pads = _pad_footprint_pads(inst.mod_path)
        plain = sorted((round(x, 3), round(y, 3), round(w, 3), round(h, 3))
                       for x, y, w, h in pads)
        mirrored = sorted((round(-x, 3), round(y, 3), round(w, 3), round(h, 3))
                          for x, y, w, h in pads)
        assert plain == mirrored, (
            f"{inst.ref} ({inst.footprint}): CHIRAL pad pattern on the "
            f"BOTTOM — its mirror image cannot seat the physical part")
        if len(pads) > 2:
            fp_name = inst.footprint.split(":")[-1]
            assert fp_name in _MIRROR_SAFE_MULTIPAD, (
                f"{inst.ref}: multi-pad footprint {fp_name} on the BOTTOM is "
                f"not in the proven mirror-safe list — prove the element "
                f"topology is mirror-invariant and add it with a basis")
    assert seen_bottom >= 100, "bottom side unexpectedly empty — guard inert"


def _pad_footprint_pads(mod_path: Path):
    """(x, y, w, h) per pad from a .kicad_mod (local frame, rot 0)."""
    doc = sexpr.loads(mod_path.read_text())
    out = []
    for node in doc:
        if not (isinstance(node, list) and node and node[0] == Sym("pad")):
            continue
        at = sexpr.find(node, "at")
        sz = sexpr.find(node, "size")
        if not (at and len(at) >= 3):
            continue
        sw, sh = (float(sz[1]), float(sz[2])) if sz and len(sz) >= 3 \
            else (0.0, 0.0)
        out.append((float(at[1]), float(at[2]), sw, sh))
    return out


# ---------------------------------------------------------------------------
# red-on-before: the OLD mirrored convention, recomputed inline, must disagree
# with the unified truth on every off-axis bottom pad (pins the measured
# pre-fix delta: pad-pitch-scale displacement, 0.79..2.96 mm on the live
# board, 100% of bottom parts affected).
# ---------------------------------------------------------------------------
def test_red_on_before_old_mirror_convention_was_wrong(model):
    affected = total = 0
    worst = 0.0
    for inst in model.insts:
        if inst.side != "bottom" or inst.mirror:
            continue
        total += 1
        rot = math.radians(inst.rotation or 0.0)
        cs, sn = math.cos(rot), math.sin(rot)
        deltas = []
        for name, ux, uy, _net in _inst_pad_geom(inst):
            # the OLD convention: px = -px before the CW rotation
            pads = {str(n[1]): (float(sexpr.find(n, "at")[1]),
                                float(sexpr.find(n, "at")[2]))
                    for n in sexpr.loads(inst.mod_path.read_text())
                    if isinstance(n, list) and n and n[0] == Sym("pad")}
            px, py = pads[name]
            ox = inst.x + (-px) * cs + py * sn
            oy = inst.y - (-px) * sn + py * cs
            deltas.append(math.hypot(ux - ox, uy - oy))
        if any(d > 0.5 for d in deltas):
            affected += 1
            worst = max(worst, max(deltas))
    # every bottom part WITH off-axis pads shows the old-convention
    # displacement (full-wire leftovers put on-axis single-pad TPs on the
    # bottom too — those are geometrically immune to the mirror bug and
    # excluded from the pin by the 0.5mm delta floor above).
    assert total >= 100
    assert affected >= 100 and affected >= total * 0.9, (
        f"only {affected}/{total} bottom parts show the old-convention "
        f"displacement — the red-on-before pin no longer reproduces")
    # full-wire bottom set: worst measured 1.90 (was 2.96 pre-wire) — still
    # 2x the 0402 pad pitch, decisively wrong.
    assert worst > 1.5, f"worst old-convention delta {worst:.3f} mm"


# ---------------------------------------------------------------------------
# fast unit (no board build): side-independence of every pad-geometry helper
# on a synthetic ASYMMETRIC footprint — the case the old convention broke.
# ---------------------------------------------------------------------------
_ASYM_MOD = """(footprint "test:asym"
  (layer "F.Cu")
  (pad "1" smd rect (at 1 0.5) (size 0.6 0.4) (layers "F.Cu"))
  (pad "2" smd rect (at -2 0) (size 0.6 0.4) (layers "F.Cu"))
)
"""


def test_helpers_side_independent_on_asymmetric_part(tmp_path):
    mod = tmp_path / "asym.kicad_mod"
    mod.write_text(_ASYM_MOD)
    # _pad_boxes / _rot_pad_bbox are side-free by signature now; the placed
    # instance transform must be identical for top and bottom.
    for rot in (0.0, 90.0, 180.0, 270.0):
        boxes = _pad_boxes(mod, rot)
        assert set(boxes) == {"1", "2"}
        insts = {
            side: FootprintInst(
                ref="X1", value="v", footprint="test:asym", x=100.0, y=50.0,
                rotation=rot, pad_nets={"1": (1, "A"), "2": (2, "B")},
                mod_path=mod, sheet="t", side=side)
            for side in ("top", "bottom")
        }
        gt = sorted(_inst_pad_geom(insts["top"]))
        gb = sorted(_inst_pad_geom(insts["bottom"]))
        assert gt == gb, f"rot={rot}: pad geometry differs by side"
        assert _rot_pad_bbox(mod, rot) is not None
    # spot-check the absolute transform at rot 90 (CW, +y-down):
    # (px,py)=(1,0.5) -> (px·cos+py·sin, -px·sin+py·cos) = (0.5, -1).
    b90 = FootprintInst(
        ref="X1", value="v", footprint="test:asym", x=100.0, y=50.0,
        rotation=90.0, pad_nets={"1": (1, "A"), "2": (2, "B")},
        mod_path=mod, sheet="t", side="bottom")
    g = {n: (x, y) for n, x, y, _ in _inst_pad_geom(b90)}
    assert g["1"] == (100.5, 49.0)
    assert g["2"] == (100.0, 52.0)
