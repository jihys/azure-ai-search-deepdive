"""
Mirror Sweden raw-documents (crawled JSON) into a public-zip storage account
using **azcopy server-to-server copy** (no local download/tar).

Tenant policy disallows shared-key auth and anonymous public blobs, so:
  - Both endpoints authenticate with the caller's AAD identity via
    AZCOPY_AUTO_LOGIN_TYPE=AZCLI (reuses `az login` token).
  - After the copy, a container-level **User Delegation SAS** (read+list,
    max 7 days) is printed so workshop participants can pull from
    `pubzip0513143342/raw-documents-seed/` via `seed_raw_documents.py`.

Prereq: caller must hold `Storage Blob Data Contributor` on BOTH source
(`stragidyn6dtfun6`) and dest (`pubzip0513143342`).

Usage:
  uv run python scripts/bundle_seed_data.py \
      --source-account stragidyn6dtfun6 \
      --source-container raw-documents \
      --dest-account pubzip0513143342 \
      --dest-container raw-documents-seed
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys

from azure.identity import AzureCliCredential
from azure.storage.blob import (
    BlobServiceClient,
    ContainerSasPermissions,
    generate_container_sas,
)


def _run_az(args: list[str]) -> str:
    cmd = ["az", *args]
    print(f"  $ {' '.join(cmd)}")
    use_shell = os.name == "nt"
    if use_shell:
        return subprocess.check_output(" ".join(cmd), text=True, shell=True).strip()
    return subprocess.check_output(cmd, text=True).strip()


def _resolve_azcopy() -> str:
    az = shutil.which("azcopy")
    if az:
        return az
    candidate = os.path.expanduser("~/bin/azcopy.exe" if os.name == "nt" else "~/bin/azcopy")
    if os.path.exists(candidate):
        return candidate
    raise RuntimeError(
        "azcopy not found. Install from https://aka.ms/downloadazcopy-v10-windows "
        "and place on PATH (or in ~/bin)."
    )


def _run_azcopy(args: list[str]) -> None:
    azcopy = _resolve_azcopy()
    env = os.environ.copy()
    env["AZCOPY_AUTO_LOGIN_TYPE"] = "AZCLI"
    cmd = [azcopy, *args]
    print(f"  $ {' '.join(cmd)}")
    subprocess.check_call(cmd, env=env)


def ensure_dest_public(dest_account: str) -> None:
    print(f"[dest] Configuring {dest_account} ...")
    rg = _run_az([
        "storage", "account", "show",
        "--name", dest_account, "--query", "resourceGroup", "-o", "tsv",
    ])
    _run_az([
        "storage", "account", "update", "-n", dest_account, "-g", rg,
        "--public-network-access", "Enabled",
        "--default-action", "Allow",
        "-o", "none",
    ])


def ensure_container(account: str, container: str) -> None:
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


def azcopy_mirror(
    source_account: str, source_container: str,
    dest_account: str, dest_container: str,
) -> None:
    """Server-to-server recursive copy. No bytes flow through this machine."""
    src_url = f"https://{source_account}.blob.core.windows.net/{source_container}"
    dst_url = f"https://{dest_account}.blob.core.windows.net/{dest_container}"
    print(f"[azcopy] {src_url}  =>  {dst_url}")
    _run_azcopy([
        "copy", f"{src_url}/*", f"{dst_url}/",
        "--recursive=true",
        "--overwrite=true",
        "--s2s-preserve-access-tier=false",
    ])


def build_container_sas_url(
    dest_account: str, dest_container: str, days: int = 7,
) -> str:
    """Container-level User Delegation SAS (read + list). Max 7 days."""
    cred = AzureCliCredential()
    svc = BlobServiceClient(
        account_url=f"https://{dest_account}.blob.core.windows.net",
        credential=cred,
    )
    now = dt.datetime.now(dt.timezone.utc)
    days = min(days, 7)
    expiry = now + dt.timedelta(days=days)
    udk = svc.get_user_delegation_key(
        key_start_time=now - dt.timedelta(minutes=5),
        key_expiry_time=expiry,
    )
    sas = generate_container_sas(
        account_name=dest_account,
        container_name=dest_container,
        user_delegation_key=udk,
        permission=ContainerSasPermissions(read=True, list=True),
        expiry=expiry,
    )
    return f"https://{dest_account}.blob.core.windows.net/{dest_container}?{sas}"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source-account", default=os.environ.get("SRC_ACCOUNT", "stragidyn6dtfun6"))
    p.add_argument("--source-container", default="raw-documents")
    p.add_argument("--dest-account", default="pubzip0513143342")
    p.add_argument("--dest-container", default="raw-documents-seed")
    p.add_argument("--sas-days", type=int, default=7,
                   help="User Delegation SAS validity in days (max 7).")
    p.add_argument("--skip-acl", action="store_true",
                   help="Skip enabling public-network on dest (assumes already on).")
    args = p.parse_args()

    if not args.skip_acl:
        ensure_dest_public(args.dest_account)

    ensure_container(args.dest_account, args.dest_container)
    azcopy_mirror(
        args.source_account, args.source_container,
        args.dest_account, args.dest_container,
    )

    sas_url = build_container_sas_url(
        args.dest_account, args.dest_container, days=args.sas_days,
    )
    print("\n" + "=" * 78)
    print(f"[ok] SEED CONTAINER URL (User Delegation SAS, valid {min(args.sas_days, 7)} days):")
    print(sas_url)
    print("=" * 78)
    print("Pass to seed_raw_documents.py via --seed-url or env SEED_URL.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
