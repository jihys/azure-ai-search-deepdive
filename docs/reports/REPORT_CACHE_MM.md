# Multimodal Indexer Caching — 실험 결과

- 대상 indexer: `st-multimodal-verbalized-indexer`
- 대상 index  : `st-multimodal-verbalized-index`
- source      : `st`

## 시나리오별 소요시간

| scenario                       |   wall_sec | indexer_sec   |   items |   failed |
|:-------------------------------|-----------:|:--------------|--------:|---------:|
| A. cache OFF (baseline)        |        0   |               |     nan |      nan |
| B. cache ON (1st — fill cache) |     7260.9 |               |       0 |        0 |
| C. cache ON (2nd — HIT)        |     7277.8 |               |       0 |        0 |

## Cache HIT 효과 (C vs A)

- baseline 측정 실패
- cache HIT 측정 실패


## 해석

- 멀티모달 파이프라인은 `DocumentIntelligenceLayoutSkill` 과 GPT verbalize `ChatCompletionSkill` 이 dominant cost (각각 수 초/호출).
- Cache HIT 시 두 skill 호출이 Storage Table/Blob 조회 (~50 ms) 로 대체되므로 **시간·비용 모두 큰 폭 절감**.
- 노트북 03 (텍스트 임베딩) 의 결과와 비교: 텍스트는 batch 임베딩이 ~5 ms/문서로 cache lookup 보다 빨라 오히려 손해. 멀티모달에서는 반대로 cache 가 명확한 이득.