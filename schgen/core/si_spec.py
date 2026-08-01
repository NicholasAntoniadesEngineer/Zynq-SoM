from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from schgen.core.project import PROJECT_ROOT

MM_PER_MIL = 0.0254
SI_SPEC_PATH = PROJECT_ROOT / "research" / "si_spec.json"


@dataclass(frozen=True)
class PairSpec:
    interface: str
    signal: str
    net_p: str
    net_n: str
    z_diff_ohm: int
    match_tol_mil: float
    intra_pair_skew_mil: float
    ac_coupled: bool
    spec_cite: str
    notes: str

    @property
    def nets(self) -> frozenset[str]:
        return frozenset((self.net_p, self.net_n))

    @property
    def intra_pair_skew_mm(self) -> float:
        return round(self.intra_pair_skew_mil * MM_PER_MIL, 4)

    @property
    def match_tol_mm(self) -> float:
        return round(self.match_tol_mil * MM_PER_MIL, 4)


def load_si_spec(path: Path = SI_SPEC_PATH) -> list[PairSpec]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — the vendored SI target table is required "
            f"(committed under the project's research/).")
    data = json.loads(path.read_text())
    out = [PairSpec(
        interface=p["interface"],
        signal=p.get("signal", ""),
        net_p=p["net_p"],
        net_n=p["net_n"],
        z_diff_ohm=int(p["z_diff_ohm"]),
        match_tol_mil=float(p["match_tol_mil"]),
        intra_pair_skew_mil=float(p["intra_pair_skew_mil"]),
        ac_coupled=bool(p["ac_coupled"]),
        spec_cite=p["spec_cite"],
        notes=p.get("notes", ""),
    ) for p in data.get("pairs", [])]
    return sorted(out, key=lambda s: (s.interface, s.net_p))


def spec_by_net(path: Path = SI_SPEC_PATH) -> dict[str, PairSpec]:
    by_net: dict[str, PairSpec] = {}
    for s in load_si_spec(path):
        by_net[s.net_p] = s
        by_net[s.net_n] = s
    return by_net


def researched_pair(net: str, kind: str,
                    by_net: dict[str, PairSpec]) -> PairSpec:
    spec = by_net.get(net)
    if spec is None:
        raise KeyError(
            f"{net}: typed {kind} but has no row in {SI_SPEC_PATH} — every "
            f"pair's intra-pair skew is read per net from the researched "
            f"table; there is no per-kind default to fall back to. Add the "
            f"pair with its standard citation.")
    return spec
