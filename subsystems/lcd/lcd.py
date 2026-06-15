"""lcd — 40-pin TTL RGB888 panel + SY7201 backlight boost + touch I2C (LIBRARY).

PROJECT-AGNOSTIC, REUSABLE subsystem (the ``subsystems/<name>/`` library layout;
exemplar: ``subsystems/usb_pd/``). A self-contained package — netlist + README +
SPICE subckt + local test — that declares its interface as ABSTRACT port + rail
names and knows NOTHING about any consuming board (no carrier net names, no
``carrier/nets.py`` / ``som_interface.json`` reads). A project consumes it by
calling :func:`circuit` with the STANDARD ``meta`` dict (see
:mod:`schgen.core.subsystem`): ``bind`` rebinds every externally-visible net to
its real board name, ``expects`` adds per-port linker deferrals, ``buses``
renames the touch-I2C bus group, ``notes`` restores house-style prose.
Standalone (``meta=None``) it keeps the abstract names so this package's
``test_lcd.py`` runs offline.

The reference design is a de-facto 40-pin 0.5 mm TTL RGB888 FFC (Innolux
AT043TN24-lineage pinout; HAOYU HY7-LCD / Adafruit #2353 7" 800x480 class) on the
JUSHUO AFC07-S40FCA-00 connector, with capacitive-touch I2C re-using FFC pins
37-40. The backlight is an on-board Silergy SY7201ABC boost WLED driver
(SWPA4030 10uH inductor, SS34 catch diode) at a 133 mA LED-string current
(I = 0.2 V / R_ISET, R_ISET = 1.5R), PWM-dimmable on EN. The user-touchable touch
I2C pair is clamped at the connector by a USBLC6-2SC6 low-cap ESD array.

ABSTRACT INTERFACE (see README.md for the full table) — the names a project
binds:

  rails (POWER/GROUND):
    +VBOOST_IN   the boost-converter input rail (5 V class) feeding the SY7201
                 IN pin, L1 and the input bulk. A project supplies a GATED rail
                 here so the backlight boost is fully off when the module is
                 powered down. 10u + 2.2u(/50V) live around the boost.
    +VDD_LCD     the panel logic + touch rail (3.3 V class). A project supplies a
                 GATED rail here so a powered-down panel is not back-fed through
                 its DISP / touch pull-ups; the panel VDD bypass (10u + 100n)
                 and the touch / DISP pulls land on this rail.
    +VDD_TP_CLAMP  the ALWAYS-ON rail referencing the touch-I2C ESD clamp
                 (USBLC6 VBUS). Kept separate from +VDD_LCD so the ESD
                 protection is valid even when the gated panel rail is off.
    GND          ground (FFC grounds + boost/ISET return + clamp ref).
  ports (PORT):
    LCD_R0..R7, LCD_G0..G7, LCD_B0..B7   the 24-bit TTL RGB888 data bus.
    LCD_PCLK     pixel clock (~33 MHz), through a 22R source-series damping R7.
    LCD_HSYNC, LCD_VSYNC, LCD_DE   timing/sync.
    LCD_DISP     display on/off (10k pull-up to +VDD_LCD -> default ON).
    BL_PWM       SY7201 EN/PWM backlight enable (100k pull-down -> default OFF).
    TP_SDA, TP_SCL   the capacitive-touch I2C bus (open-drain; 4k7 pull-ups to
                 +VDD_LCD here), brought through the USBLC6 ESD array.
    TP_RST       touch-controller reset (100k pull-down -> held in reset until
                 the host releases it). Driven reset, not an RC reset.
    TP_INT       touch interrupt (no pull — GT911-class address-select at reset
                 release; FT5206-class plain output).

DESIGN NOTES (datasheet + reference-design contract): see README.md
"Design notes" — incl. LCD-1 (the 2.2uF/50V X7R boost output cap vs the open-LED
OVP clamp) and the touch-I2C ESD/pull-up housekeeping.

Stock FFC + SY7201 + USBLC6 + inductor symbols/footprints + MPN/LCSC come from
the global ``parts/`` library entries; the FFC connector's bare-number pins stay
numeric. The netlist gate proves KiCad sees every FFC pad.
"""

from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

# ---- the abstract interface (the REUSE contract) ------------------------------
# Externally-visible net names a consuming project binds. RAILS classify as
# POWER/GROUND by name (the '+' prefix + GND), exactly as the bound carrier rails
# do, so a standalone build and a bound build share net classes.
RAILS = ("+VBOOST_IN", "+VDD_LCD", "+VDD_TP_CLAMP", "GND")
PORTS = (
    "LCD_R0", "LCD_R1", "LCD_R2", "LCD_R3", "LCD_R4", "LCD_R5", "LCD_R6", "LCD_R7",
    "LCD_G0", "LCD_G1", "LCD_G2", "LCD_G3", "LCD_G4", "LCD_G5", "LCD_G6", "LCD_G7",
    "LCD_B0", "LCD_B1", "LCD_B2", "LCD_B3", "LCD_B4", "LCD_B5", "LCD_B6", "LCD_B7",
    "LCD_DISP", "LCD_HSYNC", "LCD_VSYNC", "LCD_DE",
    "TP_SDA", "TP_SCL", "TP_RST", "TP_INT",
    "LCD_PCLK", "BL_PWM",
)
INTERFACE = RAILS + PORTS

# The capacitive-touch I2C bus this port group sits on (400 kHz). The bus NAME is
# a project-level grouping (the linker groups SDA/SCL by it) and may be overridden
# via meta["buses"]["i2c"] so a consuming board can place this touch port on one
# of its named buses; the default is the abstract name for standalone use.
I2C_BUS = "LCD_CTP"
I2C_SPEED_HZ = 400_000

# Default power-tree draw notes (a project may override the prose via
# meta["notes"][...] to cite its own dossier wording).
DRAWS_LCD_NOTE = "panel logic 25-75 mA + touch <= 25 mA"
DRAWS_LCD_A = 0.100
DRAWS_BOOST_NOTE = "SY7201 boost input @133 mA LED string (operating point + margin)"
DRAWS_BOOST_A = 0.450


def circuit(meta: "Meta | dict | None" = None) -> Circuit:
    """Build the lcd subsystem netlist with ABSTRACT port/rail names.

    ``meta`` is the STANDARD subsystem adapter contract (see
    :mod:`schgen.core.subsystem`) — a single dict a consuming project's adapter
    declares. Keys this subsystem reads (all optional; ``meta=None`` ->
    standalone abstract names for the local test):

      ``bind``    ``{abstract_name: project_net}`` rebinds the externally-visible
                  nets (the :data:`INTERFACE` names) to a project's real board
                  names. Applied last (order-preserving => byte-identical sheet).
      ``expects`` ``{abstract_port: deferral}`` attaches an EXPLICIT linker
                  deferral to a port — a project declares which of its sheets
                  will bind a deferred port (e.g. the generated SoM-connector
                  sheet for the RGB/sync lines and the touch control).
      ``buses``   ``{"i2c": name}`` the touch-I2C bus-group NAME for SDA/SCL (a
                  project-level grouping; defaults to the abstract :data:`I2C_BUS`).
      ``notes``   ``{"draws_lcd": prose, "draws_boost": prose}`` the power-tree
                  draw-note prose for each gated rail (a project may cite its own
                  dossier wording; defaults to :data:`DRAWS_LCD_NOTE` /
                  :data:`DRAWS_BOOST_NOTE`).

    ``buses`` / ``notes`` let a project reproduce its own house-style metadata
    (bus name, dossier prose) WITHOUT the library knowing any board specifics —
    keeping the library project-agnostic while a consumer's derived artifacts
    (constraints CSV, power-tree note) stay byte-stable.
    """
    meta = Meta(meta)
    i2c_bus = meta.bus("i2c", I2C_BUS)
    draws_lcd_note = meta.note("draws_lcd", DRAWS_LCD_NOTE)
    draws_boost_note = meta.note("draws_boost", DRAWS_BOOST_NOTE)
    c = Circuit("lcd", "40-pin TTL RGB LCD + SY7201 backlight boost")
    c.use_part("AFC07-S40FCA-00", ref="J1")    # bare-number FFC pins
    c.use_part("SY7201ABC", ref="U1")
    c.use_part("SWPA4030S100MT", ref="L1", value="10uH")
    c.part("D1", "Device:D_Schottky", "SS34", "Diode_SMD:D_SMA", LCSC="C8678")
    c.part("R1", "Device:R", "1.5R", R0603, LCSC="C22769")   # ISET 133mA
    c.part("C1", "Device:C", "10u", C0805, LCSC="C15850")    # boost in
    c.part("C2", "Device:C", "2.2u", C0805, LCSC="C125847")  # boost out 50V (LCD-1)
    c.part("C3", "Device:C", "100n", C0603, LCSC="C14663")    # panel VDD

    # ---- panel data: 24 RGB + syncs ----------------------------------------
    for base, names in ((5, [f"LCD_R{i}" for i in range(8)]),
                        (13, [f"LCD_G{i}" for i in range(8)]),
                        (21, [f"LCD_B{i}" for i in range(8)])):
        for off, net in enumerate(names):
            c.port(net, f"J1.{base + off}", **meta.expect_kw(net))
    for pin, net in ((31, "LCD_DISP"), (32, "LCD_HSYNC"),
                     (33, "LCD_VSYNC"), (34, "LCD_DE")):
        c.port(net, f"J1.{pin}", **meta.expect_kw(net))
    # capacitive touch on the same FFC tail. The FFC is user-touchable, so the
    # touch-I2C pair is clamped at the connector by a USBLC6-2SC6 (the board's
    # standard low-cap ESD array; 1<->6 / 3<->4 passthrough). The external FFC
    # pins land on U2.1/U2.3; the protected pair (-> the pull-ups + the host) on
    # U2.6/U2.4; clamp ref the ALWAYS-ON +VDD_TP_CLAMP, so protection is valid
    # even when the gated +VDD_LCD panel rail is off.
    c.use_part("USBLC6-2SC6", ref="U2")
    c.net("CTP_SDA_FFC", "J1.37", "U2.1")
    c.net("CTP_SCL_FFC", "J1.38", "U2.3")
    c.port("TP_SDA", "U2.6", kind="i2c", role="sda",
           bus=i2c_bus, speed_hz=I2C_SPEED_HZ, **meta.expect_kw("TP_SDA"))
    c.port("TP_SCL", "U2.4", kind="i2c", role="scl",
           bus=i2c_bus, speed_hz=I2C_SPEED_HZ, **meta.expect_kw("TP_SCL"))
    c.net("+VDD_TP_CLAMP", "U2.5")
    c.net("GND", "U2.2")
    c.port("TP_RST", "J1.39", **meta.expect_kw("TP_RST"))
    c.port("TP_INT", "J1.40", **meta.expect_kw("TP_INT"))

    # ---- housekeeping passives (lcd_backlight.md 3.1/3.2/4) ----------------
    # Touch I2C is open-drain -> REQUIRES pull-ups (bus is dead without them).
    c.part("R2", "Device:R", "4k7", R0603, LCSC="C23162")
    c.net("TP_SDA", "R2.1")
    c.net("+VDD_LCD", "R2.2")
    c.part("R3", "Device:R", "4k7", R0603, LCSC="C23162")
    c.net("TP_SCL", "R3.1")
    c.net("+VDD_LCD", "R3.2")
    # touch controller held in reset until the host releases it
    c.part("R5", "Device:R", "100k", R0603, LCSC="C25803")
    c.net("TP_RST", "R5.1")
    c.net("GND", "R5.2")
    # panel display-enable defaults ON when the gated rail is up
    c.part("R6", "Device:R", "10k", R0603, LCSC="C25804")
    c.net("LCD_DISP", "R6.1")
    c.net("+VDD_LCD", "R6.2")
    # pixel-clock source-series damping (~33 MHz, the highest-edge-rate line):
    # host-side port -> 22R -> FFC pin 30 (resistor at the source/host end)
    c.part("R7", "Device:R", "22R", R0603, LCSC="C23345")
    c.net("LCD_PCLK_PANEL", "J1.30", "R7.1")
    c.port("LCD_PCLK", "R7.2", **meta.expect_kw("LCD_PCLK"))

    # ---- panel power (gated module rails) ----------------------------------
    c.net("+VDD_LCD", "J1.4", "C3.1")
    c.net("GND", "J1.3", "J1.29", "J1.36", "C3.2")
    c.nc("J1.35", "J1.41", "J1.42")        # NC + shell tabs unused
    # bulk on the gated +VDD_LCD logic rail (lcd_backlight.md 3.1: "10uF + 100n"
    # on panel VDD; only the 100n was present — peers camera/microsd carry 10u)
    bulk = c.part(c.auto_ref("C"), "Device:C", "10u", C0805, LCSC="C15850")
    c.net("+VDD_LCD", f"{bulk.ref}.1")
    c.net("GND", f"{bulk.ref}.2")

    # ---- backlight boost: +VBOOST_IN -> L1 -> LX, D1 -> VLED+, ISET return --
    c.net("+VBOOST_IN", "U1.IN", "L1.1", "C1.1")
    c.net("GND", "U1.GND", "C1.2", "C2.2", "R1.2")
    c.net("LCD_BL_SW", "L1.2", "U1.LX")                      # LX node
    c.net("LCD_VLED_P", "D1.2", "C2.1", "U1.OVP", "J1.2")    # boost out + OVP
    c.net("LCD_BL_SW", "D1.1")
    c.net("LCD_VLED_N", "J1.1", "R1.1", "U1.FB")             # current sense
    c.port("BL_PWM", "U1.EN/PWM", **meta.expect_kw("BL_PWM"))
    # backlight EN/PWM defaults OFF (boost off until the host drives it high)
    c.part("R4", "Device:R", "100k", R0603, LCSC="C25803")
    c.net("BL_PWM", "R4.1")
    c.net("GND", "R4.2")

    # coverage gate: the gated boost feed rail + the touch I2C bus this sheet owns
    c.testpoint("+VBOOST_IN")
    c.testpoint("TP_SDA")
    c.testpoint("TP_SCL")

    # power-tree budget: panel logic + touch <= 100 mA; boost input at 133 mA
    # LED current ~= 0.30 A plus margin -> 0.45 A
    c.draws("+VDD_LCD", DRAWS_LCD_A, draws_lcd_note)
    c.draws("+VBOOST_IN", DRAWS_BOOST_A, draws_boost_note)
    # design-rule waiver: TP_RST is GPIO-driven by the host and held in reset by
    # R5 (100k pull-down) until released — a driven reset, not an RC reset, so no
    # cap-to-GND by design.
    c.waive_reset("TP_RST",
                  "GPIO-driven reset, held by 100k pull-down until PL releases")
    # part-rule waiver (CAP_VOLTAGE): C2 (2.2uF/50V X7R) on LCD_VLED_P now that
    # the boost output node resolves to its 30 V open-LED OVP clamp. The 2x MLCC
    # derate wants 60 V, but 30 V is a RARE open-LED fault TRANSIENT, not a
    # continuous bias — the continuous string voltage is ~9.6 V (50 V/2 = 25 V
    # derated >> 9.6 V). The 50 V/X7R part is dossier-sized for the transient.
    c.waive_part_rule("C2", "MLCC 50V on LCD_VLED_P: the 30V is the rare open-LED "
                      "OVP-clamp transient, not continuous (string ~9.6V); 50V/X7R "
                      "dossier-sized for it (lcd_backlight.md). 2x derate targets "
                      "continuous DC bias, not a fault clamp")
    return meta.finish(c)            # applies meta["bind"] (if any), returns c
