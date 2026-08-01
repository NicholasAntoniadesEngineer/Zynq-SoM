from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CARRIER = REPO_ROOT / "carrier"
DEVKIT = REPO_ROOT / "devkit_mini"
PACKAGE_TOKEN = "PROJECT"

TWINNED = (
    "basis.py",
    "subsystems/pd_input.py",
    "subsystems/power.py",
    "subsystems/uart_bridge.py",
    "subsystems/usb_uart_connector.py",
    "subsystems/debug_boot/debug_boot.py",
    "subsystems/mechanical/mechanical.py",
    "subsystems/power_mon/power_mon.py",
    "subsystems/power_som/power_som.py",
    "subsystems/som_decoupling/som_decoupling.py",
    "subsystems/som_j1/som_j1.py",
    "subsystems/som_j2/som_j2.py",
    "subsystems/som_j3/som_j3.py",
)


def _project_neutral(path: Path) -> str:
    return (path.read_text()
            .replace("carrier.basis", f"{PACKAGE_TOKEN}.basis")
            .replace("devkit_mini.basis", f"{PACKAGE_TOKEN}.basis"))


@pytest.mark.parametrize("rel", TWINNED)
def test_twinned_module_has_not_drifted(rel: str) -> None:
    carrier, devkit = CARRIER / rel, DEVKIT / rel
    assert carrier.is_file(), f"{carrier} missing"
    assert devkit.is_file(), f"{devkit} missing"
    assert _project_neutral(carrier) == _project_neutral(devkit), (
        f"{rel} differs between carrier/ and devkit_mini/ — these files are "
        f"verbatim copies, so a change to one must be applied to the other. "
        f"Deduplicating them is the real fix; until then this gate is what "
        f"makes the drift loud."
    )
