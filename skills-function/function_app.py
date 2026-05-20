"""
Azure Function App - AI Search Custom Skills
Azure Functions Python v2 프로그래밍 모델

Custom Web API Skills for AI Search Indexer:
  1. /api/markdown_split   — Markdown 헤더(+길이) 기반 텍스트 분할 (PDF basic 파이프라인)
  2. /api/pptx_page_split  — PPTX `<!-- PageBreak -->` 기반 슬라이드 단위 분할 (PPTX basic 파이프라인)
  3. /api/verbalize        — GPT-5.4 Vision으로 PDF 이미지/도표 설명 생성 (Verbalized 파이프라인)

배포 후 AI Search Skillset에서 Custom Web API Skill로 연결하여 사용.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import azure.functions as func
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from openai import AzureOpenAI

try:
    import fitz  # PyMuPDF — 페이지 단위 PDF 분할용
    _HAS_FITZ = True
except Exception:  # pragma: no cover
    fitz = None
    _HAS_FITZ = False

# 병렬화 파라미터
VERBALIZE_PAGE_WORKERS = int(os.environ.get("VERBALIZE_PAGE_WORKERS", "8"))
VERBALIZE_RECORD_WORKERS = int(os.environ.get("VERBALIZE_RECORD_WORKERS", "4"))
VERBALIZE_PAGE_CHAR_LIMIT = int(os.environ.get("VERBALIZE_PAGE_CHAR_LIMIT", "8000"))

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# ── 환경 변수 ────────────────────────────────────────────────
OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
GPT54_DEPLOYMENT = os.environ.get("AZURE_OPENAI_GPT54_DEPLOYMENT", "gpt-5.4")
DI_ENDPOINT = os.environ.get("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")

# Markdown split 기본 설정
DEFAULT_MAX_CHUNK_CHARS = 2000
DEFAULT_OVERLAP_CHARS = 200


def _get_openai_client() -> AzureOpenAI:
    """Managed Identity 기반 Azure OpenAI 클라이언트."""
    credential = ManagedIdentityCredential()
    token = credential.get_token("https://cognitiveservices.azure.com/.default")
    return AzureOpenAI(
        azure_endpoint=OPENAI_ENDPOINT,
        api_version="2024-12-01-preview",
        azure_ad_token=token.token,
    )


# ══════════════════════════════════════════════════════════════
# Skill 1: Markdown Header Split
# ══════════════════════════════════════════════════════════════

def _coerce_text(value) -> str:
    """DI Layout oneToMany 모드는 markdown을 list로 반환 → 하나로 합칩"""
    if value is None:
        return ""
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                # 일부 스킬은 {"content": "..."} 형태로 반환
                parts.append(str(item.get("content") or item.get("text") or ""))
            else:
                parts.append(str(item))
        return "\n\n<!-- PageBreak -->\n\n".join(p for p in parts if p)
    return str(value)


def _split_by_markdown_headers(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    """
    Markdown 텍스트를 헤더(#, ##, ###) 기준으로 분할.
    각 섹션이 max_chars를 초과하면 문자 수 기반으로 추가 분할.
    """
    if not text or not text.strip():
        return []

    # 헤더 패턴: # ~ ### 수준까지
    header_pattern = re.compile(r"^(#{1,3})\s+", re.MULTILINE)

    # 헤더 위치 찾기
    splits = []
    positions = [m.start() for m in header_pattern.finditer(text)]

    if not positions:
        # 헤더가 없으면 전체 텍스트를 문자 수로 분할
        return _split_by_chars(text, max_chars, overlap_chars)

    # 첫 헤더 이전 내용이 있으면 포함
    if positions[0] > 0:
        preamble = text[: positions[0]].strip()
        if preamble:
            splits.append(preamble)

    # 각 헤더 섹션 추출
    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        section = text[pos:end].strip()
        if section:
            splits.append(section)

    # 각 섹션이 max_chars 초과 시 문자 수 기반 추가 분할
    final_chunks = []
    for section in splits:
        if len(section) <= max_chars:
            final_chunks.append(section)
        else:
            sub_chunks = _split_by_chars(section, max_chars, overlap_chars)
            final_chunks.extend(sub_chunks)

    return final_chunks


def _split_by_chars(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    """문자 수 기반 분할 (문장 경계 우선)."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars

        if end >= len(text):
            chunks.append(text[start:].strip())
            break

        # 문장 경계에서 분할 시도 (마지막 마침표/줄바꿈 찾기)
        boundary = text.rfind("\n", start + max_chars // 2, end)
        if boundary == -1:
            boundary = text.rfind(". ", start + max_chars // 2, end)
        if boundary == -1:
            boundary = text.rfind(" ", start + max_chars // 2, end)
        if boundary == -1:
            boundary = end

        chunk = text[start : boundary + 1].strip()
        if chunk:
            chunks.append(chunk)

        # overlap 적용
        start = max(boundary + 1 - overlap_chars, start + 1)

    return chunks


@app.route(route="markdown_split", methods=["POST"])
def markdown_split(req: func.HttpRequest) -> func.HttpResponse:
    """
    AI Search Custom Web API Skill: Markdown 헤더 기반 분할

    Request body (AI Search format):
    {
        "values": [
            {
                "recordId": "1",
                "data": {
                    "text": "# Title\n## Section 1\n...",
                    "max_chunk_chars": 2000,
                    "overlap_chars": 200
                }
            }
        ]
    }

    Response:
    {
        "values": [
            {
                "recordId": "1",
                "data": { "chunks": ["# Title\n...", "## Section 1\n..."] },
                "errors": [],
                "warnings": []
            }
        ]
    }
    """
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"values": []}),
            status_code=400,
            mimetype="application/json",
        )

    results = []
    for record in body.get("values", []):
        record_id = record.get("recordId", "")
        data = record.get("data", {})
        text = _coerce_text(data.get("text", ""))
        max_chars = int(data.get("max_chunk_chars", DEFAULT_MAX_CHUNK_CHARS))
        overlap = int(data.get("overlap_chars", DEFAULT_OVERLAP_CHARS))

        try:
            chunks = _split_by_markdown_headers(text, max_chars, overlap)
            results.append({
                "recordId": record_id,
                "data": {"chunks": chunks},
                "errors": [],
                "warnings": [],
            })
        except Exception as e:
            logging.error(f"markdown_split error for record {record_id}: {e}")
            results.append({
                "recordId": record_id,
                "data": {"chunks": [text] if text else []},
                "errors": [{"message": str(e)}],
                "warnings": [],
            })

    return func.HttpResponse(
        json.dumps({"values": results}),
        status_code=200,
        mimetype="application/json",
    )


# ══════════════════════════════════════════════════════════════
# Skill 1b: PPTX Page Split (slide-level)
# ══════════════════════════════════════════════════════════════

# DI Layout이 PPTX를 markdown으로 변환할 때 슬라이드 경계에 삽입하는 마커
_PPTX_PAGE_BREAK_RE = re.compile(r"<!--\s*PageBreak\s*-->", re.IGNORECASE)


def _split_by_pptx_pages(text: str, max_chars: int) -> list[str]:
    """
    DI Layout markdown의 <!-- PageBreak --> 마커로 PPTX 슬라이드 단위 분할.
    페이지 마커가 없으면 전체를 한 chunk로 반환.
    한 슬라이드가 max_chars를 초과하면 char 기반으로 안전 분할.
    """
    if not text or not text.strip():
        return []

    pages = _PPTX_PAGE_BREAK_RE.split(text)
    pages = [p.strip() for p in pages if p and p.strip()]

    if not pages:
        return []

    final: list[str] = []
    for idx, page in enumerate(pages, start=1):
        # 슬라이드 헤더 부착으로 검색/추적성 개선
        labeled = f"<!-- Slide {idx} -->\n{page}"
        if len(labeled) <= max_chars:
            final.append(labeled)
        else:
            final.extend(_split_by_chars(labeled, max_chars, overlap_chars=0))
    return final


@app.route(route="pptx_page_split", methods=["POST"])
def pptx_page_split(req: func.HttpRequest) -> func.HttpResponse:
    """
    AI Search Custom Web API Skill: PPTX 슬라이드(페이지) 단위 분할.

    Input  : { "text": "<DI markdown w/ <!-- PageBreak --> markers>", "max_chunk_chars": 4000 }
    Output : { "chunks": ["<!-- Slide 1 -->\n...", "<!-- Slide 2 -->\n...", ...] }
    """
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"values": []}), status_code=400, mimetype="application/json"
        )

    results = []
    for record in body.get("values", []):
        record_id = record.get("recordId", "")
        data = record.get("data", {})
        text = _coerce_text(data.get("text", ""))
        # PPTX는 슬라이드당 텍스트가 작아 max를 더 크게 둔다
        max_chars = int(data.get("max_chunk_chars", 4000))

        try:
            chunks = _split_by_pptx_pages(text, max_chars)
            results.append({
                "recordId": record_id,
                "data": {"chunks": chunks},
                "errors": [],
                "warnings": [],
            })
        except Exception as e:
            logging.error(f"pptx_page_split error for record {record_id}: {e}")
            results.append({
                "recordId": record_id,
                "data": {"chunks": [text] if text else []},
                "errors": [{"message": str(e)}],
                "warnings": [],
            })

    return func.HttpResponse(
        json.dumps({"values": results}), status_code=200, mimetype="application/json"
    )


# ══════════════════════════════════════════════════════════════
# Skill 2: GPT-5.4 Verbalization (이미지/도표 설명)
# ══════════════════════════════════════════════════════════════

VERBALIZATION_SYSTEM_PROMPT = """당신은 PDF 문서의 이미지와 도표를 분석하는 전문가입니다.
주어진 PDF 페이지 이미지를 보고, 해당 페이지의 markdown 텍스트에서 figure 참조를 찾아
각 figure/이미지/도표/차트에 대한 상세한 텍스트 설명을 생성해주세요.

규칙:
1. 원본 markdown 텍스트를 유지하면서, figure 참조 부분에 설명을 추가합니다.
2. 도표/차트의 경우 데이터 값을 정확히 기술합니다.
3. 설명은 한국어로 작성합니다.
4. 원문에 figure 참조가 없더라도 이미지에 도표/차트/다이어그램이 보이면 설명을 추가합니다.
5. 설명 형식: [IMAGE_DESCRIPTION: 설명 내용]
"""


def _split_markdown_by_pagebreak(markdown_text: str) -> list[str]:
    """DI Layout 이 삽입한 `<!-- PageBreak -->` 기준으로 페이지 단위 분할."""
    if not markdown_text:
        return []
    parts = re.split(r"<!--\s*PageBreak\s*-->", markdown_text)
    return [p.strip() for p in parts if p and p.strip()]


def _split_pdf_pages_base64(pdf_base64: str) -> list[str]:
    """PDF base64 를 페이지별 base64 PDF 리스트로 분할. 실패 시 빈 리스트."""
    if not pdf_base64 or not _HAS_FITZ:
        return []
    try:
        raw = base64.b64decode(pdf_base64)
        src = fitz.open(stream=raw, filetype="pdf")
        out: list[str] = []
        for i in range(src.page_count):
            dst = fitz.open()
            dst.insert_pdf(src, from_page=i, to_page=i)
            buf = dst.tobytes()
            dst.close()
            out.append(base64.b64encode(buf).decode("ascii"))
        src.close()
        return out
    except Exception as e:
        logging.warning(f"PDF page split failed: {e}")
        return []


def _verbalize_page(client: AzureOpenAI, page_md: str, page_pdf_b64: str) -> str:
    """단일 페이지 markdown + PDF 페이지 base64 를 GPT-5.4 로 verbalize."""
    if not page_md.strip():
        return page_md
    content: list[dict] = [
        {
            "type": "text",
            "text": (
                "다음은 PDF 한 페이지의 markdown 텍스트입니다. "
                "제공된 PDF 페이지 이미지를 참고하여 도표/차트/이미지 설명을 추가해주세요.\n\n"
                f"--- MARKDOWN ---\n{page_md[:VERBALIZE_PAGE_CHAR_LIMIT]}"
            ),
        }
    ]
    if page_pdf_b64:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:application/pdf;base64,{page_pdf_b64}",
                "detail": "high",
            },
        })
    try:
        resp = client.chat.completions.create(
            model=GPT54_DEPLOYMENT,
            messages=[
                {"role": "system", "content": VERBALIZATION_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            max_tokens=4096,
            temperature=0.1,
        )
        enriched = resp.choices[0].message.content
        return enriched if enriched else page_md
    except Exception as e:
        logging.warning(f"GPT-5.4 page verbalization failed: {e}")
        return page_md


def _verbalize_with_gpt54(markdown_text: str, pdf_base64: str) -> str:
    """
    문서를 페이지(<!-- PageBreak -->) 단위로 나눠 GPT-5.4 호출을 병렬화.
    PyMuPDF 로 PDF 도 페이지별로 조각내서 각 GPT 호출이 해당 페이지만 볼 수 있도록 함.
    페이지 수와 PDF 페이지 수가 다르면 안전하게 원본 PDF 전체를 fallback 으로 사용.
    """
    if not markdown_text.strip():
        return markdown_text

    pages = _split_markdown_by_pagebreak(markdown_text)
    if not pages:
        return markdown_text

    pdf_pages = _split_pdf_pages_base64(pdf_base64) if pdf_base64 else []
    use_per_page_pdf = bool(pdf_pages) and len(pdf_pages) == len(pages)

    client = _get_openai_client()

    def _run(idx: int) -> tuple[int, str]:
        page_md = pages[idx]
        page_pdf = pdf_pages[idx] if use_per_page_pdf else (pdf_base64 if not pdf_pages else "")
        return idx, _verbalize_page(client, page_md, page_pdf)

    results: list[str] = [""] * len(pages)
    workers = max(1, min(VERBALIZE_PAGE_WORKERS, len(pages)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for idx, text in ex.map(_run, range(len(pages))):
            results[idx] = text

    return "\n\n<!-- PageBreak -->\n\n".join(results)


@app.route(route="verbalize", methods=["POST"])
def verbalize(req: func.HttpRequest) -> func.HttpResponse:
    """
    AI Search Custom Web API Skill: GPT-5.4 Vision 이미지 설명 생성

    Request body (AI Search format):
    {
        "values": [
            {
                "recordId": "1",
                "data": {
                    "markdown_text": "# Document\n![Figure 1](...)\n...",
                    "file_data": { "$type": "file", "data": "<base64>" }
                }
            }
        ]
    }

    Response:
    {
        "values": [
            {
                "recordId": "1",
                "data": { "verbalized_text": "# Document\n[IMAGE_DESCRIPTION: ...]\n..." },
                "errors": [],
                "warnings": []
            }
        ]
    }
    """
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"values": []}),
            status_code=400,
            mimetype="application/json",
        )

    records = body.get("values", []) or []

    def _process(record: dict) -> dict:
        record_id = record.get("recordId", "")
        data = record.get("data", {})
        markdown_text = _coerce_text(data.get("markdown_text", ""))
        file_data = data.get("file_data", {})
        pdf_base64 = ""
        if isinstance(file_data, dict):
            pdf_base64 = file_data.get("data", "")
        elif isinstance(file_data, str):
            pdf_base64 = file_data
        try:
            if pdf_base64 and markdown_text:
                verbalized = _verbalize_with_gpt54(markdown_text, pdf_base64)
            else:
                verbalized = markdown_text
                if not pdf_base64:
                    logging.warning(f"No file_data for record {record_id}, skipping verbalization")
            return {
                "recordId": record_id,
                "data": {"verbalized_text": verbalized},
                "errors": [],
                "warnings": [],
            }
        except Exception as e:
            logging.error(f"verbalize error for record {record_id}: {e}")
            return {
                "recordId": record_id,
                "data": {"verbalized_text": markdown_text},
                "errors": [{"message": str(e)}],
                "warnings": [],
            }

    if len(records) <= 1:
        results = [_process(r) for r in records]
    else:
        workers = max(1, min(VERBALIZE_RECORD_WORKERS, len(records)))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_process, records))

    return func.HttpResponse(
        json.dumps({"values": results}),
        status_code=200,
        mimetype="application/json",
    )
