"""
themepark_pipeline.py 단위 테스트.

requests.put을 목킹하여 Knowledge Source / Agent 페이로드를 검증한다.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


# ── 환경변수 설정 (import 전에) ──────────────────────────────

@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    """모든 테스트 전에 필수 환경변수를 설정한다."""
    env = {
        "AZURE_SEARCH_SERVICE_ENDPOINT": "https://test-search.search.windows.net",
        "AZURE_OPENAI_ENDPOINT": "https://test-openai.openai.azure.com/",
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "text-embedding-3-large",
        "AZURE_OPENAI_GPT54_DEPLOYMENT": "gpt-5.4",
        "AZURE_STORAGE_RESOURCE_ID": "/subscriptions/00000000/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/testsa",
        "AZURE_STORAGE_CONTAINER_NAME": "raw-documents",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)


@pytest.fixture
def mock_credential():
    """DefaultAzureCredential 목 객체."""
    cred = MagicMock()
    token = MagicMock()
    token.token = "fake-bearer-token"
    cred.get_token.return_value = token
    return cred


def _find_put_call(mock_put: MagicMock, url_contains: str) -> dict | None:
    """requests.put 호출 중 URL에 url_contains가 포함된 호출의 json body를 반환한다."""
    for call in mock_put.call_args_list:
        args, kwargs = call
        url = args[0] if args else kwargs.get("url", "")
        if url_contains in url:
            return kwargs.get("json")
    return None


# ══════════════════════════════════════════════════════════════
# Knowledge Source 구조 검증
# ══════════════════════════════════════════════════════════════


class TestKnowledgeSource:
    """azureBlob Knowledge Source 페이로드가 올바른지 검증한다."""

    @patch("src.pipeline.themepark_pipeline.requests.put")
    def test_ks_kind_is_azure_blob(self, mock_put, mock_credential):
        mock_put.return_value = MagicMock(status_code=201, text="")
        from src.pipeline.themepark_pipeline import setup_themepark_pipeline

        setup_themepark_pipeline(credential=mock_credential)
        body = _find_put_call(mock_put, "knowledgesources")
        assert body is not None, "KS PUT call not found"
        assert body["kind"] == "azureBlob"

    @patch("src.pipeline.themepark_pipeline.requests.put")
    def test_ks_container_and_folder(self, mock_put, mock_credential):
        mock_put.return_value = MagicMock(status_code=201, text="")
        from src.pipeline.themepark_pipeline import setup_themepark_pipeline

        setup_themepark_pipeline(credential=mock_credential)
        body = _find_put_call(mock_put, "knowledgesources")
        blob_params = body["azureBlobParameters"]
        assert blob_params["containerName"] == "raw-documents"
        assert blob_params["folderPath"] == "raw/pdf/themepark"

    @patch("src.pipeline.themepark_pipeline.requests.put")
    def test_ks_embedding_model(self, mock_put, mock_credential):
        mock_put.return_value = MagicMock(status_code=201, text="")
        from src.pipeline.themepark_pipeline import setup_themepark_pipeline

        setup_themepark_pipeline(credential=mock_credential)
        body = _find_put_call(mock_put, "knowledgesources")
        ingestion = body["azureBlobParameters"]["ingestionParameters"]
        emb = ingestion["embeddingModel"]
        assert emb["kind"] == "azureOpenAI"
        assert emb["azureOpenAIParameters"]["deploymentId"] == "text-embedding-3-large"

    @patch("src.pipeline.themepark_pipeline.requests.put")
    def test_ks_chat_completion_model(self, mock_put, mock_credential):
        mock_put.return_value = MagicMock(status_code=201, text="")
        from src.pipeline.themepark_pipeline import setup_themepark_pipeline

        setup_themepark_pipeline(credential=mock_credential)
        body = _find_put_call(mock_put, "knowledgesources")
        ingestion = body["azureBlobParameters"]["ingestionParameters"]
        chat = ingestion["chatCompletionModel"]
        assert chat["kind"] == "azureOpenAI"
        assert chat["azureOpenAIParameters"]["deploymentId"] == "gpt-5.4"

    @patch("src.pipeline.themepark_pipeline.requests.put")
    def test_ks_asset_store(self, mock_put, mock_credential):
        mock_put.return_value = MagicMock(status_code=201, text="")
        from src.pipeline.themepark_pipeline import setup_themepark_pipeline

        setup_themepark_pipeline(credential=mock_credential)
        body = _find_put_call(mock_put, "knowledgesources")
        ingestion = body["azureBlobParameters"]["ingestionParameters"]
        assert ingestion["assetStore"]["containerName"] == "themepark-assets"


# ══════════════════════════════════════════════════════════════
# Agent 구조 검증
# ══════════════════════════════════════════════════════════════


class TestAgent:
    """Knowledge Base (Agent) 페이로드가 올바른지 검증한다."""

    @patch("src.pipeline.themepark_pipeline.requests.put")
    def test_agent_models(self, mock_put, mock_credential):
        mock_put.return_value = MagicMock(status_code=201, text="")
        from src.pipeline.themepark_pipeline import setup_themepark_pipeline

        setup_themepark_pipeline(credential=mock_credential)
        body = _find_put_call(mock_put, "agents")
        assert body is not None, "Agent PUT call not found"
        assert len(body["models"]) == 1
        model = body["models"][0]
        assert model["kind"] == "azureOpenAI"
        assert model["azureOpenAIParameters"]["deploymentId"] == "gpt-5.4"

    @patch("src.pipeline.themepark_pipeline.requests.put")
    def test_agent_knowledge_sources(self, mock_put, mock_credential):
        mock_put.return_value = MagicMock(status_code=201, text="")
        from src.pipeline.themepark_pipeline import setup_themepark_pipeline

        setup_themepark_pipeline(credential=mock_credential)
        body = _find_put_call(mock_put, "agents")
        ks_list = body["knowledgeSources"]
        assert len(ks_list) == 1
        assert ks_list[0]["name"] == "ks-themepark"

    @patch("src.pipeline.themepark_pipeline.requests.put")
    def test_agent_retrieval_instructions(self, mock_put, mock_credential):
        mock_put.return_value = MagicMock(status_code=201, text="")
        from src.pipeline.themepark_pipeline import setup_themepark_pipeline

        setup_themepark_pipeline(credential=mock_credential)
        body = _find_put_call(mock_put, "agents")
        assert "테마파크" in body["retrievalInstructions"]
        assert "한국어" in body["retrievalInstructions"]


# ══════════════════════════════════════════════════════════════
# API 버전 및 보안 검증
# ══════════════════════════════════════════════════════════════


class TestApiAndSecurity:
    """API 버전과 보안 설정을 검증한다."""

    @patch("src.pipeline.themepark_pipeline.requests.put")
    def test_api_version_is_2026_05_01_preview(self, mock_put, mock_credential):
        mock_put.return_value = MagicMock(status_code=201, text="")
        from src.pipeline.themepark_pipeline import setup_themepark_pipeline

        setup_themepark_pipeline(credential=mock_credential)
        for call in mock_put.call_args_list:
            url = call[0][0] if call[0] else call[1].get("url", "")
            assert "api-version=2026-05-01-preview" in url

    @patch("src.pipeline.themepark_pipeline.requests.put")
    def test_no_hardcoded_api_key(self, mock_put, mock_credential):
        """모델 파라미터에 apiKey가 포함되지 않아야 한다."""
        mock_put.return_value = MagicMock(status_code=201, text="")
        from src.pipeline.themepark_pipeline import setup_themepark_pipeline

        setup_themepark_pipeline(credential=mock_credential)

        ks_body = _find_put_call(mock_put, "knowledgesources")
        ingestion = ks_body["azureBlobParameters"]["ingestionParameters"]
        assert "apiKey" not in ingestion["embeddingModel"]["azureOpenAIParameters"]
        assert "apiKey" not in ingestion["chatCompletionModel"]["azureOpenAIParameters"]

        agent_body = _find_put_call(mock_put, "agents")
        for model in agent_body["models"]:
            assert "apiKey" not in model["azureOpenAIParameters"]

    @patch("src.pipeline.themepark_pipeline.requests.put")
    def test_bearer_auth_header(self, mock_put, mock_credential):
        """REST 호출에 Bearer 토큰이 사용되어야 한다."""
        mock_put.return_value = MagicMock(status_code=201, text="")
        from src.pipeline.themepark_pipeline import setup_themepark_pipeline

        setup_themepark_pipeline(credential=mock_credential)
        for call in mock_put.call_args_list:
            headers = call[1].get("headers", {})
            assert headers.get("Authorization") == "Bearer fake-bearer-token"
