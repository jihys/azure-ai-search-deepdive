"""
Azure Function App - AI Search Custom Skills
Azure Functions Python v2 프로그래밍 모델

Custom Web API Skills for AI Search Indexer:
  1. /api/markdown_split   — Markdown 헤더 기반 텍스트 분할
  2. /api/verbalize        — GPT-5.4 Vision으로 PDF 이미지/도표 설명 생성

배포 후 AI Search Skillset에서 Custom Web API Skill로 연결하여 사용.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
from typing import Any

import azure.functions as func
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from openai import AzureOpenAI

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


def _verbalize_with_gpt54(markdown_text: str, pdf_base64: str) -> str:
    """
    GPT-5.4 Vision을 사용하여 PDF 내 이미지/도표를 설명하고 markdown에 삽입.
    pdf_base64: PDF 파일의 base64 인코딩 데이터
    """
    if not markdown_text.strip():
        return markdown_text

    client = _get_openai_client()

    # PDF를 이미지로 전달 (GPT-5.4는 PDF 직접 처리 가능)
    messages = [
        {"role": "system", "content": VERBALIZATION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"다음은 PDF에서 추출된 markdown 텍스트입니다. "
                    f"PDF 이미지를 참고하여 도표/차트/이미지에 대한 설명을 추가해주세요.\n\n"
                    f"--- MARKDOWN ---\n{markdown_text[:8000]}",
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:application/pdf;base64,{pdf_base64}",
                        "detail": "high",
                    },
                },
            ],
        },
    ]

    try:
        response = client.chat.completions.create(
            model=GPT54_DEPLOYMENT,
            messages=messages,
            max_tokens=4096,
            temperature=0.1,
        )
        enriched = response.choices[0].message.content
        return enriched if enriched else markdown_text
    except Exception as e:
        logging.warning(f"GPT-5.4 verbalization failed: {e}, returning original text")
        return markdown_text


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

    results = []
    for record in body.get("values", []):
        record_id = record.get("recordId", "")
        data = record.get("data", {})
        markdown_text = _coerce_text(data.get("markdown_text", ""))
        file_data = data.get("file_data", {})

        # file_data는 AI Search에서 전달하는 base64 인코딩 파일
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

            results.append({
                "recordId": record_id,
                "data": {"verbalized_text": verbalized},
                "errors": [],
                "warnings": [],
            })
        except Exception as e:
            logging.error(f"verbalize error for record {record_id}: {e}")
            results.append({
                "recordId": record_id,
                "data": {"verbalized_text": markdown_text},
                "errors": [{"message": str(e)}],
                "warnings": [],
            })

    return func.HttpResponse(
        json.dumps({"values": results}),
        status_code=200,
        mimetype="application/json",
    )
