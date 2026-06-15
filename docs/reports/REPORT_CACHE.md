# Indexer Caching 효과 비교 리포트 (Reindex vs Incremental Update)

- 생성: 2026-05-22 05:38:15
- 실험 소스: `detc`  /  indexer: `const-blob-indexer`
- Search: `https://search-ragi-63325wdo.search.windows.net`
- B.5 크롤링으로 추가된 신규 파일: **0건**

## 인덱스별 현황

| 인덱스 | 한국어명 | Blob 파일수 | 인덱스 문서수 |
|--------|----------|------------|-------------|
| prec-court-index | 판례 | 56,013 | 0 |
| const-court-index | 헌법재판소 결정례 | 9,714 | 0 |
| legis-interp-index | 법제처 해석례 | 0 | 0 |
| admin-appeal-index | 행정심판 재결례 | 90 | 0 |
| **합계** | | **65,817** | **0** |

## 결과

| 종류    | 시나리오                                    |   소요(초) | 비고                                    |
|:--------|:--------------------------------------------|-----------:|:----------------------------------------|
| Reindex | A. 캐시 OFF 전체 재인덱싱 (baseline)        |       11.7 | rc=0                                    |
| Reindex | B. 캐시 ON 전체 재인덱싱 (1차, 캐시 채움)   |       29.6 | rc=0                                    |
| Update  | C. 캐시 ON Incremental Update (신규 0건)    |        4.1 | items=None, failed=None, status=success |
| Reindex | D. 캐시 ON 전체 재인덱싱 (2차, 캐시 재사용) |       29.9 | rc=0                                    |

## 해석

- **C / A 가속비**: x2.8
- **C / B 가속비**: x7.2

- A, B, D 는 `reset` 후 재생성하므로 모두 **전체 재인덱싱(Reindex)** 입니다.
- C 는 reset 없이 `POST /indexers/{name}/run` 만 호출 → **증분 갱신(Incremental Update)**.
  - change tracking(BLOB LastModified) 로 기존 blob skip
  - SETUP_ENABLE_CACHE=1 의 enrichment cache 로 동일 입력 skill 호출 skip

### D — Reindex 때도 캐시가 재사용되는가?

- A(no-cache reindex) = **11.7s** vs D(cache 재사용 reindex) = **29.9s**
- 절감: **-18.2s (-156.3%)**
- `reset` 은 change tracking 만 무효화하고 enrichment cache 는 보존됩니다. 따라서 D 에서 모든 blob 이 재처리되지만 **임베딩 등 skill 결과는 cache HIT** 으로 재사용되어 시간/비용이 감소합니다.