# Indexer Caching 효과 비교 리포트 (Reindex vs Incremental Update)

> 측정일자: 2026-05-19 / Search: `https://search-ragi-63325wdo.search.windows.net`
> 실험 소스: `detc` (헌법재판소 결정례) / indexer: `const-blob-indexer`
> Storage: `stragi63325wdoby` / 총 소요: 3116s (51분 55초)

---

## 1. 한눈에 보기

| 항목 | 값 |
|------|---:|
| A. 파이프라인 초기화 (캐시 OFF) | 12.5s |
| B. 캐시 ON Reindex 1차 (baseline) | 1534.8s (25분 34초) |
| B.5 크롤링 신규 추가 | +0건 |
| C. Incremental Update | 17.6s |
| D. 캐시 ON Reindex 2차 (재사용) | 1529.3s (25분 29초) |
| **C / B 가속비** | **x87.2** |
| **B→D 캐시 재사용 절감** | **+5.5s (+0.4%)** |

---

## 1. 데이터 현황 (Before → After)

| 인덱스 | 한국어명 | Blob JSON (before→after) | JSONL (before→after) | 인덱스 문서 (before→after) |
|--------|----------|--------------------------|----------------------|---------------------------|
| prec-court-index | 판례 | N/A | N/A | 95,802→95,802 |
| const-court-index | 헌법재판소 결정례 | N/A | N/A | 0→38,086 (+38086) |
| legis-interp-index | 법제처 해석례 | N/A | N/A | 8,715→8,715 |
| admin-appeal-index | 행정심판 재결례 | N/A | N/A | 29,107→29,107 |
| **합계** | | **0→0** | **0→0** | **133,624→171,710** |

### 인덱스별 스토리지

| Index | docs | storage (MiB) | vector (MiB) | storage/doc (KB) | Blob 입력 (MiB) |
|-------|-----:|--------------:|-------------:|-----------------:|----------------:|
| `prec-court-index` | 95,802 | 2313.1 | 465.1 | 24.7 | 0.0 |
| `const-court-index` ⬅️ | 36,793 | 461.0 | 62.0 | 12.8 | 0.0 |
| `legis-interp-index` | 8,715 | 427.0 | 102.5 | 50.2 | 0.0 |
| `admin-appeal-index` | 29,107 | 1432.5 | 340.4 | 50.4 | 0.0 |
| **합계** | **170,417** | **4633.6** | **970.0** | — | **0.0** |

### AI Search 서비스 전체 사용량

| 항목 | 사용량 | Quota | 사용률 |
|------|------:|------:|------:|
| Storage | 4669.5 MiB | 163840 MiB | 2.85% |
| Vector | 977.8 MiB | 35840 MiB | 2.73% |
| Documents | 171,076 | — | — |
| Indexes | 7 | 50 | 14% |

---

## 2. 캐싱 시나리오 결과

| 시나리오 | 종류 | 소요(초) | 소요(분:초) | 비고 |
|----------|------|---------|------------|------|
| A. 파이프라인 초기화 (캐시 OFF, 생성만) | Reindex | 12.5 | 0:12 | rc=0 |
| B. 캐시 ON 전체 재인덱싱 (1차, 캐시 채움) | Reindex | 1534.8 | 25:34 | rc=0 |
| B.5. 크롤링 신규 데이터 추가 (0건) | Crawl | 4.2 | 0:04 | status=error, 추가=0건 |
| C. Incremental Update (신규 0건) | Update | 17.6 | 0:17 | status=success, items=0, failed=0 |
| D. 캐시 ON 전체 재인덱싱 (2차, 캐시 재사용) | Reindex | 1529.3 | 25:29 | rc=0 |

## 3. 비교 분석

- **A (Setup only)**: 12.5s — 파이프라인 생성만 (indexer 실행 없음)
- **B (cache 채움 baseline)**: 1534.8s — 캐시 ON 1차 Reindex
- **C (incremental)**: 17.6s — vs B: x87.2 빠름
- **D (cache 재사용 2차)**: 1529.3s — vs B: +5.5s (+0.4%)

### 해석

- A 는 `setup_ai_search_pipeline.py` (--run 없음) → 파이프라인 생성만
- B, D 는 `setup_ai_search_pipeline.py --run` → indexer reset + 전체 재인덱싱
- C 는 reset 없이 `POST /indexers/{name}/run` → change tracking 기반 증분
- D 에서 enrichment cache HIT 시 임베딩 재호출을 건너뛰어 B 대비 시간 절감

### 캐시 동작 정리

| 동작 | Change Tracking | Enrichment Cache | 임베딩 비용 |
|------|:-:|:-:|---:|
| Incremental run (C) | ✅ 변경분만 | ✅ 기존 결과 재사용 | 변경분만 |
| Reindex + cache warm (D) | ❌ 전체 재처리 | ✅ 기존 결과 재사용 | **$0** (cache HIT) |
| Reindex + cache cold (B 1차) | ❌ 전체 재처리 | ❌ 캐시 비어있음 | **전액** |
