from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CARRIER = REPO_ROOT / "carrier"
DEVKIT = REPO_ROOT / "devkit_mini"
PACKAGE_TOKEN = "PROJECT"

TWINNED = (
    "basis.py",
    "subsystems/pd_input.py",
    "subsystems/uart_bridge.py",
    "subsystems/usb_uart_connector.py",
    "subsystems/mechanical/mechanical.py",
    "subsystems/power_som/power_som.py",
    "subsystems/som_decoupling/som_decoupling.py",
    "subsystems/som_j1/som_j1.py",
    "subsystems/som_j2/som_j2.py",
    "subsystems/som_j3/som_j3.py",
)

# These are deliberately different board designs, not verbatim source twins.
# Their complete outputs are checked against independent pre-migration Python
# fixtures below; do not erase the differences or normalize circuit contents.
VARIANTS = (
    "subsystems/power.py",  # devkit's three rail-enable probe pads
    "subsystems/debug_boot/debug_boot.py",  # devkit's I2C pulls + SD/OTG probes
    "subsystems/power_mon/power_mon.py",  # devkit's SC supply + I2C probe pads
)


def _project_neutral(path: Path) -> str:
    return (path.read_text()
            .replace("carrier.basis", f"{PACKAGE_TOKEN}.basis")
            .replace("devkit_mini.basis", f"{PACKAGE_TOKEN}.basis"))


def _expected_circuit(project: str, name: str) -> dict:
    fixture = json.loads(
        (REPO_ROOT / "native/tests/data/authoring" /
         f"gate_{project}.json").read_text())
    return next(row["circuit"] for row in fixture["packages"]
                if row["name"] == name)


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


@pytest.mark.parametrize("project", ("carrier", "devkit_mini"))
@pytest.mark.parametrize("rel", TWINNED[1:] + VARIANTS)
def test_twinned_or_variant_circuit_preserves_independent_python_ir(
        project: str, rel: str) -> None:
    name = Path(rel).stem
    module = importlib.import_module(
        f"{project}." + rel.removesuffix(".py").replace("/", "."))
    assert module.circuit().to_ir() == _expected_circuit(project, name)


@pytest.mark.parametrize("project", ("carrier", "devkit_mini"))
def test_native_project_selection_comes_from_own_basis_location(project: str) -> None:
    module = importlib.import_module(f"{project}.basis")
    assert module.PROJECT == Path(module.__file__).resolve().parent.name == project


@pytest.mark.parametrize("project", ("carrier", "devkit_mini"))
def test_detached_adapter_retains_owner_without_project_path(
        project: str, tmp_path: Path) -> None:
    # Structure gates import flat temporary copies with no package ancestry.
    # The original basis module still identifies the owning native project.
    # Power is deliberately different, so using the wrong project cannot pass.
    source = tmp_path / "power.py"
    source.write_text((REPO_ROOT / project / "subsystems/power.py").read_text())
    spec = importlib.util.spec_from_file_location("detached_power", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.circuit().to_ir() == _expected_circuit(project, "power")
