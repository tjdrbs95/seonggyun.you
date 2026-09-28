"""슬라이드 영역 계산과 글자 크기 맞춤.

렌더러와 add_slide 검증이 같은 계산을 사용한다. 내용이 영역에 들어가지 않으면
FitError를 내고, 에이전트는 그 메시지를 보고 슬라이드를 나누거나 줄인다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

BODY_SIZES = (12, 11, 10, 9)
TABLE_SIZES = (10, 9, 8)
LINE_SPACING = 1.2
SUB_INDENT_IN = 0.2  # 하위 글머리 추가 들여쓰기
BULLET_INDENT_IN = 0.16  # 글머리 기호 공간


class FitError(ValueError):
    pass


@dataclass(frozen=True)
class Box:
    left: float
    top: float
    width: float
    height: float


@dataclass(frozen=True)
class Geometry:
    """슬라이드 크기(인치)에 따른 기본 영역. 기준은 Workday 템플릿(10 x 5.625)."""

    width: float = 10.0
    height: float = 5.625
    margin_x: float = 0.5

    @property
    def inner_width(self) -> float:
        return self.width - 2 * self.margin_x

    def message_box(self) -> Box:
        return Box(self.margin_x, 0.92, self.inner_width, 0.42)

    def body_box(self, has_message: bool) -> Box:
        top = 1.45 if has_message else 1.1
        bottom = self.height - 0.45
        return Box(self.margin_x, top, self.inner_width, bottom - top)


# ── 텍스트 크기 추정 ─────────────────────────────────────────


def _char_em(ch: str) -> float:
    o = ord(ch)
    if 0xAC00 <= o <= 0xD7AF or 0x1100 <= o <= 0x11FF or 0x3000 <= o <= 0x9FFF or 0xFF00 <= o <= 0xFFEF:
        return 0.95
    if ch == " ":
        return 0.28
    if ch.isupper() or ch.isdigit():
        return 0.64
    return 0.52


def text_width(text: str, pt: float) -> float:
    return sum(_char_em(c) for c in text) * pt / 72


def line_count(text: str, width_in: float, pt: float) -> int:
    if width_in <= 0:
        return 999
    total = 0
    for part in text.split("\n"):
        # 단어 단위 줄바꿈 여유분 8%
        total += max(1, math.ceil(text_width(part, pt) * 1.08 / width_in))
    return total


def split_bullet(text: str) -> tuple[str, int]:
    """'- '로 시작하면 하위 항목(level 1)."""
    stripped = text.lstrip()
    if stripped.startswith(("- ", "– ", "· ")):
        return stripped[2:].strip(), 1
    return text.strip(), 0


def bullets_height(bullets: list[str], width_in: float, pt: float, gap_pt: float | None = None) -> float:
    gap_pt = pt * 0.45 if gap_pt is None else gap_pt
    total = 0.0
    for raw in bullets:
        text, level = split_bullet(raw)
        indent = BULLET_INDENT_IN + level * SUB_INDENT_IN
        lines = line_count(text, width_in - indent, pt)
        total += lines * pt * LINE_SPACING / 72 + gap_pt / 72
    return total


def fit_bullets(bullets: list[str], box_width: float, box_height: float, sizes=BODY_SIZES, what="본문") -> int:
    for pt in sizes:
        if bullets_height(bullets, box_width, pt) <= box_height:
            return pt
    need = bullets_height(bullets, box_width, sizes[-1])
    raise FitError(
        f"{what} 내용이 영역을 넘칩니다(최소 {sizes[-1]}pt 기준 필요 높이 {need:.1f}in / 가능 {box_height:.1f}in, "
        f"약 {int(100 * need / box_height)}%). 항목을 줄이거나 문장을 짧게 하거나 슬라이드를 나누세요."
    )


def fit_single(text: str, width_in: float, height_in: float, sizes: tuple[int, ...], what: str) -> int:
    for pt in sizes:
        if line_count(text, width_in, pt) * pt * LINE_SPACING / 72 <= height_in:
            return pt
    raise FitError(f"{what}이(가) 너무 깁니다: '{text[:30]}…' — 더 짧게 쓰세요.")


# ── 종류별 배치 계획 ─────────────────────────────────────────

CARD_HEADER_H = 0.34
CARD_PAD = 0.1
COLUMN_GAP = 0.2
TITLE_SIZES = (18, 16, 14)
MESSAGE_SIZES = (11, 10, 9)


@dataclass
class Plan:
    """렌더러가 사용할 영역과 글자 크기."""

    title_pt: int = 18
    message_pt: int = 10
    body_pt: int = 11
    extra: dict | None = None


def _title_and_message(spec, geo: Geometry) -> Plan:
    plan = Plan()
    title = getattr(spec, "title", "")
    if title:
        plan.title_pt = fit_single(title, geo.inner_width, 0.5, TITLE_SIZES, "제목")
    message = getattr(spec, "message", "")
    if message:
        box = geo.message_box()
        plan.message_pt = fit_single(message, box.width, box.height, MESSAGE_SIZES, "헤드 메시지")
    return plan


def column_boxes(geo: Geometry, has_message: bool, n: int) -> list[Box]:
    body = geo.body_box(has_message)
    width = (body.width - COLUMN_GAP * (n - 1)) / n
    return [Box(body.left + i * (width + COLUMN_GAP), body.top, width, body.height) for i in range(n)]


MIN_CARD_H = 1.5


def fitted_height(box: Box, bullets: list[str], pt: int, header: float = CARD_HEADER_H) -> float:
    """카드 내용에 맞춘 높이. 내용이 적으면 영역 아래를 비워 두되 너무 작아지지 않게 한다."""
    need = header + 2 * CARD_PAD + bullets_height(bullets, box.width - 2 * CARD_PAD, pt) + 0.1
    return min(box.height, max(MIN_CARD_H, need))


def card_inner(box: Box) -> Box:
    return Box(
        box.left + CARD_PAD,
        box.top + CARD_HEADER_H + CARD_PAD,
        box.width - 2 * CARD_PAD,
        box.height - CARD_HEADER_H - 2 * CARD_PAD,
    )


def table_row_heights(rows: list[list[str]], widths: list[float], pt: float) -> list[float]:
    pad = 0.1  # 셀 위아래 여백 합
    heights = []
    for row in rows:
        lines = max(line_count(cell or " ", w - 0.12, pt) for cell, w in zip(row, widths))
        heights.append(lines * pt * LINE_SPACING / 72 + pad)
    return heights


def table_widths(spec_widths: list[float] | None, n: int, total: float) -> list[float]:
    ratios = spec_widths if spec_widths and len(spec_widths) == n and all(w > 0 for w in spec_widths) else [1] * n
    s = sum(ratios)
    return [total * r / s for r in ratios]


def process_boxes(geo: Geometry, has_message: bool, n: int) -> tuple[list[Box], list[Box]]:
    body = geo.body_box(has_message)
    gap = 0.08
    width = (body.width - gap * (n - 1)) / n
    chevron_h = 0.62
    chevrons = [Box(body.left + i * (width + gap), body.top, width, chevron_h) for i in range(n)]
    details_top = body.top + chevron_h + 0.12
    details = [
        Box(c.left, details_top, c.width, body.top + body.height - details_top) for c in chevrons
    ]
    return chevrons, details


def plan_slide(spec, geo: Geometry) -> Plan:
    """슬라이드 명세를 배치해 보고 글자 크기를 정한다. 넘치면 FitError."""
    kind = spec.kind
    if kind in ("cover", "closing"):
        return Plan()
    if kind == "section":
        return Plan(title_pt=fit_single(spec.title, geo.width - 3.7, 1.0, (26, 22, 18), "장 제목"))

    plan = _title_and_message(spec, geo)
    has_message = bool(getattr(spec, "message", ""))
    body = geo.body_box(has_message)

    if kind == "agenda":
        cols = 1 if len(spec.items) <= 5 else 2
        per_col = math.ceil(len(spec.items) / cols)
        col_w = (body.width - COLUMN_GAP * (cols - 1)) / cols
        plan.body_pt = fit_single(max(spec.items, key=len), col_w - 0.7, 0.45, (14, 12, 11), "목차 항목")
        plan.extra = {"per_col": per_col, "cols": cols}
    elif kind == "bullets":
        plan.body_pt = fit_bullets(spec.bullets, body.width - 0.1, body.height)
    elif kind in ("two_column", "cards"):
        columns = [spec.left, spec.right] if kind == "two_column" else spec.cards
        boxes = column_boxes(geo, has_message, len(columns))
        sizes = []
        for i, (col, box) in enumerate(zip(columns, boxes), 1):
            inner = card_inner(box)
            fit_single(col.heading, box.width - 0.16, CARD_HEADER_H, (11, 10, 9), f"{i}번째 제목")
            sizes.append(fit_bullets(col.bullets, inner.width, inner.height, what=f"{i}번째 영역"))
        plan.body_pt = min(sizes)
    elif kind == "table":
        n = len(spec.columns)
        bad = [i for i, row in enumerate(spec.rows, 1) if len(row) != n]
        if bad:
            raise FitError(f"표의 {bad}번째 행의 셀 수가 열 수({n})와 다릅니다.")
        widths = table_widths(spec.column_widths, n, body.width)
        for pt in TABLE_SIZES:
            heights = table_row_heights([spec.columns] + spec.rows, widths, pt)
            if sum(heights) <= body.height:
                plan.body_pt = pt
                break
        else:
            need = sum(table_row_heights([spec.columns] + spec.rows, widths, TABLE_SIZES[-1]))
            raise FitError(
                f"표가 영역을 넘칩니다(필요 {need:.1f}in / 가능 {body.height:.1f}in). "
                "행을 나눠 여러 슬라이드로 만들거나 셀 문장을 줄이세요."
            )
        plan.extra = {"widths": widths}
    elif kind == "process":
        chevrons, details = process_boxes(geo, has_message, len(spec.steps))
        plan.extra = {"step_pt": [
            fit_single(step.name, c.width - 0.4, 0.34, (10, 9, 8), "단계명") for step, c in zip(spec.steps, chevrons)
        ]}
        sizes = [
            fit_bullets(step.bullets, d.width - 0.16, d.height - 0.16, sizes=(10, 9, 8), what=f"'{step.name}' 단계")
            for step, d in zip(spec.steps, details)
            if step.bullets
        ]
        plan.body_pt = min(sizes) if sizes else 10
    elif kind == "headline":
        plan.title_pt = fit_single(spec.title, 3.7, 2.2, (24, 22, 20, 18), "헤드라인")
        plan.body_pt = fit_bullets(spec.bullets, geo.width - 4.7 - geo.margin_x, geo.height - 1.1, sizes=(14, 13, 12, 11, 10))
    return plan
