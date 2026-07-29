"""Every off-board connector gets a short FUNCTION descriptor on the top silk
(PWR / USB OTG / JTAG / UART / HDMI TX-RX / ETH / microSD / QWIIC / CAM / LCD /
PMODn) so the bare board is self-documenting, and its J-ref is hidden so the
label owns the clear spot beside the connector. (schgen.generate.pcb.)
"""

from __future__ import annotations

from schgen.generate import pcb


def _node_field(node, name):
    for sub in node:
        if isinstance(sub, list) and sub and str(sub[0]) == name:
            return sub
    return None


def test_every_offboard_connector_function_label_present(carrier_model):
    m = carrier_model
    labels = pcb._connector_descriptors(m, lambda k: "u", [])
    texts = [str(n[1]) for n in labels]
    # the full set of function labels the user reads on the board (off-board +
    # interior GPIO/JTAG/SWD headers)
    for want in ("PWR", "USB OTG", "JTAG", "UART", "HDMI TX", "HDMI RX",
                 "ETH", "microSD", "QWIIC", "CAM", "LCD",
                 "PMOD0", "PMOD1", "PMOD2", "GPIO", "SWD"):
        assert want in texts, f"missing connector descriptor {want!r}: {texts}"
    # one label per placed off-board connector (known sheet) + interior header
    # + switch (DIP enable / tactile button)
    n_off = sum(1 for i in m.insts
                if i.value in pcb.CONN_MATING_FACE and i.sheet in pcb._CONN_DESC)
    n_int = sum(1 for i in m.insts
                if i.ref in pcb._INT_DESC or i.ref in pcb._SW_DESC)
    assert len(labels) == n_off + n_int, (len(labels), n_off, n_int)


def test_descriptors_on_top_silk_and_on_board(carrier_model):
    m = carrier_model
    ex0, ey0 = pcb.ORIGIN_X, pcb.ORIGIN_Y
    ex1, ey1 = ex0 + m.board_w, ey0 + m.board_h
    for n in pcb._connector_descriptors(m, lambda k: "u", []):
        layer = _node_field(n, "layer")
        assert layer is not None and layer[1] == "F.SilkS", n
        at = _node_field(n, "at")
        assert at is not None
        x, y = float(at[1]), float(at[2])
        assert ex0 <= x <= ex1 and ey0 <= y <= ey1, (n[1], x, y)


def test_offboard_connector_ref_hidden_in_emitted_board(tmp_path, carrier_model):
    """The off-board connector J-refs are HIDDEN on silk (function label replaces
    them); a non-connector IC keeps its visible ref."""
    import re
    m = carrier_model
    pcb.emit_pcb(m, tmp_path / "b.kicad_pcb")
    s = (tmp_path / "b.kicad_pcb").read_text()

    def ref_hidden(ref: str) -> bool:
        i = s.find(f'"{ref}"')
        blk = s[max(0, i - 1400):i + 200]
        mm = re.search(r'\(property\s*\n?\s*"Reference"(.*?)\)\s*\n\s*\(property',
                       blk, re.S)
        return bool(mm and "(hide yes)" in mm.group(1))

    assert ref_hidden("J17001"), "USB-C connector ref must be hidden"
    assert ref_hidden("J23001"), "RJ45 connector ref must be hidden"
    assert ref_hidden("J11001"), "GPIO header ref must be hidden"
    assert not ref_hidden("U17001"), "a non-connector IC ref must stay visible"


# ---- switches (DIP enables + tactile buttons) ----------------------------------

def test_every_switch_gets_a_function_label(carrier_model):
    """EVERY switch on the board (rail/module/5V/boot DIPs + tactile buttons) gets
    a silk function label so a ref shift can't silently drop one (one per ref,
    matched by the deterministic sw-desc:<ref> uuid — degrade-independent)."""
    m = carrier_model
    labels = pcb._connector_descriptors(m, lambda k: k, [])
    uuids = {str(_node_field(n, "uuid")[1]) for n in labels}
    for ref in pcb._SW_DESC:
        assert f"sw-desc:{ref}" in uuids, f"switch {ref} has no silk label"
    assert sum(1 for u in uuids if u.startswith("sw-desc:")) == len(pcb._SW_DESC)


def test_switch_labels_clear_of_courtyards_and_designators(tmp_path, carrier_model):
    """LAW 1: no switch label may sit over any courtyard or any visible designator
    (the reason the interior labels are placed overlap-aware). Checked on the REAL
    emitted board, where the labels dodge the actually-emitted reference texts."""
    from schgen.core import sexpr
    p = tmp_path / "b.kicad_pcb"
    m = carrier_model
    pcb.emit_pcb(m, p)
    doc = sexpr.loads(p.read_text())

    # the emitted board uses hashed uuids, so match switch labels by text — each
    # switch emits EITHER its full legend OR (dense-corner degrade) the short form
    sw_texts = set()
    for v in pcb._SW_DESC.values():
        sw_texts.add(v)
        if ":" in v:
            sw_texts.add(v.split(":", 1)[0].strip())

    sw_labels = []

    def walk(n):
        if isinstance(n, list) and n and str(n[0]) == "gr_text" and \
                isinstance(n[1], str) and n[1] in sw_texts:
            at = _node_field(n, "at")
            sw_labels.append((n[1], float(at[1]), float(at[2]), pcb._font_size(n)))
        if isinstance(n, list):
            for c in n:
                walk(c)
    walk(doc)

    assert len(sw_labels) == len(pcb._SW_DESC), \
        f"expected {len(pcb._SW_DESC)} switch labels, found {len(sw_labels)}"
    courts = [pcb._inst_courtyard(i) for i in m.insts]
    texts = pcb._emitted_text_boxes(doc)
    for txt, x, y, sz in sw_labels:
        box = pcb._text_box(txt, x, y, sz, 0.0)
        assert not any(pcb._rects_overlap(box, c) for c in courts), \
            f"switch label {txt!r} over a courtyard"
        self_box = pcb._text_box(txt, x, y, sz)        # its own entry in `texts`
        others = [tb for tb in texts if tb != self_box]
        assert not any(pcb._rects_overlap(box, o) for o in others), \
            f"switch label {txt!r} over another designator"


def test_switch_ref_hidden_in_emitted_board(tmp_path, carrier_model):
    """The SW ref is hidden on silk (the function label replaces it), like the
    connectors — so a bare board reads MOD/RAIL/BOOT, not SW7002."""
    import re
    m = carrier_model
    pcb.emit_pcb(m, tmp_path / "b.kicad_pcb")
    s = (tmp_path / "b.kicad_pcb").read_text()
    i = s.find('"SW7002"')
    blk = s[max(0, i - 1400):i + 200]
    mm = re.search(r'\(property\s*\n?\s*"Reference"(.*?)\)\s*\n\s*\(property',
                   blk, re.S)
    assert mm and "(hide yes)" in mm.group(1), "module-DIP SW ref must be hidden"
