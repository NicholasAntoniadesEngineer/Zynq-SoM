"""Conservative text bounding-box estimation for the KiCad stroke font.

Every estimate is a deliberate OVERESTIMATE (never under): placement spaces
things by these boxes and the visual gate judges with them, so an honest
over-bound can only force more whitespace, never hide a collision.

KiCad default font, size 1.27 mm: average glyph advance is ~1.0 mm; we claim
0.95 * size per character. Glyph extent incl. ascenders/descenders is ~1.3 *
size; we claim 1.6 * size.
"""

from __future__ import annotations

import re

SIZE = 1.27            # default KiCad schematic text size (mm)
CHAR_W = 0.95          # claimed advance per character, fraction of size
LINE_H = 1.6           # claimed glyph height, fraction of size

# Global-label outline: text + internal margins + the chevron point.
GLABEL_PAD_LEN = 2.0   # fraction of size added to the text length
GLABEL_H = 2.2         # outline height, fraction of size
GLABEL_INSET = 0.254   # mm between the anchor (wire attachment) and the box —
                       # the chevron tip itself is the electrical contact point


_MARKUP = re.compile(r"~\{([^}]*)\}")


def text_wh(text: str, size: float = SIZE) -> tuple[float, float]:
    """(width, height) of a horizontal run of ``text``.

    KiCad overbar markup ``~{ABC}`` renders as the bare glyphs with a bar —
    measure the VISIBLE glyphs (the bar adds height we already over-claim),
    not the markup characters.
    """
    visible = _MARKUP.sub(r"\1", text)
    return (max(len(visible), 1) * CHAR_W * size, LINE_H * size)


def centered_box(text: str, cx: float, cy: float, size: float = SIZE,
                 vertical: bool = False) -> tuple[float, float, float, float]:
    """Box of center-justified text at (cx, cy); vertical=True for 90° text."""
    w, h = text_wh(text, size)
    if vertical:
        w, h = h, w
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def llabel_box(text: str, x: float, y: float, rotation: int = 0,
               size: float = SIZE) -> tuple[float, float, float, float]:
    """Rendered extent of a LOCAL net label anchored at (x, y) on a wire.

    rotation 0: text extends +x from the anchor, sitting just above the wire;
    rotation 180: text extends -x. The thin gap under the text is the label's
    own wire-offset — the wire underneath is the attachment, not a collision.
    """
    w, h = text_wh(text, size)
    w += 0.7
    gap = 0.127
    r = rotation % 360
    if r == 0:
        return (x, y - gap - h, x + w, y - gap)
    if r == 180:
        return (x - w, y - gap - h, x, y - gap)
    raise ValueError(f"unsupported local-label rotation {rotation}")


def glabel_box(text: str, x: float, y: float, rotation: int,
               size: float = SIZE) -> tuple[float, float, float, float]:
    """Rendered outline of a global/hier label anchored at (x, y).

    rotation 0: wire arrives from the left, text extends +x.
    rotation 180: wire arrives from the right, text extends -x.
    The box starts GLABEL_INSET past the anchor: the chevron tip at the anchor
    is the wire attachment (electrical necessity, like a wire end on a pin).
    """
    w, _ = text_wh(text, size)
    length = w + GLABEL_PAD_LEN * size
    half_h = GLABEL_H * size / 2
    r = rotation % 360
    if r == 0:
        return (x + GLABEL_INSET, y - half_h, x + length, y + half_h)
    if r == 180:
        return (x - length, y - half_h, x - GLABEL_INSET, y + half_h)
    if r == 90:    # pointing up, text runs upward
        return (x - half_h, y - length, x + half_h, y - GLABEL_INSET)
    if r == 270:
        return (x - half_h, y + GLABEL_INSET, x + half_h, y + length)
    raise ValueError(f"unsupported label rotation {rotation}")
