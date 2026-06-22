# PRD: 테마파크 Knowledge Source + 논문 분야 필터 추가

**Status:** ready-for-agent

## 요약

1. 기존 멀티모달 파이프라인(B-1~B-4)에 `academic_field` 필터 필드 추가 — 파일명 prefix (ST/SS/HA)에서 자동 매핑
2. 테마파크 데이터를 위한 별도 인덱스 — Foundry Knowledge Source API (default OCR + verbalization + Image Serving) 사용, DI Layout 기반 파이프라인 미사용

## 동기

1. 논문 데이터의 학문 분야(과학기술/사회과학/인문학예술체육학) 필터링으로 검색 정밀도 향상
2. 테마파크 지도/가이드 데이터는 이미지 중심이므로 Foundry의 built-in OCR + verbalization이 최적
3. Image Serving 기능으로 원본 이미지 반환 (지도 기반 질문 응답에 필수)
4. 테마파크는 별도 Knowledge Source / Knowledgebase로 등록하여 Agentic Retrieval에서 독립 검색

## 1. 논문 분야 필터 (B-1~B-4 기존 파이프라인)

### 변경 내용

- 인덱스 스키마: `academic_field` 필드 추가 (Edm.String, filterable, facetable)
- Indexer field mapping: `metadata_storage_name`에서 prefix 추출 → `academic_field`로 매핑
  - `ST_*` → `"과학기술"`
  - `SS_*` → `"사회과학"`
  - `HA_*` → `"인문학예술체육학"`
  - 기타 → `null` 또는 `"기타"`
- 방법: Indexer의 `fieldMappings`에서 custom mapping function 사용하거나, Skillset에 ConditionalSkill 추가

### 수용 기준

- `academic_field` 필드로 filter 쿼리 가능: `$filter=academic_field eq '과학기술'`
- 기존 테스트 깨지지 않음
- 파일명에 ST/SS/HA prefix가 없는 파일은 `academic_field`가 null

## 2. 테마파크 Knowledge Source (별도 인덱스)

### 아키텍처

```
Blob (raw/pdf/themepark/) 
  → Foundry Knowledge Source (azureBlob kind)
    - embeddingModel: text-embedding-3-large
    - chatCompletionModel: gpt-5.4
    - disableImageVerbalization: false
    - contentExtractionMode: "standard"  
    - assetStore: 별도 컨테이너 (이미지 저장용)
  → Knowledgebase
    - answerInstructions: 한국어 응답
    - retrievalInstructions: 테마파크 관련 쿼리 처리
  → Agentic Retrieval (enable-image-serving=true)
```

### 쿼리 패턴 (image-serving-demo.http 참조)

```json
POST /knowledgebases/{name}/retrieve?enable-image-serving=true
{
  "retrievalReasoningEffort": {"kind": "medium"},
  "outputMode": "answerSynthesis",
  "messages": [{"role": "user", "content": [{"type": "text", "text": "에버랜드에서 T-Express 위치는?"}]}]
}
```

### 데이터

- `data/raw/pdf/themepark/everland_guide.pdf` (30MB, 에버랜드 가이드맵)
- `data/raw/pdf/themepark/lotteworld_guide.pdf` (24MB, 롯데월드 가이드맵)
- `data/raw/pdf/themepark/grandpark_zoo_guidemap_2025_*.jpg` (서울대공원 동물원)
- `data/raw/pdf/themepark/2_2_3_guide_map_map02.png` (서울대공원 지도)

### 수용 기준

- Knowledge Source 생성 성공
- Knowledgebase 생성 성공
- Image verbalization 확인 (인덱스에서 `image_snippet_parent_id ne null` 쿼리)
- Image Serving 비활성/활성 비교
- 위치 관계 질문에 대해 정확한 응답 ("에버랜드에서 X와 Y는 가까운가요?")

## 변경 파일 (예상)

- `src/pipeline/multimodal_pipeline.py` — academic_field 필드 + 매핑
- `src/pipeline/themepark_pipeline.py` (신규) — Knowledge Source/KB 생성 스크립트
- `tests/test_multimodal_pipeline.py` — academic_field 관련 테스트 추가
- `notebooks/07-content-understanding.ipynb` 또는 별도 노트북 — themepark 데모

## 리스크

- Image Serving은 service-level feature flag 필요 (Gia Mondragon 연락 필요할 수 있음)
- 30MB 이미지 PDF의 verbalization 품질/비용
- Knowledge Source API 버전 (`2025-11-01-preview` 또는 최신)

## 관련 이슈

- 이슈 분해 후 등록 예정
