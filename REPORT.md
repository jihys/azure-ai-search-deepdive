# 인덱싱 리포트 (Sweden Central)

> 측정일자: 2026-05-14 / Region: `swedencentral` / Resource Group: `rg-rag-indexing-lab-swc`
> Search Service: `search-ragi-dyn6dtfu` (Standard S1)
> Embedding 모델: `text-embedding-3-large` (dim 3072)

---

## 1. 한눈에 보기

| 항목 | 값 |
|------|---:|
| 인덱스 수 | 4 (`prec`, `const`, `legis-interp`, `admin-appeal`) |
| **입력 Blob 크기** | **474.8 MiB** (8 JSONL 파일) |
| **인덱싱 대상 문서** | **59,372** |
| **AI Search 색인 완료 문서** | **59,366** (실패 6건 = 0.01%) |
| **AI Search storage 사용량** | **1,613.8 MiB** (4개 인덱스 합) |
| **AI Search vector 용량** | **335.2 MiB** (4개 인덱스 합) |
| **storage / 입력 비율** | 3.40 × |
| **vector / 입력 비율** | 0.71 × |
| **1차 인덱싱 (병렬) wall clock** | **17.5 분** (max indexer 기준) |
| **재인덱싱 (캐시 hit) wall clock** | **2.7 초** (4개 indexer 합) |
| **재인덱싱 시간 절감율** | **99.99 %** |
| **임베딩 비용 (1차)** | **약 $3.86** (text-embedding-3-large) |
| **임베딩 비용 (재인덱싱)** | **$0** (캐시) |

### 1.1 AI Search 서비스 전체 볼륨 (Tier S1)

본 프로젝트 4개 인덱스 + 별도 멀티모달 PoC 3개 인덱스를 포함한 **서비스 단위** 사용량.

| 항목 | 사용량 | Quota (S1) | 사용률 |
|------|------:|-----------:|------:|
| **Storage** | **2,225.0 MiB** (≈ 2.17 GiB) | 163,840 MiB (160 GiB) | **1.36 %** |
| **Vector index** | **498.8 MiB** | 35,840 MiB (35 GiB) | **1.39 %** |
| **Document count** | **72,291** | 무제한 (S1) | — |
| **Index count** | **7** | 50 | 14 % |

**인덱스별 분포 (서비스 전체)**

| Index | docs | storage (MiB) | vector (MiB) | 용도 |
|-------|----:|--------------:|------------:|------|
| `prec-court-index` | 18,841 | 522.7 | 108.0 | 본 프로젝트 — 판례 |
| `const-court-index` | 24,980 | 325.8 | 44.4 | 본 프로젝트 — 헌재 결정 |
| `legis-interp-index` | 8,715 | 410.0 | 102.5 | 본 프로젝트 — 법제처 해석 |
| `admin-appeal-index` | 6,830 | 342.6 | 80.3 | 본 프로젝트 — 행정심판 |
| `st-multimodal-pdf-index` | 6,307 | 309.9 | 74.2 | 멀티모달 PoC |
| `st-multimodal-pptx-index` | 311 | 14.5 | 3.9 | 멀티모달 PoC |
| `st-multimodal-verbalized-index` | 6,307 | 274.1 | 85.4 | 멀티모달 PoC |
| **본 프로젝트 4개 합** | **59,366** | **1,601.1** | **335.2** | — |
| **서비스 총합 (7 인덱스)** | **72,291** | **2,225.0** | **498.8** | — |

> 초기 단일 통합 인덱스 시도였던 빈 `law-documents-index` 와 관련 indexer/skillset/datasource(`law-*`) 는 cleanup 완료.

> S1 quota 대비 1.4 % 수준 — 기준 데이터 셋 (약 60K docs / 475 MiB) 대비 100배 (≈ 6M docs / 47 GiB) 까지 단일 서비스로 확장 여유 있음.

---

## 2. 인덱스별 상세

### 2.1 문서 / 스토리지

| Index | docs | storage (MiB) | vector (MiB) | storage/doc (KB) | vector/doc (KB) |
|-------|-----:|--------------:|-------------:|-----------------:|----------------:|
| `prec-court-index` (판례) | 18,841 | 522.7 | 108.0 | 28.4 | 5.87 |
| `const-court-index` (헌재 결정) | 24,980 | 338.5 | 44.4 | 13.9 | 1.82 |
| `legis-interp-index` (법제처 해석) | 8,715 | 410.0 | 102.5 | 48.2 | 12.05 |
| `admin-appeal-index` (행정심판) | 6,830 | 342.6 | 80.3 | 51.3 | 12.04 |
| **합계** | **59,366** | **1,613.8** | **335.2** | — | — |

> 주: `storage` 는 inverted index + 원문 + 메타 + 벡터를 모두 포함한 AI Search 내부 저장. Blob Storage 입력 (`processed-documents/*.jsonl`)과는 별개.

### 2.2 1차 인덱싱 시간 (병렬 실행)

| Index | docs | 시간 | 처리율 (docs/s) | 처리율 (MiB/min) |
|-------|-----:|-----:|----------------:|-----------------:|
| `prec-blob-indexer` | 18,841 | 864.1 s | 21.8 | 11.0 |
| `const-blob-indexer` | 24,985 | 1,049.0 s | 23.8 | 9.4 |
| `interp-blob-indexer` | 8,715 | 408.2 s | 21.3 | 10.9 |
| `admin-blob-indexer` | 6,831 | 291.9 s | 23.4 | 16.0 |
| **wall clock (병렬)** | 59,372 | **17.5 분** (longest = const) | — | — |
| **총 indexer-time** | 59,372 | **43.5 분** (단순합) | — | — |

### 2.3 재인덱싱 시간 (캐시 hit)

> 데이터 / 스킬셋 / 임베딩 입력 모두 동일하면 **HighWaterMark 기반 변경 추적**으로 처리 0건 만에 종료.

| Index | 1차 시간 | 재실행 시간 | 절감 |
|-------|---------:|------------:|-----:|
| `prec-blob-indexer` | 864.1 s | **1.2 s** | −99.86 % |
| `const-blob-indexer` | 1,049.0 s | **0.1 s** | −99.99 % |
| `interp-blob-indexer` | 408.2 s | **0.2 s** | −99.95 % |
| `admin-blob-indexer` | 291.9 s | **0.9 s** | −99.69 % |
| **합계** | 2,613 s | **2.4 s** | **−99.91 %** |

> 데이터 변경이 발생한 문서만 임베딩 재호출 → 비용도 비례 절감.

---

## 3. 비용 추정

### 3.1 1차 인덱싱

text-embedding-3-large 단가 = **$0.13 / 1M token**

| Index | 처리 docs | 추정 token (avg 500/doc) | 비용 |
|-------|----------:|-------------------------:|-----:|
| `prec` | 18,841 | 9.42 M | $1.22 |
| `const` | 24,985 | 12.49 M | $1.62 |
| `interp` | 8,715 | 4.36 M | $0.57 |
| `admin` | 6,831 | 3.42 M | $0.44 |
| **합계** | **59,372** | **29.69 M** | **≈ $3.86** |

> 실제 청구액은 한국어 토큰 분포·SplitSkill 분할 횟수에 따라 ±20 % 범위.

### 3.2 재인덱싱

| 시나리오 | 임베딩 비용 |
|----------|------------:|
| 데이터 무변경 → indexer 트리거 | **$0** |
| 메타데이터 컬럼 추가 | **$0** (인덱스 스키마만 변경, 임베딩 입력 미변경) |
| 임베딩 입력 필드 변경 | 변경분만 재호출 (변경 % × 단가) |

---

## 4. 캐싱 (Incremental Enrichment Cache)

### 4.1 두 종류 캐시

AI Search 인덱서는 **2 단계 캐시**를 사용해 재인덱싱 비용을 줄임:

| 단계 | 위치 | 동작 |
|------|------|------|
| ① **변경 추적** (Change Detection) | DataSource 정의 | `metadata_storage_last_modified` 워터마크 → 변경된 blob 만 처리 |
| ② **Enrichment Cache** (옵션) | Storage 계정의 별도 컨테이너 | Skill 단계별 결과 (split chunks / 임베딩) 영속 저장 → 동일 입력이면 임베딩 재호출 안 함 |

### 4.2 본 프로젝트 구성

- ① **변경 추적은 항상 켜짐** — `HighWaterMarkChangeDetectionPolicy(metadata_storage_last_modified)`
- ② **Enrichment Cache 는 옵션** — `SETUP_ENABLE_CACHE=1` 환경변수로 토글
  - 기본값 OFF (첫 색인은 어차피 캐시 hit 가 없으므로)
  - ON 시 `cache.storageConnectionString = ResourceId={STORAGE_ID};` (Search MSI 가 `Storage Blob Data Contributor` 필요)

### 4.3 위 측정값에서의 효과

위 § 2.3 의 재인덱싱 시간 (1.2 s 등) 은 **① 변경 추적 만으로** 달성된 결과 (데이터가 안 바뀐 케이스).

② enrichment cache 의 진가는 **임베딩 입력 필드는 그대로지만 인덱스 스키마(예: 새 필드 추가) 가 바뀌어 모든 문서를 재처리해야 할 때** 나옴 — 변경 추적만으로는 모든 문서 재처리 = 임베딩 비용 $3.86 재발생, 캐시가 있으면 임베딩 결과 재사용 = $0.

### 4.4 캐시 사용 시 주의사항

- DataSource 또는 Skillset 정의가 바뀌면 "cache가 무효화" → API 호출이 400 으로 실패. 해결: 인덱서 `reset` 후 PUT (또는 `?ignoreResetRequirement=true` 쿼리)
- Search MSI 는 cache 컨테이너에 **Storage Blob Data Contributor** 권한 필요. Reader 만 있으면 `Credentials … invalid` 에러로 transientFailure 발생
- Storage 추가 비용 발생 (수 GB 수준)

---

## 5. 인덱싱 안정성: 실패 케이스와 해결

| 라운드 | 실패 건수 | 원인 | 해결 |
|-------:|----------:|------|------|
| 1차 | 1,812 (3.05 %) | `fullText` 가 filterable/sortable/facetable 켜져 있어 32 KB 단일 토큰으로 색인 → 한도 초과 | `_text_long()` 에 filter/sort/facet=`false` 명시, custom analyzer `ko_safe` (장문 강제 분할) 적용 |
| 2차 | 10 (0.017 %) | 임베딩 입력 8K 토큰 한도 초과 | 스킬셋에 `SplitSkill(maximumPageLength=12000)` 추가 |
| 3차 | 6 (0.010 %) | 한국어 char ≈ 1 token 이라 12000 chars 도 초과 | `maximumPageLength=5000` 으로 축소 |
| **최종** | **6 (0.010 %)** | 단일 청크가 5000 chars 안에서 잘리지 않는 극단 케이스 (소수) | 운영상 무시 가능 (RAG 결과 품질에 영향 미미) |

**SplitSkill 의 역할 정리**

- `textSplitMode: "pages"` 의 *page* = PDF 페이지가 아니라 **임의 텍스트의 청크 단위**
- text-embedding-3-large 는 입력당 **8,192 token hard limit** → 긴 본문은 무조건 분할 필수
- 한국어 한자 섞인 텍스트의 경우 `1 char ≈ 1~2 token` → `maximumPageLength=5000` 이 안전 마진
- 본 프로젝트는 첫 청크 (`/document/embedSourcePages/0`) 만 임베딩 → 단일 벡터 인덱스 유지. 청크별 다중 벡터를 쓰려면 index projection 으로 parent-child 분리 필요

---

## 6. 토크나이저 / Analyzer 설계

### 6.1 두 가지 analyzer 운영

| 필드 카테고리 | Analyzer | 이유 |
|--------------|----------|------|
| 짧은 메타·요약 (`caseName`, `holdings`, `summary`, `reply`, …) | `ko.microsoft` (built-in) | 한국어 형태소 분석 표준, semantic ranking 호환 |
| 장문 본문 (`fullText`, `reason`) | `ko_safe` (custom) | 한자 블록 제거 + 200자 강제 분할 + `MicrosoftLanguageTokenizer(korean)` → 32 KB 단일 토큰 한도 회피 |

### 6.2 `ko_safe` Custom Analyzer 정의

```jsonc
{
  "@odata.type": "#Microsoft.Azure.Search.CustomAnalyzer",
  "name": "ko_safe",
  "tokenizer": "microsoft_korean_tok",
  "charFilters": ["strip_cjk", "split_long_runs"],
  "tokenFilters": ["lowercase"]
}
```

**charFilters**

- `strip_cjk`: `[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF\u3040-\u309F\u30A0-\u30FF]+` → ` ` (공백)
  - CJK 한자 + 일본어 가나 블록을 통째로 공백으로 변환 → MS 한국어 토크나이저가 건너뛸 수 없는 거대 단일 토큰 방지
- `split_long_runs`: `(\S{200})(?=\S)` → `$1 ` (200 글자마다 공백 삽입)
  - 한국어인데도 영숫자/특수문자가 200자 이상 끊김 없이 이어지는 케이스 분할

**tokenizer**

- `MicrosoftLanguageTokenizer(language=korean, maxTokenLength=200)` — 한국어 형태소 분석. ⚠️ `MicrosoftLanguageStemmingTokenizer` 는 한국어 미지원

### 6.3 왜 `ko.lucene` 이 아니라 custom analyzer 인가

- `ko.lucene` / `ko.microsoft` 등 **built-in analyzer 는 charFilter 추가 불가** → 위와 같은 32K byte 보호 불가능
- 따라서 long-form 필드는 custom analyzer 가 사실상 유일한 안전한 선택지

---

## 7. 운영 가이드

### 7.1 일반적인 워크플로

```bash
# 첫 색인 (캐시 OFF, 4개 병렬)
python scripts/setup_ai_search_pipeline.py --run

# 데이터 추가/갱신 후 (스케줄러가 자동 또는 수동 트리거)
python scripts/setup_ai_search_pipeline.py --source prec --run

# 스키마 변경 후 전체 재처리 + 임베딩 비용 절감
SETUP_ENABLE_CACHE=1 python scripts/setup_ai_search_pipeline.py --run
```

### 7.2 트러블슈팅 체크리스트

1. `Credentials provided in the connection string are invalid` → Search MSI 의 storage RBAC 확인 (`Storage Blob Data Reader` for datasource, **`Contributor`** for cache)
2. `Field 'X' contains a term that is too large to process` → 해당 필드의 filter/sort/facet 끄거나 custom analyzer 적용
3. `Skill input 'text' was N tokens, … maximum allowed '8000'` → SplitSkill 의 `maximumPageLength` 줄이기
4. `cache has data … unusable due to … alteration` → indexer reset 후 PUT (또는 `?ignoreResetRequirement=true`)
5. `transientFailure processed=0` → `lastResult.errorMessage` 확인 (storage cred / SPL approval / quota 순)

---

## 부록 A. 입력 데이터 (Blob)

| 소스 | files | size (MiB) | docs |
|------|------:|-----------:|-----:|
| `prec/` | 2 | 158.2 | 18,841 |
| `detc/` | 3 | 164.6 | 24,985 |
| `expc/` | 1 | 74.3 | 8,715 |
| `admrul/` | 2 | 77.7 | 6,831 |
| **합계** | **8** | **474.8** | **59,372** |

## 부록 B. 측정 환경

| 항목 | 값 |
|------|----|
| Region | Sweden Central |
| Search SKU | Standard S1 (Replica 1, Partition 1) |
| Storage SKU | Standard_LRS, hierarchical namespace OFF |
| OpenAI Region | swedencentral (`text-embedding-3-large`) |
| Network | All in VNET, AI Search ↔ Storage / Foundry via Shared Private Link |
| 스크립트 | `scripts/setup_ai_search_pipeline.py`, `scripts/reindex_with_metrics.py` |
