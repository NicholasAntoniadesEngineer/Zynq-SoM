"""Emit an openable KiCad PCB FOUNDATION (Stream D) — NOT autorouted.

``schgen pcb`` (also run by ``schgen board``) writes
``carrier/Zynq_Carrier.kicad_pcb`` + ``carrier/manufacturing/
Zynq_Carrier_pcb.kicad_dru``: a real, openable, DRC-clean (unrouted-net
violations only) PCB seeded from the SAME netlists/floorplan the schematic
flow uses. It does FOUR things, every number DERIVED:

1. **Board OUTLINE** on Edge.Cuts — a rectangle whose W x H is DERIVED by
   ``floorplan.derive_outline`` (SoM body + escape halo + a connector band on
   each edge + the total component area at a generous fill + a perimeter
   keep-out), sized for routing headroom; the 4 M3 mounting holes (already
   netted to CHASSIS_GND in the model) are forced to the board corners, and a
   SoM-body keep-out zone keeps routing/copper out from under the mezzanine.
2. **A FORCED 4-LAYER controlled-impedance stackup** (Sig / GND / PWR / Sig),
   the JLC04161H-7628 1.6 mm build the constraints already target — written
   into both the ``(layers)`` table and the ``(setup (stackup ...))`` block.
3. **NET CLASSES + a .kicad_dru** — default clearances/widths, the
   impedance-controlled classes for the high-speed nets (TMDS / USB2 / RGMII-
   class diff pairs) and a POWER class for the rails, with per-net
   ``netclass_patterns`` so KiCad assigns every high-speed/rail net to its
   class on open. Reuses ``schgen/generate/constraints.py`` geometry.
4. **FOOTPRINT PLACEMENT** — every BOM footprint embedded into the .kicad_pcb,
   its pads bound to the schematic nets (the merged board netlist KiCad itself
   extracts from the root sheet). Placement is THREE policies layered:
   (A1) the SoM DF40 mezzanine J1/J2/J3 placed at the centered, MIRRORED SoM
   positions (board-to-board mate) with each connector's SoM rotation; (A3)
   every other sheet's footprints packed INTO that sheet's floorplan block, so
   each subsystem clusters contiguously and its ratsnest is a local bundle, not
   a board-wide hairball; and (4) 2-SIDE assembly (default ON, the JLCPCB
   both-sides build) — SoM/edge connectors + large/active ICs on TOP (F.Cu),
   decoupling caps + small passives on BOTTOM (B.Cu) under their cluster, which
   roughly halves top-side area pressure. NO routing.

The merged board netlist is the authoritative source: it is extracted from the
already-emitted ``carrier/Zynq_Carrier.kicad_sch`` with the SAME
``netlist_gate.extract_netlist`` the electrical gate uses, so the PCB's
connectivity is exactly the schematic's — board-unique refs and all. The part
set is therefore identical to the schematic BOM by construction.

DETERMINISM: every uuid is content-derived (``emit.stable_uuid``), positions
are rounded, footprints are emitted in a fixed (ref) order — building twice
yields a byte-identical .kicad_pcb (no timestamps, no random ids).

---
PACKAGE STRUCTURE: this module was decomposed from a single 3141-line file into
a cohesive package (PURE REFACTOR — byte-identical output). The concerns split:

* ``constants``   — module tunables, the rotation/face tables, the connector
                    mating-face / descriptor / switch lookup tables, the 4-layer
                    stackup table and the ``FootprintInst`` / ``PcbModel`` /
                    ``ZoneGeom`` dataclasses (the dependency leaf).
* ``footprint``   — footprint resolution + parsing, the merged board netlist,
                    ``board_parts`` and the net-class derivation.
* ``mating_face`` — LAW-6 connector orientation maths + the placed-geometry
                    queries (pad/courtyard bboxes, ``net_pad_positions``).
* ``placement``   — the per-subsystem shelf packer, 2-side classification, the
                    edge-connector packer, ``subsystem_zone_geometry`` and the
                    ``build_model`` placement entry.
* ``embed``       — footprint EMBEDDING into the board + the layers / stackup /
                    edge / SoM-silk / keepout emit helpers.
* ``silk``        — silk-text geometry, the connector/header/switch function
                    labels and the refdes declutter pass (LAW 1).
* ``emit``        — board serialisation, the .kicad_pro / .kicad_dru writers and
                    the ``schgen pcb`` entry point (``generate`` / ``cmd_pcb``).

This ``__init__`` re-exports the SAME public surface the old module exposed, so
``from schgen.generate.pcb import X`` (and ``import ... as pcb_mod`` attribute
access) keep working unchanged — including the ``sexpr`` / ``Sym`` re-exports a
couple of verify gates import from here.
"""

from __future__ import annotations

# Re-export the s-expr helpers under this package's namespace: a couple of
# verify gates do ``from schgen.generate.pcb import sexpr, Sym`` (the monolithic
# module had them as module globals).
from schgen.core import sexpr as sexpr
from schgen.core.sexpr import Sym as Sym

from . import constants as _constants
from . import footprint as _footprint
from . import mating_face as _mating_face
from . import placement as _placement
from . import embed as _embed
from . import silk as _silk
from . import emit as _emit

# Pull every name (public AND the underscore-prefixed internals — several tests
# and gates reach for ``pcb._rot_bbox`` / ``pcb._CONN_DESC`` / etc.) from each
# submodule into the package namespace, preserving the old flat ``pcb.<name>``
# surface exactly. Order follows the dependency layering so a name defined in a
# later layer (e.g. ``build_model``) wins over any same-named earlier import.
_submods = (_constants, _footprint, _mating_face, _placement, _embed, _silk,
            _emit)
for _m in _submods:
    for _name in dir(_m):
        if _name.startswith("__"):
            continue
        globals()[_name] = getattr(_m, _name)

del _m, _name, _submods
