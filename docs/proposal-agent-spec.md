# Workday RFP Proposal Agent — Specification

> **For the receiving Claude.** This document describes an agent that answers a customer RFP (request for proposal) with a Workday proposal deck (PowerPoint). Use it to reproduce, run or extend the agent. A reference implementation exists in `github.com/tjdrbs95/seonggyun.you`, branch `claude/rfp-creation-agent-p4pqo8` (Python). If you can read that repository, treat the code as the source of truth and this spec as the explanation. If you cannot, this spec has enough detail to rebuild it. Where the two disagree, the code wins.

---

## 1. Purpose

A Workday presales consultant receives an RFP from a Korean customer and must return a proposal deck that:

1. addresses **every** RFP requirement and makes the mapping traceable (requirement ID → slide),
2. is grounded in Workday solution material (official Workday proposal documents, product data sheets), not invented claims,
3. follows the **Workday Corporate PowerPoint Template** design,
4. is written in Korean business-proposal style.

The agent does the analysis and drafting. A human reviews the output before submission; the agent is a drafting tool, not an autonomous submitter.

## 2. Users and usage

- **User:** Workday presales / solution consultant (Korean-speaking).
- **Interface:** command-line tool, interactive by default.
- **Typical run:**

  ```bash
  python -m proposal_agent rfp/Customer_RFP.pdf -b "Proposer: <partner>, scope: Core HCM + Compensation"
  ```

  1. The agent reads the RFP and the solution material.
  2. It asks the user a few batched questions (only for facts the material cannot supply).
  3. It builds the deck, then accepts free-text revision requests ("turn the security slide into a table") until the user presses Enter on an empty line.

## 3. Inputs

| Input | Flag | Handling |
|---|---|---|
| RFP files (one or more) | positional | PDF is sent to Claude **natively** (base64 document block) so tables and layout survive. DOCX/XLSX/PPTX/MD/TXT/CSV are text-extracted. HWP is rejected with "convert to PDF". |
| Workday solution material | `-k PATH` (file or folder, repeatable). Defaults to `./knowledge/` if it exists. | PDFs are **text-extracted per page with `[p.N]` markers** (pypdf) to save tokens and enable page citations. If a PDF has fewer than about 40 characters per page it is treated as scanned and sent natively. `--native-pdf` forces native sending. |
| Reference material (company intro, past proposals, meeting notes) | `-r PATH` (repeatable) | Same handling as solution material. |
| Extra instructions | `-b "..."` | Appended to the first user message inside `<instructions>`. |
| PowerPoint template | `-t PATH`, default `templates/workday_template.pptx` | Required. Not stored in the repository (confidential). |

All inputs go into the **first user message** as `document` blocks, each with `title` = file name and `context` = one of `RFP`, `Workday 솔루션 자료`, `참고 자료`, followed by one text block with the instruction. Native PDFs are capped at 24 MB in total (API request limit is 32 MB).

## 4. Outputs (in `output/`)

| File | Content |
|---|---|
| `<title>.pptx` | The proposal deck on the Workday template, with an auto-generated appendix "부록. RFP 요구사항 대응표" (requirement compliance table) placed before the closing slide. |
| `<title>_요구사항대응표.csv` | Compliance matrix: ID, category, requirement, response type, response, deck page numbers. UTF-8 with BOM so Excel opens Korean correctly. |
| `<title>.deck.json` | Full deck state (slides + requirements). Autosaved after every change. `--render deck.json -t other.pptx` re-renders without calling the model. |

## 5. Architecture

```
agent_core/          shared by the proposal agent and a sibling "RFP writer" agent
  loop.py            ToolAgent: Anthropic SDK tool runner loop, append-only history
  console.py         UserIO protocol, ConsoleIO, ask_user tool factory
  cli.py             maps API/auth errors to friendly messages + exit codes
proposal_agent/
  cli.py             argument parsing, input loading, interactive revision loop
  inputs.py          files → Claude document blocks (native PDF vs page-marked text)
  deck.py            pydantic models: slide specs, Requirement, ProposalDeck state
  layout.py          geometry + text-fit estimation (rejects overflowing slides)
  render.py          draws slides onto the template, appendix, theme extraction
  tools.py           the agent's tools + Workspace (state, autosave, export)
  prompts.py         system prompt (Korean)
  agent.py           ProposalAgent = ToolAgent + tools + prompt
```

### 5.1 Model and API settings

- SDK: official `anthropic` Python SDK, `client.beta.messages.tool_runner(...)`.
- Model: `claude-opus-5` by default (override with `--model` or `PROPOSAL_AGENT_MODEL`).
- `thinking={"type": "adaptive"}`, `output_config={"effort": "high"}` (`--effort low|medium|high|xhigh|max`).
- `max_tokens=16000` (non-streaming) and `max_iterations=250` (many tool turns per deck).
- Server-side refusal fallback: `betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`.
- Prompt caching: top-level `cache_control={"type": "ephemeral"}`. The large first message (RFP and knowledge) is reused across turns.
- History is **append-only**. After each runner iteration, append `message.to_param()` and the tool-result message to a local mirror; the next user turn starts a new runner over that mirror. If a response contains a `fallback` block, keep only text blocks before the last fallback block when echoing it back.
- After the loop: `stop_reason == "refusal"` or `"max_tokens"` produces a user-visible notice.

### 5.2 Tools

| Tool | Input | Behaviour |
|---|---|---|
| `ask_user` | `questions: list[str]` | Asks the user in one batch. Empty answers become "(no answer — assume and mark)". In `--auto` mode it returns that for every question without prompting. |
| `register_requirements` | `requirements: [{id, category, text}]` | Registers RFP requirements, at most about 40 per call. Re-registering an ID updates its text but keeps any response already recorded. |
| `set_requirement_responses` | `responses: [{id, status, response}]` | `status` ∈ `standard, configuration, extend, integration, partner, roadmap, not_supported, tbd`. Unknown IDs are reported back. |
| `add_slide` | `{slide: SlideSpec, position?: int}` | Validates the spec (pydantic) and **checks text fit**. Errors are returned as tool-result text (not exceptions) so the model can shorten or split the slide. Without `position`, the slide is inserted before a trailing closing slide. |
| `replace_slide` | `{number, slide}` | Same validation as `add_slide`. |
| `remove_slide` | `number` | |
| `read_slide` | `number` | Returns the slide spec as JSON. |
| `get_outline` | – | Slide list with RFP refs, requirement counts by status, requirements not covered by any slide, requirements without a response. |
| `finalize` | – | Renders PPTX and CSV, autosaves JSON, reports coverage gaps. |

The JSON schema for `add_slide` and `replace_slide` is produced from the pydantic models with `discriminator` keys removed and `oneOf` rewritten to `anyOf`. The function itself accepts a plain `dict` and validates it, so the model gets field-level error messages instead of a generic "invalid arguments".

### 5.3 Slide kinds (`SlideSpec`, discriminated by `kind`)

Common optional fields on content slides: `rfp_refs: list[str]` (requirement IDs the slide answers) and `notes: str` (speaker notes).

| kind | Fields | Template layout |
|---|---|---|
| `cover` | `title`, `subtitle` | `Title Slide` |
| `agenda` | `title="목차"`, `items[2..10]` | `Title Only`. Numbered navy boxes, two columns when more than 5 items. |
| `section` | `number`, `title`, `subtitle` | `Section Title` (gradient strip on the left; text is placed to its right). |
| `headline` | `title` (big message), `bullets[1..8]` | `1/2_Headline`. Big message on the left, blue accent bar, bullets on the right. |
| `bullets` | `title`, `message`, `bullets[1..12]` | `Title Only` |
| `two_column` | `title`, `message`, `left{heading, bullets}`, `right{…}` | `Title Only`. Two cards. |
| `cards` | `title`, `message`, `cards[2..4]{heading, bullets}` | `Title Only` |
| `table` | `title`, `message`, `columns[2..6]`, `rows[1..12]`, `column_widths?` | `Title Only` |
| `process` | `title`, `message`, `steps[3..6]{name, period, bullets}` | `Title Only`. Pentagon + chevrons with detail cards below. |
| `closing` | – | `Bumper Slide` |

Text conventions: a bullet starting with `- ` is a sub-bullet, and `**text**` is rendered bold. `message` is the slide's one-sentence conclusion ("head message"), shown under the title.

### 5.4 Layout fitting (`layout.py`)

- Geometry comes from the template's slide size (the Workday template is 10 × 5.625 in). Content area: x 0.5 to 9.5 in; top 1.1 in (1.45 in with a head message); bottom = slide height − 0.45 in.
- Text width is estimated per character: Hangul/CJK 0.95 em, uppercase/digits 0.64 em, lowercase 0.52 em, space 0.28 em. Wrap slack is +8% and line spacing 1.2.
- The largest font size that fits is chosen from a ladder: body 12→9 pt, tables 10→8 pt, titles 18→14 pt.
- If content does not fit even at the smallest size, a `FitError` explains how much it overflows, and the tool returns that text to the model.
- Cards and process boxes size themselves to their content (minimum 1.5 in), with equal heights across a row.
- The appendix paginates by estimated row height, with at most 12 rows per slide.

### 5.5 Visual style (matches the template's own sample slide)

| Token | Value |
|---|---|
| Font | Malgun Gothic (set on both `a:latin` and `a:ea`) |
| Title | 18 pt bold, navy `#0F2E66` (template title placeholder) |
| Head message | 9–11 pt bold navy |
| Body text | `#022043`, line spacing 120%, bullet "•" navy, sub-bullet "–" blue `#1C98E8` |
| Dark boxes (card headers, chevrons, table header) | fill `#1F497D`, white bold text |
| Outline boxes | rounded rectangle, line `#4BACC6` at 50% alpha, 0.75 pt |
| Tables | header `#1F497D`, alternating rows white / `#F3F6FA`, grid `#C9D3E0` |
| Footer | the layout's footer placeholder is cloned with a fresh shape ID and text "Workday Confidential". Page number at bottom right, 8 pt grey. "RFP 대응: <ids>" at 7 pt grey. |

Other rendering rules:
- The template's sample slides are removed; layouts and masters are kept.
- Unused empty placeholders are deleted.
- Layouts are found by name with fallbacks, so any template works: `Section Header` for sections, `Blank` for closing.
- For a non-Workday template, theme colours are derived from the template's `clrScheme` and the font from the most common typeface in its slides.

## 6. Agent behaviour (system prompt, summarised)

The system prompt is in Korean. Its rules:

**Workflow**
1. Analyse the RFP: goals, scope, requirements, mandated proposal structure or page limits, evaluation criteria and weights.
2. Register **all** requirements with their RFP IDs. If the RFP has no IDs, use `REQ-001…`.
3. Decide a response type and short response for every requirement.
4. Ask the user (1–2 batched rounds) only for proposer-specific facts: proposer name, references, team, licence scope, schedule assumptions, pricing format. If there is no answer, write `[확인 필요]` ("needs confirmation"). Never invent these facts.
5. Plan the outline. Use the RFP's mandated structure when one is given. Otherwise use the default outline below, giving more slides to heavily weighted evaluation areas.
6. Build slides, at most 5 per model turn: cover → agenda → chapters → closing.
7. Review with `get_outline` until every requirement appears in some slide's `rfp_refs` and has a response type.
8. Call `finalize`, then report slide count, counts by response type, and every `tbd`, roadmap and `[확인 필요]` item.

**Default outline** (condensed from Workday's standard proposal document)
- Ⅰ Executive summary: customer goals (operational performance, workforce engagement, AI-driven growth, investment value) and differentiators
- Ⅱ Workday for the customer's industry
- Ⅲ Workday AI (Sana, AI agents, Agent System of Record)
- Ⅳ Workday HCM (core HCM, organisation management, self-service, compensation, absence, benefits, reporting)
- Ⅴ Add-on solutions, only if in scope (payroll integration, time tracking, recruiting, learning, talent)
- Ⅵ Technology (security, data model, twice-yearly updates, integration)
- Ⅶ Requirement-by-requirement responses
- Ⅷ Delivery and services (Workday Deployment methodology, plan, team, change management, support)
- Ⅸ Assumptions and conditions
- Pricing only when the RFP asks for it.

**Honesty rules (important)**
- Do not mark a feature `standard` unless the solution material supports it. Use `tbd` and state what must be checked.
- Never present roadmap or unreleased features as available. Name the expected timing and any add-on SKU.
- Only use numbers (customer counts, savings, certifications, rankings) that appear in the material, and keep their year.
- Workday's standard proposal documents contain leftover merge fields and sample customer names (e.g. `[[ShrtCmpNm…]]`, `<customer>'s`). Replace them with the real customer name.
- Speaker notes end with `근거: <file> p.N` ("source: file page N") whenever content comes from the material.

**Korea-specific rules**
- Workday's own payroll covers the US, Canada, UK and Ireland, France and Australia. Korean payroll is proposed through partner payroll integration (Global Payroll Connect or partner connectors), with status `partner` or `integration`.
- Do not use US-only features (ACA, 401k, W-2, COBRA) as evidence for Korean requirements.
- Recruiting, Learning, Time Tracking, Scheduling, Peakon, VNDLY, Extend and AI agents may need separate subscriptions. Separate them from core HCM scope and mark `[라이선스 확인 필요]` ("licence to be confirmed") when unsure.

**Style**
- Every slide has a head message (the claim; the title is the topic).
- Choose the slide kind by content: comparison → `two_column`, three strengths → `cards`, structured data → `table`, phases → `process`, key claim → `headline`.
- 3–6 bullets per slide, each at most two lines, concrete with numbers and Workday feature names (English names kept).
- Korean proposal register: noun-ending phrases such as "~제공", "~지원함".
- Don't build a full compliance table by hand; the appendix is generated automatically.

## 7. Data handling and confidentiality

- The Workday template, Workday proposal documents, customer RFPs and outputs are **confidential**. They live only in `templates/`, `knowledge/`, `rfp/` and `output/`, which are git-ignored. The reference repository is **public**.
- Nothing from customer or Workday documents is hard-coded, except general product facts (such as payroll country coverage) in the prompt.
- API usage: documents are sent to the Anthropic API. Follow your organisation's data policy for customer RFPs.

## 8. Testing (no API key needed)

- **Unit tests:** deck operations, requirement coverage, state round-trip, fit errors, rendering every slide kind (python-pptx's built-in template stands in for the confidential Workday template), appendix pagination, input extraction (DOCX, XLSX, PPTX, MD, a handcrafted text PDF, scanned-PDF fallback, HWP rejection).
- **End-to-end:** `httpx2.MockTransport` returns scripted Messages API responses. The test checks request shape (document blocks, `fallbacks`, clean tool schema), that an overflowing slide is rejected back to the model, and that PPTX, CSV and JSON are produced.
- **Visual check:** render a sample deck on the real template, convert with LibreOffice to PDF, and inspect page images.

## 9. Known limitations and next steps

1. **Not yet run end-to-end against the live API** with a real RFP. Output quality, cost and turn count are unmeasured. Measure on 2–3 past RFPs and tune effort, prompt and slide density.
2. The visual design matches the Workday **Corporate PowerPoint Template** and its sample slide. It has not been compared against other Workday deck designs.
3. Text-extracted PDFs lose figure content; `--native-pdf` keeps it at higher token cost.
4. HWP is not supported (convert to PDF).
5. Optional future output: a Word/PDF proposal document in Workday's standard proposal-document format (cover letter, TOC, numbered chapters, Q&A chapter, appendix of assumptions). The deck model and requirement tracking can be reused for it.
6. Very large RFPs (hundreds of requirements) may need more tool turns; `MAX_ITERATIONS` is 250.

## 10. CLI reference

```
python -m proposal_agent RFP [RFP ...]
    -k, --knowledge PATH     solution material (default: ./knowledge/ if present)
    -r, --reference PATH     other reference material
    -b, --brief TEXT         extra instructions
    -t, --template PATH      PowerPoint template (default templates/workday_template.pptx)
    -o, --output PATH        output .pptx path (default output/<title>.pptx)
    --output-dir DIR         default: output
    --auto                   no questions; unknowns become [확인 필요]
    --native-pdf             send solution/reference PDFs natively
    --render DECK_JSON       re-render a saved deck without the model
    --model ID               default claude-opus-5 (env PROPOSAL_AGENT_MODEL)
    --effort LEVEL           low|medium|high|xhigh|max (env PROPOSAL_AGENT_EFFORT)
Environment: ANTHROPIC_API_KEY
Dependencies: anthropic>=1.8, python-pptx, python-docx, openpyxl, pypdf (Python 3.10+)
```
