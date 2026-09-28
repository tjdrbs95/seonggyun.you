"""제안서 테스트 공용 데이터. Workday 템플릿은 저장소에 없으므로 python-pptx 기본 템플릿을 쓴다."""

from pathlib import Path

import pptx

DEFAULT_TEMPLATE = Path(pptx.__file__).parent / "templates" / "default.pptx"

ALL_KINDS = [
    {"kind": "cover", "title": "○○그룹 Workday HCM 구축 제안서", "subtitle": "○○그룹 | 2026.10"},
    {"kind": "agenda", "items": ["제안 개요", "제안 솔루션", "요구사항 대응", "구축 방안", "운영 지원", "부록"]},
    {"kind": "section", "number": "01", "title": "제안 개요", "subtitle": "사업 이해"},
    {"kind": "headline", "title": "하나의 데이터 모델로 통합", "bullets": ["**단일 모델**: 인사·보상 통합", "- 하위 항목"],
     "rfp_refs": ["SFR-001"]},
    {"kind": "bullets", "title": "제안 배경", "message": "통합이 필요합니다.", "bullets": ["항목 1", "항목 2"],
     "rfp_refs": ["SFR-001", "SFR-002"], "notes": "발표 스크립트"},
    {"kind": "two_column", "title": "As-Is / To-Be", "left": {"heading": "As-Is", "bullets": ["분산"]},
     "right": {"heading": "To-Be", "bullets": ["통합"]}, "rfp_refs": ["SFR-002"]},
    {"kind": "cards", "title": "특장점", "cards": [{"heading": "A", "bullets": ["a"]}, {"heading": "B", "bullets": ["b"]},
                                                 {"heading": "C", "bullets": ["c"]}]},
    {"kind": "table", "title": "대응 방안", "columns": ["ID", "요구사항", "대응"],
     "rows": [["SFR-001", "통합 인사", "표준 기능"], ["SFR-002", "조직 개편", "표준 기능"]], "column_widths": [1, 3, 2]},
    {"kind": "process", "title": "방법론", "steps": [{"name": "Plan", "period": "M1", "bullets": ["착수"]},
                                                   {"name": "Configure", "bullets": ["설정"]},
                                                   {"name": "Deploy", "bullets": ["오픈"]}], "rfp_refs": ["PMR-001"]},
    {"kind": "closing"},
]
