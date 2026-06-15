---
description: "노트북 랩 셀 에러 진단 및 원본 소스 수정"
mode: "agent"
tools: ["run_in_terminal", "read_file", "replace_string_in_file", "run_notebook_cell", "read_notebook_cell_output"]
---

`notebook-lab-fixer` 스킬을 사용해서 현재 노트북의 에러를 진단하고 수정해줘.
Fix at Origin 원칙에 따라 노트북이 아닌 원본 소스(src/, infra/, scripts/)를 수정할 것.
