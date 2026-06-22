# 0022: 테마파크 Knowledge Source 파이프라인

**Status:** done
**Parent:** [PRD-themepark-and-academic-field](../prd/PRD-themepark-and-academic-field.md)

## 요약

테마파크 데이터(에버랜드, 롯데월드, 서울대공원)를 위한 별도 Knowledge Source 파이프라인을 생성한다. Foundry Knowledge Source API를 사용하여 OCR + verbalization + Image Serving을 활용한다.

## 상세

### 파이프라인 구조

```
Blob (data/raw/pdf/themepark/)
  → Foundry Knowledge Source (azureBlob kind)
    - embeddingModel: text-embedding-3-large
    - chatCompletionModel: gpt-5.4
    - disableImageVerbalization: false
    - contentExtractionMode: "standard"
    - assetStore: 별도 컨테이너 (이미지 저장용)
  → Knowledgebase
    - answerInstructions: 한국어 응답
    - retrievalInstructions: 테마파크 관련 쿼리 처리
```

### 구현 내용

1. `src/pipeline/themepark_pipeline.py` 신규 생성
   - Knowledge Source 생성 (azureBlob kind, OCR + verbalization)
   - Knowledgebase 생성 (answerInstructions, retrievalInstructions)
   - Asset Store 설정 (Image Serving용 별도 컨테이너)
2. Blob에 테마파크 데이터 업로드 (기존 `scripts/upload_multimodal_data.sh` 확장 또는 별도 스크립트)

### 데이터

- `data/raw/pdf/themepark/everland_guide.pdf` (에버랜드 가이드맵)
- `data/raw/pdf/themepark/lotteworld_guide.pdf` (롯데월드 가이드맵)
- `data/raw/pdf/themepark/grandpark_zoo_guidemap_2025_*.jpg` (서울대공원 동물원)
- `data/raw/pdf/themepark/2_2_3_guide_map_map02.png` (서울대공원 지도)

## 수용 기준

- [ ] Knowledge Source 생성 성공 (REST API 200)
- [ ] Knowledgebase 생성 성공
- [ ] 인덱스에 문서 인덱싱 확인 (`GET /indexes/{name}/docs/$count`)
- [ ] Image verbalization 동작 확인 (`$filter=image_snippet_parent_id ne null` 결과 존재)
- [ ] Asset Store에 이미지 저장 확인

## 변경 파일

- `src/pipeline/themepark_pipeline.py` (신규) — KS/KB 생성 스크립트
- `scripts/upload_themepark_data.sh` (신규, 선택) — Blob 업로드
- `.env` / `sample.env` — 필요 시 환경 변수 추가

## 의존성

- Azure AI Foundry IQ 리소스 배포 완료
- Blob Storage에 테마파크 데이터 업로드 완료
- Image Serving feature flag 활성화 필요할 수 있음

## 리스크

- Image Serving은 service-level feature flag 필요 (Gia Mondragon 연락 필요할 수 있음)
- 30MB 이미지 PDF의 verbalization 품질/비용
- Knowledge Source API 버전: `2025-11-01-preview` 또는 최신
