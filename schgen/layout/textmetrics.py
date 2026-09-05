from __future__ import annotations

import re

from schgen.core import native as _nat
from schgen.core.config import CHAR_W

SIZE = 1.27
LINE_H = 1.6

GLABEL_PAD_LEN = 2.0
GLABEL_H = 2.2
GLABEL_INSET = 0.254


_MARKUP = re.compile(r"~\{([^}]*)\}")
_LLABEL_WIDTH_PAD = 0.7
_LLABEL_GAP = 0.127


def text_wh_py(text: str, size: float = SIZE) -> tuple[float, float]:
    visible = _MARKUP.sub(r"\1", text)
    return (max(len(visible), 1) * CHAR_W * size, LINE_H * size)


def text_wh(text: str, size: float = SIZE) -> tuple[float, float]:
    if _nat.loaded():
        got = tuple(_nat.module().text_wh(text, size, CHAR_W, LINE_H))
        if _nat.trace():
            ref = text_wh_py(text, size)
            if got != ref:
                raise AssertionError(
                    f"native text_wh DIVERGENCE: cpp={got} python={ref}")
        return got
    return text_wh_py(text, size)


def centered_box_py(text: str, cx: float, cy: float, size: float = SIZE,
                    vertical: bool = False) -> tuple[float, float, float, float]:
    w, h = text_wh_py(text, size)
    if vertical:
        w, h = h, w
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def centered_box(text: str, cx: float, cy: float, size: float = SIZE,
                 vertical: bool = False) -> tuple[float, float, float, float]:
    if _nat.loaded():
        got = tuple(_nat.module().centered_box(
            text, cx, cy, size, CHAR_W, LINE_H, vertical))
        if _nat.trace():
            ref = centered_box_py(text, cx, cy, size, vertical)
            if got != ref:
                raise AssertionError(
                    f"native centered_box DIVERGENCE: cpp={got} python={ref}")
        return got
    return centered_box_py(text, cx, cy, size, vertical)


def llabel_box_py(text: str, x: float, y: float, rotation: int = 0,
                  size: float = SIZE) -> tuple[float, float, float, float]:
    w, h = text_wh_py(text, size)
    w += _LLABEL_WIDTH_PAD
    gap = _LLABEL_GAP
    r = rotation % 360
    if r == 0:
        return (x, y - gap - h, x + w, y - gap)
    if r == 180:
        return (x - w, y - gap - h, x, y - gap)
    raise ValueError(f"unsupported local-label rotation {rotation}")


def llabel_box(text: str, x: float, y: float, rotation: int = 0,
               size: float = SIZE) -> tuple[float, float, float, float]:
    if _nat.loaded():
        got = tuple(_nat.module().llabel_box(
            text, x, y, rotation, size, CHAR_W, LINE_H,
            _LLABEL_WIDTH_PAD, _LLABEL_GAP))
        if _nat.trace():
            ref = llabel_box_py(text, x, y, rotation, size)
            if got != ref:
                raise AssertionError(
                    f"native llabel_box DIVERGENCE: cpp={got} python={ref}")
        return got
    return llabel_box_py(text, x, y, rotation, size)


def glabel_box_py(text: str, x: float, y: float, rotation: int,
                  size: float = SIZE) -> tuple[float, float, float, float]:
    w, _ = text_wh_py(text, size)
    length = w + GLABEL_PAD_LEN * size
    half_h = GLABEL_H * size / 2
    r = rotation % 360
    if r == 0:
        return (x + GLABEL_INSET, y - half_h, x + length, y + half_h)
    if r == 180:
        return (x - length, y - half_h, x - GLABEL_INSET, y + half_h)
    if r == 90:
        return (x - half_h, y - length, x + half_h, y - GLABEL_INSET)
    if r == 270:
        return (x - half_h, y + GLABEL_INSET, x + half_h, y + length)
    raise ValueError(f"unsupported label rotation {rotation}")


def glabel_box(text: str, x: float, y: float, rotation: int,
               size: float = SIZE) -> tuple[float, float, float, float]:
    if _nat.loaded():
        got = tuple(_nat.module().glabel_box(
            text, x, y, rotation, size, CHAR_W, LINE_H,
            GLABEL_PAD_LEN, GLABEL_H, GLABEL_INSET))
        if _nat.trace():
            ref = glabel_box_py(text, x, y, rotation, size)
            if got != ref:
                raise AssertionError(
                    f"native glabel_box DIVERGENCE: cpp={got} python={ref}")
        return got
    return glabel_box_py(text, x, y, rotation, size)
