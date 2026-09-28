from rfp_agent.tools import NO_ANSWER, build_tools


def _tools(ws):
    return {t.name: t for t in build_tools(ws)}


def test_ask_user_collects_answers_and_marks_skipped(make_workspace):
    ws = make_workspace(answers=["3억 원", ""])
    result = _tools(ws)["ask_user"].call({"questions": ["예산은?", "일정은?"]})

    assert "Q1. 예산은?\nA1. 3억 원" in result
    assert f"A2. {NO_ANSWER}" in result
    assert len(ws.io.prompts) == 2


def test_ask_user_in_auto_mode_does_not_prompt(make_workspace):
    ws = make_workspace(interactive=False)
    result = _tools(ws)["ask_user"].call({"questions": ["예산은?"]})
    assert NO_ANSWER in result
    assert ws.io.prompts == []


def test_write_section_autosaves_and_finalize_marks_done(make_workspace):
    ws = make_workspace()
    tools = _tools(ws)
    tools["set_document_info"].call({"title": "스마트 민원 플랫폼 구축", "issuer": "○○시"})
    tools["write_section"].call({"section_id": "overview", "content": "사업 개요 본문"})

    path = ws.path()
    assert path.name == "스마트-민원-플랫폼-구축.md"
    assert "사업 개요 본문" in path.read_text(encoding="utf-8")
    assert not ws.finalized

    assert "최종본 저장 완료" in tools["finalize"].call({})
    assert ws.finalized


def test_write_section_reports_validation_error(make_workspace):
    ws = make_workspace()
    assert _tools(ws)["write_section"].call({"section_id": "overview", "content": " "}).startswith("오류")


def test_read_section_and_finalize_without_sections(make_workspace):
    ws = make_workspace()
    tools = _tools(ws)
    assert "없습니다" in tools["read_section"].call({"section_id": "overview"})
    assert tools["finalize"].call({}).startswith("오류")
    assert not ws.finalized
