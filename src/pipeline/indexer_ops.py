"""
AI Search REST API 클라이언트 및 인덱서 운영 유틸리티.

nb03/nb05 공용 — 인덱서 실행, 상태 폴링, 완료 대기.
"""

from __future__ import annotations

import os
import socket
import time
from urllib.parse import urlparse

import requests
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

API_VERSION = "2026-04-01"


class SearchAdminClient:
    """AI Search REST API 클라이언트 (API key 또는 Bearer token 인증)."""

    def __init__(self, endpoint: str | None = None, admin_key: str | None = None):
        endpoint = endpoint or os.getenv("AZURE_SEARCH_ENDPOINT") or os.getenv("AZURE_SEARCH_SERVICE_ENDPOINT", "")
        self.endpoint = _normalize_endpoint(endpoint)
        self.admin_key = admin_key or os.getenv("AZURE_SEARCH_ADMIN_KEY", "")
        self._credential = (
            DefaultAzureCredential(
                exclude_managed_identity_credential=True,
                exclude_workload_identity_credential=True,
            )
            if not self.admin_key
            else None
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.admin_key:
            headers["api-key"] = self.admin_key
        else:
            token = self._credential.get_token("https://search.azure.com/.default")
            headers["Authorization"] = f"Bearer {token.token}"
        return headers

    def request(self, method: str, path: str, body: dict | None = None, timeout: int = 120) -> dict:
        sep = "&" if "?" in path else "?"
        url = f"{self.endpoint}{path}{sep}api-version={API_VERSION}"
        resp = _request_with_retry(method, url, headers=self._headers(), json=body, timeout=timeout)
        if resp.status_code not in (200, 201, 202, 204):
            print(f"[ERROR] {method} {path} → {resp.status_code}")
            print(resp.text[:1500])
            resp.raise_for_status()
        return resp.json() if resp.content else {}

    def delete_if_exists(self, path: str) -> None:
        url = f"{self.endpoint}{path}?api-version={API_VERSION}"
        resp = _request_with_retry("DELETE", url, headers=self._headers(), timeout=120)
        if resp.status_code in (200, 202, 204):
            print(f"  - deleted {path}")

    def assert_dns_resolvable(self, attempts: int = 3, wait_sec: int = 2) -> None:
        host = urlparse(self.endpoint).hostname or ""
        if not host:
            raise RuntimeError(f"Invalid search endpoint: {self.endpoint}")
        last_exc: Exception | None = None
        for i in range(1, attempts + 1):
            try:
                socket.getaddrinfo(host, 443)
                return
            except OSError as exc:
                last_exc = exc
                if i < attempts:
                    time.sleep(wait_sec)
        raise RuntimeError(
            f"Failed to resolve AI Search host: {host}. "
            "Check DNS/network and verify endpoint."
        ) from last_exc


# ── 인덱서 운영 함수 ─────────────────────────────────────────


def run_indexer(client: SearchAdminClient, indexer_name: str) -> None:
    """인덱서 즉시 실행."""
    client.request("POST", f"/indexers/{indexer_name}/run")
    print(f"  → Indexer '{indexer_name}' 실행 요청")


def reset_indexer(client: SearchAdminClient, indexer_name: str) -> None:
    """인덱서 리셋 (change tracking 초기화)."""
    url = f"{client.endpoint}/indexers/{indexer_name}/reset?api-version={API_VERSION}"
    resp = _request_with_retry("POST", url, headers=client._headers(), json={}, timeout=120)
    if resp.status_code == 204:
        print(f"  - Indexer '{indexer_name}' reset 완료")
    elif resp.status_code != 404:
        print(f"  - Indexer reset: {resp.status_code}")


def get_indexer_status(client: SearchAdminClient, indexer_name: str) -> dict:
    """인덱서 상태 조회."""
    return client.request("GET", f"/indexers/{indexer_name}/status")


def poll_indexer(client: SearchAdminClient, indexer_name: str, timeout_sec: int = 1800, interval: int = 15) -> dict:
    """인덱서 완료까지 폴링. 완료 시 lastResult 반환."""
    start = time.time()
    while True:
        status = get_indexer_status(client, indexer_name)
        last = status.get("lastResult") or {}
        state = last.get("status", "unknown")
        processed = last.get("itemsProcessed", 0)
        failed = last.get("itemsFailed", 0)
        print(f"    [{indexer_name}] {state} (처리 {processed}건, 실패 {failed}건)")
        if state in ("success", "transientFailure", "persistentFailure", "reset"):
            return last
        if (time.time() - start) > timeout_sec:
            print(f"    [{indexer_name}] 타임아웃 ({timeout_sec}s)")
            return last
        time.sleep(interval)


def wait_for_indexer(client: SearchAdminClient, indexer_name: str, timeout_sec: int = 1800) -> dict:
    """인덱서 실행 + 완료 대기 (run + poll 합성)."""
    run_indexer(client, indexer_name)
    return poll_indexer(client, indexer_name, timeout_sec=timeout_sec)


# ── 내부 헬퍼 ────────────────────────────────────────────────


def _normalize_endpoint(endpoint: str) -> str:
    endpoint = (endpoint or "").strip()
    if not endpoint:
        return endpoint
    if not endpoint.startswith(("http://", "https://")):
        endpoint = f"https://{endpoint}"
    return endpoint.rstrip("/")


def _request_with_retry(method: str, url: str, tries: int = 3, retry_wait: int = 2, **kwargs) -> requests.Response:
    last_exc: Exception | None = None
    for i in range(1, tries + 1):
        try:
            return requests.request(method, url, **kwargs)
        except requests.exceptions.ConnectionError as exc:
            last_exc = exc
            if i < tries:
                time.sleep(retry_wait)
    raise RuntimeError(f"Connection failed after {tries} retries: {url}") from last_exc
