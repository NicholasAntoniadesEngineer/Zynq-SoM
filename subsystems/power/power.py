"""power — multi-rail regulator tree (buck + buck + LDO, PG LEDs) LIBRARY.

PROJECT-AGNOSTIC, REUSABLE subsystem. A self-contained package (netlist + README
+ SPICE subckt + local test) that declares its interface as ABSTRACT port + rail
names and knows NOTHING about any consuming board — no carrier net names, no
``carrier/nets.py`` / ``som_interface.json`` reads. A project consumes it by
calling :func:`circuit` with the STANDARD ``meta`` dict (see
:mod:`schgen.core.subsystem`): ``bind`` rebinds every externally-visible net to
its real board name, ``expects`` adds per-port linker deferrals, ``notes``
restores house-style prose. Standalone (``meta=None``) it keeps the abstract
names so this package's ``test_power.py`` runs offline.

This is the carrier's largest subsystem: a +VIN -> +5V buck (LM61460, 6 A SYNC)
-> +3V3 buck (TPS54302) -> +1V8 LDO (AP2112K) chain, each rail with an enable
PORT and a power-good LED. Reference circuit + every design number (FB dividers,
feedforward caps, EN clamp, BIAS tie, input/output caps) per the TI datasheets
(SNVSBD5D LM61460, SLVSDG6C TPS54302, AP2112K) — captured verbatim from the
proven carrier sheet; see README.md "Design notes".

REG-SIDE vs RAIL-SIDE (the external-net split a consuming current-monitor binds):
each regulator's OUTPUT cluster (inductor node, output bulk caps, FB sense, the
PG LED) sits on a REG-SIDE rail (``+VOUT_x_REG``); the board RAIL the loads see
(``+VOUT_x``) is a SEPARATE external net. A project that inserts a series shunt
(e.g. an INA3221 rail-current monitor) bridges ``+VOUT_x_REG`` -> ``+VOUT_x`` so
the consumer draw flows through (and is MEASURED by) the shunt; if the project
has no monitor, its bind map simply ties the two together. BOTH sides are
external POWER nets a project binds — they are NOT internal SIGNAL. (The buck
SWITCH nodes, FB-divider taps, BOOT/CBOOT, BIAS, VCC, RT and the PG-LED cathode
nodes ARE internal SIGNAL and stay verbatim; see README.md.)

ABSTRACT INTERFACE (see README.md for the full table) — the names a project
binds:

  rails (POWER/GROUND):
    +VIN          regulator-tree input (drives the +5V buck VIN pins + its
                  input caps). On the carrier this is the POST-shunt +VIN_SYS.
    +VOUT_5V_REG  +5V buck regulator-side output (inductor node, output bulk,
                  FB sense, PG LED, BIAS tie).
    +VOUT_5V      board +5V rail the loads see (input to the +3V3 buck).
    +VOUT_3V3_REG +3V3 buck regulator-side output.
    +VOUT_3V3     board +3V3 rail (input to the +1V8 LDO + the +1V8 PG LED
                  anode, which is necessarily up before +1V8 exists).
    +VOUT_1V8_REG +1V8 LDO regulator-side output.
    +VOUT_1V8     board +1V8 rail the loads see.
    GND           ground (also the LM61460 heat path: PGND1/PGND2/AGND).
  ports (PORT):
    EN_VOUT_5V    +5V buck enable.
    EN_VOUT_3V3   +3V3 buck enable.
    EN_VOUT_1V8   +1V8 LDO enable.

DESIGN NOTES (datasheet + bring-up contract): see README.md "Design notes".

U1 SYMBOL — FAITHFUL DOSSIER (0 hand-built symbols): U1 (LM61460) draws its
faithful ``parts/LM61460AANRJRR/`` dossier symbol — no ``lib_id=`` override
(the old hand-built ``schgen:LM61460`` is migrated away and gone from
``schgen.verify.symbol_law.PENDING_MIGRATION``). The dossier box lays its 14
pins out by package quadrant (VIN/VCC top, GND bottom, BIAS/FB/PGOOD/RT left,
EN/SW/BOOT right); the placer's box-buck stage handler routes it cleanly. The
swap was NETLIST-NEUTRAL (same pin numbers + footprint).
"""

from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta

# DELIBERATE symbol+footprint overrides (use_part lib_id=/footprint=): the
# stock KiCad regulator/FET drawings stay (pin maps cross-checked above);
# MPN/LCSC/datasheet come from parts/TPS54302DDCR/, parts/AP2112K-1.8TRG1/,
# parts/AO3400A/ and can never drift from the library folders.
BUCK_LIB = "Regulator_Switching:TPS54302"
BUCK_FP = "Package_TO_SOT_SMD:TSOT-23-6"
LDO_LIB = "Regulator_Linear:AP2204K-1.5"   # = AP2112K drawing (see docstring)
LDO_FP = "Package_TO_SOT_SMD:SOT-23-5"
FET_LIB = "Transistor_FET:Q_NMOS_GSD"
FET_FP = "Package_TO_SOT_SMD:SOT-23"
R_FP = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
LED_FP = "LED_SMD:LED_0603_1608Metric"
DZ_FP = "Diode_SMD:D_SOD-123"              # MMSZ5231B 5.1 V EN-clamp zener
L_FP = "SWPA8040S100MT:SWPA8040S100MT"     # faithful EasyEDA footprint (parts/)

# ---- the abstract interface (the REUSE contract) ------------------------------
# Externally-visible net names a consuming project binds. RAILS classify as
# POWER/GROUND by name (a leading '+' = POWER; GND = GROUND), exactly as the
# bound carrier rails do, so a standalone build and a bound build share net
# classes. PORTS are declared with c.port(...). The REG-SIDE vs RAIL-SIDE split
# (a project's current-monitor bridges +VOUT_x_REG -> +VOUT_x with a series
# shunt; the loads + the FB sense sit on opposite sides) is documented above.
RAILS = ("+VIN",
         "+VOUT_5V_REG", "+VOUT_5V",
         "+VOUT_3V3_REG", "+VOUT_3V3",
         "+VOUT_1V8_REG", "+VOUT_1V8",
         "GND")
PORTS = ("EN_VOUT_5V", "EN_VOUT_3V3", "EN_VOUT_1V8")
INTERFACE = RAILS + PORTS

# Default linker deferral for the enable PORTs (a project's rail-enable cells
# bind them on another sheet). A consuming board overrides via meta["expects"].
EXPECT_EN = "rail-enable cells (off-subsystem)"

# Default power-tree draw notes — one key per declared draw. A project overrides
# the prose via meta["notes"]["draws_<rail>"] to cite its own dossier wording
# (keeping its derived power-tree artifact byte-stable). The AMPS are fixed by
# this subsystem's own indicator/divider network (PG LEDs + FB dividers).
DRAWS_5V_A = 0.004
DRAWS_5V_NOTE = "PG LED + FB divider"
DRAWS_3V3_A = 0.009
DRAWS_3V3_NOTE = "PG LED + downstream PG-sense LED chain + FB divider"
DRAWS_1V8_A = 0.001
DRAWS_1V8_NOTE = "PG FET gate divider"

# Nominal / worst-case voltage of each abstract RAIL — the subsystem's own
# electrical contract, NOT a board value. Used by the local test to derate the
# bypass/bulk caps without depending on a board power tree. +VIN worst case =
# 21.0 V (a 20 V PD source +5%); the regulator outputs ride their nominals.
RAIL_WORST_V = {"+VIN": 21.0,
                "+VOUT_5V_REG": 5.0, "+VOUT_5V": 5.0,
                "+VOUT_3V3_REG": 3.3, "+VOUT_3V3": 3.3,
                "+VOUT_1V8_REG": 1.8, "+VOUT_1V8": 1.8,
                "GND": 0.0}


def circuit(meta: "Meta | dict | None" = None) -> Circuit:
    """Build the power subsystem netlist with ABSTRACT port/rail names.

    ``meta`` is the STANDARD subsystem adapter contract (see
    :mod:`schgen.core.subsystem`) — a single dict a consuming project's adapter
    declares. Keys this subsystem reads (all optional; ``meta=None`` ->
    standalone abstract names for the local test):

      ``bind``    ``{abstract_name: project_net}`` rebinds the externally-visible
                  nets (the :data:`INTERFACE` names) to a project's real board
                  names. Applied last (order-preserving => byte-identical sheet).
      ``expects`` ``{abstract_port: deferral}`` attaches an EXPLICIT linker
                  deferral to an enable PORT — a project declares which of its
                  sheets binds the rail-enable.
      ``notes``   ``{"draws_5v"|"draws_3v3"|"draws_1v8": prose}`` power-tree
                  draw-note prose (a project may cite its own dossier wording;
                  defaults to the :data:`DRAWS_*_NOTE` strings).
    """
    meta = Meta(meta)
    c = Circuit("power", "Power: +VIN->+5V->+3V3 bucks + +1V8 LDO, PG LEDs")

    # ---- stage 1: +VIN (20 V) -> +5V buck (LM61460, VQFN-HR, 6 A SYNC) -------
    # U1 RE-SPEC (wt/buck, 2026-06-14): the +5V buck carries the board's heaviest
    # converter load (2.95 A @ 5 V). The prior LMR33630ADDA (3 A) ran at 98% of
    # rating with no headroom, and its bare-JEDEC Tj sat over the guard band
    # (waived). RESELECTED to the LM61460AANRJRR (LCSC C2864505, JLC 2026-06-14:
    # Extended, stock 3,761): TI 3-42 V / 6-A LOW-EMI SYNCHRONOUS step-down
    # (SNVSBD5D), peak-current-mode, adjustable fSW, in the 14-pin VQFN-HR (RJR
    # "HotRod") package. 6 A rating -> ~2x margin over 2.95 A (>>40% target);
    # Vin op-max 36 V (abs 42 V) covers the 21 V +VIN rail with wide margin.
    #   Vref = 1.0 V (DS 8.3.11) -> FB divider Vout = 1.0*(1 + Rtop/Rbot);
    #     R1/R2 = 40.2k/10k -> 5.02 V (same Vref + divider RATIO as the old
    #     LMR33630). FB-top LCSC is C12447 (UNI-ROYAL 0603WAF4022T5E, 40.2k 0603
    #     1%); C25804 (10k) bottom unchanged. (The old C25750 LCSC was a mis-key
    #     -> 120k 0402; corrected here, see R1 below.)
    #   fSW = 600 kHz set by RT = 22k (DS Eq 2: RRT(kohm) = (1/fSW(kHz) -
    #     3.3e-5)*1.346e4 -> 600 kHz => 21.99k ~= 22.0k; 22k C31850 already in
    #     this sheet's BOM). 600 kHz keeps the existing 10 uH SWPA8040S: ripple
    #     dIL = Vout*(Vin-Vout)/(Vin*L*fSW) = 5*16/(21*10u*600k) = 0.63 A p-p,
    #     Ipk = 2.95 + 0.32 = 3.27 A < the 4 A Isat.
    #   L = 10 uH (DS 9.2.2.3): the Eq-11 (D<50%) MINIMUM is L >= 0.2*Vout/fSW =
    #     0.2*5/600k = 1.67 uH; 10 uH is well above min, so the part runs stable
    #     with no subharmonic oscillation (inductance must not be LESS than the
    #     minimum). 9.2.2.3 note: a larger-than-min inductor "results in less
    #     output cap being needed to limit ripple but more output cap to manage
    #     large load transients" -> the 3x22 uF COUT (above the 2x22 uF min)
    #     covers that. KEEP the existing 10 uH SWPA8040S (no churn).
    #   CBOOT = 100 nF SW->CBOOT (DS 9.2.2.6, X7R >=10 V); RBOOT short to CBOOT
    #     (DS 9.2.2.7 "RBOOT can be shorted") -> fastest SW edge, lowest HS loss:
    #     RBOOT(13) and CBOOT(14) are the SAME node (BOOT_5V0), a 0R wire, NO
    #     component.
    #   BIAS (pin 1): TIED to +VOUT_5V_REG via R11 (10 ohm series) + C28 (1 uF
    #     bypass) per DS 9.2.2.9 — the BIAS->VOUT tie reduces internal-LDO power
    #     loss I_LDO*(VIN-VOUT) at VOUT = 5 V (efficiency improvement; see the
    #     BIAS block below). BIAS max voltage 16 V >> 5 V.
    #   VCC (pin 2): 1 uF to AGND (DS 9.2.2.8 internal-LDO bypass, 16 V ceramic).
    #   RT (pin 6): 22k to GND (fSW set). PGOOD (pin 5): NC (unused open-drain;
    #     D1 rail-up LED is the PG indicator).
    #   AGND (3) ties to PGND1/PGND2 (DS pin 3 layout note).
    # THERMAL: VQFN-HR has NO center EP; its die-attach heat path is the bond-
    # frame PGND1 (9) + PGND2 (11) power-ground pads (and the wide SW pad 10),
    # all soldered to the GND copper pour — the package's exposed-pad-equivalent.
    # DS RthJA = 58.7 C/W bare JESD51-7, 25 C/W on a 4-layer board (DS 7.3 +
    # note: "with a 4-layer PCB, a RthJA = 25 C/W can be"). The thermal gate now
    # credits a CONSERVATIVE pour-aware RthJA (see thermal.py) so U1 PASSES on
    # real margin, not a waiver.
    # use_part WITHOUT a lib_id= override: U1 now draws its FAITHFUL parts/
    # dossier symbol (LM61460AANRJRR:LM61460AANRJRR), the "0 hand-built symbols"
    # migration (symbol_law). The dossier box lays its 14 pins out by package
    # quadrant — VIN1/VIN2/VCC on TOP, AGND/PGND1/PGND2 on BOTTOM, BIAS/FB/PGOOD/
    # RT on the LEFT, EN/SYNC/SW/RBOOT/CBOOT on the RIGHT — every pin distinct
    # (no stacked-duplicate / hidden-pin tricks). The regulator template's
    # box-stage handler reads input/output/ground off ANY edge (place.py
    # _buck_box_stage) so this faithful all-passive QFN box places + routes
    # cleanly. Pins are authored BY NUMBER (netlist-neutral vs the old hand
    # symbol; identical pin NUMBERS + footprint) — 1 BIAS 2 VCC 3 AGND 4 FB
    # 5 PGOOD 6 RT 7 EN/SYNC 8 VIN1 9 PGND1 10 SW 11 PGND2 12 VIN2 13 RBOOT
    # 14 CBOOT.
    c.use_part("LM61460AANRJRR", ref="U1")
    # U1 input is the regulator-tree input rail +VIN. On a board with a series
    # current-monitor it is the POST-shunt rail (the project series-inserts a
    # shunt between any inlet eFuse and the buck inputs), so the buck input
    # current — including the input-cap ripple/inrush — flows through (and is
    # measured by) that shunt. The input caps move with it.
    c.net("+VIN", "U1.8", "U1.12")                                # VIN1(8)+VIN2(12)
    c.net("GND", "U1.9", "U1.11", "U1.3")                         # PGND1(9)+PGND2(11)+AGND(3): heat path
    c.port("EN_VOUT_5V", "U1.7", **meta.expect_kw("EN_VOUT_5V"))  # EN/SYNC (pin 7)
    # INPUT CAPS (DS SNVSBD5D 9.2.2.5): bulk + the MANDATORY per-VIN-pin HF caps.
    #   - 2x 10 uF bulk (C2/C3, 1206): satisfies the ">=10 uF ceramic at the input"
    #     minimum (9.2.2.5); 50 V-class 1206 covers the 21 V +VIN rail.
    #   - 2x 100 nF HF (C1/C25, 50 V X7R): 9.2.2.5 REQUIRES a "small case size
    #     100-nF ceramic ... at EACH input/ground pin pair, VIN1/PGND1 and
    #     VIN2/PGND2, immediately adjacent to the device ... The two 100 nF must
    #     also be rated at 50 V with an X7R or better dielectric." The VQFN-HR
    #     (RJR) splits VIN/PGND across opposite package sides, so ONE 100 nF goes
    #     at each VIN/PGND location (DS example: "two 4.7-uF and two 100-nF, one
    #     at each VIN/PGND"). C14663 = YAGEO CC0603KRX7R9BB104, 100 nF 50 V X7R
    #     0603 (live JLC 2026-06-15: Basic, stock 17,789,417) — meets the
    #     50 V/X7R rule. The netlist puts both on +VIN->GND (the placer/PCB
    #     fans one to each VIN pad); the split is a layout/footprint property.
    for ref, val, fp, lcsc in (("C1", "100n", C0603, "C14663"),  # HF, VIN1/PGND1
                               ("C25", "100n", C0603, "C14663"), # HF, VIN2/PGND2
                               ("C2", "10u", C1206, "C13585"),  # bulk (>=10 uF)
                               ("C3", "10u", C1206, "C13585")):
        c.part(ref, "Device:C", val, fp, LCSC=lcsc)
        c.net("+VIN", f"{ref}.1")                                  # buck-input filter
        c.net("GND", f"{ref}.2")
    c.part("C24", "Device:C", "1u", C0603, LCSC="C15849")          # VCC int-LDO bypass
    c.net("U1_VCC", "U1.2", "C24.1")                              # VCC (pin 2), local bias
    c.net("GND", "C24.2")
    # BIAS (pin 1) TIED TO VOUT (DS SNVSBD5D 9.2.2.9): "Because VOUT = 5 V in
    # this design, the BIAS pin is tied to VOUT to reduce LDO power loss. The
    # output voltage is supplying the LDO current instead of the input voltage.
    # The power saving is I_LDO*(VIN - VOUT)." With VIN ~21 V this is the larger
    # saving (9.2.2.9 / 8.3.14). 9.2.2.9 adds: "a series resistor, 1 ohm to
    # 10 ohm, can be added between VOUT and BIAS" to keep VOUT noise/transients
    # off BIAS, and "a bypass capacitor of 1 uF or higher can be added close to
    # the BIAS pin." Max allowed BIAS voltage is 16 V (>> 5 V) — safe.
    #   R11 = 10 ohm series +VOUT_5V_REG -> BIAS (top of the 1-10 ohm band: max
    #     noise filtering; the BIAS LDO sink current is tiny so the IR drop is
    #     negligible). C22859 = UNI-ROYAL 0603WAF100JT5E 10R 0603 (live JLC
    #     2026-06-15: Basic, stock 3,513,381).
    #   C28 = 1 uF BIAS bypass -> GND, close to pin 1. C15849 = Samsung
    #     CL10A105KB8NNNC 1 uF 50 V X5R 0603 (Basic, stock 6,321,848).
    c.part("R11", "Device:R", "10R", R_FP, LCSC="C22859")          # BIAS series (1-10 ohm)
    c.net("+VOUT_5V_REG", "R11.1")                                 # tie BIAS to VOUT
    c.part("C28", "Device:C", "1u", C0603, LCSC="C15849")          # BIAS bypass
    c.net("BIAS_5V0", "U1.1", "R11.2", "C28.1")                   # BIAS (pin 1)
    c.net("GND", "C28.2")
    c.part("R10", "Device:R", "22k", R_FP, LCSC="C31850")          # RT: fSW=600kHz (DS Eq 2)
    c.net("RT_5V0", "U1.6", "R10.1")                             # RT (pin 6)
    c.net("GND", "R10.2")
    c.part("C4", "Device:C", "100n", C0603, LCSC="C14663")          # BOOT (CBOOT) cap
    # RBOOT(13) short to CBOOT(14): SAME node, a 0R wire (DS EC table) — no R.
    c.net("BOOT_5V0", "U1.14", "U1.13", "C4.1")                  # CBOOT(14)+RBOOT(13)
    c.part("L1", "Device:L", "10uH", L_FP, LCSC="C37429")
    c.net("SW_5V0", "U1.10", "C4.2", "L1.1")                      # SW(10) + CBOOT-cap + L
    # buck-1 OUTPUT cluster is +VOUT_5V_REG (reg-side of the output shunt). The
    # inductor node, output bulk caps, FB sense and the PG LED stay on the
    # regulator side; the board +VOUT_5V rail (post-shunt) carries the measured
    # consumers (the +3V3 buck input, C7/C8). A project's shunt bridges
    # +VOUT_5V_REG -> +VOUT_5V so consumer draw is measured.
    c.net("+VOUT_5V_REG", "L1.2")
    # OUTPUT CAPS (DS SNVSBD5D 9.2.2.4 + Table 9-3/9-5): 3x 22 uF ceramic for the
    # 5 V output. Table 9-5 (the 5 V application BOM) lists 3x22 uF COUT at 400 k,
    # 1000 k and 2100 kHz; Table 9-3 5 V "better transient" at 2.1 MHz is also
    # 3x22 uF. This RAISES the previous 2x22 uF (the Table 9-3 5 V *minimum* at
    # 2.1 MHz) by one cap. Justification at this design's L/fSW: 9.2.2.3 notes a
    # larger-than-minimum inductor (here 10 uH >> the ~1.67 uH Eq-11 minimum at
    # 600 kHz) "results in less output capacitance being needed to limit output
    # ripple but more output capacitance being needed to manage large load
    # transients" — so with the big 10 uH the transient term dominates and 3x22 uF
    # gives the datasheet-coherent transient margin at 5 V / 6 A. (A 47 uF/1210 was
    # considered per Table 9-3 400 kHz; the well-stocked Basic 47 uF 1210 parts on
    # JLC are 6.3 V-rated — too low for a 5 V rail with margin — and the 25 V
    # 47 uF/1210 is Extended/low-stock, so 3x22 uF reuses the proven 25 V Basic
    # C45783 and lands on the Table 9-5 5 V value.)
    for ref in ("C5", "C6", "C26"):
        c.part(ref, "Device:C", "22u", C0805, LCSC="C45783")
        c.net("+VOUT_5V_REG", f"{ref}.1")                         # output bulk, reg-side
        c.net("GND", f"{ref}.2")
    c.part("R1", "Device:R", "40.2k", R_FP, LCSC="C12447")         # FB top (VFB 1.0 -> 5.02 V); C12447 = UNI-ROYAL 0603WAF4022T5E 40.2k 0603 1%. (Prior LCSC C25750 was a mis-key: it resolves to a 120k 0402 -> the assembled FB divider would set ~13.1 V on the +5V rail and destroy the SoM. BOM-CRITICAL.)
    c.part("R2", "Device:R", "10k", R_FP, LCSC="C25804")           # FB bottom
    c.net("+VOUT_5V_REG", "R1.1")                                  # FB senses the regulated node
    c.net("FB_5V0", "U1.4", "R1.2", "R2.1")                       # FB (pin 4)
    c.net("GND", "R2.2")
    # FB FEEDFORWARD (DS SNVSBD5D 9.2.2.10 + Tables 9-2/9-3/9-5): a CFF across the
    # FB-top resistor "is used to improve phase margin and transient response of
    # circuits which have output capacitors with low ESR" (the all-ceramic COUT
    # here). The ESR-zero rule passes: ceramic COUT has its ESR zero well above
    # 200 kHz, so 9.2.2.10's "if the ESR zero ... is below 200 kHz, no CFF" does
    # NOT exclude us; and VOUT = 5 V < 14 V, so the "no CFF above 14 V" rule does
    # not apply either. Value = 22 pF C0G: Table 9-2 (5 V rows) and Table 9-5 (5 V
    # BOM) both list CFF = 22 pF. 9.2.2.10 also says: "Since this capacitor can
    # conduct noise from the output of the circuit directly to the FB node of the
    # IC, a 1-kohm resistor, RFF, can be placed in series with CFF" (Table 9-2 5 V
    # RFF = 1 kohm) — so the network is +VOUT_5V_REG -> C27(CFF) -> RFF(R12) ->
    # FB_5V0, i.e. CFF bridges the FB-top R1 with RFF damping the noise path into
    # FB. (The 3 TPS54302 bucks use the same all-ceramic feedforward idiom, PWR-4.)
    #   C27 = 22 pF 50 V C0G 0603 (CL10C220JB8NNNC, live JLC 2026-06-15: Basic,
    #     stock 1,017,863). R12 = 1 k 0603 (C21190, the sheet's existing 1k).
    c.part("C27", "Device:C", "22p", C0603, LCSC="C1653")          # CFF (DS 9.2.2.10)
    c.part("R12", "Device:R", "1k", R_FP, LCSC="C21190")           # RFF series (DS 9.2.2.10)
    c.net("+VOUT_5V_REG", "C27.1")                                 # CFF top = VOUT (across R1)
    c.net("CFF_5V0", "C27.2", "R12.1")                            # CFF -> RFF noise damp
    c.net("FB_5V0", "R12.2")                                       # RFF -> FB node
    c.part("D1", "Device:LED", "red", LED_FP, LCSC="C2286")        # +5V present indicator
    c.part("R3", "Device:R", "1k", R_FP, LCSC="C21190")
    c.net("+VOUT_5V_REG", "D1.2")                                  # LED reg-side (regulator up)
    c.net("PG_5V0", "D1.1", "R3.1")                               # plain rail-up LED (reg-side)
    c.net("GND", "R3.2")
    # PGOOD (pin 5) author NC: open-drain status output (DS pin 5, high=OK via an
    # external pull-up, low=fault). Unused here — the +5V rail-up LED (D1) is the
    # board's PG indicator — so the open-drain output is left unconnected (an
    # un-driven open-drain output floats harmlessly; nothing reads it).
    c.nc("U1.5")                                                  # PGOOD (pin 5) — unused, NC

    # ---- stage 2: +5V -> +3V3 buck ------------------------------------------
    c.use_part("TPS54302DDCR", ref="U2", lib_id=BUCK_LIB, footprint=BUCK_FP)
    c.net("+VOUT_5V", "U2.3")
    c.net("GND", "U2.1")
    c.port("EN_VOUT_3V3", "U2.5", **meta.expect_kw("EN_VOUT_3V3"))
    for ref, val, fp, lcsc in (("C7", "100n", C0603, "C14663"),
                               ("C8", "22u", C0805, "C45783")):
        c.part(ref, "Device:C", val, fp, LCSC=lcsc)
        c.net("+VOUT_5V", f"{ref}.1")
        c.net("GND", f"{ref}.2")
    c.part("C9", "Device:C", "100n", C0603, LCSC="C14663")          # BOOT
    c.net("BOOT_3V3", "U2.6", "C9.1")
    c.part("L2", "Device:L", "10uH", L_FP, LCSC="C37429")
    c.net("SW_3V3", "U2.2", "C9.2", "L2.1")
    # buck-2 OUTPUT cluster is +VOUT_3V3_REG (reg-side of the output shunt). U2's
    # INPUT stays the board +VOUT_5V (above) — it is a +5V consumer, measured by
    # the +5V output shunt.
    c.net("+VOUT_3V3_REG", "L2.2")
    for ref in ("C10", "C11"):
        c.part(ref, "Device:C", "22u", C0805, LCSC="C45783")
        c.net("+VOUT_3V3_REG", f"{ref}.1")                       # output bulk, reg-side
        c.net("GND", f"{ref}.2")
    c.part("R4", "Device:R", "100k", R_FP, LCSC="C25803")          # FB top
    c.part("R5", "Device:R", "22k", R_FP, LCSC="C31850")           # FB bottom
    c.part("C23", "Device:C", "75p", C0603, LCSC="C22399620")      # FB feedfwd
    c.net("+VOUT_3V3_REG", "R4.1", "C23.1")                       # FB + feedfwd reg-side
    c.net("FB_3V3", "U2.4", "R4.2", "R5.1", "C23.2")
    c.net("GND", "R5.2")
    c.part("D2", "Device:LED", "red", LED_FP, LCSC="C2286")        # PG +3V3
    c.part("R6", "Device:R", "330R", R_FP, LCSC="C23138")
    c.net("+VOUT_3V3_REG", "D2.2")                                # PG LED reg-side
    c.net("PG_3V3", "D2.1", "R6.1")
    c.net("GND", "R6.2")

    # ---- stage 3: +3V3 -> +1V8 LDO -------------------------------------------
    c.use_part("AP2112K-1.8TRG1", ref="U3", value="AP2112K-1.8",
               lib_id=LDO_LIB, footprint=LDO_FP)
    c.net("+VOUT_3V3", "U3.1")                                     # LDO input: board +3V3
    c.net("GND", "U3.2")
    c.port("EN_VOUT_1V8", "U3.3", **meta.expect_kw("EN_VOUT_1V8"))
    c.nc("U3.4")                                                   # NC pin
    # LDO OUTPUT is +VOUT_1V8_REG (reg-side of the output shunt). The LDO INPUT
    # cap C12 stays on the board +VOUT_3V3 (it is a +3V3 consumer, measured by
    # the +3V3 output shunt); only the output node + output cap move to
    # +VOUT_1V8_REG. A project's shunt bridges +VOUT_1V8_REG -> the board
    # +VOUT_1V8 the loads see.
    c.net("+VOUT_1V8_REG", "U3.5")
    c.part("C12", "Device:C", "1u", C0603, LCSC="C15849")          # LDO in
    c.net("+VOUT_3V3", "C12.1")
    c.net("GND", "C12.2")
    c.part("C13", "Device:C", "1u", C0603, LCSC="C15849")          # LDO out
    c.net("+VOUT_1V8_REG", "C13.1")                                # output cap reg-side
    c.net("GND", "C13.2")

    # ---- +1V8 PG sense cell (red Vf > 1.8 V -> FET sense) -------------------
    # +1V8 cannot light a red LED directly (Vf ~2.0 V > rail), so an AO3400A
    # (Vgs(th) <= 1.45 V max) senses the rail (1k gate-stop + 100k pulldown) and
    # sinks a 330R+LED chain from +VOUT_3V3 — which is necessarily up before
    # +1V8 exists. PWR-6: the gate series was 10k, which with the 100k pulldown
    # only presented +1V8 * 100/110 = 1.64 V on Vgs — barely above the 1.45 V
    # max Vth, no guaranteed turn-on. Dropping it to 1k (a pure RC gate-stop now,
    # not a divider) lets Vgs see +1V8 * 100/101 = 1.78 V, a solid margin.
    c.part("R7", "Device:R", "1k", R_FP, LCSC="C21190")            # gate-stop
    c.part("R8", "Device:R", "100k", R_FP, LCSC="C25803")          # gate pulldown
    c.use_part("AO3400A", ref="Q1", lib_id=FET_LIB, footprint=FET_FP)
    c.net("+VOUT_1V8", "R7.1")
    c.net("PG_1V8_G", "R7.2", "R8.1", "Q1.1")
    c.net("GND", "R8.2", "Q1.2")
    c.part("R9", "Device:R", "330R", R_FP, LCSC="C23138")
    c.part("D3", "Device:LED", "red", LED_FP, LCSC="C2286")        # PG +1V8
    c.net("PG_1V8_D", "Q1.3", "R9.2")
    c.net("PG_1V8_K", "R9.1", "D3.1")
    c.net("+VOUT_3V3", "D3.2")

    # ---- test points (coverage gate): the generated rails + a ground probe
    # return, at their source sheet ------------------------------------------
    for net in ("+VOUT_5V", "+VOUT_3V3", "+VOUT_1V8", "GND"):
        c.testpoint(net)

    # ---- power-tree budget declarations -------------------------------------
    c.draws("+VOUT_5V", DRAWS_5V_A, meta.note("draws_5v", DRAWS_5V_NOTE))
    c.draws("+VOUT_3V3", DRAWS_3V3_A, meta.note("draws_3v3", DRAWS_3V3_NOTE))
    c.draws("+VOUT_1V8", DRAWS_1V8_A, meta.note("draws_1v8", DRAWS_1V8_NOTE))
    # THERMAL WAIVERS (verification P2) — see carrier/research/thermal_bucks.md.
    # The TPS54302 is SOT-23-6 (DDC) with NO exposed pad; the thermal gate's
    # bare-package 2s2p RthJA (70.6 C/W) + 0.85 eff floor put Tj over the 140 C
    # guard at the worst-case rail loads. This buck is LAYOUT-CRITICAL: a power-
    # optimised 4-layer layout (large SW/VIN/PGND copper pours + a thermal-via
    # field) plus the part's real ~88-91% efficiency brings the effective RthJA
    # to ~45-55 C/W and Tj under limit.
    # REVIEW-FLAGGED: confirm by thermal sim / bench Tj at bring-up; if the
    # layout cannot hit the target RthJA, switch to an exposed-pad buck.
    _TH = ("TPS54302 SOT-23-6, no EP: bare 2s2p RthJA 70.6 C/W overstates Tj; "
           "layout-critical (power copper pour + thermal vias -> ~45-55 C/W) — "
           "VERIFY by thermal sim/bench at bring-up else move to an EP buck "
           "(see carrier/research/thermal_bucks.md)")
    c.waive_thermal("U2", _TH)
    # U1 LM61460 (wt/buck re-spec): NO LONGER WAIVED. The thermal gate now
    # CREDITS a conservative pour-aware effective RthJA (30 C/W vs the 58.7 C/W
    # bare JEDEC) on the strength of the datasheet's own poured-board data
    # (DS 7.3: 25 C/W on a 4-layer PCB; PGND1/PGND2 + SW pads soldered to the GND
    # pour, proven by the netlist). U1 PASSES on real margin: Pd 2.60 W,
    # Tj = 50 + 2.60*30 = 128 C < 140 C guard (~12 C margin). The 6 A rating also
    # gives ~2x current margin over the 2.95 A load. Bench Tj at bring-up remains
    # the final arbiter (see thermal.py pour-aware-RthJA docs + carrier/research/
    # thermal_bucks.md), but the gate no longer needs a waiver to pass it.

    return meta.finish(c)            # applies meta["bind"] (if any), returns c
