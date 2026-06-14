"""schgen preflight — live JLC/LCSC availability + cost check for subsystems.

``schgen preflight <subsystem>...`` resolves every part's ``LCSC`` field
against the JLCPCB parts library (the API the jlcpcb.com parts browser uses;
anonymous POST, verified live 2026-06-10) and reports per line item:

    stock, Basic/Extended, unit price at the required qty, extended cost

plus a rollup: total BOM cost, number of Extended reels (each Extended part
costs a JLC feeder-loading fee), and every part that is missing/not found/
out of stock. Exit is non-zero when any part is out of stock or not found —
and, unless ``--allow-missing``, when any part has no LCSC id yet (a part
that cannot be ordered is a ghost; carrier/PLAN.md: preflight fails on
ghosts).

Endpoints:
- primary: POST https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/
  smtGood/selectSmtComponentList  (keyword search; exact componentCode match)
- fallback: GET https://wmsc.lcsc.com/ftps/wm/product/detail?productCode=C…
  (LCSC catalog detail; NOTE: its stock fields read 0 without a region
  cookie, so it is used only to distinguish "exists on LCSC but not at JLC
  assembly" from "not found anywhere").
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SUBSYSTEMS_DIR = REPO_ROOT / "carrier" / "subsystems"

JLC_SEARCH_URL = ("https://jlcpcb.com/api/overseas-pcb-order/v1/"
                  "shoppingCart/smtGood/selectSmtComponentList")
LCSC_DETAIL_URL = "https://wmsc.lcsc.com/ftps/wm/product/detail?productCode={code}"


def _load_subsystem(name_or_path: str):
    path = Path(name_or_path)
    if path.suffix != ".py":
        path = SUBSYSTEMS_DIR / f"{Path(name_or_path).stem}.py"
    if not path.exists():
        raise SystemExit(f"subsystem not found: {path}")
    spec = importlib.util.spec_from_file_location(
        f"preflight_subsys_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# queries
# ---------------------------------------------------------------------------

def query_jlc(lcsc_id: str, timeout: int = 20) -> dict | None:
    """Exact-match JLCPCB parts-library lookup. None = not in JLC library."""
    body = json.dumps({"keyword": lcsc_id, "currentPage": 1,
                       "pageSize": 5}).encode()
    req = urllib.request.Request(
        JLC_SEARCH_URL, data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Origin": "https://jlcpcb.com",
                 "Referer": "https://jlcpcb.com/parts",
                 "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36")})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None
    items = ((data.get("data") or {}).get("componentPageInfo") or {}).get(
        "list") or []
    for it in items:
        if it.get("componentCode") == lcsc_id:
            return {
                "mpn": it.get("componentModelEn", ""),
                "brand": it.get("componentBrandEn", ""),
                "package": it.get("componentSpecificationEn", ""),
                "stock": int(it.get("stockCount") or 0),
                "library": ("Basic" if it.get("componentLibraryType") == "base"
                            else "Extended"),
                "min_qty": int(it.get("minPurchaseNum") or 1),
                "prices": [(int(p.get("startNumber") or 1),
                            float(p.get("productPrice") or 0))
                           for p in (it.get("componentPrices") or [])],
            }
    return None


def query_lcsc_exists(lcsc_id: str, timeout: int = 20) -> bool:
    """Does the part exist in the LCSC catalog at all? (fallback signal)"""
    req = urllib.request.Request(LCSC_DETAIL_URL.format(code=lcsc_id),
                                 headers={"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36")})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return False
    return bool(data.get("code") == 200 and data.get("result"))


def unit_price(prices: list[tuple[int, float]], qty: int) -> float:
    """Price at the ladder rung covering ``qty`` (first rung below min qty)."""
    if not prices:
        return 0.0
    best = prices[0][1]
    for start, price in sorted(prices):
        if qty >= start:
            best = price
    return best


# ---------------------------------------------------------------------------
# stock policy (SRC-2): a procurement floor + a pure, testable verdict
# ---------------------------------------------------------------------------

STOCK_FLOOR = 50   # below this, even stock >= need is a procurement risk (WARN)


def assess_stock(stock: int, need: int, floor: int = STOCK_FLOOR) -> tuple[str, str]:
    """Pure stock verdict (no network). status in {ok, low, insufficient, out}.

    A part with 10 units in stock is a landmine even when need <= 10 — one
    other order exhausts it — so stock below the floor is flagged 'low' (a
    WARNING, not a hard fail), so a single-feeder part can never pass clean.
    """
    if stock <= 0:
        return "out", "** OUT OF STOCK **"
    if stock < need:
        return "insufficient", f"** INSUFFICIENT (stock {stock} < need {need}) **"
    if stock < max(need, floor):
        return "low", f"** LOW STOCK ({stock} < floor {floor}) **"
    return "ok", ""


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

@dataclass
class LineItem:
    lcsc: str
    value: str
    refs: list[str] = field(default_factory=list)
    alt_lcsc: list[str] = field(default_factory=list)   # SRC-1 second sources


def cmd_preflight(args: argparse.Namespace) -> int:
    qty_boards = args.qty
    items: dict[str, LineItem] = {}
    missing: list[str] = []

    for name in args.subsystems:
        mod = _load_subsystem(name)
        c = mod.circuit()
        for ref, part in sorted(c.parts.items()):
            if (part.fields or {}).get("BOM") == "exclude":
                continue       # pad-only test points: copper, no BOM line
            lcsc = (part.fields or {}).get("LCSC", "").strip()
            label = f"{c.name}:{ref}"
            if not lcsc:
                missing.append(f"{label} ({part.value})")
                continue
            it = items.setdefault(lcsc, LineItem(lcsc=lcsc, value=part.value))
            it.refs.append(label)
            for a in (part.fields or {}).get("ALT_LCSC", "").split(","):
                a = a.strip()
                if a and a not in it.alt_lcsc:
                    it.alt_lcsc.append(a)             # SRC-1 second source(s)

    print(f"preflight: {len(items)} LCSC line item(s), {len(missing)} part(s) "
          f"without an LCSC id, {qty_boards} board(s)")

    failures: list[str] = []
    warnings: list[str] = []
    total_cost = 0.0
    extended_reels = 0
    floor = getattr(args, "min_stock", STOCK_FLOOR)
    if items:
        hdr = (f"{'LCSC':<12} {'MPN':<24} {'lib':<9} {'stock':>9} "
               f"{'need':>5} {'unit $':>8} {'ext $':>8}  refs")
        print(hdr)
        print("-" * len(hdr))
    for lcsc, it in sorted(items.items()):
        need = len(it.refs) * qty_boards
        info = query_jlc(lcsc)
        if info is None:
            on_lcsc = query_lcsc_exists(lcsc)
            where = "LCSC catalog only (not JLC assembly)" if on_lcsc \
                else "NOT FOUND anywhere"
            print(f"{lcsc:<12} {it.value:<24} {'?':<9} {'-':>9} {need:>5} "
                  f"{'-':>8} {'-':>8}  {where}")
            failures.append(f"{lcsc} ({it.value}): {where}")
            continue
        up = unit_price(info["prices"], max(need, info["min_qty"]))
        ext = up * need
        total_cost += ext
        if info["library"] == "Extended":
            extended_reels += 1
        status, flag = assess_stock(info["stock"], need, floor)
        flag = f"  {flag}" if flag else ""
        if status != "ok":
            chosen = None
            for alt in it.alt_lcsc:                  # try the committed 2nd sources
                ainfo = query_jlc(alt)
                if ainfo and assess_stock(ainfo["stock"], need, floor)[0] == "ok":
                    chosen = (alt, ainfo)
                    break
            if chosen:
                flag += (f"  -> 2nd source {chosen[0]} OK "
                         f"(stock {chosen[1]['stock']})")
                warnings.append(
                    f"{lcsc} ({info['mpn']}): {status} but covered by alternate "
                    f"{chosen[0]} (stock {chosen[1]['stock']})")
            elif status in ("out", "insufficient"):
                tried = (f"; no alternate clears it (tried {','.join(it.alt_lcsc)})"
                         if it.alt_lcsc else "")
                failures.append(f"{lcsc} ({info['mpn']}): {status.upper()}{tried}")
            else:  # low stock, no healthy alternate -> procurement WARNING
                warnings.append(
                    f"{lcsc} ({info['mpn']}): LOW STOCK {info['stock']} < floor "
                    f"{floor}" + ("; no healthier alternate" if it.alt_lcsc
                                  else "; no ALT_LCSC second source committed"))
        print(f"{lcsc:<12} {info['mpn'][:24]:<24} {info['library']:<9} "
              f"{info['stock']:>9} {need:>5} {up:>8.4f} {ext:>8.4f}  "
              f"{','.join(it.refs)}{flag}")

    print(f"\nTOTAL parts cost: ${total_cost:.4f} for {qty_boards} board(s); "
          f"Extended reels: {extended_reels} "
          f"(+ JLC feeder fee each)")
    if missing:
        print(f"MISSING LCSC id ({len(missing)}):")
        for m in missing:
            print(f"  {m}")
    if warnings:
        print(f"PROCUREMENT WARNINGS ({len(warnings)} — not fatal, "
              f"review before a build):")
        for w in warnings:
            print(f"  {w}")
    if failures:
        print(f"PREFLIGHT: FAIL ({len(failures)} availability problem(s))")
        for f_ in failures:
            print(f"  {f_}")
        return 1
    if missing and not args.allow_missing:
        print("PREFLIGHT: FAIL (parts without LCSC ids cannot be ordered; "
              "rerun with --allow-missing to tolerate)")
        return 1
    print("PREFLIGHT: PASS")
    return 0
