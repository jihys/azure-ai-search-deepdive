# 노트북 실행 기록

**배포 리전**: Sweden Central  
**생성 시간**: 2026-05-12

---

## 1. 01-infra-deployment.ipynb (인프라 배포)

### 목적
- Bicep으로 전체 Azure 인프라 배포 (Sweden Central)
- Logic Apps 워크플로우 배포
- AI Search 파이프라인 설정
- .env 파일 생성

### 실행 상태
- [ ] 시작 대기

### 예상 소요 시간
- Bicep 배포: ~10-15분
- SPL 배포 및 승인: ~5분
- Function App 배포: ~3분
- Logic Apps 배포: ~2분
- AI Search 파이프라인: ~5분
- **총합: ~30분**

### 출력 결과
```
[실행 후 결과 저장]
```

### 배포된 리소스
- Virtual Network (10.0.0.0/16)
- Storage Account (Private)
- Azure AI Services (GPT-5.4, text-embedding-3-large)
- Document Intelligence
- Azure AI Search (Standard S1)
- Function App (Elastic Premium)
- Logic App (Consumption)
- 4개 Shared Private Links

### 상태
- [ ] 완료

---

## 2. 02-data-crawling.ipynb (크롤링 확인 및 실행)

### 목적
- Blob Storage 크롤링 데이터 확인
- 데이터가 없으면 Logic App 수동 실행
- 크롤링 상태 및 실행 이력 확인

### 실행 상태
- [ ] 시작 대기

### 체크 사항
- Blob Storage 파일 개수: `___`개
- 크롤링 소스: `___`개 (prec, detc, expc, admrul)
- Logic App 상태: `___`
- 최근 실행 결과: `___`

### 출력 결과
```
[실행 후 결과 저장]
```

### 상태
- [ ] 완료

---

## 3. 03-indexing.ipynb (AI Search 인덱싱)

### 목적
- AI Search 4개 인덱스 생성 (판례, 헌재, 법제처, 행정심판)
- Skillset 및 Indexer 생성 및 실행
- 인덱싱 완료 대기

### 실행 상태
- [ ] 시작 대기

### 인덱싱 파이프라인 성능
**명령어**: `setup_ai_search_pipeline.py --source all --run`

| 항목 | 값 |
|------|-----|
| 시작 시간 | `___` |
| 종료 시간 | `___` |
| **소요 시간** | **`___`분 `___`초** |
| 스크립트 종료 코드 | `___` (0 = 성공) |

### 인덱싱 결과
| 인덱스명 | 문서 개수 | 상태 |
|---------|----------|------|
| prec-court-index (판례) | `___`건 | ✅/❌ |
| const-court-index (헌재) | `___`건 | ✅/❌ |
| legis-interp-index (법제처) | `___`건 | ✅/❌ |
| admin-appeal-index (행심) | `___`건 | ✅/❌ |
| **총합** | **`___`건** | |

### 출력 결과
```
[실행 후 결과 저장]
```

### 상태
- [ ] 완료

---

## 4. 04-search-and-query.ipynb (검색 및 RAG 테스트)

### 목적
- 4개 인덱스 검색 테스트 (키워드, 하이브리드, 필터)
- Multi-Index 통합 검색
- RAG (단일 인덱스 및 Cross-Index)

### 실행 상태
- [ ] 시작 대기

### 검색 성능
- 환경 설정: ✅/❌
- 인덱스 통계 조회: ✅/❌
- 키워드 검색: ✅/❌
- 하이브리드 검색: ✅/❌
- 필터 검색: ✅/❌
- Multi-Index 검색: ✅/❌
- RAG (단일 인덱스): ✅/❌
- RAG (Cross-Index): ✅/❌

### 출력 결과
```
[실행 후 결과 샘플]
```

### 상태
- [ ] 완료

---

## 최종 요약

### 전체 실행 시간
- **01 노트북**: ~30분
- **02 노트북**: ~2분 (크롤링은 백그라운드)
- **03 노트북**: ~10-20분 (AI Search 인덱싱)
- **04 노트북**: ~5분 (검색 예제)
- **총합**: ~50-60분

### 성공 여부
- [ ] 모두 성공 ✅
- [ ] 일부 실패 ⚠️
- [ ] 전체 실패 ❌

### 오류 기록
```
[오류 발생 시 기록]
```

### 최종 상태
- **작성 일시**: 2026-05-12
- **실행 리전**: Sweden Central
- **스크립트 최종 검증**: 완료 ✅
- **준비 상태**: ✅ 실행 준비 완료

---

## 다음 단계

1. ✅ Remote VM에서 01 노트북 실행 (인프라 배포)
2. ⏳ 02 노트북 실행 (크롤링 확인)
3. ⏳ 03 노트북 실행 (AI Search 인덱싱)
4. ⏳ 04 노트북 실행 (검색 및 RAG 테스트)
5. ✅ 이 파일에 실행 결과 기록

---

## 참고

- 모든 노트북은 **내부망(VNet/Private Endpoint)**에서 실행되어야 합니다.
- 인증은 **Managed Identity (DefaultAzureCredential)**를 사용합니다.
- `.env` 파일은 01 노트북에서 자동 생성됩니다.
