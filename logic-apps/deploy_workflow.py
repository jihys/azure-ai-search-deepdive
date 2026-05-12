"""
Logic Apps 워크플로우 배포 스크립트
Kudu REST API를 통해 Logic App Standard에 워크플로우를 배포합니다.

워크플로우 구성:
  - rag-indexing-workflow: Blob 트리거 → DI → Chunking → Embedding → AI Search
  - crawl-workflow: 일별 스케줄 → law.go.kr 크롤링 → Blob 업로드 (→ 자동 트리거)
"""

import json
import os
import sys

import requests
from azure.identity import DefaultAzureCredential
from azure.mgmt.web import WebSiteManagementClient
from azure.mgmt.web.models import StringDictionary
from dotenv import load_dotenv

load_dotenv()


def deploy_workflow():
    """Logic App Standard에 워크플로우 및 연결 설정 배포"""

    subscription_id = os.environ["AZURE_SUBSCRIPTION_ID"]
    resource_group = os.environ.get("AZURE_RESOURCE_GROUP", "rg-rag-indexing-lab")
    logic_app_name = os.environ.get("AZURE_LOGIC_APP_NAME", "")

    if not logic_app_name:
        print("[오류] AZURE_LOGIC_APP_NAME이 .env에 설정되지 않았습니다.")
        sys.exit(1)

    credential = DefaultAzureCredential()
    web_client = WebSiteManagementClient(credential, subscription_id)

    # 1. App Settings 업데이트 (Bicep에서 설정한 것과 병합)
    print("[배포] Logic App 앱 설정 확인 중...")
    existing = web_client.web_apps.list_application_settings(resource_group, logic_app_name)
    print(f"  기존 앱 설정 {len(existing.properties)}개 확인")

    # 2. Kudu API를 통해 워크플로우 파일 배포
    print("[배포] 워크플로우 파일 배포 중...")

    logic_apps_dir = os.path.dirname(__file__)
    files_to_deploy = {
        "host.json": os.path.join(logic_apps_dir, "host.json"),
        "connections.json": os.path.join(logic_apps_dir, "connections.json"),
        "rag-indexing-workflow/workflow.json": os.path.join(
            logic_apps_dir, "rag-indexing-workflow", "workflow.json"
        ),
        "crawl-workflow/workflow.json": os.path.join(
            logic_apps_dir, "crawl-workflow", "workflow.json"
        ),
    }

    scm_url = f"https://{logic_app_name}.scm.azurewebsites.net"
    token = credential.get_token("https://management.azure.com/.default")
    headers = {
        "Authorization": f"Bearer {token.token}",
        "Content-Type": "application/octet-stream",
    }

    success_count = 0
    for remote_path, local_path in files_to_deploy.items():
        if not os.path.exists(local_path):
            print(f"  [경고] 파일 없음: {local_path}")
            continue

        with open(local_path, "r", encoding="utf-8") as f:
            content = f.read()

        api_url = f"{scm_url}/api/vfs/site/wwwroot/{remote_path}"
        resp = requests.put(
            api_url,
            headers={**headers, "If-Match": "*"},
            data=content.encode("utf-8"),
            timeout=30,
        )

        if resp.status_code in (200, 201, 204):
            print(f"  ✓ {remote_path}")
            success_count += 1
        else:
            print(f"  ✗ {remote_path}: {resp.status_code} {resp.text[:200]}")

    print(f"\n[배포] 완료: {success_count}/{len(files_to_deploy)} 파일 배포 성공")
    print(f"[포탈] https://portal.azure.com/#resource/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Web/sites/{logic_app_name}/logicApp")


if __name__ == "__main__":
    deploy_workflow()
