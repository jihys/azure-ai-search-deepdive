# Azure AI Search Deep Dive Lab — Copilot Instructions

## 프로젝트 개요

Azure AI Search 핵심 기능을 2개 시나리오(법령 문서 / 멀티모달)로 데모하는 Hands-on Lab.

## 핵심 규칙

- **언어**: 한국어로 응답 (코드/로그/에러는 영어 유지)
- **Python 환경**: `.venv` 가상환경 사용 (`source .venv/bin/activate`)
- **Python 경로**: `.venv/bin/python` (Python 3.13)
- **노트북 커널**: `.venv` 환경 사용

## 프로젝트 구조

| 디렉토리 | 역할 |
|-----------|------|
| `src/` | 핵심 라이브러리 (crawler, preprocessing, search, blob) |
| `notebooks/` | 핸즈온 랩 노트북 01~06 |
| `scripts/` | CLI 스크립트 (인덱싱, 시드 데이터 등) |
| `infra/` | Bicep IaC (korea, sweden, sweden-public) |
| `logic-apps/` | Logic Apps 워크플로우 + Azure Functions |
| `skills-function/` | Custom Skills Azure Function |
| `data/` | raw/processed/samples 데이터 |

## 시나리오

- **A. 법령 문서**: law.go.kr 크롤링 → Logic Apps → AI Search Skillset → 4개 인덱스
- **B. 멀티모달**: PDF/PPTX → AI Search Skillset 비교 (Native vs Custom+Native) → 2개 인덱스

## Fix at Origin 원칙

노트북 셀 에러 발생 시, 노트북 안에서 임시 수정하지 말고 원본 소스(`src/`, `infra/`, `scripts/`)를 수정할 것.

## 사용 가능한 Skills

이 프로젝트에는 다음 커스텀 스킬이 등록되어 있습니다:

| Skill | 용도 |
|-------|------|
| `grill-me` | 설계/계획을 빈틈없이 인터뷰 |
| `grill-with-docs` | 인터뷰 + CONTEXT.md/ADR 문서화 |
| `notebook-lab-fixer` | 노트북 랩 셀 에러 진단·수정 |
| `tdd` | Red-Green-Refactor TDD 루프 |
| `to-issues` | 계획을 GitHub 이슈로 분해 |
| `to-prd` | 대화 내용을 PRD로 정리 |
| `triage` | 이슈 트리아지 상태 머신 |
