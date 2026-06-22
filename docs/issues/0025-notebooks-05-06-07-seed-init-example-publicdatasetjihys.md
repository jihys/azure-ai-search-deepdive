# 0025: Notebook 05/06/07 Seed Code 초기화 예시(publicdatasetjihys) 반영

**Status:** ready-for-agent
**Parent:** [PRD-notebook05-flow-and-seed-init](../prd/PRD-notebook05-flow-and-seed-init.md)

## 요약

`notebooks/05-multimodal-indexing.ipynb`, `notebooks/06-multimodal-search.ipynb`, `notebooks/07-content-understanding.ipynb`에 동일한 seed code 초기화 예시(`publicdatasetjihys`)를 반영해 신규 사용자 재현성을 높인다.

## 범위

- Notebook 05/06/07의 seed code 초기화 예시를 동일 패턴으로 정리
- `publicdatasetjihys` 기준 예시를 노트북별 컨텍스트에 맞게 제시
- 노트북 간 설명 톤과 순서를 일관화

## 비범위

- 인덱스/스킬셋/쿼리 알고리즘 변경
- 신규 데이터셋 추가
- Notebook 01~04 수정

## 무엇을 만들 것인가

세 노트북의 초기화 구간에서 seed 관련 안내를 일관된 형태로 제공한다.

- 어떤 값을 어디에 넣어야 하는지
- 왜 `publicdatasetjihys` 예시를 쓰는지
- 노트북별 차이(인덱싱/검색/CU)로 인해 달라지는 최소 안내만 분리

## 수용 기준 (검증 체크리스트)

- [ ] Notebook 05/06/07 모두에 seed 초기화 예시가 존재한다.
- [ ] 세 노트북 모두 `publicdatasetjihys`를 기준 예시로 사용한다.
- [ ] 예시 변수명/설명 문구가 노트북 간 충돌하지 않는다.
- [ ] 노트북별 목적 차이로 필요한 최소 차이 설명만 남기고 중복 설명을 줄였다.
- [ ] 신규 사용자가 05→06→07 순서로 읽을 때 seed 설정 맥락이 자연스럽게 이어진다.
- [ ] 오타/경로 불일치 없이 그대로 따라 입력 가능한 형태다.

## 리스크

- 노트북별 기존 변수 컨벤션과 seed 예시 문구가 충돌할 수 있음
- 공통화 과정에서 노트북별 필요 맥락이 부족해질 수 있음

## 선행/종속 관계

- **선행:** 오케스트레이터 3번 작업 완료, 이슈 0024 완료
- **종속:** 없음

## Blocked by

- 오케스트레이터 3번 작업 (별도 관리)
- [0024-notebook05-new-user-flow-cleanup](0024-notebook05-new-user-flow-cleanup.md)