"""Download and verify local datasheet PDFs for every ReferenceCircuit."""

from __future__ import annotations

import hashlib
import json
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from zynq_eda.catalog.refcircuits import REFCIRCUITS
from zynq_eda.catalog.registry.parts_registry import REGISTRY


CARRIER_DIR = Path(__file__).resolve().parents[1]
DATASHEETS_DIR = CARRIER_DIR / "datasheets"
MANIFEST_PATH = DATASHEETS_DIR / "manifest.json"
README_PATH = DATASHEETS_DIR / "README.md"
MIN_FILE_BYTES = 1024
DOWNLOAD_TIMEOUT_SECONDS = 45

PDF_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "application/octet-stream",
        "binary/octet-stream",
    }
)

# Verified mirror URLs when manufacturer portals block automated fetch.
MPN_MIRROR_URLS: dict[str, tuple[str, ...]] = {
    "USBLC6-4SC6": (
        "https://www.numworks.com/engineering/hardware/electrical/parts/stusblc6-esd-protection-645a312d.pdf",
    ),
    "DS3231SN#": (
        "https://cdn.sparkfun.com/datasheets/Components/General/DS3231.pdf",
    ),
    "24LC256T-I/SN": (
        "https://ww1.microchip.com/downloads/en/devicedoc/21203p.pdf",
    ),
    "SS14": (
        "https://www.diodes.com/datasheet/download/SS14.pdf",
    ),
    "DM3AT-SF-PEJM5": (
        "https://datasheet.octopart.com/DM3AT-SF-PEJM5-Hirose-datasheet-145364295.pdf",
    ),
}

# LCSC product codes for hash-URL scrape fallback.
MPN_LCSC_CODES: dict[str, str] = {
    "TYPE-C-31-M-12": "C165948",
    "HDMI-019S": "C111617",
    "RJHSE5380": "C464586",
    "FX10A-168P-SV(91)": "C6624664",
    "FPC-05F-40PH20": "C2856812",
    "1.0-15P": "C66660",
    "ZX-PM2.54-2-7PY": "C7499342",
    "HX-PZ1.27-2x5P-TP": "C41376037",
    "KH-SMA-P-8496": "C910123",
    "YLED0603G": "C19273151",
    "TS-1002S-06026C": "C455112",
    "DS-04P": "C18198092",
    "SS14": "C83852",
    "PM254R-12-08-H85": "C53026548",
}

# Same PM254 series mechanical drawing when LCSC has no hash URL for PM254R.
MPN_LCSC_VARIANT_CODES: dict[str, str] = {
    "PM254R-12-08-H85": "C2834799",
}

_ISO_CERT_SIGNATURE = b"/Differences[ 1/M/A/N/G/E/T/space/S/Y/C/R/I/F]"


@dataclass(frozen=True)
class DatasheetEntry:
    circuit_key: str
    part_mpn: str
    url: str
    local_filename: str
    local_relpath: str


def _sanitize_mpn(part_mpn: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", part_mpn.strip())
    return sanitized.strip("_") or "unknown_part"


def _local_filename_for_mpn(part_mpn: str) -> str:
    return f"{_sanitize_mpn(part_mpn)}.pdf"


def _is_valid_pdf(payload: bytes) -> bool:
    return len(payload) >= MIN_FILE_BYTES and payload[:5] == b"%PDF-"


def _is_acceptable_datasheet_pdf(payload: bytes) -> bool:
    if not _is_valid_pdf(payload):
        return False
    if _ISO_CERT_SIGNATURE in payload[:800]:
        return False
    if b"ISO/IEC" in payload[:80000] and b"MANAGEMENT SYSTEM" in payload[:80000]:
        return False
    return True


def _lcsc_hash_pdf_urls(lcsc_code: str) -> tuple[str, ...]:
    html = _download_via_curl(
        f"https://www.lcsc.com/product-detail/{lcsc_code}.html"
    ).decode("utf-8", errors="replace")
    return tuple(
        dict.fromkeys(
            re.findall(
                r"https://datasheet\.lcsc\.com/datasheet/pdf/[a-f0-9]+\.pdf(?:\?[^\s\"']*)?",
                html,
            )
        )
    )


def _urls_for_mpn(part_mpn: str, primary_url: str) -> tuple[str, ...]:
    urls: list[str] = []
    urls.extend(MPN_MIRROR_URLS.get(part_mpn, ()))
    if primary_url:
        urls.append(primary_url)
    lcsc_code = MPN_LCSC_CODES.get(part_mpn)
    if lcsc_code is not None:
        urls.extend(_lcsc_hash_pdf_urls(lcsc_code))
    variant_code = MPN_LCSC_VARIANT_CODES.get(part_mpn)
    if variant_code is not None:
        urls.extend(_lcsc_hash_pdf_urls(variant_code))
    for part in REGISTRY.values():
        if part.mpn == part_mpn and part.datasheet_url:
            urls.append(part.datasheet_url)
    deduped: list[str] = []
    for url in urls:
        if url and url not in deduped:
            deduped.append(url)
    return tuple(deduped)


def _download_via_curl(url: str) -> bytes:
    result = subprocess.run(
        [
            "curl",
            "-fsSL",
            "--max-time",
            str(DOWNLOAD_TIMEOUT_SECONDS),
            "-A",
            "Zynq-SoM-carrier-datasheet-fetch/1.0",
            url,
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"curl failed for {url}: {stderr or result.returncode}")
    return result.stdout


def collect_datasheet_entries() -> tuple[DatasheetEntry, ...]:
    seen_mpn: set[str] = set()
    entries: list[DatasheetEntry] = []
    for circuit_key, ref_circuit in REFCIRCUITS.items():
        if ref_circuit.part_mpn in seen_mpn:
            continue
        seen_mpn.add(ref_circuit.part_mpn)
        local_filename = _local_filename_for_mpn(ref_circuit.part_mpn)
        entries.append(
            DatasheetEntry(
                circuit_key=circuit_key,
                part_mpn=ref_circuit.part_mpn,
                url=ref_circuit.datasheet_url,
                local_filename=local_filename,
                local_relpath=f"datasheets/{local_filename}",
            )
        )
    return tuple(entries)


def _sha256_file(file_path: Path) -> str:
    digest = hashlib.sha256()
    with open(file_path, "rb") as pdf_file:
        for chunk in iter(lambda: pdf_file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_once(url: str) -> tuple[bytes, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; Zynq-SoM-carrier-datasheet-fetch/1.0)"
            ),
            "Accept": "application/pdf,*/*",
        },
    )
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS, context=ssl_context) as response:
        content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
        payload = response.read()
    return payload, content_type


def _download_url(url: str, destination_path: Path) -> tuple[str, bool]:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            if "lcsc.com" in url.lower():
                payload = _download_via_curl(url)
                content_type = "application/pdf"
            else:
                payload, content_type = _download_once(url)
            if not _is_acceptable_datasheet_pdf(payload):
                raise RuntimeError(
                    f"Response from {url} is not an acceptable datasheet PDF "
                    f"(content-type={content_type!r}, "
                    f"header={payload[:16]!r})"
                )
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            destination_path.write_bytes(payload)
            return content_type or "application/pdf", True
        except Exception as error:
            last_error = error
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed to download {url}: {last_error}") from last_error


def _fetch_entry(entry: DatasheetEntry, *, force: bool) -> dict[str, object]:
    destination_path = DATASHEETS_DIR / entry.local_filename
    if destination_path.exists() and not force:
        payload = destination_path.read_bytes()
        if _is_acceptable_datasheet_pdf(payload):
            return {
                "circuit_key": entry.circuit_key,
                "part_mpn": entry.part_mpn,
                "url": entry.url,
                "local_path": f"datasheets/{destination_path.name}",
                "sha256": _sha256_file(destination_path),
                "content_type": "cached",
                "size_bytes": destination_path.stat().st_size,
            }
        destination_path.unlink()

    errors: list[str] = []
    for url in _urls_for_mpn(entry.part_mpn, entry.url):
        try:
            content_type, _is_pdf = _download_url(url, destination_path)
            if not destination_path.exists():
                raise RuntimeError("File missing after download")
            return {
                "circuit_key": entry.circuit_key,
                "part_mpn": entry.part_mpn,
                "url": url,
                "local_path": f"datasheets/{destination_path.name}",
                "sha256": _sha256_file(destination_path),
                "content_type": content_type,
                "size_bytes": destination_path.stat().st_size,
            }
        except Exception as error:
            errors.append(f"{url}: {error}")
            if destination_path.exists():
                destination_path.unlink()

    raise RuntimeError(
        f"All datasheet URLs failed for {entry.part_mpn}:\n  "
        + "\n  ".join(errors)
    )


def _write_readme(entries: tuple[DatasheetEntry, ...]) -> None:
    lines = [
        "# Carrier Datasheet Corpus",
        "",
        "Local copies of manufacturer datasheets cited by `ReferenceCircuit` specs.",
        "Fetched by `fetch_datasheets.py`; SHA-256 hashes recorded in `manifest.json`.",
        "",
        "## Files",
        "",
    ]
    for entry in entries:
        lines.append(f"- `{entry.local_filename}` — {entry.part_mpn}")
    README_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_datasheets_fetched(*, force: bool = False) -> dict[str, object]:
    """Fetch only missing or invalid PDFs; refresh manifest."""
    entries = collect_datasheet_entries()
    manifest_entries: list[dict[str, object]] = []
    fetch_failures: list[str] = []
    for entry in entries:
        destination_path = DATASHEETS_DIR / entry.local_filename
        needs_fetch = force
        if not needs_fetch:
            if not destination_path.exists():
                needs_fetch = True
            else:
                needs_fetch = not _is_acceptable_datasheet_pdf(
                    destination_path.read_bytes()
                )
        if needs_fetch:
            try:
                manifest_entries.append(_fetch_entry(entry, force=True))
            except RuntimeError as error:
                fetch_failures.append(f"{entry.part_mpn}: {error}")
                if destination_path.exists() and not _is_valid_pdf(
                    destination_path.read_bytes()
                ):
                    destination_path.unlink()
        else:
            manifest_entries.append(
                {
                    "circuit_key": entry.circuit_key,
                    "part_mpn": entry.part_mpn,
                    "url": entry.url,
                    "local_path": f"datasheets/{destination_path.name}",
                    "sha256": _sha256_file(destination_path),
                    "content_type": "cached",
                    "size_bytes": destination_path.stat().st_size,
                }
            )

    manifest = {
        "version": 1,
        "entry_count": len(manifest_entries),
        "entries": manifest_entries,
        "fetch_failures": fetch_failures,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _write_readme(entries)
    if fetch_failures:
        raise RuntimeError(
            "Datasheet fetch failed for:\n  " + "\n  ".join(fetch_failures)
        )
    return manifest


def fetch_all(*, force: bool = False) -> dict[str, object]:
    """Fetch every datasheet (or only stale entries when ``force`` is False)."""
    if force:
        entries = collect_datasheet_entries()
        manifest_entries = [_fetch_entry(entry, force=True) for entry in entries]
        manifest = {
            "version": 1,
            "entry_count": len(manifest_entries),
            "entries": manifest_entries,
        }
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        _write_readme(entries)
        return manifest
    return ensure_datasheets_fetched(force=False)


def ensure_datasheets_present() -> None:
    missing: list[str] = []
    for circuit_key, ref_circuit in REFCIRCUITS.items():
        if not ref_circuit.local_datasheet_path:
            missing.append(f"{circuit_key}: no local_datasheet_path set")
            continue
        local_path = CARRIER_DIR / ref_circuit.local_datasheet_path
        if not local_path.exists():
            missing.append(
                f"{circuit_key}: missing {ref_circuit.local_datasheet_path}"
            )
            continue
        payload = local_path.read_bytes()
        if not _is_acceptable_datasheet_pdf(payload):
            missing.append(
                f"{circuit_key}: {ref_circuit.local_datasheet_path} is not a valid datasheet PDF"
            )
        if not ref_circuit.minimum_circuit_verified:
            missing.append(f"{circuit_key}: minimum_circuit_verified is False")
    if missing:
        raise RuntimeError(
            "Datasheet / refcircuit gate failed:\n  "
            + "\n  ".join(missing)
            + "\nRun: python -m zynq_eda.catalog.datasheets.fetch_datasheets"
        )


def main() -> int:
    force = "--force" in sys.argv
    manifest = fetch_all(force=force)
    print(
        f"Fetched {manifest['entry_count']} datasheets into "
        f"{DATASHEETS_DIR.relative_to(CARRIER_DIR.parents[1])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
