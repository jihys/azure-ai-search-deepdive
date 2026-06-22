# 0008 — 노트북 sweden-public 조건부 안내 추가

**Status:** done
**Parent:** N/A (legacy issue)

**Type**: docs

## 설명

3개 노트북의 마크다운 셀에서 private 배포 전용 내용에 `sweden-public` 배포 시 해당 없음을 알리는 한 줄 안내를 추가한다.

## 변경 대상

| 노트북 | 위치 | 안내 내용 |
|--------|------|-----------|
| `04-search-and-query.ipynb` | 내부망 실행 조건 아래 | 공개 엔드포인트로 직접 접근 가능 |
| `01-infra-deployment.ipynb` | 배포 리소스 테이블 아래 | VNet/PE/SPL 미배포, FC1 사용 |
| `05-multimodal-indexing.ipynb` | PE 승인 전제조건 아래 | PE 승인 불필요, 건너뛸 수 있음 |

## 제약 사항

- 기존 내용 수정/삭제 금지 — 안내 문구만 추가
- 코드 셀 변경 없음
- 노트북 JSON 구조 유지
