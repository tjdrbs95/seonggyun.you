"""에이전트가 사용하는 도구. 문서 상태와 사용자 입출력에 묶인 함수로 만든다."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from anthropic import beta_tool

from .document import RFPDocument, slugify

NO_ANSWER = "(응답 없음 — 합리적으로 가정하고 본문에 [가정] 표시)"


class UserIO(Protocol):
    def say(self, text: str) -> None: ...

    def ask(self, prompt: str) -> str: ...


@dataclass
class Workspace:
    """한 번의 RFP 작성 세션이 공유하는 상태."""

    document: RFPDocument
    output_dir: Path
    io: UserIO
    interactive: bool = True
    output_path: Path | None = None
    finalized: bool = False

    def path(self) -> Path:
        if self.output_path is None:
            self.output_path = self.output_dir / f"{slugify(self.document.title)}.md"
        return self.output_path


def build_tools(ws: Workspace) -> list:
    @beta_tool
    def ask_user(questions: list[str]) -> str:
        """발주 담당자에게 RFP 작성에 필요한 정보를 묻는다. 관련 질문을 한 번에 묶어서 전달한다.

        Args:
            questions: 사용자에게 물어볼 질문 목록. 각 질문은 한 문장으로 구체적으로 쓴다.
        """
        questions = [q.strip() for q in questions if q and q.strip()]
        if not questions:
            return "질문이 비어 있습니다."
        if not ws.interactive:
            return "\n".join(f"Q{i}. {q}\nA{i}. {NO_ANSWER}" for i, q in enumerate(questions, 1))

        ws.io.say("\n[추가 정보 요청] 모르는 항목은 엔터로 넘기면 에이전트가 가정해서 작성합니다.")
        lines = []
        for i, q in enumerate(questions, 1):
            answer = ws.io.ask(f"Q{i}. {q}\n> ").strip()
            lines.append(f"Q{i}. {q}\nA{i}. {answer or NO_ANSWER}")
        return "\n".join(lines)

    @beta_tool
    def set_document_info(title: str, issuer: str = "") -> str:
        """RFP 문서 제목과 발주 기관명을 설정한다. 사업명이 정해지면 먼저 호출한다.

        Args:
            title: 문서 제목. 예: "○○ 통합 고객관리시스템 구축 사업 제안요청서"
            issuer: 발주 기관 또는 회사명. 모르면 빈 문자열.
        """
        ws.document.set_meta(title=title, issuer=issuer)
        return f"설정 완료: 제목='{ws.document.title}', 발주 기관='{ws.document.issuer or '(미정)'}'"

    @beta_tool
    def write_section(section_id: str, content: str, title: str = "") -> str:
        """RFP의 한 섹션을 작성하거나 덮어쓴다. 한 번에 한 섹션만 작성한다.

        Args:
            section_id: 표준 목차의 section_id(예: "overview", "functional_requirements") 또는 부록용 새 id.
            content: 섹션 본문(마크다운). 섹션 제목은 제외하고, 하위 제목은 ### 를 사용한다.
            title: 표준 목차에 없는 섹션일 때 표시할 제목. 표준 섹션이면 비워 둔다.
        """
        try:
            section = ws.document.write_section(section_id, content, title or None)
        except ValueError as e:
            return f"오류: {e}"
        ws.document.save(ws.path())  # 중간 결과를 잃지 않도록 매번 저장
        ws.io.say(f"  ✎ 작성: {section.title}")
        return f"'{section.title}' 저장 완료 ({len(section.content)}자)."

    @beta_tool
    def get_outline() -> str:
        """현재까지 작성된 섹션과 아직 작성하지 않은 표준 섹션 목록을 확인한다."""
        return ws.document.outline()

    @beta_tool
    def read_section(section_id: str) -> str:
        """이미 작성된 섹션의 본문을 다시 읽는다. 섹션 간 일관성을 검토할 때 사용한다.

        Args:
            section_id: 읽을 섹션의 id.
        """
        section = ws.document.sections.get(section_id)
        if section is None:
            return f"'{section_id}' 섹션이 없습니다. get_outline으로 목록을 확인하세요."
        return f"## {section.title}\n\n{section.content}"

    @beta_tool
    def finalize() -> str:
        """모든 섹션 작성과 검토를 마친 뒤 최종 RFP 문서를 파일로 저장한다."""
        if not ws.document.sections:
            return "오류: 작성된 섹션이 없습니다."
        path = ws.document.save(ws.path())
        ws.finalized = True
        return f"최종본 저장 완료: {path}"

    return [ask_user, set_document_info, write_section, get_outline, read_section, finalize]
