"""
Azure OpenAI Embedding 생성기
"""

from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential


class EmbeddingGenerator:
    """Azure OpenAI를 사용한 텍스트 임베딩 생성"""

    def __init__(
        self,
        endpoint: str,
        api_key: str | None = None,
        deployment: str = "text-embedding-3-large",
    ):
        if api_key:
            self.client = AzureOpenAI(
                azure_endpoint=endpoint,
                api_key=api_key,
                api_version="2024-10-21",
            )
        else:
            credential = DefaultAzureCredential()
            token = credential.get_token("https://cognitiveservices.azure.com/.default")
            self.client = AzureOpenAI(
                azure_endpoint=endpoint,
                azure_ad_token=token.token,
                api_version="2024-10-21",
            )
        self.deployment = deployment

    def generate(self, text: str) -> list[float]:
        """단일 텍스트에 대한 임베딩 벡터 생성"""
        response = self.client.embeddings.create(
            input=text,
            model=self.deployment,
        )
        return response.data[0].embedding

    def generate_batch(self, texts: list[str], batch_size: int = 16) -> list[list[float]]:
        """배치 단위로 임베딩 생성"""
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = self.client.embeddings.create(
                input=batch,
                model=self.deployment,
            )
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)
            print(f"[임베딩] {i + len(batch)}/{len(texts)} 생성 완료")

        return all_embeddings

    def enrich_chunks_with_embeddings(self, chunks: list[dict]) -> list[dict]:
        """청크 리스트에 임베딩 벡터를 추가"""
        texts = [chunk["content"] for chunk in chunks]
        embeddings = self.generate_batch(texts)

        for chunk, embedding in zip(chunks, embeddings):
            chunk["embeddings"] = embedding

        print(f"[임베딩] {len(chunks)}개 청크에 임베딩 추가 완료")
        return chunks
