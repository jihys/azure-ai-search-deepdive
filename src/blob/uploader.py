"""
Azure Blob Storage 업로더 - 크롤링 데이터를 날짜별 폴더에 업로드
"""

import os
from datetime import datetime

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings


class BlobUploader:
    """Blob Storage에 날짜별 폴더 구조로 파일을 업로드"""

    def __init__(
        self,
        account_name: str | None = None,
        connection_string: str | None = None,
        container_name: str = "raw-documents",
    ):
        self.container_name = container_name

        if connection_string:
            self.blob_service = BlobServiceClient.from_connection_string(connection_string)
        elif account_name:
            account_url = f"https://{account_name}.blob.core.windows.net"
            credential = DefaultAzureCredential()
            self.blob_service = BlobServiceClient(account_url, credential=credential)
        else:
            raise ValueError("account_name 또는 connection_string 중 하나를 제공해야 합니다.")

        self.container_client = self.blob_service.get_container_client(container_name)

    def ensure_container_exists(self) -> None:
        """컨테이너가 없으면 생성"""
        try:
            self.container_client.get_container_properties()
        except Exception:
            self.container_client.create_container()
            print(f"[Blob] 컨테이너 생성: {self.container_name}")

    def upload_file(
        self,
        local_path: str,
        blob_name: str | None = None,
        date_folder: str | None = None,
        content_type: str | None = None,
    ) -> str:
        """파일을 Blob Storage에 업로드

        Args:
            local_path: 로컬 파일 경로
            blob_name: Blob 이름 (None이면 파일명 사용)
            date_folder: 날짜 폴더명 (None이면 오늘 날짜)
            content_type: Content-Type 헤더

        Returns:
            업로드된 Blob의 전체 경로
        """
        if date_folder is None:
            date_folder = datetime.now().strftime("%Y-%m-%d")

        if blob_name is None:
            blob_name = os.path.basename(local_path)

        full_blob_path = f"{date_folder}/{blob_name}"

        # Content-Type 자동 감지
        if content_type is None:
            if blob_name.endswith(".md"):
                content_type = "text/markdown; charset=utf-8"
            elif blob_name.endswith(".json"):
                content_type = "application/json; charset=utf-8"
            elif blob_name.endswith(".pdf"):
                content_type = "application/pdf"
            else:
                content_type = "application/octet-stream"

        content_settings = ContentSettings(content_type=content_type)

        with open(local_path, "rb") as f:
            self.container_client.upload_blob(
                name=full_blob_path,
                data=f,
                overwrite=True,
                content_settings=content_settings,
            )

        print(f"[Blob] 업로드 완료: {self.container_name}/{full_blob_path}")
        return full_blob_path

    def upload_content(
        self,
        content: str | bytes,
        blob_name: str,
        date_folder: str | None = None,
        content_type: str = "text/plain; charset=utf-8",
    ) -> str:
        """문자열/바이트 데이터를 직접 업로드"""
        if date_folder is None:
            date_folder = datetime.now().strftime("%Y-%m-%d")

        full_blob_path = f"{date_folder}/{blob_name}"

        if isinstance(content, str):
            content = content.encode("utf-8")

        content_settings = ContentSettings(content_type=content_type)

        self.container_client.upload_blob(
            name=full_blob_path,
            data=content,
            overwrite=True,
            content_settings=content_settings,
        )

        print(f"[Blob] 업로드 완료: {self.container_name}/{full_blob_path}")
        return full_blob_path

    def upload_directory(self, local_dir: str, date_folder: str | None = None) -> list[str]:
        """로컬 디렉토리의 모든 파일을 업로드"""
        uploaded = []
        for root, _, files in os.walk(local_dir):
            for filename in files:
                local_path = os.path.join(root, filename)
                # 상대 경로 유지
                rel_path = os.path.relpath(local_path, local_dir)
                blob_path = self.upload_file(
                    local_path=local_path,
                    blob_name=rel_path,
                    date_folder=date_folder,
                )
                uploaded.append(blob_path)
        return uploaded

    def list_blobs(self, prefix: str | None = None) -> list[str]:
        """Blob 목록 조회"""
        blobs = self.container_client.list_blobs(name_starts_with=prefix)
        return [blob.name for blob in blobs]
