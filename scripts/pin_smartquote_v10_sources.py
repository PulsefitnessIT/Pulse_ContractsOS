"""Create a non-commercial, hash-pinned identity manifest for original V10 sources.

IT operation ONLY. No catalogue rows, prices, names or customer data are
copied to GitHub or printed. Source files remain untouched on private storage.

python scripts/pin_smartquote_v10_sources.py \
 --smartquote-root /secure/SmartQuoteV10 \
 --output /secure/smartquote_source_manifest.json \
 --owner "Authorised data custodian" --effective-date 2026-11-03 \
 --confirm-source-snapshot
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import zlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FILES=("catalog","configs","pricing")
# Optional evidence is pinned when present, never substituted with synthetic data.
OPTIONAL_FILES={
    "legacy_crosswalk": ("legacy.json", 8 * 1024 * 1024),
    "historical_identity": ("historical_catalogue_index.json", 35 * 1024 * 1024),
}


def _optional_payload(path:Path, maximum:int):
    if not 2 <= path.stat().st_size <= maximum:
        raise ValueError("Optional V10 evidence is empty or oversized.")
    raw=path.read_bytes()
    if path.suffix.lower()==".gz":
        decoder=zlib.decompressobj(16+zlib.MAX_WBITS)
        decoded=decoder.decompress(raw, 80 * 1024 * 1024 + 1)
        if (len(decoded)>80 * 1024 * 1024 or not decoder.eof
            or decoder.unused_data or decoder.unconsumed_tail):
            raise ValueError("Compressed V10 history evidence is not complete or is oversized.")
        payload=json.loads(decoded.decode("utf-8"))
    else:
        payload=json.loads(raw.decode("utf-8"))
    return raw,payload



def create(root:Path, output:Path, owner:str, effective_date:str,
           *, approved_source_snapshot:bool=False):
    if not approved_source_snapshot:
        raise ValueError("IT must confirm this specific private V10 source snapshot.")
    root=root.expanduser().resolve(strict=True)
    output=output.expanduser().absolute()
    if (not root.is_dir() or not (root/"engine.py").is_file()
        or output.exists() or output.is_symlink()
        or output == ROOT or ROOT in output.parents
        or not output.parent.is_dir()):
        raise ValueError("Provide an intact private V10 runtime and a NEW manifest location outside GitHub.")
    if not 3<=len(str(owner).strip())<=120:
        raise ValueError("Provide a recorded data custodian (not a commercial approver claim).")
    try:
        dt.date.fromisoformat(effective_date)
        if len(effective_date)!=10:
            raise ValueError()
    except (TypeError,ValueError) as exc:
        raise ValueError("Source effective date must be a real YYYY-MM-DD date.") from exc
    hashes={}
    counts={}
    for kind in FILES:
        path=root/"data"/(kind+".json")
        if not path.is_file() or not 2 <= path.stat().st_size <= (20*1024*1024 if kind=="catalog" else 12*1024*1024):
            raise ValueError(f"The complete V10 {kind} evidence source is unavailable.")
        raw=path.read_bytes()
        payload=json.loads(raw.decode("utf-8"))
        if kind=="pricing":
            if not isinstance(payload,dict) or not payload.get("pricing_status"):
                raise ValueError("Pricing status is not explicitly recorded in the source.")
        elif not isinstance(payload,list) or len(payload)==0:
            raise ValueError("A required V10 catalogue/configuration source is empty.")
        hashes[kind]=hashlib.sha256(raw).hexdigest()
        counts[kind]=len(payload)
    # Audit the same legacy/history evidence that the staff reconciliation UI
    # will read. Ambiguous dual historical files must be resolved by IT.
    for kind,(filename,maximum) in OPTIONAL_FILES.items():
        source=root/"data"/filename
        if kind=="historical_identity":
            compressed=root/"data"/(filename+".gz")
            if source.is_file() and compressed.is_file():
                raise ValueError("Two original history indexes exist; select one verified snapshot.")
            if compressed.is_file():
                source=compressed
        if not source.exists():
            continue
        if not source.is_file():
            raise ValueError(f"Staged optional V10 {kind} is not a regular file.")
        try:
            raw,payload=_optional_payload(source,maximum)
        except (OSError,UnicodeError,ValueError,zlib.error,json.JSONDecodeError) as exc:
            raise ValueError(f"Staged optional V10 {kind} is invalid.") from exc
        if kind=="legacy_crosswalk":
            if not isinstance(payload,list) or len(payload)>80000:
                raise ValueError("Unexpected V10 legacy crosswalk format.")
            counts[kind]=len(payload)
        else:
            if (not isinstance(payload,dict) or not isinstance(payload.get("records"),dict)
                or len(payload["records"])>150000
                or not isinstance(payload.get("aliases",{}),dict)):
                raise ValueError("Unexpected V10 historical index format.")
            counts[kind]=len(payload["records"])
        hashes[kind]=hashlib.sha256(raw).hexdigest()
    manifest={
        "schema_version":2,
        "owner":owner.strip(),
        "effective_date":effective_date,
        "source_kind":"Original V10 private files; source identity verified, NOT commercially approved",
        "sha256":hashes,
        "commercial_rate_approval_recorded":False,
    }
    fd=os.open(str(output),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(manifest,stream,indent=2,ensure_ascii=False)
            stream.write("\n")
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return {
        "manifest_sha256":hashlib.sha256(output.read_bytes()).hexdigest(),
        "source_counts":counts,
        "commercial_rates_approved":False,
        "original_source_not_modified":True,
        "private_output":True,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smartquote-root",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--owner",required=True)
    parser.add_argument("--effective-date",required=True)
    parser.add_argument("--confirm-source-snapshot",action="store_true")
    arg=parser.parse_args()
    result=create(arg.smartquote_root,arg.output,arg.owner,
                  arg.effective_date,approved_source_snapshot=arg.confirm_source_snapshot)
    print(json.dumps(result,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
