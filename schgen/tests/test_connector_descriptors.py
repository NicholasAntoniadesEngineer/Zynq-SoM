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


def test_every_offboard_connector_function_label_present():
    m = pcb.build_model(True)
    labels = pcb._connector_descriptors(m, lambda k: "u")
    texts = [str(n[1]) for n in labels]
    # the full set of function labels the user reads on the board (off-board +
    # interior GPIO/JTAG/SWD headers)
    for want in ("PWR", "USB OTG", "JTAG", "UART", "HDMI TX", "HDMI RX",
                 "ETH", "microSD", "QWIIC", "CAM", "LCD",
                 "PMOD0", "PMOD1", "PMOD2", "GPIO", "SWD"):
        assert want in texts, f"missing connector descriptor {want!r}: {texts}"
    # one label per placed off-board connector (known sheet) + interior header
    n_off = sum(1 for i in m.insts
                if i.value in pcb.CONN_MATING_FACE and i.sheet in pcb._CONN_DESC)
    n_int = sum(1 for i in m.insts if i.ref in pcb._INT_DESC)
    assert len(labels) == n_off + n_int, (len(labels), n_off, n_int)


def test_descriptors_on_top_silk_and_on_board():
    m = pcb.build_model(True)
    ex0, ey0 = pcb.ORIGIN_X, pcb.ORIGIN_Y
    ex1, ey1 = ex0 + m.board_w, ey0 + m.board_h
    for n in pcb._connector_descriptors(m, lambda k: "u"):
        layer = _node_field(n, "layer")
        assert layer is not None and layer[1] == "F.SilkS", n
        at = _node_field(n, "at")
        assert at is not None
        x, y = float(at[1]), float(at[2])
        assert ex0 <= x <= ex1 and ey0 <= y <= ey1, (n[1], x, y)


def test_offboard_connector_ref_hidden_in_emitted_board(tmp_path):
    """The off-board connector J-refs are HIDDEN on silk (function label replaces
    them); a non-connector IC keeps its visible ref."""
    import re
    m = pcb.build_model(True)
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
