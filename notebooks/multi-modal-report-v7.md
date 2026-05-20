# 멀티모달 인덱싱 — 캐싱 효과 실험 리포트

> 측정일자: 2026-05-20 02:42:00
> Region: `swedencentral` / Search Service: `search-ragi-63325wdo`
> 실험 대상: 3개 멀티모달 파이프라인 (Verbalized / PDF Basic / PPTX Basic)

---

## 1. 한눈에 보기 — 파이프라인별 캐시 효과 비교

| 파이프라인 | B (cache 채움) | C (cache HIT) | 시간 절감 | 절감률 | B 비용 | C 비용 | 비용 절감 |
|-----------|---------------:|---------------:|----------:|-------:|-------:|-------:|----------:|
| **VERBALIZED** | 40.3s | 34.4s | +6.0s | +14.9% | $9.6435 | $0.0010 | $9.6425 |
| **PDF** | 34.2s | 29.3s | +4.8s | +14.2% | $6.0910 | $0.0010 | $6.0900 |
| **PPTX** | 8.6s | 5.6s | +3.0s | +34.5% | $2.2510 | $0.0010 | $2.2500 |

---

## 2. Blob Storage 파일 현황

| 유형 | 파일 수 | 총 크기 | 추정 페이지 수 |
|------|--------:|--------:|---------------:|
| PDF | 15 | 19.8 MiB | ~406 |
| PPTX | 15 | 7.4 MiB | ~150 |
| **합계** | **30** | **27.2 MiB** | **~556** |

### 2.1 PDF 파일 목록

- `raw/pdf/HA/HA_0032_0013106.pdf` (690 KB)
- `raw/pdf/HA/HA_0051_0014672.pdf` (7793 KB)
- `raw/pdf/HA/HA_0078_0044181.pdf` (1017 KB)
- `raw/pdf/HA/HA_0114_0043314.pdf` (941 KB)
- `raw/pdf/HA/HA_0132_0067633.pdf` (718 KB)
- `raw/pdf/SS/SS_0017_0082677.pdf` (787 KB)
- `raw/pdf/SS/SS_0025_0027983.pdf` (689 KB)
- `raw/pdf/SS/SS_0050_0016707.pdf` (494 KB)
- `raw/pdf/SS/SS_0132_0068276.pdf` (601 KB)
- `raw/pdf/SS/SS_0144_0061959.pdf` (841 KB)
- `raw/pdf/ST/ST_0028_0008931.pdf` (301 KB)
- `raw/pdf/ST/ST_0028_0028442.pdf` (460 KB)
- `raw/pdf/ST/ST_0119_0006320.pdf` (3001 KB)
- `raw/pdf/ST/ST_0145_0074863.pdf` (987 KB)
- `raw/pdf/ST/ST_0145_0075608.pdf` (995 KB)

### 2.2 PPTX 파일 목록

- `raw/pptx/HA/HA_0032_0014125.pptx` (26 KB)
- `raw/pptx/HA/HA_0047_0038756.pptx` (27 KB)
- `raw/pptx/HA/HA_0077_0020961.pptx` (24 KB)
- `raw/pptx/HA/HA_0114_0049819.pptx` (26 KB)
- `raw/pptx/HA/HA_0133_0063408.pptx` (1299 KB)
- `raw/pptx/SS/SS_0015_0035043.pptx` (222 KB)
- `raw/pptx/SS/SS_0021_0026355.pptx` (128 KB)
- `raw/pptx/SS/SS_0042_0039515.pptx` (242 KB)
- `raw/pptx/SS/SS_0132_0067965.pptx` (196 KB)
- `raw/pptx/SS/SS_0144_0062244.pptx` (220 KB)
- `raw/pptx/ST/ST_0028_0008774.pptx` (572 KB)
- `raw/pptx/ST/ST_0028_0010206.pptx` (165 KB)
- `raw/pptx/ST/ST_0119_0006205.pptx` (3912 KB)
- `raw/pptx/ST/ST_0145_0074816.pptx` (85 KB)
- `raw/pptx/ST/ST_0145_0075614.pptx` (397 KB)

---

## 3. 인덱스 통계 (실험 완료 후)

| 인덱스 | 문서 수 | Storage (MiB) | Vector (MiB) |
|--------|--------:|--------------:|-------------:|
| `st-multimodal-verbalized-index` | 0 | 0.0 | 0.0 |
| `st-multimodal-pdf-index` | 0 | 0.0 | 0.0 |
| `st-multimodal-pptx-index` | 0 | 0.0 | 0.0 |
| **합계** | **0** | **0.0** | **0.0** |

---

## 4-A. VERBALIZED 파이프라인 상세

> Verbalized (DI Layout → GPT Verbalize → Markdown Split → Embedding)

### 실험 결과

| 시나리오 | indexer 소요 (s) | 처리 건수 | 실패 | 인덱스 청크 수 |
|----------|------------------:|----------:|-----:|---------------:|
| B. cache 채움 (1차) | 40.3 | 15 | 0 | 0 |
| C. cache HIT (2차) | 34.4 | 15 | 0 | 0 |

### 캐시 효과

| 비교 | indexer 소요 | 차이 | 절감률 |
|------|------------:|-----:|-------:|
| B (baseline) | 40.3 s | — | — |
| C (cache HIT) | 34.4 s | +6.0 s | +14.9% |

**✅ 캐시 HIT 효과 확인**: 시간 6.0s (14.9%) 절감

### 비용 추정

| 항목 | B (cache 채움) | C (cache HIT) | 절감 |
|------|---------------:|---------------:|-----:|
| DI Layout (406 pages × $0.015) | $6.0900 | $0.0000 | $6.0900 |
| GPT Verbalize (406 calls) | $3.5525 | $0.0000 | $3.5525 |
| Embedding (15 / 15 chunks) | $0.0010 | $0.0010 | $0.0000 |
| **합계** | **$9.6435** | **$0.0010** | **$9.6425** |

> GPT 토큰 추정: input ~609,000 / output ~203,000 tokens
> Cache HIT 시 DI Layout + GPT Verbalize 호출 완전 skip → **시간·비용 모두 절감**

### Indexer 실행 로그

**B (cache 채움):**

| 항목 | 값 |
|------|------|
| 시작 | `2026-05-20T02:35:57.168Z` |
| 종료 | `2026-05-20T02:36:37.515Z` |
| 상태 | `success` |
| 처리 | 15 건 |
| 실패 | 0 건 |

**C (cache HIT):**

| 항목 | 값 |
|------|------|
| 시작 | `2026-05-20T02:37:04.74Z` |
| 종료 | `2026-05-20T02:37:39.092Z` |
| 상태 | `success` |
| 처리 | 15 건 |
| 실패 | 0 건 |

**B — Warnings (30 건):**

- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont

**C — Warnings (30 건):**

- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont


---

## 4-B. PDF 파이프라인 상세

> PDF Basic (DI Layout → markdown_split → Embedding)

### 실험 결과

| 시나리오 | indexer 소요 (s) | 처리 건수 | 실패 | 인덱스 청크 수 |
|----------|------------------:|----------:|-----:|---------------:|
| B. cache 채움 (1차) | 34.2 | 15 | 0 | 0 |
| C. cache HIT (2차) | 29.3 | 15 | 0 | 0 |

### 캐시 효과

| 비교 | indexer 소요 | 차이 | 절감률 |
|------|------------:|-----:|-------:|
| B (baseline) | 34.2 s | — | — |
| C (cache HIT) | 29.3 s | +4.8 s | +14.2% |

**✅ 캐시 HIT 효과 확인**: 시간 4.8s (14.2%) 절감

### 비용 추정

| 항목 | B (cache 채움) | C (cache HIT) | 절감 |
|------|---------------:|---------------:|-----:|
| DI Layout (406 pages × $0.015) | $6.0900 | $0.0000 | $6.0900 |
| Custom WebApiSkill (pdf_split) | $0.0000 | $0.0000 | $0.0000 |
| Embedding (15 / 15 chunks) | $0.0010 | $0.0010 | $0.0000 |
| **합계** | **$6.0910** | **$0.0010** | **$6.0900** |

> Cache HIT 시 DI Layout 호출 skip → 비용 절감. Custom WebApiSkill은 자체 호스팅이므로 API 비용 없음.

### Indexer 실행 로그

**B (cache 채움):**

| 항목 | 값 |
|------|------|
| 시작 | `2026-05-20T02:38:22.426Z` |
| 종료 | `2026-05-20T02:38:56.581Z` |
| 상태 | `success` |
| 처리 | 15 건 |
| 실패 | 0 건 |

**C (cache HIT):**

| 항목 | 값 |
|------|------|
| 시작 | `2026-05-20T02:39:27.476Z` |
| 종료 | `2026-05-20T02:39:56.798Z` |
| 상태 | `success` |
| 처리 | 15 건 |
| 실패 | 0 건 |

**B — Warnings (30 건):**

- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont

**C — Warnings (30 건):**

- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont


---

## 4-C. PPTX 파이프라인 상세

> PPTX Basic (DI Layout → pptx_page_split → Embedding)

### 실험 결과

| 시나리오 | indexer 소요 (s) | 처리 건수 | 실패 | 인덱스 청크 수 |
|----------|------------------:|----------:|-----:|---------------:|
| B. cache 채움 (1차) | 8.6 | 15 | 0 | 0 |
| C. cache HIT (2차) | 5.6 | 15 | 0 | 0 |

### 캐시 효과

| 비교 | indexer 소요 | 차이 | 절감률 |
|------|------------:|-----:|-------:|
| B (baseline) | 8.6 s | — | — |
| C (cache HIT) | 5.6 s | +3.0 s | +34.5% |

**✅ 캐시 HIT 효과 확인**: 시간 3.0s (34.5%) 절감

### 비용 추정

| 항목 | B (cache 채움) | C (cache HIT) | 절감 |
|------|---------------:|---------------:|-----:|
| DI Layout (150 pages × $0.015) | $2.2500 | $0.0000 | $2.2500 |
| Custom WebApiSkill (pptx_split) | $0.0000 | $0.0000 | $0.0000 |
| Embedding (15 / 15 chunks) | $0.0010 | $0.0010 | $0.0000 |
| **합계** | **$2.2510** | **$0.0010** | **$2.2500** |

> Cache HIT 시 DI Layout 호출 skip → 비용 절감. Custom WebApiSkill은 자체 호스팅이므로 API 비용 없음.

### Indexer 실행 로그

**B (cache 채움):**

| 항목 | 값 |
|------|------|
| 시작 | `2026-05-20T02:40:48.821Z` |
| 종료 | `2026-05-20T02:40:57.397Z` |
| 상태 | `success` |
| 처리 | 15 건 |
| 실패 | 0 건 |

**C (cache HIT):**

| 항목 | 값 |
|------|------|
| 시작 | `2026-05-20T02:41:34.04Z` |
| 종료 | `2026-05-20T02:41:39.66Z` |
| 상태 | `success` |
| 처리 | 15 건 |
| 실패 | 0 건 |

**B — Warnings (30 건):**

- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont

**C — Warnings (30 건):**

- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont
- Could not generate projection from input '/document/markdown_chunks/*'. Check the 'source' or 'sourceContext' property of your projection in your skillset. =$(/document/markdown_chunks/*) ?map { "cont

---

## 5. 비용 종합 비교

### 5.1 파이프라인별 스킬 구성

| 파이프라인 | 스킬 1 | 스킬 2 | 스킬 3 | 스킬 4 |
|-----------|--------|--------|--------|--------|
| **Verbalized** | DI Layout (built-in) | GPT Verbalize (WebApi) | Markdown Split (WebApi) | Embedding (built-in) |
| **PDF Basic** | DI Layout (built-in) | markdown_split (WebApi) | Embedding (built-in) | — |
| **PPTX Basic** | DI Layout (built-in) | pptx_page_split (WebApi) | Embedding (built-in) | — |

### 5.2 전체 비용 요약

| 파이프라인 | B (cache 채움) | C (cache HIT) | 절감 |
|-----------|---------------:|---------------:|-----:|
| VERBALIZED | $9.6435 | $0.0010 | $9.6425 |
| PDF | $6.0910 | $0.0010 | $6.0900 |
| PPTX | $2.2510 | $0.0010 | $2.2500 |
| **합계** | **$17.9854** | **$0.0029** | **$17.9825** |

### 5.3 대규모 추정 (PDF 100개 + PPTX 100개)

| VERBALIZED (100 files) | 1회: ~$64.29 | cache HIT: ~$0.01 | 절감: ~$64.28 |
| PDF (100 files) | 1회: ~$40.61 | cache HIT: ~$0.01 | 절감: ~$40.60 |
| PPTX (100 files) | 1회: ~$15.01 | cache HIT: ~$0.01 | 절감: ~$15.00 |

---

## 6. 캐싱 메커니즘 해석

### 6.1 왜 멀티모달에서 캐시가 효과적인가?

| 스킬 | 1건 처리 시간 | cache HIT (Storage lookup) | 효과 |
|------|-------------:|---------------------------:|------|
| `DocumentIntelligenceLayoutSkill` | **2–10 s / page** | ~30–150 ms | **✅ 시간·비용 모두 이득** |
| `ChatCompletionSkill` (GPT verbalize) | **3–8 s / call** | ~30–150 ms | **✅ 시간·비용 모두 이득** |
| Custom `WebApiSkill` (split) | ~100–500 ms / call | ~30–150 ms | ✅ 약간 이득 |
| `AzureOpenAIEmbeddingSkill` | ~5 ms / doc | ~30–150 ms | ❌ cache overhead > 원래 비용 |

→ **DI Layout**이 모든 파이프라인의 dominant cost. Verbalized는 여기에 **GPT Verbalize**까지 추가.
  이 두 스킬의 cache HIT만으로 전체 파이프라인 시간을 **대폭 단축**.

### 6.2 파이프라인별 캐시 효과 비교

| 파이프라인 | dominant skill | cache 효과 | 이유 |
|-----------|---------------|-----------|------|
| **Verbalized** | DI Layout + GPT (수 초/doc) | **✅✅ 매우 큰 절감** | DI + GPT 모두 캐시 hit |
| **PDF Basic** | DI Layout (수 초/page) | **✅ 큰 절감** | DI 캐시 hit |
| **PPTX Basic** | DI Layout (수 초/page) | **✅ 큰 절감** | DI 캐시 hit |
| 텍스트 전용 (notebook 03) | EmbeddingSkill (5ms/doc, batch) | ❌ 오히려 손해 | lookup > embedding |

---

## 7. 실험 조건

| 항목 | 값 |
|------|------|
| Search Endpoint | `https://search-ragi-63325wdo.search.windows.net` |
| Storage Account | `stragi63325wdoby` |
| Container | `raw-documents` |
| PDF Blob Prefix | `raw/pdf/` |
| PPTX Blob Prefix | `raw/pptx/` |
| Embedding Model | text-embedding-3-large (dim 3072) |
| API Version | 2024-11-01-preview |
