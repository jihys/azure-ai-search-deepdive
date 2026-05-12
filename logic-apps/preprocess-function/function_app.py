"""
Azure Function App - 청크 생성 및 메타데이터 정규화
Azure Functions Python v2 프로그래밍 모델

HTTP 트리거: Logic Apps에서 크롤링 완료 후 호출
  Body (JSON):
    source         : "prec" | "detc" | "expc" | "admrul" | "all"  (기본: "all")
    crawl_date     : 크롤링 날짜 (YYYY-MM-DD, 기본: 오늘)
    triggered_by   : 호출 출처 (기본: "logic-app")

처리 흐름:
  1. Blob Storage에서 raw-documents/{source}/{date}/ 읽기
  2. 각 JSON/MD 파일별로 청크 생성
  3. 메타데이터 정규화
  4. processed-documents/{source}/{date}/ 저장
  5. 결과 JSON 반환 (처리된 청크 수, 소스별 통계)

Storage 접근:
  - Managed Identity 기반 (VNet Integration → Storage Private Endpoint)
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional
from pathlib import PureWindowsPath

import azure.functions as func
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import ManagedIdentityCredential
from azure.storage.blob import BlobServiceClient, BlobClient
import sys

# 부모 디렉토리 추가 (src 모듈 임포트용)
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.preprocessing.chunk_processor import ChunkProcessor

app = func.FunctionApp()

# 환경 변수
STORAGE_ACCOUNT_NAME = os.environ.get("AZURE_STORAGE_ACCOUNT_NAME", "")
RAW_CONTAINER_NAME = os.environ.get("AZURE_BLOB_CONTAINER_RAW", "raw-documents")
PROCESSED_CONTAINER_NAME = os.environ.get("AZURE_BLOB_CONTAINER_PROCESSED", "processed-documents")
DEFAULT_CRAWL_DATE = os.environ.get("CRAWL_DATE", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

# Logger 설정
logger = logging.getLogger("PreprocessFunction")
logger.setLevel(logging.INFO)

# Blob 클라이언트 초기화
def get_blob_service_client() -> BlobServiceClient:
    """Managed Identity를 사용하여 BlobServiceClient 생성"""
    if STORAGE_ACCOUNT_NAME:
        account_url = f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net"
        credential = ManagedIdentityCredential()
        return BlobServiceClient(account_url=account_url, credential=credential)
    else:
        # 로컬 테스트용: AZURE_STORAGE_CONNECTION_STRING 사용
        conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        return BlobServiceClient.from_connection_string(conn_str)


@app.route(route="preprocess", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def preprocess_trigger(req: func.HttpRequest) -> func.HttpResponse:
    """
    청크 생성 및 전처리 메인 함수
    """
    logger.info(f"Preprocess function triggered: {req.method}")
    
    try:
        # 요청 파싱
        req_body = req.get_json()
        source = req_body.get("source", "all").lower()
        crawl_date = req_body.get("crawl_date", DEFAULT_CRAWL_DATE)
        triggered_by = req_body.get("triggered_by", "manual")
        
        # 유효성 검사
        if source not in ["prec", "detc", "expc", "admrul", "all"]:
            return func.HttpResponse(
                json.dumps({"error": f"Invalid source: {source}"}),
                status_code=400,
                mimetype="application/json",
            )
        
        # 처리할 소스 결정
        sources = [source] if source != "all" else ["prec", "detc", "expc", "admrul"]
        
        logger.info(f"Processing sources: {sources}, date: {crawl_date}, triggered_by: {triggered_by}")
        
        # 결과 저장소
        results = {
            "status": "success",
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "crawl_date": crawl_date,
            "sources": {},
            "total_chunks": 0,
            "total_files": 0,
            "errors": [],
        }
        
        # Blob 클라이언트
        blob_client = get_blob_service_client()
        
        # 소스별 처리
        for src in sources:
            logger.info(f"Processing source: {src}")
            
            src_result = process_source(
                blob_client=blob_client,
                source=src,
                crawl_date=crawl_date,
            )
            
            results["sources"][src] = src_result
            results["total_chunks"] += src_result["total_chunks"]
            results["total_files"] += src_result["total_files"]
            
            if src_result.get("errors"):
                results["errors"].extend(src_result["errors"])
        
        logger.info(f"Preprocessing completed: {results['total_chunks']} chunks from {results['total_files']} files")
        
        return func.HttpResponse(
            json.dumps(results, ensure_ascii=False, indent=2),
            status_code=200,
            mimetype="application/json",
        )
    
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Validation error: {str(e)}"}),
            status_code=400,
            mimetype="application/json",
        )
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return func.HttpResponse(
            json.dumps({"error": f"Internal server error: {str(e)}"}),
            status_code=500,
            mimetype="application/json",
        )


def process_source(
    blob_client: BlobServiceClient,
    source: str,
    crawl_date: str,
) -> dict:
    """
    단일 소스의 청크 생성 처리
    
    Returns:
        {
            "source": "prec",
            "total_files": 10,
            "total_chunks": 45,
            "files": [
                {"name": "law_001680.json", "chunks": 3},
                ...
            ],
            "errors": []
        }
    """
    result = {
        "source": source,
        "total_files": 0,
        "total_chunks": 0,
        "files": [],
        "errors": [],
    }
    
    try:
        # Raw 컨테이너에서 폴더 나열
        raw_container = blob_client.get_container_client(RAW_CONTAINER_NAME)
        raw_prefix = f"{source}/{crawl_date}/"
        
        logger.info(f"Listing blobs from {raw_prefix}")
        
        # 해당 폴더의 모든 파일 조회
        blobs = list(raw_container.list_blobs(name_starts_with=raw_prefix))
        
        if not blobs:
            logger.warning(f"No files found in {raw_prefix}")
            result["errors"].append(f"No files found in {raw_prefix}")
            return result
        
        # 파일 필터링 (law_XXXXX.json 또는 law_XXXXX.md)
        json_files = [b for b in blobs if b.name.endswith(".json")]
        
        logger.info(f"Found {len(json_files)} JSON files in {raw_prefix}")
        
        # JSON 파일 처리
        for blob in json_files:
            file_name = blob.name.split("/")[-1]
            
            try:
                # JSON 파일 읽기
                blob_ref = raw_container.get_blob_client(blob.name)
                blob_data = blob_ref.download_blob().readall().decode("utf-8")
                json_data = json.loads(blob_data)
                
                # 청크 생성
                processor = ChunkProcessor(source=source, crawl_date=crawl_date)
                chunks = processor.process_json_file(file_name, json_data)
                
                if chunks:
                    # Processed 컨테이너에 저장
                    chunk_count = save_chunks(
                        blob_client=blob_client,
                        source=source,
                        crawl_date=crawl_date,
                        file_id=processor._extract_file_id(file_name),
                        chunks=chunks,
                    )
                    
                    result["total_chunks"] += chunk_count
                    result["total_files"] += 1
                    result["files"].append({
                        "name": file_name,
                        "chunks": chunk_count,
                    })
                    
                    logger.info(f"Processed {file_name}: {chunk_count} chunks")
                else:
                    result["errors"].append(f"No chunks generated from {file_name}")
            
            except json.JSONDecodeError as e:
                error_msg = f"JSON decode error in {file_name}: {str(e)}"
                logger.error(error_msg)
                result["errors"].append(error_msg)
            except Exception as e:
                error_msg = f"Error processing {file_name}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                result["errors"].append(error_msg)
        
        logger.info(f"Source {source} completed: {result['total_files']} files, {result['total_chunks']} chunks")
    
    except ResourceNotFoundError as e:
        error_msg = f"Raw container or path not found: {str(e)}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
    except Exception as e:
        error_msg = f"Error processing source {source}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        result["errors"].append(error_msg)
    
    return result


def save_chunks(
    blob_client: BlobServiceClient,
    source: str,
    crawl_date: str,
    file_id: str,
    chunks: list,
) -> int:
    """
    청크를 Processed 컨테이너에 저장
    
    파일명: {source}/{crawl_date}/{file_id}_chunks.json
    내용: 청크 배열
    
    Returns:
        저장된 청크 수
    """
    processed_container = blob_client.get_container_client(PROCESSED_CONTAINER_NAME)
    
    # 청크를 JSON으로 직렬화
    processor = ChunkProcessor(source=source, crawl_date=crawl_date)
    chunk_records = processor.chunks_to_json_records(chunks)
    
    blob_name = f"{source}/{crawl_date}/{file_id}_chunks.json"
    blob_ref = processed_container.get_blob_client(blob_name)
    
    # JSON 업로드
    chunk_json = json.dumps(
        chunk_records,
        ensure_ascii=False,
        indent=2,
    )
    
    blob_ref.upload_blob(chunk_json, overwrite=True)
    logger.info(f"Saved chunks to {blob_name}")
    
    return len(chunks)
