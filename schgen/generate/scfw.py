from __future__ import annotations

import argparse
from pathlib import Path
from schgen.core import native
from schgen.core.link import load_subsystem
from schgen.core.project import PROJECT_ROOT
from schgen.generate import bringup_facts as bf, _native_docs

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = PROJECT_ROOT / "firmware" / "sc"
ScfwError = native.module().FirmwareDocsError


def missing_requirements() -> list[str]:
    return _native_docs.missing("scfw")


class Model:
    def __init__(self) -> None:
        power = load_subsystem("power").circuit
        pmon = load_subsystem("power_mon").circuit
        en = load_subsystem("bringup_en").circuit
        mods = load_subsystem("bringup_modules").circuit
        rails = load_subsystem("bringup_rails").circuit
        usbpd = load_subsystem("usb_pd").circuit
        services = load_subsystem("board_services").circuit

        self.device = bf.stm32_pin_map()["value"]
        self.chain = bf.regulator_chain(power, monitor=pmon)
        self.rail_cells = {c.enable: c for c in bf.en_cells(en)}
        self.gates = bf.module_gates(mods)
        self.expander = bf.expander(rails)
        self.monitors = bf.ina3221_monitors(pmon)

        if not any("FUSB302" in p.value for p in usbpd.parts.values()):
            raise ScfwError("usb_pd netlist no longer carries a FUSB302 -- "
                            "the PD hooks would be stale")
        if not any("TPS3823" in p.value or "TPS3823" in p.lib_id
                   for p in services.parts.values()):
            raise ScfwError("board_services no longer carries a TPS3823 -- "
                            "the watchdog hooks would be stale")

        produced = {st.rail_out for st in self.chain}
        consumed = {st.rail_in for st in self.chain}
        self.always_on = sorted((consumed - produced) | {"+3V3_SC"})



def generate(out_dir: Path = DEFAULT_OUT) -> list[Path]:
    artifacts = native.module().firmware_scfw_render(*_native_docs.inputs())
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in artifacts.items():
        path = out_dir / name
        path.write_text(text)
        written.append(path)
    return written


def cmd_scfw(args: argparse.Namespace) -> int:
    missing = missing_requirements()
    if missing:
        print(f"SCFW SCAFFOLD: SKIP — project has no {', '.join(missing)}")
        return 1
    out_dir = args.output or DEFAULT_OUT
    written = generate(out_dir)
    print(f"SCFW SCAFFOLD: {out_dir} ({len(written)} files)")
    for p in written:
        print(f"  {p.name}")
    return 0
