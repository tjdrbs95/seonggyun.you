import re


def slugify(text: str) -> str:
    """파일 이름으로 쓸 수 있게 바꾼다(한글 유지)."""
    slug = re.sub(r"[^\w가-힣-]+", "-", text.strip().lower()).strip("-")
    return slug[:60] or "rfp"
