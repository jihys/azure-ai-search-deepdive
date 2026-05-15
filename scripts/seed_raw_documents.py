"""
Seed a freshly-deployed `raw-documents` container from the prebuilt seed
archive hosted on `pubzip0513143342`.

The archive is a single `.tar.gz` containing the original blob layout of
`stragidyn6dtfun6/raw-documents/`. It is published once via
`scripts/bundle_seed_data.py` and exposed through a **User Delegation SAS**
URL (read-only, max 7-day TTL).

Flow:
  1. Stream-download the tar.gz from SEED_URL (no full file on disk).
  2. Iterate tar members and upload each as a blob to the destination
     container using the caller's AAD identity.

Prereq: caller must hold `Storage Blob Data Contributor` on the destination
account (`az login` first).

Usage:
  # SEED_URL is the SAS URL printed by bundle_seed_data.py
  export SEED_URL='https://pubzip0513143342.blob.core.windows.net/seed/raw-documents-seed.tar.gz?...'
  uv run python scripts/seed_raw_documents.py \
      --dest-account stragiabcd1234ef \
      --dest-container raw-documents
"""
from __future__ import annotations

import argparse
import os
import sys
import tarfile
import urllib.request

from azure.identity import AzureCliCredential
from azure.storage.blob import BlobServiceClient

# Default seed URL: replace via SEED_URL env var or --seed-url after re-publishing.
# (The SAS query string is required — anonymous access is disabled by tenant policy.)
DEFAULT_SEED_URL = os.environ.get(
    "SEED_URL",
    "https://pubzip0513143342.blob.core.windows.net/seed/raw-documents-seed.tar.gz",
)


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


def stream_extract_upload(
    seed_url: str, svc: BlobServiceClient, container: str, prefix: str = "",
) -> int:
    """Stream tar.gz directly from SEED_URL → upload each member as a blob.

    Uses a streaming tarfile reader ('r|gz') so the archive is never fully
    buffered on disk. Each member's bytes are read into memory once and
    uploaded.
    """
    masked = seed_url.split("?", 1)[0] + ("?<sas>" if "?" in seed_url else "")
    print(f"[stream] {masked}")
    container_client = svc.get_container_client(container)

    count = 0
    skipped = 0
    total_bytes = 0
    with urllib.request.urlopen(seed_url) as resp, \
            tarfile.open(fileobj=resp, mode="r|gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            f = tar.extractfile(member)
            if f is None:
                skipped += 1
                continue
            data = f.read()
            blob_name = f"{prefix}{member.name}" if prefix else member.name
            container_client.upload_blob(name=blob_name, data=data, overwrite=True)
            count += 1
            total_bytes += len(data)
            if count % 500 == 0:
                print(f"  ... uploaded {count} blobs ({total_bytes/1e6:.1f} MB)")
    print(f"[done] uploaded {count} blobs ({total_bytes/1e6:.1f} MB), skipped {skipped}")
    return count


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--seed-url", default=DEFAULT_SEED_URL,
                   help="Full SAS URL to the .tar.gz seed archive (env: SEED_URL).")
    p.add_argument("--dest-account", required=True,
                   help="Destination storage account name (the new deployment).")
    p.add_argument("--dest-container", default="raw-documents")
    p.add_argument("--prefix", default="",
                   help="Optional blob name prefix (e.g. 'seed/').")
    args = p.parse_args()

    if "?" not in args.seed_url:
        print("⚠️  SEED_URL has no SAS query string — public anonymous access is "
              "disabled on pubzip; download will likely 403. Use the SAS URL "
              "printed by scripts/bundle_seed_data.py.", file=sys.stderr)

    svc = ensure_container(args.dest_account, args.dest_container)
    stream_extract_upload(args.seed_url, svc, args.dest_container, args.prefix)
    return 0


if __name__ == "__main__":
    sys.exit(main())
