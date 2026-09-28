import base64

import docx
import openpyxl
import pytest
from pptx import Presentation

from proposal_agent.inputs import InputError, build_blocks, collect_files, extract_text


def test_extracts_docx_xlsx_pptx_md(tmp_path):
    d = docx.Document()
    d.add_paragraph("1. 사업 개요")
    t = d.add_table(rows=1, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "SFR-001", "통합 인사"
    d.save(tmp_path / "rfp.docx")

    wb = openpyxl.Workbook()
    wb.active.title = "요구사항"
    wb.active.append(["ID", "내용"])
    wb.active.append(["SFR-002", "조직 개편"])
    wb.save(tmp_path / "req.xlsx")

    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = "Workday Skills Cloud"
    prs.save(tmp_path / "sol.pptx")

    (tmp_path / "notes.md").write_text("# 회의록", encoding="utf-8")

    assert "SFR-001 | 통합 인사" in extract_text(tmp_path / "rfp.docx")
    assert "[시트 요구사항]" in extract_text(tmp_path / "req.xlsx")
    assert "[슬라이드 1]\nWorkday Skills Cloud" in extract_text(tmp_path / "sol.pptx")
    assert len(collect_files([tmp_path])) == 4


def test_pdf_becomes_base64_document(tmp_path):
    pdf = tmp_path / "rfp.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    [block] = build_blocks([("RFP", [pdf])])
    assert block["source"]["media_type"] == "application/pdf"
    assert base64.b64decode(block["source"]["data"]) == b"%PDF-1.4 test"
    assert block["context"] == "RFP" and block["title"] == "rfp.pdf"


def test_rejects_hwp_and_missing(tmp_path):
    (tmp_path / "rfp.hwp").write_bytes(b"x")
    with pytest.raises(InputError, match="PDF로 변환"):
        collect_files([tmp_path / "rfp.hwp"])
    with pytest.raises(InputError, match="찾을 수 없습니다"):
        collect_files([tmp_path / "none.pdf"])
