"""End-to-end REUSE proof for the devkit_mini example consumer.

Proves — OFFLINE, no kicad-cli, no network, no board — that the project-agnostic
``subsystems/<name>/`` library packages port to a SECOND board (this devkit) with
ZERO changes to the library, exactly as the real ``carrier/`` consumes them. The
only project-specific surface is the ``META`` dict each adapter in
``examples/devkit_mini/devkit_mini.py`` declares (the STANDARD
``schgen.core.subsystem.Meta`` contract).

What this asserts (per subsystem unless noted):
  * each library subsystem BUILDS under the devkit bind (no library edit);
  * the devkit's REAL net names appear and the library's ABSTRACT names do NOT
    leak (and neither do the carrier's names — it is a genuine re-bind);
  * the bind CONTRACT is honored — rejects an unknown name, a SIGNAL net, and a
    collision (two externals onto one net);
  * the LOCAL gate slices pass on every bound circuit: design_rules DECAP/EP/STRAP,
    part_rules, and model completeness (no silent float);
  * the bind is BYTE-STABLE — pure order-preserving rename (parts/refs/NCs and net
    insertion order unchanged vs the standalone abstract build);
  * CROSS-SUBSYSTEM COMPOSITION — the common +3V3_MINI logic rail and GND are the
    SAME net across all four bound subsystems (the cells compose into one board);
  * LIBRARY UNCHANGED — binding the SAME library package to the CARRIER's names vs
    the DEVKIT's names yields the carrier vs devkit net sets respectively, from one
    untouched ``circuit()``.
"""

from __future__ import annotations

import types

import pytest

from schgen.core.model import Circuit, CircuitError, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules

# the real library packages (imported directly — this test consumes the library)
from subsystems.usb_pd import usb_pd as lib_usb_pd
from subsystems.usbc_otg import usbc_otg as lib_usbc_otg
from subsystems.microsd import microsd as lib_microsd
from subsystems.uart_bridge import uart_bridge as lib_uart_bridge

# the devkit consumer under test
from examples.devkit_mini import devkit_mini as dk


# ---- fixtures / helpers ---------------------------------------------------------

@pytest.fixture(scope="module")
def lib() -> Library:
    return Library()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def _externals(c: Circuit) -> set[str]:
    return {n.name for n in c.nets.values() if n.net_class is not NetClass.SIGNAL}


# Each subsystem under test: (name, library module, devkit adapter builder, META).
# Iterating PROJECT here ties the test to the project's declared bill-of-subsystems.
_CASES = [
    ("usb_pd", lib_usb_pd, dk.usb_pd_circuit, dk.USB_PD_META),
    ("usbc_otg", lib_usbc_otg, dk.usbc_otg_circuit, dk.USBC_OTG_META),
    ("microsd", lib_microsd, dk.microsd_circuit, dk.MICROSD_META),
    ("uart_bridge", lib_uart_bridge, dk.uart_bridge_circuit, dk.UART_BRIDGE_META),
]
_IDS = [c[0] for c in _CASES]

# Names that must NEVER appear on a devkit external net: the carrier's real net
# names (proves it's a re-bind, not a copy of the carrier) + a couple of bus stems.
_CARRIER_NAMES = {
    "+3V3_SC", "+3V3", "+3V3_SD", "+5V_USB", "+1V8", "+VBUS_IN",
    "USB_D+", "USB_D-", "SC_INT_N", "VBUS_OUT_EN", "USBOTG_FLT_N",
    "SD_CARD_DETECT", "USB_UART_VBUS", "USB_UART_DP", "USB_UART_DM",
}
_CARRIER_PREFIXES = ("STM32", "SDIO_", "ZYNQ_PS")


def test_all_project_subsystems_are_covered():
    """The test iterates exactly the project's declared bill-of-subsystems."""
    assert [name for name, _ in dk.PROJECT] == _IDS


# ---- each subsystem builds under the devkit bind --------------------------------

@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_subsystem_builds_under_devkit_bind(name, libmod, build, meta):
    """The library subsystem builds when consumed with the devkit META (the only
    thing the project supplies — the library file is untouched)."""
    c = build()
    assert isinstance(c, Circuit)
    assert c.name == name
    assert c.parts, "subsystem produced no parts"


@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_devkit_names_present_no_abstract_or_carrier_leak(name, libmod, build, meta):
    """Every bound external is the devkit's REAL net name; the library's ABSTRACT
    interface names do NOT leak, and neither do the carrier's names."""
    bind = meta["bind"]
    ext = _externals(build())
    # the project's chosen real names are exactly the bind-map targets
    assert ext == set(bind.values()), (name, ext, set(bind.values()))
    # not a single abstract interface name survives (all were bound)
    abstract = set(libmod.INTERFACE)
    leaked_abstract = {a for a in abstract if a in ext and bind.get(a) == a}
    # only an identity-bound name (e.g. GND, CHASSIS_GND) may equal its abstract
    # name; every non-identity abstract name must be gone
    nonidentity_abstract = {a for a in abstract if bind.get(a) != a}
    assert not (ext & nonidentity_abstract), (name, ext & nonidentity_abstract)
    # not a carrier net name in sight (this is a re-bind, not a carrier copy)
    assert not (ext & _CARRIER_NAMES), (name, ext & _CARRIER_NAMES)
    assert not any(e.startswith(_CARRIER_PREFIXES) for e in ext), (name, ext)
    _ = leaked_abstract  # identity-bound abstract names (GND) are allowed


@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_rail_and_port_net_classes_preserved(name, libmod, build, meta):
    """Binding is a pure rename: every bound rail still classifies POWER/GROUND and
    every bound port still classifies PORT (the devkit names were chosen to keep
    the net class — e.g. '+'-prefixed rails)."""
    c = build()
    bind = meta["bind"]
    cls = {n.name: n.net_class for n in c.nets.values()}
    for abstract in libmod.RAILS:
        real = bind[abstract]
        want = NetClass.GROUND if abstract in ("GND", "CHASSIS_GND") else NetClass.POWER
        assert cls[real] is want, (name, abstract, real, cls[real])
    for abstract in libmod.PORTS:
        real = bind[abstract]
        assert cls[real] is NetClass.PORT, (name, abstract, real, cls[real])


# ---- the bind contract (the reuse API guardrails) -------------------------------

@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_bind_rejects_unknown_name(name, libmod, build, meta):
    c = libmod.circuit()
    with pytest.raises(CircuitError, match="not a net"):
        c.bind({"NOT_A_REAL_PORT": "+3V3_MINI"})


@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_bind_rejects_signal_net(name, libmod, build, meta):
    """A private SIGNAL net is never bindable (binding internal wiring is a hard
    error). Synthesize a real 2-pin internal net to exercise the guard uniformly."""
    c2 = Circuit("t", "t")
    c2.part("R1", "Device:R", "1k", "")
    c2.part("R2", "Device:R", "1k", "")
    c2.net("PRIVATE_MID", "R1.2", "R2.1")
    assert c2.nets["PRIVATE_MID"].net_class is NetClass.SIGNAL
    with pytest.raises(CircuitError, match="SIGNAL"):
        c2.bind({"PRIVATE_MID": "SOMETHING"})


@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_bind_rejects_collision(name, libmod, build, meta):
    """Two distinct externals may not bind onto one net (a LAW-0 silent short).
    Pick the subsystem's first two PORTS and try to merge them."""
    c = libmod.circuit()
    p1, p2 = libmod.PORTS[0], libmod.PORTS[1]
    with pytest.raises(CircuitError, match="cannot merge|collides|short"):
        c.bind({p1: "SHARED_BAD", p2: "SHARED_BAD"})


def test_meta_rejects_unknown_top_level_key():
    """A typo'd top-level meta key is a hard error (never silently dropped)."""
    with pytest.raises(CircuitError, match="unknown subsystem meta key"):
        lib_usb_pd.circuit({"binds": dk.USB_PD_META["bind"]})  # 'binds' != 'bind'


# ---- LOCAL gate slices on each bound subsystem ----------------------------------

@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_bound_subsystem_passes_local_design_rules(name, libmod, build, meta, lib):
    """design_rules DECAP/EP/STRAP slice passes on the bound circuit (binding is a
    pure rename; electrical completeness is unchanged from the abstract build).
    The I2C/RESET slices are board-level (shared pull-ups live off-subsystem) and
    are not asserted here."""
    r = design_rules.check([_sheet(build())], lib)
    assert not r.decap, (name, r.decap)
    assert not r.ep, (name, r.ep)
    assert not r.strap, (name, r.strap)
    # NB the decap rule examines only IC supply pins; usbc_otg's TPS2051C IN is a
    # switch input (not a decap-rule supply pin), so it legitimately checks 0 — the
    # rule actually-ran assertion is made at the project aggregate level instead
    # (test_project_aggregate_exercises_decap_rule), not per subsystem.


def test_project_aggregate_exercises_decap_rule(lib):
    """Across the whole project the DECAP rule is genuinely exercised (it is not a
    silent no-op): the four bound subsystems together present at least one IC
    supply pin to the rule, with zero findings."""
    sheets = [_sheet(c) for _, c in dk.subsystem_circuits()]
    r = design_rules.check(sheets, lib)
    assert not (r.decap or r.ep or r.strap), r.findings
    assert r.checked.get("decap", 0) >= 1, r.checked


@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_bound_subsystem_passes_part_rules(name, libmod, build, meta, tmp_path):
    """The per-part rating engine raises no HARD finding on the bound circuit
    (caps read as 'rail unresolved' on a standalone subsystem — fail-soft — which
    is acceptable for a single cell with no board power tree)."""
    r = part_rules.run([_sheet(build())], tmp_path)
    assert r.ok, (name, r.findings)


@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_bound_subsystem_model_is_complete(name, libmod, build, meta, lib):
    """Model completeness: every physical pin of every part is netted or NC — the
    same hard check the board build runs (LAW 0: no silent floats)."""
    c = build()
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})


# ---- byte-stability: bind is a pure order-preserving rename ---------------------

@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_bind_is_byte_stable_rename(name, libmod, build, meta):
    """The devkit bind renames externals ONLY and preserves everything else: same
    parts/refs/NCs, and the nets dict keeps its insertion order (byte-identical
    emit) — the standalone abstract net order maps 1:1 onto the bound order."""
    base = libmod.circuit()            # standalone, abstract names
    bound = build()                    # devkit-bound
    bind = meta["bind"]
    # same parts, refs and no-connects
    assert set(bound.parts) == set(base.parts), name
    assert {str(p) for p in bound.nc_pins} == {str(p) for p in base.nc_pins}, name
    # net insertion order preserved: each base net maps to its bound name in place
    expected_order = [bind.get(n, n) for n in base.nets]
    assert list(bound.nets) == expected_order, name


@pytest.mark.parametrize("name,libmod,build,meta", _CASES, ids=_IDS)
def test_draw_budget_follows_renamed_rail(name, libmod, build, meta):
    """Every power-tree draw budget moved onto the renamed real rail (no budget
    is left stranded on an abstract rail name)."""
    bound = build()
    bind = meta["bind"]
    for rail in bound.loads:
        assert rail in bind.values(), (name, rail)
        # the abstract source name must be gone from the load table
    abstract_power = {a for a in libmod.RAILS if bind.get(a, a) != a}
    assert not (set(bound.loads) & abstract_power), (name, bound.loads.keys())


# ---- CROSS-SUBSYSTEM COMPOSITION ------------------------------------------------

def test_shared_logic_rail_and_gnd_are_one_net_across_subsystems():
    """The composition proof: the common +3V3_MINI logic rail and GND appear, as
    the SAME (identically-named, same-class) net, in MORE THAN ONE bound subsystem
    — so the four library cells compose into a single board sharing those rails."""
    circs = dk.subsystem_circuits()
    assert {n for n, _ in circs} == set(_IDS)
    where: dict[str, list[str]] = {r: [] for r in dk.SHARED_RAILS}
    klass: dict[str, set] = {r: set() for r in dk.SHARED_RAILS}
    for name, c in circs:
        for rail in dk.SHARED_RAILS:
            net = c.nets.get(rail)
            if net is not None:
                where[rail].append(name)
                klass[rail].add(net.net_class)
    # the shared logic rail is in EVERY subsystem; GND is in every subsystem
    for rail in dk.SHARED_RAILS:
        assert len(where[rail]) >= 2, (rail, where[rail])
        # and it is the SAME net class everywhere (POWER for the rail, GROUND for GND)
        assert len(klass[rail]) == 1, (rail, klass[rail])
    assert set(where[dk.V3V3]) == set(_IDS), where[dk.V3V3]   # logic rail truly shared by all 4
    assert NetClass.POWER in klass[dk.V3V3]
    assert NetClass.GROUND in klass["GND"]


def test_no_devkit_net_collides_across_subsystems_by_accident():
    """Every external net shared between two subsystems is an INTENTIONAL shared
    rail/bus, never an accidental name clash of two private signals. (All
    cross-subsystem shared externals are POWER/GROUND/PORT, never SIGNAL — SIGNAL
    nets stayed library-private under the bind.)"""
    circs = dk.subsystem_circuits()
    owners: dict[str, list[str]] = {}
    for name, c in circs:
        for nm, net in c.nets.items():
            if net.net_class is not NetClass.SIGNAL:
                owners.setdefault(nm, []).append(name)
    shared = {nm: who for nm, who in owners.items() if len(who) > 1}
    # the only nets shared across subsystems are the declared shared rails
    assert set(shared) == set(dk.SHARED_RAILS), shared


# ---- LIBRARY UNCHANGED: carrier vs devkit from ONE circuit() --------------------

def test_same_library_binds_to_carrier_or_devkit_from_one_source():
    """The library package is unchanged: binding the SAME ``usb_pd.circuit()`` to
    the CARRIER's names vs the DEVKIT's names yields the carrier vs devkit net sets
    respectively. One untouched library file; two boards; two disjoint net sets."""
    # the carrier's authoritative usb_pd bind (mirrors carrier/subsystems/usb_pd.py)
    carrier_bind = {
        "+VDD_LOGIC": "+3V3_SC", "+VBUS_SENSE": "+VBUS_IN", "GND": "GND",
        "CC1": "STM32_USB_CC1", "CC2": "STM32_USB_CC2",
        "I2C_SDA": "STM32_I2C2_SDA", "I2C_SCL": "STM32_I2C2_SCL",
        "INT_N": "SC_INT_N",
    }
    devkit_bind = dk.USB_PD_META["bind"]

    carrier_c = lib_usb_pd.circuit({"bind": carrier_bind})
    devkit_c = lib_usb_pd.circuit({"bind": devkit_bind})

    carrier_ext = _externals(carrier_c)
    devkit_ext = _externals(devkit_c)

    # each board's externals are EXACTLY that board's chosen real names
    assert carrier_ext == set(carrier_bind.values())
    assert devkit_ext == set(devkit_bind.values())
    # the two boards' net sets diverge on everything except the universally-shared
    # identity nets (GND is the one net both boards agree on)
    assert carrier_ext & devkit_ext == {"GND"}
    # the abstract names survive on NEITHER board (both fully bound their interface)
    abstract = set(lib_usb_pd.INTERFACE) - {"GND"}
    assert not (carrier_ext & abstract)
    assert not (devkit_ext & abstract)
    # and the topology is identical (pure rename): same parts/refs on both
    assert set(carrier_c.parts) == set(devkit_c.parts)
    assert list(carrier_c.parts) == list(devkit_c.parts)


def test_devkit_uart_crossover_lives_in_the_bind_not_the_library():
    """The UART bridge<->host null-modem crossover is a PROJECT decision: the
    library brings UART out bridge-relative, and the devkit's bind maps bridge TXD
    -> host RXD (FPGA_UART0_RXD), exactly as the carrier maps it to its own host
    name. Proves host-side wiring is in the consumer, not the library."""
    bind = dk.UART_BRIDGE_META["bind"]
    # bridge TXD output crosses to the host RXD net, and vice versa
    assert bind["UART_TXD"] == "FPGA_UART0_RXD"
    assert bind["UART_RXD"] == "FPGA_UART0_TXD"
    assert bind["UART_RTS_N"] == "FPGA_UART0_CTS_N"
    assert bind["UART_CTS_N"] == "FPGA_UART0_RTS_N"
    ext = _externals(dk.uart_bridge_circuit())
    assert {"FPGA_UART0_RXD", "FPGA_UART0_TXD",
            "FPGA_UART0_CTS_N", "FPGA_UART0_RTS_N"} <= ext
