"""
Azure Document Intelligence를 활용한 문서 전처리
- Markdown 레이어 추출
- 테이블 추출
- 이미지/Figure 메타데이터 추출
"""

from dataclasses import dataclass, field

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, DocumentAnalysisFeature
from azure.identity import DefaultAzureCredential


@dataclass
class ProcessedDocument:
    """전처리된 문서 결과"""
    source_name: str
    markdown_content: str = ""
    tables: list[dict] = field(default_factory=list)
    figures: list[dict] = field(default_factory=list)
    pages: int = 0
    chunks: list[dict] = field(default_factory=list)


class DocIntelligenceProcessor:
    """Document Intelligence 기반 문서 전처리기"""

    def __init__(
        self,
        endpoint: str,
        key: str | None = None,
    ):
        if key:
            from azure.core.credentials import AzureKeyCredential
            credential = AzureKeyCredential(key)
        else:
            credential = DefaultAzureCredential()

        self.client = DocumentIntelligenceClient(endpoint=endpoint, credential=credential)

    def analyze_document(
        self,
        document_content: bytes,
        source_name: str = "document",
    ) -> ProcessedDocument:
        """문서를 분석하고 전처리 결과를 반환

        Layout 모델을 사용하여 Markdown, 테이블, 이미지를 추출합니다.
        """
        result = ProcessedDocument(source_name=source_name)

        # Document Intelligence Layout 분석
        poller = self.client.begin_analyze_document(
            model_id="prebuilt-layout",
            analyze_request=AnalyzeDocumentRequest(bytes_source=document_content),
            output_content_format="markdown",
            features=[DocumentAnalysisFeature.FIGURES],
        )
        analysis = poller.result()

        # Markdown 콘텐츠
        result.markdown_content = analysis.content or ""
        result.pages = len(analysis.pages) if analysis.pages else 0

        # 테이블 추출
        if analysis.tables:
            for i, table in enumerate(analysis.tables):
                table_data = {
                    "index": i,
                    "row_count": table.row_count,
                    "column_count": table.column_count,
                    "cells": [],
                }
                for cell in table.cells:
                    table_data["cells"].append({
                        "row": cell.row_index,
                        "col": cell.column_index,
                        "content": cell.content,
                        "kind": cell.kind if hasattr(cell, "kind") else "content",
                    })
                result.tables.append(table_data)

        # Figure 메타데이터 추출 (캡션은 DI Markdown에 이미 포함됨)
        if analysis.figures:
            for i, figure in enumerate(analysis.figures):
                figure_data = {
                    "index": i,
                    "caption": figure.caption.content if figure.caption else "",
                    "bounding_regions": [],
                }

                if figure.bounding_regions:
                    for region in figure.bounding_regions:
                        figure_data["bounding_regions"].append({
                            "page": region.page_number,
                            "polygon": [p for p in region.polygon] if region.polygon else [],
                        })

                result.figures.append(figure_data)

        print(
            f"[Doc Intelligence] {source_name}: "
            f"{result.pages}페이지, {len(result.tables)}테이블, {len(result.figures)}이미지"
        )
        return result

    def chunk_document(
        self,
        processed: ProcessedDocument,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> list[dict]:
        """전처리된 문서를 청크로 분할"""
        text = processed.markdown_content
        chunks = []
        start = 0
        chunk_index = 0

        while start < len(text):
            end = min(start + chunk_size, len(text))

            # 문장 경계에서 자르기
            if end < len(text):
                # 마지막 줄바꿈 또는 마침표 위치 찾기
                last_break = text.rfind("\n", start, end)
                if last_break == -1 or last_break <= start:
                    last_break = text.rfind(".", start, end)
                if last_break > start:
                    end = last_break + 1

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append({
                    "id": f"{processed.source_name}_{chunk_index:04d}",
                    "documentName": processed.source_name,
                    "content": chunk_text,
                    "chunkIndex": chunk_index,
                })
                chunk_index += 1

            start = end - chunk_overlap if end < len(text) else end

        # 테이블 내용도 별도 청크로 추가
        for table in processed.tables:
            table_text = self._table_to_text(table)
            if table_text:
                chunks.append({
                    "id": f"{processed.source_name}_table_{table['index']:03d}",
                    "documentName": processed.source_name,
                    "content": table_text,
                    "chunkIndex": chunk_index,
                })
                chunk_index += 1

        processed.chunks = chunks
        print(f"[청킹] {processed.source_name}: {len(chunks)}개 청크 생성")
        return chunks

    def _table_to_text(self, table: dict) -> str:
        """테이블 데이터를 텍스트로 변환"""
        rows: dict[int, dict[int, str]] = {}
        for cell in table.get("cells", []):
            r = cell["row"]
            c = cell["col"]
            rows.setdefault(r, {})[c] = cell["content"]

        lines = []
        for r in sorted(rows.keys()):
            cols = rows[r]
            line = " | ".join(cols.get(c, "") for c in sorted(cols.keys()))
            lines.append(line)

        return "\n".join(lines)
