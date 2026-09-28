"""RFP 문서 상태: 섹션 저장, 목차 순서 관리, 마크다운 렌더링과 저장."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from agent_core.text import slugify  # noqa: F401  (다른 모듈에서 여기서 가져다 씀)

# 기본 목차. 에이전트는 이 id를 사용해 섹션을 작성하고,
# 필요하면 목록에 없는 id로 추가 섹션(부록 등)을 만들 수 있다.
STANDARD_SECTIONS: list[tuple[str, str]] = [
    ("overview", "1. 사업 개요"),
    ("current_state", "2. 현황 및 문제점"),
    ("scope", "3. 사업 범위"),
    ("functional_requirements", "4. 기능 요구사항"),
    ("non_functional_requirements", "5. 비기능 요구사항"),
    ("schedule_deliverables", "6. 추진 일정 및 산출물"),
    ("project_management", "7. 사업 관리 요구사항"),
    ("budget_contract", "8. 예산 및 계약 조건"),
    ("proposal_guidelines", "9. 제안서 작성 지침"),
    ("evaluation", "10. 평가 기준 및 방법"),
    ("submission", "11. 제출 안내 및 문의처"),
]

_STANDARD_ORDER = {section_id: i for i, (section_id, _) in enumerate(STANDARD_SECTIONS)}
_STANDARD_TITLES = dict(STANDARD_SECTIONS)


@dataclass
class Section:
    section_id: str
    title: str
    content: str


@dataclass
class RFPDocument:
    title: str = "제안요청서(RFP)"
    issuer: str = ""
    sections: dict[str, Section] = field(default_factory=dict)
    # 표준 목차 밖의 섹션은 추가된 순서대로 뒤에 붙인다.
    _extra_order: list[str] = field(default_factory=list)

    def set_meta(self, title: str | None = None, issuer: str | None = None) -> None:
        if title:
            self.title = title.strip()
        if issuer:
            self.issuer = issuer.strip()

    def write_section(self, section_id: str, content: str, title: str | None = None) -> Section:
        section_id = section_id.strip()
        if not section_id:
            raise ValueError("section_id가 비어 있습니다.")
        if not content.strip():
            raise ValueError("content가 비어 있습니다.")
        resolved_title = (title or "").strip() or _STANDARD_TITLES.get(section_id) or section_id
        if section_id not in _STANDARD_ORDER and section_id not in self._extra_order:
            self._extra_order.append(section_id)
        section = Section(section_id, resolved_title, content.strip())
        self.sections[section_id] = section
        return section

    def ordered_sections(self) -> list[Section]:
        standard = [
            self.sections[section_id]
            for section_id, _ in STANDARD_SECTIONS
            if section_id in self.sections
        ]
        extra = [self.sections[section_id] for section_id in self._extra_order]
        return standard + extra

    def missing_standard_sections(self) -> list[tuple[str, str]]:
        return [(sid, title) for sid, title in STANDARD_SECTIONS if sid not in self.sections]

    def outline(self) -> str:
        lines = [f"문서 제목: {self.title}", f"발주 기관: {self.issuer or '(미정)'}", ""]
        lines.append("[작성 완료]")
        done = self.ordered_sections()
        if done:
            lines += [f"- {s.section_id}: {s.title} ({len(s.content)}자)" for s in done]
        else:
            lines.append("- (없음)")
        lines.append("")
        lines.append("[미작성 표준 섹션]")
        missing = self.missing_standard_sections()
        if missing:
            lines += [f"- {sid}: {title}" for sid, title in missing]
        else:
            lines.append("- (없음)")
        return "\n".join(lines)

    def to_markdown(self, today: date | None = None) -> str:
        today = today or date.today()
        parts = [f"# {self.title}", ""]
        meta = []
        if self.issuer:
            meta.append(f"- 발주 기관: {self.issuer}")
        meta.append(f"- 작성일: {today.isoformat()}")
        parts += meta + [""]

        sections = self.ordered_sections()
        if sections:
            parts += ["## 목차", ""]
            parts += [f"- {s.title}" for s in sections]
            parts.append("")
        for s in sections:
            parts += [f"## {s.title}", "", _demote_headings(s.content), ""]
        return "\n".join(parts).rstrip() + "\n"

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown(), encoding="utf-8")
        return path


def _demote_headings(content: str) -> str:
    """섹션 본문 안의 '#', '##' 제목을 '###' 이하로 내려 문서 구조를 유지한다."""

    def repl(match: re.Match[str]) -> str:
        level = len(match.group(1))
        return "#" * max(level, 3) + match.group(2)

    return re.sub(r"^(#{1,6})(\s)", repl, content, flags=re.MULTILINE)
