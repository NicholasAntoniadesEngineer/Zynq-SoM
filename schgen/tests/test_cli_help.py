from __future__ import annotations

import pytest

from schgen import __main__ as m

_SUBCOMMANDS = [
    "board", "bom", "build", "carrier-check", "check", "compose", "design-rules",
    "devicetree", "devkit", "firmware", "floorplan", "gallery", "link", "manifest",
    "manual", "model3d-check", "nets", "part", "part-rules", "pcb", "power-sequence",
    "powertree", "preflight", "ratsnest", "render3d", "scfw", "selftest",
    "som-interface", "spice", "subsystem", "subsystem-check", "testplan", "thermal",
    "vivado", "xdc",
]


@pytest.mark.parametrize("argv", [["--help"], *[[c, "--help"] for c in _SUBCOMMANDS]])
def test_every_subcommand_help_formats_without_a_stray_percent(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        m.main(argv)
    assert exc.value.code == 0, f"`schgen {' '.join(argv)}` did not exit cleanly"
    assert capsys.readouterr().out.strip(), f"`schgen {' '.join(argv)}` printed no help"
