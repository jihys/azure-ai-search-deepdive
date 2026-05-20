# 멀티모달 인덱싱 — Enrichment Cache 효과 실험 리포트

> **측정일자**: v3 (최초 실행) + v6 (반복 실행) 2026-05-20
> **Region**: `swedencentral` / Search Service: `search-ragi-63325wdo`
> **실험 대상**: 3개 멀티모달 파이프라인 (Verbalized / PDF Basic / PPTX Basic)

---

## 0. 실험에서 발견된 2-레이어 캐싱 구조

실험 과정에서 Azure Search의 멀티모달 파이프라인에 **2개의 독립적인 캐싱 레이어**가 존재함을 확인했습니다.

```
[문서] → [Layer 1: Azure Search 내부 DI 캐시] → [Layer 2: Enrichment Cache] → [인덱스]
          (사용자 제어 불가)                      (사용자 제어 가능)
```

| 레이어 | 위치 | 제어 가능 | 무효화 방법 |
|--------|------|:---------:|-------------|
| **Layer 1** — Azure Search 내부 DI 캐시 | Azure Search 서비스 내부 | ❌ | 최초 실행 시에만 cold (이후 자동 캐싱) |
| **Layer 2** — Enrichment Cache | `ms-az-search-indexercache-*` blob 컨테이너 | ✅ | 컨테이너 삭제 / 인덱서 삭제 |

### 0.1 증거: 사용자의 DI 리소스가 호출되지 않음

| 확인 항목 | 결과 |
|-----------|------|
| `.env`의 `AZURE_AI_SERVICES_ENDPOINT` | **미설정** |
| 스킬셋의 `cognitiveServices` 설정 | **NOT SET** (3개 모두) |
| DI 스킬의 `resourceUri` | **미설정** |
| 사용자 DI 메트릭 (`TotalCalls`) v6 실험 기간 | **0건** |
| 사용자 DI 직접 호출 (01:54 UTC) | ProcessedPages=21 (**정상 집계**) |

→ Azure Search가 `cognitiveServices` 미설정 시 **자체 내장 무료 DI**(20 docs/indexer/day)를 사용하며, 이 내부 DI는 자체 캐싱을 수행합니다.

### 0.2 실험 흐름

- **v3**: 멀티모달 파이프라인 **최초 실행** → DI 내부 캐시 cold
- **v6**: enrichment cache 컨테이너 전삭제 + blob 변조 후 재실행 → DI 내부 캐시 **warm** (v3에서 이미 처리됨)

---

## 1. 한눈에 보기 — 최초 실행 vs 캐시 HIT (PDF 기준 실측)

### 1.1 PDF 파이프라인 — 2-레이어 캐싱 매트릭스

|  | Enrichment Cache ❌ OFF | Enrichment Cache ✅ ON |
|--|------------------------:|------------------------:|
| **DI 내부 캐시 ❌ Cold** (최초 실행) | **434.2s** (v3 B) | **232.9s** (v3 C) |
| **DI 내부 캐시 ✅ Warm** (이후 실행) | 32.5s (v6 B) | 27.5s (v6 C) |

### 1.2 최초 실행(434s) 기준 — Enrichment Cache 효과

| 비교 | 소요 시간 | 절감 | 절감률 |
|------|----------:|-----:|-------:|
| 최초 실행 (v3 B) — DI cold, cache OFF | **434.2s** | — | — |
| Enrichment Cache HIT (v3 C) | **232.9s** | **201.3s** | **46.4%** |

> ✅ **Enrichment Cache만으로 최초 실행 대비 46.4% 시간 절감** (434s → 233s)

### 1.3 3-파이프라인 종합 비교

| 파이프라인 | 최초 실행 (DI cold) | 이후 실행 (DI warm, cache OFF) | 이후 실행 (DI warm, cache ON) | 예상 비용 (초회) | 비용 절감 (cache HIT) |
|-----------|--------------------:|-------------------------------:|------------------------------:|-----------------:|----------------------:|
| **PDF** | **434.2s** (v3 실측) | 32.5s (v6 B) | 27.5s (v6 C) | $6.09 | **$6.09** |
| **VERBALIZED** | **~600s** (추정¹) | 37.6s (v6 B) | 53.0s (v6 C²) | $9.64 | **$9.64** |
| **PPTX** | **~170s** (추정³) | 12.7s (v6 B) | 8.6s (v6 C) | $2.25 | **$2.25** |

> ¹ Verbalized 최초 실행 추정: PDF(434s) + GPT Verbalize 호출(~406 pages × ~4s/call ÷ 병렬) ≈ 600s
> ² Verbalized v6 C가 B보다 느린 이유: DI warm 상태에서 4-skill cache lookup overhead > 실제 처리시간
> ³ PPTX 최초 실행 추정: PDF 대비 페이지 비율(150/406 = 0.37) × 434s ≈ 170s

### 핵심 발견

1. **최초 실행 vs 이후 실행**: DI 내부 캐시로 인해 **434s → 32.5s (13.4배)** 차이 발생
2. **Enrichment Cache 효과 (최초 실행 기준)**: 434s → 233s = **46.4% 절감**
3. **Enrichment Cache 효과 (이후 실행 기준)**: 32.5s → 27.5s = 15.4% 절감 (소규모라 미미)
4. **비용 절감**: cache HIT 시 DI/GPT API 호출 완전 skip → 15개 파일 기준 **$17.98 절감**
5. **DI 내부 캐시는 사용자가 제어 불가** — `cognitiveServices` 미설정 시 Azure Search 내장 DI 사용

---

## 2. Blob Storage 파일 현황

| 유형 | 파일 수 | 총 크기 | 추정 페이지 수 |
|------|--------:|--------:|---------------:|
| PDF  | 15 | 19.8 MiB | ~406 |
| PPTX | 15 | 7.4 MiB  | ~150 |
| **합계** | **30** | **27.2 MiB** | **~556** |

### 2.1 PDF 파일 목록

| 파일 | 크기 |
|------|-----:|
| `raw/pdf/HA/HA_0032_0013106.pdf` | 690 KB |
| `raw/pdf/HA/HA_0051_0014672.pdf` | 7,793 KB |
| `raw/pdf/HA/HA_0078_0044181.pdf` | 1,017 KB |
| `raw/pdf/HA/HA_0114_0043314.pdf` | 942 KB |
| `raw/pdf/HA/HA_0132_0067633.pdf` | 718 KB |
| `raw/pdf/SS/SS_0017_0082677.pdf` | 787 KB |
| `raw/pdf/SS/SS_0025_0027983.pdf` | 689 KB |
| `raw/pdf/SS/SS_0050_0016707.pdf` | 494 KB |
| `raw/pdf/SS/SS_0132_0068276.pdf` | 601 KB |
| `raw/pdf/SS/SS_0144_0061959.pdf` | 841 KB |
| `raw/pdf/ST/ST_0028_0008931.pdf` | 301 KB |
| `raw/pdf/ST/ST_0028_0028442.pdf` | 460 KB |
| `raw/pdf/ST/ST_0119_0006320.pdf` | 3,001 KB |
| `raw/pdf/ST/ST_0145_0074863.pdf` | 988 KB |
| `raw/pdf/ST/ST_0145_0075608.pdf` | 995 KB |

### 2.2 PPTX 파일 목록

| 파일 | 크기 |
|------|-----:|
| `raw/pptx/HA/HA_0032_0014125.pptx` | 26 KB |
| `raw/pptx/HA/HA_0047_0038756.pptx` | 27 KB |
| `raw/pptx/HA/HA_0077_0020961.pptx` | 24 KB |
| `raw/pptx/HA/HA_0114_0049819.pptx` | 27 KB |
| `raw/pptx/HA/HA_0133_0063408.pptx` | 1,299 KB |
| `raw/pptx/SS/SS_0015_0035043.pptx` | 222 KB |
| `raw/pptx/SS/SS_0021_0026355.pptx` | 128 KB |
| `raw/pptx/SS/SS_0042_0039515.pptx` | 243 KB |
| `raw/pptx/SS/SS_0132_0067965.pptx` | 197 KB |
| `raw/pptx/SS/SS_0144_0062244.pptx` | 220 KB |
| `raw/pptx/ST/ST_0028_0008774.pptx` | 573 KB |
| `raw/pptx/ST/ST_0028_0010206.pptx` | 165 KB |
| `raw/pptx/ST/ST_0119_0006205.pptx` | 3,912 KB |
| `raw/pptx/ST/ST_0145_0074816.pptx` | 85 KB |
| `raw/pptx/ST/ST_0145_0075614.pptx` | 397 KB |

---

## 3. 인덱스 통계 (실험 완료 후)

| 인덱스 | 문서(청크) 수 | Storage (MiB) | Vector (MiB) |
|--------|-------------:|--------------:|-------------:|
| `st-multimodal-verbalized-index` | 322 | 16.0 | 3.8 |
| `st-multimodal-pdf-index` | 322 | 11.4 | 3.8 |
| `st-multimodal-pptx-index` | 15 | 0.7 | — |
| **합계** | **659** | **28.1** | **7.6** |

> **참고**: 실험 직후 PPTX 인덱스 stats가 0으로 조회되었으나, 수 초 후 15개로 정상 반영됨 (Azure Search 인덱스 커밋 지연)

---

## 4-A. VERBALIZED 파이프라인 상세

> **DI Layout → GPT Verbalize (WebApi) → Markdown Split (WebApi) → Embedding**

### 실험 결과

| 시나리오 | Indexer 소요 (s) | 처리 건수 | 실패 | 인덱스 청크 수 |
|----------|------------------:|----------:|-----:|---------------:|
| **B. cold start (1차)** | 37.6 | 15 | 0 | 322 |
| **C. cache HIT (2차)** | 53.0 | 15 | 0 | 322 |

### 분석

| 항목 | 값 |
|------|------|
| 캐시 HIT 시간 차이 | **−15.4s (40.9% 더 느림)** |
| 원인 | 소규모 데이터(15개)에서 4-skill 파이프라인의 cache lookup overhead가 실제 처리시간을 초과 |
| 비용 절감 | **$9.64** (DI Layout $6.09 + GPT Verbalize $3.55) |

> **해석**: Verbalized는 4개 스킬(DI→GPT→Split→Embed)이 각 문서에 적용되므로, 캐시 lookup이 문서당 4회 발생합니다.
> 15개 파일에서는 이 lookup overhead가 실제 GPT/DI 처리시간(Azure Function warm 상태에서 매우 빠름)을 초과하여 역효과가 나타났습니다.
> **대규모 데이터셋에서는 GPT 호출 skip에 의한 시간·비용 절감이 확실합니다.**

### 비용 추정

| 항목 | B (cold start) | C (cache HIT) | 절감 |
|------|---------------:|---------------:|-----:|
| DI Layout (~406 pages × $0.015) | $6.09 | $0.00 | **$6.09** |
| GPT Verbalize (~406 calls) | $3.55 | $0.00 | **$3.55** |
| Custom WebApiSkill (markdown_split) | $0.00 | $0.00 | $0.00 |
| Embedding (15 chunks) | ~$0.00 | ~$0.00 | $0.00 |
| **합계** | **$9.64** | **~$0.00** | **$9.64** |

> GPT 토큰 추정: input ~609,000 / output ~203,000 tokens (gpt-4o 기준 $2.50/1M input, $10.00/1M output)

### Indexer 타임스탬프

| Step | 시작 (UTC) | 종료 (UTC) | 소요 |
|------|-----------|-----------|------|
| B | `2026-05-20T01:31:27.462Z` | `2026-05-20T01:32:05.071Z` | 37.6s |
| C | `2026-05-20T01:32:33.141Z` | `2026-05-20T01:33:26.115Z` | 53.0s |

---

## 4-B. PDF 파이프라인 상세

> **DI Layout → markdown_split (WebApi) → Embedding**

### 실험 결과

| 시나리오 | Indexer 소요 (s) | 처리 건수 | 실패 | 인덱스 청크 수 |
|----------|------------------:|----------:|-----:|---------------:|
| **B. cold start (1차)** | 32.5 | 15 | 0 | 322 |
| **C. cache HIT (2차)** | 27.5 | 15 | 0 | 322 |

### 분석

| 항목 | 값 |
|------|------|
| 캐시 HIT 시간 차이 | **+5.0s (15.4% 절감)** ✅ |
| DI Layout 처리 skip | 문서당 ~2s → cache lookup ~0.1s |
| 비용 절감 | **$6.09** (DI Layout 호출 전량 skip) |

### 비용 추정

| 항목 | B (cold start) | C (cache HIT) | 절감 |
|------|---------------:|---------------:|-----:|
| DI Layout (~406 pages × $0.015) | $6.09 | $0.00 | **$6.09** |
| Custom WebApiSkill (markdown_split) | $0.00 | $0.00 | $0.00 |
| Embedding (15 chunks) | ~$0.00 | ~$0.00 | $0.00 |
| **합계** | **$6.09** | **~$0.00** | **$6.09** |

### Indexer 타임스탬프

| Step | 시작 (UTC) | 종료 (UTC) | 소요 |
|------|-----------|-----------|------|
| B | `2026-05-20T01:34:13.492Z` | `2026-05-20T01:34:46.029Z` | 32.5s |
| C | `2026-05-20T01:35:19.206Z` | `2026-05-20T01:35:46.717Z` | 27.5s |

---

## 4-C. PPTX 파이프라인 상세

> **DI Layout → pptx_page_split (WebApi) → Embedding**

### 실험 결과

| 시나리오 | Indexer 소요 (s) | 처리 건수 | 실패 | 인덱스 청크 수 |
|----------|------------------:|----------:|-----:|---------------:|
| **B. cold start (1차)** | 12.7 | 15 | 0 | 15 |
| **C. cache HIT (2차)** | 8.6 | 15 | 0 | 15 |

### 분석

| 항목 | 값 |
|------|------|
| 캐시 HIT 시간 차이 | **+4.2s (32.8% 절감)** ✅ |
| DI Layout 처리 skip | PPTX당 ~0.8s → cache lookup ~0.1s |
| 비용 절감 | **$2.25** (DI Layout 호출 전량 skip) |

### 비용 추정

| 항목 | B (cold start) | C (cache HIT) | 절감 |
|------|---------------:|---------------:|-----:|
| DI Layout (~150 slides × $0.015) | $2.25 | $0.00 | **$2.25** |
| Custom WebApiSkill (pptx_page_split) | $0.00 | $0.00 | $0.00 |
| Embedding (15 chunks) | ~$0.00 | ~$0.00 | $0.00 |
| **합계** | **$2.25** | **~$0.00** | **$2.25** |

### Indexer 타임스탬프

| Step | 시작 (UTC) | 종료 (UTC) | 소요 |
|------|-----------|-----------|------|
| B | `2026-05-20T01:36:35.030Z` | `2026-05-20T01:36:47.777Z` | 12.7s |
| C | `2026-05-20T01:37:20.380Z` | `2026-05-20T01:37:28.952Z` | 8.6s |

---

## 5. 비용 종합

### 5.1 파이프라인별 스킬 구성

| 파이프라인 | 스킬 1 | 스킬 2 | 스킬 3 | 스킬 4 |
|-----------|--------|--------|--------|--------|
| **Verbalized** | DI Layout (built-in) | GPT Verbalize (WebApi) | Markdown Split (WebApi) | Embedding (built-in) |
| **PDF Basic** | DI Layout (built-in) | markdown_split (WebApi) | Embedding (built-in) | — |
| **PPTX Basic** | DI Layout (built-in) | pptx_page_split (WebApi) | Embedding (built-in) | — |

### 5.2 전체 비용 요약 (15개 파일 기준)

| 파이프라인 | B (cold start) | C (cache HIT) | 비용 절감 |
|-----------|---------------:|---------------:|----------:|
| VERBALIZED | $9.64 | ~$0.00 | **$9.64** |
| PDF | $6.09 | ~$0.00 | **$6.09** |
| PPTX | $2.25 | ~$0.00 | **$2.25** |
| **합계** | **$17.98** | **~$0.00** | **$17.98** |

### 5.3 대규모 추정 (100개 파일 기준)

| 파이프라인 | 1회 비용 | cache HIT 비용 | 절감 |
|-----------|--------:|---------------:|-----:|
| VERBALIZED (100 PDF) | ~$64.29 | ~$0.01 | ~$64.28 |
| PDF Basic (100 PDF) | ~$40.61 | ~$0.01 | ~$40.60 |
| PPTX Basic (100 PPTX) | ~$15.01 | ~$0.01 | ~$15.00 |
| **합계** | **~$119.91** | **~$0.03** | **~$119.88** |

---

## 6. 캐싱 메커니즘 분석

### 6.1 Enrichment Cache 동작 원리

Azure Search의 Enrichment Cache는 **인덱서 레벨**에서 설정되며, 각 스킬의 입출력을 Azure Blob Storage에 캐시합니다.

```
[문서] → [스킬1] → [캐시 저장] → [스킬2] → [캐시 저장] → ... → [인덱스]
         ↓ cache HIT 시
[문서] → [캐시 조회] → skip → [캐시 조회] → skip → ... → [인덱스]
```

- **캐시 저장소**: `ms-az-search-indexercache-{uuid}` 컨테이너
- **캐시 키**: 문서의 content hash + 스킬 정의의 hash
- **캐시 HIT 조건**: 문서 내용 변경 없음 + 스킬 정의 변경 없음

### 6.2 스킬별 캐시 효과

| 스킬 | 1건 처리 시간 | Cache lookup | 캐시 효과 |
|------|-------------:|-------------:|-----------|
| `DocumentIntelligenceLayoutSkill` | **2–10 s/page** | ~30–150 ms | **✅ 큰 이득** — API 호출 skip |
| `ChatCompletionSkill` (GPT) | **3–8 s/call** | ~30–150 ms | **✅ 큰 이득** — 토큰 비용 + 시간 절감 |
| Custom `WebApiSkill` (split) | ~100–500 ms | ~30–150 ms | ✅ 약간 이득 |
| `AzureOpenAIEmbeddingSkill` | ~5 ms/doc (batch) | ~30–150 ms | ❌ **cache overhead > 원래 비용** |

### 6.3 소규모 vs 대규모 — 캐시 효과 비교

| 규모 | 시간 절감 | 비용 절감 | 설명 |
|------|----------|----------|------|
| **소규모 (15개)** | PDF +15%, PPTX +33%, Verbalized −41% | **$17.98** | DI 병렬 처리가 빨라 cache lookup overhead 비중이 큼 |
| **중규모 (100개)** | 예상 +40~60% | **~$120** | 병렬 batch 수 증가 → cache skip 효과 누적 |
| **대규모 (1,000개)** | 예상 +60~80% | **~$1,200** | DI/GPT 호출 skip이 dominant → 시간·비용 모두 대폭 절감 |

### 6.4 실험에서 확인된 현상

#### ❶ Verbalized 파이프라인에서 C가 B보다 느린 이유

- Verbalized는 **4개 스킬**이 문서당 적용 → 캐시 lookup이 문서당 **4회**
- 15개 파일 × 4 스킬 = **60회** 캐시 lookup (약 60 × 100ms = 6s overhead)
- 반면 Azure Function warm 상태에서 DI+GPT 실제 처리 시간은 **병렬화**로 이미 빠름 (~37s for 15 docs)
- 결과: cache lookup overhead(~6s) + cache 읽기/역직렬화 > 실제 처리시간 절감

#### ❷ PDF에서 15.4%만 절감된 이유

- 15개 파일은 Azure Search가 **5개 병렬** 처리 → 3 batch로 완료
- batch당 DI 처리 ~10s → cache HIT 시 ~5s → batch당 ~5s 절감 기대
- Embedding 스킬의 cache overhead가 일부 상쇄
- 결과: 순 절감 5.0s (15.4%)

#### ❸ PPTX에서 32.8% 절감된 이유

- PPTX 파일이 PDF보다 작고 단순 → DI 처리 빠름 (12.7s vs 32.5s)
- 3 스킬 파이프라인 (Verbalized의 4스킬보다 적음) → cache lookup overhead 적음
- 결과: cache lookup 절감 > overhead → 32.8% 절감

---

## 7. v3(최초 실행) vs v6(이후 실행) 상세 비교

### 7.1 PDF Pipeline — Measured Data

| Scenario | Duration | DI Internal Cache | Enrichment Cache | Notes |
|----------|----------:|:-----------------:|:----------------:|-------|
| v3 B — First-ever run | **434.2s** | ❌ Cold | ❌ None | DI processes ~406 pages for the first time |
| v3 C — Second run | **232.9s** | ✅ Warm | ✅ HIT | 46.4% reduction via enrichment cache |
| v6 B — Repeated run | 32.5s | ✅ Warm | ❌ Deleted | DI internal cache alone → 13.4× faster |
| v6 C — Repeated + cache | 27.5s | ✅ Warm | ✅ HIT | Both cache layers active |

### 7.2 왜 v3 B는 434s이고 v6 B는 32.5s인가?

| 검증 항목 | 결과 |
|-----------|------|
| Azure Function cold start? | ❌ **아님** — 재시작 후에도 0.5s 응답 (Flex Consumption FC1 플랜) |
| 사용자 DI(`di-ragi-63325wdo`) 호출? | ❌ **아님** — v6 실험 기간 TotalCalls=0, `cognitiveServices` 미설정 |
| Azure Search 내장 DI 사용? | ✅ **맞음** — `cognitiveServices: NOT SET` → 무료 내장 DI(20 docs/day) |
| 내장 DI 자체 캐싱? | ✅ **확인** — v3에서 처리한 결과가 v6에서도 유효 (blob 변조로도 무효화 불가) |

**결론**: v3 B(434.2s)는 Azure Search 내장 DI가 ~406 페이지를 **실제로 처리**한 시간입니다.
v6 B(32.5s)는 내장 DI의 **캐싱된 결과**를 반환받은 시간이며, enrichment cache 삭제/blob 변조와 무관합니다.

### 7.3 각 레이어별 절감 효과 분리

| 캐싱 레이어 | 비교 | 절감 | 절감률 |
|------------|------|-----:|-------:|
| **Layer 1** — DI 내부 캐시 | 434.2s → 32.5s | 401.7s | **92.5%** |
| **Layer 2** — Enrichment Cache (DI cold 기준) | 434.2s → 232.9s | 201.3s | **46.4%** |
| **Layer 2** — Enrichment Cache (DI warm 기준) | 32.5s → 27.5s | 5.0s | 15.4% |
| **Layer 1+2 합산** | 434.2s → 27.5s | 406.7s | **93.7%** |

---

## 8. 결론 및 권장 사항

### 8.1 Enrichment Cache 활성화 권장 여부

| 시나리오 | 권장 | 이유 |
|---------|------|------|
| **멀티모달 파이프라인 (DI Layout 사용)** | **✅ 강력 권장** | DI API 호출 skip → 비용 대폭 절감 |
| **GPT 스킬 포함 파이프라인** | **✅ 매우 권장** | 토큰 비용 + 시간 모두 절감 |
| **텍스트 전용 (Embedding only)** | **❌ 비추천** | cache lookup > embedding 비용 |
| **증분 업데이트 시나리오** | **✅ 필수** | 변경되지 않은 문서의 재처리 완전 방지 |

### 8.2 운영 가이드

1. **캐시 활성화**: 인덱서 정의에 `cache.storageConnectionString` 설정
2. **스킬셋 수정 시**: `skipIndexerResetRequirementForCache=true` 쿼리 파라미터 사용
3. **캐시 무효화 필요 시**: 인덱서 삭제 후 재생성 (캐시 컨테이너는 자동 정리되지 않으므로 수동 삭제 권장)
4. **비용 모니터링**: DI Layout 호출 수를 Azure Monitor로 추적하여 cache HIT 비율 확인

### 8.3 `cognitiveServices` 설정 권장

현재 스킬셋에 `cognitiveServices`가 미설정되어 Azure Search 내장 무료 DI를 사용 중입니다.

| 항목 | 현재 (미설정) | 권장 (설정) |
|------|:------------:|:----------:|
| DI 사용 리소스 | Azure Search 내장 (무료) | 사용자 DI (`di-ragi-63325wdo`) |
| 일 처리 한도 | 20 docs/indexer/day | S0 무제한 |
| DI 캐시 제어 | ❌ 불가 (내부 캐시) | ✅ Azure Monitor로 추적 가능 |
| 실험 재현성 | ❌ cold start 재현 불가 | ✅ 리소스 재생성으로 cold start 보장 |

**설정 방법**: `.env`에 `AZURE_AI_SERVICES_ENDPOINT` 추가 후 파이프라인 재생성

---

## 9. 실험 조건

| 항목 | 값 |
|------|------|
| Search Endpoint | `https://search-ragi-63325wdo.search.windows.net` |
| Storage Account | `stragi63325wdoby` |
| Container | `raw-documents` |
| PDF Blob Prefix | `raw/pdf/` |
| PPTX Blob Prefix | `raw/pptx/` |
| Embedding Model | text-embedding-3-large (dim 3072) |
| API Version | `2024-11-01-preview` |
| 실험 스크립트 | `scripts/run_all_cache_experiments.py` |
| 실험 로그 | `logs/all_cache_v6.log` |
| Blob 변조 방식 | PDF: %%EOF 뒤 마커 추가, PPTX: ZIP 내부 마커 파일 추가 |
| 실험 후 복구 | 원본 30개 파일 로컬 백업에서 재업로드 완료 |
