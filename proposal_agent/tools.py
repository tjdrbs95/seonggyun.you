"""제안서 에이전트 도구: 요구사항 정리, 슬라이드 작성·수정, 최종 저장."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from anthropic import beta_tool
from pydantic import ValidationError

from agent_core import UserIO, make_ask_user_tool
from agent_core.text import slugify

from .deck import (
    SLIDE_ADAPTER,
    STATUS_LABELS,
    AddSlideInput,
    ProposalDeck,
    ReplaceSlideInput,
    Requirement,
    RequirementResponse,
    tool_schema,
)
from .layout import FitError, plan_slide
from .render import DeckRenderer


@dataclass
class Workspace:
    """한 번의 제안서 작성 세션이 공유하는 상태."""

    deck: ProposalDeck
    renderer: DeckRenderer
    output_dir: Path
    io: UserIO
    interactive: bool = True
    output_path: Path | None = None
    finalized: bool = False

    def path(self) -> Path:
        if self.output_path is None:
            self.output_path = self.output_dir / f"{slugify(self.deck.title)}.pptx"
        return self.output_path

    def state_path(self) -> Path:
        return self.path().with_suffix(".deck.json")

    def matrix_path(self) -> Path:
        return self.path().with_name(self.path().stem + "_요구사항대응표.csv")

    def autosave(self) -> None:
        path = self.state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.deck.to_state(), ensure_ascii=False, indent=1), encoding="utf-8")

    def export(self) -> list:
        """PPTX와 요구사항 대응표(CSV)를 저장하고 그린 슬라이드 목록을 돌려준다."""
        self.autosave()
        slides = self.renderer.render(self.deck, self.path())
        write_matrix(self.deck, self.matrix_path())
        return slides


def write_matrix(deck: ProposalDeck, path: Path) -> None:
    # utf-8-sig: 엑셀에서 한글이 깨지지 않게 BOM을 붙인다.
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ID", "분류", "요구사항", "대응 유형", "대응 방안", "제안서 페이지"])
        for req in deck.requirements.values():
            pages = ", ".join(str(p) for p in deck.pages_for(req.id))
            w.writerow([req.id, req.category, req.text, STATUS_LABELS.get(req.status or "", "미정"),
                        req.response, pages])


def _validation_message(e: ValidationError) -> str:
    lines = []
    for err in e.errors()[:8]:
        loc = ".".join(str(x) for x in err["loc"])
        lines.append(f"- {loc}: {err['msg']}")
    return "입력 형식 오류:\n" + "\n".join(lines)


def build_tools(ws: Workspace) -> list:
    geo = ws.renderer.geometry

    ask_user = make_ask_user_tool(
        ws.io,
        lambda: ws.interactive,
        "제안 담당자에게 제안서 작성에 필요한 정보(제안사 정보, 수행 실적, 투입 인력, 라이선스 범위, "
        "일정 가정 등 자료에 없는 내용)를 묻는다. 관련 질문을 한 번에 묶어서 전달한다.",
    )

    @beta_tool
    def register_requirements(requirements: list[Requirement]) -> str:
        """RFP에서 뽑은 요구사항을 등록한다. 같은 ID는 문구를 갱신한다. 한 번에 최대 40건씩 등록한다.

        Args:
            requirements: 요구사항 목록(id, category, text). 대응 유형은 set_requirement_responses로 정한다.
        """
        ws.deck.register(requirements)
        ws.autosave()
        return f"{len(requirements)}건 등록. 전체 {len(ws.deck.requirements)}건."

    @beta_tool
    def set_requirement_responses(responses: list[RequirementResponse]) -> str:
        """요구사항별 대응 유형과 대응 방안을 기록한다. 부록 대응표와 CSV에 그대로 들어간다.

        Args:
            responses: (id, status, response) 목록. status는 standard/configuration/extend/integration/partner/roadmap/not_supported/tbd.
        """
        unknown = ws.deck.respond(responses)
        ws.autosave()
        msg = f"{len(responses) - len(unknown)}건 기록."
        if unknown:
            msg += f" 등록되지 않은 ID(먼저 register_requirements로 등록): {', '.join(unknown)}"
        return msg

    def _check(spec) -> str | None:
        try:
            plan_slide(spec, geo)
        except FitError as e:
            return f"오류: {e}"
        return None

    def _ref_warning(spec) -> str:
        unknown = ws.deck.unknown_refs(spec)
        return f" (주의: 등록되지 않은 요구사항 ID {', '.join(unknown)})" if unknown else ""

    def add_slide(slide: dict, position: int | None = None) -> str:
        try:
            spec = SLIDE_ADAPTER.validate_python(slide)
        except ValidationError as e:
            return _validation_message(e)
        if error := _check(spec):
            return error
        number = ws.deck.add(spec, position)
        ws.autosave()
        ws.io.say(f"  ▣ {number}. {getattr(spec, 'title', spec.kind)}")
        return f"{number}번 슬라이드로 추가(전체 {len(ws.deck.slides)}장).{_ref_warning(spec)}"

    def replace_slide(number: int, slide: dict) -> str:
        try:
            spec = SLIDE_ADAPTER.validate_python(slide)
        except ValidationError as e:
            return _validation_message(e)
        if error := _check(spec):
            return error
        try:
            ws.deck.replace(number, spec)
        except ValueError as e:
            return f"오류: {e}"
        ws.autosave()
        ws.io.say(f"  ↻ {number}. {getattr(spec, 'title', spec.kind)}")
        return f"{number}번 슬라이드를 교체했습니다.{_ref_warning(spec)}"

    add_slide_tool = beta_tool(
        add_slide,
        name="add_slide",
        description=(
            "제안서에 슬라이드 한 장을 추가한다. kind로 형식을 고른다: cover(표지), agenda(목차), "
            "section(장 구분), headline(왼쪽 큰 메시지+오른쪽 설명), bullets(글머리), two_column(좌우 비교), "
            "cards(2~4개 카드), table(표), process(단계/일정), closing(마무리). "
            "내용이 영역을 넘치면 오류를 돌려주므로 줄이거나 나눠서 다시 호출한다. "
            "글머리 항목은 '- '로 시작하면 하위 항목, '**굵게**'로 강조한다."
        ),
        input_schema=tool_schema(AddSlideInput),
    )
    replace_slide_tool = beta_tool(
        replace_slide,
        name="replace_slide",
        description="기존 슬라이드를 새 내용으로 통째로 바꾼다. 번호는 get_outline 기준.",
        input_schema=tool_schema(ReplaceSlideInput),
    )

    @beta_tool
    def remove_slide(number: int) -> str:
        """슬라이드를 삭제한다. 뒤 슬라이드 번호가 하나씩 당겨진다.

        Args:
            number: 삭제할 슬라이드 번호(1부터).
        """
        try:
            ws.deck.remove(number)
        except ValueError as e:
            return f"오류: {e}"
        ws.autosave()
        return f"{number}번 삭제. 전체 {len(ws.deck.slides)}장."

    @beta_tool
    def get_outline() -> str:
        """현재 슬라이드 목록과 요구사항 대응 현황(슬라이드 미반영, 대응 유형 미정)을 확인한다."""
        return ws.deck.outline()

    @beta_tool
    def read_slide(number: int) -> str:
        """슬라이드 한 장의 내용을 JSON으로 읽는다. 수정 전에 현재 내용을 확인할 때 사용한다.

        Args:
            number: 슬라이드 번호(1부터).
        """
        if not 1 <= number <= len(ws.deck.slides):
            return f"오류: 슬라이드 번호는 1~{len(ws.deck.slides)} 사이여야 합니다."
        return json.dumps(ws.deck.slides[number - 1].model_dump(mode="json"), ensure_ascii=False)

    @beta_tool
    def finalize() -> str:
        """제안서 PPTX와 요구사항 대응표(CSV)를 저장한다. 부록 대응표 슬라이드는 자동으로 붙는다."""
        if not ws.deck.slides:
            return "오류: 슬라이드가 없습니다."
        slides = ws.export()
        ws.finalized = True
        cov = ws.deck.coverage()
        lines = [
            f"저장 완료: {ws.path()} (부록 포함 {len(slides)}장)",
            f"요구사항 대응표: {ws.matrix_path()}",
        ]
        if cov["no_slide"]:
            lines.append(f"본문 슬라이드에서 다루지 않은 요구사항: {', '.join(cov['no_slide'])}")
        if cov["no_response"]:
            lines.append(f"대응 유형 미정: {', '.join(cov['no_response'])}")
        return "\n".join(lines)

    return [
        ask_user, register_requirements, set_requirement_responses, add_slide_tool, replace_slide_tool,
        remove_slide, get_outline, read_slide, finalize,
    ]
