"""Compatibility API for the native part importer.

Conversion, HTTP/download, cache discovery, and file publication live in C++.
The standalone replacement is native/bin/schgen part-import. Existing Python
entry points remain while schgen.__main__ and API tests still import this module.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from pathlib import Path

from schgen.core import native as _nat, sexpr

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARTS_DIR = REPO_ROOT / "parts"
EASYEDA_API = "https://easyeda.com/api/products/{lcsc}/components?version=6.4.19.5"
MODEL_STEP_URL = "https://modules.easyeda.com/qAxj6KHrDKw4blvCG8QJPs7Y/{uuid}"
MODEL_OBJ_URL = "https://modules.easyeda.com/3dmodel/{uuid}"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/120.0.0.0 Safari/537.36")
MM = 0.254
GRID = 1.27
PITCH = 2.54
PIN_LEN = 2.54
PASTE_RELIEF_MIN = 2.0
PASTE_COVER = 0.60
PASTE_PITCH_MAX = 1.5
MODEL_BODY_OVERHANG_MM = 5.0


class PartGenError(RuntimeError):
    pass


@dataclass(frozen=True)
class PinInfo:
    number: str
    name: str
    etype: str


@dataclass
class _Groups:
    left: list[PinInfo] = field(default_factory=list)
    right: list[PinInfo] = field(default_factory=list)
    top: list[PinInfo] = field(default_factory=list)
    bottom: list[PinInfo] = field(default_factory=list)


@dataclass(frozen=True)
class _EpSpec:
    w: float
    h: float
    cite: str


PACKAGE_EP: dict[str, _EpSpec] = {
    "C3192119": _EpSpec(1.0, 1.1, "MPS MPQ4423H Rev1.11 QFN-8 BOTTOM VIEW "
                        "D2xE2 = 0.95-1.05 x 1.05-1.15 mm -> 1.0x1.1 nominal"),
}


@dataclass(frozen=True)
class _PolaritySpec:
    x: float
    y: float
    size: float
    cite: str


PACKAGE_SILK_PLUS: dict[str, _PolaritySpec] = {
    "C5365933": _PolaritySpec(-5.6, 0.0, 0.6,
        "EasyEDA dataStr layer-12 SOLIDREGION '+' cross at pad-1 (V_RTC_BAT) "
        "side; board_services BT1.1=V_RTC_BAT, BT1.2=GND -> pad 1 is '+'"),
}


def _call(method: str, *args):
    try:
        native = _nat.module()
        if not hasattr(native, method):
            raise PartGenError(
                f"native {method} required; rebuild with bind_part_import")
        return getattr(native, method)(*args)
    except RuntimeError as exc:
        raise PartGenError(str(exc)) from exc


def _pin_data(pins: list[PinInfo]) -> list[dict]:
    return [asdict(pin) for pin in pins]


def _http_get(url: str, binary: bool = False,
              timeout: int = 30) -> bytes | str:
    """Native HTTPS transport; failures raise PartGenError, never empty success."""
    data = _call("part_http_get", url, timeout * 1000)
    return data if binary else data.decode("utf-8", errors="replace")


def fetch_cad(lcsc_id: str) -> dict:
    return _call("part_fetch_cad", lcsc_id)


def parse_pins(result: dict) -> list[PinInfo]:
    return [PinInfo(**pin) for pin in _call("part_import_pins", result)]


def normalize_etypes(pins: list[PinInfo], prefix: str) -> list[PinInfo]:
    return [PinInfo(**pin) for pin in
            _call("part_normalize_pin_types", _pin_data(pins), prefix)]


def part_info(result: dict) -> dict:
    return _call("part_import_info", result)


def safe_name(mpn: str) -> str:
    return _call("part_safe_name", mpn)


def group_pins(pins: list[PinInfo]) -> _Groups:
    groups = _call("part_group_pins", _pin_data(pins))
    return _Groups(**{side: [PinInfo(**pin) for pin in rows]
                      for side, rows in groups.items()})


def gen_symbol(name: str, pins: list[PinInfo], info: dict) -> list:
    return sexpr._from_tagged(
        _call("part_generate_symbol", name, _pin_data(pins), info))


def _ep_number(pins: list[PinInfo]) -> str:
    return _call("part_next_pin_number", _pin_data(pins))


def synth_ep_pin(info: dict, pins: list[PinInfo]) -> PinInfo | None:
    pin = _call("part_synthesize_ep", info.get("lcsc", ""), _pin_data(pins))
    return PinInfo(**pin) if pin is not None else None


def synth_ep_pad_nodes(number: str, lcsc: str) -> list:
    return [sexpr._from_tagged(node)
            for node in _call("part_ep_pad_nodes", number, lcsc)]


def synth_silk_plus_nodes(lcsc: str) -> list:
    return [sexpr._from_tagged(node)
            for node in _call("part_silk_plus_nodes", lcsc)]


def convert_footprint(result: dict, name: str, info: dict,
                      model_files: list[str],
                      ep_pin: PinInfo | None = None) -> tuple[list, dict | None]:
    out = _call("part_convert_footprint", result, name, info, model_files,
                asdict(ep_pin) if ep_pin is not None else None)
    for diagnostic in out["diagnostics"]:
        print(f"  3d: {diagnostic}")
    return sexpr._from_tagged(out["tree"]), out["model"]


def fetch_3d_models(uuid: str, outdir: Path, base: str, *,
                    overwrite: bool = False) -> list[str]:
    out = _call("part_fetch_3d_models", uuid, str(outdir), base, overwrite)
    for diagnostic in out["diagnostics"]:
        print(f"  3d: {diagnostic}")
    return out["files"]


def _obj_to_wrl(obj_data: str) -> str | None:
    return _call("model3d_obj_to_wrl", obj_data)


def gen_part_json(name: str, info: dict, pins: list[PinInfo],
                  model_files: list[str]) -> str:
    return _call("part_metadata_json", name, info, _pin_data(pins), model_files)


def add_part(lcsc_id: str, name: str | None = None,
             parts_dir: Path = DEFAULT_PARTS_DIR,
             from_json: Path | None = None, *,
             overwrite: bool = False) -> Path:
    """Import through native code; replacing existing files requires opt-in."""
    parts_dir = Path(parts_dir)
    out = _call("part_add", lcsc_id, name, str(parts_dir),
                str(from_json) if from_json is not None else None, overwrite)
    if parts_dir.resolve() == DEFAULT_PARTS_DIR.resolve():
        # Preserve the shared catalog lifecycle for the transitional Python CLI.
        # Native standalone callers select an explicit --catalog destination.
        try:
            if not _nat.catalog_recompile(parts_dir):
                raise PartGenError("catalog recompile returned false")
        except RuntimeError as exc:
            raise PartGenError(
                f"part files published but catalog refresh failed: {exc}") from exc
    for diagnostic in out["diagnostics"]:
        print(f"  3d: {diagnostic}")
    base = out["name"]
    outdir = Path(out["outdir"])
    print(f"part: {out['mpn']} ({out['lcsc']}) -> {outdir}")
    print(f"  symbol:    {base}.kicad_sym ({out['pins']} pins, all on {GRID} mm grid)")
    print(f"  footprint: {base}.kicad_mod ({out['pads']} pads, faithful)")
    print(f"  3d:        {', '.join(out['models']) if out['models'] else 'none'}")
    return outdir


def cmd_part_add(args: argparse.Namespace) -> int:
    try:
        add_part(args.lcsc_id, name=args.name,
                 parts_dir=args.parts_dir or DEFAULT_PARTS_DIR,
                 from_json=args.from_json,
                 overwrite=getattr(args, "overwrite", False))
        return 0
    except PartGenError as exc:
        print(f"part add FAILED: {exc}")
        return 1
