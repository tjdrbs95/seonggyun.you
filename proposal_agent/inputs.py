"""RFP·솔루션 자료 파일을 Claude 입력(document 블록)으로 바꾼다."""

from __future__ import annotations

import base64
from pathlib import Path

TEXT_SUFFIXES = {".md", ".txt", ".csv", ".tsv", ".json"}
SUPPORTED = TEXT_SUFFIXES | {".pdf", ".docx", ".pptx", ".xlsx"}
# 요청 한 건의 최대 크기는 32MB. 여유를 두고 원본 그대로 보내는 PDF 합계를 제한한다.
MAX_PDF_BYTES = 24 * 1024 * 1024
# 페이지당 평균 글자 수가 이보다 적으면 스캔 문서로 보고 원본 PDF로 보낸다.
MIN_CHARS_PER_PAGE = 40


class InputError(ValueError):
    pass


def collect_files(paths: list[Path]) -> list[Path]:
    """파일과 폴더(하위 포함)에서 지원하는 문서를 모은다."""
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files += sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED
                            and not p.name.startswith(("~$", ".")))
        elif path.is_file():
            if path.suffix.lower() == ".hwp" or path.suffix.lower() == ".hwpx":
                raise InputError(f"한글(HWP) 파일은 읽을 수 없습니다. PDF로 변환해 주세요: {path}")
            if path.suffix.lower() not in SUPPORTED:
                raise InputError(f"지원하지 않는 형식입니다({', '.join(sorted(SUPPORTED))}): {path}")
            files.append(path)
        else:
            raise InputError(f"파일을 찾을 수 없습니다: {path}")
    return files


def document_block(path: Path, context: str, pdf_as_text: bool = False) -> dict:
    """파일 하나를 document 블록으로 만든다.

    RFP PDF는 표·서식을 살리려고 원본 그대로 보내고, 분량이 많은 솔루션 자료 PDF는
    pdf_as_text=True로 페이지 번호를 붙인 텍스트로 보내 토큰을 아낀다.
    """
    suffix = path.suffix.lower()
    if suffix == ".pdf" and pdf_as_text:
        text = pdf_text(path)
        if text is not None:
            source = {"type": "text", "media_type": "text/plain", "data": text}
            return {"type": "document", "source": source, "title": path.name, "context": context}
    if suffix == ".pdf":
        data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
        source = {"type": "base64", "media_type": "application/pdf", "data": data}
    else:
        text = extract_text(path)
        if not text.strip():
            raise InputError(f"텍스트를 추출하지 못했습니다(이미지 위주 문서라면 PDF로 주세요): {path}")
        source = {"type": "text", "media_type": "text/plain", "data": text}
    return {"type": "document", "source": source, "title": path.name, "context": context}


def build_blocks(groups: list[tuple[str, list[Path], bool]]) -> list[dict]:
    """(설명, 파일 목록, PDF를 텍스트로 보낼지) 묶음을 document 블록 목록으로 만든다."""
    blocks = []
    pdf_bytes = 0
    for context, files, pdf_as_text in groups:
        for path in files:
            block = document_block(path, context, pdf_as_text)
            if block["source"]["type"] == "base64":
                pdf_bytes += path.stat().st_size
                if pdf_bytes > MAX_PDF_BYTES:
                    raise InputError(
                        "원본으로 보내는 PDF 합계가 24MB를 넘습니다. 필요한 부분만 남기거나 텍스트(DOCX/MD)로 바꿔 주세요."
                    )
            blocks.append(block)
    return blocks


def pdf_text(path: Path) -> str | None:
    """PDF에서 페이지 번호를 붙인 텍스트를 뽑는다. 스캔 문서처럼 글자가 거의 없으면 None."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    total = 0
    for i, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "").strip()
        total += len(text)
        if text:
            pages.append(f"[p.{i}]\n{text}")
    if not reader.pages or total < MIN_CHARS_PER_PAGE * len(reader.pages):
        return None
    return "\n\n".join(pages)


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".docx":
        return _docx_text(path)
    if suffix == ".pptx":
        return _pptx_text(path)
    if suffix == ".xlsx":
        return _xlsx_text(path)
    raise InputError(f"지원하지 않는 형식입니다: {path}")


def _docx_text(path: Path) -> str:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = docx.Document(str(path))
    out = []
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = Paragraph(child, doc).text.strip()
            if text:
                out.append(text)
        elif tag == "tbl":
            for row in Table(child, doc).rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                out.append(" | ".join(cells))
    return "\n".join(out)


def _pptx_text(path: Path) -> str:
    from pptx import Presentation

    prs = Presentation(str(path))
    out = []
    for i, slide in enumerate(prs.slides, 1):
        lines = []
        for shape in _walk(slide.shapes):
            if shape.has_text_frame:
                text = shape.text_frame.text.strip()
                if text:
                    lines.append(text)
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    lines.append(" | ".join(c.text.strip().replace("\n", " ") for c in row.cells))
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                lines.append(f"(노트) {notes}")
        if lines:
            out.append(f"[슬라이드 {i}]\n" + "\n".join(lines))
    return "\n\n".join(out)


def _walk(shapes):
    for shape in shapes:
        if shape.shape_type == 6:  # 그룹
            yield from _walk(shape.shapes)
        else:
            yield shape


def _xlsx_text(path: Path) -> str:
    import openpyxl

    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            cells = ["" if v is None else str(v).replace("\n", " ") for v in row]
            if any(cells):
                rows.append("\t".join(cells).rstrip())
        if rows:
            out.append(f"[시트 {ws.title}]\n" + "\n".join(rows))
    return "\n\n".join(out)
