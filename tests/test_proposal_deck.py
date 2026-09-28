import pytest

from proposal_agent.deck import SLIDE_ADAPTER, ProposalDeck, Requirement, RequirementResponse
from proposal_agent.layout import FitError, Geometry, plan_slide

from .proposal_fixtures import ALL_KINDS


def spec(d):
    return SLIDE_ADAPTER.validate_python(d)


def test_new_slides_go_before_closing():
    deck = ProposalDeck()
    deck.add(spec({"kind": "cover", "title": "제안서 A"}))
    deck.add(spec({"kind": "closing"}))
    number = deck.add(spec({"kind": "bullets", "title": "본문", "bullets": ["x"]}))
    assert number == 2
    assert [s.kind for s in deck.slides] == ["cover", "bullets", "closing"]
    assert deck.title == "제안서 A"


def test_insert_replace_remove():
    deck = ProposalDeck()
    for d in ALL_KINDS:
        deck.add(spec(d))
    deck.add(spec({"kind": "bullets", "title": "끼워넣기", "bullets": ["x"]}), position=2)
    assert deck.slides[1].title == "끼워넣기"
    deck.replace(2, spec({"kind": "bullets", "title": "교체", "bullets": ["y"]}))
    assert deck.slides[1].title == "교체"
    deck.remove(2)
    assert deck.slides[1].kind == "agenda"
    with pytest.raises(ValueError):
        deck.remove(99)


def test_requirements_coverage_and_rereg_keeps_response():
    deck = ProposalDeck()
    for d in ALL_KINDS:
        deck.add(spec(d))
    deck.register([Requirement(id="SFR-001", text="통합"), Requirement(id="SFR-009", text="급여")])
    assert deck.respond([RequirementResponse(id="SFR-001", status="standard", response="표준")]) == []
    assert deck.respond([RequirementResponse(id="X", status="tbd", response="")]) == ["X"]

    deck.register([Requirement(id="SFR-001", text="통합(수정)")])
    assert deck.requirements["SFR-001"].status == "standard"
    assert deck.requirements["SFR-001"].text == "통합(수정)"

    assert deck.pages_for("SFR-001") == [4, 5]
    cov = deck.coverage()
    assert cov["no_slide"] == ["SFR-009"]
    assert cov["no_response"] == ["SFR-009"]
    assert "SFR-009" in deck.outline()


def test_state_roundtrip():
    deck = ProposalDeck()
    for d in ALL_KINDS:
        deck.add(spec(d))
    deck.register([Requirement(id="SFR-001", text="통합", status="standard", response="표준")])
    restored = ProposalDeck.from_state(deck.to_state())
    assert restored.to_state() == deck.to_state()


def test_invalid_spec_rejected():
    with pytest.raises(Exception):
        spec({"kind": "cards", "title": "x", "cards": [{"heading": "only one", "bullets": ["a"]}]})
    with pytest.raises(Exception):
        spec({"kind": "bullets", "title": "x", "bullets": ["a"], "unknown": 1})


def test_all_kinds_fit_on_workday_geometry():
    for d in ALL_KINDS:
        plan_slide(spec(d), Geometry())


def test_overflow_raises_fit_error():
    long = "통합 인사 데이터 모델을 기반으로 모든 계열사의 조직·인사·보상 정보를 단일 화면에서 관리하고 분석할 수 있음" * 2
    with pytest.raises(FitError, match="넘칩니다"):
        plan_slide(spec({"kind": "bullets", "title": "x", "bullets": [long * 2] * 12}), Geometry())


def test_table_cell_count_mismatch():
    with pytest.raises(FitError, match="셀 수"):
        plan_slide(spec({"kind": "table", "title": "t", "columns": ["a", "b"], "rows": [["1"]]}), Geometry())
