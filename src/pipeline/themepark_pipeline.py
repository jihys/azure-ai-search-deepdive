"""
테마파크 Knowledge Source 파이프라인 설정.

Foundry azureBlob Knowledge Source를 사용하여 테마파크 가이드맵 데이터를
자동으로 인덱싱한다. Foundry가 내부적으로 OCR, 청킹, 임베딩, 이미지 verbalization을
처리하므로 별도의 index/skillset/indexer를 만들 필요 없다.

데이터: data/raw/pdf/themepark/ (에버랜드, 롯데월드, 서울대공원 가이드맵)
"""

from __future__ import annotations

import os

import requests
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

API_VERSION = "2026-05-01-preview"
KS_NAME = "ks-themepark"
AGENT_NAME = "themepark-knowledge-agent"
ASSET_CONTAINER = "themepark-assets"
FOLDER_PATH = "raw/pdf/themepark"
INDEXER_NAME = f"{KS_NAME}-indexer"


def _env(key: str, *alt_keys: str, default: str = "") -> str:
    """환경변수를 조회한다. alt_keys 순서로 fallback."""
    for k in (key, *alt_keys):
        val = os.environ.get(k, "")
        if val:
            return val
    return default


def _auth_headers(credential: DefaultAzureCredential) -> dict[str, str]:
    """Bearer 토큰 인증 헤더를 반환한다."""
    token = credential.get_token("https://search.azure.com/.default")
    return {"Authorization": f"Bearer {token.token}", "Content-Type": "application/json"}


def _build_ks_body(
    storage_resource_id: str,
    container_name: str,
    openai_endpoint: str,
    embedding_deployment: str,
    gpt_deployment: str,
) -> dict:
    """azureBlob Knowledge Source 페이로드를 구성한다."""
    return {
        "name": KS_NAME,
        "kind": "azureBlob",
        "description": "테마파크 가이드맵 (에버랜드, 롯데월드, 서울대공원)",
        "azureBlobParameters": {
            "connectionString": f"ResourceId={storage_resource_id}",
            "containerName": container_name,
            "folderPath": FOLDER_PATH,
            "isADLSGen2": False,
            "ingestionParameters": {
                "embeddingModel": {
                    "kind": "azureOpenAI",
                    "azureOpenAIParameters": {
                        "resourceUri": openai_endpoint,
                        "deploymentId": embedding_deployment,
                        "modelName": embedding_deployment,
                    },
                },
                "chatCompletionModel": {
                    "kind": "azureOpenAI",
                    "azureOpenAIParameters": {
                        "resourceUri": openai_endpoint,
                        "deploymentId": gpt_deployment,
                        "modelName": gpt_deployment,
                    },
                },
                "disableImageVerbalization": False,
                "contentExtractionMode": "standard",
                "assetStore": {
                    "connectionString": f"ResourceId={storage_resource_id}",
                    "containerName": ASSET_CONTAINER,
                },
            },
        },
    }


def _build_agent_body(openai_endpoint: str, gpt_deployment: str) -> dict:
    """Knowledge Base (Agent) 페이로드를 구성한다."""
    return {
        "name": AGENT_NAME,
        "description": "테마파크 가이드맵 검색 + Image Serving",
        "models": [
            {
                "kind": "azureOpenAI",
                "azureOpenAIParameters": {
                    "resourceUri": openai_endpoint,
                    "deploymentId": gpt_deployment,
                    "modelName": gpt_deployment,
                },
            }
        ],
        "knowledgeSources": [
            {
                "name": KS_NAME,
                "alwaysQuerySource": True,
                "includeReferences": True,
                "includeReferenceSourceData": True,
                "maxSubQueries": 3,
                "rerankerThreshold": 1.0,
            }
        ],
        "outputConfiguration": {
            "modality": "answerSynthesis",
            "includeActivity": True,
            "attemptFastPath": False,
        },
        "requestLimits": {"maxRuntimeInSeconds": 60, "maxOutputSize": 16000},
        "retrievalInstructions": (
            "너는 한국 테마파크(에버랜드, 롯데월드, 서울대공원) 가이드 어시스턴트다. "
            "가이드맵과 안내 문서에서 시설 위치, 운영 정보, 놀이기구 안내 등을 검색한다. "
            "이미지가 포함된 결과가 있으면 이미지 정보도 함께 제공하라. "
            "모든 응답은 한국어로 작성하라."
        ),
    }


def setup_themepark_pipeline(run: bool = False, credential: DefaultAzureCredential | None = None) -> None:
    """테마파크 Knowledge Source + Knowledge Base를 생성한다.

    Args:
        run: True이면 Foundry 내부 인덱서를 실행한다.
        credential: Azure 인증 자격증명. None이면 DefaultAzureCredential을 생성한다.
    """
    search_endpoint = _env("AZURE_SEARCH_SERVICE_ENDPOINT", "AZURE_SEARCH_ENDPOINT").rstrip("/")
    openai_endpoint = _env("AZURE_OPENAI_ENDPOINT")
    embedding_deployment = _env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", default="text-embedding-3-large")
    gpt_deployment = _env("AZURE_OPENAI_GPT54_DEPLOYMENT", default="gpt-5.4")
    storage_resource_id = _env("AZURE_STORAGE_RESOURCE_ID")
    container_name = _env("AZURE_STORAGE_CONTAINER_NAME", default="raw-documents")

    if credential is None:
        credential = DefaultAzureCredential(
            exclude_managed_identity_credential=True,
            exclude_workload_identity_credential=True,
        )

    headers = _auth_headers(credential)

    # ── Knowledge Source (azureBlob) ─────────────────────────
    ks_body = _build_ks_body(storage_resource_id, container_name, openai_endpoint, embedding_deployment, gpt_deployment)
    ks_url = f"{search_endpoint}/knowledgesources('{KS_NAME}')?api-version={API_VERSION}"
    print(f"  [KS] PUT {KS_NAME}")
    resp = requests.put(ks_url, headers=headers, json=ks_body, timeout=120)
    if resp.status_code not in (200, 201):
        print(f"  [ERROR] KS → {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()
    print(f"  [KS] {KS_NAME} → {resp.status_code}")

    # ── Knowledge Base (Agent) ───────────────────────────────
    agent_body = _build_agent_body(openai_endpoint, gpt_deployment)
    agent_url = f"{search_endpoint}/agents('{AGENT_NAME}')?api-version={API_VERSION}"
    print(f"  [Agent] PUT {AGENT_NAME}")
    resp = requests.put(agent_url, headers=headers, json=agent_body, timeout=120)
    if resp.status_code not in (200, 201):
        print(f"  [ERROR] Agent → {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()
    print(f"  [Agent] {AGENT_NAME} → {resp.status_code}")

    # ── 인덱서 실행 (선택) ──────────────────────────────────
    if run:
        indexer_url = f"{search_endpoint}/indexers('{INDEXER_NAME}')/search.run?api-version={API_VERSION}"
        print(f"  [Indexer] POST {INDEXER_NAME}/search.run")
        resp = requests.post(indexer_url, headers=headers, timeout=120)
        if resp.status_code not in (200, 202):
            print(f"  [WARN] Indexer run → {resp.status_code}: {resp.text[:500]}")
        else:
            print(f"  [Indexer] {INDEXER_NAME} → {resp.status_code}")
