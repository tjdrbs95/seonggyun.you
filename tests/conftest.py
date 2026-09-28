from __future__ import annotations

from pathlib import Path

import pytest

from rfp_agent.document import RFPDocument
from rfp_agent.tools import Workspace


class ScriptedIO:
    """미리 정한 답변을 순서대로 돌려주고, 출력은 기록한다."""

    def __init__(self, answers: list[str] | None = None) -> None:
        self.answers = list(answers or [])
        self.prompts: list[str] = []
        self.said: list[str] = []

    def say(self, text: str) -> None:
        self.said.append(text)

    def ask(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answers.pop(0) if self.answers else ""


@pytest.fixture
def make_workspace(tmp_path: Path):
    def _make(answers: list[str] | None = None, interactive: bool = True) -> Workspace:
        return Workspace(
            document=RFPDocument(),
            output_dir=tmp_path / "output",
            io=ScriptedIO(answers),
            interactive=interactive,
        )

    return _make
