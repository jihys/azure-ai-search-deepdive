"""
multimodal_pipeline.py 단위 테스트 — Built-in Skill 전환 검증.

SearchAdminClient.request()를 캡처하여 생성되는 스킬셋/인덱서 페이로드를 검증한다.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest


# ── 환경변수 설정 (import 전에) ──────────────────────────────

@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    """모든 테스트 전에 필수 환경변수를 설정한다."""
    env = {
        "AZURE_SEARCH_SERVICE_ENDPOINT": "https://test-search.search.windows.net",
        "AZURE_SEARCH_ADMIN_KEY": "test-admin-key",
        "AZURE_OPENAI_ENDPOINT": "https://test-openai.openai.azure.com/",
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "text-embedding-3-large",
        "AZURE_STORAGE_RESOURCE_ID": "/subscriptions/00000000/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/testsa",
        "AZURE_STORAGE_CONTAINER_NAME": "raw-documents",
        "AZURE_AI_SERVICES_ENDPOINT": "https://test-ai.cognitiveservices.azure.com/",
        "AZURE_OPENAI_GPT54_DEPLOYMENT": "gpt-5.4",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    # Custom Skill 환경변수가 없어야 함
    monkeypatch.delenv("SKILLS_FUNCTION_URL", raising=False)
    monkeypatch.delenv("SKILLS_FUNCTION_KEY", raising=False)


@pytest.fixture
def mock_client():
    """SearchAdminClient를 목킹하여 request() 호출을 캡처한다."""
    client = MagicMock()
    client.request = MagicMock(return_value={})
    client.delete_if_exists = MagicMock()
    return client


def _find_request_call(mock_client, method: str, path_contains: str) -> dict | None:
    """mock_client.request() 호출 중 특정 패턴의 호출을 찾아 body를 반환한다."""
    for call in mock_client.request.call_args_list:
        args, kwargs = call
        if len(args) >= 2 and args[0] == method and path_contains in args[1]:
            return args[2] if len(args) > 2 else kwargs.get("body")
    return None


def _extract_skills(skillset_body: dict) -> list[dict]:
    """스킬셋 페이로드에서 skills 배열을 추출한다."""
    return skillset_body.get("skills", [])


def _skill_types(skills: list[dict]) -> list[str]:
    """스킬 리스트에서 @odata.type 값들을 추출한다."""
    return [s.get("@odata.type", "") for s in skills]


# ══════════════════════════════════════════════════════════════
# Issue 0010: B-1/B-2 Basic — Custom Split → Built-in SplitSkill
# ══════════════════════════════════════════════════════════════


class TestBasicSkillset:
    """B-1/B-2 Basic 스킬셋이 Custom WebApiSkill 없이 Built-in SplitSkill을 사용하는지 검증."""

    def test_no_webapi_skill(self, mock_client):
        """Basic 스킬셋에 WebApiSkill이 없어야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline

        setup_multimodal_pipeline(pipeline="pdf", client=mock_client)

        skillset_body = _find_request_call(mock_client, "PUT", "/skillsets/multimodal-basic-skillset-pdf")
        assert skillset_body is not None, "Basic PDF skillset PUT not found"

        types = _skill_types(_extract_skills(skillset_body))
        assert "#Microsoft.Skills.Custom.WebApiSkill" not in types, \
            f"WebApiSkill should not be in basic skillset, got: {types}"

    def test_has_split_skill(self, mock_client):
        """Basic 스킬셋에 Built-in SplitSkill이 있어야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline

        setup_multimodal_pipeline(pipeline="pdf", client=mock_client)

        skillset_body = _find_request_call(mock_client, "PUT", "/skillsets/multimodal-basic-skillset-pdf")
        types = _skill_types(_extract_skills(skillset_body))
        assert "#Microsoft.Skills.Text.SplitSkill" in types, \
            f"SplitSkill should be in basic skillset, got: {types}"

    def test_split_skill_config(self, mock_client):
        """SplitSkill이 올바른 설정(maximumPageLength, pageOverlapLength)을 가져야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline

        setup_multimodal_pipeline(pipeline="pdf", client=mock_client)

        skillset_body = _find_request_call(mock_client, "PUT", "/skillsets/multimodal-basic-skillset-pdf")
        skills = _extract_skills(skillset_body)
        split_skills = [s for s in skills if s.get("@odata.type") == "#Microsoft.Skills.Text.SplitSkill"]
        assert len(split_skills) == 1

        split = split_skills[0]
        assert split.get("textSplitMode") == "pages"
        assert split.get("maximumPageLength") == 2000
        assert split.get("pageOverlapLength") == 200

    def test_di_layout_one_to_many(self, mock_client):
        """Basic 스킬셋의 DI Layout이 oneToMany 모드 + markdownHeaderDepth h2여야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline

        setup_multimodal_pipeline(pipeline="pdf", client=mock_client)

        skillset_body = _find_request_call(mock_client, "PUT", "/skillsets/multimodal-basic-skillset-pdf")
        skills = _extract_skills(skillset_body)
        di_skills = [s for s in skills if "DocumentIntelligenceLayout" in s.get("@odata.type", "")]
        assert len(di_skills) == 1
        assert di_skills[0].get("outputMode") == "oneToMany"
        assert di_skills[0].get("markdownHeaderDepth") == "h2"

    def test_index_projection_source_context(self, mock_client):
        """Index projection sourceContext가 /document/markdown_sections/*/pages/* 여야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline

        setup_multimodal_pipeline(pipeline="pdf", client=mock_client)

        skillset_body = _find_request_call(mock_client, "PUT", "/skillsets/multimodal-basic-skillset-pdf")
        projections = skillset_body.get("indexProjections", {})
        selectors = projections.get("selectors", [])
        assert len(selectors) == 1
        assert selectors[0]["sourceContext"] == "/document/markdown_sections/*/pages/*"

    def test_content_type_mapping(self, mock_client):
        """Basic projection에 content_type='text' 매핑이 있어야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline

        setup_multimodal_pipeline(pipeline="pdf", client=mock_client)

        skillset_body = _find_request_call(mock_client, "PUT", "/skillsets/multimodal-basic-skillset-pdf")
        mappings = skillset_body["indexProjections"]["selectors"][0]["mappings"]
        ct_mappings = [m for m in mappings if m["name"] == "content_type"]
        assert len(ct_mappings) == 1
        assert ct_mappings[0]["source"] == "='text'"

    def test_no_skills_function_params(self, mock_client):
        """setup_multimodal_pipeline()이 skills_function 환경변수 없이 동작해야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline

        # SKILLS_FUNCTION_URL/KEY가 없는 상태에서 에러 없이 실행
        setup_multimodal_pipeline(pipeline="pdf", client=mock_client)

        # 모든 request 호출에서 skills_function 참조가 없어야 함
        for call in mock_client.request.call_args_list:
            args = call[0]
            if len(args) > 2 and args[2]:
                body_str = str(args[2])
                assert "skills_function" not in body_str.lower() or "x-functions-key" not in body_str
    
    def test_no_phantom_fields_in_projection(self, mock_client):
        """Index projection에 phantom 필드(file_type, source_category)가 없어야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline

        setup_multimodal_pipeline(pipeline="pdf", client=mock_client)

        skillset_body = _find_request_call(mock_client, "PUT", "/skillsets/multimodal-basic-skillset-pdf")
        projections = skillset_body.get("indexProjections", {})
        mappings = projections["selectors"][0]["mappings"]
        mapping_names = [m["name"] for m in mappings]
        assert "file_type" not in mapping_names, "phantom field file_type should be removed"
        assert "source_category" not in mapping_names, "phantom field source_category should be removed"


# ══════════════════════════════════════════════════════════════
# Issue 0011: B-3/B-4 Verbalized — Custom Verbalize → GenAI Prompt
# ══════════════════════════════════════════════════════════════


class TestVerbalizedSkillset:
    """B-3/B-4 Verbalized 스킬셋이 GenAI Prompt Skill을 사용하는지 검증."""

    def test_no_webapi_skill(self, mock_client):
        """Verbalized 스킬셋에 WebApiSkill이 없어야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline

        setup_multimodal_pipeline(pipeline="verbalized", client=mock_client)

        skillset_body = _find_request_call(mock_client, "PUT", "/skillsets/multimodal-verbalized-skillset-pdf")
        assert skillset_body is not None, "Verbalized PDF skillset PUT not found"

        types = _skill_types(_extract_skills(skillset_body))
        assert "#Microsoft.Skills.Custom.WebApiSkill" not in types, \
            f"WebApiSkill should not be in verbalized skillset, got: {types}"

    def test_has_genai_prompt_skill(self, mock_client):
        """Verbalized 스킬셋에 GenAI Prompt Skill(ChatCompletionSkill)이 있어야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline

        setup_multimodal_pipeline(pipeline="verbalized", client=mock_client)

        skillset_body = _find_request_call(mock_client, "PUT", "/skillsets/multimodal-verbalized-skillset-pdf")
        types = _skill_types(_extract_skills(skillset_body))
        assert "#Microsoft.Skills.Custom.ChatCompletionSkill" in types, \
            f"ChatCompletionSkill should be in verbalized skillset, got: {types}"

    def test_genai_prompt_context_is_normalized_images(self, mock_client):
        """GenAI Prompt Skill의 context가 /document/normalized_images/* 여야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline

        setup_multimodal_pipeline(pipeline="verbalized", client=mock_client)

        skillset_body = _find_request_call(mock_client, "PUT", "/skillsets/multimodal-verbalized-skillset-pdf")
        skills = _extract_skills(skillset_body)
        genai_skills = [s for s in skills if s.get("@odata.type") == "#Microsoft.Skills.Custom.ChatCompletionSkill"]
        assert len(genai_skills) == 1
        assert genai_skills[0].get("context") == "/document/normalized_images/*"

    def test_no_merge_skill(self, mock_client):
        """Verbalized 스킬셋에 MergeSkill이 없어야 한다 (이미지 설명은 별도 청크)."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline

        setup_multimodal_pipeline(pipeline="verbalized", client=mock_client)

        skillset_body = _find_request_call(mock_client, "PUT", "/skillsets/multimodal-verbalized-skillset-pdf")
        types = _skill_types(_extract_skills(skillset_body))
        assert "#Microsoft.Skills.Text.MergeSkill" not in types, \
            f"MergeSkill should not be in verbalized skillset (images are separate chunks), got: {types}"

    def test_has_split_skill(self, mock_client):
        """Verbalized 스킬셋에 SplitSkill이 있어야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline

        setup_multimodal_pipeline(pipeline="verbalized", client=mock_client)

        skillset_body = _find_request_call(mock_client, "PUT", "/skillsets/multimodal-verbalized-skillset-pdf")
        types = _skill_types(_extract_skills(skillset_body))
        assert "#Microsoft.Skills.Text.SplitSkill" in types, \
            f"SplitSkill should be in verbalized skillset, got: {types}"

    def test_has_di_layout_one_to_many(self, mock_client):
        """Verbalized 스킬셋에 DI Layout (oneToMany, h2)이 있어야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline

        setup_multimodal_pipeline(pipeline="verbalized", client=mock_client)

        skillset_body = _find_request_call(mock_client, "PUT", "/skillsets/multimodal-verbalized-skillset-pdf")
        skills = _extract_skills(skillset_body)
        di_skills = [s for s in skills if "DocumentIntelligenceLayout" in s.get("@odata.type", "")]
        assert len(di_skills) == 1
        assert di_skills[0].get("outputMode") == "oneToMany"
        assert di_skills[0].get("markdownHeaderDepth") == "h2"

    def test_two_embedding_skills(self, mock_client):
        """Verbalized 스킬셋에 2개 Embedding 스킬(text + image)이 있어야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline

        setup_multimodal_pipeline(pipeline="verbalized", client=mock_client)

        skillset_body = _find_request_call(mock_client, "PUT", "/skillsets/multimodal-verbalized-skillset-pdf")
        skills = _extract_skills(skillset_body)
        embed_skills = [s for s in skills if "AzureOpenAIEmbedding" in s.get("@odata.type", "")]
        assert len(embed_skills) == 2, f"Expected 2 embedding skills, got {len(embed_skills)}"
        contexts = {s.get("context") for s in embed_skills}
        assert "/document/markdown_sections/*/pages/*" in contexts
        assert "/document/normalized_images/*" in contexts

    def test_two_projection_selectors(self, mock_client):
        """Verbalized projections에 text + image 2개 selector가 있어야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline

        setup_multimodal_pipeline(pipeline="verbalized", client=mock_client)

        skillset_body = _find_request_call(mock_client, "PUT", "/skillsets/multimodal-verbalized-skillset-pdf")
        selectors = skillset_body["indexProjections"]["selectors"]
        assert len(selectors) == 2
        contexts = {s["sourceContext"] for s in selectors}
        assert "/document/markdown_sections/*/pages/*" in contexts
        assert "/document/normalized_images/*" in contexts

    def test_genai_uses_mi_auth(self, mock_client):
        """GenAI Prompt Skill이 apiKey 없이 MI 인증을 사용해야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline

        setup_multimodal_pipeline(pipeline="verbalized", client=mock_client)

        skillset_body = _find_request_call(mock_client, "PUT", "/skillsets/multimodal-verbalized-skillset-pdf")
        skills = _extract_skills(skillset_body)
        genai_skills = [s for s in skills if s.get("@odata.type") == "#Microsoft.Skills.Custom.ChatCompletionSkill"]
        assert len(genai_skills) == 1
        # apiKey가 없거나 비어있어야 함 (MI 사용)
        assert "apiKey" not in genai_skills[0] or genai_skills[0]["apiKey"] in (None, ""), \
            "GenAI Prompt should use MI auth, not apiKey"


class TestVerbalizedIndexer:
    """Verbalized 인덱서에 imageAction 설정이 있는지 검증."""

    def test_image_action_in_verbalized_indexer(self, mock_client):
        """Verbalized 인덱서에 imageAction: generateNormalizedImages가 있어야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline

        setup_multimodal_pipeline(pipeline="verbalized", client=mock_client)

        indexer_body = _find_request_call(mock_client, "PUT", "/indexers/multimodal-verbalized-indexer-pdf")
        assert indexer_body is not None, "Verbalized PDF indexer PUT not found"

        config = indexer_body.get("parameters", {}).get("configuration", {})
        assert config.get("imageAction") == "generateNormalizedImages", \
            f"imageAction should be 'generateNormalizedImages', got: {config}"

    def test_no_image_action_in_basic_indexer(self, mock_client):
        """Basic 인덱서에는 imageAction이 없어야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline

        setup_multimodal_pipeline(pipeline="pdf", client=mock_client)

        indexer_body = _find_request_call(mock_client, "PUT", "/indexers/multimodal-basic-indexer-pdf")
        assert indexer_body is not None

        config = indexer_body.get("parameters", {}).get("configuration", {})
        assert "imageAction" not in config, \
            f"Basic indexer should not have imageAction, got: {config}"


# ══════════════════════════════════════════════════════════════
# Issue 0012: Custom Skill 참조 제거
# ══════════════════════════════════════════════════════════════


class TestNoCustomSkillReferences:
    """전체 파이프라인에서 Custom Skill 참조가 완전히 제거되었는지 검증."""

    def test_full_pipeline_no_webapi_skill(self, mock_client):
        """pipeline='all'로 생성 시 어떤 스킬셋에도 WebApiSkill이 없어야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline

        setup_multimodal_pipeline(pipeline="all", client=mock_client)

        for call in mock_client.request.call_args_list:
            args = call[0]
            if len(args) >= 3 and args[0] == "PUT" and "/skillsets/" in args[1]:
                body = args[2]
                types = _skill_types(body.get("skills", []))
                assert "#Microsoft.Skills.Custom.WebApiSkill" not in types, \
                    f"WebApiSkill found in {args[1]}: {types}"

    def test_no_function_key_in_any_payload(self, mock_client):
        """어떤 API 호출에도 x-functions-key가 포함되지 않아야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline

        setup_multimodal_pipeline(pipeline="all", client=mock_client)

        for call in mock_client.request.call_args_list:
            args = call[0]
            if len(args) >= 3 and args[2]:
                body_str = str(args[2])
                assert "x-functions-key" not in body_str, \
                    f"x-functions-key found in {args[1]}"


# ══════════════════════════════════════════════════════════════
# Issue 0021: academic_field 필터 필드 추가
# ══════════════════════════════════════════════════════════════


class TestAcademicFieldMapping:
    """academic_field 필터 필드가 인덱스/스킬셋/프로젝션에 올바르게 추가되었는지 검증."""

    def test_index_has_academic_field(self, mock_client):
        """인덱스 스키마에 academic_field 필드가 있어야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline
        setup_multimodal_pipeline(pipeline="pdf", client=mock_client)

        index_body = _find_request_call(mock_client, "PUT", "/indexes/multimodal-basic-index-pdf")
        assert index_body is not None
        field_names = [f["name"] for f in index_body["fields"]]
        assert "academic_field" in field_names

        af_field = [f for f in index_body["fields"] if f["name"] == "academic_field"][0]
        assert af_field["filterable"] is True
        assert af_field["facetable"] is True

    def test_basic_skillset_has_conditional_skill(self, mock_client):
        """Basic 스킬셋에 ConditionalSkill이 있어야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline
        setup_multimodal_pipeline(pipeline="pdf", client=mock_client)

        skillset_body = _find_request_call(mock_client, "PUT", "/skillsets/multimodal-basic-skillset-pdf")
        types = _skill_types(_extract_skills(skillset_body))
        assert "#Microsoft.Skills.Util.ConditionalSkill" in types

    def test_verbalized_skillset_has_conditional_skill(self, mock_client):
        """Verbalized 스킬셋에 ConditionalSkill이 있어야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline
        setup_multimodal_pipeline(pipeline="verbalized", client=mock_client)

        skillset_body = _find_request_call(mock_client, "PUT", "/skillsets/multimodal-verbalized-skillset-pdf")
        types = _skill_types(_extract_skills(skillset_body))
        assert "#Microsoft.Skills.Util.ConditionalSkill" in types

    def test_projection_has_academic_field(self, mock_client):
        """Index projection에 academic_field 매핑이 있어야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline
        setup_multimodal_pipeline(pipeline="pdf", client=mock_client)

        skillset_body = _find_request_call(mock_client, "PUT", "/skillsets/multimodal-basic-skillset-pdf")
        mappings = skillset_body["indexProjections"]["selectors"][0]["mappings"]
        mapping_names = [m["name"] for m in mappings]
        assert "academic_field" in mapping_names

        af_mapping = [m for m in mappings if m["name"] == "academic_field"][0]
        assert af_mapping["source"] == "/document/academic_field"

    def test_verbalized_projection_has_academic_field(self, mock_client):
        """Verbalized projection의 text+image selector 모두에 academic_field 매핑이 있어야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline
        setup_multimodal_pipeline(pipeline="verbalized", client=mock_client)

        skillset_body = _find_request_call(mock_client, "PUT", "/skillsets/multimodal-verbalized-skillset-pdf")
        selectors = skillset_body["indexProjections"]["selectors"]
        for selector in selectors:
            mapping_names = [m["name"] for m in selector["mappings"]]
            assert "academic_field" in mapping_names, \
                f"academic_field missing in selector with sourceContext={selector['sourceContext']}"

    def test_conditional_skill_before_embedding(self, mock_client):
        """ConditionalSkill이 embedding-skill보다 앞에 있어야 한다."""
        from src.pipeline.multimodal_pipeline import setup_multimodal_pipeline
        setup_multimodal_pipeline(pipeline="pdf", client=mock_client)

        skillset_body = _find_request_call(mock_client, "PUT", "/skillsets/multimodal-basic-skillset-pdf")
        skills = _extract_skills(skillset_body)
        cond_idx = next(i for i, s in enumerate(skills) if s.get("@odata.type") == "#Microsoft.Skills.Util.ConditionalSkill")
        embed_idx = next(i for i, s in enumerate(skills) if s.get("name") == "embedding-skill")
        assert cond_idx < embed_idx
