"""사용자 입출력과, 사용자에게 질문하는 공용 도구."""

from __future__ import annotations

from typing import Callable, Protocol

from anthropic import beta_tool

NO_ANSWER = "(응답 없음 — 합리적으로 가정하고 본문에 [가정] 표시)"


class UserIO(Protocol):
    def say(self, text: str) -> None: ...

    def ask(self, prompt: str) -> str: ...


class ConsoleIO:
    def say(self, text: str) -> None:
        print(text, flush=True)

    def ask(self, prompt: str) -> str:
        try:
            return input(prompt)
        except EOFError:
            return ""


def read_multiline(io: UserIO, prompt: str) -> str:
    io.say(prompt)
    lines = []
    while True:
        line = io.ask("")
        if not line.strip():
            break
        lines.append(line)
    return "\n".join(lines)


def make_ask_user_tool(io: UserIO, interactive: Callable[[], bool], description: str):
    """질문을 묶어서 사용자에게 묻는 ask_user 도구를 만든다.

    interactive()가 False면 질문하지 않고 '응답 없음'으로 돌려준다(--auto 모드).
    """

    def ask_user(questions: list[str]) -> str:
        questions = [q.strip() for q in questions if q and q.strip()]
        if not questions:
            return "질문이 비어 있습니다."
        if not interactive():
            return "\n".join(f"Q{i}. {q}\nA{i}. {NO_ANSWER}" for i, q in enumerate(questions, 1))

        io.say("\n[추가 정보 요청] 모르는 항목은 엔터로 넘기면 에이전트가 가정해서 작성합니다.")
        lines = []
        for i, q in enumerate(questions, 1):
            answer = io.ask(f"Q{i}. {q}\n> ").strip()
            lines.append(f"Q{i}. {q}\nA{i}. {answer or NO_ANSWER}")
        return "\n".join(lines)

    ask_user.__doc__ = f"""{description}

    Args:
        questions: 사용자에게 물어볼 질문 목록. 각 질문은 한 문장으로 구체적으로 쓴다.
    """
    return beta_tool(ask_user)
