"""
멀티모달 원천 데이터 준비 스크립트 (Step 1~2)

기능:
1) data/raw_pdf/*.zip 압축 해제
2) 파일 유형 분류(PDF/PPTX/이미지/기타)
3) Blob Storage raw/{pdf|pptx|image|other}/{source}/ 경로 업로드

예시:
  uv run python scripts/prepare_multimodal_raw_dataset.py \
    --source st \
    --zip-glob "data/raw_pdf/*.zip" \
    --container raw-documents
"""

from __future__ import annotations

import argparse
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

PDF_EXT = {".pdf"}
PPTX_EXT = {".pptx"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}


@dataclass
class FileRecord:
    local_path: Path
    category: str
    relative_name: str


def _detect_category(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in PDF_EXT:
        return "pdf"
    if ext in PPTX_EXT:
        return "pptx"
    if ext in IMAGE_EXT:
        return "image"
    return "other"


def _safe_member_name(member_name: str) -> str:
    # ZIP 내부 절대경로(/foo/bar.pdf) 방지 및 상위 경로 탈출 방지
    normalized = member_name.replace("\\", "/").lstrip("/")
    normalized = "/".join(part for part in normalized.split("/") if part not in {"", ".", ".."})
    return normalized


def extract_zip(zip_path: Path, extract_root: Path, source: str) -> list[Path]:
    target_dir = extract_root / source / zip_path.stem
    target_dir.mkdir(parents=True, exist_ok=True)

    extracted_files: list[Path] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue
            safe_name = _safe_member_name(member.filename)
            if not safe_name:
                continue
            out_path = target_dir / safe_name
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member, "r") as src, open(out_path, "wb") as dst:
                dst.write(src.read())
            extracted_files.append(out_path)

    return extracted_files


def build_records(files: list[Path], source: str, keep_subdirs: bool) -> list[FileRecord]:
    records: list[FileRecord] = []
    for f in files:
        category = _detect_category(f)
        if keep_subdirs:
            rel = f.name if f.parent.name == f.stem else str(f).split("/", 1)[-1]
            rel_name = f.as_posix().split("/", 1)[-1]
            rel_name = rel_name.split("/", 1)[-1] if "/" in rel_name else f.name
        else:
            rel_name = f.name

        records.append(FileRecord(local_path=f, category=category, relative_name=rel_name))
    return records


def upload_records(
    account_name: str,
    container_name: str,
    records: list[FileRecord],
    source: str,
    dry_run: bool,
) -> None:
    credential = DefaultAzureCredential()
    blob_service = BlobServiceClient(
        account_url=f"https://{account_name}.blob.core.windows.net",
        credential=credential,
    )

    container = blob_service.get_container_client(container_name)
    try:
        container.create_container()
        print(f"[info] container created: {container_name}")
    except Exception:
        print(f"[info] container exists: {container_name}")

    for rec in records:
        blob_name = f"raw/{rec.category}/{source}/{rec.relative_name}"
        if dry_run:
            print(f"[dry-run] {rec.local_path} -> {blob_name}")
            continue

        with open(rec.local_path, "rb") as fp:
            container.upload_blob(name=blob_name, data=fp, overwrite=True)
        print(f"[uploaded] {blob_name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare ZIP dataset and upload to raw/* paths in Blob.")
    parser.add_argument("--zip-glob", default="data/raw_pdf/*.zip", help="ZIP file glob pattern")
    parser.add_argument("--extract-dir", default="data/raw_unpacked", help="Local extraction directory")
    parser.add_argument("--source", default="st", help="Source label under raw/<type>/{source}/")
    parser.add_argument("--container", default=os.getenv("AZURE_STORAGE_CONTAINER_NAME", "raw-documents"))
    parser.add_argument("--storage-account", default=os.getenv("AZURE_STORAGE_ACCOUNT_NAME", ""))
    parser.add_argument("--dry-run", action="store_true", help="Analyze only, do not upload")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    if not args.storage_account:
        raise ValueError("AZURE_STORAGE_ACCOUNT_NAME (or --storage-account) is required.")

    zip_files = sorted(Path(".").glob(args.zip_glob))
    if not zip_files:
        raise FileNotFoundError(f"No ZIP files found for pattern: {args.zip_glob}")

    extract_root = Path(args.extract_dir)
    all_files: list[Path] = []

    print(f"[step1] ZIP discovery: {len(zip_files)} file(s)")
    for z in zip_files:
        print(f"  - {z}")

    print("[step2] unzip and classify")
    for z in zip_files:
        extracted = extract_zip(z, extract_root, args.source)
        print(f"  - {z.name}: extracted {len(extracted)} files")
        all_files.extend(extracted)

    records = build_records(all_files, args.source, keep_subdirs=False)

    stats: dict[str, int] = {"pdf": 0, "pptx": 0, "image": 0, "other": 0}
    for r in records:
        stats[r.category] += 1

    print("[summary] extracted file counts")
    print(f"  pdf   : {stats['pdf']}")
    print(f"  pptx  : {stats['pptx']}")
    print(f"  image : {stats['image']}")
    print(f"  other : {stats['other']}")

    print("[step3] upload to blob raw/<category>/<source>/")
    upload_records(
        account_name=args.storage_account,
        container_name=args.container,
        records=records,
        source=args.source,
        dry_run=args.dry_run,
    )

    print("[done] dataset preparation complete")


if __name__ == "__main__":
    main()
