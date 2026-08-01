from __future__ import annotations

from schgen.core import sexpr as sexpr
from schgen.core.sexpr import Sym as Sym

from . import constants as _constants
from . import embed as _embed
from . import emit as _emit
from . import footprint as _footprint
from . import mating_face as _mating_face
from . import placement as _placement
from . import silk as _silk
from . import turn as _turn

# Dependency layering — a later submodule's name wins over an earlier one's.
_submods = (_turn, _constants, _footprint, _mating_face, _placement, _embed,
            _silk, _emit)
for _m in _submods:
    for _name in dir(_m):
        if _name.startswith("__"):
            continue
        globals()[_name] = getattr(_m, _name)

del _m, _name, _submods
