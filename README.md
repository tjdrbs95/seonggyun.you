# RFP · 제안서 작성 에이전트

이 저장소에는 Claude 기반 에이전트가 두 개 있습니다.

| 에이전트 | 하는 일 | 결과물 |
|---|---|---|
| [**RFP 작성 에이전트**](#rfp-작성-에이전트) (`rfp_agent/`) | 발주자 입장에서 제안요청서(RFP) 작성 | 마크다운 RFP |
| [**Workday 제안서 에이전트**](#workday-제안서-에이전트) (`proposal_agent/`) | 공급사 입장에서 RFP에 대응하는 제안서 작성 | Workday 템플릿 PPTX + 요구사항 대응표 CSV |

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export ANTHROPIC_API_KEY=sk-ant-...
```

---

# Workday 제안서 에이전트

고객 RFP와 Workday 솔루션 자료를 넣으면, RFP 요구사항을 하나하나 추적하면서 **Workday Corporate PowerPoint Template** 디자인 그대로 제안서를 만들어 줍니다.

1. **RFP 분석** — 요구사항, 제안서 작성 지침(필수 목차), 평가 항목·배점을 파악하고 요구사항을 ID별로 등록
2. **대응 판단** — 요구사항마다 대응 유형(표준 기능 / 설정 / 확장(Extend) / 연동 / 파트너 솔루션 / 로드맵 / 미지원 / 확인 필요)과 대응 방안을 기록. 솔루션 자료로 확인되지 않으면 `확인 필요`로 남기고, 로드맵 기능을 현재 기능처럼 쓰지 않음
3. **추가 질문** — 제안사명, 수행 실적, 투입 인력, 라이선스 범위처럼 자료에 없는 정보만 묶어서 질문
4. **슬라이드 작성** — RFP가 지정한 목차(없으면 기본 목차)로 표지 → 목차 → 장별 슬라이드 → 마무리. 모든 슬라이드에 헤드 메시지, 대응 요구사항 ID, 발표자 노트
5. **검토·저장** — 모든 요구사항이 어느 슬라이드에서 다뤄졌는지 확인 후 저장. 부록에 **요구사항 대응표**(ID · 요구사항 · 대응 유형 · 대응 방안 · 페이지)를 자동으로 붙임

### 준비: 템플릿

Workday Corporate PowerPoint Template(Drive `Workday Presales` 폴더)을 `templates/workday_template.pptx` 로 저장하세요. 회사 문서이므로 git에는 올라가지 않습니다. 다른 디자인은 `-t 다른템플릿.pptx` 로 지정하면 그 템플릿의 레이아웃·테마 색·글꼴을 따라갑니다.

### 실행

```bash
# RFP + Workday 솔루션 자료 폴더
python -m proposal_agent rfp/○○그룹_RFP.pdf -k knowledge/

# 요구사항 목록이 엑셀로 따로 있는 경우, 참고 자료와 추가 지시까지
python -m proposal_agent rfp/본문.pdf rfp/요구사항.xlsx -k knowledge/ \
    -r refs/회사소개.pptx -b "제안사: 메가존클라우드, 1차 범위는 Core HCM + 보상"

# 질문 없이 초안만 (모르는 정보는 [확인 필요])
python -m proposal_agent rfp/rfp.pdf -k knowledge/ --auto
```

결과물(`output/`):

| 파일 | 내용 |
|---|---|
| `<제안서제목>.pptx` | Workday 템플릿으로 만든 제안서 (부록 요구사항 대응표 포함) |
| `<제안서제목>_요구사항대응표.csv` | 요구사항별 대응 유형·방안·제안서 페이지 (엑셀에서 바로 열림) |
| `<제안서제목>.deck.json` | 슬라이드 내용. 템플릿만 바꿔 다시 그릴 때 사용 |

완성 후에도 "3장 헤드 메시지를 더 강하게", "보안 요구사항 장표를 표로 바꿔줘" 처럼 이어서 수정할 수 있습니다.

```bash
# 모델 호출 없이 템플릿만 바꿔 다시 렌더링
python -m proposal_agent --render output/제안서.deck.json -t templates/다른템플릿.pptx
```

### 입력 형식

| 형식 | 처리 |
|---|---|
| PDF | 원본 그대로 Claude에 전달(표·이미지 포함 인식). 합계 24MB 이하 |
| DOCX / PPTX / XLSX | 본문·표·노트 텍스트를 추출 |
| MD / TXT / CSV | 그대로 |
| HWP | 지원 안 함 → PDF로 변환해서 넣으세요 |

### 슬라이드 형식

템플릿 레이아웃을 그대로 쓰고(표지 `Title Slide`, 본문 `Title Only`, 장 구분 `Section Title`, 강조 `1/2_Headline`, 마무리 `Bumper Slide`), 본문 도형은 템플릿 예시 장표의 서식(맑은 고딕, 제목 18pt 네이비, 본문 9~12pt, 네이비 박스 `#1F497D`, 옅은 청록 테두리 박스, `Workday Confidential` 푸터)을 따릅니다.

| kind | 용도 |
|---|---|
| `cover` / `closing` | 표지 / 마무리 |
| `agenda` | 목차(번호 박스) |
| `section` | 장 구분 |
| `headline` | 왼쪽 큰 메시지 + 오른쪽 설명 |
| `bullets` | 헤드 메시지 + 글머리 |
| `two_column` | As-Is / To-Be 같은 비교 |
| `cards` | 특장점 2~4개 |
| `table` | 요구사항·인력·일정 표 |
| `process` | 방법론 단계·일정(쉐브론) |

글이 영역을 넘치면 도구가 오류를 돌려주고, 에이전트가 문장을 줄이거나 슬라이드를 나눕니다.

### 구조

```
proposal_agent/
  cli.py      명령줄, 입력 파일 로딩
  inputs.py   PDF/DOCX/PPTX/XLSX → Claude document 블록
  deck.py     슬라이드 명세(pydantic), RFP 요구사항과 대응 현황, 저장/불러오기
  layout.py   영역 계산과 글자 크기 맞춤(넘침 검사)
  render.py   템플릿 위에 슬라이드 그리기, 부록 대응표
  tools.py    에이전트 도구(register_requirements, set_requirement_responses, add_slide, replace_slide …)
  prompts.py  Workday 제안서 작성 원칙
agent_core/   두 에이전트가 함께 쓰는 도구 실행 루프·입출력
```

---

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

두 에이전트 모두 모의 HTTP 응답으로 테스트하므로 API 키와 Workday 템플릿 없이 실행됩니다.

## B. Claude Code 서브에이전트

이 저장소를 Claude Code로 열고 다음처럼 요청하면 `rfp-writer` 서브에이전트가 같은 방식으로 RFP를 `output/` 에 작성합니다.

```
rfp-writer 에이전트로 ○○공단 홈페이지 리뉴얼 RFP 만들어줘
```

다른 프로젝트에서도 쓰려면 `.claude/agents/rfp-writer.md` 를 `~/.claude/agents/` 에 복사하세요.
