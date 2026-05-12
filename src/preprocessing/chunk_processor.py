"""
청크 생성 및 메타데이터 정규화

원문 JSON/Markdown 파일을 읽어 검색 단위 청크로 변환:
  - 청크 크기: 2000 문자 기준
  - Overlap: 200 문자 (컨텍스트 유지)
  - 메타데이터: source, crawl_date, original_file, chunk_index, total_chunks
  - 출력: processed/{source}/{date}/{file_id}_{chunk_index}.json
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class ChunkMetadata:
    """청크 메타데이터"""
    source: str  # prec, detc, expc, admrul
    crawl_date: str  # YYYY-MM-DD
    original_file: str  # law_001680.json
    file_id: str  # 001680
    chunk_index: int  # 0, 1, 2, ...
    total_chunks: int
    created_at: str  # ISO 8601


@dataclass
class Chunk:
    """청크 단위 문서"""
    metadata: ChunkMetadata
    content: str  # 실제 텍스트


class ChunkProcessor:
    """청크 생성 프로세서"""
    
    # 청크 설정
    CHUNK_SIZE = 2000  # 문자 단위
    CHUNK_OVERLAP = 200  # 오버랩 문자
    
    def __init__(self, source: str, crawl_date: str):
        """
        Args:
            source: 'prec' | 'detc' | 'expc' | 'admrul'
            crawl_date: 'YYYY-MM-DD' (raw 폴더명)
        """
        self.source = source
        self.crawl_date = crawl_date
        logger.info(f"ChunkProcessor initialized: source={source}, date={crawl_date}")
    
    def process_json_file(self, file_path: str, json_data: dict) -> list[Chunk]:
        """
        JSON 파일 처리 (메타데이터 추출 + 본문 청크화)
        
        Args:
            file_path: 원본 파일명 (예: law_001680.json)
            json_data: 파싱된 JSON 딕셔너리
            
        Returns:
            Chunk 리스트
        """
        file_id = self._extract_file_id(file_path)
        
        # JSON에서 본문 추출
        content = self._extract_content_from_json(json_data)
        
        if not content or len(content.strip()) == 0:
            logger.warning(f"Empty content in {file_path}")
            return []
        
        # 청크화
        chunks = self._chunk_text(content, file_id, file_path)
        logger.info(f"Generated {len(chunks)} chunks from {file_path}")
        
        return chunks
    
    def process_markdown_file(self, file_path: str, markdown_content: str) -> list[Chunk]:
        """
        Markdown 파일 처리 (직접 청크화)
        
        Args:
            file_path: 원본 파일명 (예: law_001680.md)
            markdown_content: Markdown 텍스트
            
        Returns:
            Chunk 리스트
        """
        file_id = self._extract_file_id(file_path)
        
        if not markdown_content or len(markdown_content.strip()) == 0:
            logger.warning(f"Empty markdown in {file_path}")
            return []
        
        # 청크화
        chunks = self._chunk_text(markdown_content, file_id, file_path)
        logger.info(f"Generated {len(chunks)} chunks from {file_path}")
        
        return chunks
    
    def _extract_file_id(self, file_path: str) -> str:
        """파일명에서 ID 추출 (예: law_001680.json -> 001680)"""
        # 파일명 추출
        filename = file_path.split('/')[-1]
        # law_XXXXXX 패턴에서 숫자만 추출
        match = re.search(r'law_(\d+)', filename)
        return match.group(1) if match else "unknown"
    
    def _extract_content_from_json(self, json_data: dict) -> str:
        """
        JSON 데이터에서 본문 추출
        
        기대하는 JSON 구조:
        {
            "sn": "001680",
            "nm": "민법",
            "lsNm": "법령",
            "promgDate": "1958-02-27",
            "content": "제1장 ...",
            ...
        }
        """
        # content 필드 우선
        if "content" in json_data and json_data["content"]:
            return json_data["content"]
        
        # 없으면 주요 필드들 합치기
        parts = []
        
        if "nm" in json_data:
            parts.append(f"[{json_data['nm']}]")
        
        if "lsNm" in json_data:
            parts.append(f"({json_data['lsNm']})")
        
        if "promgDate" in json_data:
            parts.append(f"제정: {json_data['promgDate']}")
        
        if "ammendDate" in json_data:
            parts.append(f"개정: {json_data['ammendDate']}")
        
        # 본문 시작
        if "content" in json_data:
            parts.append(json_data["content"])
        
        return "\n".join(parts)
    
    def _chunk_text(
        self,
        text: str,
        file_id: str,
        file_path: str,
    ) -> list[Chunk]:
        """
        텍스트를 청크로 분할
        
        Args:
            text: 원본 텍스트
            file_id: 파일 ID
            file_path: 원본 파일명
            
        Returns:
            Chunk 리스트
        """
        # 전처리: 여러 줄바꿈 정리
        text = re.sub(r'\n\s*\n+', '\n\n', text)
        
        chunks_list = []
        chunk_index = 0
        start = 0
        text_length = len(text)
        
        while start < text_length:
            # 청크 끝 위치
            end = min(start + self.CHUNK_SIZE, text_length)
            
            # 마지막 청크가 너무 작으면 앞 청크에 병합
            if text_length - end < 100 and chunks_list:
                # 마지막 청크에 나머지 추가
                last_chunk = chunks_list[-1]
                remaining = text[chunks_list[-1].metadata.chunk_index:]
                last_chunk.content += "\n\n" + remaining
                break
            
            # 단어 경계에서 자르기 (완전성 유지)
            if end < text_length:
                # 뒤로 가면서 공백/줄바꿈 찾기
                while end > start + int(self.CHUNK_SIZE * 0.5) and text[end] not in '\n\t ':
                    end -= 1
                end = end + 1 if end < text_length else text_length
            
            chunk_content = text[start:end].strip()
            
            if chunk_content:
                metadata = ChunkMetadata(
                    source=self.source,
                    crawl_date=self.crawl_date,
                    original_file=file_path.split('/')[-1],
                    file_id=file_id,
                    chunk_index=chunk_index,
                    total_chunks=0,  # 나중에 설정
                    created_at=datetime.utcnow().isoformat() + "Z",
                )
                
                chunk = Chunk(metadata=metadata, content=chunk_content)
                chunks_list.append(chunk)
                chunk_index += 1
            
            # 다음 청크 시작 위치 (오버랩 적용)
            start = end - self.CHUNK_OVERLAP if end < text_length else text_length
        
        # total_chunks 설정
        total = len(chunks_list)
        for chunk in chunks_list:
            chunk.metadata.total_chunks = total
        
        return chunks_list
    
    def chunks_to_json_records(self, chunks: list[Chunk]) -> list[dict]:
        """
        Chunk 객체들을 JSON 직렬화 가능한 딕셔너리로 변환
        (Azure AI Search 인덱싱용)
        """
        records = []
        for chunk in chunks:
            record = {
                "metadata": asdict(chunk.metadata),
                "content": chunk.content,
            }
            records.append(record)
        return records
    
    @staticmethod
    def validate_chunks(chunks: list[Chunk]) -> bool:
        """청크 유효성 검사"""
        if not chunks:
            logger.warning("No chunks to validate")
            return False
        
        for i, chunk in enumerate(chunks):
            if not chunk.content or len(chunk.content.strip()) == 0:
                logger.error(f"Chunk {i} has empty content")
                return False
            
            if chunk.metadata.chunk_index != i:
                logger.error(f"Chunk index mismatch at {i}")
                return False
        
        logger.info(f"Validated {len(chunks)} chunks")
        return True
