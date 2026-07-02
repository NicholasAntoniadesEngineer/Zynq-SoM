"""PLACEMENT CONTRACT (v1) for the ``power`` subsystem — plain data, no logic.

This is the datasheet-grounded layout requirement for the power tree (2x TI
LM61460 synchronous bucks + an AP2112K LDO), carried in the subsystem package
alongside its netlist / README / SPICE / tests because the electrical truths it
encodes (hot-loop tightness, FB isolation, per-pin bypass proximity) are
PROPERTIES OF THE SUBSYSTEM — portable across every carrier that instantiates
it. See ``AI_LAYOUT_ROUTING_CONCEPT.md`` "Phase L" (Pilot contract v1 +
Engine-consumption design) for the concept.

The module exports one constant, :data:`CONTRACT`, a nested dict. It has NO
logic and NO import side effects — the placement-contract gate
(``schgen/verify/placement_contract_gate.py``) reads it and checks the EMITTED
board against it; the intra-zone template (future work) reads the SAME data to
construct the layout. Both consume this file; neither is imported here.

REFS ARE LIBRARY REFS. The contract binds the subsystem's own ``power.py`` refs
(U1/C1/L1/...). A consuming board renames them into a per-sheet band (U1 ->
U20001 on the ``power`` sheet); the gate carries them across with the SAME
``schgen.generate.board._renamed_ref`` map the netlist uses. Role assignment
among INTERCHANGEABLE parts (the two HF flanking caps of a buck are electrically
identical) happens at TEMPLATE time; the gate checks the electrical REQUIREMENT
existentially (some listed 100 nF near each VIN/PGND pair), never a specific ref
-> pin binding — a per-ref check would false-fail a valid swapped layout.

LM61460 PIN MAP (SNVSBD5D Rev. D, verbatim from the repo dossier + power.py):
    1 BIAS   2 VCC   3 AGND   4 FB   5 PGOOD   6 RT   7 EN/SYNC
    8 VIN1   9 PGND1   10 SW   11 PGND2   12 VIN2   13 RBOOT   14 CBOOT
AP2112K-1.8 (SOT-23-5) PIN MAP: 1 VIN   2 GND   3 EN   4 NC   5 VOUT.

EVERY threshold carries a ``basis`` string — either an SNVSBD5D section citation
(from the Phase-L v1 table) or ``judgment:<value>`` for a distance the datasheet
does not number (LAW 7 / LAW 4: auditable, strict, never a guessed spec).
"""

from __future__ import annotations

# --- LM61460 buck pin numbers (shared by both buck stages) -----------------------
# Authored by NUMBER so the contract is footprint-revision-independent (the gate
# reads pad centers from the resolved footprint by these numbers).
_VIN1, _PGND1 = "8", "9"
_VIN2, _PGND2 = "12", "11"
_SW = "10"
_FB, _AGND = "4", "3"
_RBOOT, _CBOOT = "13", "14"
_VCC = "2"
_BIAS = "1"
_RT = "6"

# SWPA8040S inductor pad numbers: pad 1 is the SW-node side (ties to U.SW), pad 2
# is the OUTPUT side (ties to +VOUT_x_REG). The bulk_out caps hang off pad 2.
_L_SW, _L_OUT = "1", "2"

# --- AP2112K LDO pin numbers ------------------------------------------------------
_LDO_VIN = "1"
_LDO_VOUT = "5"

CONTRACT: dict = {
    "contract": "placement/v2",
    "subsystem": "power",
    "sheet": "power",
    # Datasheet the numeric bases cite. Judgment values are marked inline.
    "citations": ["SNVSBD5D Rev. D (LM61460)", "AP2112K"],
    # Netlist-derived ROLES (declared for the pilot; generalize to derivation
    # later). LIBRARY refs -> role string. Documented per-part in power.py.
    "roles": {
        # ---- stage 1: +5V buck (U1) ----
        "U1": "buck_ic",
        "C1": "cin_hf@VIN1", "C25": "cin_hf@VIN2",
        "C2": "cin_bulk", "C3": "cin_bulk",
        "C5": "cout_bulk", "C6": "cout_bulk", "C26": "cout_bulk",
        "L1": "sw_inductor",
        "R1": "fb_top", "R2": "fb_bot", "C27": "fb_cff", "R12": "fb_rff",
        "C4": "boot_cap",
        "C24": "vcc_cap",
        "R11": "bias_r", "C28": "bias_cap",
        "R10": "rt_r",
        # ---- stage 2: +3V3 buck (U2) ----
        "U2": "buck_ic",
        "C7": "cin_hf@VIN1", "C29": "cin_hf@VIN2",
        "C8": "cin_bulk", "C30": "cin_bulk",
        "C10": "cout_bulk", "C11": "cout_bulk",
        "L2": "sw_inductor",
        "R4": "fb_top", "R5": "fb_bot", "C23": "fb_cff", "R15": "fb_rff",
        "C9": "boot_cap",
        "C31": "vcc_cap",
        "R13": "bias_r", "C32": "bias_cap",
        "R14": "rt_r",
        # ---- stage 3: +1V8 LDO (U3) ----
        "U3": "ldo_ic",
        "C12": "ldo_cin", "C13": "ldo_cout",
    },
    # Every structure reads the EMITTED board and is checked by one gate branch.
    # ``ic`` is the LIBRARY ref of the stage's active device; distances are
    # pad-edge-to-pad-edge (mm); ``same_side`` requires the member on the same
    # PCB side as its IC.
    "structures": [
        # ---- HOT LOOP: existential per VIN/PGND pin-pair -------------------------
        # Each buck's TWO VIN/PGND pin-pairs must EACH have SOME contract-listed
        # 100 nF HF cap within the pad-to-pin limit, on the same side as the IC.
        # C1/C25 (and C7/C29) are interchangeable — the gate checks the pair, not
        # the ref binding (see module docstring). SNVSBD5D 9.2.2.5 requires a
        # 100 nF at EACH VIN/PGND pin-pair immediately adjacent to the device.
        {"type": "hot_loop", "ic": "U1",
         "pin_pairs": [[_VIN1, _PGND1], [_VIN2, _PGND2]],
         "caps": ["C1", "C25"],
         "max_pad_to_pin_mm": 1.0, "same_side": True,
         "basis": "SNVSBD5D 9.2.2.5|judgment:1.0"},
        {"type": "hot_loop", "ic": "U2",
         "pin_pairs": [[_VIN1, _PGND1], [_VIN2, _PGND2]],
         "caps": ["C7", "C29"],
         "max_pad_to_pin_mm": 1.0, "same_side": True,
         "basis": "SNVSBD5D 9.2.2.5|judgment:1.0"},

        # ---- BULK INPUT: behind the HF caps, <= 5 mm of a VIN pin ---------------
        {"type": "bulk_in", "ic": "U1", "caps": ["C2", "C3"],
         "vin_pins": [_VIN1, _VIN2], "max_pad_to_pin_mm": 5.0,
         "basis": "SNVSBD5D 9.2.2.5|judgment:5.0"},
        {"type": "bulk_in", "ic": "U2", "caps": ["C8", "C30"],
         "vin_pins": [_VIN1, _VIN2], "max_pad_to_pin_mm": 5.0,
         "basis": "SNVSBD5D 9.2.2.5|judgment:5.0"},

        # ---- BULK OUTPUT: the COUT bank adjacent to the inductor OUTPUT pad -----
        # v2 (Pilot iteration 2): contract v1 omitted the bucks' OUTPUT caps, so
        # they landed as bottom-side value-sorted leftovers ~10 mm from the stage
        # — leaving HALF of each power loop (L -> COUT -> GND) uncontracted. Each
        # listed COUT must sit within 5 mm pad-edge of the inductor's OUTPUT pad
        # (pad 2), on the same side as the IC. UNLIKE the existential hot_loop,
        # this is a per-member (universal) check — EVERY COUT must be in-bound, so
        # a stray one cannot hide behind a compliant sibling. SNVSBD5D Fig 11-2
        # places COUT immediately at the inductor output node (short L->COUT->GND
        # loop); 5 mm is the judgment bound (same family as bulk_in's 5 mm).
        {"type": "bulk_out", "ic": "U1", "caps": ["C5", "C6", "C26"],
         "inductor": "L1", "inductor_out_pin": _L_OUT,
         "max_pad_to_pin_mm": 5.0, "same_side": True,
         "basis": "SNVSBD5D 11.2 Fig 11-2 (COUT adjacent to L)|judgment:5.0"},
        {"type": "bulk_out", "ic": "U2", "caps": ["C10", "C11"],
         "inductor": "L2", "inductor_out_pin": _L_OUT,
         "max_pad_to_pin_mm": 5.0, "same_side": True,
         "basis": "SNVSBD5D 11.2 Fig 11-2 (COUT adjacent to L)|judgment:5.0"},

        # ---- SW NODE: inductor adjacent to the SW pad, <= 3 mm ------------------
        {"type": "sw_node", "ic": "U1", "inductor": "L1", "sw_pin": _SW,
         "max_pad_to_pin_mm": 3.0,
         "basis": "SNVSBD5D 11.1 Fig 11-2|judgment:3.0"},
        {"type": "sw_node", "ic": "U2", "inductor": "L2", "sw_pin": _SW,
         "max_pad_to_pin_mm": 3.0,
         "basis": "SNVSBD5D 11.1 Fig 11-2|judgment:3.0"},

        # ---- FB CLUSTER: divider parts near FB, away from own + foreign SW/L ----
        # Each divider member <= 3 mm of the FB pin; >= 2 mm from this buck's own
        # SW pad / inductor (tightened from 3.0 — the RJR package puts the FB pad
        # ~1.3 mm from SW, so 3.0 was geometrically infeasible for the nearest
        # divider part; see the per-structure basis); >= 5 mm from the OTHER buck's
        # SW pad / inductor.
        {"type": "fb_cluster", "ic": "U1", "fb_pin": _FB,
         "members": ["R1", "R2", "C27", "R12"],
         "own_sw_pin": _SW, "own_inductor": "L1",
         "foreign_ic": "U2", "foreign_sw_pin": _SW, "foreign_inductor": "L2",
         "max_to_fb_mm": 3.0, "min_to_own_sw_mm": 2.0, "min_to_foreign_sw_mm": 5.0,
         "basis": "SNVSBD5D 11.1|judgment:2.0 — FB pad is ~1.3mm from SW pad on "
                  "the 4.0x3.5mm RJR package (TI Fig 11-2 places the divider "
                  "immediately at FB); 3.0 was geometrically infeasible for the "
                  "nearest divider part; noise protection carried by "
                  "min_to_foreign_sw=5.0 + routing-phase trace rules"},
        {"type": "fb_cluster", "ic": "U2", "fb_pin": _FB,
         "members": ["R4", "R5", "C23", "R15"],
         "own_sw_pin": _SW, "own_inductor": "L2",
         "foreign_ic": "U1", "foreign_sw_pin": _SW, "foreign_inductor": "L1",
         "max_to_fb_mm": 3.0, "min_to_own_sw_mm": 2.0, "min_to_foreign_sw_mm": 5.0,
         "basis": "SNVSBD5D 11.1|judgment:2.0 — FB pad is ~1.3mm from SW pad on "
                  "the 4.0x3.5mm RJR package (TI Fig 11-2 places the divider "
                  "immediately at FB); 3.0 was geometrically infeasible for the "
                  "nearest divider part; noise protection carried by "
                  "min_to_foreign_sw=5.0 + routing-phase trace rules"},

        # ---- BOOT cap: <= 2 mm of pins 13/14 (RBOOT/CBOOT) ----------------------
        {"type": "boot", "ic": "U1", "cap": "C4",
         "pins": [_RBOOT, _CBOOT], "max_pad_to_pin_mm": 2.0,
         "basis": "SNVSBD5D 9.2.2.6, 11.1|judgment:2.0"},
        {"type": "boot", "ic": "U2", "cap": "C9",
         "pins": [_RBOOT, _CBOOT], "max_pad_to_pin_mm": 2.0,
         "basis": "SNVSBD5D 9.2.2.6, 11.1|judgment:2.0"},

        # ---- VCC cap: <= 2 mm of pin 2 (VCC) ------------------------------------
        {"type": "vcc_cap", "ic": "U1", "cap": "C24",
         "pin": _VCC, "max_pad_to_pin_mm": 2.0,
         "basis": "SNVSBD5D 9.2.2.8, 11.1|judgment:2.0"},
        {"type": "vcc_cap", "ic": "U2", "cap": "C31",
         "pin": _VCC, "max_pad_to_pin_mm": 2.0,
         "basis": "SNVSBD5D 9.2.2.8, 11.1|judgment:2.0"},

        # ---- BIAS cap: <= 3 mm of pin 1 (BIAS) ----------------------------------
        {"type": "bias_cap", "ic": "U1", "cap": "C28",
         "pin": _BIAS, "max_pad_to_pin_mm": 3.0,
         "basis": "SNVSBD5D 9.2.2.9|judgment:3.0"},
        {"type": "bias_cap", "ic": "U2", "cap": "C32",
         "pin": _BIAS, "max_pad_to_pin_mm": 3.0,
         "basis": "SNVSBD5D 9.2.2.9|judgment:3.0"},

        # ---- RT resistor: <= 3 mm of pin 6 (RT), AGND-referenced ----------------
        {"type": "rt_r", "ic": "U1", "resistor": "R10",
         "pin": _RT, "max_pad_to_pin_mm": 3.0,
         "basis": "SNVSBD5D 8.3.5, 11.1|judgment:3.0"},
        {"type": "rt_r", "ic": "U2", "resistor": "R14",
         "pin": _RT, "max_pad_to_pin_mm": 3.0,
         "basis": "SNVSBD5D 8.3.5, 11.1|judgment:3.0"},

        # ---- LDO stage: Cin/Cout at the LDO pins, <= 2 mm -----------------------
        {"type": "ldo_stage", "ic": "U3",
         "cin": "C12", "cin_pin": _LDO_VIN,
         "cout": "C13", "cout_pin": _LDO_VOUT,
         "max_pad_to_pin_mm": 2.0,
         "basis": "AP2112K 8.2.2|judgment:2.0"},

        # ---- SAME SIDE: every structure member on the same side as its IC -------
        # Overrides the 2-side small-passive-to-bottom policy for contract members
        # (SNVSBD5D 11.1 loop-area rule). Members are the union of every structure
        # above per IC; the gate expands them from ``roles``.
        {"type": "same_side", "ics": ["U1", "U2", "U3"],
         "basis": "SNVSBD5D 11.1 Fig 11-2"},
    ],
    # ADVISORY intra-subsystem power-flow order (NOT gated): stages arranged
    # left-to-right as the schematic stage rows, VIN entry -> +1V8 exit.
    "stage_order": ["U1", "U2", "U3"],
    # COMPOSITION-LEVEL (EXTERNAL) terms — the typed adjacency the placement_flow
    # gate enforces on the WHOLE board (zone-centroid geometry), distinct from the
    # intra-zone structures above. See AI_LAYOUT_ROUTING_CONCEPT.md "Phase L /
    # External (drives composition)". Every distance carries a ``basis`` (judgment
    # here — the datasheet is silent on inter-subsystem spacing; LAW 7).
    "external": {
        # FLOW: the board-level power chain this subsystem sits in. The gate
        # checks each consecutive hop's zone-centroid distance is within a
        # board-scaled budget. pd_input feeds usb_pd (the PD sink+FUSB302), which
        # commands the input rail into ``power`` (the 2 bucks + LDO), whose
        # outputs feed ``power_som`` (the SoM +5V/+3V3 rails). Names are SHEET
        # names (== subsystem package names).
        "flow": ["usb_pd", "power", "power_som"],
        # FACING: this subsystem's OUTPUT-role parts (the bulk_out COUT bank —
        # the physical output node of each stage) must point toward the DOWNSTREAM
        # zone in the flow (``power_som``/SoM), not away from it. The gate reads
        # the roles/structures whose members carry the output and checks the
        # centroid vector sign. ``output_roles`` selects those members from
        # ``roles`` (v2: the bulk_out COUT caps ARE the output node).
        "downstream": "power_som",
        "output_roles": ["cout_bulk"],
        # FAR: keep the switching power stage away from noise-sensitive analog
        # regions. Ethernet's magnetics/MDI line side is the nearest such region
        # on this board; until finer per-region contracts exist, the gate resolves
        # ``ethernet.line_side`` to the whole ``ethernet`` zone (documented
        # coarsening — strict: an UNRESOLVED target FAILS, never a silent skip).
        "far": [
            {"what": "ethernet.line_side", "min_mm": 10.0,
             "basis": "judgment:10.0 — buck switching node vs Ethernet MDI/"
                      "magnetics analog line side; datasheet silent on inter-"
                      "subsystem spacing (SNVSBD5D covers intra-stage only)"},
        ],
    },
}
