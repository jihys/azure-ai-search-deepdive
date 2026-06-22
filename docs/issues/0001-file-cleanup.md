# 파일 정리: 죽은 코드 삭제 + data 정리 + 리포트 이동

**Status:** done
**Parent:** [PRD-cleanup.md](../prd/PRD-cleanup.md)

## What to build

순수 파일 삭제·이동 작업. 코드 로직 변경 없이 파일 시스템만 정리한다.

**src/ 죽은 코드 삭제:**
- `src/blob/` 전체 삭제 (uploader.py — 미사용)
- `src/crawler/` 전체 삭제 (law_crawler.py, legal_data_generator.py, precedent_crawler.py — 미사용)
- `src/preprocessing/` 전체 삭제 (chunk_processor.py, legal_chunker.py, doc_intelligence.py, embedding.py, multimodal_processor.py — 미사용)
- `src/search/index_manager.py` 삭제 (범용 베이스 — 미사용)
- `scripts/__pycache__/` 삭제

**data/ 정리:**
- `data/samples/` 삭제 (0바이트 빈 JSON 4개)
- `data/raw/2026-04-15/`, `data/raw/2026-04-19/` 삭제 (불필요한 크롤링 샘플)
- `.gitignore`에 `data/*.zip` 추가 (9.4GB ZIP 파일 git 제외)
- `data/raw/*.pdf`와 `data/processed/.gitkeep`은 유지

**리포트 파일 이동:**
- `notebooks/`의 리포트 7개를 `docs/reports/`로 이동:
  - `cache_experiment_results.json`, `full_experiment_results.json`
  - `REPORT.md`, `REPORT_CACHE.md`, `REPORT_CACHE_MM.md`
  - `multi-modal-report-v7.md`, `multi-modal-report-en.md`
- 루트의 `multi-modal-report-en.md` 삭제 (notebooks/ 버전과 중복)

## Acceptance criteria

- [x] `src/`에 `search/`와 `__init__.py`만 남아있음 (`blob/`, `crawler/`, `preprocessing/` 없음)
- [x] `src/search/`에 `legal_indexes.py`, `multimodal_index.py`, `__init__.py`만 있음 (`index_manager.py` 없음)
- [x] `data/samples/` 디렉토리 없음
- [x] `data/raw/`에 `*.pdf`만 있음 (날짜별 폴더 없음)
- [x] `.gitignore`에 `data/*.zip` 패턴 존재
- [x] `notebooks/`에 `.ipynb` 파일만 있음
- [x] `docs/reports/`에 리포트 7개 존재
- [x] 루트에 `multi-modal-report-en.md` 없음
- [x] `scripts/` 디렉토리에 `__pycache__` 없음

## Blocked by

None - can start immediately
