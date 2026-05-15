"""
ZIP 샘플 추출 + 파일 타입 필터 + Blob 업로드

ZIP 내부를 풀지 않고 스트리밍하여 확장자별로 필터링/샘플링 후 Blob에 업로드합니다.

업로드 경로:
  {container}/raw/{ext}/{source}/{filename}
  예) raw-documents/raw/pdf/ST/ST_0008_0001104.pdf
      raw-documents/raw/pptx/ST/ST_0008_0001104.pptx

예시:
  uv run python scripts/sample_zip_to_blob.py \
    --zip data/raw/zips/TS_ST.zip --source ST \
    --ext pdf --sample 100

  # PDF + PPTX 모두
  uv run python scripts/sample_zip_to_blob.py \
    --zip data/raw/zips/TS_ST.zip --source ST \
    --ext pdf,pptx --sample 100
"""

from __future__ import annotations

import argparse
import io
import os
import random
import zipfile
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--zip", required=True, help="ZIP file path")
    p.add_argument("--source", required=True, help="Source label (ST/SS/HA)")
    p.add_argument("--ext", default="pdf", help="Comma-separated extensions to include (e.g. pdf,pptx)")
    p.add_argument("--sample", type=int, default=100, help="Sample N files per extension (0 = all)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--container", default=os.getenv("AZURE_STORAGE_CONTAINER_NAME", "raw-documents"))
    p.add_argument("--storage-account", default=os.getenv("AZURE_STORAGE_ACCOUNT_NAME", ""))
    p.add_argument("--prefix-root", default="raw", help="Top-level prefix in container")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    if not args.storage_account:
        raise SystemExit("AZURE_STORAGE_ACCOUNT_NAME is required")

    zip_path = Path(args.zip)
    if not zip_path.is_file():
        raise SystemExit(f"ZIP not found: {zip_path}")

    allowed_exts = {f".{e.strip().lower().lstrip('.')}" for e in args.ext.split(",") if e.strip()}
    print(f"[filter] extensions: {sorted(allowed_exts)}")

    # ── 1) ZIP 멤버 분류 (스트리밍, 압축 해제 X) ──
    by_ext: dict[str, list[zipfile.ZipInfo]] = {e: [] for e in allowed_exts}
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            ext = Path(info.filename).suffix.lower()
            if ext in allowed_exts:
                by_ext[ext].append(info)

    print(f"[scan] {zip_path.name}")
    for ext, items in by_ext.items():
        print(f"  {ext}: {len(items)} files")

    # ── 2) 샘플링 ──
    rng = random.Random(args.seed)
    selected: list[tuple[str, zipfile.ZipInfo]] = []  # (ext, info)
    for ext, items in by_ext.items():
        if args.sample and len(items) > args.sample:
            picked = rng.sample(items, args.sample)
        else:
            picked = items
        for info in picked:
            selected.append((ext, info))
        print(f"[sample] {ext}: {len(picked)} selected")

    if args.dry_run:
        print(f"[dry-run] would upload {len(selected)} files")
        for ext, info in selected[:5]:
            name = Path(info.filename).name
            print(f"  -> {args.prefix_root}/{ext.lstrip('.')}/{args.source}/{name}")
        return

    # ── 3) Blob 업로드 (스트리밍) ──
    cred = DefaultAzureCredential()
    bsc = BlobServiceClient(
        account_url=f"https://{args.storage_account}.blob.core.windows.net",
        credential=cred,
    )
    container = bsc.get_container_client(args.container)
    try:
        container.create_container()
        print(f"[blob] container created: {args.container}")
    except Exception:
        pass

    uploaded = 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        for ext, info in selected:
            fname = Path(info.filename).name
            file_type = ext.lstrip('.')
            blob_name = f"{args.prefix_root}/{file_type}/{args.source}/{fname}"
            with zf.open(info, "r") as src:
                data = src.read()
            # 사용자 메타데이터 — 인덱서가 metadata_<key> 로 enrichment 후 filterable 필드 매핑에 사용
            metadata = {
                "file_type": file_type,        # pdf | pptx
                "source_category": args.source, # ST | SS | HA
            }
            container.upload_blob(
                name=blob_name,
                data=io.BytesIO(data),
                overwrite=True,
                length=len(data),
                metadata=metadata,
            )
            uploaded += 1
            if uploaded % 20 == 0:
                print(f"  [{uploaded}/{len(selected)}] {blob_name}")

    print(f"[done] uploaded {uploaded} files from {zip_path.name}")


if __name__ == "__main__":
    main()
