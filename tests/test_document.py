from datetime import date

import pytest

from rfp_agent.document import RFPDocument, slugify


def test_sections_follow_standard_order_then_extras():
    doc = RFPDocument(title="테스트 사업 제안요청서", issuer="테스트공사")
    doc.write_section("appendix_glossary", "용어 정의", title="부록 A. 용어 정의")
    doc.write_section("evaluation", "평가 기준")
    doc.write_section("overview", "개요")

    assert [s.section_id for s in doc.ordered_sections()] == [
        "overview",
        "evaluation",
        "appendix_glossary",
    ]


def test_rewrite_replaces_content_without_duplicating():
    doc = RFPDocument()
    doc.write_section("overview", "초안")
    doc.write_section("overview", "수정본")
    assert len(doc.ordered_sections()) == 1
    assert doc.sections["overview"].content == "수정본"


def test_markdown_render_demotes_headings_and_lists_toc():
    doc = RFPDocument(title="A 사업 RFP", issuer="B기관")
    doc.write_section("overview", "# 배경\n내용\n## 목적\n내용\n#### 세부")
    md = doc.to_markdown(today=date(2026, 9, 28))

    assert md.startswith("# A 사업 RFP\n")
    assert "- 발주 기관: B기관" in md
    assert "- 작성일: 2026-09-28" in md
    assert "## 목차\n\n- 1. 사업 개요" in md
    assert "### 배경" in md and "### 목적" in md and "#### 세부" in md
    assert "\n# 배경" not in md


def test_outline_reports_missing_sections():
    doc = RFPDocument()
    doc.write_section("overview", "개요")
    outline = doc.outline()
    assert "overview: 1. 사업 개요" in outline
    assert "scope: 3. 사업 범위" in outline.split("[미작성 표준 섹션]")[1]


def test_empty_content_rejected():
    with pytest.raises(ValueError):
        RFPDocument().write_section("overview", "   ")


def test_slugify_keeps_korean():
    assert slugify("통합 고객관리시스템 구축 / RFP") == "통합-고객관리시스템-구축-rfp"
    assert slugify("!!!") == "rfp"
