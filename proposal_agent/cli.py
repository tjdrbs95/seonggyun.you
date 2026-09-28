"""명령줄 진입점: python -m proposal_agent"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from agent_core import DEFAULT_EFFORT, DEFAULT_MODEL
from agent_core.cli import run_session
from agent_core.console import ConsoleIO

from .agent import ProposalAgent
from .deck import ProposalDeck
from .inputs import InputError, build_blocks, collect_files
from .render import DeckRenderer
from .tools import Workspace

DEFAULT_TEMPLATE = Path("templates/workday_template.pptx")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="proposal-agent",
        description="RFP에 대응하는 Workday 제안서(PPTX)를 템플릿에 맞춰 작성하는 Claude 에이전트",
    )
    parser.add_argument("rfp", nargs="*", type=Path, help="RFP 파일(PDF, DOCX, XLSX, PPTX, MD). 여러 개 가능")
    parser.add_argument(
        "-k", "--knowledge", action="append", type=Path, default=[],
        help="Workday 솔루션 자료 파일 또는 폴더(여러 번 지정 가능)",
    )
    parser.add_argument(
        "-r", "--reference", action="append", type=Path, default=[],
        help="참고 자료(제안사 소개, 과거 제안서, 회의록 등) 파일 또는 폴더",
    )
    parser.add_argument("-b", "--brief", default="", help="추가 지시. 예: '제안사: ○○, 1차 범위는 Core HCM'")
    parser.add_argument("-t", "--template", type=Path, default=DEFAULT_TEMPLATE,
                        help=f"PowerPoint 템플릿(.pptx). 기본: {DEFAULT_TEMPLATE}")
    parser.add_argument("-o", "--output", type=Path, help="결과 파일 경로(.pptx). 기본: output/<제안서제목>.pptx")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--auto", action="store_true", help="질문 없이 작성합니다. 모르는 정보는 [확인 필요]로 남습니다.")
    parser.add_argument(
        "--render", type=Path, metavar="DECK_JSON",
        help="에이전트 없이 저장된 덱(.deck.json)을 템플릿으로 다시 렌더링합니다.",
    )
    parser.add_argument("--model", default=os.environ.get("PROPOSAL_AGENT_MODEL", DEFAULT_MODEL))
    parser.add_argument(
        "--effort", default=os.environ.get("PROPOSAL_AGENT_EFFORT", DEFAULT_EFFORT),
        choices=["low", "medium", "high", "xhigh", "max"],
    )
    return parser.parse_args(argv)


def build_first_message(blocks: list[dict], brief: str) -> list[dict]:
    text = "첨부한 RFP에 대응하는 Workday 제안서를 작성해 주세요."
    if brief.strip():
        text += f"\n\n<instructions>\n{brief.strip()}\n</instructions>"
    return [*blocks, {"type": "text", "text": text}]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    io = ConsoleIO()

    if not args.template.is_file():
        print(
            f"템플릿 파일이 없습니다: {args.template}\n"
            "Workday Corporate PowerPoint Template을 templates/workday_template.pptx로 저장하거나 -t로 지정하세요.",
            file=sys.stderr,
        )
        return 2
    renderer = DeckRenderer(args.template)

    if args.render:
        deck = ProposalDeck.from_state(json.loads(args.render.read_text(encoding="utf-8")))
        out = args.output or args.render.with_name(args.render.name.replace(".deck.json", ".pptx"))
        slides = renderer.render(deck, out)
        io.say(f"완료: {out} ({len(slides)}장)")
        return 0

    if not args.rfp:
        print("RFP 파일을 지정하세요. 예: python -m proposal_agent rfp.pdf -k knowledge/", file=sys.stderr)
        return 2
    try:
        blocks = build_blocks([
            ("RFP", collect_files(args.rfp)),
            ("Workday 솔루션 자료", collect_files(args.knowledge)),
            ("참고 자료", collect_files(args.reference)),
        ])
    except InputError as e:
        print(e, file=sys.stderr)
        return 2
    io.say(f"입력 문서 {len(blocks)}건을 읽었습니다. 제안서 작성을 시작합니다.")

    workspace = Workspace(
        deck=ProposalDeck(),
        renderer=renderer,
        output_dir=args.output_dir,
        io=io,
        interactive=not args.auto,
        output_path=args.output,
    )
    agent = ProposalAgent(workspace, model=args.model, effort=args.effort)

    def session() -> None:
        agent.send(build_first_message(blocks, args.brief))
        while not args.auto:
            if workspace.finalized:
                io.say(f"\n📊 제안서: {workspace.path()}\n📋 대응표: {workspace.matrix_path()}")
            request = io.ask("\n수정하거나 추가할 내용을 입력하세요 (엔터만 누르면 종료)\n> ").strip()
            if not request:
                break
            agent.send(request)

    code = run_session(session, io)
    if workspace.deck.slides:
        # 마지막 수정이나 중간에 멈춘 결과까지 저장한다.
        workspace.export()
        io.say(f"\n저장: {workspace.path()}")
    return code


if __name__ == "__main__":
    sys.exit(main())
