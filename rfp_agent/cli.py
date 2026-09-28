"""명령줄 진입점: python -m rfp_agent"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from agent_core.cli import run_session
from agent_core.console import ConsoleIO, read_multiline

from .agent import DEFAULT_EFFORT, DEFAULT_MODEL, RFPAgent
from .document import RFPDocument
from .tools import Workspace

# 참고 자료가 이보다 크면 경고만 하고 그대로 전달한다(모델 컨텍스트는 1M 토큰).
LARGE_REFERENCE_CHARS = 200_000


def build_first_message(brief: str, references: list[Path]) -> str:
    parts = [f"다음 사업에 대한 RFP를 작성해 주세요.\n\n<brief>\n{brief.strip()}\n</brief>"]
    for path in references:
        text = path.read_text(encoding="utf-8")
        if len(text) > LARGE_REFERENCE_CHARS:
            print(f"[경고] 참고 자료가 큽니다: {path} ({len(text):,}자)", file=sys.stderr)
        parts.append(f'<reference file="{path.name}">\n{text}\n</reference>')
    return "\n\n".join(parts)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="rfp-agent",
        description="대화형으로 요구사항을 수집해 제안요청서(RFP)를 작성하는 Claude 에이전트",
    )
    parser.add_argument("brief", nargs="?", help="사업 개요 한두 문장. 생략하면 실행 후 입력받습니다.")
    parser.add_argument(
        "-r", "--reference", action="append", type=Path, default=[],
        help="참고 자료 텍스트/마크다운 파일(여러 번 지정 가능). 예: 회의록, 기존 요구사항 정의서",
    )
    parser.add_argument("-o", "--output", type=Path, help="결과 파일 경로(.md). 기본값: output/<문서제목>.md")
    parser.add_argument("--output-dir", type=Path, default=Path("output"), help="결과 저장 폴더 (기본: output)")
    parser.add_argument(
        "--auto", action="store_true",
        help="질문 없이 한 번에 작성합니다. 부족한 정보는 [가정]으로 표시됩니다.",
    )
    parser.add_argument("--model", default=os.environ.get("RFP_AGENT_MODEL", DEFAULT_MODEL))
    parser.add_argument(
        "--effort", default=os.environ.get("RFP_AGENT_EFFORT", DEFAULT_EFFORT),
        choices=["low", "medium", "high", "xhigh", "max"],
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    io = ConsoleIO()

    for path in args.reference:
        if not path.is_file():
            print(f"참고 자료 파일을 찾을 수 없습니다: {path}", file=sys.stderr)
            return 2

    brief = args.brief or read_multiline(
        io, "어떤 사업의 RFP를 만들까요? 목적·대상·대략적인 범위를 자유롭게 적어 주세요. (빈 줄 입력 시 완료)"
    )
    if not brief.strip():
        print("사업 설명이 비어 있어 종료합니다.", file=sys.stderr)
        return 2

    workspace = Workspace(
        document=RFPDocument(),
        output_dir=args.output_dir,
        io=io,
        interactive=not args.auto,
        output_path=args.output,
    )
    agent = RFPAgent(workspace, model=args.model, effort=args.effort)

    def session() -> None:
        agent.send(build_first_message(brief, args.reference))
        while not args.auto:
            if workspace.finalized:
                io.say(f"\n📄 저장 위치: {workspace.path()}")
            request = io.ask("\n수정하거나 추가할 내용을 입력하세요 (엔터만 누르면 종료)\n> ").strip()
            if not request:
                break
            agent.send(request)

    code = run_session(session, io)
    if code:
        return code

    if workspace.document.sections:
        path = workspace.document.save(workspace.path())
        io.say(f"\n완료: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
