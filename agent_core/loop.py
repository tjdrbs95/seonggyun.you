"""Claude 도구 실행 루프(tool runner)로 한 사용자 턴을 끝까지 처리한다."""

from __future__ import annotations

from typing import Any

import anthropic

from .console import UserIO

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_EFFORT = "high"
# 안전 분류기가 요청을 거절하면 서버가 권장 모델로 자동 재시도한다.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOKENS = 16000
MAX_ITERATIONS = 120


class ToolAgent:
    def __init__(
        self,
        io: UserIO,
        system: str,
        tools: list,
        client: anthropic.Anthropic | None = None,
        model: str = DEFAULT_MODEL,
        effort: str = DEFAULT_EFFORT,
        max_iterations: int = MAX_ITERATIONS,
    ) -> None:
        self.io = io
        self.max_iterations = max_iterations
        self.system = system
        self.tools = tools
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.effort = effort
        # 대화 기록은 덧붙이기만 한다(이전 턴을 수정하지 않음).
        self.messages: list[dict[str, Any]] = []

    def send(self, user_content: str | list[dict[str, Any]]) -> None:
        """사용자 메시지 하나를 보내고, 에이전트가 턴을 끝낼 때까지 도구 호출을 처리한다."""
        self.messages.append({"role": "user", "content": user_content})
        runner = self.client.beta.messages.tool_runner(
            model=self.model,
            max_tokens=MAX_TOKENS,
            max_iterations=self.max_iterations,
            system=self.system,
            tools=self.tools,
            messages=self.messages,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            cache_control={"type": "ephemeral"},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )

        last = None
        for message in runner:
            last = message
            self.messages.append(_echoable(message.to_param()))
            for block in message.content:
                if block.type == "text" and block.text.strip():
                    self.io.say(block.text)
            # 도구를 실행하고(결과는 runner가 캐시해 다음 요청에 재사용) 기록에도 남긴다.
            tool_response = runner.generate_tool_call_response()
            if tool_response is not None:
                self.messages.append(tool_response)

        if last is None:
            return
        if last.stop_reason == "refusal":
            self.io.say("\n[알림] 모델이 요청 처리를 거절했습니다. 요청 내용을 바꿔 다시 시도해 주세요.")
        elif last.stop_reason == "max_tokens":
            self.io.say("\n[알림] 응답이 길이 제한에 걸려 중단되었습니다. '계속'이라고 입력하면 이어서 작성합니다.")


def _echoable(message: dict[str, Any]) -> dict[str, Any]:
    """폴백이 출력 도중 일어난 경우, 마지막 fallback 블록 이전에서는 text 블록만 되돌려 보낸다."""
    content = list(message["content"])
    fallback_indexes = [i for i, block in enumerate(content) if block.type == "fallback"]
    if not fallback_indexes:
        return message
    last = fallback_indexes[-1]
    kept = [b for b in content[:last] if b.type == "text"] + content[last:]
    return {**message, "content": kept}
