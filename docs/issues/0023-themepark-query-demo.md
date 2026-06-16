# 0023: 테마파크 쿼리 데모

**Status:** 🔲 대기  
**Parent:** [PRD-themepark-and-academic-field](../prd/PRD-themepark-and-academic-field.md)

## 요약

테마파크 Knowledge Source의 Agentic Retrieval + Image Serving 기능을 데모하는 노트북 섹션을 추가한다.

## 상세

### 노트북 구성

`notebooks/07-content-understanding.ipynb` 또는 별도 노트북(`notebooks/08-themepark-demo.ipynb`)에 다음 섹션 추가:

1. **Image Verbalization 검증**
   - 인덱스에서 `$filter=image_snippet_parent_id ne null` 쿼리
   - verbalized 이미지 청크 내용 확인

2. **Agentic Retrieval + Image Serving 비교**
   - `enable-image-serving=false` 응답 확인 (텍스트만)
   - `enable-image-serving=true` 응답 확인 (원본 이미지 URL 포함)
   - 응답 비교 시각화

3. **위치 관계 질문 예시**
   - "에버랜드에서 T-Express는 어디에 있나요?"
   - "롯데월드에서 매직캐슬과 자이로스핀은 가까운가요?"
   - 지도 기반 응답 정확도 확인

### 쿼리 패턴

```json
POST /knowledgebases/{name}/retrieve?enable-image-serving=true
{
  "retrievalReasoningEffort": {"kind": "medium"},
  "outputMode": "answerSynthesis",
  "messages": [{"role": "user", "content": [{"type": "text", "text": "에버랜드에서 T-Express 위치는?"}]}]
}
```

## 수용 기준

- [ ] Image Serving 활성화 시 응답에 원본 이미지 URL 반환 확인
- [ ] Image Serving 비활성화 시 텍스트만 반환 확인
- [ ] 위치 관계 질문에 대해 의미 있는 응답 생성
- [ ] 노트북 셀이 순서대로 오류 없이 실행 가능
- [ ] 응답 비교 (활성/비활성) 시각적으로 확인 가능

## 변경 파일

- `notebooks/07-content-understanding.ipynb` 또는 `notebooks/08-themepark-demo.ipynb` (신규)
- `src/search/` — 필요 시 쿼리 헬퍼 추가

## 의존성

- [0022-themepark-knowledge-source](0022-themepark-knowledge-source.md) 완료 필수
- Knowledge Source 인덱싱 완료 상태
