"""
멀티모달 문서 처리기
- PDF에서 텍스트 + 이미지 추출 (Document Intelligence)
- 이미지 Verbalization (GPT-5.4)
- 텍스트/이미지 설명 임베딩 (text-embedding-3-large)
- Blob Storage에 추출 이미지 저장
- AI Search 멀티모달 인덱스에 업로드

참고: https://learn.microsoft.com/en-us/azure/search/multimodal-search-overview
방식: Image Verbalization → Text Embedding
"""

import base64
import json
import uuid
from datetime import datetime, timezone

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import (
    AnalyzeDocumentRequest,
    AnalyzeOutputOption,
)
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from openai import AzureOpenAI


class MultimodalProcessor:
    """PDF → 텍스트/이미지 추출 → Verbalization → 임베딩 → 인덱싱"""

    def __init__(
        self,
        di_endpoint: str,
        openai_endpoint: str,
        storage_account_name: str,
        openai_api_key: str | None = None,
        gpt_deployment: str = "gpt-5.4",
        embedding_deployment: str = "text-embedding-3-large",
        artifacts_container: str = "processed-documents",
    ):
        credential = DefaultAzureCredential()

        self.di_client = DocumentIntelligenceClient(
            endpoint=di_endpoint, credential=credential
        )

        if openai_api_key:
            self.openai_client = AzureOpenAI(
                azure_endpoint=openai_endpoint,
                api_key=openai_api_key,
                api_version="2024-10-21",
            )
        else:
            token = credential.get_token("https://cognitiveservices.azure.com/.default")
            self.openai_client = AzureOpenAI(
                azure_endpoint=openai_endpoint,
                azure_ad_token=token.token,
                api_version="2024-10-21",
            )

        self.blob_service = BlobServiceClient(
            account_url=f"https://{storage_account_name}.blob.core.windows.net",
            credential=credential,
        )
        self.artifacts_container = artifacts_container

        self.gpt_deployment = gpt_deployment
        self.embedding_deployment = embedding_deployment

    def process_pdf(
        self,
        pdf_bytes: bytes,
        file_name: str,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> list[dict]:
        """PDF를 분석하고 멀티모달 인덱스용 문서 리스트를 반환"""
        print(f"[멀티모달] '{file_name}' 분석 시작...")

        # 1. Document Intelligence로 분석 (Layout + Figures)
        poller = self.di_client.begin_analyze_document(
            model_id="prebuilt-layout",
            analyze_request=AnalyzeDocumentRequest(bytes_source=pdf_bytes),
            output_content_format="markdown",
            output=[AnalyzeOutputOption.FIGURES],
        )
        result = poller.result()
        operation_id = poller.details["operation_id"]

        paragraphs = result.paragraphs or []
        figures = result.figures or []
        total_pages = len(result.pages) if result.pages else 0
        print(f"[멀티모달] {total_pages}페이지, {len(paragraphs)}단락, {len(figures)}이미지 추출")

        documents = []
        doc_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        blob_folder = f"multimodal/{timestamp}/{file_name}"

        # 2. 페이지별로 텍스트 청크 생성
        page_paragraphs: dict[int, list] = {}
        for para in paragraphs:
            if para.bounding_regions:
                page_num = para.bounding_regions[0].page_number
                page_paragraphs.setdefault(page_num, []).append(para)

        chunk_index = 0
        for page_num in sorted(page_paragraphs.keys()):
            page_paras = page_paragraphs[page_num]
            chunks = self._chunk_paragraphs(page_paras, chunk_size, chunk_overlap)

            if chunks:
                texts = [c["text"] for c in chunks]
                embeddings = self._generate_embeddings(texts)

                for chunk, emb in zip(chunks, embeddings):
                    documents.append({
                        "content_id": str(uuid.uuid4()),
                        "document_id": doc_id,
                        "document_title": file_name,
                        "content_type": "text",
                        "content_text": chunk["text"],
                        "content_embedding": emb,
                        "image_path": "",
                        "page_number": page_num,
                        "chunk_index": chunk_index,
                        "bounding_polygons": json.dumps(chunk.get("polygons", [])),
                    })
                    chunk_index += 1

            print(f"[멀티모달] 페이지 {page_num}: {len(chunks)}개 텍스트 청크 생성")

        # 3. 이미지(Figure) 추출 → Blob 업로드 → Verbalization → 임베딩
        for i, figure in enumerate(figures):
            try:
                # DI에서 figure 이미지 가져오기
                figure_response = self.di_client.get_analyze_result_figure(
                    model_id=result.model_id,
                    result_id=operation_id,
                    figure_id=figure.id,
                )
                image_data = b""
                for chunk in figure_response:
                    image_data += chunk

                # Blob에 이미지 저장
                blob_name = f"{blob_folder}/figure_{figure.id}.png"
                container_client = self.blob_service.get_container_client(self.artifacts_container)
                try:
                    container_client.create_container()
                except Exception:
                    pass
                container_client.upload_blob(name=blob_name, data=image_data, overwrite=True)

                # 이미지 Verbalization (GPT-5.4)
                image_base64 = base64.b64encode(image_data).decode("utf-8")
                caption = figure.caption.content if figure.caption else ""
                verbalization = self._verbalize_image(image_base64, caption, file_name)

                # Verbalization 텍스트 임베딩
                emb = self._generate_embeddings([verbalization])[0]

                page_num = figure.bounding_regions[0].page_number if figure.bounding_regions else 0
                polygons = []
                if figure.bounding_regions:
                    for region in figure.bounding_regions:
                        if region.polygon:
                            polygons.append([
                                {"x": region.polygon[j], "y": region.polygon[j + 1]}
                                for j in range(0, len(region.polygon), 2)
                            ])

                documents.append({
                    "content_id": str(uuid.uuid4()),
                    "document_id": doc_id,
                    "document_title": file_name,
                    "content_type": "image",
                    "content_text": f"[이미지 설명] {verbalization}",
                    "content_embedding": emb,
                    "image_path": blob_name,
                    "page_number": page_num,
                    "chunk_index": chunk_index,
                    "bounding_polygons": json.dumps(polygons),
                })
                chunk_index += 1
                print(f"[멀티모달] 이미지 {i + 1}/{len(figures)} 처리 완료: {blob_name}")

            except Exception as e:
                print(f"[멀티모달] 이미지 {figure.id} 처리 실패: {e}")
                continue

        print(f"[멀티모달] '{file_name}' 처리 완료: 총 {len(documents)}개 문서 (텍스트+이미지)")
        return documents

    def _chunk_paragraphs(
        self,
        paragraphs: list,
        max_tokens: int = 500,
        overlap: int = 50,
    ) -> list[dict]:
        """단락을 청크로 분할 (토큰 = 단어 기준)"""
        chunks = []
        current_text = ""
        current_tokens = 0
        current_polygons = []

        for para in paragraphs:
            tokens = para.content.split()
            if current_tokens + len(tokens) > max_tokens and current_text.strip():
                chunks.append({"text": current_text.strip(), "polygons": current_polygons})
                overlap_tokens = tokens[-overlap:] if len(tokens) > overlap else tokens
                current_text = " ".join(overlap_tokens) + " " + para.content
                current_tokens = len(current_text.split())
                current_polygons = []
            else:
                current_text += " " + para.content
                current_tokens += len(tokens)

            if para.bounding_regions:
                for region in para.bounding_regions:
                    if region.polygon:
                        current_polygons.append([
                            {"x": region.polygon[j], "y": region.polygon[j + 1]}
                            for j in range(0, len(region.polygon), 2)
                        ])

        if current_text.strip():
            chunks.append({"text": current_text.strip(), "polygons": current_polygons})

        return chunks

    def _verbalize_image(self, image_base64: str, caption: str, source_name: str) -> str:
        """GPT-5.4를 사용하여 이미지를 자연어로 설명 (Verbalization)"""
        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an expert at describing images and diagrams in documents. "
                        "Provide a concise but detailed natural language description that captures "
                        "the key information, relationships, and structure shown in the image. "
                        "This description will be used for search indexing."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"Document: '{source_name}'\n"
                                f"Caption: {caption}\n\n"
                                "Describe this image in detail for search indexing."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ]

            response = self.openai_client.chat.completions.create(
                model=self.gpt_deployment,
                messages=messages,
                max_tokens=500,
                temperature=0.3,
            )
            return response.choices[0].message.content or caption or "Image content"
        except Exception as e:
            print(f"[Verbalization 오류] {e}")
            return caption or "Image content"

    def _generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """text-embedding-3-large로 임베딩 생성"""
        response = self.openai_client.embeddings.create(
            input=texts,
            model=self.embedding_deployment,
        )
        return [item.embedding for item in response.data]
