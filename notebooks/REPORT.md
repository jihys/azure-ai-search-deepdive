# 인덱싱 리포트

- 생성 시각: 2026-05-28 04:56:01
- Storage Container: `stragi63325wdoby/raw-documents`

## 인덱스별 요약

| 인덱스명           | 한국어명          |   Blob JSON 파일수 |   인덱스 문서수 |   차이(문서-파일) | Indexer             | Indexer 상태   | 처리건수(itemCount)   | 실패건수(failedItemCount)   |   소요시간(초) |
|:-------------------|:------------------|-------------------:|----------------:|------------------:|:--------------------|:---------------|:----------------------|:----------------------------|---------------:|
| prec-court-index   | 판례              |              56013 |               0 |            -56013 | prec-blob-indexer   | success        |                       |                             |          0.239 |
| const-court-index  | 헌법재판소 결정례 |               9714 |               0 |             -9714 | const-blob-indexer  | success        |                       |                             |          1.299 |
| legis-interp-index | 법제처 해석례     |                  0 |               0 |                 0 | interp-blob-indexer | success        |                       |                             |          1.383 |
| admin-appeal-index | 행정심판 재결례   |                 90 |               0 |               -90 | admin-blob-indexer  | success        |                       |                             |          3.352 |

## 총계 비교

- Blob JSON 총 파일수: **65,817**
- 인덱스 총 문서수: **0**
- 차이(문서-파일): **-65,817**

⚠️ 인덱스 문서 수가 더 적습니다. 인덱싱 실패/누락 여부 점검이 필요합니다.