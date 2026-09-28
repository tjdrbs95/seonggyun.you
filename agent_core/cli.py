"""CLI 공통: API 오류를 사용자 메시지로 바꿔 종료 코드를 돌려준다."""

from __future__ import annotations

import sys
from typing import Callable

import anthropic


def run_session(session: Callable[[], None], io) -> int:
    try:
        session()
    except KeyboardInterrupt:
        io.say("\n중단했습니다.")
    except anthropic.AuthenticationError:
        print("인증 실패: ANTHROPIC_API_KEY 환경 변수를 확인하세요.", file=sys.stderr)
        return 1
    except anthropic.APIStatusError as e:
        print(f"API 오류 ({e.status_code}): {e.message}", file=sys.stderr)
        return 1
    except anthropic.APIConnectionError:
        print("네트워크 오류: Claude API에 연결할 수 없습니다.", file=sys.stderr)
        return 1
    except TypeError as e:
        # 자격 증명이 전혀 없으면 SDK가 요청 직전에 TypeError를 낸다.
        if "authentication method" not in str(e):
            raise
        print("API 키가 없습니다: ANTHROPIC_API_KEY 환경 변수를 설정하세요.", file=sys.stderr)
        return 1
    return 0
