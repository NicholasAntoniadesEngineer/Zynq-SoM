"""CLI parser guard — every subcommand's ``--help`` must build and render.

A literal ``%`` (or other stray printf char) in an argparse ``help=`` string raises
``ValueError: badly formed help string`` at PARSER-CONSTRUCTION time, which crashes
EVERY ``python -m schgen ...`` invocation, not just ``--help`` (argparse validates
help strings when the parser is assembled). It happened once — a ``~15%`` in the
``board --no-render`` help bricked the whole CLI. ruff cannot see it (it is a
runtime error), so THIS is the guard.

Fast + hermetic: pure argparse assembly + help formatting, no kicad-cli, no board
build, no file I/O. ``main([..., "--help"])`` builds the whole parser and formats
the requested help, then argparse raises ``SystemExit(0)``.
"""
from __future__ import annotations

import pytest

from schgen import __main__ as m

# Every registered subcommand (keep in sync with main()'s sub.add_parser calls).
# The top-level ``--help`` case already builds every subparser, so a NEW subcommand
# with a bad help string is caught even before it is added here; the per-subcommand
# rows add explicit coverage of each one's own help-format path.
_SUBCOMMANDS = [
    "board", "bom", "build", "carrier-check", "check", "compose", "design-rules",
    "devicetree", "devkit", "firmware", "floorplan", "gallery", "link", "manifest",
    "manual", "model3d-check", "nets", "part", "part-rules", "pcb", "power-sequence",
    "powertree", "preflight", "ratsnest", "render3d", "scfw", "selftest",
    "som-interface", "spice", "subsystem", "subsystem-check", "testplan", "thermal",
    "vivado", "xdc",
]


@pytest.mark.parametrize("argv", [["--help"], *[[c, "--help"] for c in _SUBCOMMANDS]])
def test_cli_help_builds_and_renders(argv, capsys):
    """``schgen <argv>`` assembles the parser and formats the help without a
    'badly formed help string' (stray %) or any other construction error, then
    exits 0. Any bad ``help=`` string in ANY subcommand fails HERE, not in a
    user's build."""
    with pytest.raises(SystemExit) as exc:
        m.main(argv)
    assert exc.value.code == 0, f"`schgen {' '.join(argv)}` did not exit cleanly"
    # argparse prints the usage/help to stdout — a non-empty body proves it rendered.
    assert capsys.readouterr().out.strip(), f"`schgen {' '.join(argv)}` printed no help"
