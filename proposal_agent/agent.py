"""제안서 작성 에이전트: 공용 도구 실행 루프에 제안서 도구와 프롬프트를 붙인다."""

from __future__ import annotations

import anthropic

from agent_core import DEFAULT_EFFORT, DEFAULT_MODEL, ToolAgent

from .prompts import SYSTEM_PROMPT
from .tools import Workspace, build_tools

# 요구사항 등록·대응·슬라이드 수십 장을 만들려면 도구 호출 턴이 많이 필요하다.
MAX_ITERATIONS = 250


class ProposalAgent(ToolAgent):
    def __init__(
        self,
        workspace: Workspace,
        client: anthropic.Anthropic | None = None,
        model: str = DEFAULT_MODEL,
        effort: str = DEFAULT_EFFORT,
    ) -> None:
        self.ws = workspace
        super().__init__(
            io=workspace.io,
            system=SYSTEM_PROMPT,
            tools=build_tools(workspace),
            client=client,
            model=model,
            effort=effort,
            max_iterations=MAX_ITERATIONS,
        )
