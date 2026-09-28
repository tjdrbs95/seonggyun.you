# RFP 작성 에이전트

사업 개요 몇 줄만 입력하면 필요한 정보를 질문으로 수집해 **제안요청서(RFP)** 를 마크다운 문서로 작성해 주는 Claude 에이전트입니다.

- 부족한 정보(예산, 일정, 사용자 규모, 연동 시스템, 보안 요건 등)는 에이전트가 묶어서 질문합니다. 모르는 항목은 엔터로 넘기면 합리적으로 가정하고 본문에 `[가정]` 으로 표시합니다.
- 표준 목차(사업 개요 → 요구사항 → 일정·산출물 → 평가 기준 → 제출 안내)에 따라 섹션별로 작성하고, 요구사항에 `FR-001`, `SEC-001` 같은 ID를 붙입니다.
- 작성 후 섹션 간 일정·예산·요구사항이 서로 맞는지 스스로 검토합니다.
- 완성 후에도 "평가 기준에서 가격 비중을 30%로 바꿔줘"처럼 수정 요청을 이어서 할 수 있습니다.

사용 방법은 두 가지입니다.

| 방법 | 필요한 것 | 적합한 경우 |
|---|---|---|
| A. Python CLI (`rfp_agent/`) | Anthropic API 키 | 터미널에서 독립 실행, 다른 시스템에 붙이기 |
| B. Claude Code 서브에이전트 (`.claude/agents/rfp-writer.md`) | Claude Code | 이 저장소를 Claude Code로 열어 대화로 작성 |

## A. Python CLI

### 설치

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export ANTHROPIC_API_KEY=sk-ant-...
```

### 실행

```bash
# 대화형: 질문에 답하며 작성
python -m rfp_agent "○○시 스마트 민원 상담 챗봇 구축. 시민 대상, 기존 민원 시스템과 연동 필요"

# 참고 자료(회의록, 기존 요구사항 정의서 등 텍스트/마크다운)를 함께 전달
python -m rfp_agent "사내 그룹웨어 교체" -r notes/meeting.md -r notes/current_system.md

# 질문 없이 한 번에 초안 작성 (부족한 정보는 [가정] 표시)
python -m rfp_agent --auto "물류 창고 WMS 고도화" -o output/wms-rfp.md
```

`pip install -e .` 후에는 `rfp-agent` 명령으로도 실행할 수 있습니다. 결과는 기본적으로 `output/<문서제목>.md` 에 저장되며, 섹션을 하나 쓸 때마다 자동 저장됩니다.

### 옵션

| 옵션 | 설명 |
|---|---|
| `brief` | 사업 개요. 생략하면 실행 후 여러 줄로 입력받습니다(빈 줄로 종료). |
| `-r, --reference` | 참고 자료 파일. 여러 번 지정 가능 |
| `-o, --output` | 결과 파일 경로 |
| `--output-dir` | 결과 폴더 (기본 `output`) |
| `--auto` | 질문 없이 작성 |
| `--model` | 사용할 모델 (기본 `claude-opus-5`, 환경 변수 `RFP_AGENT_MODEL`) |
| `--effort` | 추론 강도 `low`~`max` (기본 `high`, 환경 변수 `RFP_AGENT_EFFORT`). 빠른 초안은 `medium` 도 충분합니다. |

### 구조

```
rfp_agent/
  cli.py        명령줄 진입점, 대화 루프
  agent.py      Claude 도구 실행 루프 (tool runner), 대화 기록 관리
  tools.py      에이전트 도구: ask_user, set_document_info, write_section, get_outline, read_section, finalize
  document.py   RFP 문서 상태, 표준 목차, 마크다운 렌더링
  prompts.py    시스템 프롬프트 (작성 방식과 품질 기준)
tests/          단위 테스트 + 모의 API 응답으로 에이전트 루프 전체 검증
```

목차를 바꾸려면 `document.py` 의 `STANDARD_SECTIONS`, 작성 기준(문체, 요구사항 ID 규칙, 평가 배점 등)을 바꾸려면 `prompts.py` 를 수정하세요.

API 요청에는 적응형 추론(adaptive thinking), 프롬프트 캐싱, 서버 측 폴백(`fallbacks: "default"`, 안전 분류기가 요청을 거절하면 권장 모델로 자동 재시도)이 켜져 있습니다.

### 테스트

```bash
pytest
```

테스트는 모의 HTTP 응답을 사용하므로 API 키 없이 실행됩니다.

## B. Claude Code 서브에이전트

이 저장소를 Claude Code로 열고 다음처럼 요청하면 `rfp-writer` 서브에이전트가 같은 방식으로 RFP를 `output/` 에 작성합니다.

```
rfp-writer 에이전트로 ○○공단 홈페이지 리뉴얼 RFP 만들어줘
```

다른 프로젝트에서도 쓰려면 `.claude/agents/rfp-writer.md` 를 `~/.claude/agents/` 에 복사하세요.
