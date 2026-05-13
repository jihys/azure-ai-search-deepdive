"""
Schema-aware chunker for Korean legal documents from law.go.kr.

Source schemas (raw-documents/{source}/{date}/{seq}.json):
  prec    : 판례        - 사건명, 법원명, 선고일자, 사건번호, 판시사항, 판결요지, 참조조문, 참조판례, 전문, url
  detc    : 헌재결정례   - 사건명, 재판부, 사건번호, 결정일자, 판시사항, 결정요지, 심판대상조문, 참조조문, 참조판례, 전문, url
  expc    : 법제처해석례 - 제목, 문서번호, 회시일자, 요청기관, 질의요지, 회답, 이유, url
  admrul  : 행정심판재결례- 사건명, 사건번호, 재결일자, 재결기관, 재결결과, 재결요지, 주문, 청구취지, 이유, url

Output (processed-documents/{source}/{date}/{seq}.jsonl) — one JSON object per line:
  {
    "id": "{source}_{seq}_{chunk_index}",
    "source": "prec",
    "seq": "100007",
    "title": "...",
    "case_number": "...",
    "court": "...",
    "doc_date": "1984-12-26T00:00:00Z",
    "summary": "판시사항 + 판결요지",
    "url": "...",
    "chunk_index": 0,
    "total_chunks": 4,
    "content": "<chunked text>",
    "source_file": "prec/2026-05-12/prec_100007.json"
  }
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

CHUNK_SIZE = 1800
CHUNK_OVERLAP = 200
MIN_TAIL = 200  # if remaining text smaller than this, fold into previous chunk


@dataclass(frozen=True)
class FieldMap:
    title: tuple[str, ...]
    case_number: tuple[str, ...]
    date: tuple[str, ...]
    court: tuple[str, ...]
    summary: tuple[str, ...]
    body: tuple[str, ...]


SCHEMAS: dict[str, FieldMap] = {
    "prec": FieldMap(
        title=("사건명",),
        case_number=("사건번호",),
        date=("선고일자",),
        court=("법원명",),
        summary=("판시사항", "판결요지"),
        body=("전문", "참조조문", "참조판례"),
    ),
    "detc": FieldMap(
        title=("사건명",),
        case_number=("사건번호",),
        date=("결정일자",),
        court=("재판부",),
        summary=("판시사항", "결정요지"),
        body=("전문", "심판대상조문", "참조조문", "참조판례"),
    ),
    "expc": FieldMap(
        title=("제목",),
        case_number=("문서번호",),
        date=("회시일자",),
        court=("요청기관",),
        summary=("질의요지", "회답"),
        body=("이유",),
    ),
    "admrul": FieldMap(
        title=("사건명",),
        case_number=("사건번호",),
        date=("재결일자",),
        court=("재결기관",),
        summary=("재결요지", "주문", "청구취지"),
        body=("이유",),
    ),
}


def _norm(text: str | None) -> str:
    if not text:
        return ""
    s = str(text)
    s = re.sub(r"[\u200b\ufeff\u00a0]", " ", s)
    s = re.sub(r"\s+\n", "\n", s)
    s = re.sub(r"\n\s+", "\n", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _normalize_date(value: str | None) -> str | None:
    """Return ISO datetime string with Z, or None if unparseable."""
    if not value:
        return None
    v = str(value).strip()
    if not v:
        return None
    # Already ISO?
    try:
        # tolerate "...Z"
        if v.endswith("Z"):
            datetime.fromisoformat(v.replace("Z", "+00:00"))
            return v
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass
    # try YYYYMMDD or YYYY-MM-DD
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(v, fmt).replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            continue
    return None


def _join_fields(doc: dict, fields: Iterable[str], sep: str = "\n\n") -> str:
    parts: list[str] = []
    for f in fields:
        v = _norm(doc.get(f))
        if v:
            parts.append(f"[{f}] {v}")
    return sep.join(parts)


def _split_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        # Try to break on whitespace/newline near the end
        if end < n:
            window_start = max(start + int(size * 0.6), start + 1)
            cut = -1
            for i in range(end, window_start, -1):
                if text[i] in "\n":
                    cut = i + 1
                    break
            if cut == -1:
                for i in range(end, window_start, -1):
                    if text[i] in " \t":
                        cut = i + 1
                        break
            if cut != -1:
                end = cut
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    # Fold small tail into previous
    if len(chunks) >= 2 and len(chunks[-1]) < MIN_TAIL:
        chunks[-2] = (chunks[-2] + "\n\n" + chunks[-1]).strip()
        chunks.pop()
    return chunks


def build_records(
    *,
    source: str,
    seq: str,
    raw_doc: dict,
    source_file: str,
) -> list[dict]:
    """Build chunk records for a single legal document.

    Returns list of dicts ready for JSONL serialization / AI Search ingestion.
    """
    if source not in SCHEMAS:
        raise ValueError(f"Unknown source: {source}")
    schema = SCHEMAS[source]

    title = _norm(_first_str(raw_doc, schema.title))
    case_number = _norm(_first_str(raw_doc, schema.case_number))
    court = _norm(_first_str(raw_doc, schema.court))
    doc_date = _normalize_date(_first_str(raw_doc, schema.date))
    url = _norm(raw_doc.get("url"))

    summary_text = _join_fields(raw_doc, schema.summary)
    body_text = _join_fields(raw_doc, schema.body)

    # Combined text for chunking: title + summary + body
    head_parts: list[str] = []
    if title:
        head_parts.append(f"제목: {title}")
    if case_number:
        head_parts.append(f"사건번호: {case_number}")
    if court:
        head_parts.append(f"기관: {court}")
    head = " | ".join(head_parts)

    full_text_parts: list[str] = []
    if head:
        full_text_parts.append(head)
    if summary_text:
        full_text_parts.append(summary_text)
    if body_text:
        full_text_parts.append(body_text)
    full_text = "\n\n".join(full_text_parts).strip()

    if not full_text:
        return []

    chunks = _split_text(full_text)
    total = len(chunks)
    records: list[dict] = []
    for i, chunk in enumerate(chunks):
        records.append({
            "id": f"{source}_{seq}_{i}",
            "source": source,
            "seq": str(seq),
            "title": title or None,
            "case_number": case_number or None,
            "court": court or None,
            "doc_date": doc_date,
            "summary": summary_text or None,
            "url": url or None,
            "chunk_index": i,
            "total_chunks": total,
            "content": chunk,
            "source_file": source_file,
        })
    return records


def _first_str(doc: dict, keys: Iterable[str]) -> str:
    for k in keys:
        v = doc.get(k)
        if v:
            return str(v)
    return ""


__all__ = ["build_records", "SCHEMAS", "CHUNK_SIZE", "CHUNK_OVERLAP"]
