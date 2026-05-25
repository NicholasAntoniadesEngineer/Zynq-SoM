"""Shared helpers for refcircuit datasheet paths."""

from __future__ import annotations

import re


def local_datasheet_path(part_mpn: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", part_mpn.strip())
    return f"datasheets/{sanitized.strip('_')}.pdf"
