"""모의 HTTP 응답으로 도구 실행 루프 전체를 검증한다(API 키 불필요)."""

from __future__ import annotations

import json

import anthropic
import httpx2
from anthropic import DefaultHttpxClient

from rfp_agent.agent import FALLBACK_BETA, RFPAgent


def _message(i: int, content: list[dict], stop_reason: str) -> dict:
    return {
        "id": f"msg_{i}",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 10},
    }


def _tool_use(i: int, name: str, tool_input: dict) -> dict:
    return {"type": "tool_use", "id": f"toolu_{i}", "name": name, "input": tool_input}


SCRIPT = [
    _message(1, [
        {"type": "text", "text": "몇 가지 확인하겠습니다."},
        _tool_use(1, "set_document_info", {"title": "사내 포털 개편", "issuer": "㈜예시"}),
        _tool_use(2, "ask_user", {"questions": ["예산 범위는?", "희망 오픈 일정은?"]}),
    ], "tool_use"),
    _message(2, [_tool_use(3, "write_section", {"section_id": "overview", "content": "### 배경\n노후 포털 개편"})], "tool_use"),
    _message(3, [_tool_use(4, "write_section", {
        "section_id": "functional_requirements",
        "content": "| ID | 요구사항명 |\n|---|---|\n| FR-001 | 통합 검색 |",
    })], "tool_use"),
    _message(4, [_tool_use(5, "finalize", {})], "tool_use"),
    _message(5, [{"type": "text", "text": "완성했습니다. [가정] 일정은 6개월로 가정했습니다."}], "end_turn"),
    # 두 번째 사용자 턴(수정 요청)
    _message(6, [_tool_use(6, "write_section", {"section_id": "overview", "content": "### 배경\n수정된 개요"})], "tool_use"),
    _message(7, [{"type": "text", "text": "개요를 수정했습니다."}], "end_turn"),
]


def _mock_client(requests: list[httpx2.Request]) -> anthropic.Anthropic:
    responses = iter(SCRIPT)

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json=next(responses))

    return anthropic.Anthropic(
        api_key="test-key",
        http_client=DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
        max_retries=0,
    )


def test_full_conversation_writes_document_and_keeps_history(make_workspace):
    requests: list[httpx2.Request] = []
    ws = make_workspace(answers=["2억 원", ""])
    agent = RFPAgent(ws, client=_mock_client(requests))

    agent.send("사내 포털 개편 RFP를 만들어 주세요.")

    assert ws.finalized
    saved = ws.path().read_text(encoding="utf-8")
    assert saved.startswith("# 사내 포털 개편")
    assert "노후 포털 개편" in saved and "FR-001" in saved
    assert "몇 가지 확인하겠습니다." in ws.io.said
    assert len(ws.io.prompts) == 2  # ask_user 질문 두 개

    bodies = [json.loads(r.content) for r in requests]
    first = bodies[0]
    assert first["model"] == "claude-opus-5"
    assert first["fallbacks"] == "default"
    assert first["thinking"] == {"type": "adaptive"}
    assert first["output_config"] == {"effort": "high"}
    assert FALLBACK_BETA in requests[0].headers["anthropic-beta"]
    assert {t["name"] for t in first["tools"]} == {
        "ask_user", "set_document_info", "write_section", "get_outline", "read_section", "finalize",
    }

    # 사용자의 답변이 도구 결과로 모델에 전달되었는지
    tool_results = bodies[1]["messages"][-1]["content"]
    ask_result = next(r for r in tool_results if r["tool_use_id"] == "toolu_2")
    assert "A1. 2억 원" in ask_result["content"]

    agent.send("개요를 좀 더 구체적으로 바꿔 주세요.")
    bodies = [json.loads(r.content) for r in requests]
    assert len(bodies) == 7

    # 다음 턴 요청은 직전 요청 + 직전 응답 + 새 사용자 메시지여야 한다(기록을 덧붙이기만 함).
    last_of_turn_one, first_of_turn_two = bodies[4]["messages"], bodies[5]["messages"]
    assert first_of_turn_two[: len(last_of_turn_one)] == last_of_turn_one
    assert first_of_turn_two[len(last_of_turn_one)] == {
        "role": "assistant",
        "content": [{"type": "text", "text": "완성했습니다. [가정] 일정은 6개월로 가정했습니다."}],
    }
    assert first_of_turn_two[-1] == {"role": "user", "content": "개요를 좀 더 구체적으로 바꿔 주세요."}
    assert len(first_of_turn_two) == len(last_of_turn_one) + 2
    assert "수정된 개요" in ws.path().read_text(encoding="utf-8")


def test_refusal_is_reported(make_workspace):
    refusal = _message(1, [], "refusal")

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=refusal)

    client = anthropic.Anthropic(
        api_key="test-key",
        http_client=DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
        max_retries=0,
    )
    ws = make_workspace()
    RFPAgent(ws, client=client).send("안녕")
    assert any("거절" in s for s in ws.io.said)
