"""
Seed a freshly-deployed `raw-documents` container from the prebuilt seed
archive hosted on `pubzip0513143342`.

The archive is a single `.tar.gz` containing the original blob layout of
`stragidyn6dtfun6/raw-documents/`. It is published once via
`scripts/bundle_seed_data.py` and exposed through a **User Delegation SAS**
URL (read-only, max 7-day TTL).

Layout convention inside the tar:
    {source}/{YYYY-MM-DD}/{blob}.json|.md
    e.g. prec/2026-04-15/law_001680.json

Flow:
  1. Stream-download the tar.gz from SEED_URL (no full file on disk).
  2. Main thread iterates tar members; each member's bytes are handed to a
     ThreadPoolExecutor for parallel upload (default 24 workers).
  3. Optional --filter-source / --filter-date-from / --filter-date-to
     constrain which (source, date) folders are uploaded.

Prereq: caller must hold `Storage Blob Data Contributor` on the destination
account (`az login` first).

Usage:
  # SEED_URL is the SAS URL printed by bundle_seed_data.py
  export SEED_URL='https://pubzip0513143342.blob.core.windows.net/seed/raw-documents-seed.tar.gz?...'
  uv run python scripts/seed_raw_documents.py \
      --dest-account stragiabcd1234ef \
      --dest-container raw-documents \
      --workers 32

  # 특정 source 만, 특정 날짜 범위만
  uv run python scripts/seed_raw_documents.py \
      --dest-account stragiabcd1234ef \
      --filter-source prec,detc \
      --filter-date-from 2026-04-15 \
      --filter-date-to 2026-04-30
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
import tarfile
import threading
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor

from azure.identity import AzureCliCredential
from azure.storage.blob import BlobServiceClient, ContainerClient

# Default seed URL: replace via SEED_URL env var or --seed-url after re-publishing.
# (The SAS query string is required — anonymous access is disabled by tenant policy.)
DEFAULT_SEED_URL = os.environ.get(
    "SEED_URL",
    "https://pubzip0513143342.blob.core.windows.net/seed/raw-documents-seed.tar.gz",
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def ensure_container(account: str, container: str) -> BlobServiceClient:
    cred = AzureCliCredential()
    svc = BlobServiceClient(
        account_url=f"https://{account}.blob.core.windows.net",
        credential=cred,
    )
    try:
        svc.create_container(container)
        print(f"[dest] created container '{container}'")
    except Exception as e:
        if "ContainerAlreadyExists" not in str(e):
            raise
        print(f"[dest] container '{container}' already exists")
    return svc


def parse_layout(blob_name: str) -> tuple[str | None, str | None]:
    """Return (source, date) from '{source}/{YYYY-MM-DD}/...' layout, else (None, None)."""
    parts = blob_name.split("/", 2)
    if len(parts) >= 3 and DATE_RE.match(parts[1]):
        return parts[0], parts[1]
    return None, None


def _parse_date(s: str | None) -> dt.date | None:
    if not s:
        return None
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def stream_extract_upload(
    seed_url: str,
    svc: BlobServiceClient,
    container: str,
    prefix: str = "",
    workers: int = 24,
    filter_sources: set[str] | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
) -> int:
    """Stream tar.gz directly from SEED_URL → fan-out uploads via ThreadPool."""
    masked = seed_url.split("?", 1)[0] + ("?<sas>" if "?" in seed_url else "")
    print(f"[stream] {masked}")
    print(f"[parallel] {workers} workers")
    if filter_sources:
        print(f"[filter] sources={sorted(filter_sources)}")
    if date_from or date_to:
        print(f"[filter] date range={date_from or '*'} .. {date_to or '*'}")

    container_client: ContainerClient = svc.get_container_client(container)

    # Counters (atomic-ish via Lock)
    lock = threading.Lock()
    per_source_count: dict[str, int] = defaultdict(int)
    per_source_bytes: dict[str, int] = defaultdict(int)
    per_pair_count: dict[tuple[str, str], int] = defaultdict(int)
    failed: list[tuple[str, str]] = []
    uploaded = 0
    uploaded_bytes = 0
    started = time.monotonic()
    last_progress = started

    def _upload(name: str, data: bytes, source: str, date: str) -> None:
        nonlocal uploaded, uploaded_bytes, last_progress
        try:
            container_client.upload_blob(name=name, data=data, overwrite=True)
        except Exception as e:  # noqa: BLE001
            with lock:
                failed.append((name, str(e)[:200]))
            return
        with lock:
            uploaded += 1
            uploaded_bytes += len(data)
            per_source_count[source] += 1
            per_source_bytes[source] += len(data)
            per_pair_count[(source, date)] += 1
            now = time.monotonic()
            if uploaded % 500 == 0 or now - last_progress > 10:
                elapsed = now - started
                rate = uploaded / elapsed if elapsed else 0
                print(
                    f"  ... uploaded {uploaded:>6} blobs "
                    f"({uploaded_bytes/1e6:>7.1f} MB, {rate:>5.1f} blob/s) "
                    + " ".join(f"{s}={c}" for s, c in sorted(per_source_count.items()))
                )
                last_progress = now

    skipped_filter = 0
    skipped_other = 0
    futures: list[Future] = []
    with ThreadPoolExecutor(max_workers=workers) as pool, \
            urllib.request.urlopen(seed_url) as resp, \
            tarfile.open(fileobj=resp, mode="r|gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            f = tar.extractfile(member)
            if f is None:
                skipped_other += 1
                continue

            source, date_str = parse_layout(member.name)
            # Filter
            if filter_sources and (source is None or source not in filter_sources):
                skipped_filter += 1
                f.close() if hasattr(f, "close") else None
                continue
            if date_str and (date_from or date_to):
                try:
                    d = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    d = None
                if d is not None:
                    if date_from and d < date_from:
                        skipped_filter += 1
                        continue
                    if date_to and d > date_to:
                        skipped_filter += 1
                        continue

            data = f.read()
            blob_name = f"{prefix}{member.name}" if prefix else member.name
            futures.append(
                pool.submit(_upload, blob_name, data, source or "<root>", date_str or "<none>")
            )

            # Back-pressure: cap in-flight futures so we don't buffer the whole tar in RAM
            if len(futures) >= workers * 8:
                # Drain completed ones
                futures = [fut for fut in futures if not fut.done()]
                if len(futures) >= workers * 8:
                    futures[0].result()  # block until at least one finishes
                    futures = [fut for fut in futures if not fut.done()]

        # Wait for remaining
        for fut in futures:
            fut.result()

    elapsed = time.monotonic() - started
    print()
    print(f"[done] uploaded {uploaded} blobs ({uploaded_bytes/1e6:.1f} MB) in {elapsed:.1f}s "
          f"({uploaded/elapsed:.1f} blob/s)")
    if skipped_filter:
        print(f"       skipped (filter): {skipped_filter}")
    if skipped_other:
        print(f"       skipped (non-file/empty): {skipped_other}")
    if failed:
        print(f"       FAILED: {len(failed)}")
        for n, msg in failed[:10]:
            print(f"         - {n}: {msg}")
        if len(failed) > 10:
            print(f"         ... and {len(failed) - 10} more")

    # Per-source / per-date summary
    print("\n[summary by source]")
    print(f"  {'source':<12} {'blobs':>8} {'MB':>10}  dates")
    for source in sorted(per_source_count):
        dates = sorted({d for (s, d) in per_pair_count if s == source})
        date_summary = (
            f"{len(dates)} dates ({dates[0]} .. {dates[-1]})" if dates else "(no date)"
        )
        print(f"  {source:<12} {per_source_count[source]:>8} "
              f"{per_source_bytes[source]/1e6:>10.1f}  {date_summary}")

    return uploaded


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--seed-url", default=DEFAULT_SEED_URL,
                   help="Full SAS URL to the .tar.gz seed archive (env: SEED_URL).")
    p.add_argument("--dest-account", required=True,
                   help="Destination storage account name (the new deployment).")
    p.add_argument("--dest-container", default="raw-documents")
    p.add_argument("--prefix", default="",
                   help="Optional blob name prefix (e.g. 'seed/').")
    p.add_argument("--workers", type=int, default=24,
                   help="Parallel upload workers (default: 24).")
    p.add_argument("--filter-source", default="",
                   help="Comma-separated source folder names to include "
                        "(e.g. 'prec,detc'). Default: all.")
    p.add_argument("--filter-date-from", default="",
                   help="Only include date folders >= this YYYY-MM-DD.")
    p.add_argument("--filter-date-to", default="",
                   help="Only include date folders <= this YYYY-MM-DD.")
    args = p.parse_args()

    if "?" not in args.seed_url:
        print("⚠️  SEED_URL has no SAS query string — public anonymous access is "
              "disabled on pubzip; download will likely 403. Use the SAS URL "
              "printed by scripts/bundle_seed_data.py.", file=sys.stderr)

    filter_sources = {s.strip() for s in args.filter_source.split(",") if s.strip()} or None
    date_from = _parse_date(args.filter_date_from)
    date_to = _parse_date(args.filter_date_to)

    svc = ensure_container(args.dest_account, args.dest_container)
    stream_extract_upload(
        args.seed_url, svc, args.dest_container, args.prefix,
        workers=args.workers,
        filter_sources=filter_sources,
        date_from=date_from,
        date_to=date_to,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
