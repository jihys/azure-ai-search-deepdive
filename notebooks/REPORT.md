# 인덱싱 리포트

- 생성 시각: 2026-05-19 13:45:11
- Storage Container: `stragi63325wdoby/raw-documents`

## 인덱스별 요약

| 인덱스명           | 한국어명          |   Blob JSON 파일수 |   인덱스 문서수 |   차이(문서-파일) | Indexer             | Indexer 상태   | 처리건수(itemCount)   | 실패건수(failedItemCount)   |   소요시간(초) |
|:-------------------|:------------------|-------------------:|----------------:|------------------:|:--------------------|:---------------|:----------------------|:----------------------------|---------------:|
| prec-court-index   | 판례              |             105941 |          105906 |               -35 | prec-blob-indexer   | success        |                       |                             |       5753.74  |
| const-court-index  | 헌법재판소 결정례 |              38093 |           38086 |                -7 | const-blob-indexer  | success        |                       |                             |          7.537 |
| legis-interp-index | 법제처 해석례     |               8715 |            8715 |                 0 | interp-blob-indexer | success        |                       |                             |        884.782 |
| admin-appeal-index | 행정심판 재결례   |              29108 |           29107 |                -1 | admin-blob-indexer  | success        |                       |                             |       3125.22  |

## 총계 비교

- Blob JSON 총 파일수: **181,857**
- 인덱스 총 문서수: **181,814**
- 차이(문서-파일): **-43**

⚠️ 인덱스 문서 수가 더 적습니다. 인덱싱 실패/누락 여부 점검이 필요합니다.