"""Temporary import adapter; live extraction and contract emission are C++."""
from __future__ import annotations

from pathlib import Path

from schgen.core import native


def extract(som_sch: Path, refs: list[str]) -> dict:
    return native.module().som_extract(str(som_sch), refs)


def extract_zynq(som_sch: Path, zynq_ref: str = "U2",
                 jrefs: tuple[str, ...] = ("J1", "J2", "J3")) -> dict:
    return native.module().som_extract_zynq(str(som_sch), zynq_ref, list(jrefs))


def cmd(args) -> int:
    print(native.module().som_write_interface(
        str(args.som_sch), args.refs, str(args.output)), end="")
    return 0
