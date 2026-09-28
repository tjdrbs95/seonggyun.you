"""제안서 덱 상태: 슬라이드 명세, RFP 요구사항과 대응 현황."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

# ── RFP 요구사항 ─────────────────────────────────────────────

ResponseStatus = Literal[
    "standard", "configuration", "extend", "integration", "partner", "roadmap", "not_supported", "tbd"
]

STATUS_LABELS: dict[str, str] = {
    "standard": "표준 기능",
    "configuration": "설정",
    "extend": "확장 개발(Extend)",
    "integration": "연동",
    "partner": "파트너 솔루션",
    "roadmap": "로드맵",
    "not_supported": "미지원",
    "tbd": "확인 필요",
}


class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="RFP의 요구사항 ID. RFP에 ID가 없으면 'REQ-001'처럼 부여")
    category: str = Field("", description="요구사항 분류. 예: 기능-인사관리, 비기능-보안, 사업관리")
    text: str = Field(description="요구사항 요약(원문 의미를 유지해 한두 문장)")
    status: ResponseStatus | None = Field(None, description="대응 유형")
    response: str = Field("", description="대응 방안 요약(한두 문장)")


class RequirementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: ResponseStatus
    response: str = Field(description="대응 방안 요약(한두 문장). 로드맵·미지원이면 대안이나 일정을 적는다.")


# ── 슬라이드 명세 ────────────────────────────────────────────

_Text = Annotated[str, Field(min_length=1)]


class _Content(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rfp_refs: list[str] = Field(default_factory=list, description="이 슬라이드가 대응하는 RFP 요구사항 ID")
    notes: str = Field("", description="발표자 노트(발표 스크립트)")


class CoverSlide(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["cover"]
    title: _Text = Field(description="제안서 제목. 예: '○○그룹 Workday HCM 구축 제안서'")
    subtitle: str = Field("", description="고객사 · 제안사 · 날짜 등. 예: '○○그룹 | 2026.10'")


class AgendaSlide(_Content):
    kind: Literal["agenda"]
    title: _Text = "목차"
    items: list[_Text] = Field(min_length=2, max_length=10, description="목차 항목(장 제목)")


class SectionSlide(_Content):
    kind: Literal["section"]
    number: str = Field("", description="장 번호. 예: '01', 'Ⅱ'")
    title: _Text
    subtitle: str = ""


class BulletsSlide(_Content):
    kind: Literal["bullets"]
    title: _Text
    message: str = Field("", description="헤드 메시지: 이 장표의 결론 한 문장")
    bullets: list[_Text] = Field(
        min_length=1, max_length=12, description="글머리 항목. '- '로 시작하면 하위 항목"
    )


class Column(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: _Text
    bullets: list[_Text] = Field(min_length=1, max_length=10, description="'- '로 시작하면 하위 항목")


class TwoColumnSlide(_Content):
    kind: Literal["two_column"]
    title: _Text
    message: str = ""
    left: Column
    right: Column


class CardsSlide(_Content):
    kind: Literal["cards"]
    title: _Text
    message: str = ""
    cards: list[Column] = Field(min_length=2, max_length=4, description="2~4개 카드(강점, 특장점 등)")


class TableSlide(_Content):
    kind: Literal["table"]
    title: _Text
    message: str = ""
    columns: list[_Text] = Field(min_length=2, max_length=6)
    rows: list[list[str]] = Field(min_length=1, max_length=12, description="각 행의 셀 수는 columns와 같아야 함")
    column_widths: list[float] | None = Field(None, description="열 너비 비율. 예: [1, 3, 2]")


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: _Text = Field(description="단계명. 예: 'Plan'")
    period: str = Field("", description="기간. 예: 'M1~M2'")
    bullets: list[_Text] = Field(default_factory=list, max_length=6, description="주요 활동·산출물")


class ProcessSlide(_Content):
    kind: Literal["process"]
    title: _Text
    message: str = ""
    steps: list[Step] = Field(min_length=3, max_length=6)


class HeadlineSlide(_Content):
    kind: Literal["headline"]
    title: _Text = Field(description="왼쪽에 크게 들어갈 핵심 메시지(2~3줄)")
    bullets: list[_Text] = Field(min_length=1, max_length=8, description="오른쪽 설명 항목")


class ClosingSlide(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["closing"]


SlideSpec = Annotated[
    Union[
        CoverSlide, AgendaSlide, SectionSlide, BulletsSlide, TwoColumnSlide,
        CardsSlide, TableSlide, ProcessSlide, HeadlineSlide, ClosingSlide,
    ],
    Field(discriminator="kind"),
]
SLIDE_ADAPTER: TypeAdapter[SlideSpec] = TypeAdapter(SlideSpec)


class AddSlideInput(BaseModel):
    """add_slide 도구의 입력 스키마."""

    slide: SlideSpec
    position: int | None = Field(None, description="삽입할 슬라이드 번호(1부터). 생략하면 맨 뒤(마무리 슬라이드 앞)")


class ReplaceSlideInput(BaseModel):
    """replace_slide 도구의 입력 스키마."""

    number: int = Field(description="바꿀 슬라이드 번호(1부터)")
    slide: SlideSpec


def tool_schema(model: type[BaseModel]) -> dict:
    """pydantic 스키마에서 JSON Schema 표준이 아닌 키(discriminator)를 빼고 oneOf를 anyOf로 바꾼다."""

    def clean(node):
        if isinstance(node, dict):
            node = {k: clean(v) for k, v in node.items() if k != "discriminator"}
            if "oneOf" in node:
                node["anyOf"] = node.pop("oneOf")
            return node
        if isinstance(node, list):
            return [clean(v) for v in node]
        return node

    return clean(model.model_json_schema())


# ── 덱 ──────────────────────────────────────────────────────


@dataclass
class ProposalDeck:
    title: str = "제안서"
    slides: list = field(default_factory=list)
    requirements: dict[str, Requirement] = field(default_factory=dict)

    # 슬라이드 조작 --------------------------------------------------

    def add(self, spec, position: int | None = None) -> int:
        if position is None:
            index = len(self.slides)
            if self.slides and self.slides[-1].kind == "closing" and spec.kind != "closing":
                index -= 1
        else:
            index = min(max(position - 1, 0), len(self.slides))
        self.slides.insert(index, spec)
        if spec.kind == "cover":
            self.title = spec.title
        return index + 1

    def replace(self, number: int, spec) -> None:
        self._check_number(number)
        self.slides[number - 1] = spec
        if spec.kind == "cover":
            self.title = spec.title

    def remove(self, number: int) -> None:
        self._check_number(number)
        del self.slides[number - 1]

    def _check_number(self, number: int) -> None:
        if not 1 <= number <= len(self.slides):
            raise ValueError(f"슬라이드 번호는 1~{len(self.slides)} 사이여야 합니다.")

    # 요구사항 ---------------------------------------------------------

    def register(self, requirements: list[Requirement]) -> None:
        for req in requirements:
            existing = self.requirements.get(req.id)
            if existing and not req.status:
                # 요구사항 문구만 갱신하고 이미 정한 대응 결과는 유지한다.
                req = req.model_copy(update={"status": existing.status, "response": existing.response})
            self.requirements[req.id] = req

    def respond(self, responses: list[RequirementResponse]) -> list[str]:
        unknown = []
        for r in responses:
            req = self.requirements.get(r.id)
            if req is None:
                unknown.append(r.id)
                continue
            self.requirements[r.id] = req.model_copy(update={"status": r.status, "response": r.response})
        return unknown

    def pages_for(self, req_id: str) -> list[int]:
        return [
            i for i, s in enumerate(self.slides, 1) if req_id in getattr(s, "rfp_refs", [])
        ]

    def unknown_refs(self, spec) -> list[str]:
        return [r for r in getattr(spec, "rfp_refs", []) if r not in self.requirements]

    def coverage(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {"no_slide": [], "no_response": []}
        for req_id, req in self.requirements.items():
            if not self.pages_for(req_id):
                result["no_slide"].append(req_id)
            if not req.status:
                result["no_response"].append(req_id)
        return result

    # 요약 ------------------------------------------------------------

    def outline(self) -> str:
        lines = [f"제안서: {self.title}", f"슬라이드 {len(self.slides)}장", ""]
        for i, s in enumerate(self.slides, 1):
            title = getattr(s, "title", "") or ""
            refs = getattr(s, "rfp_refs", [])
            ref_text = f"  [RFP: {', '.join(refs)}]" if refs else ""
            lines.append(f"{i:>2}. ({s.kind}) {title}{ref_text}")
        if self.requirements:
            cov = self.coverage()
            by_status: dict[str, int] = {}
            for req in self.requirements.values():
                key = STATUS_LABELS.get(req.status or "", "미정")
                by_status[key] = by_status.get(key, 0) + 1
            lines += [
                "",
                f"RFP 요구사항 {len(self.requirements)}건 — "
                + ", ".join(f"{k} {v}" for k, v in by_status.items()),
                f"- 슬라이드에서 다루지 않은 요구사항: {', '.join(cov['no_slide']) or '없음'}",
                f"- 대응 유형 미정: {', '.join(cov['no_response']) or '없음'}",
            ]
        return "\n".join(lines)

    # 저장·불러오기 -----------------------------------------------------

    def to_state(self) -> dict:
        return {
            "title": self.title,
            "slides": [s.model_dump(mode="json") for s in self.slides],
            "requirements": [r.model_dump(mode="json") for r in self.requirements.values()],
        }

    @classmethod
    def from_state(cls, state: dict) -> "ProposalDeck":
        deck = cls(title=state.get("title", "제안서"))
        deck.slides = [SLIDE_ADAPTER.validate_python(s) for s in state.get("slides", [])]
        deck.register([Requirement.model_validate(r) for r in state.get("requirements", [])])
        return deck
