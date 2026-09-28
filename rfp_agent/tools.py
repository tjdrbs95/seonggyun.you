"""에이전트가 사용하는 도구. 문서 상태와 사용자 입출력에 묶인 함수로 만든다."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from anthropic import beta_tool

from agent_core import NO_ANSWER, UserIO, make_ask_user_tool

from .document import RFPDocument, slugify

__all__ = ["NO_ANSWER", "Workspace", "build_tools"]


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
    ask_user = make_ask_user_tool(
        ws.io,
        lambda: ws.interactive,
        "발주 담당자에게 RFP 작성에 필요한 정보를 묻는다. 관련 질문을 한 번에 묶어서 전달한다.",
    )

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
